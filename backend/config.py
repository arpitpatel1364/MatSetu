from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MatSetu"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_256BIT_RANDOM"
    BOOTH_SECRET: str = "CHANGE_ME_BOOTH_SECRET_256BIT"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://matsetu:matsetu@localhost:5432/matsetu"
    DATABASE_URL_SYNC: str = "postgresql://matsetu:matsetu@localhost:5432/matsetu"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_VOTERS: str = "voter_faces"
    QDRANT_COLLECTION_WORKERS: str = "worker_faces"
    QDRANT_VECTOR_SIZE: int = 512

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_FACES: str = "matsetu-faces"
    MINIO_BUCKET_RECEIPTS: str = "matsetu-receipts"
    MINIO_SECURE: bool = False

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 1

    # OTP
    OTP_EXPIRE_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 3
    OTP_THERMAL_EXPIRE_SECONDS: int = 60

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # MSG91 fallback
    MSG91_AUTH_KEY: str = ""
    MSG91_SENDER_ID: str = "MATSETU"

    # Face recognition thresholds
    ARCFACE_SIMILARITY_THRESHOLD: float = 0.65
    LIVENESS_THRESHOLD: float = 0.7
    FACE_DRIFT_ALERT_THRESHOLD: float = 0.10
    WORKER_REAUTH_INTERVAL_MINUTES: int = 30
    WORKER_REAUTH_VOTE_COUNT: int = 20
    WORKER_BACKGROUND_CHECK_MINUTES: int = 5

    # GPS
    GPS_MAX_DISTANCE_METERS: int = 500
    GPS_IMPOSSIBLE_MOVEMENT_KM: float = 10.0
    GPS_IMPOSSIBLE_MOVEMENT_MINUTES: int = 10

    # Anomaly detection
    TURNOUT_DEVIATION_THRESHOLD: float = 0.15
    TURNOUT_DEVIATION_DURATION_MIN: int = 30

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # TOTP
    TOTP_ISSUER: str = "MatSetu-ECI"
    TOTP_DIGITS: int = 6
    TOTP_INTERVAL: int = 30

    # IP Allowlist enforcement
    T1_IP_ALLOWLIST_REQUIRED: bool = True
    T2_IP_ALLOWLIST_REQUIRED: bool = True

    # Supported languages (22 official Indian languages)
    SUPPORTED_LANGUAGES: List[str] = [
        "hi", "en", "bn", "te", "mr", "ta", "ur", "gu", "kn",
        "ml", "or", "pa", "as", "mai", "sat", "kok", "dog",
        "mni", "sd", "ks", "ne", "bo"
    ]

    # Nomination deadline enforcement
    NOMINATION_DEADLINE_STRICT: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
