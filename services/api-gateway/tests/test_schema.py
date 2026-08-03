import uuid

import pytest
from sqlalchemy import event, text

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
def owner_with_data():
    """Three workflows, each with a run and a step result, owned by one user.

    Built here rather than relying on whatever is already in the database:
    queries are scoped by owner now, so a test assuming ambient rows would
    pass or fail depending on what earlier runs left behind.
    """
    owner = str(uuid.uuid4())
    with engine.begin() as conn:
        for index in range(3):
            workflow_id = conn.execute(
                text(
                    """
                    INSERT INTO workflows (name, created_by, dag_json)
                    VALUES (:name, :owner, :dag) RETURNING id
                    """
                ),
                {
                    "name": f"batch-{index}-{uuid.uuid4().hex[:6]}",
                    "owner": owner,
                    "dag": '{"nodes": [{"id": "a", "type": "llm_call", "config": {}}]}',
                },
            ).scalar_one()
            step_id = conn.execute(
                text(
                    """
                    INSERT INTO steps (workflow_id, node_id, type, config_json, step_order)
                    VALUES (:wf, 'a', 'llm_call', '{}', 0) RETURNING id
                    """
                ),
                {"wf": str(workflow_id)},
            ).scalar_one()
            run_id = conn.execute(
                text(
                    "INSERT INTO runs (workflow_id, status) "
                    "VALUES (:wf, 'COMPLETE') RETURNING id"
                ),
                {"wf": str(workflow_id)},
            ).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO step_results
                        (run_id, step_id, status, attempt, prompt_tokens, completion_tokens)
                    VALUES (:run, :step, 'SUCCESS', 1, 7, 12)
                    """
                ),
                {"run": str(run_id), "step": str(step_id)},
            )
    return owner


async def run(document: str, user_id: str):
    result = await schema.execute(
        document,
        context_value={
            "loaders": build_loaders(),
            "user_id": user_id,
            "limiter": UserRateLimiter(),
        },
    )
    assert not result.errors, result.errors
    return result.data


def counting():
    """Count SQL round trips for whatever runs inside."""
    calls = {"n": 0}

    def listener(*args, **kwargs):
        calls["n"] += 1

    event.listen(engine, "before_cursor_execute", listener)
    return calls, lambda: event.remove(engine, "before_cursor_execute", listener)


async def test_nested_query_is_batched_not_n_plus_1(owner_with_data):
    calls, stop = counting()
    try:
        data = await run(
            "{ workflows { name runs { status stepResults { nodeId } } } }",
            owner_with_data,
        )
    finally:
        stop()

    # One query per level regardless of row count. Without the DataLoaders
    # this was 1 + workflows + runs.
    assert calls["n"] == 3, f"expected 3 queries, got {calls['n']}"
    assert len(data["workflows"]) == 3


async def test_step_results_carry_the_node_id(owner_with_data):
    data = await run(
        "{ workflows { runs { stepResults { nodeId status } } } }", owner_with_data
    )
    results = [
        sr for wf in data["workflows"] for r in wf["runs"] for sr in r["stepResults"]
    ]
    assert len(results) == 3
    assert all(sr["nodeId"] == "a" for sr in results)


async def test_status_argument_filters_runs(owner_with_data):
    data = await run('{ workflows { runs(status: "NOPE") { status } } }', owner_with_data)
    assert all(wf["runs"] == [] for wf in data["workflows"])


async def test_unknown_id_resolves_to_null_not_an_error(owner_with_data):
    data = await run(
        '{ workflow(id: "00000000-0000-0000-0000-000000000000") { name } }',
        owner_with_data,
    )
    assert data["workflow"] is None
