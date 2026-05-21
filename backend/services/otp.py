"""
OTP service.
SEC-5: OTPs expire in 5 min, max 3 attempts, stored as SHA-256(otp) only.
R8: OTP_PRINT_FALLBACK if SMS fails (60-second expiry thermal slip).
"""
import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.config import settings
from backend.models import OTPRecord

logger = logging.getLogger(__name__)


def _generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


async def create_otp(db: AsyncSession, voter_id: UUID, thermal: bool = False) -> str:
    """Generate OTP, store hash in DB, return plaintext OTP."""
    otp = _generate_otp()
    expire_seconds = settings.OTP_THERMAL_EXPIRE_SECONDS if thermal else settings.OTP_EXPIRE_SECONDS
    record = OTPRecord(
        id=uuid4(),
        voter_id=voter_id,
        otp_hash=_hash_otp(otp),
        attempts=0,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expire_seconds),
        is_used=False,
        delivery_method="thermal" if thermal else "sms"
    )
    db.add(record)
    await db.flush()
    return otp


async def verify_otp(db: AsyncSession, voter_id: UUID, entered_otp: str) -> Tuple[bool, int]:
    """
    Verify OTP. Returns (success, attempts_remaining).
    SEC-5: max 3 attempts, 5-min expiry.
    """
    result = await db.execute(
        select(OTPRecord)
        .where(OTPRecord.voter_id == voter_id)
        .where(OTPRecord.is_used == False)
        .where(OTPRecord.expires_at > datetime.now(timezone.utc))
        .order_by(OTPRecord.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        return False, 0

    if record.attempts >= settings.OTP_MAX_ATTEMPTS:
        return False, 0

    record.attempts += 1
    remaining = settings.OTP_MAX_ATTEMPTS - record.attempts

    if record.otp_hash == _hash_otp(entered_otp):
        record.is_used = True
        await db.flush()
        return True, remaining

    await db.flush()
    return False, remaining


async def send_otp_sms(mobile: str, otp: str, language: str = "en") -> Tuple[bool, str]:
    """Send OTP via Twilio (primary) or MSG91 (fallback)."""
    msg = _build_otp_message(otp, language)
    success = await _send_twilio(mobile, msg)
    if success:
        return True, "twilio"
    success = await _send_msg91(mobile, msg)
    if success:
        return True, "msg91"
    return False, "failed"


def _build_otp_message(otp: str, language: str) -> str:
    messages = {
        "hi": f"आपका MatSetu मतदान OTP है: {otp}। यह {settings.OTP_EXPIRE_SECONDS // 60} मिनट में समाप्त होगा।",
        "en": f"Your MatSetu voting OTP is: {otp}. Valid for {settings.OTP_EXPIRE_SECONDS // 60} minutes.",
        "gu": f"તમારો MatSetu મતદાન OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} મિનિટ માટે માન્ય.",
        "ta": f"உங்கள் MatSetu வாக்கு OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} நிமிடங்களுக்கு செல்லுபடியாகும்.",
        "te": f"మీ MatSetu ఓటింగ్ OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} నిమిషాలు చెల్లుబాటు.",
        "mr": f"तुमचा MatSetu मतदान OTP: {otp}. {settings.OTP_EXPIRE_SECONDS // 60} मिनिटांसाठी वैध.",
        "bn": f"আপনার MatSetu ভোটদান OTP: {otp}। {settings.OTP_EXPIRE_SECONDS // 60} মিনিটের জন্য বৈধ।",
    }
    return messages.get(language, messages["en"])


async def _send_twilio(mobile: str, message: str) -> bool:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured")
        return False
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(to=mobile, from_=settings.TWILIO_FROM_NUMBER, body=message)
        return True
    except Exception as e:
        logger.error(f"Twilio send failed: {e}")
        return False


async def _send_msg91(mobile: str, message: str) -> bool:
    if not settings.MSG91_AUTH_KEY:
        logger.warning("MSG91 auth key not configured")
        return False
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/flow/",
                json={
                    "authkey": settings.MSG91_AUTH_KEY,
                    "sender": settings.MSG91_SENDER_ID,
                    "mobiles": mobile,
                    "message": message
                },
                timeout=10
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"MSG91 send failed: {e}")
        return False
