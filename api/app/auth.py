"""Bearer tokens for the two non-public audiences.

Agents get INTERNAL_TOKEN (never PayPal credentials); the admin console gets ADMIN_TOKEN.
An unset token rejects every request, so a missing env var fails closed.
A project's owner gets their own token when they apply (X-Project-Token); only its hash is stored.
"""

import hashlib
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


def new_owner_token() -> tuple[str, str]:
    """(token for the applicant, hash to store)."""
    token = secrets.token_urlsafe(24)
    return token, hash_owner_token(token)


def hash_owner_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_owner_token(token: str | None, stored_hash: str | None) -> None:
    if not token or not stored_hash or not secrets.compare_digest(hash_owner_token(token), stored_hash):
        raise HTTPException(401, detail={"error": "BAD_PROJECT_TOKEN", "message": "Missing or wrong X-Project-Token"})
