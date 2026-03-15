"""
Token budgeting for Step 4 context: estimate token usage and enforce caps.
Trim order: low-score relationships → low-score entities → extra parent chunks → optional neighboring chunks.
Deterministic; debug output includes token estimates and trim counts.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit


# Suggested defaults
DEFAULT_MAX_PARENTS = 6
DEFAULT_MAX_ENTITY_EXPANSIONS = 8
DEFAULT_MAX_RELATIONSHIP_LINES = 12
DEFAULT_MAX_TOTAL_TOKENS = 3500


def _default_estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token. No external tokenizer required."""
    if not text or not isinstance(text, str):
        return 0
    return max(1, (len(text.strip()) + 3) // 4)


@dataclass
class BudgetConfig:
    """Configurable limits for context budgeting."""

    max_parents: int = DEFAULT_MAX_PARENTS
    max_entity_expansions: int = DEFAULT_MAX_ENTITY_EXPANSIONS
    max_relationship_lines: int = DEFAULT_MAX_RELATIONSHIP_LINES
    max_total_tokens: int = DEFAULT_MAX_TOTAL_TOKENS
    estimate_fn: Callable[[str], int] = field(default_factory=lambda: _default_estimate_tokens)


def estimate_chunk_tokens(hit: RetrievalHit, estimate_fn: Callable[[str], int]) -> int:
    """Tokens for one chunk/parent block (text + small overhead)."""
    overhead = 10  # "Chunk(id): " etc.
    return estimate_fn(hit.text) + overhead


def estimate_entity_tokens(hit: EntityHit, estimate_fn: Callable[[str], int]) -> int:
    """Tokens for one entity expansion line."""
    s = f"{hit.canonical_name} ({hit.entity_type})"
    return estimate_fn(s) + 5


def estimate_relationship_tokens(hit: RelationshipHit, estimate_fn: Callable[[str], int]) -> int:
    """Tokens for one relationship line."""
    s = f"{hit.source_name} --{hit.rel_type}--> {hit.target_name}"
    return estimate_fn(s) + 5


def apply_budget(
    bundle: ContextBundle,
    config: Optional[BudgetConfig] = None,
    *,
    max_parents: Optional[int] = None,
    max_entity_expansions: Optional[int] = None,
    max_relationship_lines: Optional[int] = None,
    max_total_tokens: Optional[int] = None,
) -> ContextBundle:
    """
    Enforce caps and trim low-value context. Trim order:
    1. Low-score relationships (keep top max_relationship_lines)
    2. Low-score entities (keep top max_entity_expansions)
    3. Extra parent chunks beyond max_parents
    4. Neighboring chunks (Chunk hits that are not ParentChunk)
    If still over max_total_tokens, trim further in the same order until under cap.
    Returns new bundle with debug.token_budget set (estimates, trimmed counts, final counts).
    """
    cfg = config or BudgetConfig()
    if max_parents is not None:
        cfg = BudgetConfig(max_parents=max_parents, max_entity_expansions=cfg.max_entity_expansions, max_relationship_lines=cfg.max_relationship_lines, max_total_tokens=cfg.max_total_tokens, estimate_fn=cfg.estimate_fn)
    if max_entity_expansions is not None:
        cfg = BudgetConfig(max_parents=cfg.max_parents, max_entity_expansions=max_entity_expansions, max_relationship_lines=cfg.max_relationship_lines, max_total_tokens=cfg.max_total_tokens, estimate_fn=cfg.estimate_fn)
    if max_relationship_lines is not None:
        cfg = BudgetConfig(max_parents=cfg.max_parents, max_entity_expansions=cfg.max_entity_expansions, max_relationship_lines=max_relationship_lines, max_total_tokens=cfg.max_total_tokens, estimate_fn=cfg.estimate_fn)
    if max_total_tokens is not None:
        cfg = BudgetConfig(max_parents=cfg.max_parents, max_entity_expansions=cfg.max_entity_expansions, max_relationship_lines=cfg.max_relationship_lines, max_total_tokens=max_total_tokens, estimate_fn=cfg.estimate_fn)

    est = cfg.estimate_fn
    debug: dict = dict(bundle.debug)

    # 1) Relationships: sort by score desc, cap
    rel_sorted = sorted(bundle.relationship_hits, key=lambda r: -r.score)
    rel_trimmed = rel_sorted[cfg.max_relationship_lines:]
    rel_kept = rel_sorted[: cfg.max_relationship_lines]
    debug["relationship_trimmed"] = len(rel_trimmed)
    debug["relationship_kept"] = len(rel_kept)

    # 2) Entities: sort by score desc, cap
    ent_sorted = sorted(bundle.entity_hits, key=lambda e: -e.score)
    ent_trimmed = ent_sorted[cfg.max_entity_expansions:]
    ent_kept = ent_sorted[: cfg.max_entity_expansions]
    debug["entity_trimmed"] = len(ent_trimmed)
    debug["entity_kept"] = len(ent_kept)

    # 3) Chunk hits: split parent vs neighboring
    parent_hits = [h for h in bundle.chunk_hits if h.node_label == "ParentChunk"]
    neighbor_hits = [h for h in bundle.chunk_hits if h.node_label != "ParentChunk"]
    parent_sorted = sorted(parent_hits, key=lambda h: -h.score)
    parent_trimmed = parent_sorted[cfg.max_parents:]
    parent_kept = parent_sorted[: cfg.max_parents]
    debug["parent_trimmed"] = len(parent_trimmed)
    debug["parent_kept"] = len(parent_kept)

    # 4) Neighboring chunks: keep all for now; we'll trim by total tokens next
    neighbor_sorted = sorted(neighbor_hits, key=lambda h: -h.score)
    chunk_kept = list(parent_kept) + list(neighbor_sorted)

    def total_tokens(chunks: list[RetrievalHit], entities: list[EntityHit], relationships: list[RelationshipHit]) -> int:
        return (
            sum(estimate_chunk_tokens(h, est) for h in chunks)
            + sum(estimate_entity_tokens(h, est) for h in entities)
            + sum(estimate_relationship_tokens(h, est) for h in relationships)
        )

    # 5) If over max_total_tokens, trim in order: drop low-score neighbors, then relationships, entities, parents
    entities_final = list(ent_kept)
    relationships_final = list(rel_kept)
    neighbor_keep_count = len(neighbor_sorted)
    chunks_final = list(parent_kept) + neighbor_sorted[:neighbor_keep_count]
    current = total_tokens(chunks_final, entities_final, relationships_final)
    debug["token_estimate_initial"] = current
    neighbor_dropped = 0

    while current > cfg.max_total_tokens:
        trimmed = False
        if neighbor_keep_count > 0:
            neighbor_keep_count -= 1
            neighbor_dropped += 1
            trimmed = True
        elif len(relationships_final) > 0:
            relationships_final = relationships_final[:-1]
            trimmed = True
        elif len(entities_final) > 0:
            entities_final = entities_final[:-1]
            trimmed = True
        elif len(parent_kept) > 0:
            parent_kept = parent_kept[:-1]
            trimmed = True
        if not trimmed:
            break
        chunks_final = list(parent_kept) + neighbor_sorted[:neighbor_keep_count]
        current = total_tokens(chunks_final, entities_final, relationships_final)

    debug["neighbor_chunks_dropped_for_budget"] = neighbor_dropped
    debug["token_estimate_final"] = current
    debug["token_budget"] = {
        "chunk_tokens": sum(estimate_chunk_tokens(h, est) for h in chunks_final),
        "entity_tokens": sum(estimate_entity_tokens(h, est) for h in entities_final),
        "relationship_tokens": sum(estimate_relationship_tokens(h, est) for h in relationships_final),
        "total_tokens": current,
        "max_total_tokens": cfg.max_total_tokens,
        "final_chunk_count": len(chunks_final),
        "final_entity_count": len(entities_final),
        "final_relationship_count": len(relationships_final),
    }

    return ContextBundle(
        chunk_hits=chunks_final,
        entity_hits=entities_final,
        relationship_hits=relationships_final,
        evidence=bundle.evidence,
        prompt_sections=bundle.prompt_sections,
        debug=debug,
    )
