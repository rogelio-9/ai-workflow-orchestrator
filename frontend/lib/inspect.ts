import type { DagJson, DagNode } from "./layout";

/**
 * Turns a dag node into the rows the inspector shows.
 *
 * Kept out of the component because it is the part that can be wrong: which
 * keys count as configuration, what an absent value means, and what a node's
 * dependents are. Rendering a list of label/value pairs cannot be.
 */

export type Field = {
  label: string;
  value: string;
  /** True when the workflow says nothing and the backend applies a default. */
  inherited?: boolean;
};

/** Rendered above the generic config rows, in this order, when present. */
const PROMOTED: Record<string, string> = {
  model: "Model",
  prompt: "Prompt",
  url: "URL",
  provider: "Provider",
  temperature: "Temperature",
  max_tokens: "Max tokens",
};

function display(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function configFields(node: DagNode): Field[] {
  const config = node.config ?? {};
  const fields: Field[] = [];

  for (const [key, label] of Object.entries(PROMOTED)) {
    if (key in config) fields.push({ label, value: display(config[key]) });
  }

  // Anything the promoted list does not know about still has to appear -- a
  // config key that silently vanished from the panel would look like the
  // backend dropped it.
  for (const [key, value] of Object.entries(config)) {
    if (key in PROMOTED) continue;
    fields.push({ label: key, value: display(value) });
  }

  return fields;
}

export function retryFields(node: DagNode): Field[] {
  const policy = node.retry_policy;
  if (!policy || Object.keys(policy).length === 0) {
    // Not the same as "no retries": the worker has its own ladder. Saying
    // "default" rather than showing nothing keeps that distinction visible.
    return [{ label: "Policy", value: "worker default", inherited: true }];
  }
  return Object.entries(policy).map(([key, value]) => ({
    label: key,
    value: display(value),
  }));
}

/** Nodes that declare this one as a dependency. */
export function dependents(dag: DagJson, nodeId: string): string[] {
  return (dag.nodes ?? [])
    .filter((candidate) => (candidate.depends_on ?? []).includes(nodeId))
    .map((candidate) => candidate.id);
}

/** Dependencies that are not nodes in this graph. */
export function danglingDependencies(dag: DagJson, node: DagNode): string[] {
  const known = new Set((dag.nodes ?? []).map((candidate) => candidate.id));
  return (node.depends_on ?? []).filter((dependency) => !known.has(dependency));
}
