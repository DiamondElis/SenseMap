"""
Normalize raw extracted entities: whitespace, casing, punctuation, type validation, glossary resolution.
"""

import re
from typing import Any

from .schema import ENTITY_TYPES


def _strip_surrounding_punctuation(s: str) -> str:
    """Remove leading/trailing punctuation and whitespace."""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"^[\s\.,;:!?\-—–\'\"\(\)\[\]]+", "", s)
    s = re.sub(r"[\s\.,;:!?\-—–\'\"\(\)\[\]]+$", "", s)
    return s.strip()


def _normalize_casing(s: str) -> str:
    """Title-case for multi-word; leave single words as-is (capitalized)."""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    if not s:
        return ""
    if " " in s or "-" in s:
        return s.title()
    return s[0].upper() + s[1:].lower() if len(s) > 1 else s.upper()


def _build_alias_map(glossary: dict) -> dict[str, dict[str, Any]]:
    """Build map: normalized alias -> {canonical_name, type, description}."""
    alias_map: dict[str, dict[str, Any]] = {}
    entities = glossary.get("entities") if isinstance(glossary, dict) else []
    if not entities:
        return alias_map
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        canonical = ent.get("canonical_name") or ""
        typ = ent.get("type") or ""
        desc = ent.get("description") or ""
        alias_map[canonical.strip().lower()] = {"canonical_name": canonical.strip(), "type": typ, "description": desc}
        for a in ent.get("aliases") or []:
            if a and isinstance(a, str):
                alias_map[a.strip().lower()] = {"canonical_name": canonical.strip(), "type": typ, "description": desc}
    return alias_map


def normalize_entity(
    raw_entity: dict,
    glossary: dict,
    schema: dict,
) -> dict[str, Any]:
    """
    Normalize a single raw extracted entity.
    - Strip whitespace and surrounding punctuation from text fields.
    - Title/case cleanup for canonical_candidate.
    - Validate type against schema; if invalid, remap to DocumentTopic as safe default or drop.
    - If raw_text/canonical_candidate matches a glossary alias, set canonical_candidate to glossary canonical_name and use glossary type/description when missing.
    Returns a dict with keys: raw_text, canonical_candidate, type, description, confidence.
    Invalid types are remapped to DocumentTopic (safe default) so we don't drop entities.
    """
    allowed = set(schema.get("entity_types", ENTITY_TYPES))
    raw_text = (raw_entity.get("raw_text") or "")
    if isinstance(raw_text, str):
        raw_text = _strip_surrounding_punctuation(raw_text)
    else:
        raw_text = ""
    canonical_candidate = (raw_entity.get("canonical_candidate") or raw_text or "")
    if isinstance(canonical_candidate, str):
        canonical_candidate = _strip_surrounding_punctuation(canonical_candidate)
    else:
        canonical_candidate = str(canonical_candidate).strip()
    if canonical_candidate:
        canonical_candidate = _normalize_casing(canonical_candidate)
    entity_type = (raw_entity.get("type") or "").strip()
    description = (raw_entity.get("description") or "")
    if isinstance(description, str):
        description = description.strip()[:500]
    else:
        description = ""
    confidence = raw_entity.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
    if confidence is None or not (0 <= confidence <= 1):
        confidence = 0.0

    alias_map = _build_alias_map(glossary)
    lookup_key = (canonical_candidate or raw_text).lower()
    if lookup_key in alias_map:
        info = alias_map[lookup_key]
        canonical_candidate = info.get("canonical_name", canonical_candidate)
        if not entity_type or entity_type not in allowed:
            entity_type = info.get("type", entity_type)
        if not description and info.get("description"):
            description = info.get("description", "")[:500]

    if entity_type not in allowed:
        entity_type = "DocumentTopic"

    return {
        "raw_text": raw_text,
        "canonical_candidate": canonical_candidate,
        "type": entity_type,
        "description": description,
        "confidence": float(confidence),
    }
