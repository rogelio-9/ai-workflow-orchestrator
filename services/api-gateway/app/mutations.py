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


async def _post(path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=ORCHESTRATOR_URL, timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(path, **kwargs)

    if response.is_error:
        # Surface the orchestrator's own reason. Collapsing it into a generic
        # message would hide "workflow not found" and "dag has a cycle" behind
        # the same string.
        detail = response.json().get("detail", response.text)
        raise ValueError(f"orchestrator returned {response.status_code}: {detail}")

    return response.json()


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_workflow(
        self, name: str, dag_json: JSON, created_by: uuid.UUID
    ) -> WorkflowRef:
        body = await _post(
            "/workflows",
            json={"name": name, "dag_json": dag_json, "created_by": str(created_by)},
        )
        return WorkflowRef(id=body["id"], name=body["name"], version=body["version"])

    @strawberry.mutation
    async def run_workflow(
        self, workflow_id: uuid.UUID, input_vars: JSON | None = None
    ) -> RunRef:
        body = await _post(
            "/runs",
            json={"workflow_id": str(workflow_id), "input_vars": input_vars or {}},
        )
        return RunRef(
            id=body["id"], workflow_id=body["workflow_id"], status=body["status"]
        )

    @strawberry.mutation
    async def retry_run(
        self, run_id: uuid.UUID, from_node_id: str | None = None
    ) -> RunRef:
        """Resume a failed run. Without from_node_id every step whose latest
        attempt did not succeed is republished."""
        params = {"from_node_id": from_node_id} if from_node_id else None
        body = await _post(f"/runs/{run_id}/retry", params=params)
        return RunRef(
            id=body["id"], workflow_id=body["workflow_id"], status=body["status"]
        )
