# Entity–relation extraction pipeline (hybrid graph)

Run **after** baseline retrieval and the lexical graph are in place. Sequence: lexical graph first → entity extraction → relation extraction → resolution → hybrid graph.

## DAG: `entity_relation_pipeline`

1. **load_chunks** — Load chunk id and text from Neo4j (optionally limit for testing).
2. **extract_entities** — Per chunk: LLM (if `OPENAI_API_KEY`) or spaCy NER for typed entities (PERSON, ORG, LOCATION, DATE, OTHER).
3. **write_entities_and_mentions** — Create `Entity` nodes and `(Chunk)-[:MENTIONS]->(Entity)`.
4. **extract_relations** — For entity pairs co-occurring in the same chunk: LLM or fallback `RELATED_TO`.
5. **write_relations** — Create `(Entity)-[:RELATES_TO {type}]->(Entity)`.
6. **resolve_entities** — Fuzzy matching (rapidfuzz) + optional embedding similarity; produce canonical id map.
7. **apply_resolution** — Re-point MENTIONS and RELATES_TO to canonical entities; remove duplicates.

## New node/edge types

| Type | Description |
|------|-------------|
| `:Entity` | Extracted entity; properties `id`, `name`, `type`. |
| `(Chunk)-[:MENTIONS]->(Entity)` | Chunk mentions an entity. |
| `(Entity)-[:RELATES_TO]->(Entity)` | Relation (property `type`, e.g. WORKS_AT, RELATED_TO). |

## Config

- **OPENAI_API_KEY** — Enables LLM for entity and relation extraction; otherwise spaCy and generic `RELATED_TO`.
- **CHUNK_LIMIT** in DAG — Set `> 0` in `entity_relation_pipeline.py` to process only N chunks (e.g. for testing).
- **FUZZY_THRESHOLD** — rapidfuzz score (default 85) for merging duplicate entities.

## Approach

- **Entity extraction**: LLM for flexible typed entities; spaCy `en_core_web_sm` as cheaper fallback.
- **Relation extraction**: LLM for relation labels between co-occurring entities; fallback `RELATED_TO`.
- **Resolution**: Fuzzy matching on name (within type) + optional embedding similarity; merge duplicates and update graph.

Schema grounding, entity/relation extraction, and pruning are separate stages as in Neo4j’s GraphRAG KG builder; clustering and summarization can be added later.
