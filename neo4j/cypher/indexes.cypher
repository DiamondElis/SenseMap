// Indexes for lexical graph. Run after constraints.
// Vector index on Chunk.embedding for retrieval; range indexes for filtering and ordering.

CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

CREATE RANGE INDEX document_source_type IF NOT EXISTS
FOR (d:Document) ON (d.source_type);

CREATE RANGE INDEX document_created_at IF NOT EXISTS
FOR (d:Document) ON (d.created_at);

CREATE RANGE INDEX parent_chunk_position IF NOT EXISTS
FOR (p:ParentChunk) ON (p.position);

CREATE RANGE INDEX chunk_position IF NOT EXISTS
FOR (c:Chunk) ON (c.position);

CREATE RANGE INDEX entity_canonical_name IF NOT EXISTS
FOR (e:Entity) ON (e.canonical_name);

CREATE RANGE INDEX entity_type IF NOT EXISTS
FOR (e:Entity) ON (e.type);

CREATE FULLTEXT INDEX entity_names_description IF NOT EXISTS
FOR (e:Entity) ON EACH [e.canonical_name, e.description];
