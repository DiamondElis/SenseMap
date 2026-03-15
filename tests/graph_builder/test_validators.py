"""Validator tests: reject malformed payloads."""
from datetime import datetime, timezone
import pytest

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk
from services.graph_builder.validators import validate_lexical_payload, ValidationError


def _doc() -> NormalizedDocument:
    return NormalizedDocument(
        id="doc1",
        source_id="doc1",
        source_type="txt",
        title="Test",
        text="Some text.",
    )


def _run() -> IngestionRun:
    return IngestionRun(
        id="run1",
        source_type="txt",
        started_at=datetime.now(timezone.utc),
        status="running",
        version="0.1",
        input_path="/tmp/test.txt",
    )


def _parent(pid: str = "p1", text: str = "parent text") -> ParentChunk:
    return ParentChunk(
        id=pid,
        document_id="doc1",
        text=text,
        position=0,
        token_count=2,
    )


def _child(cid: str = "c1", parent_id: str = "p1", text: str = "child text") -> ChildChunk:
    return ChildChunk(
        id=cid,
        parent_id=parent_id,
        document_id="doc1",
        text=text,
        position=0,
        token_count=2,
    )


def test_valid_payload_passes():
    """Valid payload does not raise."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1")]
    children = [_child("c1", "p1")]
    validate_lexical_payload(doc, parents, children, run)


def test_validators_reject_empty_child_text():
    """Child with empty text raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1")]
    children = [_child("c1", "p1", text="   ")]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "empty text" in str(exc.value).lower() or "ChildChunk" in str(exc.value)


def test_validators_reject_empty_parent_text():
    """Parent with empty text raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1", text="")]
    children = [_child("c1", "p1")]
    with pytest.raises(ValidationError):
        validate_lexical_payload(doc, parents, children, run)


def test_validators_reject_child_with_missing_parent():
    """Child whose parent_id is not in parent list raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1")]
    children = [_child("c1", parent_id="nonexistent")]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "parent_id" in str(exc.value) or "not in" in str(exc.value)


def test_validators_reject_duplicate_parent_ids():
    """Duplicate parent chunk id raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [
        ParentChunk(id="p1", document_id="doc1", text="a", position=0, token_count=1),
        ParentChunk(id="p1", document_id="doc1", text="b", position=1, token_count=1),
    ]
    children = [
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="x", position=0, token_count=1),
        ChildChunk(id="c2", parent_id="p1", document_id="doc1", text="y", position=1, token_count=1),
    ]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "Duplicate" in str(exc.value) and "parent" in str(exc.value).lower()


def test_validators_reject_duplicate_chunk_ids():
    """Duplicate chunk id (e.g. parent and child same id) raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("same")]
    children = [_child("same", "same")]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "Duplicate" in str(exc.value)


def test_validators_reject_parent_document_id_mismatch():
    """Parent with document_id != document.id raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [
        ParentChunk(
            id="p1",
            document_id="other",
            text="parent text",
            position=0,
            token_count=2,
        )
    ]
    children = [_child("c1", "p1")]
    with pytest.raises(ValidationError):
        validate_lexical_payload(doc, parents, children, run)


def test_validators_reject_empty_document_id():
    """Document with empty id raises ValidationError."""
    doc = NormalizedDocument(id="", source_id="x", source_type="txt", title="T", text="x")
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, [_parent()], [_child()], _run())
    assert "document" in str(exc.value).lower() and "id" in str(exc.value).lower()


def test_validators_reject_empty_document_title():
    """Document with empty title raises ValidationError."""
    doc = NormalizedDocument(id="doc1", source_id="doc1", source_type="txt", title=" ", text="x")
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, [_parent()], [_child()], _run())
    assert "title" in str(exc.value).lower()


def test_validators_reject_empty_document_source_type():
    """Document with empty source_type raises ValidationError."""
    doc = NormalizedDocument(id="doc1", source_id="doc1", source_type=" ", title="T", text="x")
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, [_parent()], [_child()], _run())
    assert "source_type" in str(exc.value).lower()


def test_validators_reject_non_contiguous_parent_positions():
    """Parent chunks with non-contiguous positions (e.g. 0, 2) raise ValidationError."""
    doc = _doc()
    run = _run()
    parents = [
        ParentChunk(id="p0", document_id="doc1", text="a", position=0, token_count=1),
        ParentChunk(id="p1", document_id="doc1", text="b", position=2, token_count=1),
    ]
    children = [
        ChildChunk(id="c0", parent_id="p0", document_id="doc1", text="x", position=0, token_count=1),
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="y", position=0, token_count=1),
    ]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "contiguous" in str(exc.value).lower() or "monotonic" in str(exc.value).lower()


def test_validators_reject_non_contiguous_child_positions():
    """Children of same parent with non-contiguous positions raise ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1")]
    children = [
        ChildChunk(id="c0", parent_id="p1", document_id="doc1", text="a", position=0, token_count=1),
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="b", position=2, token_count=1),
    ]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "contiguous" in str(exc.value).lower()


def test_validators_reject_parent_with_no_children():
    """Parent that has no children raises ValidationError (orphan parent)."""
    doc = _doc()
    run = _run()
    parents = [
        ParentChunk(id="p1", document_id="doc1", text="parent", position=0, token_count=1),
        ParentChunk(id="p2", document_id="doc1", text="parent2", position=1, token_count=1),
    ]
    children = [_child("c1", "p1")]  # only p1 has a child; p2 has none
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "no children" in str(exc.value).lower() or "at least one child" in str(exc.value).lower()


def test_validators_reject_invalid_embedding_type():
    """Child with embedding that is not a list of numbers raises ValidationError."""
    doc = _doc()
    run = _run()
    parents = [_parent("p1")]
    children = [
        ChildChunk(
            id="c1",
            parent_id="p1",
            document_id="doc1",
            text="x",
            position=0,
            token_count=1,
            embedding=["not", "floats"],
        )
    ]
    with pytest.raises(ValidationError) as exc:
        validate_lexical_payload(doc, parents, children, run)
    assert "embedding" in str(exc.value).lower()
