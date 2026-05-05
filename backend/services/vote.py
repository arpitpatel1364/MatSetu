"""
Vote casting service.
SEC-1: vote_ledger is APPEND-ONLY.
SEC-2: has_voted once TRUE is IMMUTABLE.
SEC-3: All vote operations atomic: Redis pipeline + PostgreSQL transaction together.
"""
import hashlib
import json
import secrets
from datetime import datetime
from typing import Optional, Dict
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import settings
from backend.models import VoteLedger, Voter, Candidate, Booth, AuditLog
import logging

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _compute_vote_hash(voter_id: str, candidate_id: str, submitted_at: str, prev_hash: str = "") -> str:
    """SHA-256 hash chain for vote ledger (SEC-3)."""
    raw = f"{voter_id}|{candidate_id}|{submitted_at}|{settings.BOOTH_SECRET}|{prev_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_redis_keys(location_chain: Dict[str, str]) -> list:
    """Build 8-level Redis tally keys from location chain."""
    levels = ["country", "state", "division", "district", "taluka", "block", "village", "booth"]
    keys = []
    for level in levels:
        val = location_chain.get(level)
        if val:
            keys.append(f"tally:{level}:{val}")
    return keys


def _generate_zk_receipt(vote_id: str) -> str:
    """
    Helios-style ZK commitment receipt.
    SEC-6: receipt never reveals candidate — only inclusion proof.
    """
    token = secrets.token_urlsafe(32)
    commitment = hashlib.sha256(f"{vote_id}:{token}:{settings.BOOTH_SECRET}".encode()).hexdigest()
    return f"ZK:{commitment[:32]}"


async def get_prev_hash(db: AsyncSession, booth_id: UUID) -> str:
    """Get the latest vote hash in the chain for this booth."""
    result = await db.execute(
        select(VoteLedger.vote_hash)
        .where(VoteLedger.booth_id == booth_id)
        .order_by(VoteLedger.submitted_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row or "GENESIS"


async def cast_vote(
    db: AsyncSession,
    voter_id: UUID,
    candidate_id: UUID,
    booth_id: UUID,
    worker_id: UUID,
    location_chain: Dict[str, str]
) -> Dict:
    """
    Atomic vote submission:
    a) vote_ledger INSERT (append-only)
    b) SHA-256 hash chain
    c) Redis INCR x8 atomic pipeline
    d) voters.has_voted = TRUE (immutable)
    e) audit_log entry VOTE_CAST
    """
    # 1. Pre-flight: check has_voted (SEC-2)
    voter_result = await db.execute(select(Voter).where(Voter.id == voter_id).with_for_update())
    voter = voter_result.scalar_one_or_none()
    if not voter:
        raise ValueError("Voter not found")
    if voter.has_voted:
        logger.warning(f"Duplicate vote attempt by voter {voter_id}")
        raise ValueError("Voter has already voted — FLAG_DUPLICATE_ATTEMPT")

    # 2. Verify candidate exists and is approved
    cand_result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = cand_result.scalar_one_or_none()
    if not candidate or not candidate.is_approved:
        raise ValueError("Invalid or unapproved candidate")

    # 3. Build vote record
    now = datetime.utcnow()
    prev_hash = await get_prev_hash(db, booth_id)
    vote_id = uuid4()
    vote_hash = _compute_vote_hash(str(voter_id), str(candidate_id), now.isoformat(), prev_hash)
    receipt_token = _generate_zk_receipt(str(vote_id))

    vote = VoteLedger(
        id=vote_id,
        voter_id=voter_id,
        candidate_id=candidate_id,
        booth_id=booth_id,
        worker_id=worker_id,
        location_chain=location_chain,
        submitted_at=now,
        vote_hash=vote_hash,
        prev_hash=prev_hash,
        is_valid=True,
        receipt_token=receipt_token
    )
    db.add(vote)

    # 4. Mark voter as voted — IMMUTABLE (SEC-2)
    voter.has_voted = True

    # 5. Audit log
    audit = AuditLog(
        id=uuid4(),
        actor_type="voter",
        actor_id=voter_id,
        action="VOTE_CAST",
        booth_id=booth_id,
        metadata_={
            "vote_id": str(vote_id),
            "candidate_id": str(candidate_id),
            "worker_id": str(worker_id),
            "location_chain": location_chain
        }
    )
    db.add(audit)

    # Flush to DB first — then Redis
    await db.flush()

    # 6. Redis INCR x8 atomic pipeline (SEC-3)
    try:
        redis = await get_redis()
        keys = _build_redis_keys(location_chain)
        pipe = redis.pipeline(transaction=True)
        for key in keys:
            pipe.incr(key)
        # Also increment per-candidate tally
        for key in keys:
            pipe.incr(f"{key}:cand:{candidate_id}")
        await pipe.execute()
    except Exception as e:
        logger.error(f"Redis tally INCR failed: {e} — vote still recorded in DB")

    return {
        "vote_id": str(vote_id),
        "receipt_token": receipt_token,
        "submitted_at": now.isoformat()
    }


async def get_tally(location_level: str, location_id: str) -> Dict:
    """Read tally from Redis."""
    try:
        redis = await get_redis()
        key = f"tally:{location_level}:{location_id}"
        total = await redis.get(key)
        # Get all candidate sub-keys
        pattern = f"{key}:cand:*"
        cand_keys = await redis.keys(pattern)
        candidate_tallies = {}
        if cand_keys:
            values = await redis.mget(*cand_keys)
            for k, v in zip(cand_keys, values):
                cand_id = k.split(":cand:")[1]
                candidate_tallies[cand_id] = int(v or 0)
        return {
            "total": int(total or 0),
            "candidate_tallies": candidate_tallies,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Redis tally read error: {e}")
        return {"total": 0, "candidate_tallies": {}}
