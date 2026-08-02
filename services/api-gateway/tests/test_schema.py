import os

import pytest
from sqlalchemy import event, text

from app.db import engine
from app.loaders import build_loaders
from app.schema import schema


@pytest.fixture(autouse=True)
def _requires_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("postgres not running")


async def run(query: str):
    result = await schema.execute(query, context_value={"loaders": build_loaders()})
    assert not result.errors, result.errors
    return result.data


def counting():
    """Count SQL round trips for whatever runs inside."""
    calls = {"n": 0}

    def listener(*args, **kwargs):
        calls["n"] += 1

    event.listen(engine, "before_cursor_execute", listener)
    return calls, lambda: event.remove(engine, "before_cursor_execute", listener)


async def test_nested_query_is_batched_not_n_plus_1():
    calls, stop = counting()
    try:
        data = await run("{ workflows { name runs { status stepResults { nodeId } } } }")
    finally:
        stop()

    # One query per level, regardless of how many rows come back. Without the
    # DataLoaders this was 1 + workflows + runs.
    assert calls["n"] == 3, f"expected 3 queries, got {calls['n']}"
    assert len(data["workflows"]) > 0


async def test_step_results_carry_the_node_id():
    data = await run("{ workflows { runs { stepResults { nodeId status } } } }")
    results = [
        sr
        for wf in data["workflows"]
        for r in wf["runs"]
        for sr in r["stepResults"]
    ]
    assert results, "no step results in the database to assert on"
    assert all(sr["nodeId"] for sr in results)


async def test_status_argument_filters_runs():
    data = await run('{ workflows { runs(status: "NOPE") { status } } }')
    assert all(wf["runs"] == [] for wf in data["workflows"])


async def test_unknown_id_resolves_to_null_not_an_error():
    data = await run('{ workflow(id: "00000000-0000-0000-0000-000000000000") { name } }')
    assert data["workflow"] is None
