"""
Three-stage entity resolution: exact -> fuzzy -> embedding. Never auto-merge on type conflict, short ambiguous names, or marginal similarity.
"""

from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .canonicalize import canonicalize_name, glossary_canonical_name
from .fuzzy_match import fuzzy_match_entity
from .embedding_match import embedding_match_entity, EMBEDDING_MARGINAL, EMBEDDING_STRONG, SHORT_NAME_MAX_LENGTH


class ResolutionResult(BaseModel):
    """Result of resolving a candidate entity against existing entities and glossary."""

    action: Literal["exact_match", "fuzzy_match", "embedding_match", "create_new", "review"]
    entity_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    candidates: list[dict] = Field(default_factory=list)


def _candidate_name(candidate: dict) -> str:
    return (candidate.get("canonical_candidate") or candidate.get("name") or "").strip()


def _candidate_type(candidate: dict) -> str:
    return (candidate.get("type") or "").strip()


def _existing_by_canonical(existing_entities: list[dict]) -> dict[str, dict]:
    """Map canonical name -> first entity with that name (id, name, type)."""
    out: dict[str, dict] = {}
    for e in existing_entities:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or e.get("canonical_name") or "").strip()
        eid = e.get("id")
        if name is None or eid is None:
            continue
        key = canonicalize_name(name)
        if key and key not in out:
            out[key] = {"entity_id": str(eid), "name": name, "type": (e.get("type") or "").strip()}
    return out


def resolve_entity(
    candidate: dict,
    existing_entities: list[dict],
    glossary: dict,
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    allow_self_merge: bool = False,
) -> ResolutionResult:
    """
    Three-stage resolution:
    1. Exact normalized match (after glossary canonicalization).
    2. Fuzzy match (single high-confidence, type agreement).
    3. Embedding similarity with type agreement (strong threshold only for auto-merge; marginal -> review).

    Never auto-merge if: types conflict, name is short and ambiguous, cosine similarity is marginal.
    In uncertain cases returns action="review" with candidates.
    """
    name = _candidate_name(candidate)
    cand_type = _candidate_type(candidate)
    if not name:
        return ResolutionResult(action="create_new", entity_id=None, confidence=0.0, candidates=[])

    # Glossary-driven canonicalization for exact match
    canonical_from_glossary = glossary_canonical_name(name, glossary)
    if canonical_from_glossary:
        name_for_exact = canonicalize_name(canonical_from_glossary)
    else:
        name_for_exact = canonicalize_name(name)

    by_canonical = _existing_by_canonical(existing_entities)
    if name_for_exact and name_for_exact in by_canonical:
        existing = by_canonical[name_for_exact]
        if allow_self_merge or _type_agrees(cand_type, existing["type"]):
            return ResolutionResult(
                action="exact_match",
                entity_id=existing["entity_id"],
                confidence=1.0,
                candidates=[existing],
            )
        return ResolutionResult(
            action="review",
            entity_id=None,
            confidence=0.0,
            candidates=[existing],
        )

    # Rule 2: Fuzzy match
    fuzzy = fuzzy_match_entity(candidate, existing_entities, threshold=0.85, top_k=3)
    if fuzzy:
        best = fuzzy[0]
        if best["score"] >= 0.9 and len(fuzzy) == 1 and _type_agrees(cand_type, best["type"]):
            return ResolutionResult(
                action="fuzzy_match",
                entity_id=best["entity_id"],
                confidence=best["score"],
                candidates=fuzzy,
            )
        if best["score"] >= 0.85:
            return ResolutionResult(action="review", entity_id=None, confidence=best["score"], candidates=fuzzy)

    # Rule 3: Embedding with type agreement
    emb_matches = embedding_match_entity(
        candidate,
        existing_entities,
        embed_fn=embed_fn,
        strong_threshold=EMBEDDING_STRONG,
        marginal_threshold=EMBEDDING_MARGINAL,
        short_name_max_length=SHORT_NAME_MAX_LENGTH,
        top_k=3,
    )
    if emb_matches:
        best = emb_matches[0]
        sim = best["similarity"]
        is_marginal = best.get("is_marginal", EMBEDDING_MARGINAL <= sim < EMBEDDING_STRONG)
        is_short = best.get("is_short_name", len(name) <= SHORT_NAME_MAX_LENGTH)
        if sim >= EMBEDDING_STRONG and not is_short and not is_marginal:
            return ResolutionResult(
                action="embedding_match",
                entity_id=best["entity_id"],
                confidence=sim,
                candidates=emb_matches,
            )
        return ResolutionResult(
            action="review",
            entity_id=None,
            confidence=sim,
            candidates=emb_matches,
        )

    return ResolutionResult(action="create_new", entity_id=None, confidence=0.0, candidates=[])


def _type_agrees(a: str, b: str) -> bool:
    if not a or not b:
        return True
    return a.strip().lower() == b.strip().lower()
