"""Materializes dag_json nodes as steps rows, one set per workflow version.

Copy-on-write: an edit writes a new set of rows at a new version rather than
replacing the old ones. Deleting them is what the step_results foreign key
refuses once a run has recorded results, and that refusal is correct --
history should not be made to point at a graph that changed underneath it.

workflows.dag_json remains the current, editable copy. workflow_versions holds
the immutable snapshot each run is replayed against.
"""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dag_parser import topological_sort
from app.models import Step


def sync_steps(db: Session, workflow) -> dict[str, uuid.UUID]:
    """Write this workflow's steps rows at its current version.

    Returns node_id -> step uuid, which the run publisher needs to put a real
    foreign key on each Kafka message.
    """
    # Snapshot the graph so a run started on this version can still be read
    # back after later edits overwrite workflows.dag_json.
    db.execute(
        text(
            """
            INSERT INTO workflow_versions (workflow_id, version, dag_json)
            VALUES (:workflow_id, :version, CAST(:dag_json AS jsonb))
            ON CONFLICT (workflow_id, version) DO UPDATE SET dag_json = EXCLUDED.dag_json
            """
        ),
        {
            "workflow_id": str(workflow.id),
            "version": workflow.version,
            "dag_json": json.dumps(workflow.dag_json),
        },
    )

    # Same version written twice only happens when a create is retried; the
    # rows would collide with the uniqueness constraint otherwise.
    db.query(Step).filter(
        Step.workflow_id == workflow.id, Step.version == workflow.version
    ).delete()

    nodes = workflow.dag_json.get("nodes", [])
    order = {node_id: i for i, node_id in enumerate(topological_sort(workflow.dag_json))}

    # Ids are assigned before any row is built: depends_on is uuid[], so every
    # node needs an id before its dependents can reference it.
    ids = {node["id"]: uuid.uuid4() for node in nodes}

    for node in nodes:
        db.add(
            Step(
                id=ids[node["id"]],
                workflow_id=workflow.id,
                version=workflow.version,
                node_id=node["id"],
                type=node.get("type", "llm_call"),
                config_json=node.get("config", {}),
                depends_on=[ids[dep] for dep in node.get("depends_on") or []],
                step_order=order.get(node["id"]),
                retry_policy=node.get("retry_policy"),
            )
        )

    return ids
