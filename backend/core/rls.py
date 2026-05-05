from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from backend.core.jwt import decode_token
from typing import Dict, Any
import ipaddress
import logging

logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


async def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer)
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    # Store in request state for RLS
    request.state.admin_payload = payload
    return payload


async def get_current_worker(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer)
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("role") != "T6":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Worker role required")
    return payload


def require_role(*roles: str):
    async def dep(payload: Dict = Depends(get_current_admin)):
        if payload.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return payload
    return dep


def check_ip_allowlist(request: Request, ip_allowlist: list) -> bool:
    """Check if request IP is in admin's allowlist (SEC-4 / T1-T2 enforcement)."""
    if not ip_allowlist:
        return True
    client_ip = request.client.host
    try:
        client_addr = ipaddress.ip_address(client_ip)
        for entry in ip_allowlist:
            try:
                if client_addr == ipaddress.ip_address(str(entry)):
                    return True
                if client_addr in ipaddress.ip_network(str(entry), strict=False):
                    return True
            except ValueError:
                continue
    except ValueError:
        pass
    return False
