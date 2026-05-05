from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import AuditLog, AnomalyEvent
import logging

logger = logging.getLogger(__name__)

VALID_ACTIONS = {
    "VOTER_SCAN", "OTP_SENT", "VOTE_CAST", "ANOMALY_FLAG", "ANOMALY_OVERRIDE",
    "OTP_PRINT_FALLBACK", "UNCONTESTED_DECLARED", "UNCONTESTED_REVERSED",
    "ELECTION_STARTED", "ELECTION_STOPPED", "WORKER_LOGIN", "WORKER_REAUTH",
    "ADMIN_LOGIN", "BOOTH_ACTIVATED", "BOOTH_DEACTIVATED",
    "FACE_ENROLL_VOTER", "FACE_ENROLL_WORKER", "HASH_CHAIN_VERIFY"
}


async def log_action(
    db: AsyncSession,
    actor_type: str,
    actor_id: UUID,
    action: str,
    booth_id: Optional[UUID] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Write to immutable audit log."""
    if action not in VALID_ACTIONS:
        logger.warning(f"Unknown audit action: {action}")
    entry = AuditLog(
        id=uuid4(),
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        booth_id=booth_id,
        metadata_=metadata or {},
        logged_at=datetime.utcnow(),
        is_tampered=False
    )
    db.add(entry)


async def raise_anomaly(
    db: AsyncSession,
    flag_type: str,
    booth_id: Optional[UUID] = None,
    worker_id: Optional[UUID] = None,
    voter_id: Optional[UUID] = None,
    details: Optional[Dict] = None
) -> AnomalyEvent:
    """Create anomaly event and corresponding audit log entry."""
    event = AnomalyEvent(
        id=uuid4(),
        flag_type=flag_type,
        booth_id=booth_id,
        worker_id=worker_id,
        voter_id=voter_id,
        details=details or {},
        is_resolved=False,
        created_at=datetime.utcnow()
    )
    db.add(event)
    await log_action(
        db,
        actor_type="system",
        actor_id=worker_id or voter_id or uuid4(),
        action="ANOMALY_FLAG",
        booth_id=booth_id,
        metadata={"flag_type": flag_type, "details": details or {}}
    )
    return event
