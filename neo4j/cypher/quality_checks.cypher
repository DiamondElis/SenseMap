// Quality checks for the hybrid (lexical + entity) graph. Run manually during development.
// Usage: cypher-shell -u neo4j -p <password> -f neo4j/cypher/quality_checks.cypher
// Or run individual queries in Neo4j Browser.
//
// These are read-only queries; they do not modify the graph.

// ----- 1. Entity counts by type -----
MATCH (e:Entity)
RETURN e.type AS type, count(*) AS count
ORDER BY count DESC
;

// ----- 2. Mentions without canonical entity (unresolved) -----
MATCH (m:EntityMention)
WHERE NOT (m)-[:REFERS_TO]->(:Entity)
RETURN count(m) AS unresolved_mentions
;

// ----- 3. Chunks not yet entity-processed -----
MATCH (c:Chunk)
WHERE c.entity_processed_at IS NULL
RETURN c.id AS id
LIMIT 20
;

// ----- 4. Duplicate suspicious canonical names (case-insensitive) -----
MATCH (e:Entity)
WITH toLower(e.canonical_name) AS name, collect(e.id) AS ids, count(*) AS n
WHERE n > 1
RETURN name, ids, n
ORDER BY n DESC
;
