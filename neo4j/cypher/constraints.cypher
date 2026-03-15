// Lexical graph schema: run once before any ingestion.
// Document, ParentChunk, Chunk, IngestionRun (lexical); Entity, Community (optional GraphRAG).

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

// Conversation memory (Step 5): candidate layer and validation
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
