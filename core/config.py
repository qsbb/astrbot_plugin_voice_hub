from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.xiaomimimo.com/v1",
    "model": "mimo-v2.5-tts-voiceclone",
    "output_format": "wav",
    "default_context": "",
    "max_text_chars": 500,
    "max_voice_file_mb": 10,
    "max_concurrency": 1,
    "send_as_file_fallback": True,
    "emotion_routing_enabled": True,
    "emotion_contexts": {},
    "segment_enabled": True,
    "segment_threshold_chars": 180,
    "segment_max_segments": 6,
    "admin_users": [],
}


@dataclass(slots=True)
class PluginConfig:
    api_key: str
    base_url: str
    model: str
    output_format: str
    default_context: str
    max_text_chars: int
    max_voice_file_mb: int
    max_concurrency: int
    send_as_file_fallback: bool
    emotion_routing_enabled: bool
    emotion_contexts: dict[str, str]
    segment_enabled: bool
    segment_threshold_chars: int
    segment_max_segments: int
    admin_users: list[str]

    @property
    def max_voice_file_bytes(self) -> int:
        return max(1, self.max_voice_file_mb) * 1024 * 1024


def normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for key in cfg:
            if key in raw:
                cfg[key] = raw[key]

    cfg["api_key"] = str(cfg.get("api_key") or "").strip()
    cfg["base_url"] = str(cfg.get("base_url") or DEFAULT_CONFIG["base_url"]).rstrip("/")
    cfg["model"] = str(cfg.get("model") or DEFAULT_CONFIG["model"]).strip()
    cfg["output_format"] = str(cfg.get("output_format") or "wav").strip().lower()
    cfg["default_context"] = str(cfg.get("default_context") or "")
    cfg["max_text_chars"] = max(1, int(cfg.get("max_text_chars") or 500))
    cfg["max_voice_file_mb"] = max(1, int(cfg.get("max_voice_file_mb") or 10))
    cfg["max_concurrency"] = max(1, int(cfg.get("max_concurrency") or 1))
    cfg["send_as_file_fallback"] = bool(cfg.get("send_as_file_fallback", True))
    cfg["emotion_routing_enabled"] = bool(cfg.get("emotion_routing_enabled", True))
    raw_contexts = cfg.get("emotion_contexts") or {}
    if not isinstance(raw_contexts, dict):
        raw_contexts = {}
    cfg["emotion_contexts"] = {
        str(key).strip().lower(): str(value or "").strip()
        for key, value in dict(raw_contexts).items()
        if str(key).strip() and str(value or "").strip()
    }
    cfg["segment_enabled"] = bool(cfg.get("segment_enabled", True))
    cfg["segment_threshold_chars"] = max(1, int(cfg.get("segment_threshold_chars") or 180))
    cfg["segment_max_segments"] = max(1, int(cfg.get("segment_max_segments") or 6))
    admins = cfg.get("admin_users") or []
    cfg["admin_users"] = [str(item).strip() for item in admins if str(item).strip()]
    return cfg


def build_plugin_config(raw: dict[str, Any] | None) -> PluginConfig:
    cfg = normalize_config(raw)
    return PluginConfig(**cfg)
