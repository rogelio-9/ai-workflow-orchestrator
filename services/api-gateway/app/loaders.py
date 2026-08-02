"""Batch loaders for the nesting resolvers.

Without these, `workflows { runs { stepResults } }` issues one query per
parent -- measured at 72 for 47 workflows and 24 runs. Each loader collapses a
level into a single `= ANY(:ids)`, so the count is one per level regardless of
how many rows come back.

Loaders are built per request, never module-level: a DataLoader caches by key
for its lifetime, so a shared one would serve a second request whatever the
first one saw.
"""

import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import text
from strawberry.dataloader import DataLoader

from app.db import engine


def _rows(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


async def _rows_async(sql: str, **params):
    # The driver is sync. Off the event loop, or one slow query stalls every
    # other request this process is serving.
    return await asyncio.to_thread(_rows, sql, **params)


async def _load_runs(workflow_ids: list[uuid.UUID]) -> list[list[dict]]:
    rows = await _rows_async(
        """
        SELECT id, workflow_id, status, input_vars, started_at, ended_at
        FROM runs
        WHERE workflow_id = ANY(:workflow_ids)
        ORDER BY started_at DESC
        """,
        workflow_ids=workflow_ids,
    )

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["workflow_id"]].append(dict(row))

    # Order and length must match the requested keys exactly -- DataLoader
    # matches results to callers positionally, so a missing key needs an empty
    # list rather than a gap.
    return [grouped[workflow_id] for workflow_id in workflow_ids]


async def _load_step_results(run_ids: list[uuid.UUID]) -> list[list[dict]]:
    rows = await _rows_async(
        """
        SELECT sr.run_id, sr.step_id, s.node_id, sr.status, sr.attempt,
               sr.output_json, sr.latency_ms, sr.prompt_tokens,
               sr.completion_tokens, sr.error_message, sr.created_at
        FROM step_results sr
        JOIN steps s ON s.id = sr.step_id
        WHERE sr.run_id = ANY(:run_ids)
        ORDER BY s.step_order, sr.attempt
        """,
        run_ids=run_ids,
    )

    grouped = defaultdict(list)
    for row in rows:
        record = dict(row)
        record.pop("run_id")
        grouped[row["run_id"]].append(record)

    return [grouped[run_id] for run_id in run_ids]


def build_loaders() -> dict[str, DataLoader]:
    return {
        "runs": DataLoader(load_fn=_load_runs),
        "step_results": DataLoader(load_fn=_load_step_results),
    }
