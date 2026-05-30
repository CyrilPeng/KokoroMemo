"""Rule-based gate for deciding whether long-term retrieval is needed."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.query_builder import RetrievalQuery


@dataclass
class RetrievalGateInput:
    query: RetrievalQuery
    state_row_count: int = 0
    avg_state_confidence: float | None = None
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
    state_count = gate_input.state_row_count
    avg_confidence = gate_input.avg_state_confidence
    if mode == "always":
        return _decision(True, "mode_always", ["mode_always"], mode, state_count, avg_confidence)
    if mode == "never":
        return _decision(False, "mode_never", ["mode_never"], mode, state_count, avg_confidence)

    latest_user_text = (gate_input.query.latest_user_text or "").strip()

    if mode == "keyword_only":
        for keyword in gate_input.trigger_keywords:
            if keyword and keyword in latest_user_text:
                return _decision(True, f"keyword:{keyword}", [f"keyword:{keyword}"], mode, state_count, avg_confidence)
        return _decision(False, "no_keyword_match", ["no_keyword_match"], mode, state_count, avg_confidence)

    reasons: list[str] = []

    if gate_input.vector_search_on_new_session and (gate_input.turn_index is None or gate_input.turn_index <= 0):
        reasons.append("new_session")

    for keyword in gate_input.trigger_keywords:
        if keyword and keyword in latest_user_text:
            reasons.append(f"keyword:{keyword}")
            break

    every_n = gate_input.vector_search_every_n_turns
    if every_n > 0 and gate_input.turn_index is not None and gate_input.turn_index > 0 and gate_input.turn_index % every_n == 0:
        reasons.append(f"periodic:{every_n}")

    if state_count > 0 and avg_confidence is not None and avg_confidence < gate_input.vector_search_when_state_confidence_below:
        reasons.append("low_state_confidence")

    if reasons:
        return _decision(True, reasons[0], reasons, mode, state_count, avg_confidence)

    text_len = len(latest_user_text)
    if text_len < gate_input.skip_when_latest_user_text_chars_below:
        return _decision(False, "short_latest_user_text", ["short_latest_user_text"], mode, state_count, avg_confidence)

    if gate_input.skip_when_state_is_sufficient and state_count > 0:
        return _decision(False, "state_sufficient", ["state_sufficient"], mode, state_count, avg_confidence)

    return _decision(True, "no_state_fallback", ["no_state_fallback"], mode, state_count, avg_confidence)


def _decision(
    should_retrieve: bool,
    reason: str,
    reasons: list[str],
    mode: str,
    state_count: int,
    avg_confidence: float | None,
) -> RetrievalGateDecision:
    return RetrievalGateDecision(
        should_retrieve=should_retrieve,
        reason=reason,
        reasons=reasons,
        mode=mode,
        state_item_count=state_count,
        avg_state_confidence=avg_confidence,
    )
