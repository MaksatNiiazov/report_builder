from __future__ import annotations

from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

REPORT_READ = "report_builder.reports.read"
REPORT_EXECUTE = "report_builder.reports.execute"
REPORT_MANAGE = "report_builder.reports.manage"
SOURCE_MANAGE = "report_builder.sources.manage"
AUDIT_READ = "report_builder.audit.read"

bearer_scheme = HTTPBearer(auto_error=False)


def get_identity_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {
            "sub": "local-dev",
            "email": "local-dev@turkuaz.local",
            "full_name": "Local Developer",
            "permissions": [
                REPORT_READ,
                REPORT_EXECUTE,
                REPORT_MANAGE,
                SOURCE_MANAGE,
                AUDIT_READ,
            ],
        }
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return jwt.decode(
            credentials.credentials,
            settings.identity_secret_key,
            algorithms=[settings.identity_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def has_permission(claims: dict[str, Any], permission: str) -> bool:
    permissions = claims.get("permissions")
    if isinstance(permissions, list) and ("*" in permissions or permission in permissions):
        return True
    branch_id = claims.get("active_branch_id") or claims.get("branch_id")
    scoped_by_id = claims.get("branch_permissions_by_id")
    if isinstance(scoped_by_id, dict) and branch_id is not None:
        values = scoped_by_id.get(str(branch_id))
        if isinstance(values, list) and permission in values:
            return True
    branch_code = claims.get("branch_code")
    scoped_by_code = claims.get("branch_permissions")
    if isinstance(scoped_by_code, dict) and isinstance(branch_code, str):
        values = scoped_by_code.get(branch_code)
        if isinstance(values, list) and permission in values:
            return True
    return False


def require_permission(permission: str):
    def dependency(
        claims: Annotated[dict[str, Any], Depends(get_identity_claims)],
    ) -> dict[str, Any]:
        if has_permission(claims, permission):
            return claims
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission}",
        )

    return dependency


def actor_from_claims(claims: dict[str, Any]) -> str | None:
    value = claims.get("email") or claims.get("sub")
    return str(value) if value else None
