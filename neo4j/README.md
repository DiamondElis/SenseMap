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
