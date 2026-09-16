"""Public ``series.control@1.0`` adapter for safe voice settings."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

FIELDS: dict[str, dict[str, Any]] = {
    "segment_enabled": {
        "type": "bool",
        "default": True,
        "control": "overrideable",
        "secret": False,
    },
    "segment_threshold_chars": {
        "type": "int",
        "default": 180,
        "minimum": 1,
        "maximum": 10000,
        "control": "overrideable",
        "secret": False,
    },
    "segment_max_segments": {
        "type": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 64,
        "control": "overrideable",
        "secret": False,
    },
    "reply_mode": {
        "type": "enum",
        "default": "audio_only",
        "values": ["audio_only", "text_and_audio", "text_only"],
        "control": "overrideable",
        "secret": False,
    },
    "tts_trigger_mode": {
        "type": "enum",
        "default": "probability",
        "values": ["probability", "llm_decides"],
        "control": "overrideable",
        "secret": False,
    },
}


def _path(plugin: Any) -> Path:
    return Path(plugin.data_dir) / "series-control.json"


def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for name, value in values.items():
        definition = FIELDS.get(name)
        if definition is None:
            continue
        if definition["type"] == "bool" and isinstance(value, bool):
            clean[name] = value
        elif (
            definition["type"] == "int"
            and isinstance(value, int)
            and not isinstance(value, bool)
            and definition["minimum"] <= value <= definition["maximum"]
        ):
            clean[name] = value
        elif definition["type"] == "enum" and value in definition["values"]:
            clean[name] = value
    return clean


def _load(plugin: Any) -> dict[str, Any]:
    try:
        raw = json.loads(_path(plugin).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {"revision": 0, "overrides": {}}
    if not isinstance(raw, dict):
        return {"revision": 0, "overrides": {}}
    try:
        revision = int(raw.get("revision", 0) or 0)
    except (TypeError, ValueError):
        revision = 0
    overrides = raw.get("overrides")
    return {
        "revision": max(0, revision),
        "overrides": _clean_values(overrides if isinstance(overrides, dict) else {}),
    }


def _remember_native(plugin: Any, fields: Any) -> None:
    saved = getattr(plugin, "_series_control_native_values", None)
    if saved is None:
        saved = plugin._series_control_native_values = {}
    config = getattr(plugin, "config", {})
    for name in fields:
        if name not in saved:
            saved[name] = config.get(name, FIELDS[name]["default"])


def _native_config(plugin: Any) -> dict[str, Any]:
    native = dict(getattr(plugin, "config", {}) or {})
    for name, value in getattr(plugin, "_series_control_native_values", {}).items():
        native[name] = value
    return native


def native_view(plugin: Any) -> dict[str, Any]:
    """原生配置视图（不含核覆盖层），固化与备份共用。"""
    native = _native_config(plugin)
    return {
        name: native.get(name, definition["default"])
        for name, definition in FIELDS.items()
    }


def sync_runtime(plugin: Any) -> None:
    """按当前模式与磁盘覆盖层重新应用运行时视图（供固化入口复用）。"""
    _apply_runtime(plugin, _load(plugin)["overrides"])


def _apply_runtime(plugin: Any, overrides: dict[str, Any]) -> None:
    effective = _native_config(plugin)
    if getattr(plugin, "_series_control_mode", "native") == "managed":
        effective.update(overrides)
    effective = plugin._coerce_config(effective)
    plugin.config = effective
    builder = getattr(plugin, "build_plugin_config", None)
    if callable(builder):
        plugin.plugin_config = builder(effective)


def _write(plugin: Any, state: dict[str, Any]) -> None:
    path = _path(plugin)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".series-control-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def contract(plugin: Any) -> dict[str, Any]:
    return {
        "name": "series.control@1.0",
        "version": "1.0",
        "series_id": "ningxin_suxi",
        "plugin_id": "astrbot_plugin_voice_hub",
        "plugin_name": "凝心溯溪-声",
        "capabilities": [
            "read_schema",
            "read_snapshot",
            "read_native",
            "validate_patch",
            "apply_patch",
            "reset_override",
            "write_native",
        ],
        "read_only": False,
        "secrets_in_response": False,
        "max_patch_fields": len(FIELDS),
    }


def schema(plugin: Any) -> dict[str, Any]:
    return {
        "contract_name": "series.control@1.0",
        "contract_version": "1.0",
        "plugin_id": "astrbot_plugin_voice_hub",
        "revision": _load(plugin)["revision"],
        "fields": {name: dict(definition) for name, definition in FIELDS.items()},
    }


def snapshot(plugin: Any) -> dict[str, Any]:
    state = _load(plugin)
    overrides = state["overrides"]
    managed_mode = getattr(plugin, "_series_control_mode", "native") == "managed"
    native = _native_config(plugin)
    fields = {}
    for name, definition in FIELDS.items():
        item: dict[str, Any] = {
            "native_configured": name in (getattr(plugin, "config", {}) or {}),
            "managed_configured": name in overrides,
            "effective_source": "managed"
            if managed_mode and name in overrides
            else "plugin",
            "effective_value": overrides[name]
            if managed_mode and name in overrides
            else native.get(name, definition["default"]),
        }
        # 原生配置现值：供核「一键读取 / 一键固化」使用；secret 不回传。
        if definition.get("secret") or definition.get("write_only"):
            item["secret"] = True
        else:
            item["native_value"] = native.get(name, definition["default"])
        fields[name] = item
    return {"status": "ok", "revision": state["revision"], "fields": fields}


def set_mode(plugin: Any, mode: str) -> dict[str, Any]:
    next_mode = mode if mode in {"native", "managed"} else "native"
    if next_mode == "managed":
        overrides = _load(plugin)["overrides"]
        _remember_native(plugin, overrides)
        plugin._series_control_mode = next_mode
        _apply_runtime(plugin, overrides)
    else:
        plugin._series_control_mode = "native"
        _apply_runtime(plugin, {})
        plugin._series_control_native_values = {}
    return {"success": True, "mode": plugin._series_control_mode}


def validate(plugin: Any, patch: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
    state = _load(plugin)
    if state["revision"] != int(expected_revision):
        return {"valid": False, "reason": "REVISION_CONFLICT"}
    if not isinstance(patch, dict) or not patch or len(patch) > len(FIELDS):
        return {"valid": False, "reason": "PATCH_INVALID"}
    for name, value in patch.items():
        definition = FIELDS.get(name)
        if definition is None:
            return {"valid": False, "reason": "PATCH_INVALID"}
        if definition["type"] == "bool" and not isinstance(value, bool):
            return {"valid": False, "reason": "PATCH_INVALID"}
        if definition["type"] == "int" and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not definition["minimum"] <= value <= definition["maximum"]
        ):
            return {"valid": False, "reason": "PATCH_INVALID"}
        if definition["type"] == "enum" and value not in definition["values"]:
            return {"valid": False, "reason": "PATCH_INVALID"}
    return {"valid": True, "revision": state["revision"]}


def apply(plugin: Any, patch: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
    result = validate(plugin, patch, expected_revision=expected_revision)
    if not result.get("valid"):
        return {"success": False, **result}
    state = _load(plugin)
    before = dict(state["overrides"])
    before_revision = state["revision"]
    before_native = dict(getattr(plugin, "_series_control_native_values", {}))
    if getattr(plugin, "_series_control_mode", "native") == "managed":
        _remember_native(plugin, patch)
    state["overrides"].update(patch)
    state["revision"] += 1
    try:
        _write(plugin, {"schema_version": 1, **state})
        _apply_runtime(plugin, state["overrides"])
    except Exception:
        state["overrides"] = before
        state["revision"] = before_revision
        plugin._series_control_native_values = before_native
        try:
            _write(plugin, {"schema_version": 1, **state})
            _apply_runtime(plugin, before)
        except Exception:
            pass
        return {"success": False, "reason": "APPLY_FAILED_ROLLED_BACK"}
    return {"success": True, "revision": state["revision"]}


def native_write(
    plugin: Any,
    patch: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """一键固化：把当前生效值写进插件自身配置（核掉线后仍按此运行）。

    只接受 FIELDS 白名单字段；先做类型/边界校验，再交给插件层备份 +
    运行时同步 + 原子落盘。任何失败都返回 error，覆盖层与 revision 不变。
    """
    state = _load(plugin)
    revision = state["revision"]
    try:
        expected = revision if expected_revision is None else int(expected_revision)
    except (TypeError, ValueError):
        return {
            "status": "error",
            "reason": "REVISION_CONFLICT",
            "revision": revision,
        }
    if expected != revision:
        return {
            "status": "error",
            "reason": "REVISION_CONFLICT",
            "revision": revision,
        }
    if not isinstance(patch, dict) or not patch or len(patch) > len(FIELDS):
        return {"status": "error", "reason": "PATCH_INVALID", "revision": revision}
    clean: dict[str, Any] = {}
    for name, value in patch.items():
        definition = FIELDS.get(name)
        if definition is None:
            return {
                "status": "error",
                "reason": "UNKNOWN_FIELD",
                "field": str(name),
                "revision": revision,
            }
        kind = definition["type"]
        if kind == "bool":
            if not isinstance(value, bool):
                return {
                    "status": "error",
                    "reason": "INVALID_TYPE",
                    "field": name,
                    "revision": revision,
                }
        elif kind == "int":
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not definition["minimum"] <= value <= definition["maximum"]
            ):
                return {
                    "status": "error",
                    "reason": "INVALID_VALUE",
                    "field": name,
                    "revision": revision,
                }
        elif kind == "enum":
            if value not in definition["values"]:
                return {
                    "status": "error",
                    "reason": "INVALID_VALUE",
                    "field": name,
                    "revision": revision,
                }
        else:  # pragma: no cover - 白名单 schema 固定，防御性兜底
            return {
                "status": "error",
                "reason": "INVALID_TYPE",
                "field": name,
                "revision": revision,
            }
        clean[name] = value

    hook = getattr(plugin, "_apply_native_series_control_values", None)
    if not callable(hook):
        return {"status": "error", "reason": "UNSUPPORTED", "revision": revision}
    outcome = hook(clean)
    if not isinstance(outcome, dict) or outcome.get("status") != "ok":
        reason = str((outcome or {}).get("reason") or "PERSIST_FAILED")
        return {"status": "error", "reason": reason, "revision": revision}
    return {
        "status": "ok",
        "reason": "APPLIED",
        "revision": revision,
        "written": list(outcome.get("written") or sorted(clean)),
        "skipped": list(outcome.get("skipped") or []),
        "backup_id": str(outcome.get("backup_id") or ""),
    }


def reset(
    plugin: Any,
    fields: list[str] | None,
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    state = _load(plugin)
    if expected_revision is not None and state["revision"] != int(expected_revision):
        return {"success": False, "reason": "REVISION_CONFLICT"}
    names = list(state["overrides"]) if fields is None else fields
    if any(name not in FIELDS for name in names):
        return {"success": False, "reason": "PATCH_INVALID"}
    before = dict(state["overrides"])
    before_revision = state["revision"]
    for name in names:
        state["overrides"].pop(name, None)
    state["revision"] += 1
    try:
        _write(plugin, {"schema_version": 1, **state})
        _apply_runtime(plugin, state["overrides"])
    except Exception:
        state["overrides"] = before
        state["revision"] = before_revision
        try:
            _write(plugin, {"schema_version": 1, **state})
            _apply_runtime(plugin, before)
        except Exception:
            pass
        return {"success": False, "reason": "APPLY_FAILED_ROLLED_BACK"}
    return {"success": True, "revision": state["revision"]}
