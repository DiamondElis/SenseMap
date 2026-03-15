"""
Provenance helpers for lexical graph writing.
Build IngestionRun metadata, assign pipeline version, set timestamps,
and return consistent node property dicts for Document, ParentChunk, Chunk, IngestionRun.
Deterministic and reusable from CLI pipeline and Airflow.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk

# Pipeline version; bump when schema or behaviour changes. Override via env.
INGESTION_VERSION = os.environ.get("SENSEMAP_INGESTION_VERSION", "0.1.0")

# Max characters stored for document text in the graph (provenance/display)
MAX_DOCUMENT_TEXT_LENGTH = 10_000


def now_iso() -> str:
    """Current UTC time as ISO 8601 string. Use for consistent timestamps."""
    return datetime.now(timezone.utc).isoformat()


def make_ingestion_run(
    source_type: str,
    input_path: str,
    version: str,
    *,
    run_id: Optional[str] = None,
    status: str = "running",
    started_at: Optional[datetime] = None,
) -> IngestionRun:
    """
    Build an IngestionRun with stable id, timestamps, and version.
    Use from CLI pipeline or Airflow; keeps provenance fields consistent.
    """
    rid = run_id or str(uuid.uuid4())
    started = started_at or datetime.now(timezone.utc)
    return IngestionRun(
        id=rid,
        source_type=source_type,
        started_at=started,
        status=status,
        version=version,
        input_path=str(Path(input_path).resolve()),
    )


def build_ingestion_run(
    source_type: str,
    input_path: str,
    run_id: Optional[str] = None,
    status: str = "running",
    version: Optional[str] = None,
) -> IngestionRun:
    """
    Legacy builder: same as make_ingestion_run with version defaulting to INGESTION_VERSION.
    """
    return make_ingestion_run(
        source_type=source_type,
        input_path=input_path,
        version=version or INGESTION_VERSION,
        run_id=run_id,
        status=status,
    )


def document_properties(document: NormalizedDocument) -> dict[str, Any]:
    """
    Normalized property dict for a Document node. Use for SET in Cypher.
    Truncates text to MAX_DOCUMENT_TEXT_LENGTH; datetimes as ISO strings.
    """
    text = (document.text or "")[:MAX_DOCUMENT_TEXT_LENGTH]
    created_at: Optional[str] = None
    if document.created_at is not None:
        created_at = (
            document.created_at.isoformat()
            if document.created_at.tzinfo
            else document.created_at.replace(tzinfo=timezone.utc).isoformat()
        )
    return {
        "id": document.id,
        "source_id": document.source_id,
        "source_type": document.source_type,
        "title": document.title,
        "author": document.author,
        "uri": document.uri,
        "created_at": created_at,
        "text": text,
        "metadata": document.metadata,
    }


def parent_chunk_properties(parent: ParentChunk) -> dict[str, Any]:
    """Normalized property dict for a ParentChunk node. Use for SET in Cypher."""
    return {
        "id": parent.id,
        "document_id": parent.document_id,
        "text": parent.text,
        "position": parent.position,
        "token_count": parent.token_count,
        "metadata": parent.metadata,
    }


def child_chunk_properties(child: ChildChunk) -> dict[str, Any]:
    """
    Normalized property dict for a Chunk (child) node, excluding embedding.
    Use for SET in Cypher; set embedding in a separate SET when present.
    """
    return {
        "id": child.id,
        "parent_id": child.parent_id,
        "document_id": child.document_id,
        "text": child.text,
        "position": child.position,
        "token_count": child.token_count,
        "metadata": child.metadata,
    }


def ingestion_run_properties(run: IngestionRun) -> dict[str, Any]:
    """Normalized property dict for an IngestionRun node. Use for SET in Cypher."""
    started_at: Optional[str] = None
    if run.started_at is not None:
        started_at = (
            run.started_at.isoformat()
            if run.started_at.tzinfo
            else run.started_at.replace(tzinfo=timezone.utc).isoformat()
        )
    return {
        "id": run.id,
        "source_type": run.source_type,
        "started_at": started_at,
        "status": run.status,
        "version": run.version,
        "input_path": run.input_path,
    }
