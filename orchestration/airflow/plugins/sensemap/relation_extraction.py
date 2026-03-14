"""
Relation extraction between entities that co-occur in the same chunk.
LLM for flexible relation types; simple fallback otherwise.
Output: list of (entity_a_id, entity_b_id, relation_type).
"""
from __future__ import annotations

import os
from typing import Any

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def extract_relations_llm(
    text: str,
    entity_pairs: list[tuple[str, str, str, str]],
    api_key: str | None = None,
) -> list[tuple[str, str, str]]:
    """
    entity_pairs: list of (entity_a_id, entity_a_name, entity_b_id, entity_b_name).
    Returns list of (entity_a_id, entity_b_id, relation_type).
    """
    key = api_key or OPENAI_API_KEY
    if not key or not entity_pairs:
        return []
    if not text.strip():
        return [(a_id, b_id, "RELATED_TO") for a_id, _, b_id, _ in entity_pairs]
    out: list[tuple[str, str, str]] = []
    # Batch pairs to stay under token limit
    batch_size = 15
    for i in range(0, len(entity_pairs), batch_size):
        batch = entity_pairs[i : i + batch_size]
        pairs_desc = "; ".join(f"({aname}, {bname})" for _, aname, _, bname in batch)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Given the text and entity pairs, for each pair give a short relation type (e.g. WORKS_AT, LOCATED_IN, FOUNDED). Reply with a JSON array of strings, one per pair in order. Use RELATED_TO if unclear.",
                    },
                    {"role": "user", "content": f"Text:\n{text[:4000]}\n\nPairs (in order): {pairs_desc}"},
                ],
                max_tokens=512,
            )
            raw = (resp.choices[0].message.content or "").strip()
            if "```" in raw:
                raw = raw.split("```")[1].replace("json", "").strip()
            labels = __import__("json").loads(raw)
            if isinstance(labels, list):
                for idx, (a_id, _, b_id, _) in enumerate(batch):
                    label = labels[idx] if idx < len(labels) else "RELATED_TO"
                    rel = (label if isinstance(label, str) else "RELATED_TO").strip().replace(" ", "_")[:64] or "RELATED_TO"
                    out.append((a_id, b_id, rel))
            else:
                for a_id, _, b_id, _ in batch:
                    out.append((a_id, b_id, "RELATED_TO"))
        except Exception:
            for a_id, _, b_id, _ in batch:
                out.append((a_id, b_id, "RELATED_TO"))
    return out


def extract_relations_fallback(entity_pairs: list[tuple[str, str, str, str]]) -> list[tuple[str, str, str]]:
    """No LLM: assign generic RELATED_TO."""
    return [(a_id, b_id, "RELATED_TO") for a_id, _, b_id, _ in entity_pairs]


def extract_relations(
    text: str,
    entity_pairs: list[tuple[str, str, str, str]],
    use_llm: bool = True,
    api_key: str | None = None,
) -> list[tuple[str, str, str]]:
    """Hybrid: LLM if available, else fallback."""
    if use_llm and (api_key or OPENAI_API_KEY):
        return extract_relations_llm(text, entity_pairs, api_key=api_key or OPENAI_API_KEY or None)
    return extract_relations_fallback(entity_pairs)
