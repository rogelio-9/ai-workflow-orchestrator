"""Write path: everything goes through the orchestrator's REST API.

Reads talk to Postgres directly because a join is cheaper than a fan-out of
HTTP calls. Writes do not get that shortcut -- creating a workflow validates
the DAG, and starting a run publishes to Kafka. Reimplementing either here
would mean two services owning the same invariants, and they would drift.
"""

import os
import uuid

import httpx
import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from app.db import rows_async

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")
TIMEOUT_SECONDS = float(os.environ.get("ORCHESTRATOR_TIMEOUT_SECONDS", "30"))


@strawberry.type
class WorkflowRef:
    id: uuid.UUID
    name: str
    version: int


@strawberry.type
class RunRef:
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str


async def _request(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=ORCHESTRATOR_URL, timeout=TIMEOUT_SECONDS) as client:
        response = await client.request(method, path, **kwargs)

    if response.is_error:
        # Surface the orchestrator's own reason. Collapsing it into a generic
        # message would hide "workflow not found" and "dag has a cycle" behind
        # the same string.
        detail = response.json().get("detail", response.text)
        raise ValueError(f"orchestrator returned {response.status_code}: {detail}")

    return response.json()


async def _post(path: str, **kwargs) -> dict:
    return await _request("POST", path, **kwargs)


async def _patch(path: str, **kwargs) -> dict:
    return await _request("PATCH", path, **kwargs)


def _throttle(info: Info) -> None:
    """Writes are throttled, reads are not: a run spawns LLM calls and
    worker time, a query costs three SELECTs."""
    info.context["limiter"].check(info.context["user_id"])


# The orchestrator has no authentication of its own -- it trusts whatever
# reaches it. That makes this gateway the only place ownership is enforced, and
# it applies to writes as much as to reads: a caller who cannot read a workflow
# must not be able to run it, because running it spends the owner's LLM budget
# and writes rows attached to their run history.
#
# Ids arrive from the client, so every one of them has to be re-checked here
# rather than trusted because it looks well-formed.


class NotFound(Exception):
    """Raised for both "does not exist" and "not yours".

    Deliberately indistinguishable. A distinct "forbidden" would confirm that
    the id names a real workflow, which is the disclosure the read path avoids
    by returning null.
    """


async def _require_workflow(info: Info, workflow_id: uuid.UUID) -> None:
    rows = await rows_async(
        "SELECT 1 FROM workflows WHERE id = :id AND created_by = :user_id",
        id=workflow_id,
        user_id=info.context["user_id"],
    )
    if not rows:
        raise NotFound("workflow not found")


async def _require_run(info: Info, run_id: uuid.UUID) -> None:
    # runs has no created_by column; the join to workflows is what carries
    # ownership, exactly as on the read path.
    rows = await rows_async(
        """
        SELECT 1 FROM runs r
        JOIN workflows w ON w.id = r.workflow_id
        WHERE r.id = :id AND w.created_by = :user_id
        """,
        id=run_id,
        user_id=info.context["user_id"],
    )
    if not rows:
        raise NotFound("run not found")


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_workflow(
        self, info: Info, name: str, dag_json: JSON
    ) -> WorkflowRef:
        """Ownership comes from the verified token, never from an argument.

        Accepting created_by from the client let any caller write a workflow
        owned by anyone -- and then read it back once queries are scoped.
        """
        _throttle(info)
        body = await _post(
            "/workflows",
            json={
                "name": name,
                "dag_json": dag_json,
                "created_by": info.context["user_id"],
            },
        )
        return WorkflowRef(id=body["id"], name=body["name"], version=body["version"])

    @strawberry.mutation
    async def update_workflow(
        self, info: Info, id: uuid.UUID, name: str | None = None,
        dag_json: JSON | None = None,
    ) -> WorkflowRef:
        """Save an edited workflow.

        Copy-on-write happens in the orchestrator: changing dag_json bumps the
        version and writes a new set of steps rows, leaving earlier runs
        pointing at the graph they actually executed.
        """
        _throttle(info)
        await _require_workflow(info, id)

        # Only the fields the caller sent. Passing name=None through would
        # blank the name on a dag-only save, since the orchestrator cannot tell
        # "unset" from "set to null" in a JSON body.
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if dag_json is not None:
            changes["dag_json"] = dag_json
        if not changes:
            raise ValueError("update_workflow needs a name or a dag_json")

        body = await _patch(f"/workflows/{id}", json=changes)
        return WorkflowRef(id=body["id"], name=body["name"], version=body["version"])

    @strawberry.mutation
    async def run_workflow(
        self, info: Info, workflow_id: uuid.UUID, input_vars: JSON | None = None
    ) -> RunRef:
        _throttle(info)
        await _require_workflow(info, workflow_id)
        body = await _post(
            "/runs",
            json={"workflow_id": str(workflow_id), "input_vars": input_vars or {}},
        )
        return RunRef(
            id=body["id"], workflow_id=body["workflow_id"], status=body["status"]
        )

    @strawberry.mutation
    async def retry_run(
        self, info: Info, run_id: uuid.UUID, from_node_id: str | None = None
    ) -> RunRef:
        """Resume a failed run. Without from_node_id every step whose latest
        attempt did not succeed is republished."""
        _throttle(info)
        await _require_run(info, run_id)
        params = {"from_node_id": from_node_id} if from_node_id else None
        body = await _post(f"/runs/{run_id}/retry", params=params)
        return RunRef(
            id=body["id"], workflow_id=body["workflow_id"], status=body["status"]
        )
