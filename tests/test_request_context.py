"""Tests for inbound request context resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.requests import Request

from app.core.config import AppConfig
from app.proxy.request_parser import resolve_context


def _request(headers: dict[str, str] | None = None, query_string: bytes = b"") -> Request:
    raw_headers = [(name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": raw_headers,
        "query_string": query_string,
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def _cfg(tmp_path: Path, mode: str = "request") -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.sqlite.app_db = str(tmp_path / "app.sqlite")
    cfg.conversation.session_identity_mode = mode
    return cfg


@pytest.mark.asyncio
async def test_request_mode_uses_explicit_conversation_id(tmp_path):
    cfg = _cfg(tmp_path)
    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "metadata": {"conversation_id": "client-session-a"},
    }

    ctx = await resolve_context(_request({"authorization": "Bearer same-key"}), body, str(tmp_path), cfg)

    assert ctx.conversation_id == "client-session-a"


@pytest.mark.asyncio
async def test_api_key_mode_groups_different_client_sessions_by_same_key(tmp_path):
    cfg = _cfg(tmp_path, mode="api_key")
    req = _request({"authorization": "Bearer rp-session-key"})
    body_a = {
        "messages": [{"role": "user", "content": "hello"}],
        "metadata": {"conversation_id": "unstable-session-a"},
    }
    body_b = {
        "messages": [{"role": "user", "content": "again"}],
        "metadata": {"conversation_id": "unstable-session-b"},
    }

    ctx_a = await resolve_context(req, body_a, str(tmp_path), cfg)
    ctx_b = await resolve_context(req, body_b, str(tmp_path), cfg)

    assert ctx_a.conversation_id == ctx_b.conversation_id
    assert ctx_a.conversation_id == "conv_key_rp-session-key"


@pytest.mark.asyncio
async def test_api_key_mode_keeps_keys_isolated(tmp_path):
    cfg = _cfg(tmp_path, mode="api_key")
    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "metadata": {"conversation_id": "same-client-session"},
    }

    ctx_a = await resolve_context(_request({"authorization": "Bearer key-a"}), body, str(tmp_path), cfg)
    ctx_b = await resolve_context(_request({"authorization": "Bearer key-b"}), body, str(tmp_path), cfg)

    assert ctx_a.conversation_id != ctx_b.conversation_id
    assert ctx_a.conversation_id == "conv_key_key-a"
    assert ctx_b.conversation_id == "conv_key_key-b"
    assert ctx_b.conversation_id.startswith("conv_key_")


@pytest.mark.asyncio
async def test_api_key_mode_accepts_query_key_for_gemini_clients(tmp_path):
    cfg = _cfg(tmp_path, mode="api_key")
    body = {"messages": [{"role": "user", "content": "hello"}]}

    ctx_a = await resolve_context(_request(query_string=b"key=gemini-style-key"), body, str(tmp_path), cfg)
    ctx_b = await resolve_context(_request(query_string=b"key=gemini-style-key"), body, str(tmp_path), cfg)

    assert ctx_a.conversation_id == ctx_b.conversation_id
    assert ctx_a.conversation_id == "conv_key_gemini-style-key"


@pytest.mark.asyncio
async def test_api_key_mode_sanitizes_key_before_using_as_conversation_id(tmp_path):
    cfg = _cfg(tmp_path, mode="api_key")
    body = {"messages": [{"role": "user", "content": "hello"}]}

    ctx = await resolve_context(_request({"authorization": "Bearer RP Slot #1"}), body, str(tmp_path), cfg)

    assert ctx.conversation_id == "conv_key_rp_slot_1"
