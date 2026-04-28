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
    # Direct reject: trivial content
    if importance < 0.3:
        return "reject"

    tags = tags or []
    if "addressing" in tags and importance >= 0.85 and confidence >= 0.85 and risk_level != "high":
        return "approve"

    # Types that always need review in AIRP scenarios.
    if card_type in ("boundary", "preference", "relationship", "world_state", "character_state"):
        return "pending"

    # High risk always pending
    if risk_level == "high":
        return "pending"

    # Auto-approve high-quality candidates
    if importance >= 0.7 and confidence >= 0.85:
        return "approve"

    # Medium quality → pending
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
