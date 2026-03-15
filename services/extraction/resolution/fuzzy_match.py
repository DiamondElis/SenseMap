"""
Fuzzy match a candidate entity against existing entities by name similarity.
"""

import difflib
from typing import Any

from .canonicalize import canonicalize_name


def fuzzy_match_entity(
    candidate: dict,
    existing_entities: list[dict],
    *,
    threshold: float = 0.85,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Return list of existing entities that fuzzy-match the candidate name, sorted by score descending.
    Each item: {entity_id, name, type, score} with score in [0, 1].
    Only includes entities with score >= threshold. Requires type agreement for inclusion
    (caller may still use for review if types differ).
    """
    name = (candidate.get("canonical_candidate") or candidate.get("name") or "").strip()
    if not name:
        return []
    cand_type = (candidate.get("type") or "").strip()
    norm_name = canonicalize_name(name)
    if not norm_name:
        return []

    scored: list[dict[str, Any]] = []
    for e in existing_entities:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        ename = (e.get("name") or e.get("canonical_name") or "").strip()
        if not ename or eid is None:
            continue
        norm_e = canonicalize_name(ename)
        if not norm_e:
            continue
        ratio = difflib.SequenceMatcher(None, norm_name, norm_e).ratio()
        if ratio < threshold:
            continue
        scored.append({
            "entity_id": str(eid),
            "name": ename,
            "type": (e.get("type") or "").strip(),
            "score": round(ratio, 4),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
