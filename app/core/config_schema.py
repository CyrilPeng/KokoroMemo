"""Machine-readable configuration metadata and deprecation registry."""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from typing import Any

from app.core.config import AppConfig

DEPRECATED_CONFIG_FIELDS: dict[str, str] = {
    "memory.extraction.extract_after_each_turn": "抽取由 memory.extraction_enabled 控制，该开关未参与运行逻辑",
    "memory.extraction.fallback_rule_based": "规则回退尚未实现，当前判断模型失败时不会回退",
    "memory.hot_context.inject_always": "状态板注入由会话 injection_policy 控制",
    "memory.state_updater.auto_expire_resolved_items": "自动过期尚未实现，resolved 行保留审计",
    "conversation.detect_system_prompt_change": "系统提示词变化检测尚未实现",
}


def _field_default(field) -> Any:
    if field.default is not MISSING:
        return field.default
    if field.default_factory is not MISSING:
        try:
            return field.default_factory()
        except Exception:
            return None
    return None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def iter_config_fields(config_cls: type = AppConfig, prefix: str = "") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for field in fields(config_cls):
        value = _field_default(field)
        path = f"{prefix}.{field.name}" if prefix else field.name
        if is_dataclass(value):
            result.extend(iter_config_fields(type(value), path))
            continue
        reason = DEPRECATED_CONFIG_FIELDS.get(path)
        result.append(
            {
                "path": path,
                "type": str(field.type),
                "default": _json_safe(value),
                "deprecated": reason is not None,
                "deprecation_reason": reason,
            }
        )
    return result


def get_config_schema() -> dict[str, Any]:
    config_fields = iter_config_fields()
    return {
        "version": 1,
        "fields": config_fields,
        "deprecated": [field["path"] for field in config_fields if field["deprecated"]],
    }
