# Airflow local setup and runbook

Run Step 6 orchestration (lexical ingestion, entity graph, enrichment, conversation memory) locally with Airflow and Neo4j.

## Prerequisites

- Docker and Docker Compose
- (Optional) Neo4j Browser or `cypher-shell` for inspection queries

## 1. Start Airflow locally

From the **repo root**:

```bash
# Start Neo4j and Airflow (and optionally api/web)
docker compose up -d neo4j airflow

# Wait for Airflow to be ready (webserver on 8080)
# Then open: http://localhost:8080
# Login: admin / admin (or _AIRFLOW_WWW_USER_* from docker-compose)
```

- **Airflow UI**: http://localhost:8080  
- **Neo4j Browser**: http://localhost:7474 (neo4j / password123)  
- DAGs are loaded from `orchestration/airflow/dags/`; plugins from `orchestration/airflow/plugins/`.  
- Staged data and input files under `data/` are mounted at `/opt/airflow/data` in the Airflow container.

## 2. Trigger each DAG

All four DAGs are **manual** (no schedule). Trigger from the UI or CLI.

| DAG ID | Purpose | Params / notes |
|--------|---------|----------------|
| **lexical_ingestion_dag** | Load PDFs → parse → chunk → embed → write lexical graph | `source_path` (default `/opt/airflow/data/raw/pdfs`). Put PDFs in `data/raw/pdfs/` (or equivalent path in container). |
| **entity_graph_dag** | Fetch unprocessed chunks → extract entities/relations → resolve → write hybrid graph | No params. Only chunks without `MENTIONS->Entity` are processed. |
| **answer_graph_enrichment_dag** | Project graph to GDS → PageRank → Leiden → FastRP → write back scores → validate | No params. Requires existing Entity/Chunk/Document graph. |
| **conversation_candidate_dag** | Ingest transcript → extract claims → validate → auto-merge safe → create review tasks | `input_path` (default `/opt/airflow/data/raw/conversations`). Put conversation JSON in that path. |

**UI:** Open the DAG → **Trigger DAG** (optionally **Trigger w/ config** to pass params as JSON, e.g. `{"source_path": "/opt/airflow/data/raw/pdfs"}`).

**CLI (inside Airflow container):**

```bash
docker compose exec airflow airflow dags trigger lexical_ingestion_dag
docker compose exec airflow airflow dags trigger entity_graph_dag
docker compose exec airflow airflow dags trigger answer_graph_enrichment_dag
docker compose exec airflow airflow dags trigger conversation_candidate_dag \
  --conf '{"input_path": "/opt/airflow/data/raw/conversations"}'
```

## 3. Inspect PipelineRun and TaskRun

### 3.1 From the Airflow UI

- **DAG** → **Runs**: see run history and status.  
- **Run** → **Task instances**: see each task’s state (success / failed / skipped) and logs.  
- **PipelineRun / TaskRun in Neo4j**: created at DAG start and at each task start; status is updated on success, failure, or skip. Use Cypher (below) to query them.

### 3.2 Cypher: pipeline and task observability

Run these in Neo4j Browser or `cypher-shell` (e.g. `docker compose exec neo4j cypher-shell -u neo4j -p password123`).

**Show recent pipeline runs**

```cypher
MATCH (p:PipelineRun)
RETURN p.id, p.dag_id, p.run_id, p.status, p.started_at, p.finished_at
ORDER BY p.started_at DESC
LIMIT 20;
```

**Show tasks for one pipeline run**  
Use `p.id` (equals `dag_id + "_" + run_id`, e.g. `lexical_ingestion_dag_manual__2025-03-13T12:00:00+00:00`) or `p.run_id` (Airflow run_id):

```cypher
MATCH (p:PipelineRun)-[:RAN_TASK]->(t:TaskRun)
WHERE p.id = $pipeline_run_id
RETURN t.task_id, t.status, t.started_at, t.finished_at
ORDER BY t.started_at;
```

Example with literal id:

```cypher
MATCH (p:PipelineRun)-[:RAN_TASK]->(t:TaskRun)
WHERE p.id = 'lexical_ingestion_dag_manual__2025-03-13T12:00:00+00:00'
RETURN t.task_id, t.status, t.started_at, t.finished_at
ORDER BY t.started_at;
```

**Show what a task wrote** (replace `$task_run_id` with e.g. `lexical_ingestion_dag_manual__2025-03-13T12:00:00+00:00_write_lexical_graph`)

```cypher
MATCH (t:TaskRun)-[:WROTE]->(n)
WHERE t.id = $task_run_id
RETURN labels(n), n.id
LIMIT 100;
```

### 3.3 Inspection by pipeline type

**What was ingested (lexical)**  
Documents and chunks created by a run:

```cypher
MATCH (p:PipelineRun {id: $pipeline_run_id})-[:RAN_TASK]->(tr:TaskRun)-[:WROTE]->(n)
WHERE n:Document OR n:Chunk
RETURN tr.task_id, labels(n)[0], n.id
ORDER BY tr.task_id, n.id
LIMIT 200;
```

**What was extracted (entity graph)**  
Entities and relations written by the entity graph DAG:

```cypher
MATCH (p:PipelineRun)-[:RAN_TASK]->(tr:TaskRun)-[:WROTE]->(n)
WHERE p.dag_id = 'entity_graph_dag' AND (n:Entity OR n:Chunk)
RETURN p.run_id, tr.task_id, labels(n)[0], n.id
ORDER BY p.started_at DESC, tr.task_id
LIMIT 100;
```

**What was enriched (GDS)**  
Nodes with GDS-written properties (pagerank, communityId, graphEmbedding):

```cypher
MATCH (n)
WHERE n.pagerank IS NOT NULL OR n.communityId IS NOT NULL OR n.graphEmbedding IS NOT NULL
RETURN labels(n), n.id,
       n.pagerank IS NOT NULL AS has_pagerank,
       n.communityId IS NOT NULL AS has_community,
       n.graphEmbedding IS NOT NULL AS has_embedding
LIMIT 50;
```

**Review queue (conversation candidates)**  
Claims that need review:

```cypher
MATCH (c:CandidateClaim)-[:HAS_STATUS]->(v:ValidationTask)
WHERE v.status = 'needs-review'
RETURN c.id, c.text, v.reason
ORDER BY c.id
LIMIT 100;
```

## 4. Rerun a failed pipeline

1. **Inspect**: Use the Cypher queries above to see which PipelineRun and TaskRuns failed.  
2. **Fix**: Address the cause (e.g. input path, Neo4j connectivity, missing data).  
3. **Rerun**:
   - **Full DAG**: In the UI, open the DAG and **Trigger DAG** again (new run_id; new PipelineRun in Neo4j).  
   - **From a task**: Use **Clear** on the failed (and optionally downstream) tasks, then let the scheduler run them again. Clearing does not delete PipelineRun/TaskRun nodes; new task runs update or create TaskRun status.  
4. **Idempotency**: Lexical and entity writers use MERGE; enrichment overwrites properties; conversation memory uses MERGE. Rerunning the same or a new DAG run should not create uncontrolled duplicates.

## 5. Run orchestration tests

DAG structure tests (import, task IDs, dependencies, callables, metadata) require Airflow and project dependencies. From repo root, with a venv that has `airflow` and project packages installed:

```bash
# Optional: use the same env as the Airflow image
pip install -r orchestration/airflow/requirements.txt  # if present
pip install apache-airflow  # or match Dockerfile

# Run orchestration tests (conftest adds dags/ and plugins/ to path)
pytest tests/orchestration/ -v
```

If `airflow` is not installed, those tests are skipped.

## Summary

| Step | Action |
|------|--------|
| Start | `docker compose up -d neo4j airflow` |
| UI | http://localhost:8080 (admin / admin) |
| Trigger | DAG → Trigger DAG (with params if needed) |
| Inspect runs | Airflow UI → DAG runs + task instances |
| Inspect graph | Neo4j Cypher: PipelineRun, TaskRun, WROTE, and pipeline-specific queries above |
| Rerun | Trigger DAG again or Clear failed tasks and re-run |
