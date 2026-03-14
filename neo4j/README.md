# Neo4j schema (lexical graph)

Initial graph model: **Document** and **Chunk** nodes with vector embeddings and structural links, plus **Entity** and **Community** for GraphRAG. This is the recommended starting point before any ingestion.

## Initialize schema (before ingestion)

With Neo4j running (e.g. `docker compose up -d neo4j`), from repo root:

```bash
# Option 1: run each file
cypher-shell -u neo4j -p password123 -f neo4j/cypher/constraints.cypher
cypher-shell -u neo4j -p password123 -f neo4j/cypher/indexes.cypher

# Option 2: pipe both (constraints then indexes)
cat neo4j/cypher/constraints.cypher neo4j/cypher/indexes.cypher | cypher-shell -u neo4j -p password123
```

Or run the statements in **Neo4j Browser** (http://localhost:7474), in order: `constraints.cypher` then `indexes.cypher`.

## Contents

| File | Purpose |
|------|--------|
| `cypher/constraints.cypher` | Unique constraints: `Document.id`, `Chunk.id`, `Entity.id`, `Community.id` |
| `cypher/indexes.cypher` | Vector index on `Chunk.embedding` (1536 dims, cosine), range index on `Chunk.position`, text index on `Entity.name` |

Vector index uses **cosine** similarity and **1536** dimensions as recommended for text embeddings.

## Hybrid graph (after entity extraction)

Once the entity-relation pipeline has run, the graph also has:

- **(:Entity)** — extracted entities (constraint on `id`, text index on `name`).
- **(:Chunk)-[:MENTIONS]->(:Entity)** — chunk mentions an entity.
- **(:Entity)-[:RELATES_TO]->(:Entity)** — relation between entities (optional property `type`).

See `cypher/queries/hybrid_graph.cypher` for examples. Build order: lexical graph first, then entity extraction → relation extraction → resolution → hybrid graph.

## GDS enrichment (after hybrid graph is stable)

Do not run on a weak graph. When entities and relationships are in place, run Graph Data Science algorithms:

- **Cypher scripts**: `cypher/gds/project_kg.cypher` then `pagerank.cypher`, `leiden.cypher`, `fastrp.cypher`, `node_similarity.cypher` (optional).
- **Airflow**: DAG **gds_enrichment** runs project → PageRank → Leiden → FastRP → Node Similarity.

Writes: `pagerank`, `communityId`, `graphEmbedding` (128 dims), and optional `(:X)-[:SIMILAR { score }]->(:Y)` for related-entity suggestions. See `docs/runbooks/gds-enrichment.md`.
