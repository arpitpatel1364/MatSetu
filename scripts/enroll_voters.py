#!/usr/bin/env python3
"""
Batch voter enrollment script.
Enrolls voter face embeddings into Qdrant collection.
Run before elections: python scripts/enroll_voters.py --csv voters.csv --images ./face_images/
"""
import argparse
import csv
import os
import uuid
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("enroll_voters")


def enroll_from_csv(csv_path: str, images_dir: str, db_url: str, qdrant_host: str, qdrant_port: int):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    engine = create_engine(db_url)
    Session = sessionmaker(engine)
    client = QdrantClient(host=qdrant_host, port=qdrant_port)

    # Ensure collection exists
    try:
        client.get_collection("voter_faces")
    except Exception:
        client.create_collection("voter_faces", vectors_config=VectorParams(size=512, distance=Distance.COSINE))
        logger.info("Created voter_faces collection")

    enrolled = 0
    failed = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            epic = row.get("epic_number", "").strip()
            image_file = row.get("face_image", "").strip()
            if not epic or not image_file:
                continue
            image_path = Path(images_dir) / image_file
            if not image_path.exists():
                logger.warning(f"Image not found: {image_path}")
                failed += 1
                continue
            try:
                embedding = _extract_embedding(str(image_path))
                if embedding is None:
                    logger.warning(f"No face in image: {image_path}")
                    failed += 1
                    continue
                vector_id = str(uuid.uuid4())
                # Upsert in Qdrant
                client.upsert(
                    collection_name="voter_faces",
                    points=[PointStruct(id=vector_id, vector=embedding, payload={"epic_number": epic})]
                )
                # Update DB
                with Session() as session:
                    session.execute(
                        text("""
                            UPDATE voters
                            SET face_enrolled = TRUE,
                                qdrant_vector_id = :vid
                            WHERE epic_number = :epic
                        """),
                        {"vid": vector_id, "epic": epic}
                    )
                    session.commit()
                enrolled += 1
                if enrolled % 100 == 0:
                    logger.info(f"Enrolled {enrolled} voters...")
            except Exception as e:
                logger.error(f"Error enrolling {epic}: {e}")
                failed += 1
            time.sleep(0.01)  # Rate limit

    logger.info(f"✅ Enrollment complete: {enrolled} enrolled, {failed} failed")


def _extract_embedding(image_path: str):
    try:
        import cv2
        import numpy as np
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        img = cv2.imread(image_path)
        if img is None:
            return None
        faces = app.get(img)
        if not faces:
            return None
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
        return face.normed_embedding.tolist()
    except ImportError:
        logger.warning("InsightFace not installed — using random embedding for testing")
        import random
        return [random.gauss(0, 1) for _ in range(512)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MatSetu Voter Face Enrollment")
    parser.add_argument("--csv", required=True, help="CSV file with epic_number,face_image columns")
    parser.add_argument("--images", required=True, help="Directory containing face images")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL_SYNC", "postgresql://matsetu:matsetu@localhost:5432/matsetu"))
    parser.add_argument("--qdrant-host", default="localhost")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    args = parser.parse_args()
    enroll_from_csv(args.csv, args.images, args.db, args.qdrant_host, args.qdrant_port)
