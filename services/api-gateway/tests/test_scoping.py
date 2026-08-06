"""Ownership is enforced in SQL, so these assert on isolation between users."""

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


@pytest.fixture
def two_owners():
    """A workflow and a run for each of two users."""
    alice, bob = uuid.uuid4(), uuid.uuid4()
    made = {}
    with engine.begin() as conn:
        for label, owner in (("alice", alice), ("bob", bob)):
            workflow_id = conn.execute(
                text(
                    """
                    INSERT INTO workflows (name, created_by, dag_json)
                    VALUES (:name, :owner, '{"nodes": []}') RETURNING id
                    """
                ),
                {"name": f"scope-{label}-{uuid.uuid4().hex[:6]}", "owner": str(owner)},
            ).scalar_one()
            run_id = conn.execute(
                text(
                    "INSERT INTO runs (workflow_id, workflow_version, status) "
                    "VALUES (:wf, 1, 'COMPLETE') RETURNING id"
                ),
                {"wf": str(workflow_id)},
            ).scalar_one()
            made[label] = {"owner": str(owner), "workflow": workflow_id, "run": run_id}
    return made


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


async def test_listing_returns_only_your_own(two_owners):
    data = await query("{ workflows { id } }", two_owners["alice"]["owner"])
    ids = {row["id"] for row in data["workflows"]}
    assert str(two_owners["alice"]["workflow"]) in ids
    assert str(two_owners["bob"]["workflow"]) not in ids


async def test_fetching_someone_elses_workflow_returns_null(two_owners):
    data = await query(
        "query ($id: UUID!) { workflow(id: $id) { id } }",
        two_owners["alice"]["owner"],
        id=str(two_owners["bob"]["workflow"]),
    )
    # null, not an authorization error: "forbidden" would confirm the row
    # exists, which is itself a disclosure.
    assert data["workflow"] is None


async def test_your_own_workflow_still_resolves(two_owners):
    data = await query(
        "query ($id: UUID!) { workflow(id: $id) { id } }",
        two_owners["alice"]["owner"],
        id=str(two_owners["alice"]["workflow"]),
    )
    assert data["workflow"]["id"] == str(two_owners["alice"]["workflow"])


async def test_runs_inherit_ownership_from_their_workflow(two_owners):
    data = await query(
        "query ($id: UUID!) { run(id: $id) { id } }",
        two_owners["alice"]["owner"],
        id=str(two_owners["bob"]["run"]),
    )
    # runs has no created_by column -- the join to workflows is what enforces
    # this, so it would silently leak if that join were dropped.
    assert data["run"] is None
