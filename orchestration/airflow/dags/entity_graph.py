"""
Entity graph DAG: read parent chunks -> extract entities -> extract relations
-> resolve entities -> write hybrid graph -> validate.
Thin orchestration: each task calls existing sensemap (entity/relation/resolution/neo4j) functions.
PipelineRun/TaskRun metadata in Neo4j; WROTE links where possible.

Idempotency: only_unprocessed=True so only chunks without MENTIONS->Entity are processed; writers use MERGE.
Skip: when no unprocessed chunks, first task returns skipped and TaskRun status set to "skipped".
Retries: 1 for fetch/extract/resolve/validate; 0 for write_entity_graph (no retry on merge/write).
Failures: on_failure_callback marks TaskRun and PipelineRun failed; partial outputs remain traceable.
"""
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, OPENAI_API_KEY
from sensemap.entity_extraction import extract_entities
from sensemap.relation_extraction import extract_relations
from sensemap.resolution import resolve_entities
from sensemap.neo4j_entity_writer import (
    load_chunks_for_extraction,
    load_entities_for_resolution,
    write_entities_and_mentions,
    write_relations,
    apply_resolution,
)
from sensemap.staged_io import read_json, write_json

DAG_ID = "entity_graph_dag"
START_TASK_ID = "start_pipeline_run"
CLOSE_TASK_ID = "close_pipeline_run"
CHUNK_LIMIT = 0
FUZZY_THRESHOLD = 85


def _run_id(context):
    return context["run_id"]


def _pipeline_run_id(context):
    return context["ti"].xcom_pull(task_ids=START_TASK_ID)


def _task_run_id(pipeline_run_id: str, task_id: str) -> str:
    return f"{pipeline_run_id}_{task_id}"


def _with_metadata(task_id: str, run_content_fn):
    """Create TaskRun (running), run content fn, update TaskRun (success), link WROTE when possible."""

    def _wrapped(**context):
        pipeline_run_id = _pipeline_run_id(context)
        if not pipeline_run_id:
            raise ValueError("Missing pipeline_run_id from start_pipeline_run")
        run_id = _run_id(context)
        tr_id = _task_run_id(pipeline_run_id, task_id)
        now = datetime.now(timezone.utc)
        try:
            from neo4j_hooks import Neo4jHook
            from services.orchestration.pipeline_metadata import (
                create_task_run,
                update_task_run_status,
                link_task_run_wrote,
            )
            from shared.python.models.pipeline_runs import TaskRunRecord
            with Neo4jHook().get_session() as session:
                create_task_run(
                    session,
                    TaskRunRecord(
                        id=tr_id,
                        pipeline_run_id=pipeline_run_id,
                        task_id=task_id,
                        status="running",
                        started_at=now,
                        finished_at=None,
                        metadata={"run_id": run_id},
                    ),
                    pipeline_run_id,
                )
        except Exception:
            pass
        try:
            result = run_content_fn(**context)
            output_node_ids = None
            status = "success"
            metadata_update = None
            if isinstance(result, dict):
                if result.get("skipped"):
                    status = "skipped"
                    metadata_update = {"skipped": True, "reason": result.get("reason", "")}
                elif "output_node_ids" in result:
                    output_node_ids = result["output_node_ids"]
            elif isinstance(result, list):
                output_node_ids = result
            now_end = datetime.now(timezone.utc)
            try:
                from neo4j_hooks import Neo4jHook
                from services.orchestration.pipeline_metadata import update_task_run_status, link_task_run_wrote
                with Neo4jHook().get_session() as session:
                    update_task_run_status(
                        session, tr_id, status, finished_at=now_end, metadata_update=metadata_update
                    )
                    if output_node_ids and status == "success":
                        link_task_run_wrote(session, tr_id, output_node_ids)
            except Exception:
                pass
            return result
        except Exception as e:
            now_end = datetime.now(timezone.utc)
            try:
                from neo4j_hooks import Neo4jHook
                from services.orchestration.pipeline_metadata import update_task_run_status
                with Neo4jHook().get_session() as session:
                    update_task_run_status(session, tr_id, "failed", finished_at=now_end, metadata_update={"error": str(e)})
            except Exception:
                pass
            raise

    return _wrapped


def _on_failure_callback(context):
    try:
        from neo4j_hooks import Neo4jHook
        from services.orchestration.pipeline_metadata import update_task_run_status, update_pipeline_run_status
        pipeline_run_id = context["ti"].xcom_pull(task_ids=START_TASK_ID)
        task_id = context.get("task").task_id
        if pipeline_run_id and task_id and task_id != START_TASK_ID:
            tr_id = _task_run_id(pipeline_run_id, task_id)
            with Neo4jHook().get_session() as session:
                update_task_run_status(session, tr_id, "failed", metadata_update={"error": str(context.get("exception"))})
                update_pipeline_run_status(session, pipeline_run_id, "failed")
    except Exception:
        pass


# --- Pipeline start / end ---


def task_start_pipeline_run(**context):
    run_id = _run_id(context)
    pipeline_run_id = f"{DAG_ID}_{run_id}"
    now = datetime.now(timezone.utc)
    try:
        from neo4j_hooks import Neo4jHook
        from services.orchestration.pipeline_metadata import create_pipeline_run
        from shared.python.models.pipeline_runs import PipelineRunRecord
        with Neo4jHook().get_session() as session:
            create_pipeline_run(
                session,
                PipelineRunRecord(
                    id=pipeline_run_id,
                    dag_id=DAG_ID,
                    run_id=run_id,
                    status="running",
                    started_at=now,
                    finished_at=None,
                    metadata={},
                ),
            )
    except Exception:
        pass
    return pipeline_run_id


def task_close_pipeline_run(**context):
    pipeline_run_id = _pipeline_run_id(context)
    if pipeline_run_id:
        try:
            from neo4j_hooks import Neo4jHook
            from services.orchestration.pipeline_metadata import update_pipeline_run_status
            with Neo4jHook().get_session() as session:
                update_pipeline_run_status(session, pipeline_run_id, "success")
        except Exception:
            pass
    return pipeline_run_id


# --- Content tasks (call existing sensemap functions) ---


def _task_fetch_unprocessed_parent_chunks(**context):
    run_id = _run_id(context)
    chunks = load_chunks_for_extraction(
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
        limit=CHUNK_LIMIT,
        only_unprocessed=True,
    )
    write_json(run_id, "chunks", [{"chunk_id": cid, "text": t} for cid, t in chunks])
    if not chunks:
        return {"run_id": run_id, "skipped": True, "reason": "no unprocessed chunks"}
    return run_id


def _task_extract_entities(**context):
    run_id = context["ti"].xcom_pull(task_ids="fetch_unprocessed_parent_chunks")
    if isinstance(run_id, dict):
        run_id = run_id.get("run_id")
    if not run_id:
        return {"run_id": None, "skipped": True, "reason": "no run_id from fetch"}
    chunks = read_json(run_id, "chunks")
    chunk_entities = []
    for item in chunks:
        entities = extract_entities(
            item["text"], use_llm=bool(OPENAI_API_KEY), api_key=OPENAI_API_KEY or None
        )
        if entities:
            chunk_entities.append({"chunk_id": item["chunk_id"], "entities": entities})
    write_json(run_id, "chunk_entities", chunk_entities)
    chunk_entities_tuples = [(x["chunk_id"], x["entities"]) for x in chunk_entities]
    write_entities_and_mentions(chunk_entities_tuples, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    entity_ids = [e.get("id") for ce in chunk_entities_tuples for e in ce[1] if e.get("id")]
    return {"run_id": run_id, "output_node_ids": entity_ids}


def _task_extract_relations(**context):
    run_id = context["ti"].xcom_pull(task_ids="extract_entities")
    if isinstance(run_id, dict):
        run_id = run_id.get("run_id", run_id)
    chunks = {x["chunk_id"]: x["text"] for x in read_json(run_id, "chunks")}
    chunk_entities = read_json(run_id, "chunk_entities")
    relations = []
    for item in chunk_entities:
        cid, entities = item["chunk_id"], item["entities"]
        if len(entities) < 2:
            continue
        text = chunks.get(cid, "")
        pairs = []
        for i, a in enumerate(entities):
            for b in entities[i + 1 :]:
                pairs.append((a["id"], a["name"], b["id"], b["name"]))
        rels = extract_relations(text, pairs, use_llm=bool(OPENAI_API_KEY), api_key=OPENAI_API_KEY or None)
        relations.extend([list(r) for r in rels])
    write_json(run_id, "relations", relations)
    return run_id


def _task_resolve_entities(**context):
    run_id = context["ti"].xcom_pull(task_ids="extract_relations")
    entities = load_entities_for_resolution(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    id_to_canonical = resolve_entities(entities, fuzzy_threshold=FUZZY_THRESHOLD)
    write_json(run_id, "id_to_canonical", id_to_canonical)
    return run_id


def _task_write_entity_graph(**context):
    run_id = context["ti"].xcom_pull(task_ids="resolve_entities")
    rels = read_json(run_id, "relations")
    relations = [tuple(r) for r in rels]
    id_to_canonical = read_json(run_id, "id_to_canonical")
    write_relations(relations, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    apply_resolution(id_to_canonical, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return run_id


def _task_validate_entity_graph(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_entity_graph")
    if isinstance(run_id, dict):
        run_id = run_id.get("run_id")
    chunk_entities = read_json(run_id, "chunk_entities")
    relations = read_json(run_id, "relations")
    id_to_canonical = read_json(run_id, "id_to_canonical")
    if not chunk_entities and not relations:
        return run_id
    return run_id


with DAG(
    dag_id=DAG_ID,
    default_args={
        "owner": "sensemap",
        "retries": 1,
        "on_failure_callback": _on_failure_callback,
    },
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["entity", "graph", "extraction"],
) as dag:
    start = PythonOperator(task_id=START_TASK_ID, python_callable=task_start_pipeline_run)
    fetch_chunks = PythonOperator(
        task_id="fetch_unprocessed_parent_chunks",
        python_callable=_with_metadata("fetch_unprocessed_parent_chunks", _task_fetch_unprocessed_parent_chunks),
    )
    extract_ent = PythonOperator(
        task_id="extract_entities",
        python_callable=_with_metadata("extract_entities", _task_extract_entities),
    )
    extract_rel = PythonOperator(
        task_id="extract_relations",
        python_callable=_with_metadata("extract_relations", _task_extract_relations),
    )
    resolve_ent = PythonOperator(
        task_id="resolve_entities",
        python_callable=_with_metadata("resolve_entities", _task_resolve_entities),
    )
    write_graph = PythonOperator(
        task_id="write_entity_graph",
        python_callable=_with_metadata("write_entity_graph", _task_write_entity_graph),
        retries=0,
    )
    validate_entity = PythonOperator(
        task_id="validate_entity_graph",
        python_callable=_with_metadata("validate_entity_graph", _task_validate_entity_graph),
    )
    close = PythonOperator(task_id=CLOSE_TASK_ID, python_callable=task_close_pipeline_run)

    start >> fetch_chunks >> extract_ent >> extract_rel >> resolve_ent >> write_graph >> validate_entity >> close
