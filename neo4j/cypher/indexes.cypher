// Indexes for lexical graph. Run after constraints.
// Vector dimensions and cosine similarity per Neo4j Cypher recommendations for text embeddings.

CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk)
ON c.embedding
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

CREATE RANGE INDEX chunk_position IF NOT EXISTS
FOR (c:Chunk) ON (c.position);

CREATE TEXT INDEX entity_name IF NOT EXISTS
FOR (e:Entity) ON (e.name);
