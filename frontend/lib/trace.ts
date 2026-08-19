import type { DagJson } from "./layout";

/**
 * Folding a run's step_results into something a trace can render.
 *
 * step_results is append-only: a step that was retried has several rows, and
 * the worker's ladder can add more within one delivery. The interesting
 * questions -- what happened to this node, how much did it cost, what is the
 * graph still waiting on -- all need that history collapsed, and collapsing it
 * wrongly is silent. Hence a module with tests rather than logic inside JSX.
 */

export type StepResult = {
  stepId: string;
  nodeId: string;
  status: string;
  attempt: number;
  outputJson: Record<string, unknown> | null;
  latencyMs: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
  errorMessage: string | null;
  createdAt: string;
};

/** A node's state in the trace, whether or not it ever produced a result. */
export type NodeTrace = {
  nodeId: string;
  status: "SUCCESS" | "FAILED" | "RETRYING" | "PENDING";
  attempts: number;
  latestAttempt: StepResult | null;
  /** Every row for this node, oldest first -- the retry history. */
  history: StepResult[];
  totalLatencyMs: number;
  totalTokens: number;
};

/**
 * Latest result per node, by time.
 *
 * Deliberately not by attempt number: a user-initiated retry continues the
 * sequence now, but rows written before that fix restart at 1, so attempt is
 * not monotonic across the whole table. Time is.
 */
function byTimeAscending(a: StepResult, b: StepResult): number {
  return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
}

export function traceNodes(dag: DagJson, results: StepResult[]): NodeTrace[] {
  const grouped = new Map<string, StepResult[]>();
  for (const result of results) {
    const list = grouped.get(result.nodeId) ?? [];
    list.push(result);
    grouped.set(result.nodeId, list);
  }

  // Driven by the graph, not by the results: a node that never ran has no rows
  // at all, and omitting it would make a stalled run look like a short one.
  return (dag.nodes ?? []).map((node) => {
    const history = (grouped.get(node.id) ?? []).sort(byTimeAscending);
    const latest = history.length > 0 ? history[history.length - 1] : null;

    return {
      nodeId: node.id,
      status: (latest?.status as NodeTrace["status"]) ?? "PENDING",
      attempts: history.length,
      latestAttempt: latest,
      history,
      // Summed across attempts: a step that failed twice before succeeding
      // cost all three calls, and reporting only the last one understates it.
      totalLatencyMs: history.reduce((sum, r) => sum + (r.latencyMs ?? 0), 0),
      totalTokens: history.reduce(
        (sum, r) => sum + (r.promptTokens ?? 0) + (r.completionTokens ?? 0),
        0,
      ),
    };
  });
}

export type TraceTotals = {
  executionMs: number;
  tokens: number;
  steps: number;
  ran: number;
};

/**
 * What the run actually cost.
 *
 * Execution time is summed from the steps, not taken from the run's
 * started_at/ended_at span: a retry clears ended_at but keeps the original
 * start, so that span includes however long the run sat failed before someone
 * pressed the button.
 */
export function traceTotals(nodes: NodeTrace[]): TraceTotals {
  return {
    executionMs: nodes.reduce((sum, node) => sum + node.totalLatencyMs, 0),
    tokens: nodes.reduce((sum, node) => sum + node.totalTokens, 0),
    steps: nodes.length,
    ran: nodes.filter((node) => node.status !== "PENDING").length,
  };
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
