"""
Server-Sent Events (SSE) router.
Real-time dashboard updates: vote counts, anomalies, booth status.
"""
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database import get_db, AsyncSessionLocal
from backend.models import Voter, Booth, AnomalyEvent, Constituency
from backend.services.vote import get_tally
from backend.core.rls import require_role
import logging

router = APIRouter(prefix="/api/v1/sse", tags=["sse"])
logger = logging.getLogger(__name__)


async def _national_tally_stream(request: Request) -> AsyncGenerator[str, None]:
    """Stream national vote tally every 5 seconds."""
    while True:
        if await request.is_disconnected():
            break
        try:
            async with AsyncSessionLocal() as db:
                total_voted = (await db.execute(
                    select(func.count(Voter.id)).where(Voter.has_voted == True)
                )).scalar() or 0
                total_voters = (await db.execute(
                    select(func.count(Voter.id))
                )).scalar() or 1
                active_booths = (await db.execute(
                    select(func.count(Booth.id)).where(Booth.is_active == True)
                )).scalar() or 0
                anomaly_count = (await db.execute(
                    select(func.count(AnomalyEvent.id)).where(AnomalyEvent.is_resolved == False)
                )).scalar() or 0

            data = {
                "event": "tally_update",
                "total_voted": total_voted,
                "total_voters": total_voters,
                "turnout_percent": round(total_voted / total_voters * 100, 2),
                "active_booths": active_booths,
                "anomaly_count": anomaly_count,
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            logger.error(f"SSE tally stream error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        await asyncio.sleep(5)


async def _booth_status_stream(request: Request, booth_id: str) -> AsyncGenerator[str, None]:
    """Stream booth-level vote count every 3 seconds."""
    while True:
        if await request.is_disconnected():
            break
        try:
            tally = await get_tally("booth", booth_id)
            data = {
                "event": "booth_tally",
                "booth_id": booth_id,
                "total": tally["total"],
                "candidate_tallies": tally["candidate_tallies"],
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        await asyncio.sleep(3)


async def _anomaly_stream(request: Request) -> AsyncGenerator[str, None]:
    """Stream new unresolved anomalies every 10 seconds."""
    last_seen_id = None
    while True:
        if await request.is_disconnected():
            break
        try:
            async with AsyncSessionLocal() as db:
                query = select(AnomalyEvent).where(
                    AnomalyEvent.is_resolved == False
                ).order_by(AnomalyEvent.created_at.desc()).limit(10)
                result = await db.execute(query)
                events = result.scalars().all()

            for event in reversed(events):
                if last_seen_id is None or str(event.id) != str(last_seen_id):
                    data = {
                        "event": "anomaly",
                        "id": str(event.id),
                        "flag_type": event.flag_type,
                        "booth_id": str(event.booth_id) if event.booth_id else None,
                        "details": event.details,
                        "created_at": event.created_at.isoformat()
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            if events:
                last_seen_id = str(events[0].id)
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        await asyncio.sleep(10)


@router.get("/tally/national")
async def sse_national_tally(
    request: Request,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4", "T5"))
):
    """SSE: National tally stream (every 5s)."""
    return StreamingResponse(
        _national_tally_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/tally/booth/{booth_id}")
async def sse_booth_tally(
    request: Request,
    booth_id: str,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4", "T5", "T6"))
):
    """SSE: Booth-level tally stream (every 3s)."""
    return StreamingResponse(
        _booth_status_stream(request, booth_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/anomalies")
async def sse_anomalies(
    request: Request,
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4"))
):
    """SSE: Anomaly event stream (every 10s)."""
    return StreamingResponse(
        _anomaly_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
