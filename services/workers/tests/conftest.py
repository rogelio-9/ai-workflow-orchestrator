"""Put the worker and the generated stubs on the path.

The image sets PYTHONPATH=/app/gen:/app (see the Dockerfile); a local pytest
run gets neither, so importing base_worker fails on llm_gateway_pb2. Resolved
from this file rather than the working directory so the suite runs the same
whether invoked from the repo root or from services/workers.
"""

import sys
from pathlib import Path

WORKERS = Path(__file__).resolve().parent.parent
REPO = WORKERS.parent.parent

for path in (WORKERS, REPO / "gen"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
