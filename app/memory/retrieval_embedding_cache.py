"""Short-TTL LRU cache for retrieval embedding vectors.

Only caches (embedding_model, query_text) -> embedding vector lookups.
Not used for write/extraction paths (sync_card_vector, extract_and_route, judge).
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger("kokoromemo.retrieval_embedding_cache")


def _normalize_query(text: str) -> str:
    """Trim and collapse consecutive whitespace to a single space."""
    return re.sub(r"\s+", " ", text.strip())


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class _CacheEntry:
    vector: list[float]
    cached_at: float = field(default_factory=time.monotonic)


class RetrievalEmbeddingCache:
    """Thread-unsafe LRU cache for retrieval embedding vectors."""

    def __init__(self, ttl_seconds: float = 60.0, capacity: int = 128) -> None:
        self.ttl_seconds = ttl_seconds
        self.capacity = max(1, capacity)
        self._store: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()
        self.stats = CacheStats()

    def _make_key(self, model: str, query_text: str) -> tuple[str, str]:
        return (model, _normalize_query(query_text))

    def get(self, model: str, query_text: str) -> list[float] | None:
        key = self._make_key(model, query_text)
        entry = self._store.get(key)
        if entry is None:
            self.stats.misses += 1
            return None

        age = time.monotonic() - entry.cached_at
        if age > self.ttl_seconds:
            del self._store[key]
            self.stats.expirations += 1
            self.stats.misses += 1
            return None

        self._store.move_to_end(key)
        self.stats.hits += 1
        return list(entry.vector)

    def put(self, model: str, query_text: str, vector: list[float]) -> None:
        key = self._make_key(model, query_text)
        if key in self._store:
            self._store.move_to_end(key)
            self._store[key] = _CacheEntry(vector=list(vector))
            return

        while len(self._store) >= self.capacity:
            self._store.popitem(last=False)
            self.stats.evictions += 1

        self._store[key] = _CacheEntry(vector=list(vector))

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


_retrieval_cache: RetrievalEmbeddingCache | None = None


def get_retrieval_cache() -> RetrievalEmbeddingCache:
    global _retrieval_cache
    if _retrieval_cache is None:
        _retrieval_cache = RetrievalEmbeddingCache()
    return _retrieval_cache


def init_retrieval_cache(ttl_seconds: float = 60.0, capacity: int = 128) -> RetrievalEmbeddingCache:
    global _retrieval_cache
    _retrieval_cache = RetrievalEmbeddingCache(ttl_seconds=ttl_seconds, capacity=capacity)
    return _retrieval_cache
