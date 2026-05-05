from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class UncontestedDeclareRequest(BaseModel):
    """
    POST /api/v1/election/uncontested/{constituency_id}
    Requires T1 Master Admin + T2 State Admin sign-off (2-admin dual approval).
    TOTP re-confirmation required (SEC-9).
    """
    master_admin_totp: str = Field(..., pattern=r"^\d{6}$")
    state_admin_id: UUID
    state_admin_totp: str = Field(..., pattern=r"^\d{6}$")
    nomination_deadline_passed: bool = Field(
        ...,
        description="Caller confirms nomination deadline has passed (R6)"
    )


class UncontestedReverseRequest(BaseModel):
    """
    DELETE /api/v1/election/uncontested/{constituency_id}
    Requires same 2-admin sign-off (R7).
    """
    master_admin_totp: str = Field(..., pattern=r"^\d{6}$")
    state_admin_id: UUID
    state_admin_totp: str = Field(..., pattern=r"^\d{6}$")
    reason: str = Field(..., min_length=10, max_length=500)


class UncontestedConstituencyResponse(BaseModel):
    constituency_id: UUID
    constituency_name: str
    state_id: UUID
    candidate_id: UUID
    candidate_name: str
    party_name: Optional[str] = None
    declared_at: datetime
    declared_by: UUID
    election_status: str   # UNCONTESTED

    class Config:
        from_attributes = True


class UncontestedListResponse(BaseModel):
    total: int
    constituencies: List[UncontestedConstituencyResponse]
