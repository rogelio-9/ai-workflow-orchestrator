"use client";

import { useCallback, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  DEFAULT_KIND_COLOR,
  KIND_COLORS,
  layoutDag,
  type CanvasNodeData,
  type DagJson,
} from "@/lib/layout";
import { NodeInspector } from "./NodeInspector";
import { StepNode } from "./StepNode";

// Defined outside the component: React Flow warns and remounts every node if
// this object identity changes between renders.
const NODE_TYPES = { step: StepNode };

// React Flow's dark theme paints minimap blocks #2b2b2b on a #141414 panel,
// which is invisible at minimap scale. Colouring them by step type fixes the
// contrast and makes the minimap readable as a map rather than a grey box.
function nodeColor(node: Node) {
  const { kind } = node.data as CanvasNodeData;
  return KIND_COLORS[kind] ?? DEFAULT_KIND_COLOR;
}

export function WorkflowCanvas({ dag }: { dag: DagJson }) {
  const { nodes, edges } = useMemo(() => layoutDag(dag), [dag]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(node.id);
  }, []);

  // Clicking empty canvas clears the panel. Without it the inspector keeps
  // describing a node the user has visually stopped pointing at.
  const onPaneClick = useCallback(() => setSelectedId(null), []);

  // Derived rather than stored: holding the selected node in its own state
  // would let the two drift apart whenever the dag prop changes.
  const selected = useMemo(
    () => (dag.nodes ?? []).find((node) => node.id === selectedId) ?? null,
    [dag, selectedId],
  );

  const withSelection = useMemo(
    () => nodes.map((node) => ({ ...node, selected: node.id === selectedId })),
    [nodes, selectedId],
  );

  if (nodes.length === 0) {
    return <div className="state">This workflow has no steps.</div>;
  }

  return (
    <div className="canvas-shell">
      <div className="canvas">
        {/* Read-only for now. Dragging is disabled rather than merely ignored:
            nodes are laid out by dagre and nothing persists a position, so
            letting a user move one would silently discard it on reload.

            colorMode defaults to "light", which is why the minimap and controls
            first rendered as pale blocks against a dark page. The library ships
            both palettes; it just has to be told to follow the OS. */}
        <ReactFlow
          nodes={withSelection}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          colorMode="system"
          nodesDraggable={false}
          nodesConnectable={false}
          fitView
          proOptions={{ hideAttribution: false }}
        >
          <Background />
          <Controls showInteractive={false} />
          {/* Top-right, because the minimap and React Flow's attribution both
              default to bottom-right and the minimap covers it. The attribution
              is required unless you hold a pro licence, so it has to stay
              legible rather than be hidden behind a panel. */}
          <MiniMap position="top-right" nodeColor={nodeColor} pannable zoomable />
        </ReactFlow>
      </div>

      <NodeInspector node={selected} dag={dag} />
    </div>
  );
}
