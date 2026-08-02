"""GraphQL schema for the public API.

Reads come straight from Postgres; writes will go through the orchestrator's
REST API so its validation and Kafka publishing stay in one place. Reading
directly is what keeps a nested query from fanning out into an HTTP request
per level, which would reintroduce the round trips GraphQL exists to remove.

The nesting resolvers go through DataLoaders (see loaders.py) so they do not
reintroduce the same fan-out in SQL instead.
"""

import asyncio
import datetime
import uuid

import strawberry
from sqlalchemy import text
from strawberry.scalars import JSON
from strawberry.types import Info

from app.db import engine


@strawberry.type
class StepResult:
    step_id: uuid.UUID
    node_id: str
    status: str
    attempt: int
    output_json: JSON | None
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    error_message: str | None
    created_at: datetime.datetime


@strawberry.type
class Run:
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    input_vars: JSON | None
    started_at: datetime.datetime | None
    ended_at: datetime.datetime | None

    @strawberry.field
    async def step_results(self, info: Info) -> list[StepResult]:
        """Joined through steps so each result carries its node_id -- the id a
        human recognises, rather than the surrogate key."""
        rows = await info.context["loaders"]["step_results"].load(self.id)
        return [StepResult(**row) for row in rows]


@strawberry.type
class Workflow:
    id: uuid.UUID
    name: str
    dag_json: JSON
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    @strawberry.field
    async def runs(self, info: Info, status: str | None = None) -> list[Run]:
        rows = await info.context["loaders"]["runs"].load(self.id)
        # Filtered after the batch rather than in SQL: folding the argument
        # into the key would give every distinct status its own batch and undo
        # the batching.
        return [Run(**row) for row in rows if status is None or row["status"] == status]


def _rows(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


async def _rows_async(sql: str, **params):
    return await asyncio.to_thread(_rows, sql, **params)


@strawberry.type
class Query:
    @strawberry.field
    async def workflows(self) -> list[Workflow]:
        rows = await _rows_async(
            """
            SELECT id, name, dag_json, version, created_at, updated_at
            FROM workflows ORDER BY created_at DESC
            """
        )
        return [Workflow(**row) for row in rows]

    @strawberry.field
    async def workflow(self, id: uuid.UUID) -> Workflow | None:
        rows = await _rows_async(
            """
            SELECT id, name, dag_json, version, created_at, updated_at
            FROM workflows WHERE id = :id
            """,
            id=id,
        )
        return Workflow(**rows[0]) if rows else None

    @strawberry.field
    async def run(self, id: uuid.UUID) -> Run | None:
        rows = await _rows_async(
            """
            SELECT id, workflow_id, status, input_vars, started_at, ended_at
            FROM runs WHERE id = :id
            """,
            id=id,
        )
        return Run(**rows[0]) if rows else None


schema = strawberry.Schema(query=Query)
