"""
Lexical ingestion DAG: load document -> parse -> chunk -> embed -> write lexical graph -> validate.
Thin orchestration: each task calls existing Step 1/Step 2 (sensemap) functions.
PipelineRun/TaskRun metadata in Neo4j; WROTE links where possible.

Idempotency: writers use MERGE by node id; reruns overwrite, no duplicate nodes.
Retries: 1 for load/parse/chunk/embed/validate; 0 for write_lexical_graph (no retry on write).
Failures: on_failure_callback marks TaskRun and PipelineRun failed; partial outputs remain traceable.
"""
from datetime import datetime, timezone
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import (
    CHILD_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    EMBEDDING_MODEL,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    OPENAI_API_KEY,
    PARENT_CHUNK_OVERLAP,
    PARENT_CHUNK_SIZE,
)
from sensemap.load_documents import load_documents
from sensemap.parse_documents import parse_documents
from sensemap.chunking import create_parent_child_chunks
from sensemap.embeddings import generate_chunk_embeddings
from sensemap.neo4j_writer import (
    write_documents,
    write_parent_chunks,
    write_child_chunks,
    create_part_of_and_next_chunk_edges,
    validate_ingestion_run,
)
from sensemap.staged_io import read_json, write_json

DAG_ID = "lexical_ingestion_dag"
DEFAULT_SOURCE_PATH = "/opt/airflow/data/raw/pdfs"
START_TASK_ID = "start_pipeline_run"
CLOSE_TASK_ID = "close_pipeline_run"


def _run_id(context):
    return context["run_id"]


def _source_path(context):
    return context["params"].get("source_path", DEFAULT_SOURCE_PATH)


def _pipeline_run_id(context):
    return context["ti"].xcom_pull(task_ids=START_TASK_ID)


def _task_run_id(pipeline_run_id: str, task_id: str) -> str:
    return f"{pipeline_run_id}_{task_id}"


def _with_metadata(task_id: str, run_content_fn):
    """Run content fn; create TaskRun (running), run fn, update TaskRun (success), link WROTE when possible."""

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
            hook = Neo4jHook()
            with hook.get_session() as session:
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
            if isinstance(result, dict) and "output_node_ids" in result:
                output_node_ids = result["output_node_ids"]
            elif isinstance(result, list):
                output_node_ids = result
            now_end = datetime.now(timezone.utc)
            try:
                from neo4j_hooks import Neo4jHook
                from services.orchestration.pipeline_metadata import update_task_run_status, link_task_run_wrote
                with Neo4jHook().get_session() as session:
                    update_task_run_status(session, tr_id, "success", finished_at=now_end)
                    if output_node_ids:
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
    """Update TaskRun and PipelineRun to failed."""
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
                    metadata={"source_path": _source_path(context)},
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


def _task_load_document(**context):
    run_id = _run_id(context)
    paths = load_documents(_source_path(context))
    path_strs = [str(p) for p in paths]
    write_json(run_id, "paths", path_strs)
    return run_id


def _task_parse_document(**context):
    run_id = context["ti"].xcom_pull(task_ids="load_document")
    path_strs = read_json(run_id, "paths")
    parsed_docs = parse_documents([Path(p) for p in path_strs])
    write_json(run_id, "parsed_docs", parsed_docs)
    return run_id


def _task_chunk_document(**context):
    run_id = context["ti"].xcom_pull(task_ids="parse_document")
    parsed_docs = read_json(run_id, "parsed_docs")
    parent_chunks, child_chunks = create_parent_child_chunks(
        parsed_docs,
        parent_chunk_size=PARENT_CHUNK_SIZE,
        parent_chunk_overlap=PARENT_CHUNK_OVERLAP,
        child_chunk_size=CHILD_CHUNK_SIZE,
        child_chunk_overlap=CHILD_CHUNK_OVERLAP,
    )
    write_json(run_id, "parent_chunks", parent_chunks)
    write_json(run_id, "child_chunks", child_chunks)
    return run_id


def _task_embed_child_chunks(**context):
    run_id = context["ti"].xcom_pull(task_ids="chunk_document")
    child_chunks = read_json(run_id, "child_chunks")
    child_chunks = generate_chunk_embeddings(
        child_chunks, model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY or None
    )
    write_json(run_id, "child_chunks", child_chunks)
    return run_id


def _task_write_lexical_graph(**context):
    run_id = context["ti"].xcom_pull(task_ids="embed_child_chunks")
    parsed_docs = read_json(run_id, "parsed_docs")
    parent_chunks = read_json(run_id, "parent_chunks")
    child_chunks = read_json(run_id, "child_chunks")
    write_documents(parsed_docs, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    write_parent_chunks(parent_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    write_child_chunks(child_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    create_part_of_and_next_chunk_edges(
        parent_chunks, child_chunks, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    )
    doc_ids = [d.get("id") for d in parsed_docs if d.get("id")]
    chunk_ids = [p.get("id") for p in parent_chunks if p.get("id")] + [c.get("id") for c in child_chunks if c.get("id")]
    return {"run_id": run_id, "output_node_ids": doc_ids + chunk_ids}


def _task_validate_lexical_graph(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_lexical_graph")
    if isinstance(run_id, dict):
        run_id = run_id.get("run_id")
    parsed_docs = read_json(run_id, "parsed_docs")
    parent_chunks = read_json(run_id, "parent_chunks")
    child_chunks = read_json(run_id, "child_chunks")
    validate_ingestion_run(
        run_id,
        expected_docs=len(parsed_docs),
        expected_parent_chunks=len(parent_chunks),
        expected_child_chunks=len(child_chunks),
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )
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
    tags=["lexical", "ingestion"],
    params={"source_path": DEFAULT_SOURCE_PATH},
) as dag:
    start = PythonOperator(task_id=START_TASK_ID, python_callable=task_start_pipeline_run)
    load_document = PythonOperator(
        task_id="load_document",
        python_callable=_with_metadata("load_document", _task_load_document),
    )
    parse_document = PythonOperator(
        task_id="parse_document",
        python_callable=_with_metadata("parse_document", _task_parse_document),
    )
    chunk_document = PythonOperator(
        task_id="chunk_document",
        python_callable=_with_metadata("chunk_document", _task_chunk_document),
    )
    embed_child_chunks = PythonOperator(
        task_id="embed_child_chunks",
        python_callable=_with_metadata("embed_child_chunks", _task_embed_child_chunks),
    )
    write_lexical_graph = PythonOperator(
        task_id="write_lexical_graph",
        python_callable=_with_metadata("write_lexical_graph", _task_write_lexical_graph),
        retries=0,
    )
    validate_lexical_graph = PythonOperator(
        task_id="validate_lexical_graph",
        python_callable=_with_metadata("validate_lexical_graph", _task_validate_lexical_graph),
    )
    close = PythonOperator(task_id=CLOSE_TASK_ID, python_callable=task_close_pipeline_run)

    start >> load_document >> parse_document >> chunk_document >> embed_child_chunks >> write_lexical_graph >> validate_lexical_graph >> close
