"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CanvasNodeData } from "@/lib/layout";

export function StepNode({ data }: NodeProps) {
  const step = data as CanvasNodeData;
  return (
    <div className="step-node" data-kind={step.kind}>
      {/* Both handles always render. A source node with no incoming edge still
          needs its target handle in the DOM, or adding an edge to it later
          has nothing to attach to. */}
      <Handle type="target" position={Position.Left} />
      <div className="step-node-kind">{step.kind}</div>
      <div className="step-node-label">{step.label}</div>
      {step.model && <div className="step-node-model">{step.model}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
