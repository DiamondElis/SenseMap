"""
Neo4j hooks for Airflow. Provide driver/session, query helpers, and optional PipelineRun/TaskRun writes.
Connection and config live here; DAG tasks use the hook without low-level connection logic.
"""
from contextlib import contextmanager
from typing import Any, Iterator, Optional

try:
    from airflow.hooks.base import BaseHook
    _AIRFLOW_AVAILABLE = True
except ImportError:
    _AIRFLOW_AVAILABLE = False
    BaseHook = object  # type: ignore[misc, assignment]


def get_neo4j_driver(
    conn_id: str = "neo4j_default",
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Any:
    """
    Return a Neo4j driver. Uses Airflow Connection when available; else shared config / env.
    Caller is responsible for closing the driver, or use Neo4jHook.get_session().
    """
    if _AIRFLOW_AVAILABLE:
        try:
            conn = BaseHook.get_connection(conn_id)
            u = uri or conn.host or "bolt://localhost:7687"
            if u and not u.startswith("bolt://") and not u.startswith("neo4j://"):
                u = f"bolt://{u}"
            usr = user or conn.login or "neo4j"
            pwd = password or conn.password or ""
            return _driver_from_params(u, usr, pwd)
        except Exception:
            pass
    try:
        from shared.python.config import settings
        u = uri or settings.NEO4J_URI
        usr = user or settings.NEO4J_USER
        pwd = password or settings.NEO4J_PASSWORD
        return _driver_from_params(u, usr, pwd)
    except ImportError:
        import os
        u = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        usr = user or os.environ.get("NEO4J_USER", "neo4j")
        pwd = password or os.environ.get("NEO4J_PASSWORD", "password")
        return _driver_from_params(u, usr, pwd)


def _driver_from_params(uri: str, user: str, password: str) -> Any:
    from neo4j import GraphDatabase
    return GraphDatabase.driver(uri, auth=(user, password))


# --- Query helpers (session-scoped; no connection logic in callers) ---


def run_write_query(
    session: Any,
    query: str,
    params: Optional[dict[str, Any]] = None,
) -> None:
    """Run a single write query (MERGE/SET/CREATE). Params default to {}."""
    session.run(query, params or {})


def run_read_query(
    session: Any,
    query: str,
    params: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Run a read query; return list of records as dicts."""
    result = session.run(query, params or {})
    return [dict(record) for record in result]


def run_batched_write(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    batch_size: int = 500,
    rows_param: str = "rows",
) -> None:
    """Run UNWIND $rows AS row in batches. Empty rows is a no-op."""
    if not rows:
        return
    for i in range(0, len(rows), batch_size):
        session.run(query, {rows_param: rows[i : i + batch_size]})


# --- Optional PipelineRun / TaskRun writes (for audit in Neo4j) ---


def write_pipeline_run_record(session: Any, record: Any) -> None:
    """MERGE a PipelineRun node from PipelineRunRecord. Idempotent."""
    from shared.python.models.pipeline_runs import PipelineRunRecord
    if not isinstance(record, PipelineRunRecord):
        record = PipelineRunRecord(**record) if isinstance(record, dict) else record
    run_write_query(
        session,
        """
        MERGE (p:PipelineRun {id: $id})
        SET p.dag_id = $dag_id, p.run_id = $run_id, p.status = $status,
            p.started_at = $started_at, p.finished_at = $finished_at, p.metadata = $metadata
        """,
        {
            "id": record.id,
            "dag_id": record.dag_id,
            "run_id": record.run_id,
            "status": record.status,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "metadata": record.metadata,
        },
    )


def write_task_run_record(session: Any, record: Any) -> None:
    """MERGE a TaskRun node from TaskRunRecord. Idempotent."""
    from shared.python.models.pipeline_runs import TaskRunRecord
    if not isinstance(record, TaskRunRecord):
        record = TaskRunRecord(**record) if isinstance(record, dict) else record
    run_write_query(
        session,
        """
        MERGE (t:TaskRun {id: $id})
        SET t.pipeline_run_id = $pipeline_run_id, t.task_id = $task_id, t.status = $status,
            t.started_at = $started_at, t.finished_at = $finished_at, t.metadata = $metadata
        """,
        {
            "id": record.id,
            "pipeline_run_id": record.pipeline_run_id,
            "task_id": record.task_id,
            "status": record.status,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "metadata": record.metadata,
        },
    )


if _AIRFLOW_AVAILABLE:

    class Neo4jHook(BaseHook):
        """
        Airflow Hook for Neo4j. Use get_conn() for a driver or get_session() for a session context.
        Use run_write_query / run_read_query / run_batched_write with a session to avoid connection boilerplate.
        Optionally write_pipeline_run / write_task_run for audit.
        """

        conn_name_attr = "neo4j_conn_id"
        default_conn_name = "neo4j_default"
        conn_type = "neo4j"
        hook_name = "Neo4j"

        def __init__(self, neo4j_conn_id: str = default_conn_name, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.neo4j_conn_id = neo4j_conn_id
            self._driver: Any = None

        def get_conn(self) -> Any:
            """Return a Neo4j driver. Caller may close it or use get_session() instead."""
            return get_neo4j_driver(conn_id=self.neo4j_conn_id)

        @contextmanager
        def get_session(self) -> Iterator[Any]:
            """Context manager that yields a session and closes driver on exit. Use for task-scoped work."""
            driver = get_neo4j_driver(conn_id=self.neo4j_conn_id)
            try:
                with driver.session() as session:
                    yield session
            finally:
                driver.close()

        def run_write_query(self, session: Any, query: str, params: Optional[dict[str, Any]] = None) -> None:
            run_write_query(session, query, params)

        def run_read_query(self, session: Any, query: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
            return run_read_query(session, query, params)

        def run_batched_write(
            self,
            session: Any,
            query: str,
            rows: list[dict[str, Any]],
            batch_size: int = 500,
            rows_param: str = "rows",
        ) -> None:
            run_batched_write(session, query, rows, batch_size, rows_param)

        def write_pipeline_run(self, session: Any, record: Any) -> None:
            """Optionally persist PipelineRunRecord to Neo4j for audit."""
            write_pipeline_run_record(session, record)

        def write_task_run(self, session: Any, record: Any) -> None:
            """Optionally persist TaskRunRecord to Neo4j for audit."""
            write_task_run_record(session, record)
