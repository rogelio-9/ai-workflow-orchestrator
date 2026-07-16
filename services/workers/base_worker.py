import json
import logging
import os
import signal
import sys

from confluent_kafka import Consumer, KafkaError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("base_worker")

TOPIC = "workflow.tasks"

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
        }
    )


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    consumer = build_consumer()
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
            log.info(
                "received step_id=%s partition=%s offset=%s",
                payload.get("step_id"),
                msg.partition(),
                msg.offset(),
            )
    finally:
        consumer.close()
        log.info("consumer closed")


if __name__ == "__main__":
    main()