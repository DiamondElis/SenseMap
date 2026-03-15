"""
Normalize extracted relationships: validate type, ensure source/target in entity set, discard self-loops, direction.
"""

from typing import Any

from ..entities.schema import RELATIONSHIP_TYPES, is_valid_relationship_type


def _entity_name_set(entities: list[dict]) -> set[str]:
    """Build set of acceptable names (canonical_candidate, raw_text) from Pass A entities."""
    names: set[str] = set()
    for e in entities:
        if not isinstance(e, dict):
            continue
        for key in ("canonical_candidate", "raw_text"):
            val = e.get(key)
            if val and isinstance(val, str):
                names.add(val.strip())
                names.add(val.strip().lower())
    return names


def normalize_relationship(
    rel: dict,
    entities: list[dict],
    schema: dict,
    *,
    allow_self_loops: bool = False,
) -> dict[str, Any] | None:
    """
    Normalize a single relationship.
    - Validate relationship type against schema; reject if invalid.
    - Ensure source_name and target_name reference the extracted entity set (by name match).
    - Discard self-loops (source == target) unless allow_self_loops.
    - Return normalized dict or None if malformed/unsupported.
    """
    if not rel or not isinstance(rel, dict):
        return None
    rel_types = set(schema.get("relationship_types", RELATIONSHIP_TYPES))
    rel_type = (rel.get("type") or "").strip()
    if not rel_type or not is_valid_relationship_type(rel_type) or rel_type not in rel_types:
        return None
    source_name = (rel.get("source_name") or "").strip()
    target_name = (rel.get("target_name") or "").strip()
    if not source_name or not target_name:
        return None
    name_set = _entity_name_set(entities)
    # Match case-insensitively for inclusion
    if source_name.lower() not in name_set and source_name not in name_set:
        return None
    if target_name.lower() not in name_set and target_name not in name_set:
        return None
    if not allow_self_loops and source_name.lower() == target_name.lower():
        return None
    source_type = (rel.get("source_type") or "").strip()
    target_type = (rel.get("target_type") or "").strip()
    description = (rel.get("description") or "")
    if isinstance(description, str):
        description = description.strip()[:500]
    else:
        description = ""
    confidence = rel.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
    if confidence is None or not (0 <= confidence <= 1):
        confidence = 0.0
    return {
        "source_name": source_name,
        "source_type": source_type,
        "target_name": target_name,
        "target_type": target_type,
        "type": rel_type,
        "confidence": float(confidence),
        "description": description,
    }


def normalize_relationships(
    relationships: list[dict],
    entities: list[dict],
    schema: dict,
    *,
    allow_self_loops: bool = False,
) -> list[dict[str, Any]]:
    """
    Normalize and filter a list of relationships.
    Returns only relationships that reference known entities and pass validation.
    """
    result = []
    for rel in relationships:
        norm = normalize_relationship(rel, entities, schema, allow_self_loops=allow_self_loops)
        if norm is not None:
            result.append(norm)
    return result
