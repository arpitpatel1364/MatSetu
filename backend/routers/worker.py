"""
Worker authentication router.
T6 Worker auth: ArcFace + GPS + mTLS cert.
Re-auth every 30 min OR every 20 votes.
Background face check every 5 min.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID, uuid4
from datetime import datetime

from backend.database import get_db
from backend.models import Worker, WorkerLocTrail, Booth
from backend.services.face import extract_embedding, check_liveness, cosine_similarity
from backend.services.qdrant import search_face
from backend.services.gps import check_worker_gps
from backend.services.audit import log_action, raise_anomaly
from backend.core.jwt import create_access_token
from backend.config import settings
import logging

router = APIRouter(prefix="/api/v1/worker", tags=["worker"])
logger = logging.getLogger(__name__)


@router.post("/login")
async def worker_login(
    request: Request,
    employee_id: str,
    face_image_b64: str,
    gps_lat: float,
    gps_lng: float,
    gps_accuracy_m: int,
    device_id: str,
    booth_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Worker login: ArcFace face scan → GPS check → mTLS cert.
    Fires FLAG_GPS_VIOLATION or FLAG_IMPOSSIBLE_MOVEMENT on anomaly.
    """
    # Verify mTLS cert fingerprint from request headers
    cert_fingerprint = request.headers.get("X-Client-Cert-Fingerprint", "")

    # Find worker
    result = await db.execute(
        select(Worker)
        .where(Worker.employee_id == employee_id)
        .where(Worker.is_active == True)
    )
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Verify assigned booth
    if str(worker.booth_id) != str(booth_id):
        raise HTTPException(status_code=403, detail="Worker not assigned to this booth")

    # Verify mTLS cert
    booth_result = await db.execute(select(Booth).where(Booth.id == booth_id))
    booth = booth_result.scalar_one_or_none()
    if booth and booth.cert_fingerprint and cert_fingerprint != booth.cert_fingerprint:
        await raise_anomaly(db, "FLAG_GPS_VIOLATION", booth_id=booth_id, worker_id=worker.id,
                            details={"reason": "mTLS cert mismatch"})
        raise HTTPException(status_code=403, detail="mTLS certificate verification failed")

    # GPS check
    gps_ok, gps_flags = await check_worker_gps(db, worker.id, gps_lat, gps_lng, gps_accuracy_m)
    anomaly_flags = {}
    if gps_flags:
        for flag in gps_flags:
            anomaly_flags[flag] = True
            await raise_anomaly(db, flag.split(":")[0], booth_id=booth_id, worker_id=worker.id,
                                details={"gps_lat": gps_lat, "gps_lng": gps_lng})
        if not gps_ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"GPS validation failed: {', '.join(gps_flags)}"
            )

    # Face verification
    is_live, liveness_score = check_liveness(face_image_b64)
    if not is_live:
        await raise_anomaly(db, "FLAG_LIVENESS_FAIL", booth_id=booth_id, worker_id=worker.id,
                            details={"liveness_score": liveness_score})
        raise HTTPException(status_code=403, detail="Liveness check failed")

    embedding = extract_embedding(face_image_b64)
    if embedding is None:
        raise HTTPException(status_code=422, detail="No face detected")

    if worker.face_vector_id:
        matches = search_face(settings.QDRANT_COLLECTION_WORKERS, embedding, top_k=1)
        if not matches:
            raise HTTPException(status_code=403, detail="Face verification failed")
        _, similarity, _ = matches[0]
        if similarity < settings.ARCFACE_SIMILARITY_THRESHOLD:
            await raise_anomaly(db, "FLAG_FACE_DRIFT", booth_id=booth_id, worker_id=worker.id,
                                details={"similarity": similarity})
            raise HTTPException(status_code=403, detail="Face similarity too low")
    else:
        similarity = 1.0  # Not yet enrolled — allow login, force enrollment

    # Log location trail
    trail = WorkerLocTrail(
        id=uuid4(),
        worker_id=worker.id,
        event_type="LOGIN",
        booth_id=booth_id,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        gps_accuracy_m=gps_accuracy_m,
        face_similarity=similarity,
        device_id=device_id,
        recorded_at=datetime.utcnow(),
        anomaly_flags=anomaly_flags
    )
    db.add(trail)
    await log_action(db, "worker", worker.id, "WORKER_LOGIN", booth_id=booth_id,
                     metadata={"employee_id": employee_id, "device_id": device_id})

    # Issue worker JWT
    token = create_access_token({
        "sub": str(worker.id),
        "role": "T6",
        "scope_type": "one_booth",
        "scope_id": str(booth_id),
        "employee_id": employee_id
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "worker_id": str(worker.id),
        "booth_id": str(booth_id),
        "reauth_interval_min": settings.WORKER_REAUTH_INTERVAL_MINUTES,
        "reauth_vote_count": settings.WORKER_REAUTH_VOTE_COUNT
    }


@router.post("/reauth/{worker_id}")
async def worker_reauth(
    worker_id: UUID,
    face_image_b64: str,
    gps_lat: float,
    gps_lng: float,
    gps_accuracy_m: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Re-authentication every 30 min OR every 20 votes.
    Background face check trigger.
    """
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    is_live, liveness_score = check_liveness(face_image_b64)
    embedding = extract_embedding(face_image_b64)

    similarity = 1.0
    if worker.face_vector_id and embedding is not None:
        matches = search_face(settings.QDRANT_COLLECTION_WORKERS, embedding, top_k=1)
        if matches:
            _, similarity, _ = matches[0]
            # FLAG_FACE_DRIFT: similarity drops significantly
            if similarity < settings.ARCFACE_SIMILARITY_THRESHOLD - settings.FACE_DRIFT_ALERT_THRESHOLD:
                await raise_anomaly(db, "FLAG_FACE_DRIFT", booth_id=worker.booth_id,
                                    worker_id=worker_id,
                                    details={"similarity": similarity, "event": "REAUTH"})

    trail = WorkerLocTrail(
        id=uuid4(), worker_id=worker_id, event_type="REAUTH",
        booth_id=worker.booth_id, gps_lat=gps_lat, gps_lng=gps_lng,
        gps_accuracy_m=gps_accuracy_m, face_similarity=similarity,
        recorded_at=datetime.utcnow(), anomaly_flags={}
    )
    db.add(trail)
    await log_action(db, "worker", worker_id, "WORKER_REAUTH", booth_id=worker.booth_id)

    # Issue fresh JWT
    token = create_access_token({
        "sub": str(worker.id), "role": "T6",
        "scope_type": "one_booth", "scope_id": str(worker.booth_id)
    })
    return {"access_token": token, "similarity": similarity}
