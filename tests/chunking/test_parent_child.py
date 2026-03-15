"""Chunking tests: ordered parent and child chunks, stable IDs."""
import pytest

from shared.python.models.ingestion import NormalizedDocument
from services.chunking import create_parent_chunks, create_child_chunks


def _doc(text: str, source_id: str = "doc1") -> NormalizedDocument:
    return NormalizedDocument(
        id=source_id,
        source_id=source_id,
        source_type="txt",
        title="Test",
        text=text,
    )


def test_short_doc_produces_one_parent_and_at_least_one_child():
    """Short document creates at least one parent and one child."""
    doc = _doc("One short paragraph.")
    parents = create_parent_chunks(doc)
    children = create_child_chunks(doc, parents)
    assert len(parents) >= 1
    assert len(children) >= 1
    assert parents[0].document_id == doc.id
    assert children[0].parent_id == parents[0].id
    assert children[0].document_id == doc.id


def test_parent_positions_ordered():
    """Parent chunks have stable ascending positions."""
    text = " ".join([f"Paragraph {i} with enough words. " * 20 for i in range(5)])
    doc = _doc(text)
    parents = create_parent_chunks(doc, target_tokens=200, overlap_ratio=0.15)
    positions = [p.position for p in parents]
    assert positions == sorted(positions)
    assert positions == list(range(len(parents)))


def test_child_positions_ordered_per_parent():
    """Children of the same parent have ascending positions."""
    text = " ".join([f"Paragraph {i}. " * 30 for i in range(5)])
    doc = _doc(text)
    parents = create_parent_chunks(doc, target_tokens=300, overlap_ratio=0.15)
    children = create_child_chunks(doc, parents, target_tokens=100, overlap_ratio=0.15)
    by_parent: dict[str, list] = {}
    for c in children:
        by_parent.setdefault(c.parent_id, []).append(c)
    for pid, chunks in by_parent.items():
        pos = [c.position for c in chunks]
        assert pos == sorted(pos)
        assert pos == list(range(len(chunks)))


def test_every_child_has_valid_parent_id():
    """Every child's parent_id appears in parent list."""
    doc = _doc("A. " * 100)
    parents = create_parent_chunks(doc, target_tokens=200, overlap_ratio=0.15)
    children = create_child_chunks(doc, parents, target_tokens=80, overlap_ratio=0.15)
    parent_ids = {p.id for p in parents}
    for c in children:
        assert c.parent_id in parent_ids


def test_chunk_ids_stable_across_runs():
    """Same document produces same chunk IDs on repeated runs."""
    text = "Stable content for hashing. " * 50
    doc = _doc(text, source_id="stable")
    p1 = create_parent_chunks(doc)
    c1 = create_child_chunks(doc, p1)
    p2 = create_parent_chunks(doc)
    c2 = create_child_chunks(doc, p2)
    assert [x.id for x in p1] == [x.id for x in p2]
    assert [x.id for x in c1] == [x.id for x in c2]


def test_no_empty_chunks():
    """No parent or child has empty text."""
    doc = _doc("Some content. " * 40)
    parents = create_parent_chunks(doc)
    children = create_child_chunks(doc, parents)
    for p in parents:
        assert (p.text or "").strip()
    for c in children:
        assert (c.text or "").strip()
