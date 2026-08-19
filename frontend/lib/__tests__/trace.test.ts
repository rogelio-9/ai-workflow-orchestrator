import assert from "node:assert/strict";
import { test } from "node:test";
import { formatMs, traceNodes, traceTotals, type StepResult } from "../trace.ts";
import type { DagJson } from "../layout.ts";

const DAG: DagJson = {
  nodes: [
    { id: "a", type: "llm_call" },
    { id: "b", type: "llm_call", depends_on: ["a"] },
  ],
};

function result(overrides: Partial<StepResult> = {}): StepResult {
  return {
    stepId: "s1",
    nodeId: "a",
    status: "SUCCESS",
    attempt: 1,
    outputJson: null,
    latencyMs: 100,
    promptTokens: 5,
    completionTokens: 7,
    errorMessage: null,
    createdAt: "2026-08-18T10:00:00Z",
    ...overrides,
  };
}

test("a node with no results is pending, not missing", () => {
  const [a, b] = traceNodes(DAG, [result({ nodeId: "a" })]);
  assert.equal(a.status, "SUCCESS");
  // Driven by the graph, not the results. Omitting b would make a stalled run
  // look like a short one that finished.
  assert.equal(b.nodeId, "b");
  assert.equal(b.status, "PENDING");
  assert.equal(b.attempts, 0);
});

test("the latest result by time decides the node status", () => {
  const nodes = traceNodes(DAG, [
    result({ status: "FAILED", attempt: 2, createdAt: "2026-08-18T10:00:00Z" }),
    result({ status: "SUCCESS", attempt: 1, createdAt: "2026-08-18T10:05:00Z" }),
  ]);
  // Not by attempt: rows written before the retry fix restart at 1, so attempt
  // is not monotonic across the table. The success came later, so it wins.
  assert.equal(nodes[0].status, "SUCCESS");
  assert.equal(nodes[0].attempts, 2);
});

test("history is ordered oldest first", () => {
  const nodes = traceNodes(DAG, [
    result({ status: "SUCCESS", createdAt: "2026-08-18T10:05:00Z" }),
    result({ status: "FAILED", createdAt: "2026-08-18T10:00:00Z" }),
  ]);
  assert.deepEqual(
    nodes[0].history.map((r) => r.status),
    ["FAILED", "SUCCESS"],
  );
});

test("cost is summed across attempts, not taken from the last one", () => {
  const nodes = traceNodes(DAG, [
    result({ status: "FAILED", latencyMs: 300, promptTokens: 5, completionTokens: 0,
             createdAt: "2026-08-18T10:00:00Z" }),
    result({ status: "SUCCESS", latencyMs: 200, promptTokens: 5, completionTokens: 7,
             createdAt: "2026-08-18T10:01:00Z" }),
  ]);
  // A step that failed once before succeeding cost both calls. Reporting only
  // the successful one understates what the run spent.
  assert.equal(nodes[0].totalLatencyMs, 500);
  assert.equal(nodes[0].totalTokens, 17);
});

test("null latency and tokens do not poison the sums", () => {
  // A failed step records an error and no usage figures at all.
  const nodes = traceNodes(DAG, [
    result({ status: "FAILED", latencyMs: null, promptTokens: null, completionTokens: null }),
  ]);
  assert.equal(nodes[0].totalLatencyMs, 0);
  assert.equal(nodes[0].totalTokens, 0);
});

test("totals count steps that ran separately from steps in the graph", () => {
  const totals = traceTotals(traceNodes(DAG, [result({ nodeId: "a" })]));
  assert.deepEqual(totals, { executionMs: 100, tokens: 12, steps: 2, ran: 1 });
});

test("an empty graph totals to zero rather than throwing", () => {
  assert.deepEqual(traceTotals(traceNodes({}, [])), {
    executionMs: 0, tokens: 0, steps: 0, ran: 0,
  });
});

test("milliseconds switch to seconds above a second", () => {
  assert.equal(formatMs(340), "340ms");
  assert.equal(formatMs(2700), "2.7s");
});
