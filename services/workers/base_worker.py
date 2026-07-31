import json
import logging
import os
import signal
import uuid
import redis
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError, Producer
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("base_worker")

TOPIC = "workflow.tasks"

MAX_ATTEMPTS = 3

DLQ_TOPIC = "workflow.tasks.dlq"

LOCK_TTL_SECONDS = 60
PROCESSED_TTL_SECONDS = 60 * 60 * 24
STEPS_DONE_TTL_SECONDS = 60 * 60 * 24

# No real executor until the execution engine lands; this hook lets us force
# failures to exercise the retry path. TODO(executor)
FAIL_STEPS = set(filter(None, os.environ.get("FAIL_STEPS", "").split(",")))

running = True


def _shutdown(signum, frame):
    global running
    running = False


def build_consumer() -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "group.id": "workflow-workers",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )


def build_redis() -> redis.Redis:
    return redis.Redis.from_url(
        os.environ["REDIS_URL"], decode_responses=True
    )


def build_producer() -> Producer:
    return Producer(
        {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "enable.idempotence": True,
        }
    )


def build_engine():
    return create_engine(os.environ["DATABASE_URL"])

def load_dag(engine, run_id: str) -> dict:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT w.dag_json FROM runs r "
                "JOIN workflows w ON w.id = r.workflow_id "
                "WHERE r.id = :run_id"
            ),
            {"run_id": run_id},
        ).first()
    return row[0] if row else {}


def load_step_ids(engine, run_id: str) -> dict[str, str]:
    """node_id -> steps row uuid, for the workflow behind this run."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.node_id, s.id
                FROM steps s
                JOIN runs r ON r.workflow_id = s.workflow_id
                WHERE r.id = :run_id
                """
            ),
            {"run_id": run_id},
        ).all()
    return {node_id: str(step_uuid) for node_id, step_uuid in rows}


def unblocked_steps(dag_json: dict, done: set[str]) -> list[dict]:
    # Duplicated from services/orchestrator/app/dag_parser.py rather than
    # imported, same cross-service argument as build_producer. A shared package
    # is the real fix. TODO(shared)
    return [
        n
        for n in dag_json.get("nodes", [])
        # Root steps are the orchestrator's job at run creation; re-publishing
        # them here would duplicate the first wave on every completion.
        if n.get("depends_on")
        and n["id"] not in done
        and all(dep in done for dep in n["depends_on"])
    ]


def execute_step(payload: dict) -> None:
    node_id = payload.get("node_id")
    if node_id in FAIL_STEPS:
        raise RuntimeError(f"injected failure for node_id={node_id}")
    

def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    consumer = build_consumer()
    r = build_redis()
    producer = build_producer()
    engine = build_engine()
    consumer.subscribe([TOPIC])
    log.info("subscribed to %s", TOPIC)

    try:
        while running:
            # Returns None on timeout rather than blocking forever, so the
            # loop can notice a shutdown signal between polls.
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("consumer error: %s", msg.error())
                continue

            payload = json.loads(msg.value())
            # node_id is graph identity (locks, done-set, logs); step_id is the
            # steps row uuid that step_results must reference.
            node_id = payload.get("node_id")
            step_id = payload.get("step_id")
            attempt = payload.get("attempt", 0)
            run_id = msg.key().decode()

            processed_key = f"processed:step:{run_id}:{node_id}"
            if r.exists(processed_key):
                log.info("node_id=%s already processed, skipping", node_id)
                consumer.commit(msg)
                continue

            if attempt > MAX_ATTEMPTS:
                log.error(
                    "node_id=%s exhausted %s attempts, routing to DLQ",
                    node_id, MAX_ATTEMPTS,
                )
                producer.produce(
                    DLQ_TOPIC,
                    key=msg.key(),
                    value=json.dumps(payload).encode(),
                )
                producer.flush()
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE runs SET status='FAILED', ended_at=now() "
                            "WHERE id = :run_id"
                        ),
                        {"run_id": run_id},
                    )
                consumer.commit(msg)
                continue

            lock_key = f"lock:step:{run_id}:{node_id}"
            token = str(uuid.uuid4())

            acquired = r.set(lock_key, token, nx=True, ex=LOCK_TTL_SECONDS)
            if not acquired:
                log.info("node_id=%s already locked, skipping", node_id)
                consumer.commit(msg)
                continue

            retry_payload = None

            try:
                log.info(
                    "executing node_id=%s partition=%s offset=%s attempt=%s",
                    node_id,
                    msg.partition(),
                    msg.offset(),
                    attempt,
                )
                execute_step(payload)

                done_key = f"run:{run_id}:steps_done"
                r.sadd(done_key, node_id)
                r.expire(done_key, STEPS_DONE_TTL_SECONDS)
                done = set(r.smembers(done_key))

                dag_json = load_dag(engine, run_id)
                step_ids = load_step_ids(engine, run_id)
                published_at = datetime.now(timezone.utc).isoformat()
                for node in unblocked_steps(dag_json, done):
                    log.info("publishing unblocked node_id=%s", node["id"])
                    producer.produce(
                        TOPIC,
                        key=msg.key(),
                        value=json.dumps(
                            {
                                "run_id": run_id,
                                "node_id": node["id"],
                                "step_id": step_ids[node["id"]],
                                "step_type": node.get("type"),
                                "attempt": 1,
                                "config": node.get("config", {}),
                                "input_vars": payload.get("input_vars", {}),
                                "published_at": published_at,
                            }
                        ).encode(),
                    )
                producer.flush()

                if {n["id"] for n in dag_json.get("nodes", [])} <= done:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE runs SET status='COMPLETE', ended_at=now() "
                                "WHERE id = :run_id"
                            ),
                            {"run_id": run_id},
                        )
                    log.info("run_id=%s complete", run_id)

                # Marker is set after fan-out, not before: a crash between the
                # two would otherwise leave the step marked done with its
                # downstream never published, stalling the run permanently.
                r.set(processed_key, "1", ex=PROCESSED_TTL_SECONDS)
                consumer.commit(msg)
            except Exception:
                log.exception("node_id=%s failed on attempt=%s", node_id, attempt)
                retry_payload = {**payload, "attempt": attempt + 1}
            finally:
                # Check-then-delete is not atomic; a lock that expired mid-work
                # and was re-taken could be released by the wrong owner. Needs a
                # Lua script (Redis SET docs) to do both in one round trip.
                # TODO(locking)
                if r.get(lock_key) == token:
                    r.delete(lock_key)

            # Republish only after the lock is released, or the redelivery lands
            # while this worker still holds it and gets dropped by the skip path.
            if retry_payload is not None:
                # Sleep-and-republish; Kafka has no delayed delivery. Bounded by
                # max.poll.interval.ms - longer backoffs need delay topics.
                time.sleep(2 ** attempt)
                producer.produce(
                    TOPIC,
                    key=msg.key(),
                    value=json.dumps(retry_payload).encode(),
                )
                producer.flush()
                consumer.commit(msg)
    finally:
        consumer.close()
        log.info("consumer closed")


if __name__ == "__main__":
    main()