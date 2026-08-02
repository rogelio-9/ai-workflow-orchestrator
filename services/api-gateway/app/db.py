"""Read-only database access for the GraphQL read path.

Raw SQL rather than the orchestrator's ORM models: this service does not own
that schema, the same call the worker makes. Importing another service's
models would couple their deploys together for no benefit on a read path.
"""

import os

from sqlalchemy import create_engine

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
