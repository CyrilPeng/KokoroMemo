"""Semi-automatic review policy for memory card candidates."""

from __future__ import annotations


def auto_review(
    card_type: str,
    importance: float,
    confidence: float,
    risk_level: str = "low",
    tags: list[str] | None = None,
) -> str:
    """Determine review action for a candidate card.

    Returns: 'approve' | 'pending' | 'reject'

    Rules (semi_auto mode):
    - Auto-approve: importance >= 0.7, confidence >= 0.85, risk != high,
      not boundary/relationship type
    - Pending: boundary/relationship, low confidence, high risk
    - Reject: very low importance (< 0.3)
    """
    # 直接拒绝：琐碎内容
    if importance < 0.3:
        return "reject"

    tags = tags or []
    if "risk:high" in tags:
        risk_level = "high"
    elif "risk:medium" in tags:
        risk_level = "medium"
    elif "risk:low" in tags:
        risk_level = "low"

    if "suggested_action:reject" in tags:
        return "reject"
    if "suggested_action:pending" in tags:
        return "pending"
    if "suggested_action:auto_approve" in tags and importance >= 0.7 and confidence >= 0.8 and risk_level != "high":
        return "approve"

    low_risk_roleplay_tags = {"roleplay_rule", "speech_style", "persona_rule", "speech_habit"}
    if low_risk_roleplay_tags.intersection(tags) and importance >= 0.7 and confidence >= 0.8 and risk_level == "low":
        return "approve"

    # AIRP 场景中始终需要复核的类型。
    if card_type in ("boundary", "preference", "relationship", "world_state", "character_state"):
        return "pending"

    # 高风险内容始终进入待审核
    if risk_level == "high":
        return "pending"

    # 自动批准高质量候选项
    if importance >= 0.7 and confidence >= 0.85:
        return "approve"

    # 中等质量进入待审核
    if confidence < 0.6:
        return "pending"

    return "pending"


def determine_risk_level(card_type: str, confidence: float) -> str:
    """Determine risk level for a candidate card."""
    if card_type in ("boundary", "relationship", "world_state"):
        return "high" if confidence < 0.8 else "medium"
    if confidence < 0.5:
        return "medium"
    return "low"
