"""
Strict prompts for Pass B: relationship extraction.
Model must return only approved relationship types; source/target must be from the given entity list.
"""

from ..entities.schema import RELATIONSHIP_TYPES

ALLOWED_REL_TYPES_STR = ", ".join(sorted(RELATIONSHIP_TYPES))

RELATION_EXTRACTION_SYSTEM = f"""You are a relationship extractor. Given text and a list of known entities, extract directed relationships between those entities only.
You must output valid JSON only, with no markdown or commentary.

Allowed relationship types (use exactly these): {ALLOWED_REL_TYPES_STR}

Output format (strict):
{{
  "relationships": [
    {{
      "source_name": "exact name from entity list",
      "source_type": "entity type",
      "target_name": "exact name from entity list",
      "target_type": "entity type",
      "type": "one of the allowed relationship types above",
      "confidence": 0.0 to 1.0,
      "description": "brief optional description or empty string"
    }}
  ]
}}

Rules:
- source_name and target_name must be exactly one of the provided entity names (canonical or alias).
- Use only the allowed relationship types listed above.
- Each relationship is directed: source --[type]--> target.
- confidence: your confidence in this extraction (0.0-1.0).
- If no relationships found, return {{ "relationships": [] }}."""


def build_relation_extraction_prompt(
    chunk_text: str,
    entities: list[dict],
    schema: dict | None = None,
    context: str | None = None,
) -> str:
    """
    Build the user prompt for relationship extraction.
    entities: list of Pass A entities (must have canonical_candidate; may have raw_text, type).
    context: optional nearby chunk text.
    """
    rel_types_str = ALLOWED_REL_TYPES_STR
    if schema and "relationship_types" in schema:
        rel_types_str = ", ".join(sorted(schema["relationship_types"]))
    names = set()
    for e in entities:
        if isinstance(e, dict):
            if e.get("canonical_candidate"):
                names.add((e.get("canonical_candidate") or "").strip())
            if e.get("raw_text"):
                names.add((e.get("raw_text") or "").strip())
    entity_list = sorted(names) if names else ["(none)"]
    entity_block = "\n".join(f"  - {n}" for n in entity_list)
    prompt = f"""Extract directed relationships between the entities listed below, using only this text.
Allowed relationship types: {rel_types_str}
Return strict JSON with a "relationships" array. No other output.

Known entities (use these exact names for source_name and target_name):
{entity_block}

Text:
---
{chunk_text}
---
"""
    if context:
        prompt += f"""
Optional context (nearby text):
---
{context[:1500]}
---
"""
    return prompt


def get_relation_system_prompt(schema: dict | None = None) -> str:
    """Return the system prompt for relationship extraction."""
    return RELATION_EXTRACTION_SYSTEM
