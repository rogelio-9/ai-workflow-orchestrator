import datetime
import importlib
import uuid

import pytest
from fastapi import HTTPException
from jose import jwt

SECRET = "test-secret-not-the-real-one"


@pytest.fixture
def auth(monkeypatch):
    """Reload the module so its env-read module constants pick up the test
    values -- they are read at import, not per call."""
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("AUTH_DISABLED", "false")
    import app.auth

    return importlib.reload(app.auth)


def token(secret=SECRET, algorithm="HS256", **claims):
    payload = {"sub": str(uuid.uuid4()), **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_valid_token_yields_its_subject(auth):
    user_id = str(uuid.uuid4())
    assert auth.user_id_from(f"Bearer {token(sub=user_id)}") == user_id


def test_missing_header_is_rejected(auth):
    with pytest.raises(HTTPException) as exc:
        auth.user_id_from(None)
    assert exc.value.status_code == 401
    # RFC 6750: tell the client which scheme to retry with.
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Basic abc123", "sometoken", "Bearer "],
)
def test_malformed_headers_are_rejected(auth, header):
    with pytest.raises(HTTPException) as exc:
        auth.user_id_from(header)
    assert exc.value.status_code == 401


def test_token_signed_with_another_secret_is_rejected(auth):
    with pytest.raises(HTTPException) as exc:
        auth.user_id_from(f"Bearer {token(secret='attacker-secret')}")
    assert exc.value.status_code == 401


def test_expired_token_is_rejected(auth):
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    with pytest.raises(HTTPException) as exc:
        auth.user_id_from(f"Bearer {token(exp=past)}")
    assert exc.value.status_code == 401


def test_rejection_does_not_reveal_why(auth):
    """An expired token and a forged one must be indistinguishable, or the
    response tells an attacker whether they held a real token."""
    expired = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)

    with pytest.raises(HTTPException) as a:
        auth.user_id_from(f"Bearer {token(exp=expired)}")
    with pytest.raises(HTTPException) as b:
        auth.user_id_from(f"Bearer {token(secret='attacker-secret')}")

    assert a.value.detail == b.value.detail


def test_token_without_a_subject_is_rejected(auth):
    unsigned_subject = jwt.encode({"role": "admin"}, SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        auth.user_id_from(f"Bearer {unsigned_subject}")
    assert exc.value.status_code == 401


def test_blank_secret_is_a_server_error_not_a_rejection(monkeypatch):
    """A blank secret would verify every signature against "", so this is
    misconfiguration, not a bad credential."""
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    import app.auth

    module = importlib.reload(app.auth)

    with pytest.raises(HTTPException) as exc:
        module.user_id_from("Bearer anything")
    assert exc.value.status_code == 500


def test_auth_defaults_to_enforcing(monkeypatch):
    """Forgetting AUTH_DISABLED in a deployed environment must fail closed."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    import app.auth

    module = importlib.reload(app.auth)

    assert module.AUTH_DISABLED is False
    with pytest.raises(HTTPException):
        module.user_id_from(None)
