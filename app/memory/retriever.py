"""Retrieve relevant memories using vector search and scoring."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from app.core.time_util import naive_local_now

from app.memory.query_builder import RetrievalQuery
from app.providers.embedding_base import EmbeddingProvider
from app.storage.lancedb_store import LanceDBStore

logger = logging.getLogger("kokoromemo.retriever")


@dataclass
class MemoryCandidate:
    memory_id: str
    content: str
    scope: str
    memory_type: str
    importance: float
    confidence: float
    vector_score: float
    final_score: float


def _recency_score(updated_at: str | None) -> float:
    if not updated_at:
        return 0.5
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            now = datetime.now(dt.tzinfo)
        else:
            now = naive_local_now()
        days = (now - dt).total_seconds() / 86400
    except Exception:
        return 0.5
    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.85
    if days <= 30:
        return 0.65
    if days <= 180:
        return 0.45
    return 0.30


def _scope_score(scope: str) -> float:
    return {"conversation": 1.0, "character": 0.85, "global": 0.70}.get(scope, 0.5)


async def retrieve_memories(
    query: RetrievalQuery,
    embedding_provider: EmbeddingProvider,
    lancedb_store: LanceDBStore,
    vector_top_k: int = 30,
    final_top_k: int = 6,
    scoring_weights: dict | None = None,
) -> list[MemoryCandidate]:
    """Retrieve and rank memories."""
    weights = scoring_weights or {
        "vector_weight": 0.55,
        "importance_weight": 0.20,
        "recency_weight": 0.10,
        "scope_weight": 0.10,
        "confidence_weight": 0.05,
    }

    # Embed query
    try:
        query_vector = await embedding_provider.embed_text(query.query_text)
    except Exception as e:
        logger.warning("Embedding failed, skipping retrieval: %s", e)
        return []

    # Build where filter
    sf = query.scope_filter
    clauses = [
        "status = 'active'",
        f"user_id = '{sf['user_id']}'",
    ]
    scope_clauses = ["scope = 'global'"]
    if sf.get("character_id"):
        scope_clauses.append(f"(scope = 'character' AND character_id = '{sf['character_id']}')")
    if sf.get("conversation_id"):
        scope_clauses.append(f"(scope = 'conversation' AND conversation_id = '{sf['conversation_id']}')")
    clauses.append(f"({' OR '.join(scope_clauses)})")
    where = " AND ".join(clauses)

    # Search
    try:
        results = lancedb_store.search(query_vector, where=where, top_k=vector_top_k)
    except Exception as e:
        logger.warning("LanceDB search failed: %s", e)
        return []

    # Score and rank
    candidates = []
    for row in results:
        vs = 1.0 - row.get("_distance", 0.5)  # cosine distance -> similarity
        imp = row.get("importance", 0.5)
        conf = row.get("confidence", 0.5)
        rec = _recency_score(row.get("updated_at"))
        sc = _scope_score(row.get("scope", "global"))

        final = (
            vs * weights["vector_weight"]
            + imp * weights["importance_weight"]
            + rec * weights["recency_weight"]
            + sc * weights["scope_weight"]
            + conf * weights["confidence_weight"]
        )

        candidates.append(MemoryCandidate(
            memory_id=row.get("memory_id", ""),
            content=row.get("content", ""),
            scope=row.get("scope", ""),
            memory_type=row.get("memory_type", ""),
            importance=imp,
            confidence=conf,
            vector_score=vs,
            final_score=final,
        ))

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    return candidates[:final_top_k]
