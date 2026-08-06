"use client";

import { useQuery } from "@apollo/client/react";
import { WORKFLOWS, type WorkflowSummary } from "@/lib/queries";

function relative(iso: string | null): string {
  if (!iso) return "never";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function WorkflowsPage() {
  const { data, loading, error } = useQuery<{ workflows: WorkflowSummary[] }>(WORKFLOWS);

  if (loading) return <p className="state">Loading workflows…</p>;

  if (error) {
    return (
      <div className="state" data-kind="error">
        <strong>Could not load workflows.</strong>
        <p className="muted">{error.message}</p>
      </div>
    );
  }

  const workflows = data?.workflows ?? [];

  if (workflows.length === 0) {
    return (
      <div className="state">
        <strong>No workflows yet.</strong>
        <p className="muted">Create one through the orchestrator API to see it here.</p>
      </div>
    );
  }

  return (
    <>
      <h1>Workflows</h1>
      <p className="muted">{workflows.length} owned by you</p>

      <ul className="workflow-list">
        {workflows.map((workflow) => {
          // Runs arrive newest first from the gateway, so the head is the
          // latest -- and it may have executed an older version of the graph.
          const latest = workflow.runs[0];
          return (
            <li key={workflow.id} className="workflow-card">
              <div>
                <h2>{workflow.name}</h2>
                <p className="muted">
                  {workflow.runs.length} run{workflow.runs.length === 1 ? "" : "s"}
                  {latest ? ` · last ${relative(latest.startedAt)}` : ""}
                  {" · edited "}
                  {relative(workflow.updatedAt)}
                </p>
              </div>
              <div className="badges">
                <span className="badge">v{workflow.version}</span>
                {latest && (
                  <span className="badge" data-status={latest.status}>
                    {latest.status}
                    {/* A run pinned to an older version ran a different graph
                        than the one this card links to. Saying so here avoids
                        the trace looking wrong later. */}
                    {latest.workflowVersion !== workflow.version
                      ? ` on v${latest.workflowVersion}`
                      : ""}
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}
