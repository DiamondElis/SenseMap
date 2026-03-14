"""
PDF ingestion pipeline DAG:
  load_documents -> parse_documents -> create_parent_child_chunks
  -> generate_chunk_embeddings -> write_documents_to_neo4j -> write_chunks_to_neo4j
  -> create_part_of_and_next_chunk_edges -> validate_ingestion_run
"""
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    OPENAI_API_KEY,
    CHILD_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    EMBEDDING_MODEL,
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
from sensemap.staged_io import ensure_staged, read_json, write_json

DEFAULT_SOURCE_PATH = "/opt/airflow/data/raw/pdfs"


def _run_id(context) -> str:
    return context["run_id"]


def _source_path(context) -> str:
    return context["params"].get("source_path", DEFAULT_SOURCE_PATH)


def task_load_documents(**context):
    run_id = _run_id(context)
    source_path = _source_path(context)
    paths = load_documents(source_path)
    path_strs = [str(p) for p in paths]
    write_json(run_id, "paths", path_strs)
    return run_id


def task_parse_documents(**context):
    run_id = context["ti"].xcom_pull(task_ids="load_documents")
    path_strs = read_json(run_id, "paths")
    paths = [Path(p) for p in path_strs]
    parsed_docs = parse_documents(paths)
    write_json(run_id, "parsed_docs", parsed_docs)
    return run_id


def task_create_parent_child_chunks(**context):
    run_id = context["ti"].xcom_pull(task_ids="parse_documents")
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


def task_generate_chunk_embeddings(**context):
    run_id = context["ti"].xcom_pull(task_ids="create_parent_child_chunks")
    child_chunks = read_json(run_id, "child_chunks")
    child_chunks = generate_chunk_embeddings(
        child_chunks,
        model=EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY or None,
    )
    write_json(run_id, "child_chunks", child_chunks)
    return run_id


def task_write_documents_to_neo4j(**context):
    run_id = context["ti"].xcom_pull(task_ids="generate_chunk_embeddings")
    parsed_docs = read_json(run_id, "parsed_docs")
    write_documents(parsed_docs, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return run_id


def task_write_chunks_to_neo4j(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_documents_to_neo4j")
    parent_chunks = read_json(run_id, "parent_chunks")
    child_chunks = read_json(run_id, "child_chunks")
    write_parent_chunks(parent_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    write_child_chunks(child_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return run_id


def task_create_part_of_and_next_chunk_edges(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_chunks_to_neo4j")
    parent_chunks = read_json(run_id, "parent_chunks")
    child_chunks = read_json(run_id, "child_chunks")
    create_part_of_and_next_chunk_edges(
        parent_chunks, child_chunks, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    )
    return run_id


def task_validate_ingestion_run(**context):
    run_id = context["ti"].xcom_pull(task_ids="create_part_of_and_next_chunk_edges")
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


with DAG(
    dag_id="ingest_pdf_pipeline",
    default_args={
        "owner": "sensemap",
        "retries": 1,
    },
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["ingestion", "pdf", "lexical-graph"],
    params={"source_path": DEFAULT_SOURCE_PATH},
) as dag:
    load_documents_task = PythonOperator(
        task_id="load_documents",
        python_callable=task_load_documents,
    )
    parse_documents_task = PythonOperator(
        task_id="parse_documents",
        python_callable=task_parse_documents,
    )
    create_parent_child_chunks_task = PythonOperator(
        task_id="create_parent_child_chunks",
        python_callable=task_create_parent_child_chunks,
    )
    generate_chunk_embeddings_task = PythonOperator(
        task_id="generate_chunk_embeddings",
        python_callable=task_generate_chunk_embeddings,
    )
    write_documents_to_neo4j_task = PythonOperator(
        task_id="write_documents_to_neo4j",
        python_callable=task_write_documents_to_neo4j,
    )
    write_chunks_to_neo4j_task = PythonOperator(
        task_id="write_chunks_to_neo4j",
        python_callable=task_write_chunks_to_neo4j,
    )
    create_part_of_and_next_chunk_edges_task = PythonOperator(
        task_id="create_part_of_and_next_chunk_edges",
        python_callable=task_create_part_of_and_next_chunk_edges,
    )
    validate_ingestion_run_task = PythonOperator(
        task_id="validate_ingestion_run",
        python_callable=task_validate_ingestion_run,
    )

    (
        load_documents_task
        >> parse_documents_task
        >> create_parent_child_chunks_task
        >> generate_chunk_embeddings_task
        >> write_documents_to_neo4j_task
        >> write_chunks_to_neo4j_task
        >> create_part_of_and_next_chunk_edges_task
        >> validate_ingestion_run_task
    )
