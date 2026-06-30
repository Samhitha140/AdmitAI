"""
Auth dependency — verifies Supabase JWT from Authorization: Bearer <token>.
Frontend signs in via Google OAuth through Supabase JS SDK and sends the
access_token in every request header.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.supabase_client import get_admin_client

_bearer = HTTPBearer(auto_error=False)


def _verify(token: str) -> dict:
    """Call Supabase to verify the access token and return user info."""
    try:
        client = get_admin_client()
        resp = client.auth.get_user(token)
        if not resp.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return {"id": str(resp.user.id), "email": resp.user.email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Strict auth — raises 401 if no valid token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _verify(credentials.credentials)


async def optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict | None:
    """Soft auth — returns None if no token (used by /chat for guest mode)."""
    if not credentials:
        return None
    try:
        return _verify(credentials.credentials)
    except HTTPException:
        return None


# keep old name for backward compat with any code that imports get_current_user
async def get_current_user(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            return _verify(auth[7:])
        except HTTPException:
            pass
    return None
