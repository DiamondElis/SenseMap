"""
Canonicalize entity names for exact-match resolution.
Glossary-driven: resolve aliases to canonical name before other resolution steps.
"""

import re
from typing import Any


def canonicalize_name(name: str) -> str:
    """
    Normalize a name for comparison: strip, lowercase, collapse whitespace, remove surrounding punctuation.
    Does not apply glossary; use glossary_canonical_name for alias resolution.
    """
    if not name or not isinstance(name, str):
        return ""
    s = name.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^[\s\.,;:!?\-—–\'\"\(\)\[\]]+", "", s)
    s = re.sub(r"[\s\.,;:!?\-—–\'\"\(\)\[\]]+$", "", s)
    return s.strip()


def _build_glossary_lookup(glossary: dict) -> dict[str, str]:
    """Build map: normalized alias or canonical -> canonical_name."""
    lookup: dict[str, str] = {}
    entities = glossary.get("entities") if isinstance(glossary, dict) else []
    if not entities:
        return lookup
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        canonical = (ent.get("canonical_name") or "").strip()
        if not canonical:
            continue
        lookup[canonicalize_name(canonical)] = canonical
        for a in ent.get("aliases") or []:
            if a and isinstance(a, str):
                lookup[canonicalize_name(a)] = canonical
    return lookup


def glossary_canonical_name(name: str, glossary: dict) -> str | None:
    """
    If name (or its canonical form) is an alias or canonical name in the glossary, return the canonical name.
    Otherwise return None. Use before exact match so alias-heavy duplicates resolve cleanly.
    """
    if not name or not isinstance(glossary, dict):
        return None
    key = canonicalize_name(name)
    return _build_glossary_lookup(glossary).get(key)
