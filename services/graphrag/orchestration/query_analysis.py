"""
Lightweight rule-based query classification for routing.
Outputs: query type (factual local, multi-hop/entity, broad summarization) and routing hints.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class RoutingHints:
    """Hints for the retriever pipeline selection."""

    enable_graph_expansion: bool = False
    parent_child_only: bool = False
    use_community: bool = False  # Stub for later community retrieval


@dataclass
class QueryAnalysis:
    """Result of query analysis: classification and routing hints."""

    query: str
    query_type: str  # "factual_local" | "multi_hop_entity" | "broad_summarization"
    routing_hints: RoutingHints = field(default_factory=RoutingHints)
    detected_entities: List[str] = field(default_factory=list)
    debug: dict = field(default_factory=dict)


# Keywords that suggest graph expansion (relationships, connections)
GRAPH_EXPANSION_KEYWORDS = (
    "relationship", "relationships", "related", "relation", "connect", "connected",
    "connection", "influence", "influences", "influenced", "which", "who worked",
    "worked on", "links", "linked", "between", "among",
)

# Phrases that suggest "which X worked on Y" style
MULTI_HOP_PHRASES = ("which ", "who ", "what ", "how does ", "how do ", "influence", "related to")

# Keywords that suggest broad / corpus-wide / summarization
BROAD_KEYWORDS = (
    "summarize", "summary", "overview", "all ", "entire", "corpus", "whole",
    "across the", "throughout", "generally", "in general", "broad",
)


def analyze_query(query: str) -> QueryAnalysis:
    """
    Rule-based query classification. Deterministic and easy to inspect.
    - factual_local: narrow fact lookup → parent-child only
    - multi_hop_entity: relationships, connections, "which X worked on Y" → enable graph expansion
    - broad_summarization: summarization / corpus-wide → stub community path for later
    """
    q = (query or "").strip()
    q_lower = q.lower()
    tokens = q_lower.split()
    debug: dict = {"matched": []}

    # 1) Broad / summarization
    if any(w in q_lower for w in BROAD_KEYWORDS):
        debug["matched"].append("broad_keyword")
        return QueryAnalysis(
            query=q,
            query_type="broad_summarization",
            routing_hints=RoutingHints(enable_graph_expansion=False, parent_child_only=False, use_community=True),
            debug=debug,
        )

    # 2) Multi-hop / entity / relationship
    if any(kw in q_lower for kw in GRAPH_EXPANSION_KEYWORDS):
        debug["matched"].append("graph_expansion_keyword")
        return QueryAnalysis(
            query=q,
            query_type="multi_hop_entity",
            routing_hints=RoutingHints(enable_graph_expansion=True, parent_child_only=False, use_community=False),
            debug=debug,
        )
    if any(phrase in q_lower for phrase in MULTI_HOP_PHRASES) and len(tokens) >= 4:
        debug["matched"].append("multi_hop_phrase")
        return QueryAnalysis(
            query=q,
            query_type="multi_hop_entity",
            routing_hints=RoutingHints(enable_graph_expansion=True, parent_child_only=False, use_community=False),
            debug=debug,
        )

    # 3) Factual local (narrow): short or specific fact
    if len(tokens) <= 4 or not any(kw in q_lower for kw in ("relationship", "related", "connection", "influence")):
        debug["matched"].append("factual_local")
        return QueryAnalysis(
            query=q,
            query_type="factual_local",
            routing_hints=RoutingHints(enable_graph_expansion=False, parent_child_only=True, use_community=False),
            debug=debug,
        )

    # Default: treat as factual local, parent-child only
    debug["matched"].append("default_factual")
    return QueryAnalysis(
        query=q,
        query_type="factual_local",
        routing_hints=RoutingHints(enable_graph_expansion=False, parent_child_only=True, use_community=False),
        debug=debug,
    )
