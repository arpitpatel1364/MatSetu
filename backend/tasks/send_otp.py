"""
Celery tasks for async OTP dispatch.
Primary: Twilio SMS
Fallback: MSG91
Thermal print fallback (R8): 60-second expiry slip via booth printer.
"""
import asyncio
import logging
from celery import Celery
from backend.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "matsetu",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "backend.tasks.send_otp.send_otp_task": {"queue": "otp"},
        "backend.tasks.generate_receipt.generate_receipt_task": {"queue": "receipts"},
    }
)


@celery_app.task(
    name="backend.tasks.send_otp.send_otp_task",
    bind=True,
    max_retries=2,
    default_retry_delay=5
)
def send_otp_task(self, voter_id: str, mobile: str, language: str, booth_id: str):
    """
    Dispatch OTP via Twilio → MSG91 → thermal print fallback.
    R8: If SMS fails, signal booth printer for thermal OTP slip (60s expiry).
    """
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Use sync engine in Celery worker
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(engine)

    otp = _generate_otp()
    otp_hash = _hash_otp(otp)

    # Store OTP in DB
    with Session() as session:
        from datetime import datetime, timedelta
        import uuid
        from backend.models import OTPRecord

        # Expire old OTPs for this voter
        session.query(OTPRecord).filter(
            OTPRecord.voter_id == voter_id,
            OTPRecord.is_used == False
        ).update({"is_used": True})

        record = OTPRecord(
            id=uuid.uuid4(),
            voter_id=voter_id,
            otp_hash=otp_hash,
            attempts=0,
            expires_at=datetime.utcnow() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS),
            is_used=False,
            delivery_method="sms"
        )
        session.add(record)
        session.commit()

    # Try Twilio
    twilio_ok = _try_twilio(mobile, otp, language)
    if twilio_ok:
        logger.info(f"OTP sent via Twilio to {mobile[-4:]}")
        return {"method": "twilio", "success": True}

    # Try MSG91
    msg91_ok = _try_msg91(mobile, otp, language)
    if msg91_ok:
        logger.info(f"OTP sent via MSG91 to {mobile[-4:]}")
        return {"method": "msg91", "success": True}

    # R8: SMS failed — signal booth thermal printer
    logger.warning(f"SMS failed — triggering thermal print fallback for booth {booth_id}")
    _trigger_thermal_print(voter_id, otp, booth_id)

    # Update OTP record to thermal with 60-second expiry
    with Session() as session:
        from datetime import datetime, timedelta
        session.query(OTPRecord).filter(
            OTPRecord.voter_id == voter_id,
            OTPRecord.is_used == False
        ).update({
            "expires_at": datetime.utcnow() + timedelta(seconds=settings.OTP_THERMAL_EXPIRE_SECONDS),
            "delivery_method": "thermal"
        })
        # Audit log
        from backend.models import AuditLog
        import uuid
        session.add(AuditLog(
            id=uuid.uuid4(),
            actor_type="system",
            actor_id=uuid.UUID(voter_id),
            action="OTP_PRINT_FALLBACK",
            metadata_={"booth_id": booth_id, "reason": "SMS delivery failed"}
        ))
        session.commit()
    return {"method": "thermal", "success": True}


def _generate_otp(length: int = 6) -> str:
    import secrets
    import string
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _hash_otp(otp: str) -> str:
    import hashlib
    return hashlib.sha256(otp.encode()).hexdigest()


def _build_message(otp: str, language: str) -> str:
    messages = {
        "hi": f"MatSetu OTP: {otp}। {settings.OTP_EXPIRE_SECONDS // 60} मिनट में समाप्त।",
        "en": f"MatSetu OTP: {otp}. Expires in {settings.OTP_EXPIRE_SECONDS // 60} min.",
        "gu": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} મિનિટ.",
        "ta": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} நிமிடங்கள்.",
        "te": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} నిమిషాలు.",
        "mr": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} मिनिटे.",
        "bn": f"MatSetu OTP: {otp}। {settings.OTP_EXPIRE_SECONDS // 60} মিনিট।",
        "kn": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} ನಿಮಿಷಗಳು.",
        "ml": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} മിനിറ്റ്.",
        "pa": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} ਮਿੰਟ.",
        "or": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} ମିନିଟ.",
        "as": f"MatSetu OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} মিনিট.",
    }
    return messages.get(language, messages["en"])


def _try_twilio(mobile: str, otp: str, language: str) -> bool:
    if not settings.TWILIO_ACCOUNT_SID:
        return False
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            to=mobile,
            from_=settings.TWILIO_FROM_NUMBER,
            body=_build_message(otp, language)
        )
        return True
    except Exception as e:
        logger.error(f"Twilio error: {e}")
        return False


def _try_msg91(mobile: str, otp: str, language: str) -> bool:
    if not settings.MSG91_AUTH_KEY:
        return False
    try:
        import requests
        resp = requests.post(
            "https://api.msg91.com/api/v5/flow/",
            json={
                "authkey": settings.MSG91_AUTH_KEY,
                "sender": settings.MSG91_SENDER_ID,
                "mobiles": mobile,
                "message": _build_message(otp, language)
            },
            timeout=8
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"MSG91 error: {e}")
        return False


def _trigger_thermal_print(voter_id: str, otp: str, booth_id: str):
    """
    Signal booth thermal printer via Redis pub/sub.
    Booth UI listens and prints 60-second OTP slip.
    """
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        import json
        r.publish(
            f"booth:{booth_id}:thermal_print",
            json.dumps({
                "type": "OTP_PRINT",
                "voter_id": voter_id,
                "otp": otp,
                "expires_seconds": settings.OTP_THERMAL_EXPIRE_SECONDS
            })
        )
    except Exception as e:
        logger.error(f"Thermal print signal failed: {e}")
