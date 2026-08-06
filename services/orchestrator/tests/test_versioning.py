"""Editing a workflow that has already run.

Before copy-on-write, PATCH deleted the steps rows and Postgres refused:
step_results held a foreign key to them. The refusal was correct -- the fix is
not to delete, so that a finished run keeps describing the graph it ran.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app
from app.models import Run, Step, Workflow

client = TestClient(app)

V1 = {"nodes": [{"id": "first", "type": "llm_call", "config": {"prompt": "v1"}}]}
V2 = {
    "nodes": [
        {"id": "first", "type": "llm_call", "config": {"prompt": "v2"}},
        {"id": "second", "type": "llm_call", "config": {}, "depends_on": ["first"]},
    ]
}


def _create(dag_json=V1):
    response = client.post(
        "/workflows",
        json={
            "name": f"version-{uuid.uuid4().hex[:8]}",
            "created_by": str(uuid.uuid4()),
            "dag_json": dag_json,
        },
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _run_and_record(workflow_id):
    """A completed run with a step_result -- the FK that used to block PATCH."""
    with SessionLocal() as db:
        workflow = db.get(Workflow, workflow_id)
        run = Run(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status="COMPLETE",
            input_vars={},
        )
        db.add(run)
        db.flush()
        step = (
            db.query(Step)
            .filter(Step.workflow_id == workflow.id, Step.version == workflow.version)
            .first()
        )
        db.execute(
            text(
                "INSERT INTO step_results (run_id, step_id, status, attempt) "
                "VALUES (:run, :step, 'SUCCESS', 1)"
            ),
            {"run": str(run.id), "step": str(step.id)},
        )
        db.commit()
        return run.id


def _patch(workflow_id, dag_json=V2):
    return client.patch(f"/workflows/{workflow_id}", json={"dag_json": dag_json})


def test_editing_a_workflow_that_has_run_succeeds():
    workflow_id = _create()
    _run_and_record(workflow_id)
    response = _patch(workflow_id)
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_the_old_steps_rows_survive_the_edit():
    workflow_id = _create()
    _run_and_record(workflow_id)
    _patch(workflow_id)

    with SessionLocal() as db:
        rows = {
            (step.version, step.node_id)
            for step in db.query(Step).filter(Step.workflow_id == workflow_id)
        }
    # v1's single node is still there alongside v2's two.
    assert rows == {(1, "first"), (2, "first"), (2, "second")}


def test_a_finished_run_still_resolves_to_the_graph_it_ran():
    workflow_id = _create()
    run_id = _run_and_record(workflow_id)
    _patch(workflow_id)

    with SessionLocal() as db:
        prompt = db.execute(
            text(
                """
                SELECT v.dag_json->'nodes'->0->'config'->>'prompt'
                FROM runs r
                JOIN workflow_versions v
                  ON v.workflow_id = r.workflow_id AND v.version = r.workflow_version
                WHERE r.id = :run_id
                """
            ),
            {"run_id": str(run_id)},
        ).scalar_one()
    # Not "v2": the workflow says v2 now, but this run did not execute that.
    assert prompt == "v1"


def test_a_new_run_pins_the_current_version():
    workflow_id = _create()
    _run_and_record(workflow_id)
    _patch(workflow_id)

    with SessionLocal() as db:
        workflow = db.get(Workflow, workflow_id)
        run = Run(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status="PENDING",
            input_vars={},
        )
        db.add(run)
        db.commit()
        assert run.workflow_version == 2


def test_editing_twice_keeps_every_version():
    workflow_id = _create()
    _patch(workflow_id)
    _patch(workflow_id, {"nodes": [{"id": "only", "type": "llm_call", "config": {}}]})

    with SessionLocal() as db:
        versions = [
            row[0]
            for row in db.execute(
                text(
                    "SELECT version FROM workflow_versions "
                    "WHERE workflow_id = :id ORDER BY version"
                ),
                {"id": str(workflow_id)},
            )
        ]
    assert versions == [1, 2, 3]


def test_step_ids_are_not_reused_across_versions():
    workflow_id = _create()
    _patch(workflow_id)

    with SessionLocal() as db:
        by_version = {}
        for step in db.query(Step).filter(
            Step.workflow_id == workflow_id, Step.node_id == "first"
        ):
            by_version[step.version] = step.id
    # Same node_id, different rows. step_results points at the row, which is
    # what keeps a trace attached to one version rather than to a name.
    assert by_version[1] != by_version[2]
