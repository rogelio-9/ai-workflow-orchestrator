"""Mint a development JWT for the API gateway.

Local only. There is no login flow yet, and the gateway rejects unsigned
requests by design, so something has to produce a token for curl and for the
frontend dev server. It reads JWT_SECRET from the environment rather than
taking it as an argument, so the secret never lands in shell history.

    JWT_SECRET=$(grep ^JWT_SECRET .env | cut -d= -f2) python scripts/mint_token.py <user-uuid>
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "12"))


def main() -> int:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        print("JWT_SECRET is not set", file=sys.stderr)
        return 1

    subject = sys.argv[1] if len(sys.argv) > 1 else str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    print(
        jwt.encode(
            {
                "sub": subject,
                "iat": now,
                "exp": now + timedelta(hours=TTL_HOURS),
            },
            secret,
            algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
