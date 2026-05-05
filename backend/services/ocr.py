"""
OCR service for EPIC / E-EPIC QR card scanning.
Uses Tesseract 5 for text extraction.
"""
import base64
import re
import logging
from typing import Optional, Dict
import numpy as np

logger = logging.getLogger(__name__)


def extract_epic_from_image(image_b64: str) -> Optional[str]:
    """
    Use Tesseract to extract EPIC number from voter ID card image.
    Returns EPIC number string or None.
    """
    try:
        import pytesseract
        import cv2

        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # Pre-process: grayscale + denoise + threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Tesseract PSM 6: uniform block of text
        config = "--psm 6 -l eng"
        text = pytesseract.image_to_string(thresh, config=config)

        # EPIC format: 3 letters + 7 digits (e.g. ABC1234567) or state variations
        match = re.search(r"\b([A-Z]{2,3}[0-9]{7,8})\b", text)
        if match:
            return match.group(1)

        # E-EPIC QR code fallback — scan QR
        qr_result = _scan_qr(img)
        if qr_result:
            return qr_result

        return None
    except ImportError:
        logger.warning("pytesseract not installed — using mock EPIC extraction")
        return None
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return None


def _scan_qr(img: np.ndarray) -> Optional[str]:
    """Scan QR code from image for E-EPIC."""
    try:
        import cv2
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data:
            # E-EPIC QR contains JSON with EPIC number
            import json
            try:
                payload = json.loads(data)
                return payload.get("epicNumber") or payload.get("epic_number") or payload.get("vid")
            except json.JSONDecodeError:
                # Plain EPIC string
                if re.match(r"^[A-Z]{2,3}[0-9]{7,8}$", data):
                    return data
        return None
    except Exception as e:
        logger.error(f"QR scan error: {e}")
        return None
