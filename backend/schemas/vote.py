from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class VoteCastRequest(BaseModel):
    voter_id: UUID
    candidate_id: UUID
    booth_id: UUID
    worker_id: UUID
    ballot_token: str    # short-lived token from OTP verification
    location_chain: Dict[str, str]   # 8-level: country→state→...→booth


class VoteCastResponse(BaseModel):
    success: bool
    vote_id: Optional[UUID] = None
    receipt_token: Optional[str] = None   # ZK anonymous receipt (SEC-6)
    message: str


class BallotRequest(BaseModel):
    voter_id: UUID
    ballot_token: str
    booth_id: UUID
    language: str = "hi"


class CandidateOnBallot(BaseModel):
    id: UUID
    full_name: str
    party_name: Optional[str] = None
    party_abbreviation: Optional[str] = None
    symbol_url: Optional[str] = None
    serial_number: int


class BallotResponse(BaseModel):
    voter_name: str
    constituency_name: str
    candidates: list[CandidateOnBallot]
    expires_at: datetime


class TallyResponse(BaseModel):
    booth_id: Optional[str] = None
    village_id: Optional[str] = None
    block_id: Optional[str] = None
    taluka_id: Optional[str] = None
    district_id: Optional[str] = None
    division_id: Optional[str] = None
    state_id: Optional[str] = None
    country_total: Optional[int] = None
    candidate_tallies: Optional[Dict[str, int]] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
