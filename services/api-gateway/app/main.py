"""FastAPI host for the GraphQL schema."""

from fastapi import FastAPI
from sqlalchemy import text
from strawberry.fastapi import GraphQLRouter

from app.db import engine
from app.loaders import build_loaders
from app.schema import schema


async def get_context():
    # Fresh loaders per request: a DataLoader caches by key for its lifetime,
    # so a shared instance would serve stale rows to later requests.
    return {"loaders": build_loaders()}


app = FastAPI(title="API Gateway")
app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql")


@app.get("/health")
def health():
    # SELECT 1 so this reports database reachability, not just liveness --
    # the same readiness-vs-liveness split as the orchestrator's.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
