# GDS enrichment (PageRank, Leiden, FastRP, Node Similarity)

**Do not run GDS on a weak graph.** Wait until entities and relationships are stable (e.g. after `entity_relation_pipeline` has run).

## What runs

1. **Project** — Drop existing `kg` if present; project graph `kg` from nodes `Document`, `Chunk`, `Entity` and relationships `PART_OF`, `MENTIONS`, `RELATES_TO`, `NEXT_CHUNK`.
2. **PageRank** — Node importance from graph structure → writes property `pagerank`.
3. **Leiden** — Hierarchical communities (improves on Louvain) → writes property `communityId` (randomSeed: 19).
4. **FastRP** — Structural node embeddings (128 dims) → writes property `graphEmbedding`.
5. **Node Similarity** — Relatedness from shared neighborhoods → writes relationship type `SIMILAR` with property `score` (topK: 10) for related-entity suggestions.

## How to run

- **Airflow**: Trigger the **gds_enrichment** DAG (manual). Optionally set `SKIP_NODE_SIMILARITY = True` in `orchestration/airflow/dags/gds_enrichment.py` to run only PageRank, Leiden, FastRP.
- **Cypher (Neo4j Browser or cypher-shell)**: Run the scripts in `neo4j/cypher/gds/` in order:
  1. `project_kg.cypher`
  2. `pagerank.cypher`
  3. `leiden.cypher`
  4. `fastrp.cypher`
  5. `node_similarity.cypher` (optional)

## Suggested order

1. Lexical graph (PDF ingestion).
2. Baseline retrieval working.
3. Entity extraction → relation extraction → resolution (hybrid graph).
4. **Then** run GDS enrichment.

## Properties and relationships written

| Target | Property / Relationship | Algorithm |
|--------|--------------------------|-----------|
| All projected nodes | `pagerank` | PageRank |
| All projected nodes | `communityId` | Leiden |
| All projected nodes | `graphEmbedding` (list of 128 floats) | FastRP |
| Node pairs | `(:Node)-[:SIMILAR { score }]->(:Node)` | Node Similarity |

Neo4j must have the **graph-data-science** plugin and `gds.*` procedures allowed (see docker-compose).
