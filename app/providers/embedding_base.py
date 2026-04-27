"""Base class for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    provider_name: str
    model: str
    dimension: int

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        pass

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(t) for t in texts]

    @abstractmethod
    async def health_check(self) -> dict:
        pass
