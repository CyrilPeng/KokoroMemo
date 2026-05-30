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
from app.memory.graph import get_active_edges_for_cards
from app.memory.query_builder import RetrievalQuery
from app.memory.retrieval_embedding_cache import get_retrieval_cache
from app.providers.embedding_base import EmbeddingProvider
from app.providers.rerank_base import RerankProvider
from app.storage.sqlite_cards import (
    get_cards_by_ids,
    get_mounted_library_ids,
    get_pinned_cards,
    get_recent_important_cards,
)

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
    library_id: str = ""
    source_conversation_id: str | None = None
    source_character_id: str | None = None
    importance_score: float = 0.0
    recency_score: float = 0.0
    scope_score: float = 0.0
    confidence_score: float = 0.0

    @classmethod
    def from_card(
        cls,
        card: dict,
        *,
        source: str,
        vector_score: float = 0.5,
        final_score: float = 0.0,
    ) -> MemoryCandidate:
        """Build a MemoryCandidate from a raw card dict, avoiding repetition at each retrieval path."""
        importance = card.get("importance", 0.5)
        confidence = card.get("confidence", 0.5)
        scope = card.get("scope", "")
        return cls(
            card_id=card.get("card_id", ""),
            content=card.get("content", ""),
            scope=scope,
            card_type=card.get("card_type", ""),
            importance=importance,
            confidence=confidence,
            vector_score=vector_score,
            final_score=final_score,
            source=source,
            library_id=card.get("library_id", ""),
            source_conversation_id=card.get("conversation_id"),
            source_character_id=card.get("character_id"),
            importance_score=importance,
            recency_score=_recency_score(card.get("created_at")),
            scope_score=_scope_score(scope),
            confidence_score=confidence,
        )


def _recency_score(created_at: str | None) -> float:
    if not created_at:
        return 0.5
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo is not None else naive_local_now()
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


async def _resolve_query_vector(
    embedding_provider: EmbeddingProvider,
    query: RetrievalQuery,
) -> list[float]:
    """Resolve the vector used for retrieval without changing retrieval semantics."""
    cache = get_retrieval_cache()
    model = getattr(embedding_provider, "model", "") or getattr(embedding_provider, "provider_name", "")
    query_vector = cache.get(model, query.query_text)
    if query_vector is not None:
        logger.debug("Retrieval embedding cache hit")
        return query_vector

    query_vector = await embedding_provider.embed_text(query.query_text)
    cache.put(model, query.query_text, query_vector)
    return query_vector


async def retrieve_cards(
    query: RetrievalQuery,
    embedding_provider: EmbeddingProvider,
    lancedb_store,
    cards_db_path: str,
    vector_top_k: int = 30,
    final_top_k: int = 8,
    scoring_weights: dict | None = None,
    allowed_scopes: set[str] | None = None,
    rerank_provider: RerankProvider | None = None,
    rerank_top_k: int | None = None,
    rerank_batch_size: int = 20,
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

    # --- 路径 1：置顶 / 边界卡片 ---
    try:
        pinned = await get_pinned_cards(cards_db_path, user_id, character_id, mounted_library_ids)
        for card in pinned:
            cid = card.get("card_id", "")
            if cid in seen_ids:
                continue
            if not _is_card_visible_for_query(card, allowed_scopes, character_id, conversation_id):
                continue
            seen_ids.add(cid)
            all_candidates.append(
                MemoryCandidate.from_card(
                    card,
                    source="pinned",
                    vector_score=1.0,  # 置顶卡片始终保持高优先级
                    final_score=1.0,
                )
            )
    except Exception as e:
        logger.warning("Pinned cards retrieval failed: %s", e)

    # --- 路径 2：向量召回（LanceDB）---
    try:
        query_vector = await _resolve_query_vector(embedding_provider, query)

        # 构建作用域过滤条件（所有用户可控 ID 必须转义单引号，防止 filter 注入）
        safe_user_id = user_id.replace("'", "''")
        clauses = ["status = 'active'", f"user_id = '{safe_user_id}'"]
        if mounted_library_ids:
            escaped_ids = [library_id.replace("'", "''") for library_id in mounted_library_ids]
            library_filter = ", ".join(f"'{library_id}'" for library_id in escaped_ids)
            clauses.append(f"library_id IN ({library_filter})")
        scope_clauses = []
        if "global" in allowed_scopes:
            scope_clauses.append("scope = 'global'")
        if "character" in allowed_scopes and character_id:
            safe_character_id = character_id.replace("'", "''")
            scope_clauses.append(f"(scope = 'character' AND character_id = '{safe_character_id}')")
        if "conversation" in allowed_scopes and conversation_id:
            safe_conversation_id = conversation_id.replace("'", "''")
            scope_clauses.append(f"(scope = 'conversation' AND conversation_id = '{safe_conversation_id}')")
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
            if not _is_card_visible_for_query(card, allowed_scopes, character_id, conversation_id):
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

            all_candidates.append(
                MemoryCandidate.from_card(
                    card,
                    source="vector",
                    vector_score=vs,
                    final_score=final,
                )
            )
    except Exception as e:
        logger.warning("Vector retrieval failed (degraded): %s", e)

    # --- 路径 3：近期重要卡片 ---
    try:
        recent = await get_recent_important_cards(cards_db_path, user_id, character_id, library_ids=mounted_library_ids)
        for card in recent:
            cid = card.get("card_id", "")
            if cid in seen_ids:
                continue
            if not _is_card_visible_for_query(card, allowed_scopes, character_id, conversation_id):
                continue
            seen_ids.add(cid)
            all_candidates.append(
                MemoryCandidate.from_card(
                    card,
                    source="recent",
                    vector_score=0.5,
                    final_score=card.get("importance", 0.5) * 0.8,
                )
            )
    except Exception as e:
        logger.warning("Recent cards retrieval failed: %s", e)

    # --- 路径 4：图关系扩展 ---
    try:
        seed_ids = [c.card_id for c in all_candidates]
        candidate_scores = {c.card_id: c.final_score for c in all_candidates}
        edges = await get_active_edges_for_cards(cards_db_path, seed_ids)
        expand_ids: set[str] = set()
        suppress_ids: set[str] = set()

        for edge in edges:
            source_id = edge["source_card_id"]
            target_id = edge["target_card_id"]
            edge_type = edge["edge_type"]

            if edge_type in {"constrains", "same_as"}:
                if source_id in seen_ids and target_id not in seen_ids:
                    expand_ids.add(target_id)
                if target_id in seen_ids and source_id not in seen_ids:
                    expand_ids.add(source_id)
            elif edge_type == "contradicts":
                if source_id in seen_ids and target_id in seen_ids:
                    if candidate_scores.get(source_id, 0.0) >= candidate_scores.get(target_id, 0.0):
                        suppress_ids.add(target_id)
                    else:
                        suppress_ids.add(source_id)
                elif source_id in seen_ids:
                    suppress_ids.add(target_id)
                elif target_id in seen_ids:
                    suppress_ids.add(source_id)
            elif edge_type == "supersedes":
                if source_id in seen_ids:
                    suppress_ids.add(target_id)
                elif target_id in seen_ids:
                    expand_ids.add(source_id)
                    suppress_ids.add(target_id)
            elif edge_type in {"supports", "elaborates", "belongs_to", "continues", "related"}:
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
                if not _is_card_visible_for_query(card, allowed_scopes, character_id, conversation_id):
                    continue
                if mounted_library_set and card.get("library_id") not in mounted_library_set:
                    continue
                cid = card.get("card_id", "")
                seen_ids.add(cid)
                importance = card.get("importance", 0.5)
                all_candidates.append(
                    MemoryCandidate.from_card(
                        card,
                        source="graph",
                        vector_score=0.6,
                        final_score=max(0.75, importance * 0.9),
                    )
                )
    except Exception as e:
        logger.warning("Graph expansion failed: %s", e)

    if rerank_provider and all_candidates:
        all_candidates = await _rerank_candidates(
            query,
            all_candidates,
            rerank_provider,
            candidate_top_k=rerank_top_k or len(all_candidates),
            batch_size=rerank_batch_size,
        )

    # 排序：置顶卡片优先（保证 score=1.0），然后按 final_score 排序
    all_candidates.sort(key=lambda c: c.final_score, reverse=True)
    return all_candidates[:final_top_k]


async def _rerank_candidates(
    query: RetrievalQuery,
    candidates: list[MemoryCandidate],
    rerank_provider: RerankProvider,
    *,
    candidate_top_k: int,
    batch_size: int,
) -> list[MemoryCandidate]:
    pinned = [candidate for candidate in candidates if candidate.source == "pinned"]
    rerankable = [candidate for candidate in candidates if candidate.source != "pinned"]
    if not rerankable:
        return candidates

    rerankable.sort(key=lambda candidate: candidate.final_score, reverse=True)
    selected = rerankable[: max(1, candidate_top_k)]
    untouched = rerankable[len(selected) :]
    batch_size = max(1, batch_size)

    reranked: list[MemoryCandidate] = []
    for start in range(0, len(selected), batch_size):
        batch = selected[start : start + batch_size]
        documents = [candidate.content for candidate in batch]
        try:
            results = await rerank_provider.rerank(query.query_text, documents)
        except Exception as exc:
            logger.warning("Rerank failed (degraded): %s", exc)
            return candidates

        used_indexes: set[int] = set()
        for index, score in results:
            if index < 0 or index >= len(batch) or index in used_indexes:
                continue
            used_indexes.add(index)
            candidate = batch[index]
            candidate.final_score = max(0.0, min(1.0, score))
            reranked.append(candidate)

        for index, candidate in enumerate(batch):
            if index not in used_indexes:
                reranked.append(candidate)

    return pinned + reranked + untouched


def _is_card_visible_for_query(
    card: dict,
    allowed_scopes: set[str],
    character_id: str | None,
    conversation_id: str | None,
) -> bool:
    scope = card.get("scope")
    if scope not in allowed_scopes:
        return False
    if scope == "global":
        return True
    if scope == "character":
        return bool(character_id) and card.get("character_id") == character_id
    if scope == "conversation":
        return bool(conversation_id) and card.get("conversation_id") == conversation_id
    return False
