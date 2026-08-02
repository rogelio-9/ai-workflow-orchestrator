"""Resume a failed run from its failed steps.

Two pieces of state have to be undone before a step can run again, and both
were put there deliberately:

  processed:step:{run_id}:{node_id}  -- the idempotency guard. It exists so a
      Kafka redelivery does not execute a step twice, which means a retry that
      leaves it in place gets silently skipped rather than re-run.
  run:{run_id}:steps_done            -- drives dependency fan-out. A failed
      step should not be in it, but a step being *re-run* must come out, or
      its downstream will be republished the moment it completes again.

Retrying resumes the existing run rather than creating a new one: the point is
to avoid repeating the steps that already succeeded, and their step_results
rows are attached to this run id.
"""

import os
from datetime import datetime, timezone

import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.kafka_producer import flush, publish_step
from app.models import Run, Step, Workflow

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

_redis = redis.from_url(REDIS_URL, decode_responses=True)


def failed_nodes(db: Session, run_id) -> list[str]:
    """node_ids whose latest attempt in this run did not succeed."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (s.node_id) s.node_id, sr.status
            FROM step_results sr
            JOIN steps s ON s.id = sr.step_id
            WHERE sr.run_id = :run_id
            ORDER BY s.node_id, sr.attempt DESC, sr.created_at DESC
            """
        ),
        {"run_id": str(run_id)},
    ).all()
    return [node_id for node_id, status in rows if status != "SUCCESS"]


def retry_run(db: Session, run: Run, from_node_id: str | None = None) -> list[str]:
    """Republish the run's failed steps. Returns the node_ids republished."""
    workflow = db.get(Workflow, run.workflow_id)

    if from_node_id is not None:
        targets = [from_node_id]
    else:
        targets = failed_nodes(db, run.id)

    if not targets:
        return []

    step_ids = {
        step.node_id: str(step.id)
        for step in db.query(Step).filter(Step.workflow_id == workflow.id)
    }
    nodes = {node["id"]: node for node in workflow.dag_json.get("nodes", [])}

    done_key = f"run:{run.id}:steps_done"
    published_at = datetime.now(timezone.utc).isoformat()

    for node_id in targets:
        node = nodes.get(node_id)
        if node is None:
            raise KeyError(f"node {node_id!r} is not in this workflow's dag_json")

        # Clear both markers before publishing, not after: the worker can pick
        # the message up the instant it lands, and would skip it if the
        # processed key were still set.
        _redis.delete(f"processed:step:{run.id}:{node_id}")
        _redis.srem(done_key, node_id)

        publish_step(
            {
                "run_id": str(run.id),
                "node_id": node_id,
                "step_id": step_ids[node_id],
                "step_type": node.get("type"),
                "attempt": 1,
                "config": node.get("config", {}),
                "input_vars": run.input_vars or {},
                "published_at": published_at,
            }
        )

    flush()

    run.status = "RUNNING"
    run.ended_at = None
    db.commit()

    return targets
