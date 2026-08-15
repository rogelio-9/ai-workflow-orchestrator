import assert from "node:assert/strict";
import { test } from "node:test";
import {
  configFields,
  danglingDependencies,
  dependents,
  retryFields,
} from "../inspect.ts";
import type { DagJson } from "../layout.ts";

const DAG: DagJson = {
  nodes: [
    { id: "fetch", type: "tool_call", config: { url: "https://example.com" } },
    { id: "left", type: "llm_call", config: {}, depends_on: ["fetch"] },
    { id: "right", type: "llm_call", config: {}, depends_on: ["fetch"] },
    { id: "join", type: "llm_call", config: {}, depends_on: ["left", "right"] },
  ],
};

function labels(fields: { label: string }[]) {
  return fields.map((field) => field.label);
}

test("promoted config keys come first, in a fixed order", () => {
  const fields = configFields({
    id: "a",
    config: { temperature: 0.2, prompt: "hi", model: "mock:echo" },
  });
  // Not object insertion order: the panel should read the same way for every
  // node regardless of how the JSON happened to be written.
  assert.deepEqual(labels(fields), ["Model", "Prompt", "Temperature"]);
});

test("unrecognised config keys still appear", () => {
  const fields = configFields({ id: "a", config: { model: "m", weird_knob: 3 } });
  // A key that silently vanished from the panel would look like the backend
  // dropped it.
  assert.deepEqual(labels(fields), ["Model", "weird_knob"]);
});

test("temperature zero is shown, not treated as absent", () => {
  const fields = configFields({ id: "a", config: { temperature: 0 } });
  // The same explicit-presence trap the proto hit: 0 is a real setting.
  assert.equal(fields.length, 1);
  assert.equal(fields[0].value, "0");
});

test("non-string values are rendered as json rather than [object Object]", () => {
  const fields = configFields({ id: "a", config: { tools: ["search", "fetch"] } });
  assert.equal(fields[0].value, '["search","fetch"]');
});

test("a node with no config yields no rows", () => {
  assert.deepEqual(configFields({ id: "a" }), []);
});

test("an absent retry policy reads as the worker default, marked inherited", () => {
  const [field] = retryFields({ id: "a" });
  // "No retries" and "the worker's own ladder applies" are different claims,
  // and only one of them is true.
  assert.equal(field.value, "worker default");
  assert.equal(field.inherited, true);
});

test("an empty retry policy object is also the default", () => {
  assert.equal(retryFields({ id: "a", retry_policy: {} })[0].inherited, true);
});

test("an explicit retry policy is listed field by field", () => {
  const fields = retryFields({ id: "a", retry_policy: { max_attempts: 5 } });
  assert.deepEqual(labels(fields), ["max_attempts"]);
  assert.equal(fields[0].inherited, undefined);
});

test("dependents are the nodes that name this one", () => {
  assert.deepEqual(dependents(DAG, "fetch"), ["left", "right"]);
  assert.deepEqual(dependents(DAG, "join"), []);
});

test("dangling dependencies are those with no matching node", () => {
  const node = { id: "orphan", depends_on: ["fetch", "ghost"] };
  assert.deepEqual(danglingDependencies({ ...DAG, nodes: [...DAG.nodes!, node] }, node), [
    "ghost",
  ]);
});

test("a node with no dependencies has none dangling", () => {
  assert.deepEqual(danglingDependencies(DAG, DAG.nodes![0]), []);
});
