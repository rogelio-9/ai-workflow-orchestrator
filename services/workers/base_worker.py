import json
import logging
import os
import signal
import uuid
import redis

from confluent_kafka import Consumer, KafkaError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("base_worker")

TOPIC = "workflow.tasks"

LOCK_TTL_SECONDS = 60

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


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    consumer = build_consumer()
    r = build_redis()
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
            step_id = payload.get("step_id")
            lock_key = f"lock:step:{step_id}"
            token = str(uuid.uuid4())

            acquired = r.set(lock_key, token, nx=True, ex=LOCK_TTL_SECONDS)
            if not acquired:
                log.info("step_id=%s already locked, skipping", step_id)
                consumer.commit(msg)
                continue

            try:
                log.info(
                    "executing step_id=%s partition=%s offset=%s",
                    step_id,
                    msg.partition(),
                    msg.offset(),
                )
                consumer.commit(msg)
            finally:
                # Check-then-delete is not atomic; a lock that expired mid-work
                # and was re-taken could be released by the wrong owner. Needs a
                # Lua script (Redis SET docs) to do both in one round trip.
                # TODO(locking)
                if r.get(lock_key) == token:
                    r.delete(lock_key)
    finally:
        consumer.close()
        log.info("consumer closed")


if __name__ == "__main__":
    main()