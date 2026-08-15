"use client";

import {
  configFields,
  danglingDependencies,
  dependents,
  retryFields,
} from "@/lib/inspect";
import { KIND_COLORS, DEFAULT_KIND_COLOR, type DagJson, type DagNode } from "@/lib/layout";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="inspector-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Fields({ fields }: { fields: { label: string; value: string; inherited?: boolean }[] }) {
  if (fields.length === 0) return <p className="muted">None.</p>;
  return (
    <dl className="fields">
      {fields.map((field) => (
        <div key={field.label} className="field">
          <dt>{field.label}</dt>
          <dd data-inherited={field.inherited ? "true" : undefined}>{field.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function NodeInspector({ node, dag }: { node: DagNode | null; dag: DagJson }) {
  if (!node) {
    return (
      <aside className="inspector">
        <p className="muted">Select a step to inspect its configuration.</p>
      </aside>
    );
  }

  const kind = node.type ?? "llm_call";
  const downstream = dependents(dag, node.id);
  const dangling = danglingDependencies(dag, node);
  const upstream = node.depends_on ?? [];

  return (
    <aside className="inspector">
      <header className="inspector-header">
        <span
          className="inspector-swatch"
          style={{ background: KIND_COLORS[kind] ?? DEFAULT_KIND_COLOR }}
        />
        <div>
          <div className="inspector-kind">{kind}</div>
          <h2>{node.id}</h2>
        </div>
      </header>

      <Section title="Configuration">
        <Fields fields={configFields(node)} />
      </Section>

      <Section title="Retries">
        <Fields fields={retryFields(node)} />
      </Section>

      <Section title="Dependencies">
        {upstream.length === 0 ? (
          <p className="muted">None — this step starts the run.</p>
        ) : (
          <ul className="chips">
            {upstream.map((id) => (
              <li key={id} className="chip" data-dangling={dangling.includes(id) || undefined}>
                {id}
                {dangling.includes(id) && " · missing"}
              </li>
            ))}
          </ul>
        )}
        {dangling.length > 0 && (
          <p className="muted warn">
            {dangling.length === 1 ? "This dependency is" : "These dependencies are"} not a
            step in this workflow, so {dangling.length === 1 ? "it is" : "they are"} ignored
            when the graph is laid out and executed.
          </p>
        )}
      </Section>

      <Section title="Dependents">
        {downstream.length === 0 ? (
          <p className="muted">None — nothing waits on this step.</p>
        ) : (
          <ul className="chips">
            {downstream.map((id) => (
              <li key={id} className="chip">
                {id}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </aside>
  );
}
