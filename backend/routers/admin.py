from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID, uuid4
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models import (
    Booth, Worker, AnomalyEvent, AdminAccount, Constituency,
    Voter, VoteLedger, Candidate
)
from backend.schemas.admin import (
    BoothCreateRequest, BoothResponse, WorkerCreateRequest,
    AnomalyEventResponse, AnomalyOverrideRequest,
    ElectionStartRequest, ElectionStopRequest, DashboardStatsResponse
)
from backend.services.audit import log_action
from backend.core.rls import require_role, get_current_admin
from backend.core.totp import verify_totp
import logging

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.get("/dashboard", response_model=DashboardStatsResponse)
async def dashboard(
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4", "T5")),
    db: AsyncSession = Depends(get_db)
):
    total_voters = (await db.execute(select(func.count(Voter.id)))).scalar() or 0
    total_voted = (await db.execute(
        select(func.count(Voter.id)).where(Voter.has_voted == True)
    )).scalar() or 0
    active_booths = (await db.execute(
        select(func.count(Booth.id)).where(Booth.is_active == True)
    )).scalar() or 0
    total_booths = (await db.execute(select(func.count(Booth.id)))).scalar() or 0
    anomaly_count = (await db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.is_resolved == False)
    )).scalar() or 0
    uncontested_count = (await db.execute(
        select(func.count(Constituency.id)).where(Constituency.election_status == "UNCONTESTED")
    )).scalar() or 0

    return DashboardStatsResponse(
        total_voters=total_voters,
        total_voted=total_voted,
        turnout_percent=round(total_voted / total_voters * 100, 2) if total_voters else 0.0,
        active_booths=active_booths,
        total_booths=total_booths,
        anomaly_count=anomaly_count,
        uncontested_count=uncontested_count,
        last_updated=datetime.utcnow()
    )


@router.post("/booth", response_model=BoothResponse)
async def create_booth(
    body: BoothCreateRequest,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    booth = Booth(id=uuid4(), **body.model_dump())
    db.add(booth)
    await db.flush()
    return BoothResponse.model_validate(booth)


@router.post("/booth/{booth_id}/activate")
async def activate_booth(
    booth_id: UUID,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    """Activate booth — checks constituency is not UNCONTESTED (R3)."""
    result = await db.execute(select(Booth).where(Booth.id == booth_id))
    booth = result.scalar_one_or_none()
    if not booth:
        raise HTTPException(status_code=404, detail="Booth not found")

    # R3: Do not activate booths in UNCONTESTED constituencies
    const_result = await db.execute(
        select(Constituency).where(Constituency.id == booth.constituency_id)
    )
    constituency = const_result.scalar_one_or_none()
    if constituency and constituency.election_status == "UNCONTESTED":
        raise HTTPException(
            status_code=400,
            detail="R3: Cannot activate booth — constituency is UNCONTESTED. No voting takes place."
        )

    booth.is_active = True
    await log_action(db, "admin", UUID(payload["sub"]), "BOOTH_ACTIVATED",
                     booth_id=booth_id)
    return {"booth_id": str(booth_id), "is_active": True}


@router.post("/booth/{booth_id}/deactivate")
async def deactivate_booth(
    booth_id: UUID,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Booth).where(Booth.id == booth_id))
    booth = result.scalar_one_or_none()
    if not booth:
        raise HTTPException(status_code=404, detail="Booth not found")
    booth.is_active = False
    await log_action(db, "admin", UUID(payload["sub"]), "BOOTH_DEACTIVATED", booth_id=booth_id)
    return {"booth_id": str(booth_id), "is_active": False}


@router.post("/election/start")
async def start_election(
    body: ElectionStartRequest,
    payload: dict = Depends(require_role("T1")),
    db: AsyncSession = Depends(get_db)
):
    """SEC-9: Election start requires TOTP re-confirmation."""
    admin_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == payload["sub"])
    )
    admin = admin_result.scalar_one_or_none()
    if not admin or not verify_totp(admin.totp_secret, body.totp_code):
        raise HTTPException(status_code=401, detail="TOTP verification failed")

    query = select(Constituency).where(Constituency.election_status == "PENDING")
    if body.constituency_ids:
        query = query.where(Constituency.id.in_(body.constituency_ids))
    result = await db.execute(query)
    constituencies = result.scalars().all()

    activated = 0
    for c in constituencies:
        if c.election_status != "UNCONTESTED":
            c.election_status = "OPEN"
            activated += 1

    await log_action(db, "admin", UUID(payload["sub"]), "ELECTION_STARTED",
                     metadata={"constituencies_opened": activated})
    return {"message": f"Election started for {activated} constituencies"}


@router.post("/election/stop")
async def stop_election(
    body: ElectionStopRequest,
    payload: dict = Depends(require_role("T1")),
    db: AsyncSession = Depends(get_db)
):
    """SEC-9: Election stop requires TOTP re-confirmation."""
    admin_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == payload["sub"])
    )
    admin = admin_result.scalar_one_or_none()
    if not admin or not verify_totp(admin.totp_secret, body.totp_code):
        raise HTTPException(status_code=401, detail="TOTP verification failed")

    query = select(Constituency).where(Constituency.election_status == "OPEN")
    if body.constituency_ids:
        query = query.where(Constituency.id.in_(body.constituency_ids))
    result = await db.execute(query)
    constituencies = result.scalars().all()
    for c in constituencies:
        c.election_status = "CLOSED"

    # Also deactivate all active booths
    booth_result = await db.execute(select(Booth).where(Booth.is_active == True))
    for booth in booth_result.scalars().all():
        booth.is_active = False

    await log_action(db, "admin", UUID(payload["sub"]), "ELECTION_STOPPED",
                     metadata={"constituencies_closed": len(constituencies)})
    return {"message": f"Election closed for {len(constituencies)} constituencies"}


@router.get("/anomalies", response_model=list[AnomalyEventResponse])
async def list_anomalies(
    resolved: bool = False,
    limit: int = 100,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AnomalyEvent)
        .where(AnomalyEvent.is_resolved == resolved)
        .order_by(AnomalyEvent.created_at.desc())
        .limit(limit)
    )
    return [AnomalyEventResponse.model_validate(e) for e in result.scalars().all()]


@router.post("/anomaly/{anomaly_id}/override")
async def override_anomaly(
    anomaly_id: UUID,
    body: AnomalyOverrideRequest,
    payload: dict = Depends(require_role("T1", "T2", "T3")),
    db: AsyncSession = Depends(get_db)
):
    """SEC-8: Manual override requires TOTP + audit log ANOMALY_OVERRIDE entry."""
    admin_result = await db.execute(select(AdminAccount).where(AdminAccount.id == payload["sub"]))
    admin = admin_result.scalar_one_or_none()
    if not admin or not verify_totp(admin.totp_secret, body.totp_code):
        raise HTTPException(status_code=401, detail="TOTP verification failed")

    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Anomaly event not found")

    event.is_resolved = True
    event.resolved_by = UUID(payload["sub"])
    event.override_reason = body.reason
    event.resolved_at = datetime.utcnow()

    await log_action(db, "admin", UUID(payload["sub"]), "ANOMALY_OVERRIDE",
                     booth_id=event.booth_id,
                     metadata={"anomaly_id": str(anomaly_id), "reason": body.reason})
    return {"message": "Anomaly resolved", "anomaly_id": str(anomaly_id)}


@router.post("/worker", response_model=dict)
async def create_worker(
    body: WorkerCreateRequest,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    worker = Worker(id=uuid4(), **body.model_dump())
    db.add(worker)
    await db.flush()
    return {"worker_id": str(worker.id), "message": "Worker created — enroll face to activate"}


@router.get("/audit-log")
async def get_audit_log(
    action: str = None,
    limit: int = 100,
    payload: dict = Depends(require_role("T1", "T2")),
    db: AsyncSession = Depends(get_db)
):
    """SEC-10: Master Admin has read-only on audit_log. No write access."""
    from backend.models import AuditLog
    query = select(AuditLog).order_by(AuditLog.logged_at.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id),
            "actor_type": l.actor_type,
            "actor_id": str(l.actor_id),
            "action": l.action,
            "booth_id": str(l.booth_id) if l.booth_id else None,
            "metadata": l.metadata_,
            "logged_at": l.logged_at.isoformat()
        }
        for l in logs
    ]
