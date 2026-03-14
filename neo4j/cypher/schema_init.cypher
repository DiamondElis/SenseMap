// Initialize Neo4j schema before any ingestion.
// Lexical graph: Document, Chunk (with vector embeddings), Entity, Community.
// Run constraints first, then indexes.
//
// From repo root (with Neo4j running, e.g. docker compose up -d neo4j):
//
//   cypher-shell -u neo4j -p password123 -f neo4j/cypher/constraints.cypher
//   cypher-shell -u neo4j -p password123 -f neo4j/cypher/indexes.cypher
//
// Or pipe both (constraints must complete before indexes):
//
//   cat neo4j/cypher/constraints.cypher neo4j/cypher/indexes.cypher | cypher-shell -u neo4j -p password123
