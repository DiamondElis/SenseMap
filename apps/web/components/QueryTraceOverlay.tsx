"use client";

type QueryTraceOverlayProps = {
  queryTraceId?: string;
  nodeCount: number;
};

export function QueryTraceOverlay({ queryTraceId, nodeCount }: QueryTraceOverlayProps) {
  if (!queryTraceId) return null;
  return (
    <div
      style={{
        position: "fixed",
        bottom: "1rem",
        left: "50%",
        transform: "translateX(-50%)",
        padding: "0.5rem 1rem",
        background: "rgba(0,0,0,0.8)",
        color: "#e0e0e0",
        borderRadius: 8,
        fontSize: "0.875rem",
        zIndex: 10,
        border: "1px solid #333",
      }}
    >
      <strong>Query trace</strong>: {queryTraceId.slice(0, 8)}… — {nodeCount} nodes (retrieved evidence)
    </div>
  );
}
