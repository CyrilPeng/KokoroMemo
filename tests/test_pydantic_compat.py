from __future__ import annotations

from app.core.pydantic_compat import dump_model, validate_model


class V1LikeModel:
    @classmethod
    def parse_obj(cls, data):
        return {"parsed": data}


class V1LikeInstance:
    def dict(self):
        return {"legacy": True}


def test_validate_model_supports_parse_obj_only_models():
    result = validate_model(V1LikeModel, {"messages": []})

    assert result == {"parsed": {"messages": []}}


def test_dump_model_supports_dict_only_models():
    result = dump_model(V1LikeInstance())

    assert result == {"legacy": True}
