"""JWT validation for the public API.

Auth lives here rather than in the orchestrator because this is the only
service exposed to the internet: the orchestrator, gateway and workers sit on
the compose network and trust each other. Putting the check at the edge means
one place to reason about, rather than an identity claim being re-verified at
every hop.
"""

import os

from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# Local development only. Defaults to enforcing, so forgetting to set it in a
# deployed environment fails closed rather than open.
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in {"1", "true", "yes"}

DEV_USER_ID = "00000000-0000-0000-0000-000000000000"


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            # Required by RFC 6750 -- tells the client which scheme to retry
            # with rather than leaving it to guess.
            headers={"WWW-Authenticate": "Bearer"},
        )


def user_id_from(authorization: str | None) -> str:
    """Extract and verify the caller's identity from an Authorization header."""
    if AUTH_DISABLED:
        return DEV_USER_ID

    if not JWT_SECRET:
        # A blank secret would make every signature verify against "", so this
        # is a 500, not a 401: the server is misconfigured, not the caller.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET is not configured",
        )

    if not authorization:
        raise AuthError("missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("expected 'Authorization: Bearer <token>'")

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        # Deliberately not echoing the library's message: it distinguishes an
        # expired token from a bad signature, which tells an attacker whether
        # they had a real token.
        raise AuthError("invalid or expired token") from exc

    subject = claims.get("sub")
    if not subject:
        raise AuthError("token has no subject claim")

    return subject


async def require_user(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency. Rejects before the request reaches the schema."""
    return user_id_from(authorization)
