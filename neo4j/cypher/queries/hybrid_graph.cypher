// Hybrid graph: run after entity/relation extraction.
// Node types: Document, Chunk, Entity.
// Edge types: (Chunk)-[:PART_OF]->(Document), (Chunk)-[:PART_OF]->(Chunk), (Chunk)-[:NEXT_CHUNK]->(Chunk),
//             (Chunk)-[:MENTIONS]->(Entity), (Entity)-[:RELATES_TO]->(Entity).
// No new constraints; Entity.id and entity_name index already exist in constraints.cypher / indexes.cypher.

// Example: create MENTIONS (run from application code, not here)
// MATCH (c:Chunk {id: $chunk_id}), (e:Entity {id: $entity_id}) MERGE (c)-[:MENTIONS]->(e)

// Example: create RELATES_TO (run from application code)
// MATCH (a:Entity {id: $a_id}), (b:Entity {id: $b_id}) MERGE (a)-[r:RELATES_TO]->(b) SET r.type = $relation_type
