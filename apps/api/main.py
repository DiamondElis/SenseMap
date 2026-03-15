"""
SenseMap retrieval API: basic vector, parent-child, NEXT_CHUNK expansion, answer, subgraph.
Step 4: POST /answer wires the GraphRAG answer pipeline (analyze → route → retrieve → dedupe → rerank → budget → assemble → LLM).
"""
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from config import OPENAI_API_KEY, EMBEDDING_MODEL
from embeddings import embed_query
from retrieval import (
    basic_vector_retrieve,
    parent_child_retrieve,
    expand_adjacency,
    get_subgraph,
)
from graph_serving import (
    get_neighborhood,
    get_community,
    get_query_trace_ids,
    store_query_trace,
    generate_query_id,
    list_lexical_documents,
    get_lexical_document,
    get_lexical_preview,
    get_graph_entities,
    get_entity_neighborhood,
    get_hybrid_document,
)

app = FastAPI(title="SenseMap API", version="0.1.0")


# ---- Step 4 answer pipeline response shaping ----

def _route_to_external_name(route: str) -> str:
    """Map internal route choice to stable external name for graph viewer and tooling."""
    return {
        "vector_only": "vector_only",
        "parent_child": "parent_child",
        "parent_child_expand": "parent_child_plus_graph_expand",
        "community": "community",
    }.get(route, route)


def _build_answer_response(pipeline_result: dict[str, Any], include_debug: bool) -> dict[str, Any]:
    """Shape pipeline output into the external deliverable: provenance (documents, parent_chunks, chunks, entities, relationships), graph_trace, debug."""
    ctx = pipeline_result.get("debug", {}).get("context_object") or {}
    sections = ctx.get("sections", {})
    citation_map = ctx.get("citation_map", {})

    chunk_entries = (sections.get("[Chunk Context]", {}) or {}).get("entries", [])
    entity_entries = (sections.get("[Entity Context]", {}) or {}).get("entries", [])
    rel_entries = (sections.get("[Relationship Context]", {}) or {}).get("entries", [])

    # Provenance: documents (unique by document_id / document_title)
    doc_set = set()
    documents = []
    for e in chunk_entries:
        doc_id = e.get("document_title") or e.get("parent_chunk_id") or e.get("node_id")
        key = (doc_id, e.get("document_title"))
        if key not in doc_set:
            doc_set.add(key)
            documents.append({"document_id": doc_id, "document_title": e.get("document_title") or str(doc_id)})

    # parent_chunks
    parent_set = set()
    parent_chunks = []
    for e in chunk_entries:
        pid = e.get("parent_chunk_id") or e.get("node_id")
        if pid not in parent_set:
            parent_set.add(pid)
            parent_chunks.append({
                "parent_chunk_id": pid,
                "document_id": e.get("document_title") or e.get("document_id"),
            })

    # chunks
    chunks = [
        {
            "chunk_id": e.get("chunk_id") or e.get("node_id"),
            "node_id": e.get("node_id"),
            "text_preview": (e.get("text") or "")[:300],
            "score": e.get("score"),
            "document_title": e.get("document_title"),
            "parent_chunk_id": e.get("parent_chunk_id"),
        }
        for e in chunk_entries
    ]

    # entities
    entities = [
        {
            "entity_id": e.get("entity_id"),
            "canonical_name": e.get("canonical_name"),
            "entity_type": e.get("entity_type"),
            "score": e.get("score"),
        }
        for e in entity_entries
    ]

    # relationships
    relationships = [
        {
            "source_id": e.get("source_id"),
            "target_id": e.get("target_id"),
            "source_name": e.get("source_name"),
            "target_name": e.get("target_name"),
            "rel_type": e.get("rel_type"),
            "score": e.get("score"),
            "source_chunk_ids": e.get("source_chunk_ids", []),
        }
        for e in rel_entries
    ]

    # graph_trace: nodes and edges for UI highlighting
    nodes = []
    for e in chunk_entries:
        nodes.append({
            "id": e.get("node_id") or e.get("chunk_id"),
            "label": e.get("node_label", "Chunk"),
            "text": (e.get("text") or "")[:500],
            "type": e.get("node_label", "Chunk"),
        })
    for e in entity_entries:
        nodes.append({
            "id": e.get("entity_id"),
            "label": "Entity",
            "text": e.get("canonical_name") or "",
            "type": e.get("entity_type") or "",
        })
    edges = []
    for e in rel_entries:
        src = e.get("source_id") or e.get("source_name")
        tgt = e.get("target_id") or e.get("target_name")
        if src and tgt:
            edges.append({"source": str(src), "target": str(tgt), "type": e.get("rel_type", "RELATES_TO")})

    provenance = {
        "documents": documents,
        "parent_chunks": parent_chunks,
        "chunks": chunks,
        "entities": entities,
        "relationships": relationships,
    }

    response = {
        "answer": pipeline_result.get("answer", ""),
        "provenance": provenance,
        "graph_trace": {"nodes": nodes, "edges": edges},
    }
    if include_debug:
        response["debug"] = {
            "route": _route_to_external_name(pipeline_result.get("provenance", {}).get("route", "")),
            "token_budget": pipeline_result.get("debug", {}).get("token_budget"),
            "analysis": pipeline_result.get("debug", {}).get("analysis"),
        }
    return response


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


class AnswerRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    use_parent_child: bool = True


class AnswerRequestV2(BaseModel):
    """Step 4 answer: question + optional budget and debug."""
    question: str = Field(..., min_length=1, description="User question")
    max_context_tokens: int = Field(3500, ge=100, le=16000, description="Max context tokens for budgeting")
    debug: bool = Field(True, description="Include debug (route, token_budget) in response")


class ExpandRequest(BaseModel):
    chunk_ids: list[str] = Field(..., min_length=1)
    depth: int = Field(1, ge=0, le=3)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/retrieve/basic")
def retrieve_basic(body: RetrieveRequest) -> list[dict[str, Any]]:
    """Basic vector retriever on chunks (embedding similarity)."""
    embedding = embed_query(body.query, model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
    return basic_vector_retrieve(embedding, top_k=body.top_k)


@app.post("/retrieve/parent-child")
def retrieve_parent_child(body: RetrieveRequest) -> list[dict[str, Any]]:
    """
    Parent-child retriever: vector search on child chunks, return parent chunks with score.
    Matches GraphRAG pattern: (node)<-[:HAS_CHILD]-(parent) → we use (child)-[:PART_OF]->(parent:Chunk).
    """
    embedding = embed_query(body.query, model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
    return parent_child_retrieve(embedding, top_k=body.top_k)


@app.post("/answer")
def answer(body: AnswerRequestV2) -> dict[str, Any]:
    """
    Step 4 answer pipeline: analyze question → route → retrieve → dedupe → rerank → budget → assemble → LLM.
    Returns answer, provenance (documents, parent_chunks, chunks, entities, relationships), graph_trace (nodes, edges), and optional debug.
    """
    try:
        from services.graphrag.context_builders import BudgetConfig
        from services.graphrag.orchestration.answer_pipeline import run_answer_pipeline
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Answer pipeline not available: {e}")

    budget_config = BudgetConfig(max_total_tokens=body.max_context_tokens)
    result = run_answer_pipeline(body.question, budget_config=budget_config)
    return _build_answer_response(result, include_debug=body.debug)


@app.get("/graph/documents")
def graph_documents() -> list[dict[str, Any]]:
    """List Document nodes (id, title, source_type) for loading a lexical graph."""
    return list_lexical_documents()


@app.get("/graph/document/{document_id}")
def graph_document(document_id: str) -> dict[str, Any]:
    """
    Return full lexical graph for one document: Document, ParentChunk, Chunk, IngestionRun
    and edges HAS_PARENT, HAS_CHILD, NEXT_CHUNK, INGESTED_IN.
    """
    return get_lexical_document(document_id)


@app.get("/graph/lexical-preview")
def graph_lexical_preview(document_id: str = Query(..., alias="document_id")) -> dict[str, Any]:
    """Return lexical graph for one document (same as GET /graph/document/{document_id})."""
    return get_lexical_preview(document_id)


@app.get("/graph/subgraph")
def graph_subgraph(chunk_ids: str, expand_depth: int = 1) -> dict[str, Any]:
    """
    Return subgraph for visualization: nodes and edges for the given chunk ids
    plus NEXT_CHUNK and PART_OF neighborhood.
    Query params: chunk_ids=id1,id2,... and optional expand_depth (default 1).
    """
    ids = [x.strip() for x in chunk_ids.split(",") if x.strip()]
    if not ids:
        return {"nodes": [], "edges": []}
    return get_subgraph(ids, expand_depth=expand_depth)


@app.get("/graph/entities")
def graph_entities(chunk_id: str = Query(..., alias="chunk_id")) -> dict[str, Any]:
    """Return Chunk, EntityMention, Entity and edges MENTIONS, REFERS_TO, HAS_ENTITY for one chunk. Query param: chunk_id."""
    return get_graph_entities(chunk_id)


@app.get("/graph/entity-neighborhood")
def graph_entity_neighborhood(
    entity_id: str = Query(..., alias="id"),
    hops: int = Query(2, ge=0, le=5),
) -> dict[str, Any]:
    """Expand from an entity (or any node) by N hops. Query params: id, hops (default 2)."""
    return get_entity_neighborhood(entity_id, hops=hops)


@app.get("/graph/hybrid-document")
def graph_hybrid_document(document_id: str = Query(..., alias="document_id")) -> dict[str, Any]:
    """Return combined lexical + entity graph for one document (chunk→mention→entity paths and RELATES_TO). Query param: document_id."""
    return get_hybrid_document(document_id)


@app.get("/graph/neighborhood")
def graph_neighborhood(
    node_id: str = Query(..., alias="id"),
    hops: int = Query(2, ge=0, le=5),
) -> dict[str, Any]:
    """Expand from node id by N hops; return nodes and edges for visualization. Query params: id, hops (default 2)."""
    return get_neighborhood(node_id, hops=hops)


@app.get("/graph/community/{community_id}")
def graph_community(community_id: str) -> dict[str, Any]:
    """Return all nodes with communityId = community_id and edges between them."""
    return get_community(community_id)


@app.get("/graph/query-trace/{query_id}")
def graph_query_trace(query_id: str, expand_depth: int = 1) -> dict[str, Any]:
    """Return subgraph for the stored query trace (chunk/node ids from a prior /answer or retrieval)."""
    ids = get_query_trace_ids(query_id)
    if not ids:
        return {"nodes": [], "edges": [], "query_id": query_id}
    data = get_subgraph(ids, expand_depth=expand_depth)
    data["query_id"] = query_id
    return data


# Optional: adjacency expansion as POST for many ids
@app.post("/retrieve/expand")
def retrieve_expand(body: ExpandRequest) -> list[dict[str, Any]]:
    """Expand from chunk ids along NEXT_CHUNK to get adjacent chunks."""
    return expand_adjacency(body.chunk_ids, depth=body.depth)
