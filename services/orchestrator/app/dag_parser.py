from collections import deque
from typing import Any


class InvalidDag(Exception):
    """The graph cannot be executed as written. Distinct exception types rather
    than one message, so callers can map them without string-matching."""


class CycleError(InvalidDag):
    """The execution engine catches this to fail a run fast; a bare ValueError
    would force it to string-match the message."""


class UnknownDependency(InvalidDag):
    """A depends_on names an id that is not a node in this graph."""


class DuplicateNodeId(InvalidDag):
    """Two nodes share an id."""


def validate(dag_json: dict[str, Any]) -> None:
    """Reject graphs that would fail confusingly further down.

    Both checks guard against silence rather than crashes. A duplicate id is
    swallowed by the dict comprehensions below, so one of the two nodes simply
    disappears from the run with nothing logged. A dangling dependency leaves
    its dependent's in-degree permanently above zero, which the cycle check
    then reports as a cycle -- a true failure with a false explanation.
    """
    nodes = dag_json.get("nodes", [])

    seen: set[str] = set()
    for node in nodes:
        if node["id"] in seen:
            raise DuplicateNodeId(f"duplicate node id {node['id']!r}")
        seen.add(node["id"])

    for node in nodes:
        for dep in node.get("depends_on") or []:
            if dep not in seen:
                raise UnknownDependency(
                    f"node {node['id']!r} depends on {dep!r}, which is not a node "
                    "in this workflow"
                )


def topological_sort(dag_json: dict[str, Any]) -> list[str]:
    validate(dag_json)

    nodes = dag_json.get("nodes", [])

    in_degree: dict[str, int] = {n["id"]: len(n.get("depends_on", [])) for n in nodes}
    dependents: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for n in nodes:
        for dep in n.get("depends_on", []):
            dependents[dep].append(n["id"])

    queue = deque(node_id for node_id, deg in in_degree.items() if deg == 0)

    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # A node still carrying in-degree was never freed, which can only happen
    # if it sits in a dependency cycle.
    if len(order) != len(in_degree):
        raise CycleError("dag contains a cycle; no valid topological ordering exists")

    return order

def ready_steps(dag_json: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in dag_json.get("nodes", []) if not n.get("depends_on")]