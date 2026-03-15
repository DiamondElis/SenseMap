"""Unit tests for entity normalization: glossary alias maps to canonical candidate."""
import pytest

from services.extraction.entities.schema import ENTITY_TYPES
from services.extraction.entities.normalize import normalize_entity


def _schema():
    return {"entity_types": list(ENTITY_TYPES)}


def test_glossary_alias_maps_to_canonical_candidate():
    """When raw_text or canonical_candidate matches a glossary alias, output uses glossary canonical_name and type."""
    glossary = {
        "entities": [
            {
                "canonical_name": "Acme Corporation",
                "type": "Organization",
                "description": "Main company",
                "aliases": ["Acme Corp", "acme"],
            },
        ],
    }
    raw = {
        "raw_text": "Acme Corp",
        "canonical_candidate": "Acme Corp",
        "type": "",
        "description": "",
        "confidence": 0.9,
    }
    out = normalize_entity(raw, glossary, _schema())
    assert out["canonical_candidate"] == "Acme Corporation"
    assert out["type"] == "Organization"
    assert "Main" in (out.get("description") or "")


def test_glossary_canonical_name_lookup():
    """When canonical_candidate is the glossary canonical name, it is preserved."""
    glossary = {
        "entities": [
            {"canonical_name": "Bob Smith", "type": "Person", "aliases": []},
        ],
    }
    raw = {"raw_text": "Bob Smith", "canonical_candidate": "Bob Smith", "type": "Person", "confidence": 1.0}
    out = normalize_entity(raw, glossary, _schema())
    assert out["canonical_candidate"] == "Bob Smith"
    assert out["type"] == "Person"


def test_glossary_case_insensitive_alias():
    """Glossary alias lookup is case-insensitive."""
    glossary = {
        "entities": [
            {"canonical_name": "Acme", "type": "Organization", "aliases": ["ACME"]},
        ],
    }
    raw = {"raw_text": "acme", "canonical_candidate": "acme", "type": "", "confidence": 0.8}
    out = normalize_entity(raw, glossary, _schema())
    assert out["canonical_candidate"] == "Acme"
    assert out["type"] == "Organization"


def test_invalid_entity_type_remapped_to_document_topic():
    """Invalid entity type is remapped to DocumentTopic (safe default), not dropped."""
    raw = {"raw_text": "Foo", "canonical_candidate": "Foo", "type": "InvalidType", "confidence": 0.5}
    out = normalize_entity(raw, {}, _schema())
    assert out["type"] == "DocumentTopic"
    assert out["canonical_candidate"] == "Foo"
