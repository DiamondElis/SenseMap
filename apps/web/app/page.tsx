"use client";

import { useState, useEffect } from "react";
import { GraphScene } from "@/components/GraphScene";
import { Filters } from "@/components/Filters";
import { QueryTraceOverlay } from "@/components/QueryTraceOverlay";
import styles from "./page.module.css";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type GraphData = {
  nodes: Array<{
    id: string;
    label?: string;
    text?: string;
    communityId?: number | string;
    pagerank?: number;
    type?: string;
  }>;
  edges: Array<{ source: string; target: string; type?: string }>;
  query_id?: string;
};

type DocumentOption = { id: string; title: string; source_type: string };

export default function Home() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"document" | "neighborhood" | "community" | "query-trace" | "entities" | "entity-neighborhood" | "hybrid-document">("document");
  const [documents, setDocuments] = useState<DocumentOption[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [neighborhoodId, setNeighborhoodId] = useState("");
  const [hops, setHops] = useState(2);
  const [communityId, setCommunityId] = useState("");
  const [queryTraceId, setQueryTraceId] = useState("");
  const [chunkIdForEntities, setChunkIdForEntities] = useState("");
  const [entityIdForNeighborhood, setEntityIdForNeighborhood] = useState("");
  const [entityHops, setEntityHops] = useState(2);
  const [hybridDocumentId, setHybridDocumentId] = useState("");
  const [graphMode, setGraphMode] = useState<"lexical" | "hybrid" | "entity-only">("hybrid");
  const [showMentions, setShowMentions] = useState(true);
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set());
  const [colorBy, setColorBy] = useState<"label" | "community">("label");
  const [queryTraceNodeIds, setQueryTraceNodeIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/graph/documents`)
      .then((res) => (res.ok ? res.json() : []))
      .then(async (list: DocumentOption[]) => {
        if (cancelled) return;
        setDocuments(list);
        if (list.length > 0) {
          setSelectedDocumentId(list[0].id);
          try {
            const res = await fetch(`${API_URL}/graph/document/${encodeURIComponent(list[0].id)}`);
            if (res.ok && !cancelled) {
              const data: GraphData = await res.json();
              setGraphData(data);
              setView("document");
            }
          } catch {
            // ignore; user can click Load document graph
          }
        }
      })
      .catch(() => { if (!cancelled) setDocuments([]); });
    return () => { cancelled = true; };
  }, []);

  const fetchDocumentGraph = async () => {
    const docId = selectedDocumentId?.trim();
    if (!docId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/graph/document/${encodeURIComponent(docId)}`);
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("document");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchNeighborhood = async () => {
    if (!neighborhoodId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/graph/neighborhood?id=${encodeURIComponent(neighborhoodId.trim())}&hops=${hops}`
      );
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("neighborhood");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchCommunity = async () => {
    if (!communityId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/graph/community/${encodeURIComponent(communityId.trim())}`
      );
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("community");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchQueryTrace = async () => {
    if (!queryTraceId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/graph/query-trace/${encodeURIComponent(queryTraceId.trim())}?expand_depth=1`
      );
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("query-trace");
      setQueryTraceNodeIds(new Set(data.nodes.map((n) => n.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchEntitiesForChunk = async () => {
    const cid = chunkIdForEntities.trim();
    if (!cid) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/graph/entities?chunk_id=${encodeURIComponent(cid)}`);
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("entities");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchEntityNeighborhood = async () => {
    const eid = entityIdForNeighborhood.trim();
    if (!eid) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/graph/entity-neighborhood?id=${encodeURIComponent(eid)}&hops=${entityHops}`
      );
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("entity-neighborhood");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchHybridDocument = async () => {
    const docId = (hybridDocumentId.trim() || selectedDocumentId).trim();
    if (!docId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/graph/hybrid-document?document_id=${encodeURIComponent(docId)}`);
      if (!res.ok) throw new Error(await res.text());
      const data: GraphData = await res.json();
      setGraphData(data);
      setView("hybrid-document");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className={styles.main}>
      <aside className={styles.sidebar}>
        <h1 className={styles.title}>SenseMap</h1>
        <Filters
          filterLabels={filterLabels}
          setFilterLabels={setFilterLabels}
          colorBy={colorBy}
          setColorBy={setColorBy}
          nodeLabels={graphData ? [...new Set(graphData.nodes.map((n) => n.label || "Node"))] : []}
        />
        <section className={styles.controls}>
          <h2>Graph mode</h2>
          <div className={styles.field}>
            <label>View</label>
            <select value={graphMode} onChange={(e) => setGraphMode(e.target.value as "lexical" | "hybrid" | "entity-only")}>
              <option value="lexical">Lexical only</option>
              <option value="hybrid">Hybrid</option>
              <option value="entity-only">Entity only</option>
            </select>
          </div>
          <div className={styles.field}>
            <label>
              <input type="checkbox" checked={showMentions} onChange={(e) => setShowMentions(e.target.checked)} />
              Show mention nodes
            </label>
          </div>
        </section>
        <section className={styles.controls}>
          <h2>Load graph</h2>
          <div className={styles.field}>
            <label>Document (lexical graph)</label>
            <select
              value={selectedDocumentId}
              onChange={(e) => setSelectedDocumentId(e.target.value)}
              disabled={loading}
            >
              <option value="">Select a document</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title || d.id}
                </option>
              ))}
            </select>
            <button onClick={fetchDocumentGraph} disabled={loading || !selectedDocumentId}>
              Load document graph
            </button>
          </div>
          <div className={styles.field}>
            <label>Neighborhood (node id)</label>
            <input
              value={neighborhoodId}
              onChange={(e) => setNeighborhoodId(e.target.value)}
              placeholder="e.g. ent_Company_abc123"
            />
            <input
              type="number"
              min={0}
              max={5}
              value={hops}
              onChange={(e) => setHops(Number(e.target.value))}
            />
            <button onClick={fetchNeighborhood} disabled={loading}>
              Load neighborhood
            </button>
          </div>
          <div className={styles.field}>
            <label>Community (communityId)</label>
            <input
              value={communityId}
              onChange={(e) => setCommunityId(e.target.value)}
              placeholder="e.g. 0"
            />
            <button onClick={fetchCommunity} disabled={loading}>
              Load community
            </button>
          </div>
          <div className={styles.field}>
            <label>Query trace (query_id from /answer)</label>
            <input
              value={queryTraceId}
              onChange={(e) => setQueryTraceId(e.target.value)}
              placeholder="uuid from answer response"
            />
            <button onClick={fetchQueryTrace} disabled={loading}>
              Load query trace
            </button>
          </div>
          <div className={styles.field}>
            <label>Entities for chunk (chunk_id)</label>
            <input
              value={chunkIdForEntities}
              onChange={(e) => setChunkIdForEntities(e.target.value)}
              placeholder="chunk id"
            />
            <button onClick={fetchEntitiesForChunk} disabled={loading}>
              Load entities
            </button>
          </div>
          <div className={styles.field}>
            <label>Entity neighborhood (entity id)</label>
            <input
              value={entityIdForNeighborhood}
              onChange={(e) => setEntityIdForNeighborhood(e.target.value)}
              placeholder="entity id"
            />
            <input type="number" min={0} max={5} value={entityHops} onChange={(e) => setEntityHops(Number(e.target.value))} />
            <button onClick={fetchEntityNeighborhood} disabled={loading}>
              Load entity neighborhood
            </button>
          </div>
          <div className={styles.field}>
            <label>Hybrid document (document_id)</label>
            <input
              value={hybridDocumentId}
              onChange={(e) => setHybridDocumentId(e.target.value)}
              placeholder={selectedDocumentId || "document id"}
            />
            <button onClick={fetchHybridDocument} disabled={loading}>
              Load hybrid document
            </button>
          </div>
        </section>
        {error && <p className={styles.error}>{error}</p>}
      </aside>
      <div className={styles.scene}>
        <GraphScene
          graphData={graphData}
          filterLabels={filterLabels}
          colorBy={colorBy}
          queryTraceNodeIds={view === "query-trace" ? queryTraceNodeIds : undefined}
          graphMode={graphMode}
          showMentions={showMentions}
        />
      </div>
      <QueryTraceOverlay
        queryTraceId={view === "query-trace" ? queryTraceId : undefined}
        nodeCount={graphData?.nodes.length ?? 0}
      />
    </main>
  );
}
