"use client";

import { useState } from "react";
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

export default function Home() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"neighborhood" | "community" | "query-trace">("neighborhood");
  const [neighborhoodId, setNeighborhoodId] = useState("");
  const [hops, setHops] = useState(2);
  const [communityId, setCommunityId] = useState("");
  const [queryTraceId, setQueryTraceId] = useState("");
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set());
  const [colorBy, setColorBy] = useState<"label" | "community">("label");
  const [queryTraceNodeIds, setQueryTraceNodeIds] = useState<Set<string>>(new Set());

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
          <h2>Load graph</h2>
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
        </section>
        {error && <p className={styles.error}>{error}</p>}
      </aside>
      <div className={styles.scene}>
        <GraphScene
          graphData={graphData}
          filterLabels={filterLabels}
          colorBy={colorBy}
          queryTraceNodeIds={view === "query-trace" ? queryTraceNodeIds : undefined}
        />
      </div>
      <QueryTraceOverlay
        queryTraceId={view === "query-trace" ? queryTraceId : undefined}
        nodeCount={graphData?.nodes.length ?? 0}
      />
    </main>
  );
}
