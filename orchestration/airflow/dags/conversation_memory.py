"""
Conversation candidate DAG: load conversation -> extract candidate claims
-> validate -> auto-merge safe items -> create review tasks.
Thin orchestration: each task calls services.conversation_memory (ingest, extract, validate, merge).
PipelineRun/TaskRun metadata in Neo4j; on_failure preserves partial provenance.

Idempotency: ingest/extract/validate use MERGE; execute_merge uses MERGE for RELATES_TO (rerun-safe).
Retries: 1 for ingest/extract/validate/create_review_tasks; 0 for auto_merge_safe_items (no retry on merge).
Failures: on_failure_callback marks TaskRun and PipelineRun failed; partial outputs remain traceable.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from sensemap.staged_io import read_json, write_json

DAG_ID = "conversation_candidate_dag"
START_TASK_ID = "start_pipeline_run"
CLOSE_TASK_ID = "close_pipeline_run"
DEFAULT_INPUT_PATH = "/opt/airflow/data/raw/conversations"


def _run_id(context):
    return context["run_id"]


def _pipeline_run_id(context):
    return context["ti"].xcom_pull(task_ids=START_TASK_ID)


def _input_path(context):
    return context["params"].get("input_path", DEFAULT_INPUT_PATH)


def _task_run_id(pipeline_run_id: str, task_id: str) -> str:
    return f"{pipeline_run_id}_{task_id}"


def _with_metadata(task_id: str, run_content_fn):
    """Create TaskRun (running), run content fn, update TaskRun (success). On exception mark failed."""

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
            now_end = datetime.now(timezone.utc)
            try:
                from neo4j_hooks import Neo4jHook
                from services.orchestration.pipeline_metadata import update_task_run_status
                with Neo4jHook().get_session() as session:
                    update_task_run_status(session, tr_id, "success", finished_at=now_end)
            except Exception:
                pass
            return result
        except Exception as e:
            now_end = datetime.now(timezone.utc)
            try:
                from neo4j_hooks import Neo4jHook
                from services.orchestration.pipeline_metadata import update_task_run_status
                with Neo4jHook().get_session() as session:
                    update_task_run_status(
                        session, tr_id, "failed", finished_at=now_end, metadata_update={"error": str(e)}
                    )
            except Exception:
                pass
            raise

    return _wrapped


def _on_failure_callback(context):
    """Update TaskRun and PipelineRun to failed to preserve partial provenance."""
    try:
        from neo4j_hooks import Neo4jHook
        from services.orchestration.pipeline_metadata import update_task_run_status, update_pipeline_run_status
        pipeline_run_id = context["ti"].xcom_pull(task_ids=START_TASK_ID)
        task_id = context.get("task").task_id
        if pipeline_run_id and task_id and task_id != START_TASK_ID:
            tr_id = _task_run_id(pipeline_run_id, task_id)
            with Neo4jHook().get_session() as session:
                update_task_run_status(
                    session, tr_id, "failed", metadata_update={"error": str(context.get("exception"))}
                )
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
                    metadata={"input_path": _input_path(context)},
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


# --- Content tasks (call conversation_memory service layer) ---


def _task_ingest_transcript(**context):
    from services.conversation_memory.ingest import ingest_transcript as ingest_transcript_fn

    run_id = _run_id(context)
    input_path = _input_path(context)
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Conversation input path not found: {path}")
    raw = json.loads(path.read_text())
    conversation, messages = ingest_transcript_fn(
        raw, uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
    )
    write_json(run_id, "messages", [m.model_dump() for m in messages])
    return {"conversation_id": conversation.id}


def _task_extract_candidate_claims(**context):
    from shared.python.models.conversation import MessageRecord
    from services.conversation_memory.extract_claims import extract_claims_from_conversation
    from services.conversation_memory.ingest import write_candidate_claims_to_graph
    from services.graph_builder.merge_utils import get_driver

    run_id = _run_id(context)
    prev = context["ti"].xcom_pull(task_ids="ingest_transcript")
    conversation_id = prev["conversation_id"]
    messages_data = read_json(run_id, "messages")
    messages = [MessageRecord.model_validate(m) for m in messages_data]
    if not messages:
        write_json(run_id, "claims", [])
        write_json(run_id, "relations", [])
        return {"conversation_id": conversation_id, "claim_count": 0}
    claims, relations = extract_claims_from_conversation(messages)
    driver = get_driver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    try:
        with driver.session() as session:
            write_candidate_claims_to_graph(session, conversation_id, claims, relations)
    finally:
        driver.close()
    write_json(run_id, "claims", [c.model_dump() for c in claims])
    write_json(run_id, "relations", [r.model_dump() for r in relations])
    return {"conversation_id": conversation_id, "claim_count": len(claims)}


def _task_validate_candidates(**context):
    from shared.python.models.conversation import (
        CandidateClaimRecord,
        CandidateRelationRecord,
        ValidationTaskRecord,
    )
    from services.conversation_memory.ingest import (
        fetch_accepted_relations,
        write_validation_tasks_to_graph,
    )
    from services.conversation_memory.validate import validate_candidate_claim
    from services.extraction.pipeline import fetch_existing_entities
    from services.graph_builder.merge_utils import get_driver

    run_id = _run_id(context)
    claims_data = read_json(run_id, "claims")
    relations_data = read_json(run_id, "relations")
    if not claims_data:
        write_json(run_id, "validation_tasks", [])
        return {"run_id": run_id, "needs_review": 0}
    claims = [CandidateClaimRecord.model_validate(c) for c in claims_data]
    relations = [CandidateRelationRecord.model_validate(r) for r in relations_data]
    driver = get_driver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    try:
        existing_entities = fetch_existing_entities(driver)
        accepted_relations = fetch_accepted_relations(driver)
        glossary = {}
        validation_tasks = []
        for claim in claims:
            rels_for_claim = [r for r in relations if r.claim_id == claim.id]
            vt = validate_candidate_claim(
                claim, rels_for_claim, existing_entities, glossary=glossary
            )
            validation_tasks.append(vt)
        with driver.session() as session:
            write_validation_tasks_to_graph(session, claims, validation_tasks)
    finally:
        driver.close()
    write_json(run_id, "validation_tasks", [vt.model_dump() for vt in validation_tasks])
    needs_review = sum(1 for vt in validation_tasks if vt.status == "needs-review")
    return {"run_id": run_id, "needs_review": needs_review}


def _task_auto_merge_safe_items(**context):
    from shared.python.models.conversation import (
        CandidateClaimRecord,
        CandidateRelationRecord,
        ValidationTaskRecord,
    )
    from services.conversation_memory.ingest import fetch_accepted_relations
    from services.conversation_memory.merge import execute_merge, merge_decision
    from services.extraction.pipeline import fetch_existing_entities
    from services.graph_builder.merge_utils import get_driver

    run_id = _run_id(context)
    prev = context["ti"].xcom_pull(task_ids="extract_candidate_claims")
    conversation_id = prev.get("conversation_id") if isinstance(prev, dict) else None
    if not conversation_id:
        return {"merged_count": 0}
    claims_data = read_json(run_id, "claims")
    relations_data = read_json(run_id, "relations")
    validation_tasks_data = read_json(run_id, "validation_tasks")
    if not claims_data:
        return {"merged_count": 0}
    claims = [CandidateClaimRecord.model_validate(c) for c in claims_data]
    relations = [CandidateRelationRecord.model_validate(r) for r in relations_data]
    validation_tasks = [ValidationTaskRecord.model_validate(v) for v in validation_tasks_data]
    driver = get_driver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    merged_count = 0
    try:
        existing_entities = fetch_existing_entities(driver)
        accepted_relations = fetch_accepted_relations(driver)
        glossary = {}
        for claim, vt in zip(claims, validation_tasks):
            rels_for_claim = [r for r in relations if r.claim_id == claim.id]
            mr = merge_decision(
                claim, rels_for_claim, vt, existing_entities, accepted_relations, glossary=glossary
            )
            if mr.decision == "auto_merge":
                ex = execute_merge(
                    claim,
                    rels_for_claim,
                    vt,
                    mr,
                    existing_entities,
                    conversation_id,
                    glossary=glossary,
                    uri=NEO4J_URI,
                    user=NEO4J_USER,
                    password=NEO4J_PASSWORD,
                )
                if ex.relations_written > 0 or ex.candidate_status_updated:
                    merged_count += 1
    finally:
        driver.close()
    return {"merged_count": merged_count}


def _task_create_review_tasks(**context):
    """Ensure review queue is populated (ValidationTask nodes already written in validate_candidates)."""
    from services.conversation_memory.ingest import run_review_queue
    from services.graph_builder.merge_utils import get_driver

    driver = get_driver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    try:
        items = run_review_queue(driver)
    finally:
        driver.close()
    return {"review_queue_count": len(items)}


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
    tags=["conversation", "memory", "candidate", "review-queue"],
    params={"input_path": DEFAULT_INPUT_PATH},
) as dag:
    start = PythonOperator(task_id=START_TASK_ID, python_callable=task_start_pipeline_run)
    ingest = PythonOperator(
        task_id="ingest_transcript",
        python_callable=_with_metadata("ingest_transcript", _task_ingest_transcript),
    )
    extract = PythonOperator(
        task_id="extract_candidate_claims",
        python_callable=_with_metadata("extract_candidate_claims", _task_extract_candidate_claims),
    )
    validate = PythonOperator(
        task_id="validate_candidates",
        python_callable=_with_metadata("validate_candidates", _task_validate_candidates),
    )
    auto_merge = PythonOperator(
        task_id="auto_merge_safe_items",
        python_callable=_with_metadata("auto_merge_safe_items", _task_auto_merge_safe_items),
        retries=0,
    )
    create_review = PythonOperator(
        task_id="create_review_tasks",
        python_callable=_with_metadata("create_review_tasks", _task_create_review_tasks),
    )
    close = PythonOperator(task_id=CLOSE_TASK_ID, python_callable=task_close_pipeline_run)

    start >> ingest >> extract >> validate >> auto_merge >> create_review >> close
