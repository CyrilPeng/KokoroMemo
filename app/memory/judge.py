"""LLM-based memory judgment and extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.memory.extractor import ExtractedMemory
from app.proxy.llm_providers import create_llm_provider


@dataclass
class MemoryJudgeConfigView:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30
    temperature: float = 0.0
    prompt: str = ""


async def judge_memories_with_llm(
    user_message: str,
    assistant_message: str,
    character_id: str | None,
    config: MemoryJudgeConfigView,
    min_importance: float = 0.45,
    min_confidence: float = 0.55,
) -> list[ExtractedMemory]:
    """Use a cheap/fast model to decide which memory cards to create."""
    if not config.base_url or not config.model:
        return []

    provider = create_llm_provider(
        provider=config.provider,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
    )
    prompt = config.prompt.strip() or DEFAULT_MEMORY_JUDGE_PROMPT
    response = await provider.chat(
        {
            "model": config.model,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"用户发言：{user_message}\n助手回复：{assistant_message}"},
            ],
        },
        config.timeout_seconds,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    payload = _parse_json(content)
    memories: list[ExtractedMemory] = []
    for item in payload.get("memories", []):
        if not isinstance(item, dict):
            continue
        if item.get("should_remember") is False:
            continue
        memory_type = item.get("memory_type") or item.get("card_type") or "preference"
        memory_content = item.get("content") or item.get("memory") or ""
        importance = float(item.get("importance", 0.5))
        confidence = float(item.get("confidence", 0.6))
        if not memory_content or importance < min_importance or confidence < min_confidence:
            continue
        tags = item.get("tags") or [memory_type]
        if not isinstance(tags, list):
            tags = [str(tags)]
        memories.append(ExtractedMemory(
            scope=item.get("scope") or ("character" if character_id else "global"),
            memory_type=memory_type,
            content=memory_content[:500],
            importance=importance,
            confidence=confidence,
            tags=[str(tag) for tag in tags],
        ))
    return memories


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"memories": []}
    return payload if isinstance(payload, dict) else {"memories": []}


DEFAULT_MEMORY_JUDGE_PROMPT = """你是 KokoroMemo 的轻量记忆判断 API，职责类似 SillyTavern 的填表模型。
只判断当前一轮对话是否应该生成长期记忆卡片。只输出 JSON，不要解释。

输出格式：
{
  "memories": [
    {
      "should_remember": true,
      "scope": "global|character|conversation",
      "memory_type": "preference|boundary|relationship|event|promise|correction|world_state|character_state|summary",
      "content": "给长期记忆库保存的简洁中文事实",
      "importance": 0.0,
      "confidence": 0.0,
      "tags": ["标签"]
    }
  ]
}

规则：
1. 用户明确要求记住、称呼、偏好、边界、承诺、重要关系变化时，应生成记忆。
2. “从现在起叫我主人”这类称呼偏好应输出 preference，content 写成“用户希望被称呼为“主人”。”，importance/confidence 至少 0.85，并包含 tags: ["preference", "addressing"]。
3. 助手单方面编造、普通寒暄、短暂动作、没有长期价值的剧情推进，不要生成记忆。
4. 边界和敏感偏好可以生成候选，但要保持原意，不要扩大解释。
"""
