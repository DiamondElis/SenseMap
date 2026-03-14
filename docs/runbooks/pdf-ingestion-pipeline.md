# PDF ingestion pipeline (ingest_pdf_pipeline)

First production ingestion: **PDF → load → parse → parent/child chunks → embeddings → Neo4j lexical graph**.

## DAG tasks (order)

1. **load_documents** — List PDF paths under `source_path` (default `/opt/airflow/data/raw/pdfs`).
2. **parse_documents** — Extract text per PDF; output parsed docs.
3. **create_parent_child_chunks** — Parent chunks (e.g. 2048 chars), then child chunks (e.g. 512 chars) for parent-child retrieval.
4. **generate_chunk_embeddings** — Embed child chunk text (1536 dims, OpenAI or placeholder).
5. **write_documents_to_neo4j** — Create `Document` nodes.
6. **write_chunks_to_neo4j** — Create `Chunk` nodes (parents and children with embeddings); `PART_OF` to Document and parent.
7. **create_part_of_and_next_chunk_edges** — `NEXT_CHUNK` between consecutive parents and between consecutive children.
8. **validate_ingestion_run** — Assert document and chunk counts for this run.

## Running

1. **Neo4j schema**: Run `neo4j/cypher/constraints.cypher` and `neo4j/cypher/indexes.cypher` once (see `neo4j/README.md`).
2. **Input**: Place PDFs in `data/raw/pdfs/` (or set DAG param `source_path` to another path inside the Airflow container, e.g. `/opt/airflow/data/raw/pdfs`).
3. **Trigger**: In Airflow UI (http://localhost:8080), open DAG **ingest_pdf_pipeline** and trigger a run (optionally override `source_path` in params).
4. **Staged data**: Per-run intermediates under `data/staged/<run_id>/` (paths, parsed_docs, parent_chunks, child_chunks).

## Config (env)

- **NEO4J_URI**, **NEO4J_USER**, **NEO4J_PASSWORD** — Neo4j (from Airflow container use `bolt://neo4j:7687`).
- **OPENAI_API_KEY** — For real embeddings; if unset, child chunks get zero vectors (pipeline still runs).
- **PARENT_CHUNK_SIZE**, **PARENT_CHUNK_OVERLAP**, **CHILD_CHUNK_SIZE**, **CHILD_CHUNK_OVERLAP** — Optional; defaults in `sensemap.config`.

## Airflow image

The Compose Airflow service is built from `orchestration/airflow/Dockerfile`, which installs `neo4j`, `openai`, and `pypdf` from `orchestration/airflow/requirements.txt`.
