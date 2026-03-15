"""Validate graph write payload consistency before write. Pure logic; no Neo4j."""

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk


class ValidationError(Exception):
    """Raised when payload validation fails."""

    pass


def validate_document(document: NormalizedDocument) -> None:
    """
    Validate document fields required for graph write.
    Raises ValidationError if id missing, title empty, or source_type missing.
    """
    if not (document.id or "").strip():
        raise ValidationError("Document id is missing or empty")
    if not (document.title or "").strip():
        raise ValidationError("Document title is empty")
    if not (document.source_type or "").strip():
        raise ValidationError("Document source_type is missing or empty")


def validate_parent_chunks(document: NormalizedDocument, parents: list[ParentChunk]) -> None:
    """
    Validate parent chunk list: no duplicate IDs, all reference document, non-empty text,
    positions strictly monotonic and contiguous (0, 1, 2, ...).
    """
    seen_ids: set[str] = set()
    positions: list[int] = []

    for p in parents:
        if not (p.text or "").strip():
            raise ValidationError(f"ParentChunk {p.id} has empty text")
        if p.id in seen_ids:
            raise ValidationError(f"Duplicate parent chunk id: {p.id}")
        seen_ids.add(p.id)
        if p.document_id != document.id:
            raise ValidationError(
                f"ParentChunk {p.id} document_id {p.document_id!r} does not match document.id {document.id!r}"
            )
        if p.position < 0:
            raise ValidationError(f"ParentChunk {p.id} has negative position {p.position}")
        positions.append(p.position)

    if positions:
        positions_sorted = sorted(positions)
        if positions_sorted != list(range(len(positions_sorted))):
            raise ValidationError(
                "Parent chunk positions must be contiguous and strictly monotonic (0, 1, 2, ...); "
                f"got positions {positions_sorted}"
            )


def validate_child_chunks(
    document: NormalizedDocument,
    parents: list[ParentChunk],
    children: list[ChildChunk],
) -> None:
    """
    Validate child chunk list: no duplicate IDs, every parent_id in parents,
    every document_id matches document, non-empty text, non-negative position,
    embedding if present must be a list of floats.
    """
    parent_ids = {p.id for p in parents}
    seen_ids: set[str] = set()

    for c in children:
        if not (c.text or "").strip():
            raise ValidationError(f"ChildChunk {c.id} has empty text")
        if c.id in seen_ids:
            raise ValidationError(f"Duplicate child chunk id: {c.id}")
        seen_ids.add(c.id)
        if c.parent_id not in parent_ids:
            raise ValidationError(
                f"ChildChunk {c.id} parent_id {c.parent_id!r} not in parent_chunks (orphan chunk)"
            )
        if c.document_id != document.id:
            raise ValidationError(
                f"ChildChunk {c.id} document_id {c.document_id!r} does not match document.id {document.id!r}"
            )
        if c.position < 0:
            raise ValidationError(f"ChildChunk {c.id} has negative position {c.position}")
        if c.embedding is not None:
            if not isinstance(c.embedding, list):
                raise ValidationError(
                    f"ChildChunk {c.id} embedding must be a list of floats; got {type(c.embedding).__name__}"
                )
            for i, x in enumerate(c.embedding):
                if not isinstance(x, (int, float)):
                    raise ValidationError(
                        f"ChildChunk {c.id} embedding[{i}] must be float; got {type(x).__name__}"
                    )


def validate_chunk_contiguity(children: list[ChildChunk]) -> None:
    """
    Validate that within each parent, child positions are contiguous (0, 1, 2, ...).
    Prevents broken chains for NEXT_CHUNK.
    """
    by_parent: dict[str, list[int]] = {}
    for c in children:
        by_parent.setdefault(c.parent_id, []).append(c.position)

    for parent_id, positions in by_parent.items():
        sorted_pos = sorted(positions)
        expected = list(range(len(sorted_pos)))
        if sorted_pos != expected:
            raise ValidationError(
                f"Child positions for parent {parent_id!r} must be contiguous (0, 1, 2, ...); "
                f"got {sorted_pos}"
            )


def validate_ingestion_run(run: IngestionRun) -> None:
    """Validate ingestion run fields required for graph write."""
    if not (run.id or "").strip():
        raise ValidationError("IngestionRun id is missing or empty")
    if not (run.source_type or "").strip():
        raise ValidationError("IngestionRun source_type is missing or empty")
    if run.started_at is None:
        raise ValidationError("IngestionRun started_at is missing")


def validate_payload(
    document: NormalizedDocument,
    parents: list[ParentChunk],
    children: list[ChildChunk],
    ingestion_run: IngestionRun,
    *,
    allow_empty_parents: bool = False,
) -> None:
    """
    Full payload validation before graph write.
    - Document, IngestionRun, parent chunks, child chunks validated.
    - Orphan children rejected; duplicate IDs rejected; empty text rejected.
    - Parent-child associations and position contiguity verified.
    - By default every parent must have at least one child; set allow_empty_parents=True to allow parents with no children.
    Raises ValidationError with a human-readable message on first failure.
    """
    validate_document(document)
    validate_ingestion_run(ingestion_run)
    validate_parent_chunks(document, parents)
    validate_child_chunks(document, parents, children)
    validate_chunk_contiguity(children)

    if not allow_empty_parents and parents:
        parent_ids_with_children = {c.parent_id for c in children}
        for p in parents:
            if p.id not in parent_ids_with_children:
                raise ValidationError(
                    f"ParentChunk {p.id} has no children; every parent must have at least one child"
                )


def validate_lexical_payload(
    document: NormalizedDocument,
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
    ingestion_run: IngestionRun,
) -> None:
    """
    Legacy entrypoint: same as validate_payload with allow_empty_parents=False.
    Verify payload is consistent. Raises ValidationError if invalid.
    """
    validate_payload(document, parent_chunks, child_chunks, ingestion_run, allow_empty_parents=False)
