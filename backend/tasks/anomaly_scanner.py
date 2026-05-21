import logging
import math
from datetime import datetime, timedelta, timezone
from celery import shared_task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.tasks.send_otp import celery_app
from backend.models import WorkerLocTrail, AnomalyEvent, Booth, Worker

logger = logging.getLogger(__name__)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius of earth in meters
    phi_1 = math.radians(float(lat1))
    phi_2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2 - lat1))
    delta_lambda = math.radians(float(lon2 - lon1))
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@celery_app.task(name="backend.tasks.anomaly_scanner.scan_location_anomalies")
def scan_location_anomalies():
    """
    Periodic task to scan WorkerLocTrail and detect cross-booth movement or GPS violations.
    Runs every 60 seconds.
    """
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(engine)
    
    with Session() as session:
        # Check recent worker loc trails (last 5 minutes)
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        recent_trails = session.query(WorkerLocTrail).filter(WorkerLocTrail.recorded_at >= recent_time).all()
        
        for trail in recent_trails:
            if not trail.gps_lat or not trail.gps_lng or not trail.booth_id:
                continue
            
            # Fetch assigned booth
            booth = session.query(Booth).filter(Booth.id == trail.booth_id).first()
            if not booth or not booth.gps_lat or not booth.gps_lng:
                continue
            
            # Distance from assigned booth
            distance_m = haversine_distance(trail.gps_lat, trail.gps_lng, booth.gps_lat, booth.gps_lng)
            if distance_m > 500:
                # Check if anomaly already logged recently to avoid spam
                existing = session.query(AnomalyEvent).filter(
                    AnomalyEvent.worker_id == trail.worker_id,
                    AnomalyEvent.flag_type == "FLAG_GPS_VIOLATION",
                    AnomalyEvent.is_resolved == False
                ).first()
                if not existing:
                    import uuid
                    anomaly = AnomalyEvent(
                        id=uuid.uuid4(),
                        flag_type="FLAG_GPS_VIOLATION",
                        booth_id=booth.id,
                        worker_id=trail.worker_id,
                        details={"distance_m": round(distance_m, 2), "lat": float(trail.gps_lat), "lng": float(trail.gps_lng)},
                        created_at=datetime.now(timezone.utc),
                        is_resolved=False
                    )
                    session.add(anomaly)
                    logger.warning(f"Worker {trail.worker_id} GPS violation: {distance_m}m from booth")

        # Cross-booth movement (velocity check)
        # Fetch last 2 trails for each active worker within last 1 hour
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        workers = session.query(Worker).filter(Worker.is_active == True).all()
        for worker in workers:
            trails = session.query(WorkerLocTrail).filter(
                WorkerLocTrail.worker_id == worker.id,
                WorkerLocTrail.recorded_at >= one_hour_ago
            ).order_by(WorkerLocTrail.recorded_at.desc()).limit(2).all()
            
            if len(trails) == 2:
                t1, t2 = trails[0], trails[1]  # t1 is more recent
                if t1.booth_id != t2.booth_id and t1.gps_lat and t2.gps_lat:
                    dist = haversine_distance(t1.gps_lat, t1.gps_lng, t2.gps_lat, t2.gps_lng)
                    time_diff_s = (t1.recorded_at - t2.recorded_at).total_seconds()
                    
                    if time_diff_s > 0:
                        velocity_m_s = dist / time_diff_s
                        velocity_km_h = velocity_m_s * 3.6
                        
                        # Threshold: e.g. > 100 km/h is impossible movement
                        if velocity_km_h > 100:
                            existing = session.query(AnomalyEvent).filter(
                                AnomalyEvent.worker_id == worker.id,
                                AnomalyEvent.flag_type == "FLAG_IMPOSSIBLE_MOVEMENT",
                                AnomalyEvent.is_resolved == False
                            ).first()
                            
                            if not existing:
                                import uuid
                                anomaly = AnomalyEvent(
                                    id=uuid.uuid4(),
                                    flag_type="FLAG_IMPOSSIBLE_MOVEMENT",
                                    worker_id=worker.id,
                                    details={
                                        "velocity_km_h": round(velocity_km_h, 2),
                                        "distance_m": round(dist, 2),
                                        "time_diff_s": round(time_diff_s, 2),
                                        "from_booth": str(t2.booth_id),
                                        "to_booth": str(t1.booth_id)
                                    },
                                    created_at=datetime.now(timezone.utc),
                                    is_resolved=False
                                )
                                session.add(anomaly)
                                logger.warning(f"Worker {worker.id} impossible movement: {velocity_km_h} km/h")
        
        session.commit()

# Register beat schedule
if not hasattr(celery_app.conf, "beat_schedule"):
    celery_app.conf.beat_schedule = {}

celery_app.conf.beat_schedule["scan-location-anomalies-every-60s"] = {
    "task": "backend.tasks.anomaly_scanner.scan_location_anomalies",
    "schedule": 60.0,
}
