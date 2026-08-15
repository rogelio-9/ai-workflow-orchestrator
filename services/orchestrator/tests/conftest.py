"""Skip the suite when its dependencies are not up.

Most of these tests talk to Postgres, and a few publish to Kafka. Without the
stack running they failed with a connection refused per test, which buries a
real regression in twelve identical stack traces and makes `make test` useless
as a signal on a machine where Docker is not started.

Skipping is only honest because the checks are cheap and specific: a skipped
test says "not exercised", which is different from passing.
"""

import os

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(autouse=True, scope="session")
def _requires_postgres():
    try:
        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}", allow_module_level=True)
