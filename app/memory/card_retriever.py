"""Multi-path memory card retriever.

Routes:
1. Pinned / boundary cards (SQLite direct)
2. Vector recall (LanceDB, approved only)
3. Recent important cards (SQLite)
4. Graph expansion (future, placeholder)

All routes return MemoryCandidate, merged and deduplicated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.core.time_util import naive_local_now

from app.memory.query_builder import RetrievalQuery
from app.providers.embedding_base import EmbeddingProvider
from app.memory.graph import get_active_edges_for_cards
from app.storage.sqlite_cards import get_cards_by_ids, get_pinned_cards, get_recent_important_cards
from app.storage.sqlite_cards import get_mounted_library_ids

logger = logging.getLogger("kokoromemo.card_retriever")


@dataclass
class MemoryCandidate:
    card_id: str
    content: str
    scope: str
    card_type: str
    importance: float
    confidence: float
    vector_score: float
    final_score: float
    source: str  # 'pinned' | 'vector' | 'recent' | 'graph'


def _recency_score(created_at: str | None) -> float:
    if not created_at:
        return 0.5
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
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


async def retrieve_cards(
    query: RetrievalQuery,
    embedding_provider: EmbeddingProvider,
    lancedb_store,
    cards_db_path: str,
    vector_top_k: int = 30,
    final_top_k: int = 8,
    scoring_weights: dict | None = None,
    allowed_scopes: set[str] | None = None,
) -> list[MemoryCandidate]:
    """Multi-path retrieval of approved memory cards.

    allowed_scopes: subset of {"global", "character", "conversation"} indicating which
    scopes are eligible for recall. None = all enabled. If empty set, returns no candidates.
    """
    weights = scoring_weights or {
        "vector_weight": 0.55,
        "importance_weight": 0.20,
        "recency_weight": 0.10,
        "scope_weight": 0.10,
        "confidence_weight": 0.05,
    }
    if allowed_scopes is None:
        allowed_scopes = {"global", "character", "conversation"}
    if not allowed_scopes:
        return []

    seen_ids: set[str] = set()
    all_candidates: list[MemoryCandidate] = []

    sf = query.scope_filter
    user_id = sf["user_id"]
    character_id = sf.get("character_id")
    conversation_id = sf.get("conversation_id")
    mounted_library_ids = await get_mounted_library_ids(cards_db_path, conversation_id) if conversation_id else None
    mounted_library_set = set(mounted_library_ids or [])

    # --- Route 1: Pinned / boundary cards ---
    try:
        pinned = await get_pinned_cards(cards_db_path, user_id, character_id, mounted_library_ids)
        for card in pinned:
            cid = card["card_id"]
            if cid in seen_ids:
                continue
            if card.get("scope") not in allowed_scopes:
                continue
            seen_ids.add(cid)
            all_candidates.append(MemoryCandidate(
                card_id=cid,
                content=card["content"],
                scope=card["scope"],
                card_type=card["card_type"],
                importance=card["importance"],
                confidence=card["confidence"],
                vector_score=1.0,  # pinned always high priority
                final_score=1.0,
                source="pinned",
            ))
    except Exception as e:
        logger.warning("Pinned cards retrieval failed: %s", e)

    # --- Route 2: Vector recall (LanceDB) ---
    try:
        query_vector = await embedding_provider.embed_text(query.query_text)

        # Build scope filter
        clauses = ["status = 'active'", f"user_id = '{user_id}'"]
        if mounted_library_ids:
            escaped_ids = [library_id.replace("'", "''") for library_id in mounted_library_ids]
            library_filter = ", ".join(f"'{library_id}'" for library_id in escaped_ids)
            clauses.append(f"library_id IN ({library_filter})")
        scope_clauses = []
        if "global" in allowed_scopes:
            scope_clauses.append("scope = 'global'")
        if "character" in allowed_scopes and character_id:
            scope_clauses.append(f"(scope = 'character' AND character_id = '{character_id}')")
        if "conversation" in allowed_scopes and conversation_id:
            scope_clauses.append(f"(scope = 'conversation' AND conversation_id = '{conversation_id}')")
        if not scope_clauses:
            raise RuntimeError("no_scope_eligible")
        clauses.append(f"({' OR '.join(scope_clauses)})")
        where = " AND ".join(clauses)

        results = lancedb_store.search(query_vector, where=where, top_k=vector_top_k)

        card_ids = [row.get("memory_id", "") for row in results if row.get("memory_id")]
        sqlite_cards = await get_cards_by_ids(cards_db_path, card_ids)

        for row in results:
            cid = row.get("memory_id", "")
            card = sqlite_cards.get(cid)
            if cid in seen_ids or not card or card.get("status") != "approved":
                continue
            if mounted_library_set and card.get("library_id") not in mounted_library_set:
                continue
            seen_ids.add(cid)

            vs = 1.0 - row.get("_distance", 0.5)
            imp = card.get("importance", 0.5)
            conf = card.get("confidence", 0.5)
            rec = _recency_score(card.get("created_at"))
            sc = _scope_score(card.get("scope", "global"))

            final = (
                vs * weights["vector_weight"]
                + imp * weights["importance_weight"]
                + rec * weights["recency_weight"]
                + sc * weights["scope_weight"]
                + conf * weights["confidence_weight"]
            )

            all_candidates.append(MemoryCandidate(
                card_id=cid,
                content=card.get("content", ""),
                scope=card.get("scope", ""),
                card_type=card.get("card_type", ""),
                importance=imp,
                confidence=conf,
                vector_score=vs,
                final_score=final,
                source="vector",
            ))
    except Exception as e:
        logger.warning("Vector retrieval failed (degraded): %s", e)

    # --- Route 3: Recent important cards ---
    try:
        recent = await get_recent_important_cards(cards_db_path, user_id, character_id, library_ids=mounted_library_ids)
        for card in recent:
            cid = card["card_id"]
            if cid in seen_ids:
                continue
            if card.get("scope") not in allowed_scopes:
                continue
            seen_ids.add(cid)
            all_candidates.append(MemoryCandidate(
                card_id=cid,
                content=card["content"],
                scope=card["scope"],
                card_type=card["card_type"],
                importance=card["importance"],
                confidence=card["confidence"],
                vector_score=0.5,
                final_score=card["importance"] * 0.8,
                source="recent",
            ))
    except Exception as e:
        logger.warning("Recent cards retrieval failed: %s", e)

    # --- Route 4: Graph expansion ---
    try:
        seed_ids = [c.card_id for c in all_candidates]
        edges = await get_active_edges_for_cards(cards_db_path, seed_ids)
        expand_ids: set[str] = set()
        suppress_ids: set[str] = set()

        for edge in edges:
            source_id = edge["source_card_id"]
            target_id = edge["target_card_id"]
            edge_type = edge["edge_type"]

            if edge_type == "constrains":
                if source_id in seen_ids and target_id not in seen_ids:
                    expand_ids.add(target_id)
                if target_id in seen_ids and source_id not in seen_ids:
                    expand_ids.add(source_id)
            elif edge_type == "supersedes":
                if source_id in seen_ids:
                    suppress_ids.add(target_id)
                elif target_id in seen_ids:
                    expand_ids.add(source_id)
                    suppress_ids.add(target_id)
            elif edge_type in ("supports", "related"):
                if source_id in seen_ids and target_id not in seen_ids:
                    expand_ids.add(target_id)

        if suppress_ids:
            all_candidates = [c for c in all_candidates if c.card_id not in suppress_ids]
            seen_ids -= suppress_ids

        expand_ids -= seen_ids
        if expand_ids:
            graph_cards = await get_cards_by_ids(cards_db_path, list(expand_ids))
            for card in graph_cards.values():
                if card.get("status") != "approved":
                    continue
                if card.get("scope") not in allowed_scopes:
                    continue
                if mounted_library_set and card.get("library_id") not in mounted_library_set:
                    continue
                cid = card["card_id"]
                seen_ids.add(cid)
                all_candidates.append(MemoryCandidate(
                    card_id=cid,
                    content=card["content"],
                    scope=card["scope"],
                    card_type=card["card_type"],
                    importance=card["importance"],
                    confidence=card["confidence"],
                    vector_score=0.6,
                    final_score=max(0.75, card["importance"] * 0.9),
                    source="graph",
                ))
    except Exception as e:
        logger.warning("Graph expansion failed: %s", e)

    # Sort: pinned first (score=1.0 guaranteed), then by final_score
    all_candidates.sort(key=lambda c: c.final_score, reverse=True)
    return all_candidates[:final_top_k]
