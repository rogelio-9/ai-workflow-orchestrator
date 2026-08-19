"use client";

import { useMemo } from "react";
import { Background, Controls, ReactFlow, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutDag, type DagJson } from "@/lib/layout";
import { formatMs, type NodeTrace } from "@/lib/trace";
import { TraceStepNode } from "./TraceStepNode";

const NODE_TYPES = { step: TraceStepNode };

/**
 * The same graph the builder draws, coloured by what happened to each node.
 *
 * The dag comes from the run's version snapshot, so this is the graph that
 * actually executed -- drawing the workflow's current one would put the right
 * results around the wrong nodes.
 */
export function TraceCanvas({ dag, nodes }: { dag: DagJson; nodes: NodeTrace[] }) {
  const { nodes: laidOut, edges } = useMemo(() => layoutDag(dag), [dag]);

  const withStatus = useMemo(() => {
    const byId = new Map(nodes.map((node) => [node.nodeId, node]));
    return laidOut.map((node): Node => {
      const trace = byId.get(node.id);
      return {
        ...node,
        data: {
          ...node.data,
          status: trace?.status ?? "PENDING",
          // Shown on the node itself so the expensive step is visible without
          // opening every row underneath.
          detail: trace && trace.totalLatencyMs > 0 ? formatMs(trace.totalLatencyMs) : undefined,
          attempts: trace?.attempts ?? 0,
        },
      };
    });
  }, [laidOut, nodes]);

  if (laidOut.length === 0) {
    return <div className="state">The graph for this run has no steps.</div>;
  }

  return (
    <div className="canvas canvas-trace">
      <ReactFlow
        nodes={withStatus}
        edges={edges}
        nodeTypes={NODE_TYPES}
        colorMode="system"
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
