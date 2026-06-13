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
    admins = cfg.get("admin_users") or []
    cfg["admin_users"] = [str(item).strip() for item in admins if str(item).strip()]
    return cfg


def build_plugin_config(raw: dict[str, Any] | None) -> PluginConfig:
    cfg = normalize_config(raw)
    return PluginConfig(**cfg)
