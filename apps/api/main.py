"""
SenseMap retrieval API: basic vector, parent-child, NEXT_CHUNK expansion, answer, subgraph.
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
)

app = FastAPI(title="SenseMap API", version="0.1.0")


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


class AnswerRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    use_parent_child: bool = True


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
def answer(body: AnswerRequest) -> dict[str, Any]:
    """
    Retrieve context (parent-child by default), then produce an answer.
    Without OPENAI_API_KEY returns a placeholder answer with retrieved context.
    """
    embedding = embed_query(body.query, model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
    if body.use_parent_child:
        chunks = parent_child_retrieve(embedding, top_k=body.top_k)
    else:
        chunks = basic_vector_retrieve(embedding, top_k=body.top_k)
    context = "\n\n".join(c["text"] for c in chunks if c.get("text"))
    if not context:
        return {"answer": "No relevant context found.", "sources": [], "context_used": False}
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Answer using only the provided context. If the context does not contain the answer, say so."},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {body.query}"},
                ],
                max_tokens=500,
            )
            answer_text = resp.choices[0].message.content or ""
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")
    else:
        answer_text = f"[Placeholder] Answer for: “{body.query}”. Use POST /retrieve/parent-child for context; set OPENAI_API_KEY for real answers."
    query_id = generate_query_id()
    store_query_trace(query_id, [c["id"] for c in chunks])
    return {
        "answer": answer_text,
        "query_id": query_id,
        "sources": [{"id": c["id"], "score": c.get("score"), "text_preview": (c.get("text") or "")[:200]} for c in chunks],
        "context_used": True,
    }


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
