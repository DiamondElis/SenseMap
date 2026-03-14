// Node Similarity: relatedness from shared neighborhoods.
// Writes relationships SIMILAR with property 'score' (topK per node for related-entity suggestions).
// Run after project_kg.cypher. Optional: run last so the graph projection includes all nodes.

CALL gds.nodeSimilarity.write('kg', {
  writeRelationshipType: 'SIMILAR',
  writeProperty: 'score',
  topK: 10,
  similarityCutoff: 0.1
}) YIELD nodesCompared, relationshipsWritten
RETURN nodesCompared, relationshipsWritten;
