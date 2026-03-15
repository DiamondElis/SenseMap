"""Unit tests for relationship normalization: type validation, entity refs, self-loops."""
import pytest

from services.extraction.entities.schema import RELATIONSHIP_TYPES
from services.extraction.relations.normalize import normalize_relationship, normalize_relationships


def _schema():
    return {"relationship_types": set(RELATIONSHIP_TYPES)}


def _entities():
    return [
        {"canonical_candidate": "Acme Corp", "raw_text": "Acme Corp", "type": "Organization"},
        {"canonical_candidate": "Bob Smith", "raw_text": "Bob Smith", "type": "Person"},
    ]


def test_relation_type_normalization_works():
    """Valid relationship type with valid source/target names returns normalized dict."""
    rel = {
        "source_name": "Acme Corp",
        "target_name": "Bob Smith",
        "type": "RELATES_TO",
        "confidence": 0.9,
    }
    out = normalize_relationship(rel, _entities(), _schema())
    assert out is not None
    assert out["type"] == "RELATES_TO"
    assert out["source_name"] == "Acme Corp"
    assert out["target_name"] == "Bob Smith"
    assert out["confidence"] == 0.9


def test_invalid_relation_type_returns_none():
    """Invalid relationship type is rejected (returns None)."""
    rel = {"source_name": "Acme Corp", "target_name": "Bob Smith", "type": "INVALID_TYPE"}
    assert normalize_relationship(rel, _entities(), _schema()) is None


def test_relationship_source_target_must_be_in_entity_set():
    """Source and target must match extracted entity names (case-insensitive)."""
    rel = {"source_name": "Acme Corp", "target_name": "Unknown Entity", "type": "RELATES_TO"}
    assert normalize_relationship(rel, _entities(), _schema()) is None

    rel2 = {"source_name": "Unknown", "target_name": "Bob Smith", "type": "RELATES_TO"}
    assert normalize_relationship(rel2, _entities(), _schema()) is None


def test_self_loop_discarded_by_default():
    """Self-loops (source == target) are discarded unless allow_self_loops=True."""
    entities = [{"canonical_candidate": "Acme", "raw_text": "Acme", "type": "Organization"}]
    rel = {"source_name": "Acme", "target_name": "Acme", "type": "RELATES_TO"}
    assert normalize_relationship(rel, entities, _schema(), allow_self_loops=False) is None
    out = normalize_relationship(rel, entities, _schema(), allow_self_loops=True)
    assert out is not None
    assert out["source_name"] == out["target_name"] == "Acme"


def test_normalize_relationships_filters_invalid():
    """normalize_relationships returns only valid relationships."""
    entities = _entities()
    rels = [
        {"source_name": "Acme Corp", "target_name": "Bob Smith", "type": "RELATES_TO"},
        {"source_name": "Acme Corp", "target_name": "Bob Smith", "type": "INVALID"},
        {"source_name": "Acme Corp", "target_name": "Bob Smith", "type": "MENTIONS"},
    ]
    out = normalize_relationships(rels, entities, _schema())
    assert len(out) == 2
    types = {r["type"] for r in out}
    assert "RELATES_TO" in types and "MENTIONS" in types
    assert "INVALID" not in types
