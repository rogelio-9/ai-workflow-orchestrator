"""FastAPI host for the GraphQL schema."""

from fastapi import FastAPI
from sqlalchemy import text
from strawberry.fastapi import GraphQLRouter

from app.db import engine
from app.schema import schema

app = FastAPI(title="API Gateway")
app.include_router(GraphQLRouter(schema), prefix="/graphql")


@app.get("/health")
def health():
    # SELECT 1 so this reports database reachability, not just liveness --
    # the same readiness-vs-liveness split as the orchestrator's.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
