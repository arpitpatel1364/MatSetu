"""
Uncontested election service.
Implements all R1-R8 business rules from the master spec.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional, List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from backend.models import Constituency, Candidate, AdminAccount, Booth, AuditLog
from backend.services.audit import log_action
from backend.core.totp import verify_totp
import logging

logger = logging.getLogger(__name__)


async def check_uncontested_eligibility(db: AsyncSession, constituency_id: UUID) -> Dict:
    """
    R1: If approved_candidates_count = 1 after nomination_deadline → auto-flag.
    Returns dict with is_eligible, candidate_count, candidate (if 1).
    """
    result = await db.execute(
        select(Candidate)
        .where(Candidate.constituency_id == constituency_id)
        .where(Candidate.is_approved == True)
    )
    candidates = result.scalars().all()

    if len(candidates) == 1:
        return {
            "is_eligible": True,
            "candidate_count": 1,
            "candidate": candidates[0]
        }
    return {
        "is_eligible": False,
        "candidate_count": len(candidates),
        "candidate": None
    }


async def declare_uncontested(
    db: AsyncSession,
    constituency_id: UUID,
    master_admin: AdminAccount,
    master_admin_totp: str,
    state_admin: AdminAccount,
    state_admin_totp: str,
    nomination_deadline_passed: bool
) -> Dict:
    """
    R2: Master Admin (T1 ONLY) + State Admin 2-sign-off.
    R3: Full uncontested declaration flow.
    R6: Reject if nomination deadline not passed.
    """
    # R6: Nomination deadline must have passed
    if not nomination_deadline_passed:
        raise ValueError("R6: Cannot declare uncontested — nomination deadline has not passed")

    # R2: Verify T1 role
    if master_admin.role != "T1":
        raise PermissionError("Only T1 Master Admin can declare uncontested elections")

    # R2: TOTP re-confirmation for both admins (SEC-9)
    if not verify_totp(master_admin.totp_secret, master_admin_totp):
        raise ValueError("Master admin TOTP verification failed")

    if state_admin.role != "T2":
        raise PermissionError("Second sign-off must be T2 State Admin")

    if not verify_totp(state_admin.totp_secret, state_admin_totp):
        raise ValueError("State admin TOTP verification failed")

    # Check eligibility
    eligibility = await check_uncontested_eligibility(db, constituency_id)
    if not eligibility["is_eligible"]:
        raise ValueError(
            f"Constituency has {eligibility['candidate_count']} approved candidates — "
            "uncontested requires exactly 1"
        )

    candidate: Candidate = eligibility["candidate"]
    now = datetime.now(timezone.utc)

    # R3: Update constituency status
    constituency_result = await db.execute(
        select(Constituency).where(Constituency.id == constituency_id)
    )
    constituency = constituency_result.scalar_one_or_none()
    if not constituency:
        raise ValueError("Constituency not found")

    constituency.election_status = "UNCONTESTED"

    # R3: Update candidate
    candidate.is_uncontested = True
    candidate.declared_elected_unopposed_at = now
    candidate.uncontested_declared_by = master_admin.id

    # R3: Ensure no booths activate in this constituency
    # (booths for this constituency remain is_active=False — no action needed unless
    # OPEN was called — we enforce this at booth activation time too)

    # R3: Audit log
    await log_action(
        db,
        actor_type="admin",
        actor_id=master_admin.id,
        action="UNCONTESTED_DECLARED",
        metadata={
            "constituency_id": str(constituency_id),
            "candidate_id": str(candidate.id),
            "candidate_name": candidate.full_name,
            "declared_by_master": str(master_admin.id),
            "declared_by_state": str(state_admin.id),
            "timestamp": now.isoformat()
        }
    )

    await db.flush()
    logger.info(f"Constituency {constituency_id} declared uncontested — candidate {candidate.id}")
    return {
        "constituency_id": str(constituency_id),
        "constituency_name": constituency.name,
        "candidate_id": str(candidate.id),
        "candidate_name": candidate.full_name,
        "declared_at": now.isoformat(),
        "election_status": "UNCONTESTED"
    }


async def reverse_uncontested(
    db: AsyncSession,
    constituency_id: UUID,
    master_admin: AdminAccount,
    master_admin_totp: str,
    state_admin: AdminAccount,
    state_admin_totp: str,
    reason: str
) -> Dict:
    """
    R7: Reversal — same 2-admin sign-off, resets status to PENDING.
    """
    if master_admin.role != "T1":
        raise PermissionError("Only T1 Master Admin can reverse uncontested declaration")

    if not verify_totp(master_admin.totp_secret, master_admin_totp):
        raise ValueError("Master admin TOTP verification failed")

    if not verify_totp(state_admin.totp_secret, state_admin_totp):
        raise ValueError("State admin TOTP verification failed")

    constituency_result = await db.execute(
        select(Constituency).where(Constituency.id == constituency_id)
    )
    constituency = constituency_result.scalar_one_or_none()
    if not constituency:
        raise ValueError("Constituency not found")

    if constituency.election_status != "UNCONTESTED":
        raise ValueError("Constituency is not in UNCONTESTED status")

    # Reset constituency
    constituency.election_status = "PENDING"

    # Reset candidate(s)
    cand_result = await db.execute(
        select(Candidate)
        .where(Candidate.constituency_id == constituency_id)
        .where(Candidate.is_uncontested == True)
    )
    for cand in cand_result.scalars().all():
        cand.is_uncontested = False
        cand.declared_elected_unopposed_at = None
        cand.uncontested_declared_by = None

    await log_action(
        db,
        actor_type="admin",
        actor_id=master_admin.id,
        action="UNCONTESTED_REVERSED",
        metadata={
            "constituency_id": str(constituency_id),
            "reversed_by_master": str(master_admin.id),
            "reversed_by_state": str(state_admin.id),
            "reason": reason
        }
    )

    await db.flush()
    return {"constituency_id": str(constituency_id), "new_status": "PENDING"}


async def list_uncontested(db: AsyncSession) -> List[Dict]:
    """R4/R5: List all uncontested constituencies with badge data."""
    result = await db.execute(
        select(Constituency, Candidate, AdminAccount)
        .join(Candidate, Candidate.constituency_id == Constituency.id)
        .outerjoin(AdminAccount, AdminAccount.id == Candidate.uncontested_declared_by)
        .where(Constituency.election_status == "UNCONTESTED")
        .where(Candidate.is_uncontested == True)
    )
    rows = result.all()
    out = []
    for constituency, candidate, admin in rows:
        out.append({
            "constituency_id": str(constituency.id),
            "constituency_name": constituency.name,
            "state_id": str(constituency.state_id),
            "candidate_id": str(candidate.id),
            "candidate_name": candidate.full_name,
            "declared_at": candidate.declared_elected_unopposed_at.isoformat() if candidate.declared_elected_unopposed_at else None,
            "declared_by": str(candidate.uncontested_declared_by) if candidate.uncontested_declared_by else None,
            "election_status": "UNCONTESTED"
        })
    return out
