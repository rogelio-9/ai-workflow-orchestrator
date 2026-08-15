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
# The worker imports the generated gRPC stubs, which live outside any one
# service -- the same path the gateway's Dockerfile puts on PYTHONPATH.
GEN = Path(__file__).resolve().parents[3] / "gen"

BOOT_TIMEOUT_SECONDS = 30
RUN_TIMEOUT_SECONDS = 60

# Every step is an llm_call because every step has to actually execute.
#
# This used to open with a tool_call and a transform, and passed -- because the
# worker silently skipped step types it did not own, marked them done, and
# published their dependents anyway. The run reached COMPLETE having run one
# step of three, and the assertion below could not tell the difference. Skipping
# is now a terminal failure, which is what turned this test red and exposed it.
LINEAR_DAG = {
    "nodes": [
        # mock, not ollama or gemini: this test measures the pipeline, not
        # somebody else's inference.
        {
            "id": "fetch",
            "type": "llm_call",
            "config": {"model": "mock:echo", "prompt_template": "Fetch it."},
        },
        {
            "id": "clean",
            "type": "llm_call",
            "config": {"model": "mock:echo", "prompt_template": "Clean it."},
            "depends_on": ["fetch"],
        },
        {
            "id": "summarize",
            "type": "llm_call",
            "config": {"model": "mock:echo", "prompt_template": "Summarize it."},
            "depends_on": ["clean"],
        },
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
        "PYTHONPATH": str(GEN),
        "LLM_GATEWAY_GRPC": os.environ.get("LLM_GATEWAY_GRPC", "localhost:50052"),
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


def _gateway_up() -> bool:
    import socket

    host, _, port = os.environ.get("LLM_GATEWAY_GRPC", "localhost:50052").partition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False


def test_linear_workflow_runs_to_completion(worker):
    if not _gateway_up():
        pytest.skip("llm-gateway not running (docker compose up -d llm-gateway)")

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

    with create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT sr.status, sr.prompt_tokens, sr.completion_tokens,
                       sr.output_json->>'completion' AS completion
                FROM step_results sr
                JOIN steps s ON s.id = sr.step_id
                WHERE sr.run_id = :run_id AND s.node_id = 'summarize'
                """
            ),
            {"run_id": run_id},
        ).one()

    # The join through steps only resolves if the FK holds a real uuid, which
    # is what the whole node_id / step_id split was for.
    assert row.status == "SUCCESS"
    assert row.completion.startswith("[mock:echo]")
    assert row.prompt_tokens > 0 and row.completion_tokens > 0

    # Every step, not just the last one. A run status of COMPLETE only means
    # the graph was satisfied -- it says nothing about whether each step
    # actually executed, which is exactly how a skipped step hid here before.
    with create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        executed = conn.execute(
            text(
                """
                SELECT s.node_id, sr.status
                FROM step_results sr
                JOIN steps s ON s.id = sr.step_id
                WHERE sr.run_id = :run_id
                """
            ),
            {"run_id": run_id},
        ).all()

    assert {node_id: status for node_id, status in executed} == {
        "fetch": "SUCCESS",
        "clean": "SUCCESS",
        "summarize": "SUCCESS",
    }
