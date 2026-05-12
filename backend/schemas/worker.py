from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class WorkerLoginRequest(BaseModel):
    employee_id: str
    face_image_b64: str
    gps_lat: float
    gps_lng: float
    gps_accuracy_m: int
    device_id: str
    booth_id: UUID

class WorkerReauthRequest(BaseModel):
    face_image_b64: str
    gps_lat: float
    gps_lng: float
    gps_accuracy_m: int
