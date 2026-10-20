import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
bearer_credentials = Depends(bearer_scheme)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
) -> str:
    """Return the verified user ID from a JWT subject claim."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=503,
            detail="JWT authentication is not configured.",
        )

    if not settings.auth_jwt_issuer or not settings.auth_jwt_audience:
        raise HTTPException(
            status_code=503,
            detail="JWT issuer and audience are not configured.",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 128:
        raise HTTPException(status_code=401, detail="Invalid token subject.")

    return subject
