"""Dummy embedding provider for testing."""

from __future__ import annotations

import hashlib
import struct

from app.providers.embedding_base import EmbeddingProvider


class DummyEmbeddingProvider(EmbeddingProvider):
    """Generates deterministic pseudo-random vectors from text hash. For testing only."""

    def __init__(self, dimension: int = 4096):
        self.provider_name = "dummy"
        self.model = "dummy"
        self.dimension = dimension

    async def embed_text(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        # 扩展哈希以填满维度
        repeats = (self.dimension * 4 // len(h)) + 1
        raw = (h * repeats)[: self.dimension * 4]
        vec = list(struct.unpack(f"{self.dimension}f", raw[:self.dimension * 4]))
        # 归一化
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    async def health_check(self) -> dict:
        return {"status": "ok", "dimension": self.dimension, "provider": "dummy"}
