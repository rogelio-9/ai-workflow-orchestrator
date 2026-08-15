"""Ownership on the write path.

The read path was scoped in session 25; the mutations were not, and a caller
who could not read a workflow could still run it. Running someone else's
workflow spends their LLM budget and writes rows into their run history, so
these assert the same isolation the read tests do -- for writes.

The orchestrator is never reached in these tests: every case must be refused
before the HTTP call, so a failure here shows up as an unexpected success
rather than a connection error.
"""

import uuid

import pytest
from sqlalchemy import text

from app.db import engine
from app.loaders import build_loaders
from app import mutations
from app.ratelimit import UserRateLimiter
from app.schema import schema


@pytest.fixture(autouse=True)
def _requires_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("postgres not running")


@pytest.fixture
def alice_and_bob():
    """A workflow and a run owned by alice; bob owns nothing."""
    alice, bob = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        workflow_id = conn.execute(
            text(
                """
                INSERT INTO workflows (name, created_by, dag_json)
                VALUES (:name, :owner, '{"nodes": []}') RETURNING id
                """
            ),
            {"name": f"mut-{uuid.uuid4().hex[:6]}", "owner": alice},
        ).scalar_one()
        run_id = conn.execute(
            text(
                "INSERT INTO runs (workflow_id, workflow_version, status) "
                "VALUES (:wf, 1, 'FAILED') RETURNING id"
            ),
            {"wf": str(workflow_id)},
        ).scalar_one()
    return {"alice": alice, "bob": bob, "workflow": workflow_id, "run": run_id}


async def mutate(document: str, user_id: str, **variables):
    return await schema.execute(
        document,
        variable_values=variables or None,
        context_value={
            "loaders": build_loaders(),
            "user_id": user_id,
            "limiter": UserRateLimiter(),
        },
    )


RUN = "mutation ($id: UUID!) { runWorkflow(workflowId: $id) { id } }"
RETRY = "mutation ($id: UUID!) { retryRun(runId: $id) { id } }"
UPDATE = """
mutation ($id: UUID!) {
  updateWorkflow(id: $id, name: "renamed-by-bob") { id version }
}
"""


async def test_running_someone_elses_workflow_is_refused(alice_and_bob):
    result = await mutate(RUN, alice_and_bob["bob"], id=str(alice_and_bob["workflow"]))
    assert result.errors, "bob must not be able to run alice's workflow"
    assert "not found" in str(result.errors[0].message)


async def test_retrying_someone_elses_run_is_refused(alice_and_bob):
    result = await mutate(RETRY, alice_and_bob["bob"], id=str(alice_and_bob["run"]))
    assert result.errors
    assert "not found" in str(result.errors[0].message)


async def test_updating_someone_elses_workflow_is_refused(alice_and_bob):
    result = await mutate(UPDATE, alice_and_bob["bob"], id=str(alice_and_bob["workflow"]))
    assert result.errors
    assert "not found" in str(result.errors[0].message)

    # And the refusal is not merely cosmetic -- nothing changed.
    with engine.connect() as conn:
        name = conn.execute(
            text("SELECT name FROM workflows WHERE id = :id"),
            {"id": str(alice_and_bob["workflow"])},
        ).scalar_one()
    assert name != "renamed-by-bob"


async def test_a_missing_id_is_refused_the_same_way_as_someone_elses(alice_and_bob):
    absent = await mutate(RUN, alice_and_bob["bob"], id=str(uuid.uuid4()))
    theirs = await mutate(RUN, alice_and_bob["bob"], id=str(alice_and_bob["workflow"]))
    # Identical messages: a distinct "forbidden" would confirm the id names a
    # real workflow, which is what the read path's null already avoids.
    assert absent.errors[0].message == theirs.errors[0].message


async def test_the_check_runs_before_the_orchestrator_is_called(
    alice_and_bob, monkeypatch
):
    """The ordering is the whole protection, so it gets its own test.

    With the orchestrator pointed at a closed port, a refusal that still says
    "not found" proves the request was rejected here. If the check ever moved
    below the HTTP call this fails with a connection error instead.
    """
    monkeypatch.setattr(mutations, "ORCHESTRATOR_URL", "http://127.0.0.1:1")

    result = await mutate(RUN, alice_and_bob["bob"], id=str(alice_and_bob["workflow"]))
    assert "not found" in str(result.errors[0].message)

    # Control: the owner does get as far as the (unreachable) orchestrator,
    # which is what makes the assertion above meaningful rather than vacuous.
    owner = await mutate(RUN, alice_and_bob["alice"], id=str(alice_and_bob["workflow"]))
    assert "not found" not in str(owner.errors[0].message)
