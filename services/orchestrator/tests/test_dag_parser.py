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

def test_a_dependency_on_an_unknown_node_is_rejected():
    from app.dag_parser import UnknownDependency

    with pytest.raises(UnknownDependency) as exc:
        topological_sort({"nodes": [{"id": "a", "depends_on": ["ghost"]}]})
    # Without the explicit check this surfaced as a cycle error: the dangling
    # dependency keeps the in-degree above zero forever, so the cycle branch
    # fires with a true failure and a false explanation.
    assert "ghost" in str(exc.value)


def test_duplicate_node_ids_are_rejected():
    from app.dag_parser import DuplicateNodeId

    # The dict comprehensions collapse duplicates silently, so one of the two
    # nodes would simply never run and nothing would say so.
    with pytest.raises(DuplicateNodeId):
        topological_sort({"nodes": [{"id": "a"}, {"id": "a"}]})


def test_a_valid_graph_still_sorts():
    order = topological_sort(
        {"nodes": [{"id": "b", "depends_on": ["a"]}, {"id": "a"}]}
    )
    assert order == ["a", "b"]
