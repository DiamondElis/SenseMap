// Leiden: hierarchical communities; improves on Louvain connectivity.
// Writes property 'communityId'. Run after project_kg.cypher.

CALL gds.leiden.write('kg', {
  writeProperty: 'communityId',
  randomSeed: 19
}) YIELD nodePropertiesWritten, communityCount
RETURN nodePropertiesWritten, communityCount;
