import { gql } from "@apollo/client";

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
