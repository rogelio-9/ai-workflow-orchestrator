import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import app

WORKER = Path(__file__).resolve().parents[2] / "workers" / "base_worker.py"

BOOT_TIMEOUT_SECONDS = 30
RUN_TIMEOUT_SECONDS = 60

LINEAR_DAG = {
    "nodes": [
        {"id": "fetch", "type": "tool_call", "config": {}},
        {"id": "clean", "type": "transform", "config": {}, "depends_on": ["fetch"]},
        {"id": "summarize", "type": "llm_call", "config": {}, "depends_on": ["clean"]},
    ]
}


@pytest.fixture
def worker(tmp_path):
    log_path = tmp_path / "worker.log"
    env = {
        **os.environ,
        "KAFKA_BOOTSTRAP_SERVERS": os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    }

    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            [sys.executable, str(WORKER)], env=env, stderr=log_file, stdout=log_file
        )

        # The worker must own its partitions before the run is created, or the
        # first wave is published into a group with no members and the test
        # waits out its timeout on a rebalance rather than on real work.
        deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if "subscribed to" in log_path.read_text():
                break
            if proc.poll() is not None:
                pytest.fail(f"worker exited early:\n{log_path.read_text()}")
            time.sleep(0.25)
        else:
            proc.kill()
            pytest.fail(f"worker never subscribed:\n{log_path.read_text()}")

        yield log_path

        proc.terminate()
        proc.wait(timeout=10)


def test_linear_workflow_runs_to_completion(worker):
    client = TestClient(app)

    workflow = client.post(
        "/workflows",
        json={
            "name": f"itest-linear-{uuid.uuid4().hex[:8]}",
            "created_by": str(uuid.uuid4()),
            "dag_json": LINEAR_DAG,
        },
    )
    assert workflow.status_code == 201

    run = client.post(
        "/runs",
        json={"workflow_id": workflow.json()["id"], "input_vars": {"url": "x"}},
    )
    assert run.status_code == 201
    run_id = run.json()["id"]

    # Polling a fresh connection each time, not a held session: the worker
    # commits from another process, so a session opened before that commit
    # would keep returning the snapshot it started with.
    engine = create_engine(os.environ["DATABASE_URL"])
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    status = None
    while time.monotonic() < deadline:
        with engine.begin() as conn:
            status = conn.execute(
                text("SELECT status FROM runs WHERE id = :id"), {"id": run_id}
            ).scalar_one()
        if status in ("COMPLETE", "FAILED"):
            break
        time.sleep(0.5)

    assert status == "COMPLETE", (
        f"run ended {status!r}\n\nworker log:\n{worker.read_text()}"
    )