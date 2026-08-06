import assert from "node:assert/strict";
import { test } from "node:test";
import { layoutDag, type DagJson } from "../layout.ts";

const DIAMOND: DagJson = {
  nodes: [
    { id: "fetch", type: "tool_call" },
    { id: "left", type: "llm_call", depends_on: ["fetch"] },
    { id: "right", type: "llm_call", depends_on: ["fetch"] },
    { id: "join", type: "llm_call", depends_on: ["left", "right"] },
  ],
};

function byId(nodes: ReturnType<typeof layoutDag>["nodes"]) {
  return Object.fromEntries(nodes.map((node) => [node.id, node]));
}

test("every dag node becomes a canvas node", () => {
  const { nodes } = layoutDag(DIAMOND);
  assert.deepEqual(
    nodes.map((node) => node.id).sort(),
    ["fetch", "join", "left", "right"],
  );
});

test("one edge per dependency, pointing dependency -> dependent", () => {
  const { edges } = layoutDag(DIAMOND);
  assert.deepEqual(
    edges.map((edge) => `${edge.source}->${edge.target}`).sort(),
    ["fetch->left", "fetch->right", "left->join", "right->join"],
  );
});

test("dependencies are laid out to the left of their dependents", () => {
  const nodes = byId(layoutDag(DIAMOND).nodes);
  // rankdir LR: this is what makes the graph read as execution order rather
  // than as an arbitrary cloud of boxes.
  assert.ok(nodes.fetch.position.x < nodes.left.position.x);
  assert.ok(nodes.left.position.x < nodes.join.position.x);
});

test("siblings are separated vertically, not stacked", () => {
  const nodes = byId(layoutDag(DIAMOND).nodes);
  assert.notEqual(nodes.left.position.y, nodes.right.position.y);
});

test("a dependency on a node that does not exist is dropped", () => {
  // dagre would otherwise invent the missing node and render it as an empty
  // box, which reads as a bug in the canvas rather than in the workflow.
  const { nodes, edges } = layoutDag({
    nodes: [{ id: "only", type: "llm_call", depends_on: ["ghost"] }],
  });
  assert.equal(nodes.length, 1);
  assert.deepEqual(edges, []);
});

test("an empty dag produces nothing rather than throwing", () => {
  assert.deepEqual(layoutDag({}), { nodes: [], edges: [] });
  assert.deepEqual(layoutDag({ nodes: [] }), { nodes: [], edges: [] });
});

test("node type falls back to llm_call and carries the model through", () => {
  const { nodes } = layoutDag({
    nodes: [{ id: "a", config: { model: "gemini-flash-lite-latest" } }],
  });
  assert.equal(nodes[0].data.kind, "llm_call");
  assert.equal(nodes[0].data.model, "gemini-flash-lite-latest");
});
