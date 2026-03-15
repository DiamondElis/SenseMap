"""
Hybrid router: select retriever stack by query type.
Choices: vector only, parent-child, or parent-child + graph expansion.
One single pattern is unlikely to serve every purpose; routing is modular and testable.
"""
from typing import Literal, Optional

from shared.python.models.retrieval import (
    EntityHit,
    RelationshipHit,
    RetrievalHit,
)
from shared.python.models.context import ContextBundle

from .basic_vector import retrieve as basic_vector_retrieve
from .parent_child import retrieve as parent_child_retrieve
from .graph_expand import expand as graph_expand


RouteKind = Literal["vector_only", "parent_child", "parent_child_expand"]


def _classify(query: str) -> RouteKind:
    """
    Simple query-based routing. Extend with NLU or agentic logic later.
    - Short or single-term -> vector_only (fast, precise).
    - Default -> parent_child (broader context).
    - Queries asking for relations/connections/context -> parent_child_expand.
    """
    q = (query or "").strip().lower()
    if not q:
        return "vector_only"
    # Heuristic: expansion keywords suggest user wants entity/relationship context
    expand_keywords = ("related", "relation", "relationship", "connection", "connect", "context", "around", "expand", "who", "what about")
    if any(w in q for w in expand_keywords):
        return "parent_child_expand"
    # Short query (e.g. one or two words) -> vector only for speed
    if len(q.split()) <= 2:
        return "vector_only"
    return "parent_child"


def retrieve(
    query: str,
    *,
    route: RouteKind | None = None,
    k: int = 8,
    k_children: int = 12,
    k_parents: int = 6,
    max_hops: int = 2,
    max_entities: int = 10,
    max_relationships: int = 20,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> ContextBundle:
    """
    Route the query to the appropriate retriever stack and return a ContextBundle.
    If route is None, it is chosen by _classify(query).
    """
    if route is None:
        route = _classify(query)

    chunk_hits: list[RetrievalHit] = []
    entity_hits: list[EntityHit] = []
    relationship_hits: list[RelationshipHit] = []

    if route == "vector_only":
        chunk_hits = basic_vector_retrieve(query, k=k, uri=uri, user=user, password=password)
        return ContextBundle(
            chunk_hits=chunk_hits,
            entity_hits=[],
            relationship_hits=[],
            evidence=[],
            prompt_sections={},
            debug={"route": "vector_only"},
        )

    if route == "parent_child":
        chunk_hits = parent_child_retrieve(
            query, k_children=k_children, k_parents=k_parents, uri=uri, user=user, password=password
        )
        return ContextBundle(
            chunk_hits=chunk_hits,
            entity_hits=[],
            relationship_hits=[],
            evidence=[],
            prompt_sections={},
            debug={"route": "parent_child"},
        )

    # parent_child_expand
    chunk_hits = parent_child_retrieve(
        query, k_children=k_children, k_parents=k_parents, uri=uri, user=user, password=password
    )
    entity_hits, relationship_hits, extra_chunks = graph_expand(
        chunk_hits,
        entity_hits=None,
        max_hops=max_hops,
        max_entities=max_entities,
        max_relationships=max_relationships,
        uri=uri,
        user=user,
        password=password,
    )
    # Optionally merge extra_chunks into chunk_hits (avoid duplicates)
    seen = {h.node_id for h in chunk_hits}
    for h in extra_chunks:
        if h.node_id not in seen:
            seen.add(h.node_id)
            chunk_hits.append(h)

    return ContextBundle(
        chunk_hits=chunk_hits,
        entity_hits=entity_hits,
        relationship_hits=relationship_hits,
        evidence=[],
        prompt_sections={},
        debug={"route": "parent_child_expand"},
    )
