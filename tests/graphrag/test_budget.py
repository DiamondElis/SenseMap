"""Unit tests for token budget: trim order and caps."""
import pytest

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit
from services.graphrag.context_builders.budget import (
    apply_budget,
    BudgetConfig,
    estimate_chunk_tokens,
    estimate_entity_tokens,
    estimate_relationship_tokens,
    DEFAULT_MAX_PARENTS,
    DEFAULT_MAX_ENTITY_EXPANSIONS,
    DEFAULT_MAX_RELATIONSHIP_LINES,
    DEFAULT_MAX_TOTAL_TOKENS,
)


def test_estimate_functions_return_positive_tokens():
    """Token estimates are positive for non-empty content."""
    hit_c = RetrievalHit(node_id="c1", node_label="Chunk", text="Some text here", score=0.9, metadata={}, provenance={})
    hit_e = EntityHit(entity_id="e1", canonical_name="Acme", entity_type="Organization", score=0.9, metadata={})
    hit_r = RelationshipHit(source_id="e1", source_name="A", target_id="e2", target_name="B", rel_type="RELATES_TO", score=0.8, metadata={})
    fn = lambda s: max(1, (len(s) + 3) // 4)
    assert estimate_chunk_tokens(hit_c, fn) >= 1
    assert estimate_entity_tokens(hit_e, fn) >= 1
    assert estimate_relationship_tokens(hit_r, fn) >= 1


def test_budgeter_trims_in_correct_order():
    """Apply budget: relationships capped first (low score dropped), then entities, then parents; high-score kept."""
    bundle = ContextBundle(
        chunk_hits=[
            RetrievalHit(node_id="p1", node_label="ParentChunk", text="x" * 200, score=0.9, metadata={}, provenance={}),
            RetrievalHit(node_id="p2", node_label="ParentChunk", text="y" * 200, score=0.8, metadata={}, provenance={}),
            RetrievalHit(node_id="p3", node_label="ParentChunk", text="z" * 200, score=0.7, metadata={}, provenance={}),
            RetrievalHit(node_id="p4", node_label="ParentChunk", text="w" * 200, score=0.6, metadata={}, provenance={}),
        ],
        entity_hits=[
            EntityHit(entity_id="e1", canonical_name="E1", entity_type="Concept", score=0.95, metadata={}),
            EntityHit(entity_id="e2", canonical_name="E2", entity_type="Concept", score=0.85, metadata={}),
            EntityHit(entity_id="e3", canonical_name="E3", entity_type="Concept", score=0.75, metadata={}),
            EntityHit(entity_id="e4", canonical_name="E4", entity_type="Concept", score=0.65, metadata={}),
            EntityHit(entity_id="e5", canonical_name="E5", entity_type="Concept", score=0.55, metadata={}),
        ],
        relationship_hits=[
            RelationshipHit(source_id="e1", source_name="E1", target_id="e2", target_name="E2", rel_type="RELATES_TO", score=0.9, metadata={}),
            RelationshipHit(source_id="e2", source_name="E2", target_id="e3", target_name="E3", rel_type="RELATES_TO", score=0.8, metadata={}),
            RelationshipHit(source_id="e3", source_name="E3", target_id="e4", target_name="E4", rel_type="RELATES_TO", score=0.7, metadata={}),
            RelationshipHit(source_id="e4", source_name="E4", target_id="e5", target_name="E5", rel_type="RELATES_TO", score=0.6, metadata={}),
        ],
    )
    config = BudgetConfig(max_parents=2, max_entity_expansions=3, max_relationship_lines=2, max_total_tokens=5000)
    result = apply_budget(bundle, config=config)

    assert len(result.relationship_hits) == 2
    assert result.relationship_hits[0].score >= result.relationship_hits[1].score
    assert len(result.entity_hits) == 3
    assert result.entity_hits[0].score >= result.entity_hits[-1].score
    assert len([h for h in result.chunk_hits if h.node_label == "ParentChunk"]) == 2
    assert result.debug.get("token_budget")
    assert result.debug["token_budget"]["total_tokens"] <= config.max_total_tokens


def test_budget_debug_contains_trim_counts():
    """Debug output includes relationship_trimmed, entity_trimmed, parent_trimmed."""
    bundle = ContextBundle(
        chunk_hits=[RetrievalHit(node_id="p1", node_label="ParentChunk", text="short", score=0.9, metadata={}, provenance={})],
        entity_hits=[
            EntityHit(entity_id=f"e{i}", canonical_name=f"E{i}", entity_type="Concept", score=0.9 - i * 0.1, metadata={})
            for i in range(10)
        ],
        relationship_hits=[],
    )
    config = BudgetConfig(max_entity_expansions=2)
    result = apply_budget(bundle, config=config)
    assert result.debug.get("entity_trimmed") == 8
    assert result.debug.get("entity_kept") == 2
