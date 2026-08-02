"""FastAPI host for the GraphQL schema."""

from fastapi import Depends, FastAPI
from sqlalchemy import text
from strawberry.fastapi import GraphQLRouter

from app.auth import require_user
from app.db import engine
from app.loaders import build_loaders
from app.schema import schema


async def get_context(user_id: str = Depends(require_user)):
    # Fresh loaders per request: a DataLoader caches by key for its lifetime,
    # so a shared instance would serve stale rows to later requests.
    return {"loaders": build_loaders(), "user_id": user_id}


app = FastAPI(title="API Gateway")

# Auth runs as a dependency of the context, so an unauthenticated request is
# rejected with 401 before any resolver executes -- not inside one, where the
# failure would arrive as a 200 with an errors array.
app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql")


@app.get("/health")
def health():
    # SELECT 1 so this reports database reachability, not just liveness --
    # the same readiness-vs-liveness split as the orchestrator's. Unauthenticated
    # on purpose: a probe should not need a token to say the process is up.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
