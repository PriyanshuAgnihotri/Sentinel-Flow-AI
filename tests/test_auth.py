from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import get_current_user
from app.core.config import settings


@pytest.fixture
def jwt_settings(monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-unit-tests-32-bytes-minimum")
    monkeypatch.setattr(settings, "auth_jwt_issuer", "sentinelflow-tests")
    monkeypatch.setattr(settings, "auth_jwt_audience", "sentinelflow-api")


def make_token(
    *,
    subject="test-user",
    issuer="sentinelflow-tests",
    audience="sentinelflow-api",
    secret="test-secret-for-unit-tests-32-bytes-minimum",
    expires_delta=timedelta(minutes=5),
):
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + expires_delta,
        },
        secret,
        algorithm="HS256",
    )


def credentials(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_returns_verified_subject(jwt_settings):
    token = make_token(subject="user-123")

    assert get_current_user(credentials(token)) == "user-123"


def test_get_current_user_rejects_missing_credentials(jwt_settings):
    with pytest.raises(HTTPException) as exc:
        get_current_user(None)

    assert exc.value.status_code == 401


def test_get_current_user_rejects_invalid_signature(jwt_settings):
    token = make_token(secret="wrong-secret-for-unit-tests-32-bytes")

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials(token))

    assert exc.value.status_code == 401


def test_get_current_user_rejects_expired_token(jwt_settings):
    token = make_token(expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials(token))

    assert exc.value.status_code == 401


def test_get_current_user_rejects_wrong_issuer(jwt_settings):
    token = make_token(issuer="untrusted-issuer")

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials(token))

    assert exc.value.status_code == 401


def test_get_current_user_rejects_wrong_audience(jwt_settings):
    token = make_token(audience="other-api")

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials(token))

    assert exc.value.status_code == 401


def test_get_current_user_requires_auth_configuration(monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "")
    monkeypatch.setattr(settings, "auth_jwt_issuer", "sentinelflow-tests")
    monkeypatch.setattr(settings, "auth_jwt_audience", "sentinelflow-api")

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials("any-token"))

    assert exc.value.status_code == 503


def test_get_current_user_rejects_empty_subject(jwt_settings):
    token = make_token(subject="")

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials(token))

    assert exc.value.status_code == 401
