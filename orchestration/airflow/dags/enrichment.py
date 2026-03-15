"""
Answer graph enrichment DAG: project graph to GDS -> PageRank -> Leiden -> FastRP
-> write back scores -> validate enrichment.
Thin orchestration: each task calls sensemap gds_runner step-wise functions.
PipelineRun/TaskRun metadata in Neo4j; on_failure preserves partial provenance.

Idempotency: project drops then projects; algorithms overwrite node properties (no duplicate state).
Retries: 0 for project_graph (drop+project); 1 for pagerank/leiden/fastrp/write_back/validate.
Failures: on_failure_callback marks TaskRun and PipelineRun failed; partial outputs remain traceable.
"""
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from sensemap.gds_runner import (
    project_graph,
    run_pagerank,
    run_leiden,
    run_fastrp,
    write_back_node_similarity,
    validate_enrichment,
)

DAG_ID = "answer_graph_enrichment_dag"
START_TASK_ID = "start_pipeline_run"
CLOSE_TASK_ID = "close_pipeline_run"
SKIP_NODE_SIMILARITY = True  # Optional; set False to run Node Similarity in write_back_scores


def _run_id(context):
    return context["run_id"]


def _pipeline_run_id(context):
    return context["ti"].xcom_pull(task_ids=START_TASK_ID)


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


# --- Content tasks (call gds_runner step-wise) ---


def _task_project_graph(**context):
    return project_graph(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)


def _task_run_pagerank(**context):
    return run_pagerank(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)


def _task_run_leiden(**context):
    return run_leiden(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)


def _task_run_fastrp(**context):
    return run_fastrp(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)


def _task_write_back_scores(**context):
    """Write back optional Node Similarity scores; skip if SKIP_NODE_SIMILARITY."""
    if SKIP_NODE_SIMILARITY:
        return {"skipped": True, "reason": "node_similarity_disabled"}
    return write_back_node_similarity(
        uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
    )


def _task_validate_enrichment(**context):
    return validate_enrichment(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)


with DAG(
    dag_id=DAG_ID,
    default_args={
        "owner": "sensemap",
        "retries": 0,
        "on_failure_callback": _on_failure_callback,
    },
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["enrichment", "gds", "answer-graph"],
) as dag:
    start = PythonOperator(task_id=START_TASK_ID, python_callable=task_start_pipeline_run)
    project = PythonOperator(
        task_id="project_graph",
        python_callable=_with_metadata("project_graph", _task_project_graph),
        retries=0,
    )
    pagerank = PythonOperator(
        task_id="run_pagerank",
        python_callable=_with_metadata("run_pagerank", _task_run_pagerank),
        retries=1,
    )
    leiden = PythonOperator(
        task_id="run_leiden",
        python_callable=_with_metadata("run_leiden", _task_run_leiden),
        retries=1,
    )
    fastrp = PythonOperator(
        task_id="run_fastrp",
        python_callable=_with_metadata("run_fastrp", _task_run_fastrp),
        retries=1,
    )
    write_back = PythonOperator(
        task_id="write_back_scores",
        python_callable=_with_metadata("write_back_scores", _task_write_back_scores),
        retries=1,
    )
    validate = PythonOperator(
        task_id="validate_enrichment",
        python_callable=_with_metadata("validate_enrichment", _task_validate_enrichment),
        retries=1,
    )
    close = PythonOperator(task_id=CLOSE_TASK_ID, python_callable=task_close_pipeline_run)

    start >> project >> pagerank >> leiden >> fastrp >> write_back >> validate >> close
