"""Unit tests for entity resolution: exact match, ambiguous short name returns review, conflicting type blocks auto-merge."""
import pytest

from services.extraction.resolution.merge import resolve_entity, ResolutionResult
from services.extraction.resolution.canonicalize import canonicalize_name, glossary_canonical_name


def test_exact_match_resolution_works():
    """When candidate normalizes to same name as an existing entity (and type agrees), resolution is exact_match."""
    existing = [
        {"id": "ent_1", "name": "Acme Corporation", "canonical_name": "Acme Corporation", "type": "Organization"},
    ]
    glossary = {}
    candidate = {"canonical_candidate": "Acme Corporation", "type": "Organization", "raw_text": "Acme Corp"}
    result = resolve_entity(candidate, existing, glossary)
    assert result.action == "exact_match"
    assert result.entity_id == "ent_1"
    assert result.confidence == 1.0


def test_exact_match_after_glossary_canonicalization():
    """Glossary alias resolving to existing canonical name yields exact_match."""
    existing = [
        {"id": "ent_1", "name": "Acme Corporation", "canonical_name": "Acme Corporation", "type": "Organization"},
    ]
    glossary = {
        "entities": [
            {"canonical_name": "Acme Corporation", "type": "Organization", "aliases": ["Acme Corp"]},
        ],
    }
    candidate = {"canonical_candidate": "Acme Corp", "type": "Organization", "raw_text": "Acme Corp"}
    result = resolve_entity(candidate, existing, glossary)
    assert result.action == "exact_match"
    assert result.entity_id == "ent_1"


def test_conflicting_type_blocks_auto_merge():
    """When name matches exactly but type conflicts, resolution is review (no auto-merge)."""
    existing = [
        {"id": "ent_1", "name": "Acme", "canonical_name": "Acme", "type": "Organization"},
    ]
    glossary = {}
    candidate = {"canonical_candidate": "Acme", "type": "Person", "raw_text": "Acme"}
    result = resolve_entity(candidate, existing, glossary)
    assert result.action == "review"
    assert result.entity_id is None
    assert len(result.candidates) == 1
    assert result.candidates[0]["entity_id"] == "ent_1"


def test_ambiguous_short_name_returns_review():
    """Short-name candidate that matches via embedding but is_short_name=True yields review (no unsafe merge)."""
    # Resolver does not auto-merge when candidate name is short (<=4 chars) to avoid ambiguous merges.
    def high_sim_embed(texts):
        return [[0.9] * 64 for _ in texts]

    existing = [
        {"id": "e1", "name": "NLP", "canonical_name": "NLP", "type": "Concept", "embedding": [0.9] * 64},
    ]
    # "N.L.P." normalizes to "n.l.p." so no exact match with "nlp"; embedding similarity can be high
    # but is_short_name=True forces review.
    candidate = {"canonical_candidate": "N.L.P.", "type": "Concept", "raw_text": "N.L.P."}
    result = resolve_entity(candidate, existing, {}, embed_fn=high_sim_embed)
    assert result.action == "review"
    assert result.entity_id is None
    assert len(result.candidates) >= 1




def test_create_new_when_no_match():
    """When no existing entity matches, resolution is create_new."""
    existing = []
    candidate = {"canonical_candidate": "New Entity", "type": "Concept", "raw_text": "New Entity"}
    result = resolve_entity(candidate, existing, {})
    assert result.action == "create_new"
    assert result.entity_id is None
    assert result.confidence == 0.0


def test_canonicalize_name_normalizes_for_comparison():
    """canonicalize_name strips, lowercases, collapses space, removes surrounding punctuation."""
    assert canonicalize_name("  Acme   Corp  ") == "acme corp"
    assert canonicalize_name("Acme Corp.") == "acme corp"
    assert canonicalize_name("") == ""


def test_glossary_canonical_name_returns_canonical():
    """glossary_canonical_name returns the canonical name when input is an alias."""
    glossary = {
        "entities": [
            {"canonical_name": "Acme Corporation", "aliases": ["Acme Corp", "ACME"]},
        ],
    }
    assert glossary_canonical_name("Acme Corp", glossary) == "Acme Corporation"
    assert glossary_canonical_name("acme", glossary) == "Acme Corporation"
    assert glossary_canonical_name("Unknown", glossary) is None
