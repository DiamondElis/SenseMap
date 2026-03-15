// Initialize Neo4j schema for the lexical graph (and optional Entity/Community).
// Run this once before ingestion. Idempotent: safe on empty and non-empty DBs.
//
// From repo root (Neo4j running, e.g. docker compose up -d neo4j):
//
//   cypher-shell -u neo4j -p <password> -f neo4j/cypher/schema_init.cypher
//
// Or run constraints and indexes separately:
//
//   cypher-shell -u neo4j -p <password> -f neo4j/cypher/constraints.cypher
//   cypher-shell -u neo4j -p <password> -f neo4j/cypher/indexes.cypher
//
// Order: constraints must complete before indexes (vector index requires Chunk to exist).

// ----- 1. Constraints (unique node ids) -----

CREATE CONSTRAINT document_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT parent_chunk_id IF NOT EXISTS
FOR (p:ParentChunk) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT ingestion_run_id IF NOT EXISTS
FOR (r:IngestionRun) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (e:Entity) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT entity_mention_id IF NOT EXISTS
FOR (m:EntityMention) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (c:Claim) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT community_id IF NOT EXISTS
FOR (c:Community) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT conversation_id IF NOT EXISTS
FOR (c:Conversation) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT message_id IF NOT EXISTS
FOR (m:Message) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT candidate_claim_id IF NOT EXISTS
FOR (cc:CandidateClaim) REQUIRE cc.id IS UNIQUE;

CREATE CONSTRAINT candidate_relation_id IF NOT EXISTS
FOR (cr:CandidateRelation) REQUIRE cr.id IS UNIQUE;

CREATE CONSTRAINT validation_task_id IF NOT EXISTS
FOR (v:ValidationTask) REQUIRE v.id IS UNIQUE;

// ----- 2. Indexes (vector + range for retrieval and filtering) -----

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

CREATE RANGE INDEX validation_task_status IF NOT EXISTS
FOR (v:ValidationTask) ON (v.status);

CREATE RANGE INDEX message_position IF NOT EXISTS
FOR (m:Message) ON (m.position);
