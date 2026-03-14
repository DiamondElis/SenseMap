// PageRank: node importance from graph structure. Writes property 'pagerank'.
// Run after project_kg.cypher.

CALL gds.pageRank.write('kg', {
  writeProperty: 'pagerank'
}) YIELD nodePropertiesWritten, ranIterations
RETURN nodePropertiesWritten, ranIterations;
