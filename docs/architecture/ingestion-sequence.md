# Ingestion and graph build sequence

Order supported by the codebase and GraphRAG pattern docs:

1. **Lexical graph first** — PDF/document ingestion → chunking → embeddings → Neo4j (Document, Chunk, PART_OF, NEXT_CHUNK). Baseline retrieval (vector, parent-child, adjacency) works on this.
2. **Entity extraction** — Chunk → entity extraction (LLM or spaCy) → Entity nodes and (Chunk)-[:MENTIONS]->(Entity).
3. **Relation extraction** — Co-occurring entities → relation extraction (LLM or fallback) → (Entity)-[:RELATES_TO]->(Entity).
4. **Entity resolution** — Fuzzy matching + optional embedding similarity → merge duplicates, re-point MENTIONS and RELATES_TO to canonical entities.
5. **Hybrid graph** — Lexical + entity/relation layer. Later: clustering, community summarization, and graph pruning as separate stages.

Do not add entity extraction until baseline retrieval is working on the lexical graph.
