"""Security middleware — API key validation & CORS configuration."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Optional bearer-token gate.

    If ``settings.api_key`` is set, every request must include
    ``Authorization: Bearer <key>``.  If the setting is ``None`` or empty,
    the gate is disabled (open access for local dev).
    """
    if not settings.api_key:
        return  # gate disabled

    if credentials is None or credentials.credentials != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
