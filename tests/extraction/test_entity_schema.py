"""Unit tests for entity schema: type validation and rejection of invalid types."""
import pytest

from services.extraction.entities.schema import (
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
    is_valid_entity_type,
    is_valid_relationship_type,
    validate_entity_type,
    validate_relationship_type,
)


def test_valid_entity_types_accepted():
    """Every allowed entity type is accepted by is_valid_entity_type and validate_entity_type."""
    for t in ENTITY_TYPES:
        assert is_valid_entity_type(t) is True
        validate_entity_type(t)  # no raise


def test_invalid_entity_type_rejected():
    """Invalid entity type returns False and validate_entity_type raises ValueError."""
    assert is_valid_entity_type("") is False
    assert is_valid_entity_type("InvalidType") is False
    assert is_valid_entity_type("person") is False  # case-sensitive
    assert is_valid_entity_type("PERSON") is False

    with pytest.raises(ValueError) as exc_info:
        validate_entity_type("InvalidType")
    assert "Invalid entity type" in str(exc_info.value)
    assert "InvalidType" in str(exc_info.value)
    assert "Allowed:" in str(exc_info.value)


def test_valid_relationship_types_accepted():
    """Every allowed relationship type is accepted."""
    for t in RELATIONSHIP_TYPES:
        assert is_valid_relationship_type(t) is True
        validate_relationship_type(t)  # no raise


def test_invalid_relationship_type_rejected():
    """Invalid relationship type returns False and validate_relationship_type raises ValueError."""
    assert is_valid_relationship_type("") is False
    assert is_valid_relationship_type("INVALID_REL") is False

    with pytest.raises(ValueError) as exc_info:
        validate_relationship_type("INVALID_REL")
    assert "Invalid relationship type" in str(exc_info.value)
    assert "INVALID_REL" in str(exc_info.value)
