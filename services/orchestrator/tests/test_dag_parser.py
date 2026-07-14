import pytest

from app.dag_parser import CycleError, topological_sort


def assert_valid_order(dag: dict, order: list[str]) -> None:
    """A topological order is correct if every node appears after all of its
    dependencies. Asserting this invariant, rather than an exact sequence,
    keeps branching/parallel tests from breaking when tie-break order changes."""
    position = {node_id: i for i, node_id in enumerate(order)}
    for node in dag["nodes"]:
        for dep in node.get("depends_on", []):
            assert position[dep] < position[node["id"]]


def test_linear_dag():
    dag = {
        "nodes": [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": ["b"]},
        ]
    }
    assert topological_sort(dag) == ["a", "b", "c"]


def test_branching_dag():
    dag = {
        "nodes": [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": ["a"]},
            {"id": "d", "depends_on": ["b", "c"]},
        ]
    }
    order = topological_sort(dag)
    assert_valid_order(dag, order)
    assert set(order) == {"a", "b", "c", "d"}


def test_parallel_dag():
    dag = {
        "nodes": [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": []},
            {"id": "d", "depends_on": ["c"]},
        ]
    }
    order = topological_sort(dag)
    assert_valid_order(dag, order)
    assert set(order) == {"a", "b", "c", "d"}


def test_cycle_raises():
    dag = {
        "nodes": [
            {"id": "x", "depends_on": ["y"]},
            {"id": "y", "depends_on": ["x"]},
        ]
    }
    with pytest.raises(CycleError):
        topological_sort(dag)