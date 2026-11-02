"""Bearer tokens for the two non-public audiences.

Agents get INTERNAL_TOKEN (never PayPal credentials); the admin console gets ADMIN_TOKEN.
An unset token rejects every request, so a missing env var fails closed.
"""

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def _check(creds: HTTPAuthorizationCredentials | None, expected: str) -> None:
    if not expected:
        raise HTTPException(503, detail={"error": "TOKEN_NOT_CONFIGURED", "message": "Server token is not set"})
    if creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(401, detail={"error": "UNAUTHORIZED", "message": "Missing or wrong bearer token"})


def require_internal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), settings: Settings = Depends(get_settings)
) -> None:
    _check(creds, settings.internal_token)


def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), settings: Settings = Depends(get_settings)
) -> None:
    _check(creds, settings.admin_token)
