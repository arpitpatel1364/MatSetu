from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class VoterScanRequest(BaseModel):
    epic_number: str = Field(..., min_length=6, max_length=20)
    booth_id: UUID
    worker_id: UUID


class VoterScanOCRRequest(BaseModel):
    image_b64: str
    booth_id: UUID
    worker_id: UUID


class VoterFaceVerifyRequest(BaseModel):
    voter_id: UUID
    face_image_b64: str   # base64 JPEG


class VoterFaceVerifyResponse(BaseModel):
    voter_id: UUID
    similarity: float
    liveness_score: float
    passed: bool
    fail_reason: Optional[str] = None


class OTPSendRequest(BaseModel):
    voter_id: UUID
    booth_id: UUID


class OTPVerifyRequest(BaseModel):
    voter_id: UUID
    otp: str = Field(..., min_length=6, max_length=8)
    booth_id: UUID


class OTPVerifyResponse(BaseModel):
    success: bool
    attempts_remaining: int
    ballot_token: Optional[str] = None   # short-lived token to show ballot


class VoterResponse(BaseModel):
    id: UUID
    epic_number: str
    full_name: str
    dob: Optional[str]
    gender: Optional[str]
    booth_id: UUID
    has_voted: bool
    face_enrolled: bool
    preferred_language: str

    class Config:
        from_attributes = True


class VoterEnrollRequest(BaseModel):
    epic_number: str
    full_name: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    mobile: Optional[str] = None
    state_code: str
    booth_id: UUID
    preferred_language: str = "hi"
