"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CanvasNodeData } from "@/lib/layout";

type TraceNodeData = CanvasNodeData & {
  status: string;
  detail?: string;
  attempts: number;
};

export function TraceStepNode({ data }: NodeProps) {
  const step = data as TraceNodeData;
  return (
    <div className="step-node" data-kind={step.kind} data-status={step.status}>
      <Handle type="target" position={Position.Left} />
      <div className="step-node-kind">
        {step.status}
        {/* A node that took more than one attempt is the interesting one, so
            the count appears here rather than only in the list below. */}
        {step.attempts > 1 && ` · ${step.attempts}×`}
      </div>
      <div className="step-node-label">{step.label}</div>
      {step.detail && <div className="step-node-model">{step.detail}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
