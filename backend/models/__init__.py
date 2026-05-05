import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text,
    Integer, Numeric, CHAR, ARRAY, UniqueConstraint, Index,
    CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, TIMESTAMPTZ
from sqlalchemy.orm import relationship
from backend.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ──────────────────────────────────────────────
# Geographic hierarchy tables
# ──────────────────────────────────────────────

class Country(Base):
    __tablename__ = "countries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(CHAR(2), unique=True, nullable=False)


class State(Base):
    __tablename__ = "states"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_id = Column(UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False)
    name = Column(String(100), nullable=False)
    code = Column(CHAR(2), unique=True, nullable=False)
    country = relationship("Country")


class Division(Base):
    __tablename__ = "divisions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state_id = Column(UUID(as_uuid=True), ForeignKey("states.id"), nullable=False)
    name = Column(String(100), nullable=False)
    state = relationship("State")


class District(Base):
    __tablename__ = "districts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    division_id = Column(UUID(as_uuid=True), ForeignKey("divisions.id"), nullable=False)
    state_id = Column(UUID(as_uuid=True), ForeignKey("states.id"), nullable=False)
    name = Column(String(100), nullable=False)
    division = relationship("Division")
    state = relationship("State")


class Taluka(Base):
    __tablename__ = "talukas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"), nullable=False)
    name = Column(String(100), nullable=False)
    district = relationship("District")


class Block(Base):
    __tablename__ = "blocks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    taluka_id = Column(UUID(as_uuid=True), ForeignKey("talukas.id"), nullable=False)
    name = Column(String(100), nullable=False)
    taluka = relationship("Taluka")


class Village(Base):
    __tablename__ = "villages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    block_id = Column(UUID(as_uuid=True), ForeignKey("blocks.id"), nullable=False)
    name = Column(String(100), nullable=False)
    block = relationship("Block")


# ──────────────────────────────────────────────
# Party
# ──────────────────────────────────────────────

class Party(Base):
    __tablename__ = "parties"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    abbreviation = Column(String(20), nullable=False)
    eci_id = Column(String(50), unique=True)
    party_type = Column(String(50))   # NATIONAL / STATE / REGIONAL / INDEPENDENT
    symbol_url = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)


# ──────────────────────────────────────────────
# Constituency
# ──────────────────────────────────────────────

class Constituency(Base):
    __tablename__ = "constituencies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    state_id = Column(UUID(as_uuid=True), ForeignKey("states.id"), nullable=False)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"))
    type = Column(String(20), nullable=False)  # VIDHAN / LOK_SABHA
    total_registered_voters = Column(Integer, default=0)
    reserved_category = Column(String(20), default="GENERAL")  # GENERAL / SC / ST
    election_status = Column(
        String(20), default="PENDING",
        nullable=False
    )  # PENDING | OPEN | CLOSED | UNCONTESTED
    __table_args__ = (
        CheckConstraint(
            "election_status IN ('PENDING','OPEN','CLOSED','UNCONTESTED')",
            name="ck_constituency_election_status"
        ),
    )
    state = relationship("State")
    district = relationship("District")


# ──────────────────────────────────────────────
# Booth
# ──────────────────────────────────────────────

class Booth(Base):
    __tablename__ = "booths"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    booth_number = Column(String(50), nullable=False)
    constituency_id = Column(UUID(as_uuid=True), ForeignKey("constituencies.id"), nullable=False)
    state_id = Column(UUID(as_uuid=True), ForeignKey("states.id"), nullable=False)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"))
    taluka_id = Column(UUID(as_uuid=True), ForeignKey("talukas.id"))
    village_id = Column(UUID(as_uuid=True), ForeignKey("villages.id"))
    gps_lat = Column(Numeric(10, 7))
    gps_lng = Column(Numeric(10, 7))
    booth_type = Column(String(20), default="regular")  # regular/remote/mobile/home
    cert_fingerprint = Column(Text)   # mTLS per-booth cert SHA-256
    is_active = Column(Boolean, default=False, nullable=False)
    constituency = relationship("Constituency")
    state = relationship("State")


# ──────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────

class Worker(Base):
    __tablename__ = "workers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(200), nullable=False)
    employee_id = Column(String(50), unique=True, nullable=False)
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"), nullable=False)
    face_vector_id = Column(UUID(as_uuid=True))   # Qdrant point ID
    shift_start = Column(String(8))   # HH:MM:SS
    shift_end = Column(String(8))
    is_active = Column(Boolean, default=True, nullable=False)
    booth = relationship("Booth")


# ──────────────────────────────────────────────
# Voter
# ──────────────────────────────────────────────

class Voter(Base):
    __tablename__ = "voters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    epic_number = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    dob = Column(String(10))   # YYYY-MM-DD
    gender = Column(CHAR(1))   # M/F/O
    mobile = Column(String(15))
    state_code = Column(CHAR(2))
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"), nullable=False)
    face_enrolled = Column(Boolean, default=False, nullable=False)
    has_voted = Column(Boolean, default=False, nullable=False)   # IMMUTABLE once TRUE (SEC-2)
    qdrant_vector_id = Column(UUID(as_uuid=True))
    preferred_language = Column(String(5), default="hi")
    booth = relationship("Booth")
    __table_args__ = (
        Index("ix_voters_epic", "epic_number"),
        Index("ix_voters_booth_id", "booth_id"),
    )


# ──────────────────────────────────────────────
# Candidate
# ──────────────────────────────────────────────

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(200), nullable=False)
    party_id = Column(UUID(as_uuid=True), ForeignKey("parties.id"))
    constituency_id = Column(UUID(as_uuid=True), ForeignKey("constituencies.id"), nullable=False)
    symbol_url = Column(Text)
    nomination_date = Column(TIMESTAMPTZ)
    is_approved = Column(Boolean, default=False, nullable=False)
    # Uncontested election fields
    is_uncontested = Column(Boolean, default=False, nullable=False)
    declared_elected_unopposed_at = Column(TIMESTAMPTZ, nullable=True)
    uncontested_declared_by = Column(UUID(as_uuid=True), ForeignKey("admin_accounts.id"), nullable=True)
    party = relationship("Party")
    constituency = relationship("Constituency")


# ──────────────────────────────────────────────
# Admin Accounts
# ──────────────────────────────────────────────

class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)   # bcrypt
    totp_secret = Column(Text)                     # encrypted TOTP secret
    role = Column(String(30), nullable=False)      # T1..T5
    scope_type = Column(String(30))                # all_india / one_state / one_div / one_dist / one_const
    scope_id = Column(UUID(as_uuid=True))
    ip_allowlist = Column(ARRAY(INET))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)
    last_login_at = Column(TIMESTAMPTZ)


# ──────────────────────────────────────────────
# Vote Ledger  — APPEND-ONLY (SEC-1)
# ──────────────────────────────────────────────

class VoteLedger(Base):
    __tablename__ = "vote_ledger"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voter_id = Column(UUID(as_uuid=True), ForeignKey("voters.id"), unique=True, nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"), nullable=False)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id"), nullable=False)
    location_chain = Column(JSONB, nullable=False)   # 8-level hierarchy
    submitted_at = Column(TIMESTAMPTZ, default=datetime.utcnow, nullable=False)
    vote_hash = Column(Text, nullable=False)          # SHA-256
    prev_hash = Column(Text)                          # chain link
    is_valid = Column(Boolean, default=True, nullable=False)
    receipt_token = Column(Text)                      # ZK proof token
    __table_args__ = (
        Index("ix_vote_ledger_booth_id", "booth_id"),
        Index("ix_vote_ledger_submitted_at", "submitted_at"),
    )


# ──────────────────────────────────────────────
# OTP Store  (SEC-5: stored as SHA-256 only)
# ──────────────────────────────────────────────

class OTPRecord(Base):
    __tablename__ = "otp_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voter_id = Column(UUID(as_uuid=True), ForeignKey("voters.id"), nullable=False)
    otp_hash = Column(Text, nullable=False)    # SHA-256(otp)
    attempts = Column(Integer, default=0, nullable=False)
    expires_at = Column(TIMESTAMPTZ, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    delivery_method = Column(String(20), default="sms")   # sms / msg91 / thermal
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Worker Location Trail
# ──────────────────────────────────────────────

class WorkerLocTrail(Base):
    __tablename__ = "worker_loc_trail"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id"), nullable=False)
    event_type = Column(String(50), nullable=False)   # LOGIN / REAUTH / BACKGROUND_CHECK
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"))
    gps_lat = Column(Numeric(10, 7))
    gps_lng = Column(Numeric(10, 7))
    gps_accuracy_m = Column(Integer)
    face_similarity = Column(Numeric(4, 3))
    device_id = Column(Text)
    recorded_at = Column(TIMESTAMPTZ, default=datetime.utcnow, nullable=False)
    anomaly_flags = Column(JSONB, default=dict)
    worker = relationship("Worker")


# ──────────────────────────────────────────────
# Audit Log
# ──────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_type = Column(String(20), nullable=False)   # voter / worker / admin
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(60), nullable=False)
    # VOTER_SCAN / OTP_SENT / VOTE_CAST / ANOMALY_FLAG / ANOMALY_OVERRIDE
    # OTP_PRINT_FALLBACK / UNCONTESTED_DECLARED / UNCONTESTED_REVERSED
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"))
    metadata_ = Column("metadata", JSONB, default=dict)
    logged_at = Column(TIMESTAMPTZ, default=datetime.utcnow, nullable=False)
    is_tampered = Column(Boolean, default=False, nullable=False)
    __table_args__ = (
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_logged_at", "logged_at"),
        Index("ix_audit_log_booth_id", "booth_id"),
    )


# ──────────────────────────────────────────────
# Anomaly Events
# ──────────────────────────────────────────────

class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flag_type = Column(String(60), nullable=False)
    # FLAG_GPS_VIOLATION / FLAG_IMPOSSIBLE_MOVEMENT / FLAG_FACE_DRIFT
    # FLAG_TURNOUT_DEVIATION / FLAG_ABNORMAL_VOTE_RATE / FLAG_DUPLICATE_ATTEMPT
    # FLAG_LIVENESS_FAIL / FLAG_BOOTH_OFFLINE
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"))
    worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id"))
    voter_id = Column(UUID(as_uuid=True), ForeignKey("voters.id"))
    details = Column(JSONB, default=dict)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("admin_accounts.id"))
    override_reason = Column(Text)
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow, nullable=False)
    resolved_at = Column(TIMESTAMPTZ)


# ──────────────────────────────────────────────
# Booth Heartbeat (for offline detection)
# ──────────────────────────────────────────────

class BoothHeartbeat(Base):
    __tablename__ = "booth_heartbeats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booth_id = Column(UUID(as_uuid=True), ForeignKey("booths.id"), nullable=False, unique=True)
    last_seen_at = Column(TIMESTAMPTZ, default=datetime.utcnow, nullable=False)
    version = Column(String(20))
    ip_address = Column(INET)
    booth = relationship("Booth")
