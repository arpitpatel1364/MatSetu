from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from backend.database import get_db
from backend.models import AdminAccount
from backend.schemas.auth import AdminLoginRequest, AdminLoginResponse, AdminCreateRequest, AdminResponse, TokenRefreshRequest
from backend.core.bcrypt_utils import verify_password, hash_password
from backend.core.totp import verify_totp, generate_totp_secret, encrypt_totp_secret, get_totp_uri
from backend.core.jwt import create_access_token, create_refresh_token, decode_token
from backend.core.rls import get_current_admin, require_role, check_ip_allowlist
from backend.services.audit import log_action
from backend.config import settings
from jose import JWTError
import logging
from uuid import uuid4


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(
    request: Request,
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Admin login with password + TOTP (2FA). IP allowlist enforced for T1/T2."""
    result = await db.execute(
        select(AdminAccount)
        .where(AdminAccount.username == body.username)
        .where(AdminAccount.is_active == True)
    )
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # TOTP verification
    if not verify_totp(admin.totp_secret, body.totp_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")

    # IP allowlist check for T1 and T2 (mandatory)
    if admin.role in ("T1", "T2") and admin.ip_allowlist:
        if not check_ip_allowlist(request, admin.ip_allowlist):
            await log_action(db, "admin", admin.id, "ADMIN_LOGIN",
                             metadata={"status": "IP_BLOCKED", "ip": request.client.host})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not in allowlist")

    # Update last login
    admin.last_login_at = datetime.utcnow()

    token_data = {
        "sub": str(admin.id),
        "username": admin.username,
        "role": admin.role,
        "scope_type": admin.scope_type,
        "scope_id": str(admin.scope_id) if admin.scope_id else None
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    await log_action(db, "admin", admin.id, "ADMIN_LOGIN",
                     metadata={"status": "SUCCESS", "ip": request.client.host})

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=admin.role,
        scope_type=admin.scope_type or "",
        scope_id=str(admin.scope_id) if admin.scope_id else None,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/admin/refresh", response_model=AdminLoginResponse)
async def refresh_token(body: TokenRefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        token_data = {k: v for k, v in payload.items() if k not in ("exp", "iat", "type")}
        return AdminLoginResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
            role=payload.get("role", ""),
            scope_type=payload.get("scope_type", ""),
            scope_id=payload.get("scope_id"),
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/admin/create", response_model=AdminResponse)
async def create_admin(
    body: AdminCreateRequest,
    payload: dict = Depends(require_role("T1")),
    db: AsyncSession = Depends(get_db)
):
    """T1 Master Admin only — create new admin account."""
    totp_secret = generate_totp_secret()
    admin = AdminAccount(
        id=uuid4(),
        username=body.username,
        password_hash=hash_password(body.password),
        totp_secret=encrypt_totp_secret(totp_secret),
        role=body.role,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        ip_allowlist=body.ip_allowlist or [],
        is_active=True
    )
    db.add(admin)
    await db.flush()
    return AdminResponse(
        id=admin.id,
        username=admin.username,
        role=admin.role,
        scope_type=admin.scope_type or "",
        scope_id=admin.scope_id,
        is_active=True,
        created_at=admin.created_at or datetime.utcnow(),
        totp_uri=get_totp_uri(totp_secret, body.username)
    )
