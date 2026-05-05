from backend.services.face import extract_embedding, check_liveness, cosine_similarity
from backend.services.qdrant import get_client, ensure_collections, upsert_face, search_face
from backend.services.otp import create_otp, verify_otp, send_otp_sms
from backend.services.vote import cast_vote, get_tally
from backend.services.audit import log_action, raise_anomaly
from backend.services.uncontested import declare_uncontested, reverse_uncontested, list_uncontested
from backend.services.ocr import extract_epic_from_image
from backend.services.gps import check_worker_gps, haversine_distance_m
