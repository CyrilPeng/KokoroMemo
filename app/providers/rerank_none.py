"""No-op rerank provider (passthrough)."""

from __future__ import annotations

from app.providers.rerank_base import RerankProvider


class NoRerankProvider(RerankProvider):
    def __init__(self):
        self.provider_name = "none"
        self.model = "none"

    async def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        return [(i, 1.0) for i in range(len(documents))]

    async def health_check(self) -> dict:
        return {"status": "ok", "provider": "none"}
