import pyotp
import base64
from cryptography.fernet import Fernet
from backend.config import settings
import os

# Derive a Fernet key from SECRET_KEY (must be 32 bytes base64url-encoded)
_raw = settings.SECRET_KEY.encode()[:32].ljust(32, b"0")
FERNET_KEY = base64.urlsafe_b64encode(_raw)
_cipher = Fernet(FERNET_KEY)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return _cipher.encrypt(secret.encode()).decode()


def decrypt_totp_secret(encrypted: str) -> str:
    return _cipher.decrypt(encrypted.encode()).decode()


def get_totp_uri(secret: str, username: str) -> str:
    totp = pyotp.TOTP(secret, digits=settings.TOTP_DIGITS, interval=settings.TOTP_INTERVAL)
    return totp.provisioning_uri(name=username, issuer_name=settings.TOTP_ISSUER)


def verify_totp(encrypted_secret: str, code: str) -> bool:
    secret = decrypt_totp_secret(encrypted_secret)
    totp = pyotp.TOTP(secret, digits=settings.TOTP_DIGITS, interval=settings.TOTP_INTERVAL)
    # Allow 1 window tolerance (30s before/after)
    return totp.verify(code, valid_window=1)
