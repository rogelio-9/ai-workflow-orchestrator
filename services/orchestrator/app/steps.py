"""Materializes dag_json nodes as steps rows.

dag_json stays the source of truth for the graph -- it is what the builder
saves and what the DAG parser reads. The steps table is its database
projection, and it exists so step_results has a real row to reference.
"""

import uuid

from sqlalchemy.orm import Session

from app.dag_parser import topological_sort
from app.models import Step


def sync_steps(db: Session, workflow) -> dict[str, uuid.UUID]:
    """Replace the workflow's steps rows from its dag_json.

    Returns node_id -> step uuid, which the run publisher needs to put a real
    foreign key on each Kafka message.
    """
    db.query(Step).filter(Step.workflow_id == workflow.id).delete()

    nodes = workflow.dag_json.get("nodes", [])
    order = {node_id: i for i, node_id in enumerate(topological_sort(workflow.dag_json))}

    # Ids are assigned before any row is built: depends_on is uuid[], so every
    # node needs an id before its dependents can reference it. Generating them
    # here rather than letting the column default fire is what makes that
    # possible in a single pass.
    ids = {node["id"]: uuid.uuid4() for node in nodes}

    for node in nodes:
        db.add(
            Step(
                id=ids[node["id"]],
                workflow_id=workflow.id,
                node_id=node["id"],
                type=node.get("type", "llm_call"),
                config_json=node.get("config", {}),
                depends_on=[ids[dep] for dep in node.get("depends_on") or []],
                step_order=order.get(node["id"]),
                retry_policy=node.get("retry_policy"),
            )
        )

    return ids
