# Graph-serving API and 3D visualization

Build order: **subgraph APIs first**, then the UI. The visualization consumes these endpoints so it stays integrated with retrieval and answers.

## Graph-serving endpoints (FastAPI)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/graph/neighborhood?id=<entity_id>&hops=2` | Expand from a node (any label) by N hops; returns nodes and edges with `label`, `communityId`, `pagerank`, `type`, `text`. |
| GET | `/graph/community/<community_id>` | All nodes with `communityId` equal to the given id and edges between them (from GDS Leiden). |
| GET | `/graph/query-trace/<query_id>?expand_depth=1` | Subgraph for a prior retrieval/answer: `query_id` is returned by `POST /answer` and stored in memory; returns the chunk/node subgraph for that trace. |
| GET | `/graph/subgraph?chunk_ids=id1,id2&expand_depth=1` | Subgraph for given chunk ids (NEXT_CHUNK and PART_OF). |

`POST /answer` now returns `query_id` and stores the source chunk ids so `GET /graph/query-trace/<query_id>` can return the evidence subgraph.

## UI (Next.js + Three.js)

- **App shell**: Sidebar with load controls and filters; main area is the 3D canvas.
- **Three.js graph scene**: Nodes as spheres, edges as lines; OrbitControls for pan/zoom (semantic zoom).
- **Filters**: Node type (hide by label: Entity, Chunk, Document).
- **Coloring**: By **label** (fixed colors per label) or by **community** (hash-based hue from `communityId`).
- **Hover**: Metadata tooltip (id, label, type, communityId, pagerank, text preview).
- **Query-trace overlay**: When viewing a query-trace load, nodes from that trace are highlighted (emissive) and a bottom overlay shows the query_id and node count.

Use **Load neighborhood**, **Load community**, or **Load query trace** with an id from the API; then filter and color as needed.
