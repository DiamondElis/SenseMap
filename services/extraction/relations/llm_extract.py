"""
Pass B: relationship extraction via LLM with strict JSON output.
Takes chunk text and extracted entities (Pass A); returns typed directed relationships.
"""

import json
import re
from typing import Any, Callable

from .prompts import build_relation_extraction_prompt, get_relation_system_prompt
from .normalize import normalize_relationships


def _default_llm_call(system: str, user: str) -> str:
    """Call OpenAI chat completion. Requires openai and OPENAI_API_KEY."""
    try:
        from openai import OpenAI
        import os
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return '{"relationships": []}'
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
        return '{"relationships": []}'


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from model output; tolerate markdown code blocks."""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    if not text:
        return {"relationships": []}
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return {"relationships": []}
        if "relationships" not in data:
            data["relationships"] = []
        if not isinstance(data["relationships"], list):
            data["relationships"] = []
        return data
    except json.JSONDecodeError:
        return {"relationships": []}


def extract_relationships(
    chunk_text: str,
    entities: list[dict],
    schema: dict,
    *,
    context: str | None = None,
    allow_self_loops: bool = False,
    llm_call: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """
    Extract relationships from chunk text given Pass A entities (Pass B).
    - Uses strict prompt with allowed relationship types only.
    - Source/target must be from the provided entity list.
    - Parses LLM JSON and normalizes each relationship (type validation, entity scope, self-loops).
    - context: optional nearby chunk text.
    - allow_self_loops: if False, drop source_name == target_name.
    Returns {"relationships": [{"source_name", "source_type", "target_name", "target_type", "type", "confidence", "description"}, ...]}.
    """
    system = get_relation_system_prompt(schema)
    user = build_relation_extraction_prompt(chunk_text, entities, schema, context=context)
    call = llm_call or _default_llm_call
    response = call(system, user)
    data = _parse_json_response(response)
    raw = data.get("relationships") or []
    schema_typed = schema if isinstance(schema, dict) else {}
    if not schema_typed:
        from ..entities.schema import RELATIONSHIP_TYPES
        schema_typed = {"relationship_types": set(RELATIONSHIP_TYPES)}
    if "relationship_types" not in schema_typed:
        from ..entities.schema import RELATIONSHIP_TYPES
        schema_typed = {"relationship_types": set(RELATIONSHIP_TYPES)}
    normalized = normalize_relationships(
        raw,
        entities,
        schema_typed,
        allow_self_loops=allow_self_loops,
    )
    return {"relationships": normalized}
