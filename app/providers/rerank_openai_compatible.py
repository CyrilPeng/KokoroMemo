"""OpenAI-compatible rerank provider (works with ModelArk Qwen3-Reranker etc.)."""

from __future__ import annotations

import httpx

from app.providers.rerank_base import RerankProvider


class OpenAICompatibleRerankProvider(RerankProvider):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 8):
        self.provider_name = "openai_compatible"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        url = f"{self.base_url}/rerank"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            idx = item["index"]
            score = item["relevance_score"]
            results.append((idx, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def health_check(self) -> dict:
        try:
            result = await self.rerank("test", ["test document"])
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
