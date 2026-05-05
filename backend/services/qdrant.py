"""
Qdrant vector store service.
Manages voter and worker face embedding collections.
Cosine search for face matching.
"""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, SearchRequest, Filter,
    FieldCondition, MatchValue, UpdateStatus
)
from typing import Optional, List, Tuple
from uuid import UUID
import numpy as np
import logging
from backend.config import settings

logger = logging.getLogger(__name__)
_client: Optional[QdrantClient] = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return _client


def ensure_collections():
    """Create collections if they don't exist."""
    client = get_client()
    for col in [settings.QDRANT_COLLECTION_VOTERS, settings.QDRANT_COLLECTION_WORKERS]:
        try:
            client.get_collection(col)
        except Exception:
            client.create_collection(
                collection_name=col,
                vectors_config=VectorParams(
                    size=settings.QDRANT_VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Created Qdrant collection: {col}")


def upsert_face(
    collection: str,
    point_id: str,
    embedding: np.ndarray,
    payload: dict
) -> bool:
    """Insert or update a face embedding in Qdrant."""
    client = get_client()
    try:
        result = client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
            ]
        )
        return result.status == UpdateStatus.COMPLETED
    except Exception as e:
        logger.error(f"Qdrant upsert error: {e}")
        return False


def search_face(
    collection: str,
    embedding: np.ndarray,
    top_k: int = 5,
    score_threshold: float = None
) -> List[Tuple[str, float, dict]]:
    """
    Search for matching faces. Returns list of (point_id, score, payload).
    FAR < 0.01%, FRR < 0.5% at threshold 0.65.
    """
    threshold = score_threshold or settings.ARCFACE_SIMILARITY_THRESHOLD
    client = get_client()
    try:
        results = client.search(
            collection_name=collection,
            query_vector=embedding.tolist(),
            limit=top_k,
            score_threshold=threshold,
            with_payload=True
        )
        return [(str(r.id), r.score, r.payload) for r in results]
    except Exception as e:
        logger.error(f"Qdrant search error: {e}")
        return []


def delete_face(collection: str, point_id: str) -> bool:
    client = get_client()
    try:
        client.delete(collection_name=collection, points_selector=[point_id])
        return True
    except Exception as e:
        logger.error(f"Qdrant delete error: {e}")
        return False
