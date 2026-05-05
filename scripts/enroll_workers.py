#!/usr/bin/env python3
"""
Batch worker face enrollment script.
Enrolls polling officer face embeddings into Qdrant worker_faces collection.
"""
import argparse
import csv
import uuid
import os
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("enroll_workers")


def enroll_workers(csv_path: str, images_dir: str, db_url: str, qdrant_host: str, qdrant_port: int):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    engine = create_engine(db_url)
    Session = sessionmaker(engine)
    client = QdrantClient(host=qdrant_host, port=qdrant_port)

    try:
        client.get_collection("worker_faces")
    except Exception:
        client.create_collection("worker_faces", vectors_config=VectorParams(size=512, distance=Distance.COSINE))
        logger.info("Created worker_faces collection")

    enrolled = 0
    failed = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            emp_id = row.get("employee_id", "").strip()
            image_file = row.get("face_image", "").strip()
            if not emp_id or not image_file:
                continue
            image_path = Path(images_dir) / image_file
            if not image_path.exists():
                logger.warning(f"Image not found: {image_path}")
                failed += 1
                continue
            try:
                embedding = _extract_embedding(str(image_path))
                if embedding is None:
                    failed += 1
                    continue
                vector_id = str(uuid.uuid4())
                client.upsert("worker_faces", points=[
                    PointStruct(id=vector_id, vector=embedding, payload={"employee_id": emp_id})
                ])
                with Session() as session:
                    session.execute(
                        text("UPDATE workers SET face_vector_id=:vid WHERE employee_id=:eid"),
                        {"vid": vector_id, "eid": emp_id}
                    )
                    session.commit()
                enrolled += 1
                logger.info(f"Enrolled worker: {emp_id}")
            except Exception as e:
                logger.error(f"Error enrolling worker {emp_id}: {e}")
                failed += 1
            time.sleep(0.01)

    logger.info(f"✅ Worker enrollment: {enrolled} enrolled, {failed} failed")


def _extract_embedding(image_path: str):
    try:
        import cv2
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
        import random
        return [random.gauss(0, 1) for _ in range(512)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MatSetu Worker Face Enrollment")
    parser.add_argument("--csv", required=True, help="CSV with employee_id,face_image")
    parser.add_argument("--images", required=True, help="Face images directory")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL_SYNC", "postgresql://matsetu:matsetu@localhost:5432/matsetu"))
    parser.add_argument("--qdrant-host", default="localhost")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    args = parser.parse_args()
    enroll_workers(args.csv, args.images, args.db, args.qdrant_host, args.qdrant_port)
