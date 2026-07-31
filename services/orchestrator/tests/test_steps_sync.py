import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Step

client = TestClient(app)

DIAMOND = {
    "nodes": [
        {"id": "fetch", "type": "tool_call", "config": {"url": "x"}},
        {"id": "left", "type": "llm_call", "config": {}, "depends_on": ["fetch"]},
        {"id": "right", "type": "llm_call", "config": {}, "depends_on": ["fetch"]},
        {"id": "join", "type": "llm_call", "config": {}, "depends_on": ["left", "right"]},
    ]
}


def _create(dag_json):
    response = client.post(
        "/workflows",
        json={
            "name": "sync-test",
            "created_by": str(uuid.uuid4()),
            "dag_json": dag_json,
        },
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _steps(workflow_id):
    with SessionLocal() as db:
        return {s.node_id: s for s in db.query(Step).filter(Step.workflow_id == workflow_id)}


def test_creating_a_workflow_materializes_one_step_per_node():
    steps = _steps(_create(DIAMOND))
    assert set(steps) == {"fetch", "left", "right", "join"}


def test_depends_on_holds_step_uuids_not_node_ids():
    steps = _steps(_create(DIAMOND))
    # The column is uuid[]; resolving it requires every row to have an id
    # before any row is built, which is why sync_steps assigns them up front.
    assert steps["join"].depends_on == [steps["left"].id, steps["right"].id]
    assert steps["fetch"].depends_on == []


def test_step_order_follows_topological_order():
    steps = _steps(_create(DIAMOND))
    assert steps["fetch"].step_order < steps["left"].step_order
    assert steps["left"].step_order < steps["join"].step_order


def test_patching_the_graph_resyncs_the_rows():
    workflow_id = _create(DIAMOND)
    response = client.patch(
        f"/workflows/{workflow_id}",
        json={"dag_json": {"nodes": [{"id": "only", "type": "llm_call", "config": {}}]}},
    )
    assert response.status_code == 200
    assert set(_steps(workflow_id)) == {"only"}


def test_same_node_id_allowed_across_different_workflows():
    # The unique constraint is (workflow_id, node_id) -- "summarize" is not
    # reserved globally.
    first, second = _create(DIAMOND), _create(DIAMOND)
    assert _steps(first)["fetch"].id != _steps(second)["fetch"].id
