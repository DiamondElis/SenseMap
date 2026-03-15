"""
Embedding similarity match with type agreement. Marginal similarity or short names -> review, not auto-merge.
"""

from typing import Any, Callable

# Thresholds: above STRONG can auto-merge (with type agreement); between MARGINAL and STRONG -> review
EMBEDDING_STRONG = 0.9
EMBEDDING_MARGINAL = 0.7
SHORT_NAME_MAX_LENGTH = 4


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(obj: dict) -> list[float] | None:
    emb = obj.get("embedding")
    if emb is None or not isinstance(emb, list):
        return None
    if not all(isinstance(x, (int, float)) for x in emb):
        return None
    return [float(x) for x in emb]


def _type_agrees(cand_type: str, existing_type: str) -> bool:
    if not cand_type or not existing_type:
        return True
    return cand_type.strip().lower() == existing_type.strip().lower()


def embedding_match_entity(
    candidate: dict,
    existing_entities: list[dict],
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    strong_threshold: float = EMBEDDING_STRONG,
    marginal_threshold: float = EMBEDDING_MARGINAL,
    short_name_max_length: int = SHORT_NAME_MAX_LENGTH,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Return list of existing entities with embedding similarity and type agreement.
    Each item: {entity_id, name, type, similarity, is_marginal, is_short_name}.
    - is_marginal: similarity in [marginal_threshold, strong_threshold) -> do not auto-merge, use review.
    - is_short_name: candidate name length <= short_name_max_length -> ambiguous, prefer review.
    Only includes entities with type agreement and similarity >= marginal_threshold.
    If candidate has no embedding and embed_fn is None, returns [].
    """
    cand_name = (candidate.get("canonical_candidate") or candidate.get("name") or "").strip()
    cand_type = (candidate.get("type") or "").strip()
    cand_emb = _get_embedding(candidate)
    if cand_emb is None and embed_fn:
        try:
            vecs = embed_fn([cand_name or " "])
            if vecs and len(vecs) > 0 and vecs[0]:
                cand_emb = vecs[0]
        except Exception:
            pass
    if cand_emb is None:
        return []

    is_short = len(cand_name) <= short_name_max_length
    results: list[dict[str, Any]] = []
    for e in existing_entities:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        ename = (e.get("name") or e.get("canonical_name") or "").strip()
        etype = (e.get("type") or "").strip()
        if eid is None or not ename:
            continue
        if not _type_agrees(cand_type, etype):
            continue
        e_emb = _get_embedding(e)
        if e_emb is None and embed_fn:
            try:
                vecs = embed_fn([ename])
                if vecs and len(vecs) > 0 and vecs[0]:
                    e_emb = vecs[0]
            except Exception:
                continue
        if e_emb is None:
            continue
        sim = _cosine_similarity(cand_emb, e_emb)
        if sim < marginal_threshold:
            continue
        results.append({
            "entity_id": str(eid),
            "name": ename,
            "type": etype,
            "similarity": round(sim, 4),
            "is_marginal": marginal_threshold <= sim < strong_threshold,
            "is_short_name": is_short,
        })
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]
