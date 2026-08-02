"""GraphQL schema for the public API.

Reads come straight from Postgres; writes will go through the orchestrator's
REST API so its validation and Kafka publishing stay in one place. Reading
directly is what keeps a nested query from fanning out into an HTTP request
per level, which would reintroduce the round trips GraphQL exists to remove.

KNOWN N+1: the nesting resolvers below issue one query per parent, so
`workflows { runs { stepResults } }` currently costs 1 + W + R queries --
measured at 72 for 47 workflows and 24 runs, against 3 if batched. Moving
them to strawberry.dataloader.DataLoader collapses each level into a single
`WHERE id = ANY(:ids)`. TODO(dataloader)
"""

import datetime
import uuid
from typing import Any

import strawberry
from sqlalchemy import text
from strawberry.scalars import JSON

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
    def step_results(self) -> list[StepResult]:
        """Joined through steps so each result carries its node_id -- the id a
        human recognises, rather than the surrogate key."""
        return _step_results_for(self.id)


@strawberry.type
class Workflow:
    id: uuid.UUID
    name: str
    dag_json: JSON
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    @strawberry.field
    def runs(self, status: str | None = None) -> list["Run"]:
        return _runs_for(self.id, status)


def _rows(sql: str, **params) -> list[Any]:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


def _step_results_for(run_id: uuid.UUID) -> list[StepResult]:
    rows = _rows(
        """
        SELECT sr.step_id, s.node_id, sr.status, sr.attempt, sr.output_json,
               sr.latency_ms, sr.prompt_tokens, sr.completion_tokens,
               sr.error_message, sr.created_at
        FROM step_results sr
        JOIN steps s ON s.id = sr.step_id
        WHERE sr.run_id = :run_id
        ORDER BY s.step_order, sr.attempt
        """,
        run_id=run_id,
    )
    return [StepResult(**row) for row in rows]


def _runs_for(workflow_id: uuid.UUID, status: str | None) -> list[Run]:
    rows = _rows(
        """
        SELECT id, workflow_id, status, input_vars, started_at, ended_at
        FROM runs
        WHERE workflow_id = :workflow_id
          AND (:status IS NULL OR status = :status)
        ORDER BY started_at DESC
        """,
        workflow_id=workflow_id,
        status=status,
    )
    return [Run(**row) for row in rows]


@strawberry.type
class Query:
    @strawberry.field
    def workflows(self) -> list[Workflow]:
        rows = _rows(
            """
            SELECT id, name, dag_json, version, created_at, updated_at
            FROM workflows ORDER BY created_at DESC
            """
        )
        return [Workflow(**row) for row in rows]

    @strawberry.field
    def workflow(self, id: uuid.UUID) -> Workflow | None:
        rows = _rows(
            """
            SELECT id, name, dag_json, version, created_at, updated_at
            FROM workflows WHERE id = :id
            """,
            id=id,
        )
        return Workflow(**rows[0]) if rows else None

    @strawberry.field
    def run(self, id: uuid.UUID) -> Run | None:
        rows = _rows(
            """
            SELECT id, workflow_id, status, input_vars, started_at, ended_at
            FROM runs WHERE id = :id
            """,
            id=id,
        )
        return Run(**rows[0]) if rows else None


schema = strawberry.Schema(query=Query)
