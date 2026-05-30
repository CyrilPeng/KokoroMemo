from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.core.prompts import HOT_CONTEXT_HEADER
from app.memory.query_builder import RetrievalQuery
from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
from app.memory.state_injector import inject_state_board

HOT_CONTEXT_HEADER_ZH = HOT_CONTEXT_HEADER["zh"]


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def make_query(text: str) -> RetrievalQuery:
    return RetrievalQuery(text, text, f"user: {text}", {"user_id": "u1", "character_id": "c1", "conversation_id": "conv1"})


def test_state_injector_preserves_original_system_prompt():
    messages = [
        {"role": "system", "content": "原始设定"},
        {"role": "user", "content": "继续"},
    ]
    injected = inject_state_board(messages, HOT_CONTEXT_HEADER_ZH)
    assert injected[0]["content"] == "原始设定"
    assert injected[1]["content"] == HOT_CONTEXT_HEADER_ZH
    assert injected[2]["role"] == "user"


def test_retrieval_gate_keyword_triggers():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("你还记得上次的约定吗"),
            state_row_count=1,
            avg_state_confidence=0.7,
            turn_index=3,
            trigger_keywords=["还记得", "约定"],
        )
    )
    assert decision.should_retrieve is True
    assert decision.reason.startswith("keyword:")


def test_retrieval_gate_short_text_skips():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("嗯"),
            state_row_count=0,
            avg_state_confidence=None,
            turn_index=3,
            vector_search_on_new_session=False,
            trigger_keywords=[],
            skip_when_latest_user_text_chars_below=4,
        )
    )
    assert decision.should_retrieve is False
    assert decision.reason == "short_latest_user_text"


def test_retrieval_gate_low_confidence_triggers():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("继续推进剧情"),
            state_row_count=1,
            avg_state_confidence=0.3,
            turn_index=3,
            vector_search_on_new_session=False,
            trigger_keywords=[],
            vector_search_when_state_confidence_below=0.65,
        )
    )
    assert decision.should_retrieve is True
    assert decision.reason == "low_state_confidence"


def test_retrieval_gate_new_session():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("你好啊今天天气不错"),
            state_row_count=0,
            avg_state_confidence=None,
            turn_index=0,
            vector_search_on_new_session=True,
            trigger_keywords=[],
            skip_when_latest_user_text_chars_below=4,
        )
    )
    assert decision.should_retrieve is True
    assert "new_session" in decision.reason


def test_retrieval_gate_state_sufficient_skips():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("继续推进剧情"),
            state_row_count=3,
            avg_state_confidence=0.9,
            turn_index=4,
            vector_search_on_new_session=False,
            trigger_keywords=[],
            vector_search_every_n_turns=0,
            vector_search_when_state_confidence_below=0.6,
            skip_when_state_is_sufficient=True,
            skip_when_latest_user_text_chars_below=2,
        )
    )
    assert decision.should_retrieve is False
    assert decision.reason == "state_sufficient"
