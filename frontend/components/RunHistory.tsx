"use client";

import Link from "next/link";
import { useMutation } from "@apollo/client/react";
import { RETRY_RUN, WORKFLOW, type Run } from "@/lib/queries";
import { duration, isRetryable, isRunning, ranOlderVersion, tally } from "@/lib/runs";

function RetryButton({ runId, workflowId }: { runId: string; workflowId: string }) {
  const [retry, { loading, error }] = useMutation(RETRY_RUN, {
    variables: { id: runId },
    // Retrying resumes this run rather than creating a new one, so the row
    // itself changes; refetching the workflow is what redraws it.
    refetchQueries: [{ query: WORKFLOW, variables: { id: workflowId } }],
  });

  return (
    <>
      <button className="button button-quiet" onClick={() => retry()} disabled={loading}>
        {loading ? "Retrying…" : "Retry"}
      </button>
      {error && <span className="warn">{error.message}</span>}
    </>
  );
}

export function RunHistory({
  runs,
  workflowId,
  currentVersion,
}: {
  runs: Run[];
  workflowId: string;
  currentVersion: number;
}) {
  const counts = tally(runs);

  if (counts.total === 0) {
    return (
      <section className="history">
        <h2>Runs</h2>
        <p className="muted">This workflow has not been run yet.</p>
      </section>
    );
  }

  return (
    <section className="history">
      <h2>Runs</h2>
      <p className="muted">
        {counts.total} total
        {counts.failed > 0 && ` · ${counts.failed} failed`}
        {counts.running > 0 && ` · ${counts.running} in flight`}
      </p>

      <ol className="run-list">
        {runs.map((run) => {
          const stale = ranOlderVersion(run, currentVersion);
          return (
            <li key={run.id} className="run-row">
              <span className="badge" data-status={run.status}>
                {run.status}
              </span>

              {/* The id is the handle for correlating with worker logs, so it
                  is shown rather than hidden behind the row being clickable. */}
              <Link className="run-id" href={`/runs/${run.id}`}>
                {run.id.slice(0, 8)}
              </Link>

              <span className="muted">
                {new Date(run.startedAt ?? "").toLocaleString()}
              </span>

              <span className="muted" data-live={isRunning(run) || undefined}>
                {duration(run)}
              </span>

              {/* Only flagged when it differs. Labelling every run with its
                  version makes the one that matters harder to notice. */}
              <span className="badge" data-muted={!stale || undefined}>
                v{run.workflowVersion}
                {stale && " · older graph"}
              </span>

              <span className="run-actions">
                {isRetryable(run) && (
                  <RetryButton runId={run.id} workflowId={workflowId} />
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
