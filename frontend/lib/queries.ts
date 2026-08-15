import { gql } from "@apollo/client";
import type { DagNode } from "./layout";

export const WORKFLOWS = gql`
  query Workflows {
    workflows {
      id
      name
      version
      updatedAt
      runs {
        id
        status
        workflowVersion
        startedAt
      }
    }
  }
`;

export type Run = {
  id: string;
  status: string;
  workflowVersion: number;
  startedAt: string | null;
};

export type WorkflowSummary = {
  id: string;
  name: string;
  version: number;
  updatedAt: string | null;
  runs: Run[];
};

export const WORKFLOW = gql`
  query Workflow($id: UUID!) {
    workflow(id: $id) {
      id
      name
      version
      dagJson
      updatedAt
      runs {
        id
        status
        workflowVersion
        startedAt
      }
    }
  }
`;

export type WorkflowDetail = WorkflowSummary & {
  dagJson: { nodes?: DagNode[] };
};

export const RUN_WORKFLOW = gql`
  mutation RunWorkflow($id: UUID!) {
    runWorkflow(workflowId: $id) {
      id
      status
    }
  }
`;
