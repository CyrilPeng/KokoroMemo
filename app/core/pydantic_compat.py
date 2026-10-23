"""Small Pydantic v1/v2 compatibility layer for Termux and desktop installs."""

from __future__ import annotations

from typing import Any

import pydantic
from pydantic import BaseModel

PYDANTIC_V2 = pydantic.VERSION.split(".", 1)[0] == "2"

if PYDANTIC_V2:
    from pydantic import ConfigDict
else:
    ConfigDict = None  # type: ignore[assignment]


class CompatBaseModel(BaseModel):
    """Base model that accepts extra fields under both Pydantic major versions."""

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


def validate_model(model_cls: type[BaseModel], data: Any) -> BaseModel:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)
    return model_cls.parse_obj(data)


def dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
