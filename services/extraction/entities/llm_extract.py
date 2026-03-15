"""
Entity-only (Pass A) extraction via LLM with strict JSON output.
"""

import json
import re
from typing import Any, Callable

from .prompts import build_extraction_prompt, get_system_prompt
from .normalize import normalize_entity


def _default_llm_call(system: str, user: str) -> str:
    """Call OpenAI chat completion. Requires openai and OPENAI_API_KEY."""
    try:
        from openai import OpenAI
        import os
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return '{"entities": []}'
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return '{"entities": []}'


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from model output; tolerate markdown code blocks."""
    text = (text or "").strip()
    # Strip markdown code block if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    if not text:
        return {"entities": []}
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return {"entities": []}
        if "entities" not in data:
            data["entities"] = []
        if not isinstance(data["entities"], list):
            data["entities"] = []
        return data
    except json.JSONDecodeError:
        return {"entities": []}


def extract_entities(
    chunk_text: str,
    glossary: dict,
    schema: dict,
    *,
    llm_call: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """
    Extract entities from chunk text (Pass A: entity-only).
    - Uses strict prompt with allowed types only.
    - Parses LLM JSON and normalizes each entity (whitespace, type validation, glossary resolution).
    - llm_call(system, user) -> response_text; if None, uses default OpenAI call.
    Returns {"entities": [{"raw_text", "canonical_candidate", "type", "description", "confidence"}, ...]}.
    """
    system = get_system_prompt(schema)
    user = build_extraction_prompt(chunk_text, schema)
    call = llm_call or _default_llm_call
    response = call(system, user)
    data = _parse_json_response(response)
    entities = data.get("entities") or []
    schema_typed = schema if isinstance(schema, dict) else {}
    if not schema_typed and schema is not None:
        try:
            from .schema import ENTITY_TYPES
            schema_typed = {"entity_types": list(ENTITY_TYPES)}
        except Exception:
            schema_typed = {}
    if not schema_typed:
        from .schema import ENTITY_TYPES
        schema_typed = {"entity_types": list(ENTITY_TYPES)}
    normalized = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        try:
            norm = normalize_entity(ent, glossary, schema_typed)
            if norm.get("raw_text") or norm.get("canonical_candidate"):
                normalized.append(norm)
        except Exception:
            continue
    return {"entities": normalized}
