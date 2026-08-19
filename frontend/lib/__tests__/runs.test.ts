import assert from "node:assert/strict";
import { test } from "node:test";
import {
  duration,
  isRetryable,
  isRunning,
  ranOlderVersion,
  tally,
} from "../runs.ts";
import type { Run } from "../queries.ts";

function run(overrides: Partial<Run> = {}): Run {
  return {
    id: "r1",
    status: "COMPLETE",
    workflowVersion: 1,
    startedAt: "2026-08-18T10:00:00Z",
    endedAt: "2026-08-18T10:00:12Z",
    ...overrides,
  };
}

test("duration is the span between start and end", () => {
  assert.equal(duration(run()), "12s");
});

test("durations over a minute read as minutes and seconds", () => {
  assert.equal(
    duration(run({ endedAt: "2026-08-18T10:01:30Z" })),
    "1m 30s",
  );
  assert.equal(duration(run({ endedAt: "2026-08-18T10:02:00Z" })), "2m");
});

test("sub-second runs do not render as 0s", () => {
  // The mock provider finishes in milliseconds; "0s" reads as "did not run".
  assert.equal(duration(run({ endedAt: "2026-08-18T10:00:00.4Z" })), "<1s");
});

test("a run with no end reports time elapsed, not a blank", () => {
  const now = new Date("2026-08-18T10:00:05Z").getTime();
  // Either still going or abandoned mid-flight. Both are more informative
  // than an em dash, which reads as "no information".
  assert.equal(duration(run({ endedAt: null }), now), "5s so far");
});

test("a run that never started has nothing to report", () => {
  assert.equal(duration(run({ startedAt: null })), "—");
});

test("only failed runs are retryable", () => {
  // The orchestrator answers 409 for anything else, so offering the button
  // elsewhere promises what the backend refuses.
  assert.equal(isRetryable(run({ status: "FAILED" })), true);
  assert.equal(isRetryable(run({ status: "COMPLETE" })), false);
  assert.equal(isRetryable(run({ status: "RUNNING" })), false);
});

test("anything not terminal counts as running", () => {
  assert.equal(isRunning(run({ status: "PENDING" })), true);
  assert.equal(isRunning(run({ status: "RUNNING" })), true);
  assert.equal(isRunning(run({ status: "COMPLETE" })), false);
  assert.equal(isRunning(run({ status: "FAILED" })), false);
});

test("a run is stale when it executed a version that is no longer current", () => {
  assert.equal(ranOlderVersion(run({ workflowVersion: 1 }), 2), true);
  assert.equal(ranOlderVersion(run({ workflowVersion: 2 }), 2), false);
});

test("the tally counts failures and in-flight runs separately", () => {
  const counts = tally([
    run({ status: "COMPLETE" }),
    run({ status: "FAILED" }),
    run({ status: "FAILED" }),
    run({ status: "RUNNING" }),
  ]);
  assert.deepEqual(counts, { total: 4, failed: 2, running: 1 });
});

test("an empty history tallies to zero rather than throwing", () => {
  assert.deepEqual(tally([]), { total: 0, failed: 0, running: 0 });
});

test("spans over an hour roll up instead of accumulating minutes", () => {
  // A retried run keeps its original started_at, so this is reachable with
  // ordinary data -- it rendered as "5589m 52s" against the live database.
  assert.equal(duration(run({ endedAt: "2026-08-18T13:30:00Z" })), "3h 30m");
  assert.equal(duration(run({ endedAt: "2026-08-18T12:00:00Z" })), "2h");
});

test("spans over a day roll up to days", () => {
  assert.equal(duration(run({ endedAt: "2026-08-22T07:00:00Z" })), "3d 21h");
  assert.equal(duration(run({ endedAt: "2026-08-20T10:00:00Z" })), "2d");
});
