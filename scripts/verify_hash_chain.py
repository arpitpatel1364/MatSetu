#!/usr/bin/env python3
"""
Post-election audit: verify SHA-256 hash chain integrity of vote_ledger.
Detects any tampering with the append-only ledger.
"""
import hashlib
import os
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("verify_hash_chain")


def verify_chain(db_url: str, booth_id: str = None, output_file: str = None):
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)

    with engine.connect() as conn:
        query = """
            SELECT id, voter_id, candidate_id, booth_id, submitted_at,
                   vote_hash, prev_hash
            FROM vote_ledger
            WHERE is_valid = TRUE
        """
        params = {}
        if booth_id:
            query += " AND booth_id = :booth_id"
            params["booth_id"] = booth_id
        query += " ORDER BY booth_id, submitted_at ASC"

        result = conn.execute(text(query), params)
        rows = result.fetchall()

    logger.info(f"Verifying {len(rows)} vote records...")

    # Group by booth
    from collections import defaultdict
    booths = defaultdict(list)
    for row in rows:
        booths[str(row.booth_id)].append(row)

    total_ok = 0
    total_tampered = 0
    tampered_records = []

    for bid, votes in booths.items():
        prev_hash = "GENESIS"
        for i, vote in enumerate(votes):
            # Recompute expected hash
            # Note: BOOTH_SECRET needed — read from env
            booth_secret = os.getenv("BOOTH_SECRET", "CHANGE_ME_BOOTH_SECRET_256BIT")
            expected_hash = hashlib.sha256(
                f"{vote.voter_id}|{vote.candidate_id}|{vote.submitted_at.isoformat()}|{booth_secret}|{prev_hash}".encode()
            ).hexdigest()

            if vote.vote_hash != expected_hash:
                logger.error(
                    f"TAMPERED! vote_id={vote.id} booth={bid} "
                    f"expected={expected_hash[:16]}... got={vote.vote_hash[:16]}..."
                )
                tampered_records.append({
                    "vote_id": str(vote.id),
                    "booth_id": bid,
                    "position": i,
                    "expected_hash": expected_hash,
                    "stored_hash": vote.vote_hash
                })
                total_tampered += 1
            else:
                total_ok += 1

            # Also verify prev_hash linkage
            if i > 0 and vote.prev_hash != votes[i-1].vote_hash:
                logger.error(
                    f"CHAIN BROKEN! vote_id={vote.id} prev_hash mismatch "
                    f"expected={votes[i-1].vote_hash[:16]}... got={vote.prev_hash[:16]}..."
                )

            prev_hash = vote.vote_hash

    logger.info(f"✅ Valid: {total_ok} | ❌ Tampered: {total_tampered}")

    if output_file:
        import json
        report = {
            "verification_time": datetime.utcnow().isoformat(),
            "total_votes": len(rows),
            "valid_votes": total_ok,
            "tampered_votes": total_tampered,
            "tampered_records": tampered_records,
            "chain_integrity": "INTACT" if total_tampered == 0 else "COMPROMISED"
        }
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report saved to {output_file}")

    return total_tampered == 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MatSetu Vote Ledger Hash Chain Verifier")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL_SYNC", "postgresql://matsetu:matsetu@localhost:5432/matsetu"))
    parser.add_argument("--booth", default=None, help="Verify specific booth only")
    parser.add_argument("--output", default="chain_audit_report.json", help="Output report file")
    args = parser.parse_args()
    ok = verify_chain(args.db, args.booth, args.output)
    sys.exit(0 if ok else 1)
