// FastRP: scalable structural node embeddings for similarity and ML.
// Writes property 'graphEmbedding' (128 dimensions). Run after project_kg.cypher.

CALL gds.fastRP.write('kg', {
  embeddingDimension: 128,
  writeProperty: 'graphEmbedding'
}) YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
