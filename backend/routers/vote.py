from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from uuid import UUID

from backend.database import get_db
from backend.models import Candidate, Constituency, Party
from backend.schemas.vote import VoteCastRequest, VoteCastResponse, BallotRequest, BallotResponse, CandidateOnBallot, TallyResponse
from backend.services.vote import cast_vote, get_tally
from backend.services.audit import log_action
from backend.core.rls import get_current_worker, require_role
import logging

router = APIRouter(prefix="/api/v1/vote", tags=["vote"])
logger = logging.getLogger(__name__)

# Import shared ballot_tokens from voter router
from backend.routers.voter import _ballot_tokens


@router.post("/ballot", response_model=BallotResponse)
async def get_ballot(
    body: BallotRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 9: Show ballot — candidate name + party + symbol (22 languages).
    Validates ballot_token (2-minute expiry).
    """
    token_record = _ballot_tokens.get(str(body.voter_id))
    if not token_record:
        raise HTTPException(status_code=401, detail="No active ballot session")
    if token_record["token"] != body.ballot_token:
        raise HTTPException(status_code=401, detail="Invalid ballot token")
    if datetime.now(timezone.utc) > token_record["expires_at"]:
        _ballot_tokens.pop(str(body.voter_id), None)
        raise HTTPException(status_code=401, detail="Ballot session expired")
    if token_record["booth_id"] != str(body.booth_id):
        raise HTTPException(status_code=403, detail="Booth mismatch")

    # Get voter's constituency via booth
    from backend.models import Voter, Booth, Constituency
    voter_result = await db.execute(select(Voter).where(Voter.id == body.voter_id))
    voter = voter_result.scalar_one_or_none()
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    booth_result = await db.execute(select(Booth).where(Booth.id == voter.booth_id))
    booth = booth_result.scalar_one_or_none()

    constituency_result = await db.execute(
        select(Constituency).where(Constituency.id == booth.constituency_id)
    )
    constituency = constituency_result.scalar_one_or_none()
    if not constituency:
        raise HTTPException(status_code=404, detail="Constituency not found")

    # Verify constituency is OPEN
    if constituency.election_status != "OPEN":
        raise HTTPException(
            status_code=403,
            detail=f"Election not open in this constituency (status: {constituency.election_status})"
        )

    # Get candidates
    cand_result = await db.execute(
        select(Candidate, Party)
        .outerjoin(Party, Party.id == Candidate.party_id)
        .where(Candidate.constituency_id == constituency.id)
        .where(Candidate.is_approved == True)
        .order_by(Candidate.nomination_date)
    )
    rows = cand_result.all()

    candidates = [
        CandidateOnBallot(
            id=c.id,
            full_name=c.full_name,
            party_name=p.name if p else "Independent",
            party_abbreviation=p.abbreviation if p else "IND",
            symbol_url=c.symbol_url,
            serial_number=i + 1
        )
        for i, (c, p) in enumerate(rows)
    ]

    return BallotResponse(
        voter_name=voter.full_name,
        constituency_name=constituency.name,
        candidates=candidates,
        expires_at=token_record["expires_at"]
    )


@router.post("/cast", response_model=VoteCastResponse)
async def cast_vote_endpoint(
    body: VoteCastRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 10: Atomic vote submission.
    SEC-1/SEC-2/SEC-3 enforced inside cast_vote().
    Step 11: ZK receipt is returned in response.
    """
    # Validate ballot token
    token_record = _ballot_tokens.get(str(body.voter_id))
    if not token_record or token_record["token"] != body.ballot_token:
        raise HTTPException(status_code=401, detail="Invalid or expired ballot token")
    if datetime.now(timezone.utc) > token_record["expires_at"]:
        _ballot_tokens.pop(str(body.voter_id), None)
        raise HTTPException(status_code=401, detail="Ballot session expired")

    try:
        result = await cast_vote(
            db,
            voter_id=body.voter_id,
            candidate_id=body.candidate_id,
            booth_id=body.booth_id,
            worker_id=body.worker_id,
            location_chain=body.location_chain
        )
        # Clear ballot token (one-use)
        _ballot_tokens.pop(str(body.voter_id), None)
        return VoteCastResponse(
            success=True,
            vote_id=result["vote_id"],
            receipt_token=result["receipt_token"],
            message="Vote cast successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Vote cast error: {e}")
        raise HTTPException(status_code=500, detail="Vote submission failed — please retry")


@router.get("/tally/{level}/{location_id}", response_model=TallyResponse)
async def tally(
    level: str,
    location_id: str,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4", "T5"))
):
    """Real-time tally from Redis. Scoped by admin role."""
    valid_levels = ["country", "state", "division", "district", "taluka", "block", "village", "booth"]
    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Invalid level. Must be one of {valid_levels}")
    data = await get_tally(level, location_id)
    return TallyResponse(
        candidate_tallies=data["candidate_tallies"],
        last_updated=datetime.now(timezone.utc)
    )


@router.get("/verify-receipt/{receipt_token}")
async def verify_receipt(receipt_token: str, db: AsyncSession = Depends(get_db)):
    """Public receipt verification — confirms vote is in ledger (SEC-6: no candidate revealed)."""
    from backend.models import VoteLedger
    result = await db.execute(
        select(VoteLedger.id, VoteLedger.submitted_at, VoteLedger.is_valid)
        .where(VoteLedger.receipt_token == receipt_token)
    )
    row = result.one_or_none()
    if not row:
        return {"valid": False, "message": "Receipt not found in ledger"}
    return {
        "valid": row.is_valid,
        "vote_id": str(row.id),
        "submitted_at": row.submitted_at.isoformat(),
        "message": "Vote is recorded in the ledger"
        # NOTE: candidate is never returned (SEC-6)
    }
