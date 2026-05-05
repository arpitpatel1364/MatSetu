from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class BoothCreateRequest(BaseModel):
    name: str
    booth_number: str
    constituency_id: UUID
    state_id: UUID
    district_id: Optional[UUID] = None
    taluka_id: Optional[UUID] = None
    village_id: Optional[UUID] = None
    gps_lat: float = Field(..., ge=-90, le=90)
    gps_lng: float = Field(..., ge=-180, le=180)
    booth_type: str = "regular"


class BoothResponse(BaseModel):
    id: UUID
    name: str
    booth_number: str
    constituency_id: UUID
    is_active: bool
    gps_lat: Optional[float]
    gps_lng: Optional[float]

    class Config:
        from_attributes = True


class WorkerCreateRequest(BaseModel):
    full_name: str
    employee_id: str
    booth_id: UUID
    shift_start: str
    shift_end: str


class AnomalyEventResponse(BaseModel):
    id: UUID
    flag_type: str
    booth_id: Optional[UUID]
    worker_id: Optional[UUID]
    voter_id: Optional[UUID]
    details: dict
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AnomalyOverrideRequest(BaseModel):
    """SEC-8: All manual admin overrides → ANOMALY_OVERRIDE in audit_log."""
    reason: str = Field(..., min_length=10, max_length=1000)
    totp_code: str = Field(..., pattern=r"^\d{6}$")


class ElectionStartRequest(BaseModel):
    """SEC-9: Election start requires TOTP re-confirmation."""
    totp_code: str = Field(..., pattern=r"^\d{6}$")
    constituency_ids: Optional[List[UUID]] = None   # None = all active


class ElectionStopRequest(BaseModel):
    totp_code: str = Field(..., pattern=r"^\d{6}$")
    constituency_ids: Optional[List[UUID]] = None


class DashboardStatsResponse(BaseModel):
    total_voters: int
    total_voted: int
    turnout_percent: float
    active_booths: int
    total_booths: int
    anomaly_count: int
    uncontested_count: int
    last_updated: datetime
