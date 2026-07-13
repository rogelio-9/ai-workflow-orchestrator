from typing import Any


def topological_sort(dag_json: dict[str, Any]) -> list[str]:
    # Real implementation will order nodes so every node follows its
    # dependencies (Kahn's algorithm over the edges). Stubbed until the
    # execution engine needs a true ordering.
    return [node["id"] for node in dag_json.get("nodes", [])]
