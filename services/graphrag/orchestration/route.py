"""
Choose retriever pipeline from query analysis.
Options: vector only, parent-child, parent-child + graph expansion, community (stub).
Routing behavior is deterministic and debuggable.
"""
from typing import Literal

from .query_analysis import QueryAnalysis, RoutingHints

RouteChoice = Literal["vector_only", "parent_child", "parent_child_expand", "community"]


def select_retriever_stack(analysis: QueryAnalysis) -> RouteChoice:
    """
    Map query analysis to retriever stack choice.
    - factual_local + parent_child_only → parent_child (or vector_only for very short)
    - multi_hop_entity + enable_graph_expansion → parent_child_expand
    - broad_summarization + use_community → community (stub; fallback to parent_child for now)
    - else parent_child
    """
    hints: RoutingHints = analysis.routing_hints
    q = (analysis.query or "").strip()
    tokens = q.split()

    if hints.use_community and analysis.query_type == "broad_summarization":
        # Stub: community path not implemented yet; fall back to parent_child
        return "parent_child"

    if hints.enable_graph_expansion:
        return "parent_child_expand"

    if hints.parent_child_only:
        # Very short factual query → vector only for speed
        if len(tokens) <= 2:
            return "vector_only"
        return "parent_child"

    # Default
    return "parent_child"


def route_for_debug(analysis: QueryAnalysis) -> dict:
    """Return a small dict describing the routing decision for debug/provenance."""
    choice = select_retriever_stack(analysis)
    return {
        "query_type": analysis.query_type,
        "enable_graph_expansion": analysis.routing_hints.enable_graph_expansion,
        "parent_child_only": analysis.routing_hints.parent_child_only,
        "use_community": analysis.routing_hints.use_community,
        "retriever_stack": choice,
    }
