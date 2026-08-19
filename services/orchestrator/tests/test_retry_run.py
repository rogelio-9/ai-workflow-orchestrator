import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app
from app.models import Run, Step, Workflow
from app.retry_run import failed_nodes

client = TestClient(app)

DAG = {
    "nodes": [
        {"id": "first", "type": "llm_call", "config": {"model": "mock:echo"}},
        {
            "id": "second",
            "type": "llm_call",
            "depends_on": ["first"],
            "config": {"model": "mock:echo"},
        },
    ]
}


@pytest.fixture
def run_with_steps():
    """A workflow, its steps rows, and a run -- built directly so the fixture
    does not depend on Kafka being up."""
    with SessionLocal() as db:
        workflow = Workflow(
            name=f"retry-test-{uuid.uuid4().hex[:8]}",
            created_by=uuid.uuid4(),
            dag_json=DAG,
        )
        db.add(workflow)
        db.flush()

        from app.steps import sync_steps

        sync_steps(db, workflow)

        run = Run(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status="FAILED",
            input_vars={},
        )
        db.add(run)
        db.commit()

        steps = {
            step.node_id: step.id
            for step in db.query(Step).filter(Step.workflow_id == workflow.id)
        }
        yield run.id, steps


def record(run_id, step_id, status, attempt):
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO step_results (run_id, step_id, status, attempt)
                VALUES (:run_id, :step_id, :status, :attempt)
                """
            ),
            {
                "run_id": str(run_id),
                "step_id": str(step_id),
                "status": status,
                "attempt": attempt,
            },
        )
        db.commit()


def test_only_the_latest_attempt_decides(run_with_steps):
    run_id, steps = run_with_steps
    # Failed twice, then succeeded. A node that eventually worked is not a
    # candidate for retry, however many attempts it burned getting there.
    record(run_id, steps["first"], "RETRYING", 1)
    record(run_id, steps["first"], "RETRYING", 2)
    record(run_id, steps["first"], "SUCCESS", 3)

    with SessionLocal() as db:
        assert failed_nodes(db, run_id) == []


def test_node_whose_latest_attempt_failed_is_returned(run_with_steps):
    run_id, steps = run_with_steps
    record(run_id, steps["first"], "SUCCESS", 1)
    record(run_id, steps["second"], "RETRYING", 1)
    record(run_id, steps["second"], "FAILED", 2)

    with SessionLocal() as db:
        assert failed_nodes(db, run_id) == ["second"]


def test_retry_with_nothing_failed_is_a_conflict(run_with_steps):
    run_id, steps = run_with_steps
    record(run_id, steps["first"], "SUCCESS", 1)
    record(run_id, steps["second"], "SUCCESS", 1)

    response = client.post(f"/runs/{run_id}/retry")
    # 409 rather than a quiet 200: the caller asked to resume work that does
    # not exist.
    assert response.status_code == 409
    assert "no failed steps" in response.json()["detail"]


def test_retry_of_an_unknown_run_is_404():
    assert client.post(f"/runs/{uuid.uuid4()}/retry").status_code == 404


def test_retry_of_a_node_not_in_the_graph_is_400(run_with_steps):
    run_id, _ = run_with_steps
    response = client.post(f"/runs/{run_id}/retry", params={"from_node_id": "ghost"})
    assert response.status_code == 400
    assert "ghost" in response.json()["detail"]


def test_a_retry_that_succeeds_clears_the_node(run_with_steps):
    run_id, steps = run_with_steps
    # The worker's own ladder: two attempts inside one delivery, then failure.
    record(run_id, steps["first"], "RETRYING", 1)
    record(run_id, steps["first"], "FAILED", 2)
    with SessionLocal() as db:
        assert failed_nodes(db, run_id) == ["first"]

    # A user-initiated retry, which restarts the attempt count. Ordering by
    # attempt sorted this success underneath the attempt-2 failure, so the node
    # stayed failed and every later retry re-ran a step that had worked.
    record(run_id, steps["first"], "SUCCESS", 1)
    with SessionLocal() as db:
        assert failed_nodes(db, run_id) == []


def test_a_republished_step_continues_the_attempt_count(run_with_steps):
    from app.retry_run import next_attempt

    run_id, steps = run_with_steps
    record(run_id, steps["first"], "RETRYING", 1)
    record(run_id, steps["first"], "FAILED", 2)

    with SessionLocal() as db:
        attempts = next_attempt(db, run_id, {"first": str(steps["first"])})
    # Not 1: two rows both labelled "attempt 1" are indistinguishable in a
    # trace, and the count is the only record of what the step cost.
    assert attempts["first"] == 3


def test_a_step_with_no_results_starts_at_one(run_with_steps):
    from app.retry_run import next_attempt

    run_id, steps = run_with_steps
    with SessionLocal() as db:
        attempts = next_attempt(db, run_id, {"second": str(steps["second"])})
    assert attempts["second"] == 1
