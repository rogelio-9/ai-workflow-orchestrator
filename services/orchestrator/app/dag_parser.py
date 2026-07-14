from collections import deque
from typing import Any


class CycleError(Exception):
    """The execution engine catches this to fail a run fast; a bare ValueError
    would force it to string-match the message."""


def topological_sort(dag_json: dict[str, Any]) -> list[str]:
    nodes = dag_json.get("nodes", [])

    in_degree: dict[str, int] = {n["id"]: len(n.get("depends_on", [])) for n in nodes}
    dependents: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for n in nodes:
        # TODO(validation): a depends_on id not present in nodes raises a raw
        # KeyError here; convert to an explicit validation error when the API
        # ingests untrusted DAG JSON.
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