"use client";

import { useMutation } from "@apollo/client/react";
import { RUN_WORKFLOW, WORKFLOW } from "@/lib/queries";

export function RunButton({ workflowId }: { workflowId: string }) {
  const [run, { loading, error, data }] = useMutation<{
    runWorkflow: { id: string; status: string };
  }>(RUN_WORKFLOW, {
    variables: { id: workflowId },
    // The new run has to appear in the history without a manual reload, and
    // refetching is honest about where the truth is: the run's status is
    // decided by the workers, so writing an optimistic one here would be a
    // guess that is wrong within a second.
    refetchQueries: [{ query: WORKFLOW, variables: { id: workflowId } }],
  });

  return (
    <div className="run-control">
      <button onClick={() => run()} disabled={loading} className="button">
        {loading ? "Starting…" : "Run workflow"}
      </button>
      {data && (
        <span className="muted">
          started {data.runWorkflow.id.slice(0, 8)} · {data.runWorkflow.status}
        </span>
      )}
      {error && <span className="warn">{error.message}</span>}
    </div>
  );
}
