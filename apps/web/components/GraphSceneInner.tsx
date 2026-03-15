"use client";

import { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Line } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import type { GraphData } from "@/app/page";

const LABEL_COLORS: Record<string, string> = {
  Entity: "#3b82f6",
  EntityMention: "#06b6d4",
  Chunk: "#22c55e",
  Document: "#f59e0b",
  ParentChunk: "#a855f7",
  IngestionRun: "#64748b",
  Node: "#94a3b8",
};

const SEMANTIC_EDGE_TYPES = new Set(["RELATES_TO", "REFERS_TO", "MENTIONS", "HAS_ENTITY"]);
const LEXICAL_EDGE_TYPES = new Set(["HAS_PARENT", "HAS_CHILD", "NEXT_CHUNK", "INGESTED_IN"]);
const LEXICAL_LABELS = new Set(["Document", "ParentChunk", "Chunk", "IngestionRun"]);
const ENTITY_LABELS = new Set(["Entity", "EntityMention"]);

const ENTITY_TYPE_COLORS: Record<string, string> = {
  Person: "#3b82f6",
  Organization: "#8b5cf6",
  Concept: "#06b6d4",
  Technology: "#10b981",
  Method: "#f59e0b",
  Material: "#ef4444",
  Place: "#ec4899",
  Event: "#6366f1",
  DocumentTopic: "#14b8a6",
};
const DEFAULT_ENTITY_TYPE_COLOR = "#64748b";

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h << 5) - h + str.charCodeAt(i);
  return Math.abs(h);
}

function nodeColor(node: GraphData["nodes"][0], colorBy: "label" | "community"): string {
  if (colorBy === "label") {
    if (node.label === "Entity" && node.type) {
      return ENTITY_TYPE_COLORS[node.type] ?? DEFAULT_ENTITY_TYPE_COLOR;
    }
    return LABEL_COLORS[node.label || "Node"] ?? "#94a3b8";
  }
  const cid = node.communityId != null ? String(node.communityId) : "none";
  const hue = hash(cid) % 360;
  return `hsl(${hue}, 65%, 55%)`;
}

function layoutNodes(nodes: GraphData["nodes"], edges: GraphData["edges"]): Map<string, [number, number, number]> {
  const pos = new Map<string, [number, number, number]>();
  const n = nodes.length;
  if (n === 0) return pos;
  if (n === 1) {
    pos.set(nodes[0].id, [0, 0, 0]);
    return pos;
  }
  const radius = 8;
  for (let i = 0; i < n; i++) {
    const phi = Math.acos(-1 + (2 * i) / n);
    const theta = Math.sqrt(n * Math.PI) * phi;
    pos.set(nodes[i].id, [
      radius * Math.cos(theta) * Math.sin(phi),
      radius * Math.sin(theta) * Math.sin(phi),
      radius * Math.cos(phi),
    ]);
  }
  return pos;
}

type SceneContentProps = {
  graphData: GraphData | null;
  filterLabels: Set<string>;
  colorBy: "label" | "community";
  queryTraceNodeIds?: Set<string>;
  graphMode: "lexical" | "hybrid" | "entity-only";
  showMentions: boolean;
  onHover: (node: GraphData["nodes"][0] | null) => void;
};

function SceneContent({ graphData, filterLabels, colorBy, queryTraceNodeIds, graphMode, showMentions, onHover }: SceneContentProps) {
  const { visibleNodes, visibleEdges } = useMemo(() => {
    if (!graphData) return { visibleNodes: [] as GraphData["nodes"], visibleEdges: [] as GraphData["edges"] };
    let nodes = graphData.nodes.filter((n) => !filterLabels.has(n.label || "Node"));
    let edges = graphData.edges;

    if (!showMentions) {
      const mentionIds = new Set(nodes.filter((n) => n.label === "EntityMention").map((n) => n.id));
      nodes = nodes.filter((n) => n.label !== "EntityMention");
      edges = edges.filter((e) => !mentionIds.has(e.source) && !mentionIds.has(e.target));
    }

    if (graphMode === "lexical") {
      nodes = nodes.filter((n) => LEXICAL_LABELS.has(n.label || ""));
      edges = edges.filter((e) => LEXICAL_EDGE_TYPES.has(e.type || ""));
    } else if (graphMode === "entity-only") {
      nodes = nodes.filter((n) => ENTITY_LABELS.has(n.label || ""));
      edges = edges.filter((e) => SEMANTIC_EDGE_TYPES.has(e.type || ""));
    }

    const nodeIds = new Set(nodes.map((n) => n.id));
    edges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    return { visibleNodes: nodes, visibleEdges: edges };
  }, [graphData, filterLabels, graphMode, showMentions]);

  const positions = useMemo(() => {
    if (!visibleNodes.length) return new Map<string, [number, number, number]>();
    return layoutNodes(visibleNodes, visibleEdges);
  }, [visibleNodes, visibleEdges]);

  if (visibleNodes.length === 0) {
    return (
      <mesh>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshBasicMaterial color="#333" />
      </mesh>
    );
  }

  return (
    <>
      {visibleNodes.map((node) => {
        const pos = positions.get(node.id);
        if (!pos) return null;
        const isTrace = queryTraceNodeIds?.has(node.id);
        return (
          <group key={node.id} position={pos}>
            <mesh
              onPointerOver={(e: ThreeEvent<PointerEvent>) => {
                e.stopPropagation();
                onHover(node);
              }}
              onPointerOut={() => onHover(null)}
            >
              <sphereGeometry args={[isTrace ? 0.35 : 0.28, 16, 16]} />
              <meshStandardMaterial
                color={nodeColor(node, colorBy)}
                emissive={isTrace ? "#3b82f6" : "#000000"}
                emissiveIntensity={isTrace ? 0.4 : 0}
              />
            </mesh>
          </group>
        );
      })}
      {visibleEdges
        .filter((e) => positions.has(e.source) && positions.has(e.target))
        .map((edge, i) => {
          const a = positions.get(edge.source)!;
          const b = positions.get(edge.target)!;
          const isSemantic = SEMANTIC_EDGE_TYPES.has(edge.type || "");
          const color = isSemantic ? "#06b6d4" : "#444";
          return (
            <Line key={`${edge.source}-${edge.target}-${i}`} points={[a, b]} color={color} />
          );
        })}
    </>
  );
}

type GraphSceneInnerProps = {
  graphData: GraphData | null;
  filterLabels: Set<string>;
  colorBy: "label" | "community";
  queryTraceNodeIds?: Set<string>;
  graphMode?: "lexical" | "hybrid" | "entity-only";
  showMentions?: boolean;
};

export function GraphSceneInner({ graphData, filterLabels, colorBy, queryTraceNodeIds, graphMode = "hybrid", showMentions = true }: GraphSceneInnerProps) {
  const [hovered, setHovered] = useState<GraphData["nodes"][0] | null>(null);

  return (
    <>
      <div
        style={{
          position: "absolute",
          top: 8,
          left: 8,
          right: 8,
          zIndex: 5,
          pointerEvents: "none",
          color: "#e0e0e0",
          fontSize: "0.8rem",
          background: hovered ? "rgba(0,0,0,0.85)" : "transparent",
          padding: hovered ? "0.5rem 0.75rem" : 0,
          borderRadius: 6,
          maxWidth: 320,
        }}
      >
        {hovered && (
          <>
            <div><strong>{hovered.label ?? "Node"}</strong> {hovered.id}</div>
            {hovered.type && <div>type: {hovered.type}</div>}
            {hovered.communityId != null && <div>community: {String(hovered.communityId)}</div>}
            {hovered.pagerank != null && <div>pagerank: {Number(hovered.pagerank).toFixed(4)}</div>}
            {hovered.text && <div style={{ marginTop: 4, fontSize: "0.75rem", color: "#a0a0a0" }}>{hovered.text.slice(0, 120)}…</div>}
          </>
        )}
      </div>
      <Canvas camera={{ position: [0, 0, 20], fov: 50 }} gl={{ antialias: true }}>
        <color attach="background" args={["#0f0f12"]} />
        <ambientLight intensity={0.4} />
        <pointLight position={[10, 10, 10]} intensity={1} />
        <pointLight position={[-10, -10, 5]} intensity={0.5} />
        <SceneContent
          graphData={graphData}
          filterLabels={filterLabels}
          colorBy={colorBy}
          queryTraceNodeIds={queryTraceNodeIds}
          graphMode={graphMode}
          showMentions={showMentions}
          onHover={setHovered}
        />
        <OrbitControls enableDamping dampingFactor={0.05} minDistance={5} maxDistance={80} />
      </Canvas>
    </>
  );
}
