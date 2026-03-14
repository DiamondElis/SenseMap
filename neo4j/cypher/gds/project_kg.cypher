// Project the knowledge graph for GDS: Document, Chunk, Entity and their relationships.
// Run once before PageRank, Leiden, FastRP, Node Similarity.
// Drop existing 'kg' if present so the projection is fresh.

CALL gds.graph.drop('kg', false) YIELD graphName
RETURN graphName;

CALL gds.graph.project(
  'kg',
  ['Document', 'Chunk', 'Entity'],
  ['PART_OF', 'MENTIONS', 'RELATES_TO', 'NEXT_CHUNK']
) YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
