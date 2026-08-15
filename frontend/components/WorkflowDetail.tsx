"use client";

import Link from "next/link";
import { useQuery } from "@apollo/client/react";
import { WORKFLOW, type WorkflowDetail as Detail } from "@/lib/queries";
import { RunButton } from "./RunButton";
import { WorkflowCanvas } from "./WorkflowCanvas";

export function WorkflowDetail({ id }: { id: string }) {
  const { data, loading, error } = useQuery<{ workflow: Detail | null }>(WORKFLOW, {
    variables: { id },
  });

  if (loading) return <p className="state">Loading workflow…</p>;

  if (error) {
    return (
      <div className="state" data-kind="error">
        <strong>Could not load this workflow.</strong>
        <p className="muted">{error.message}</p>
      </div>
    );
  }

  const workflow = data?.workflow;

  if (!workflow) {
    // The gateway returns null for a workflow you do not own as well as for
    // one that does not exist -- saying "forbidden" here would confirm it is
    // real, which is the disclosure the null was chosen to avoid.
    return (
      <div className="state">
        <strong>Not found.</strong>
        <p className="muted">
          No workflow with that id is available to you. <Link href="/">Back to the list</Link>
        </p>
      </div>
    );
  }

  const stale = workflow.runs.filter((run) => run.workflowVersion !== workflow.version);

  return (
    <>
      <p className="muted">
        <Link href="/">← Workflows</Link>
      </p>
      <div className="detail-heading">
        <h1>{workflow.name}</h1>
        <RunButton workflowId={workflow.id} />
      </div>
      <p className="muted">
        v{workflow.version} · {workflow.runs.length} run
        {workflow.runs.length === 1 ? "" : "s"}
        {stale.length > 0 && ` · ${stale.length} ran an earlier version`}
      </p>

      <WorkflowCanvas dag={workflow.dagJson} />
    </>
  );
}
