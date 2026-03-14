"""
Entity extraction from chunk text: LLM for flexible typed entities, spaCy as cheaper fallback.
Output: list of {id, name, type} per chunk.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _entity_id(name: str, type_: str) -> str:
    h = hashlib.sha256(f"{name.strip().lower()}|{type_}".encode()).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())[:64]
    return f"ent_{safe}_{h}"


def extract_entities_llm(text: str, api_key: str | None = None) -> list[dict[str, Any]]:
    """Use LLM to extract entities with types. Returns [{id, name, type}, ...]."""
    key = api_key or OPENAI_API_KEY
    if not key or not text.strip():
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Extract all named entities from the text. For each entity give a type: PERSON, ORG, LOCATION, DATE, or OTHER. Reply with a JSON array of objects with keys 'name' and 'type' only. No other text.",
                },
                {"role": "user", "content": text[:8000]},
            ],
            max_tokens=1024,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Handle markdown code block
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            type_ = (item.get("type") or "OTHER").strip().upper()
            if not name or len(name) > 500:
                continue
            if type_ not in ("PERSON", "ORG", "LOCATION", "DATE", "OTHER"):
                type_ = "OTHER"
            key_ = (name.lower(), type_)
            if key_ in seen:
                continue
            seen.add(key_)
            out.append({"id": _entity_id(name, type_), "name": name, "type": type_})
        return out
    except Exception:
        return []


def extract_entities_spacy(text: str) -> list[dict[str, Any]]:
    """Use spaCy NER as fallback. Returns [{id, name, type}, ...]."""
    if not text.strip():
        return []
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        return []
    doc = nlp(text[:100000])
    type_map = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOCATION", "LOC": "LOCATION", "DATE": "DATE", "NORP": "ORG"}
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for ent in doc.ents:
        name = ent.text.strip()
        if not name or len(name) > 500:
            continue
        type_ = type_map.get(ent.label_, "OTHER")
        key_ = (name.lower(), type_)
        if key_ in seen:
            continue
        seen.add(key_)
        out.append({"id": _entity_id(name, type_), "name": name, "type": type_})
    return out


def extract_entities(text: str, use_llm: bool = True, api_key: str | None = None) -> list[dict[str, Any]]:
    """Hybrid: try LLM first if key set and use_llm; else spaCy."""
    if use_llm and (api_key or OPENAI_API_KEY):
        entities = extract_entities_llm(text, api_key=api_key or OPENAI_API_KEY or None)
        if entities:
            return entities
    return extract_entities_spacy(text)
