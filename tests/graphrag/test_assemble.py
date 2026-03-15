"""Unit tests for context assembly: section ordering and structure."""
import pytest

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit
from services.graphrag.context_builders.assemble import (
    assemble,
    SECTION_CHUNK,
    SECTION_ENTITY,
    SECTION_RELATIONSHIP,
    SECTION_EVIDENCE,
)


def test_assembler_preserves_section_ordering():
    """Assembled prompt has [Chunk Context], [Entity Context], [Relationship Context], [Evidence / Provenance] in that order."""
    bundle = ContextBundle(
        chunk_hits=[
            RetrievalHit(node_id="c1", node_label="Chunk", text="Chunk text", score=0.9, metadata={}, provenance={}),
        ],
        entity_hits=[
            EntityHit(entity_id="e1", canonical_name="Ergonomics", entity_type="Concept", score=0.9, metadata={}),
        ],
        relationship_hits=[
            RelationshipHit(source_id="e1", source_name="Ergonomics", target_id="e2", target_name="Design", rel_type="INFLUENCES", score=0.8, metadata={}),
        ],
    )
    prompt_text, debug_object = assemble(bundle)

    assert SECTION_CHUNK in prompt_text
    assert SECTION_ENTITY in prompt_text
    assert SECTION_RELATIONSHIP in prompt_text
    assert SECTION_EVIDENCE in prompt_text
    chunk_pos = prompt_text.index(SECTION_CHUNK)
    entity_pos = prompt_text.index(SECTION_ENTITY)
    rel_pos = prompt_text.index(SECTION_RELATIONSHIP)
    evidence_pos = prompt_text.index(SECTION_EVIDENCE)
    assert chunk_pos < entity_pos < rel_pos < evidence_pos


def test_assembler_debug_object_has_sections():
    """Debug context object has sections with entries and prompt_lines."""
    bundle = ContextBundle(
        chunk_hits=[RetrievalHit(node_id="c1", node_label="Chunk", text="Hello", score=0.9, metadata={}, provenance={})],
        entity_hits=[],
        relationship_hits=[],
    )
    _, debug_object = assemble(bundle)
    sections = debug_object.get("sections", {})
    assert SECTION_CHUNK in sections
    assert "entries" in sections[SECTION_CHUNK]
    assert "prompt_lines" in sections[SECTION_CHUNK]
    assert sections[SECTION_CHUNK]["entries"][0]["node_id"] == "c1"


def test_assembler_empty_bundle_still_has_four_sections():
    """Empty bundle still produces all four section headers with (none) content."""
    bundle = ContextBundle()
    prompt_text, _ = assemble(bundle)
    assert SECTION_CHUNK in prompt_text
    assert SECTION_ENTITY in prompt_text
    assert SECTION_RELATIONSHIP in prompt_text
    assert SECTION_EVIDENCE in prompt_text
    assert "(none)" in prompt_text
