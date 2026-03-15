"""
Pipeline run and task run records for orchestration (e.g. Airflow).
Reusable across DAGs for tracking run identity and status.
Graph-native: PipelineRun and TaskRun nodes in Neo4j with RAN_TASK and WROTE relationships.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Status values for queryability. Transitions: running -> success | failed | skipped.
PIPELINE_RUN_STATUSES = ("running", "success", "failed", "skipped")
TASK_RUN_STATUSES = ("running", "success", "failed", "skipped")


class PipelineRunRecord(BaseModel):
    """One pipeline (DAG) run. Persisted as :PipelineRun in Neo4j."""

    id: str
    dag_id: str
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRunRecord(BaseModel):
    """One task run within a pipeline run. Persisted as :TaskRun; can link WROTE to output nodes."""

    id: str
    pipeline_run_id: str
    task_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_node_ids: list[str] = Field(default_factory=list, description="Node ids for (TaskRun)-[:WROTE]->(n)")
