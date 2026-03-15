"""
End-to-end answer pipeline: analyze query → route → retrieve → dedupe → rerank → budget → assemble → LLM.
Returns answer text plus structured provenance and debug context.
"""
from typing import Any, Callable, Optional

from shared.python.models.context import ContextBundle

from services.graphrag.retrievers.hybrid_router import retrieve as hybrid_retrieve
from services.graphrag.context_builders import (
    dedupe_bundle,
    rerank_bundle,
    apply_budget,
    assemble,
    BudgetConfig,
)
from .query_analysis import analyze_query
from .route import select_retriever_stack, route_for_debug


def _default_llm(prompt_context: str, query: str, system_prompt: Optional[str] = None) -> str:
    """Call OpenAI chat completion when OPENAI_API_KEY is set; otherwise return placeholder."""
    from shared.python.config import settings
    if not settings.OPENAI_API_KEY:
        return f"[Placeholder] Answer for: “{query}”. Set OPENAI_API_KEY for real answers."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        sys = system_prompt or "Answer using only the provided context. If the context does not contain the answer, say so."
        resp = client.chat.completions.create(
            model=getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": f"{prompt_context}\n\nQuestion: {query}"},
            ],
            max_tokens=500,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[LLM error: {e}]"


def run_answer_pipeline(
    query: str,
    *,
    llm_fn: Optional[Callable[[str, str], str]] = None,
    system_prompt: Optional[str] = None,
    budget_config: Optional[BudgetConfig] = None,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
) -> dict[str, Any]:
    """
    One function to drive end-to-end answer generation from question to final response payload.
    Steps: analyze query → route → retrieve → dedupe → rerank → budget → assemble → LLM.
    Returns dict with: answer, provenance, debug.
    """
    query = (query or "").strip()
    if not query:
        return {
            "answer": "",
            "provenance": {"context_used": False, "sources": [], "route": None},
            "debug": {"error": "empty query"},
        }

    # 1) Analyze and route
    analysis = analyze_query(query)
    route_choice = select_retriever_stack(analysis)
    route_debug = route_for_debug(analysis)

    # 2) Retrieve
    bundle = hybrid_retrieve(
        query,
        route=route_choice,
        k=8,
        k_children=12,
        k_parents=6,
        max_hops=2,
        max_entities=10,
        max_relationships=20,
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
    )
    bundle.debug["analysis"] = {
        "query_type": analysis.query_type,
        "routing_hints": {
            "enable_graph_expansion": analysis.routing_hints.enable_graph_expansion,
            "parent_child_only": analysis.routing_hints.parent_child_only,
            "use_community": analysis.routing_hints.use_community,
        },
        "matched": analysis.debug.get("matched", []),
    }
    bundle.debug["route"] = route_debug

    # 3) Dedupe
    bundle = dedupe_bundle(bundle)

    # 4) Rerank
    bundle = rerank_bundle(bundle)

    # 5) Budget
    cfg = budget_config or BudgetConfig()
    bundle = apply_budget(bundle, config=cfg)
    bundle.debug.setdefault("token_budget", {})

    # 6) Assemble
    prompt_text, debug_context_object = assemble(bundle)
    bundle.debug["context_object"] = debug_context_object

    # 7) LLM
    llm = llm_fn or (lambda ctx, q: _default_llm(ctx, q, system_prompt))
    answer_text = llm(prompt_text, query)

    # 8) Provenance
    sources = []
    for h in bundle.chunk_hits:
        sources.append({
            "node_id": h.node_id,
            "node_label": h.node_label,
            "score": h.score,
            "text_preview": (h.text or "")[:200],
        })
    provenance = {
        "context_used": True,
        "sources": sources,
        "route": route_choice,
        "chunk_count": len(bundle.chunk_hits),
        "entity_count": len(bundle.entity_hits),
        "relationship_count": len(bundle.relationship_hits),
        "sections": list(debug_context_object.get("sections", {}).keys()),
    }

    return {
        "answer": answer_text,
        "provenance": provenance,
        "debug": {
            "analysis": bundle.debug.get("analysis"),
            "route": bundle.debug.get("route"),
            "token_budget": bundle.debug.get("token_budget"),
            "context_object": debug_context_object,
        },
    }
