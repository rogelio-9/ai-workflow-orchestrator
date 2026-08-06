import dagre from "@dagrejs/dagre";
import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";

/**
 * dag_json describes structure, not geometry: a node has an id, a type, and
 * its dependencies, but no coordinates. React Flow needs x/y for every node,
 * so the positions are computed here rather than stored.
 *
 * That is the right default while the canvas is read-only. Once nodes can be
 * dragged the positions become user intent and have to be persisted -- see the
 * note in components/WorkflowCanvas.tsx.
 */

export type DagNode = {
  id: string;
  type?: string;
  config?: Record<string, unknown>;
  depends_on?: string[] | null;
};

export type DagJson = { nodes?: DagNode[] };

export type CanvasNodeData = {
  label: string;
  kind: string;
  model?: string;
  [key: string]: unknown;
};

/** One palette for both the canvas border and the minimap block, so a node is
 *  the same colour wherever it appears. */
export const KIND_COLORS: Record<string, string> = {
  llm_call: "#1971c2",
  tool_call: "#f08c00",
  router: "#7048e8",
};

export const DEFAULT_KIND_COLOR = "#6b6b6b";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 64;

function subtitle(node: DagNode): string | undefined {
  const config = node.config ?? {};
  const model = config.model ?? config.url ?? config.provider;
  return typeof model === "string" ? model : undefined;
}

export function layoutDag(dag: DagJson): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } {
  const dagNodes = dag.nodes ?? [];

  const graph = new dagre.graphlib.Graph();
  // Left-to-right reads like the execution order. ranksep is generous because
  // edge labels and the fan-in on diamond graphs get cramped otherwise.
  graph.setGraph({ rankdir: "LR", ranksep: 90, nodesep: 40 });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const node of dagNodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  const edges: Edge[] = [];
  for (const node of dagNodes) {
    for (const dependency of node.depends_on ?? []) {
      // A dependency naming a node that is not in the graph would make dagre
      // invent a phantom node, which renders as an unlabelled box and looks
      // like a bug in the canvas rather than in the workflow.
      if (!dagNodes.some((candidate) => candidate.id === dependency)) continue;
      graph.setEdge(dependency, node.id);
      edges.push({
        id: `${dependency}->${node.id}`,
        source: dependency,
        target: node.id,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    }
  }

  dagre.layout(graph);

  const nodes: Node<CanvasNodeData>[] = dagNodes.map((node) => {
    const positioned = graph.node(node.id);
    return {
      id: node.id,
      type: "step",
      // dagre returns the centre; React Flow positions by the top-left corner.
      position: {
        x: positioned.x - NODE_WIDTH / 2,
        y: positioned.y - NODE_HEIGHT / 2,
      },
      data: {
        label: node.id,
        kind: node.type ?? "llm_call",
        model: subtitle(node),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });

  return { nodes, edges };
}
