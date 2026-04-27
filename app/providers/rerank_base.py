"""Base class for rerank providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RerankProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    async def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        """Rerank documents. Returns list of (original_index, score) sorted by score desc."""
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        pass
