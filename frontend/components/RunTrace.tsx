"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@apollo/client/react";
import { RUN_TRACE } from "@/lib/queries";
import type { DagJson } from "@/lib/layout";
import {
  formatMs,
  traceNodes,
  traceTotals,
  type NodeTrace,
  type StepResult,
} from "@/lib/trace";
import { TraceCanvas } from "./TraceCanvas";

type RunTraceData = {
  run: {
    id: string;
    workflowId: string;
    workflowVersion: number;
    status: string;
    startedAt: string | null;
    endedAt: string | null;
    inputVars: Record<string, unknown> | null;
    dagJson: DagJson | null;
    stepResults: StepResult[];
  } | null;
};

function Output({ result }: { result: StepResult }) {
  if (result.errorMessage) {
    return <pre className="trace-output" data-kind="error">{result.errorMessage}</pre>;
  }
  const completion = result.outputJson?.completion;
  if (typeof completion === "string") {
    return <pre className="trace-output">{completion}</pre>;
  }
  if (result.outputJson) {
    return <pre className="trace-output">{JSON.stringify(result.outputJson, null, 2)}</pre>;
  }
  return <p className="muted">No output recorded.</p>;
}

function StepRow({ node }: { node: NodeTrace }) {
  const [open, setOpen] = useState(false);
  const latest = node.latestAttempt;

  return (
    <li className="trace-step" data-status={node.status}>
      <button className="trace-head" onClick={() => setOpen(!open)} disabled={!latest}>
        <span className="badge" data-status={node.status}>{node.status}</span>
        <strong>{node.nodeId}</strong>
        <span className="muted">
          {node.attempts === 0
            ? "never ran"
            : `${node.attempts} attempt${node.attempts === 1 ? "" : "s"}`}
        </span>
        <span className="muted">{node.totalLatencyMs > 0 ? formatMs(node.totalLatencyMs) : "—"}</span>
        <span className="muted">{node.totalTokens > 0 ? `${node.totalTokens} tok` : "—"}</span>
        <span className="muted">{latest ? (open ? "▾" : "▸") : ""}</span>
      </button>

      {open && latest && (
        <div className="trace-body">
          <Output result={latest} />
          {/* Earlier attempts only when there were any -- a retried step is
              the case where the last row alone misleads. */}
          {node.history.length > 1 && (
            <details className="trace-history">
              <summary className="muted">{node.history.length - 1} earlier attempt(s)</summary>
              {node.history.slice(0, -1).map((attempt, index) => (
                <div key={index} className="trace-attempt">
                  <span className="badge" data-status={attempt.status}>{attempt.status}</span>
                  <span className="muted">
                    {new Date(attempt.createdAt).toLocaleTimeString()}
                    {attempt.latencyMs != null && ` · ${formatMs(attempt.latencyMs)}`}
                  </span>
                  <Output result={attempt} />
                </div>
              ))}
            </details>
          )}
        </div>
      )}
    </li>
  );
}

export function RunTrace({ id }: { id: string }) {
  const { data, loading, error } = useQuery<RunTraceData>(RUN_TRACE, { variables: { id } });

  if (loading) return <p className="state">Loading run…</p>;
  if (error) {
    return (
      <div className="state" data-kind="error">
        <strong>Could not load this run.</strong>
        <p className="muted">{error.message}</p>
      </div>
    );
  }

  const run = data?.run;
  if (!run) {
    return (
      <div className="state">
        <strong>Not found.</strong>
        <p className="muted">
          No run with that id is available to you. <Link href="/">Back to workflows</Link>
        </p>
      </div>
    );
  }

  if (!run.dagJson) {
    // Reachable for rows written straight to SQL before versioning existed.
    // Saying so beats drawing the current graph and implying it is this one.
    return (
      <div className="state" data-kind="error">
        <strong>No graph snapshot for this run.</strong>
        <p className="muted">
          It predates workflow versioning, so the graph it executed was not recorded.
        </p>
      </div>
    );
  }

  const nodes = traceNodes(run.dagJson, run.stepResults);
  const totals = traceTotals(nodes);

  return (
    <>
      <p className="muted">
        <Link href={`/workflows/${run.workflowId}`}>← Back to workflow</Link>
      </p>

      <div className="detail-heading">
        <h1>
          Run <code>{run.id.slice(0, 8)}</code>
        </h1>
        <span className="badge" data-status={run.status}>{run.status}</span>
      </div>

      <p className="muted">
        graph v{run.workflowVersion} · {totals.ran}/{totals.steps} steps ran ·{" "}
        {/* Summed from the steps, not the run's start-to-end span: a retry
            keeps the original started_at, so that span counts idle time. */}
        {formatMs(totals.executionMs)} executing · {totals.tokens} tokens
      </p>

      <TraceCanvas dag={run.dagJson} nodes={nodes} />

      <section className="history">
        <h2>Steps</h2>
        <ol className="trace-list">
          {nodes.map((node) => (
            <StepRow key={node.nodeId} node={node} />
          ))}
        </ol>
      </section>
    </>
  );
}
