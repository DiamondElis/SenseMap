"""Unit tests for entity_writer: write_entity_graph produces correct queries and params."""
from unittest.mock import MagicMock, patch

import pytest

from services.graph_builder.entity_writer import (
    write_entity_graph,
    _resolve_entity_ids,
    _name_to_entity_id_map,
    _stable_entity_id,
)


def test_stable_entity_id_deterministic():
    """_stable_entity_id is deterministic for same (canonical_name, type)."""
    a = _stable_entity_id("Acme Corp", "Organization")
    b = _stable_entity_id("Acme Corp", "Organization")
    assert a == b
    assert a.startswith("entity_")
    assert len(a) == len("entity_") + 16


def test_resolve_entity_ids_uses_resolution_result_entity_id():
    """_resolve_entity_ids uses resolution_results[i].entity_id when set."""
    entities = [
        {"canonical_candidate": "Acme", "type": "Organization"},
        {"canonical_candidate": "Bob", "type": "Person"},
    ]
    class Res:
        entity_id = "existing_ent_1"
    results = [Res(), None]
    out = _resolve_entity_ids(entities, results)
    assert len(out) == 2
    assert out[0][0] == "existing_ent_1"
    assert out[0][1] == "Acme"
    assert out[1][0] != "existing_ent_1"
    assert out[1][1] == "Bob"


def test_resolve_entity_ids_generates_stable_id_when_no_result():
    """When resolution result has no entity_id, _resolve_entity_ids uses _stable_entity_id."""
    entities = [{"canonical_candidate": "New Entity", "type": "Concept"}]
    results = []
    out = _resolve_entity_ids(entities, results)
    assert len(out) == 1
    assert out[0][0].startswith("entity_")
    assert out[0][1] == "New Entity"


def test_name_to_entity_id_map_includes_canonical_and_raw():
    """_name_to_entity_id_map maps both canonical_candidate and raw_text to entity_id."""
    entities = [
        {"canonical_candidate": "Acme Corp", "raw_text": "Acme", "type": "Organization"},
    ]
    class Res:
        entity_id = "ent_1"
    results = [Res()]
    m = _name_to_entity_id_map(entities, results)
    assert m.get("Acme Corp") == "ent_1"
    assert m.get("acme corp") == "ent_1"
    assert m.get("Acme") == "ent_1"


@patch("services.graph_builder.entity_writer.get_driver")
def test_write_entity_graph_merges_entities_and_mentions(mock_get_driver):
    """write_entity_graph MERGEs Entity nodes and EntityMention, links Chunk-MENTIONS-Mention-REFERS_TO-Entity."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    entities = [
        {"canonical_candidate": "Acme", "raw_text": "Acme", "type": "Organization", "confidence": 0.9},
    ]
    relationships = []
    class Res:
        entity_id = None
    resolution_results = [Res()]

    write_entity_graph(
        "chunk_1",
        entities,
        relationships,
        resolution_results,
        "test_extractor",
    )

    mock_driver.close.assert_called_once()
    calls = [c[0][0] for c in mock_session.run.call_args_list]
    assert any("MERGE (e:Entity" in c and "row.id" in c for c in calls)
    assert any("EntityMention" in c and "MENTIONS" in c for c in calls)
    assert any("entity_processed_at" in c for c in calls)


@patch("services.graph_builder.entity_writer.get_driver")
def test_write_entity_graph_empty_entities_marks_processed(mock_get_driver):
    """write_entity_graph with no entities still marks chunk as entity_processed_at and creates Claim."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    write_entity_graph("chunk_empty", [], [], [], "test")

    mock_driver.close.assert_called_once()
    calls = [c[0][0] for c in mock_session.run.call_args_list]
    assert any("entity_processed_at" in c and "chunk_empty" in (c or "") for c in calls)
    assert any("Claim" in c and "SUPPORTED_BY" in c for c in calls)


@patch("services.graph_builder.entity_writer.get_driver")
def test_write_entity_graph_skips_empty_chunk_id(mock_get_driver):
    """write_entity_graph with empty chunk_id does nothing (no session run)."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    write_entity_graph("", [{"canonical_candidate": "E", "type": "Concept"}], [], [], "test")
    write_entity_graph("   ", [{"canonical_candidate": "E", "type": "Concept"}], [], [], "test")

    mock_session.run.assert_not_called()
