"""
Graph-native orchestration metadata: PipelineRun and TaskRun nodes in Neo4j.
- Create PipelineRun at DAG start; create TaskRun at task start.
- (PipelineRun)-[:RAN_TASK]->(TaskRun); (TaskRun)-[:WROTE]->(Document|Chunk|Entity|Community).
- Status transitions: running -> success | failed | skipped. finished_at set on status update.
- Partial provenance: failed runs remain inspectable; TaskRun and PipelineRun keep failed/skipped status.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from shared.python.models.pipeline_runs import PipelineRunRecord, TaskRunRecord


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _run_write(session: Any, query: str, params: dict[str, Any]) -> None:
    """Run a single write query. Session is provided by caller (e.g. Neo4j hook)."""
    session.run(query, params)


def create_pipeline_run(session: Any, record: PipelineRunRecord | dict[str, Any]) -> None:
    """
    Create or update a PipelineRun node at DAG start. Idempotent MERGE.
    """
    if isinstance(record, dict):
        record = PipelineRunRecord(**record)
    _run_write(
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
            "started_at": _iso(record.started_at),
            "finished_at": _iso(record.finished_at),
            "metadata": record.metadata,
        },
    )


def create_task_run(
    session: Any,
    record: TaskRunRecord | dict[str, Any],
    pipeline_run_id: str,
) -> None:
    """
    Create or update a TaskRun node at task start and link (PipelineRun)-[:RAN_TASK]->(TaskRun).
    Idempotent MERGE so partial provenance is preserved on retries.
    """
    if isinstance(record, dict):
        record = TaskRunRecord(**record)
    _run_write(
        session,
        """
        MERGE (t:TaskRun {id: $id})
        SET t.pipeline_run_id = $pipeline_run_id, t.task_id = $task_id, t.status = $status,
            t.started_at = $started_at, t.finished_at = $finished_at, t.metadata = $metadata
        WITH t
        MATCH (p:PipelineRun {id: $pipeline_run_id})
        MERGE (p)-[:RAN_TASK]->(t)
        """,
        {
            "id": record.id,
            "pipeline_run_id": pipeline_run_id,
            "task_id": record.task_id,
            "status": record.status,
            "started_at": _iso(record.started_at),
            "finished_at": _iso(record.finished_at),
            "metadata": record.metadata,
        },
    )


def update_pipeline_run_status(
    session: Any,
    pipeline_run_id: str,
    status: str,
    finished_at: Optional[datetime] = None,
    metadata_update: Optional[dict[str, Any]] = None,
) -> None:
    """Update PipelineRun status (e.g. success/failed) and optionally finished_at and metadata."""
    params: dict[str, Any] = {
        "id": pipeline_run_id,
        "status": status,
        "finished_at": _iso(finished_at or datetime.now(timezone.utc)),
    }
    if metadata_update is not None:
        params["metadata"] = metadata_update
    query = """
        MATCH (p:PipelineRun {id: $id})
        SET p.status = $status, p.finished_at = $finished_at
        """
    if metadata_update is not None:
        query += ", p.metadata = $metadata"
    _run_write(session, query, params)


def update_task_run_status(
    session: Any,
    task_run_id: str,
    status: str,
    finished_at: Optional[datetime] = None,
    metadata_update: Optional[dict[str, Any]] = None,
) -> None:
    """Update TaskRun status (success/failed/skipped). Sets finished_at to now if not provided."""
    params: dict[str, Any] = {
        "id": task_run_id,
        "status": status,
        "finished_at": _iso(finished_at or datetime.now(timezone.utc)),
    }
    if metadata_update is not None:
        params["metadata"] = metadata_update
    query = """
        MATCH (t:TaskRun {id: $id})
        SET t.status = $status, t.finished_at = $finished_at
        """
    if metadata_update is not None:
        query += ", t.metadata = $metadata"
    _run_write(session, query, params)


def link_task_run_wrote(
    session: Any,
    task_run_id: str,
    node_ids: list[str],
) -> None:
    """
    Create (TaskRun)-[:WROTE]->(n) for each node n whose id is in node_ids and
    n is one of :Document, :Chunk, :Entity, :Community. Skips missing nodes.
    Call after a task completes to attach output node IDs for provenance.
    """
    if not node_ids:
        return
    _run_write(
        session,
        """
        MATCH (t:TaskRun {id: $task_run_id})
        UNWIND $node_ids AS nid
        MATCH (n)
        WHERE n.id = nid AND (n:Document OR n:Chunk OR n:Entity OR n:Community)
        MERGE (t)-[:WROTE]->(n)
        """,
        {"task_run_id": task_run_id, "node_ids": node_ids},
    )
