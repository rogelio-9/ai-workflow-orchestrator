"""Run.dagJson must be the graph the run executed, not the current one.

Session 26 made runs immutable against later edits by pinning them to a
version. That guarantee only reaches a user if the API serves the pinned graph
-- reading workflows.dag_json here would draw the wrong nodes around the right
results, which is the exact mismatch versioning exists to prevent.
"""

import uuid

import pytest
from sqlalchemy import text

from app.db import engine
from app.loaders import build_loaders
from app.ratelimit import UserRateLimiter
from app.schema import schema


@pytest.fixture(autouse=True)
def _requires_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("postgres not running")


V1 = '{"nodes": [{"id": "old", "type": "llm_call", "config": {"model": "mock:v1"}}]}'
V2 = '{"nodes": [{"id": "new", "type": "llm_call", "config": {"model": "mock:v2"}}]}'


@pytest.fixture
def edited_workflow():
    """A workflow at v2 with a run still pinned to v1."""
    owner = str(uuid.uuid4())
    with engine.begin() as conn:
        workflow_id = conn.execute(
            text(
                """
                INSERT INTO workflows (name, created_by, dag_json, version)
                VALUES (:name, :owner, CAST(:dag AS jsonb), 2) RETURNING id
                """
            ),
            {"name": f"trace-{uuid.uuid4().hex[:6]}", "owner": owner, "dag": V2},
        ).scalar_one()

        for version, dag in ((1, V1), (2, V2)):
            conn.execute(
                text(
                    "INSERT INTO workflow_versions (workflow_id, version, dag_json) "
                    "VALUES (:wf, :v, CAST(:dag AS jsonb))"
                ),
                {"wf": str(workflow_id), "v": version, "dag": dag},
            )

        run_id = conn.execute(
            text(
                "INSERT INTO runs (workflow_id, workflow_version, status) "
                "VALUES (:wf, 1, 'COMPLETE') RETURNING id"
            ),
            {"wf": str(workflow_id)},
        ).scalar_one()

    return {"owner": owner, "workflow": workflow_id, "run": run_id}


async def query(document: str, user_id: str, **variables):
    result = await schema.execute(
        document,
        variable_values=variables or None,
        context_value={
            "loaders": build_loaders(),
            "user_id": user_id,
            "limiter": UserRateLimiter(),
        },
    )
    assert not result.errors, result.errors
    return result.data


TRACE = "query ($id: UUID!) { run(id: $id) { workflowVersion dagJson } }"


async def test_the_run_serves_the_graph_it_executed(edited_workflow):
    data = await query(TRACE, edited_workflow["owner"], id=str(edited_workflow["run"]))
    run = data["run"]
    assert run["workflowVersion"] == 1
    # v1's node, not v2's -- the workflow has moved on since this run.
    assert [node["id"] for node in run["dagJson"]["nodes"]] == ["old"]


async def test_the_workflow_still_serves_its_current_graph(edited_workflow):
    # The two fields answer different questions and must not converge.
    data = await query(
        "query ($id: UUID!) { workflow(id: $id) { version dagJson } }",
        edited_workflow["owner"],
        id=str(edited_workflow["workflow"]),
    )
    assert data["workflow"]["version"] == 2
    assert [n["id"] for n in data["workflow"]["dagJson"]["nodes"]] == ["new"]


async def test_a_run_with_no_snapshot_resolves_to_null_rather_than_erroring(
    edited_workflow,
):
    # Rows written straight to SQL before versioning existed have no snapshot.
    # The trace should be able to say so, not fail the whole query.
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                "INSERT INTO runs (workflow_id, workflow_version, status) "
                "VALUES (:wf, 99, 'COMPLETE') RETURNING id"
            ),
            {"wf": str(edited_workflow["workflow"])},
        ).scalar_one()

    data = await query(TRACE, edited_workflow["owner"], id=str(run_id))
    assert data["run"]["dagJson"] is None


async def test_someone_elses_run_is_still_invisible(edited_workflow):
    data = await query(TRACE, str(uuid.uuid4()), id=str(edited_workflow["run"]))
    # The new field must not become a way around the ownership join.
    assert data["run"] is None
