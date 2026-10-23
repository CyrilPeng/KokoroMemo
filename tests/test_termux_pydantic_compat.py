from __future__ import annotations

import pydantic
import pytest

if pydantic.VERSION.split(".", 1)[0] == "2":
    pytest.skip("Termux pydantic v1 compatibility job only", allow_module_level=True)


def test_backend_imports_with_pydantic_v1():
    import app.main

    assert app.main.app is not None


def test_openai_request_model_validates_with_pydantic_v1():
    from app.api.routes_openai import ChatCompletionRequest
    from app.core.pydantic_compat import validate_model

    request = validate_model(
        ChatCompletionRequest,
        {"messages": [{"role": "user", "content": "你好"}]},
    )

    assert request.messages[0].role == "user"
    assert request.messages[0].content == "你好"


def test_admin_payload_keeps_extra_fields_with_pydantic_v1():
    from app.api.admin.schemas import AdminPayload
    from app.core.pydantic_compat import validate_model

    payload = validate_model(AdminPayload, {"profile_id": "airp_roleplay", "custom": 1})

    assert payload.profile_id == "airp_roleplay"
    assert payload.custom == 1
