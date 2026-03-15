"""
Constrained entity and relationship schema for extraction.
Extraction must use only these types; no arbitrary types by default.
"""

# Allowed entity types (strict)
ENTITY_TYPES = frozenset({
    "Person",
    "Organization",
    "Concept",
    "Technology",
    "Method",
    "Material",
    "Place",
    "Event",
    "DocumentTopic",
})

# Allowed relationship types (strict)
RELATIONSHIP_TYPES = frozenset({
    "MENTIONS",
    "RELATES_TO",
    "USES",
    "PART_OF",
    "INFLUENCES",
    "AUTHORED_BY",
    "ABOUT",
    "LOCATED_IN",
    "DERIVED_FROM",
})


def is_valid_entity_type(entity_type: str) -> bool:
    """Return True if entity_type is in the allowed set."""
    return entity_type in ENTITY_TYPES


def is_valid_relationship_type(rel_type: str) -> bool:
    """Return True if rel_type is in the allowed set."""
    return rel_type in RELATIONSHIP_TYPES


def validate_entity_type(entity_type: str) -> None:
    """Raise ValueError if entity_type is not allowed."""
    if not is_valid_entity_type(entity_type):
        raise ValueError(
            f"Invalid entity type {entity_type!r}. "
            f"Allowed: {sorted(ENTITY_TYPES)}"
        )


def validate_relationship_type(rel_type: str) -> None:
    """Raise ValueError if rel_type is not allowed."""
    if not is_valid_relationship_type(rel_type):
        raise ValueError(
            f"Invalid relationship type {rel_type!r}. "
            f"Allowed: {sorted(RELATIONSHIP_TYPES)}"
        )
