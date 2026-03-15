// Optional: lexical-only constraints (also included in constraints.cypher / schema_init.cypher).
// Run schema_init.cypher for full schema.

CREATE CONSTRAINT parent_chunk_id IF NOT EXISTS
FOR (pc:ParentChunk) REQUIRE pc.id IS UNIQUE;

CREATE CONSTRAINT ingestion_run_id IF NOT EXISTS
FOR (r:IngestionRun) REQUIRE r.id IS UNIQUE;
