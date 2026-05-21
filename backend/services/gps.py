"""
GPS anomaly detection.
FLAG_GPS_VIOLATION: worker >500m from assigned booth at login.
FLAG_IMPOSSIBLE_MOVEMENT: worker at 2 booths >10km apart within 10 min.
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import WorkerLocTrail, Booth, Worker
from backend.config import settings
import logging

logger = logging.getLogger(__name__)


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in meters between two GPS coordinates."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def check_worker_gps(
    db: AsyncSession,
    worker_id: UUID,
    gps_lat: float,
    gps_lng: float,
    gps_accuracy_m: int
) -> Tuple[bool, list]:
    """
    Returns (ok, list_of_flags).
    Checks GPS_VIOLATION and IMPOSSIBLE_MOVEMENT.
    """
    flags = []

    # Get worker's assigned booth
    worker_result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = worker_result.scalar_one_or_none()
    if not worker:
        return False, ["WORKER_NOT_FOUND"]

    booth_result = await db.execute(select(Booth).where(Booth.id == worker.booth_id))
    booth = booth_result.scalar_one_or_none()
    if booth and booth.gps_lat and booth.gps_lng:
        dist = haversine_distance_m(
            float(booth.gps_lat), float(booth.gps_lng),
            gps_lat, gps_lng
        )

        if dist > settings.GPS_MAX_DISTANCE_METERS:
            flags.append(f"FLAG_GPS_VIOLATION:distance={dist:.0f}m")
            logger.warning(f"Worker {worker_id} is {dist:.0f}m from booth {worker.booth_id}")

    # Check impossible movement
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.GPS_IMPOSSIBLE_MOVEMENT_MINUTES)
    recent_result = await db.execute(
        select(WorkerLocTrail)
        .where(WorkerLocTrail.worker_id == worker_id)
        .where(WorkerLocTrail.recorded_at >= cutoff)
        .order_by(WorkerLocTrail.recorded_at.desc())
        .limit(5)
    )
    recent_locs = recent_result.scalars().all()

    for loc in recent_locs:
        if loc.gps_lat and loc.gps_lng:
            prev_dist = haversine_distance_m(
                float(loc.gps_lat), float(loc.gps_lng),
                gps_lat, gps_lng
            )
            if prev_dist > settings.GPS_IMPOSSIBLE_MOVEMENT_KM * 1000:
                flags.append(f"FLAG_IMPOSSIBLE_MOVEMENT:dist={prev_dist/1000:.1f}km")
                break

    return len(flags) == 0, flags
