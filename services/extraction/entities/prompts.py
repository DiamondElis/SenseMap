"""
Strict extraction prompts for entity-only (Pass A) extraction.
Model must return JSON with allowed types only.
"""

from .schema import ENTITY_TYPES

ALLOWED_TYPES_STR = ", ".join(sorted(ENTITY_TYPES))

EXTRACTION_SYSTEM = f"""You are an entity extractor. Extract only named entities from the given text.
You must output valid JSON only, with no markdown or commentary.

Allowed entity types (use exactly these): {ALLOWED_TYPES_STR}

Output format (strict):
{{
  "entities": [
    {{
      "raw_text": "exact span from text",
      "canonical_candidate": "normalized form or same as raw_text",
      "type": "one of the allowed types above",
      "description": "brief description or empty string",
      "confidence": 0.0 to 1.0
    }}
  ]
}}

Rules:
- Include only entities that appear in the text.
- Use only the allowed types listed above.
- raw_text: exact substring from the input.
- canonical_candidate: normalized name (e.g. title case, no extra punctuation); use raw_text if unsure.
- confidence: your confidence in this extraction (0.0-1.0).
- If no entities found, return {{ "entities": [] }}."""


def build_extraction_prompt(chunk_text: str, schema: dict | None = None) -> str:
    """
    Build the user prompt for entity extraction.
    schema may provide entity_types list; otherwise ENTITY_TYPES from schema module is used.
    """
    types_str = ALLOWED_TYPES_STR
    if schema and "entity_types" in schema:
        types_str = ", ".join(sorted(schema["entity_types"]))
    return f"""Extract all named entities from this text. Use only these types: {types_str}.
Return strict JSON with an "entities" array. No other output.

Text:
---
{chunk_text}
---
"""


def get_system_prompt(schema: dict | None = None) -> str:
    """Return the system prompt for entity extraction. schema optional override for entity_types."""
    return EXTRACTION_SYSTEM
