"""Rule-based gate for deciding whether long-term retrieval is needed."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.query_builder import RetrievalQuery
from app.memory.state_schema import ConversationStateItem


@dataclass
class RetrievalGateInput:
    query: RetrievalQuery
    state_items: list[ConversationStateItem] = field(default_factory=list)
    turn_index: int | None = None
    mode: str = "auto"
    vector_search_on_new_session: bool = True
    vector_search_every_n_turns: int = 6
    vector_search_when_state_confidence_below: float = 0.65
    trigger_keywords: list[str] = field(default_factory=list)
    skip_when_latest_user_text_chars_below: int = 4
    skip_when_state_is_sufficient: bool = True


@dataclass
class RetrievalGateDecision:
    should_retrieve: bool
    reason: str
    reasons: list[str]
    mode: str
    state_item_count: int
    avg_state_confidence: float | None


def decide_retrieval(gate_input: RetrievalGateInput) -> RetrievalGateDecision:
    """Decide whether to run expensive vector retrieval."""
    mode = (gate_input.mode or "auto").lower()
    stats = _state_stats(gate_input.state_items)
    if mode == "always":
        return _decision(True, "mode_always", ["mode_always"], mode, stats)
    if mode == "never":
        return _decision(False, "mode_never", ["mode_never"], mode, stats)

    latest_user_text = (gate_input.query.latest_user_text or "").strip()
    reasons: list[str] = []

    if gate_input.vector_search_on_new_session and (gate_input.turn_index is None or gate_input.turn_index <= 0):
        reasons.append("new_session")

    for keyword in gate_input.trigger_keywords:
        if keyword and keyword in latest_user_text:
            reasons.append(f"keyword:{keyword}")
            break

    every_n = gate_input.vector_search_every_n_turns
    if every_n > 0 and gate_input.turn_index is not None and gate_input.turn_index > 0:
        if gate_input.turn_index % every_n == 0:
            reasons.append(f"periodic:{every_n}")

    avg_confidence = stats[1]
    if gate_input.state_items and avg_confidence is not None:
        if avg_confidence < gate_input.vector_search_when_state_confidence_below:
            reasons.append("low_state_confidence")

    if reasons:
        return _decision(True, reasons[0], reasons, mode, stats)

    text_len = len(latest_user_text)
    if text_len < gate_input.skip_when_latest_user_text_chars_below:
        return _decision(False, "short_latest_user_text", ["short_latest_user_text"], mode, stats)

    if gate_input.skip_when_state_is_sufficient and gate_input.state_items:
        return _decision(False, "state_sufficient", ["state_sufficient"], mode, stats)

    return _decision(True, "no_state_fallback", ["no_state_fallback"], mode, stats)


def _state_stats(items: list[ConversationStateItem]) -> tuple[int, float | None]:
    active_items = [item for item in items if item.status == "active"]
    if not active_items:
        return 0, None
    return len(active_items), sum(item.confidence for item in active_items) / len(active_items)


def _decision(
    should_retrieve: bool,
    reason: str,
    reasons: list[str],
    mode: str,
    stats: tuple[int, float | None],
) -> RetrievalGateDecision:
    return RetrievalGateDecision(
        should_retrieve=should_retrieve,
        reason=reason,
        reasons=reasons,
        mode=mode,
        state_item_count=stats[0],
        avg_state_confidence=stats[1],
    )
