# Retrieval API (baseline GraphRAG)

Baseline retrieval before entity extraction: basic vector → parent-child → NEXT_CHUNK expansion.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/retrieve/basic` | Vector similarity search on `Chunk.embedding`. |
| POST | `/retrieve/parent-child` | Vector search on child chunks; return parent chunks (text + score). GraphRAG pattern: child embeddings, return parents. |
| POST | `/retrieve/expand` | Expand from chunk ids along `NEXT_CHUNK` to get adjacent chunks. |
| POST | `/answer` | Retrieve context (parent-child by default), then answer via LLM or placeholder. |
| GET | `/graph/subgraph` | Nodes and edges for visualization. Query: `chunk_ids=id1,id2` and optional `expand_depth=1`. |

## Request/response examples

**POST /retrieve/basic**, **/retrieve/parent-child**

```json
{ "query": "What is the main topic?", "top_k": 5 }
```

Response: `[{ "id", "text", "score", "metadata" }, ...]`

**POST /answer**

```json
{ "query": "Summarize the document.", "top_k": 5, "use_parent_child": true }
```

Response: `{ "answer", "sources", "context_used" }`. Set `OPENAI_API_KEY` for real LLM answers.

**GET /graph/subgraph**

```
GET /graph/subgraph?chunk_ids=doc1_p0_c0,doc1_p0_c1&expand_depth=1
```

Response: `{ "nodes": [{ "id", "text" }], "edges": [{ "source", "target", "type" }] }`.

## Schema

- **Basic**: uses vector index `chunk_embedding` (1536 dims, cosine) on `Chunk`.
- **Parent-child**: `(child:Chunk)-[:PART_OF]->(parent:Chunk)`; equivalent to `(node)<-[:HAS_CHILD]-(parent)` in GraphRAG material.
- **Expand**: `(Chunk)-[:NEXT_CHUNK]-(Chunk)` for adjacency.

Run the PDF ingestion pipeline so the lexical graph is populated before calling these endpoints.
