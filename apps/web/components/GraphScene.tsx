"use client";

import { Suspense, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { GraphData } from "@/app/page";

const Scene = dynamic(() => import("./GraphSceneInner").then((m) => m.GraphSceneInner), {
  ssr: false,
  loading: () => <div style={{ width: "100%", height: "100%", background: "#0f0f12", display: "flex", alignItems: "center", justifyContent: "center", color: "#666" }}>Loading scene…</div>,
});

type GraphSceneProps = {
  graphData: GraphData | null;
  filterLabels: Set<string>;
  colorBy: "label" | "community";
  queryTraceNodeIds?: Set<string>;
};

export function GraphScene(props: GraphSceneProps) {
  return (
    <div style={{ width: "100%", height: "100%" }}>
      <Suspense fallback={<div style={{ width: "100%", height: "100%", background: "#0f0f12" }} />}>
        <Scene {...props} />
      </Suspense>
    </div>
  );
}
