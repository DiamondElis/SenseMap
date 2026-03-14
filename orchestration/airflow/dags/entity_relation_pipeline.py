"""
Entity extraction → relation extraction → resolution → hybrid graph.
Run after baseline retrieval (and lexical graph) is in place.
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY
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

DAG_ID = "entity_relation_pipeline"
CHUNK_LIMIT = 0  # 0 = all chunks; set > 0 for testing
FUZZY_THRESHOLD = 85


def _run_id(context):
    return context["run_id"]


def task_load_chunks(**context):
    run_id = _run_id(context)
    chunks = load_chunks_for_extraction(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, limit=CHUNK_LIMIT)
    write_json(run_id, "chunks", [{"chunk_id": cid, "text": t} for cid, t in chunks])
    return run_id


def task_extract_entities(**context):
    run_id = context["ti"].xcom_pull(task_ids="load_chunks")
    chunks = read_json(run_id, "chunks")
    chunk_entities = []
    for item in chunks:
        cid, text = item["chunk_id"], item["text"]
        entities = extract_entities(text, use_llm=bool(OPENAI_API_KEY), api_key=OPENAI_API_KEY or None)
        if entities:
            chunk_entities.append({"chunk_id": cid, "entities": entities})
    write_json(run_id, "chunk_entities", chunk_entities)
    return run_id


def task_write_entities_and_mentions(**context):
    run_id = context["ti"].xcom_pull(task_ids="extract_entities")
    data = read_json(run_id, "chunk_entities")
    chunk_entities = [(x["chunk_id"], x["entities"]) for x in data]
    write_entities_and_mentions(chunk_entities, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return run_id


def task_extract_relations(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_entities_and_mentions")
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


def task_write_relations(**context):
    run_id = context["ti"].xcom_pull(task_ids="extract_relations")
    rels = read_json(run_id, "relations")
    relations = [tuple(r) for r in rels]
    write_relations(relations, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return run_id


def task_resolve_entities(**context):
    run_id = context["ti"].xcom_pull(task_ids="write_relations")
    entities = load_entities_for_resolution(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    id_to_canonical = resolve_entities(entities, fuzzy_threshold=FUZZY_THRESHOLD)
    write_json(run_id, "id_to_canonical", id_to_canonical)
    return run_id


def task_apply_resolution(**context):
    run_id = context["ti"].xcom_pull(task_ids="resolve_entities")
    id_to_canonical = read_json(run_id, "id_to_canonical")
    apply_resolution(id_to_canonical, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)


with DAG(
    dag_id=DAG_ID,
    default_args={"owner": "sensemap", "retries": 1},
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["extraction", "entity", "relation", "hybrid-graph"],
) as dag:
    load_chunks = PythonOperator(task_id="load_chunks", python_callable=task_load_chunks)
    extract_entities_task = PythonOperator(task_id="extract_entities", python_callable=task_extract_entities)
    write_entities = PythonOperator(task_id="write_entities_and_mentions", python_callable=task_write_entities_and_mentions)
    extract_relations_task = PythonOperator(task_id="extract_relations", python_callable=task_extract_relations)
    write_relations_task = PythonOperator(task_id="write_relations", python_callable=task_write_relations)
    resolve_entities_task = PythonOperator(task_id="resolve_entities", python_callable=task_resolve_entities)
    apply_resolution_task = PythonOperator(task_id="apply_resolution", python_callable=task_apply_resolution)

    (
        load_chunks
        >> extract_entities_task
        >> write_entities
        >> extract_relations_task
        >> write_relations_task
        >> resolve_entities_task
        >> apply_resolution_task
    )
