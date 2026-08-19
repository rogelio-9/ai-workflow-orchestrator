import type { Run } from "./queries";

/**
 * What the run history says about a run.
 *
 * Kept out of the component because these are claims that can be wrong -- how
 * long a run took, whether it can be retried, whether it still describes the
 * current graph. Laying out rows cannot be.
 */

/** Runs the orchestrator will still act on. */
export const TERMINAL_STATUSES = new Set(["COMPLETE", "FAILED"]);

export function isRunning(run: Run): boolean {
  return !TERMINAL_STATUSES.has(run.status);
}

/**
 * Only a failed run can be retried.
 *
 * The orchestrator answers 409 for anything else ("run has no failed steps to
 * retry"), so offering the button on a completed run promises something the
 * backend refuses.
 */
export function isRetryable(run: Run): boolean {
  return run.status === "FAILED";
}

/** True when this run executed a version of the graph that is no longer current. */
export function ranOlderVersion(run: Run, currentVersion: number): boolean {
  return run.workflowVersion !== currentVersion;
}

function formatSeconds(seconds: number): string {
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;

  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round(seconds % 60);
    return rest === 0 ? `${minutes}m` : `${minutes}m ${rest}s`;
  }

  // Longer spans roll up rather than accumulating minutes. A retried run keeps
  // its original started_at, so its span covers however long it sat failed
  // before someone pressed the button -- rendering that as "5589m 52s" is
  // arithmetically true and completely unreadable.
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.round((seconds % 3600) / 60);
    return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
  }

  const days = Math.floor(seconds / 86400);
  const hours = Math.round((seconds % 86400) / 3600);
  return hours === 0 ? `${days}d` : `${days}d ${hours}h`;
}

/**
 * How long the run took, or has been going.
 *
 * This is wall-clock span, not time spent executing. A retry clears ended_at
 * and keeps the original started_at, so a run retried days later legitimately
 * spans those days. Actual execution time has to come from the step results,
 * which is the trace viewer's job.
 *
 * `now` is a parameter rather than a call to Date.now() so the elapsed branch
 * is testable; a function that reads the clock internally can only be asserted
 * against itself.
 */
export function duration(run: Run, now: number = Date.now()): string {
  if (!run.startedAt) return "—";
  const started = new Date(run.startedAt).getTime();

  if (!run.endedAt) {
    // A run with no end is either still going or was abandoned mid-flight.
    // Either way the honest figure is time since it started, not a blank.
    return `${formatSeconds((now - started) / 1000)} so far`;
  }

  return formatSeconds((new Date(run.endedAt).getTime() - started) / 1000);
}

export type RunTally = { total: number; failed: number; running: number };

export function tally(runs: Run[]): RunTally {
  return {
    total: runs.length,
    failed: runs.filter((run) => run.status === "FAILED").length,
    running: runs.filter(isRunning).length,
  };
}
