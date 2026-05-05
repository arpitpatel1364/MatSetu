from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    totp_code: str = Field(..., pattern=r"^\d{6}$")

    @field_validator("totp_code")
    @classmethod
    def totp_digits_only(cls, v):
        if not v.isdigit():
            raise ValueError("TOTP must be 6 digits")
        return v


class AdminLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    scope_type: str
    scope_id: Optional[str] = None
    expires_in: int


class AdminCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=12)
    role: str = Field(..., pattern=r"^T[1-5]$")
    scope_type: str
    scope_id: Optional[UUID] = None
    ip_allowlist: Optional[List[str]] = None


class AdminResponse(BaseModel):
    id: UUID
    username: str
    role: str
    scope_type: str
    scope_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    totp_uri: Optional[str] = None   # only on creation

    class Config:
        from_attributes = True


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    totp_uri: str
    secret: str   # shown once for QR setup
