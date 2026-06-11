import pytest

from app.memory.review_policy import auto_review, determine_risk_level


@pytest.mark.parametrize(
    "card_type",
    ["boundary", "preference", "relationship", "world_state", "character_state"],
)
def test_airp_sensitive_memory_types_require_review(card_type: str) -> None:
    assert auto_review(card_type, importance=0.9, confidence=0.95, risk_level="low") == "pending"


@pytest.mark.parametrize("tag", ["roleplay_rule", "speech_style", "persona_rule", "speech_habit"])
def test_low_risk_roleplay_rules_can_auto_approve(tag: str) -> None:
    assert auto_review("rule", importance=0.8, confidence=0.85, risk_level="low", tags=[tag]) == "approve"


def test_high_risk_tag_overrides_auto_approve_suggestion() -> None:
    assert (
        auto_review(
            "rule",
            importance=0.9,
            confidence=0.95,
            risk_level="low",
            tags=["risk:high", "suggested_action:auto_approve"],
        )
        == "pending"
    )


def test_reject_suggestion_and_low_importance_are_not_promoted() -> None:
    assert auto_review("preference", importance=0.9, confidence=0.95, tags=["suggested_action:reject"]) == "reject"
    assert auto_review("rule", importance=0.2, confidence=0.95, tags=["suggested_action:auto_approve"]) == "reject"


@pytest.mark.parametrize(
    ("card_type", "confidence", "expected"),
    [
        ("boundary", 0.7, "high"),
        ("relationship", 0.9, "medium"),
        ("world_state", 0.9, "medium"),
        ("preference", 0.4, "medium"),
        ("preference", 0.8, "low"),
    ],
)
def test_determine_risk_level_for_airp_memory_types(card_type: str, confidence: float, expected: str) -> None:
    assert determine_risk_level(card_type, confidence) == expected
