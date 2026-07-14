import json
import logging
import os

from confluent_kafka import Producer

logger = logging.getLogger(__name__)

TOPIC_TASKS = "workflow.tasks"

_producer = Producer(
    {
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "enable.idempotence": True,
    }
)


def _on_delivery(err, msg):
    # produce() returns before the broker responds, so this is the only place a
    # publish failure ever surfaces
    if err is not None:
        logger.error("step publish failed: run_id=%s error=%s", msg.key(), err)


def publish_step(step_message: dict) -> None:
    _producer.produce(
        topic=TOPIC_TASKS,
        key=step_message["run_id"],
        value=json.dumps(step_message),
        on_delivery=_on_delivery,
    )
    _producer.poll(0)


def flush(timeout: float = 10.0) -> int:
    return _producer.flush(timeout)