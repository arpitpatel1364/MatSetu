"""
Voter authentication router.
Implements the full 11-step EVM-replacement voter flow.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4, UUID
from datetime import datetime, timedelta
import secrets

from backend.database import get_db
from backend.models import Voter, OTPRecord, Booth
from backend.schemas.voter import (
    VoterScanRequest, VoterFaceVerifyRequest, VoterFaceVerifyResponse,
    OTPSendRequest, OTPVerifyRequest, OTPVerifyResponse, VoterResponse
)
from backend.services.face import extract_embedding, check_liveness, cosine_similarity
from backend.services.qdrant import search_face
from backend.services.otp import create_otp, verify_otp, send_otp_sms
from backend.services.audit import log_action, raise_anomaly
from backend.services.ocr import extract_epic_from_image
from backend.core.rls import get_current_worker
from backend.config import settings
from backend.tasks.send_otp import send_otp_task
import logging

router = APIRouter(prefix="/api/v1/voter", tags=["voter"])
logger = logging.getLogger(__name__)

# Short-lived ballot tokens: voter_id → token (in-memory, cleared after use)
_ballot_tokens: dict = {}


@router.post("/scan", response_model=VoterResponse)
async def scan_voter(
    body: VoterScanRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 1-2: EPIC scan → PostgreSQL lookup.
    Booth worker initiates voter identification.
    """
    result = await db.execute(
        select(Voter).where(Voter.epic_number == body.epic_number)
    )
    voter = result.scalar_one_or_none()
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found in electoral roll")

    # Verify voter is assigned to this booth (scope check)
    if str(voter.booth_id) != str(body.booth_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voter not assigned to this booth"
        )

    await log_action(db, "voter", voter.id, "VOTER_SCAN",
                     booth_id=body.booth_id,
                     metadata={"epic_number": body.epic_number, "worker_id": str(body.worker_id)})
    return VoterResponse.model_validate(voter)


@router.post("/scan-ocr")
async def scan_voter_ocr(
    image_b64: str,
    booth_id: UUID,
    worker_id: UUID,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """Step 1: OCR-based EPIC extraction from card image."""
    epic = extract_epic_from_image(image_b64)
    if not epic:
        raise HTTPException(status_code=422, detail="Could not extract EPIC from image")
    result = await db.execute(select(Voter).where(Voter.epic_number == epic))
    voter = result.scalar_one_or_none()
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")
    return VoterResponse.model_validate(voter)


@router.post("/face-verify", response_model=VoterFaceVerifyResponse)
async def face_verify(
    body: VoterFaceVerifyRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Steps 3-4: ArcFace liveness + identity verification.
    Raises FLAG_LIVENESS_FAIL or fails with low similarity.
    """
    voter_result = await db.execute(select(Voter).where(Voter.id == body.voter_id))
    voter = voter_result.scalar_one_or_none()
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    # Step 3: Liveness check
    is_live, liveness_score = check_liveness(body.face_image_b64)
    if not is_live:
        await raise_anomaly(db, "FLAG_LIVENESS_FAIL", voter_id=body.voter_id,
                            details={"liveness_score": liveness_score})
        return VoterFaceVerifyResponse(
            voter_id=body.voter_id, similarity=0.0,
            liveness_score=liveness_score, passed=False,
            fail_reason="Liveness check failed — possible spoofing attempt"
        )

    # Step 4: ArcFace embedding + Qdrant search
    if not voter.face_enrolled or not voter.qdrant_vector_id:
        return VoterFaceVerifyResponse(
            voter_id=body.voter_id, similarity=0.0,
            liveness_score=liveness_score, passed=False,
            fail_reason="Face not enrolled — use Aadhaar OTP fallback"
        )

    embedding = extract_embedding(body.face_image_b64)
    if embedding is None:
        return VoterFaceVerifyResponse(
            voter_id=body.voter_id, similarity=0.0,
            liveness_score=liveness_score, passed=False,
            fail_reason="No face detected in image"
        )

    matches = search_face(
        settings.QDRANT_COLLECTION_VOTERS,
        embedding,
        top_k=1,
        score_threshold=settings.ARCFACE_SIMILARITY_THRESHOLD
    )

    if not matches:
        return VoterFaceVerifyResponse(
            voter_id=body.voter_id, similarity=0.0,
            liveness_score=liveness_score, passed=False,
            fail_reason="Face did not match enrolled record — use OTP fallback"
        )

    point_id, similarity, _ = matches[0]
    if str(point_id) != str(voter.qdrant_vector_id):
        return VoterFaceVerifyResponse(
            voter_id=body.voter_id, similarity=similarity,
            liveness_score=liveness_score, passed=False,
            fail_reason="Face matched different voter record"
        )

    return VoterFaceVerifyResponse(
        voter_id=body.voter_id,
        similarity=similarity,
        liveness_score=liveness_score,
        passed=True
    )


@router.post("/otp/send")
async def send_otp(
    body: OTPSendRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 7: Dispatch OTP via Celery.
    Twilio primary → MSG91 fallback → thermal print (R8) on SMS failure.
    """
    voter_result = await db.execute(select(Voter).where(Voter.id == body.voter_id))
    voter = voter_result.scalar_one_or_none()
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    # Step 6 check — has already voted?
    if voter.has_voted:
        await raise_anomaly(db, "FLAG_DUPLICATE_ATTEMPT", voter_id=body.voter_id,
                            booth_id=body.booth_id)
        raise HTTPException(status_code=409, detail="Voter has already cast their vote")

    # Dispatch via Celery (async)
    send_otp_task.delay(
        str(body.voter_id),
        voter.mobile or "",
        voter.preferred_language or "en",
        str(body.booth_id)
    )

    await log_action(db, "voter", body.voter_id, "OTP_SENT",
                     booth_id=body.booth_id,
                     metadata={"mobile_masked": f"****{(voter.mobile or '')[-4:]}"})
    return {"message": "OTP dispatched", "expires_in": settings.OTP_EXPIRE_SECONDS}


@router.post("/otp/verify", response_model=OTPVerifyResponse)
async def verify_voter_otp(
    body: OTPVerifyRequest,
    worker_payload: dict = Depends(get_current_worker),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 8: Verify OTP (max 3 attempts, 5-min expiry).
    Returns ballot_token on success.
    """
    success, remaining = await verify_otp(db, body.voter_id, body.otp)

    if not success:
        if remaining == 0:
            raise HTTPException(status_code=429, detail="OTP expired or max attempts reached")
        return OTPVerifyResponse(success=False, attempts_remaining=remaining)

    # Generate short-lived ballot token (valid 2 minutes for ballot display)
    ballot_token = secrets.token_urlsafe(32)
    _ballot_tokens[str(body.voter_id)] = {
        "token": ballot_token,
        "expires_at": datetime.utcnow() + timedelta(minutes=2),
        "booth_id": str(body.booth_id)
    }

    return OTPVerifyResponse(success=True, attempts_remaining=remaining, ballot_token=ballot_token)


@router.post("/has-voted-check")
async def has_voted_check(voter_id: UUID, db: AsyncSession = Depends(get_db)):
    """Step 6: Explicit has_voted check (also called pre-OTP)."""
    result = await db.execute(select(Voter.has_voted).where(Voter.id == voter_id))
    has_voted = result.scalar_one_or_none()
    if has_voted is None:
        raise HTTPException(status_code=404, detail="Voter not found")
    return {"voter_id": str(voter_id), "has_voted": has_voted}
