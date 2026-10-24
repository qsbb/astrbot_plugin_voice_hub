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
    "reply_mode": "audio_only",
    "auto_tts_enabled": False,
    "tts_trigger_mode": "probability",
    "auto_tts_probability": 0.0,
    "auto_tts_group_whitelist": [],
    "auto_tts_group_blacklist": [],
    "auto_tts_private_whitelist": [],
    "auto_tts_private_blacklist": [],
    "file_fallback_enabled": True,
    "output_retention_days": 7,
    "output_max_files": 100,
    "emotion_routing_enabled": True,
    "emotion_contexts": {},
    "ai_style_director_enabled": False,
    "ai_style_director_provider_id": "",
    "ai_style_director_prompt": "",
    "ai_style_director_mode": "direct",
    "ai_style_director_max_chars": 120,
    "ai_style_director_optimize_text": True,
    "ai_style_director_fallback_to_emotion": True,
    "ai_style_director_debug_log": True,
    "segment_enabled": True,
    "segment_threshold_chars": 180,
    "segment_max_segments": 6,
    "segment_delay_per_audio_second_ms": 700,
    "segment_delay_ms": 350,
    "admin_users": [],
    "replace_url_in_tts": True,
    "api_server_enabled": False,
    "api_server_host": "127.0.0.1",
    "api_server_port": 9960,
    "api_server_token": "",
    "api_server_rate_limit_per_minute": 30,
    "api_server_max_input_chars": 500,
    "tts_backend": "mimo",  # "mimo" / "astrbot" / "fishaudio"
    "astrbot_tts_provider_id": "",  # 空=用 AstrBot 默认 TTS 提供商
    # FishAudio 后端（官方 api.fish.audio / api.fish-audio.cn 或自建兼容接口）
    "fishaudio_api_key": "",
    "fishaudio_api_base": "https://api.fish-audio.cn/v1",
    "fishaudio_reference_id": "",  # 32 位十六进制参考模型 ID；空=可按角色名查询
    "fishaudio_character": "",  # reference_id 为空时的角色名回退（仅官方接口）
    "fishaudio_model": "auto",  # auto / s2.1-pro-free / s2.1-pro / s2-pro / s1
    "fishaudio_emotion_mode": "balanced",  # balanced / expressive / manual
    "fishaudio_timeout_seconds": 120,
    "fishaudio_proxy": "",  # NAS 直连被劫持/拦截时填 http://127.0.0.1:7897 之类
    # 音频传输方式：path=本地路径（要求 NapCat 能读到 AstrBot 文件系统）
    # base64=Record 内嵌 base64://（跨机部署默认）；shared_path=WSL/Linux+Windows 共享目录
    "audio_transport": "path",
    "shared_path_linux": "/mnt/c/Users/Public/mimo_tts_audio",
    "shared_path_windows": "C:\\Users\\Public\\mimo_tts_audio",
    "base64_max_mb": 50,
    # LLM 情绪化朗读判断：probability 模式下让主 LLM 在回复开头输出朗读意愿标记
    "llm_tts_judge_enabled": False,
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
    reply_mode: str
    auto_tts_enabled: bool
    tts_trigger_mode: str
    auto_tts_probability: float
    auto_tts_group_whitelist: list[str]
    auto_tts_group_blacklist: list[str]
    auto_tts_private_whitelist: list[str]
    auto_tts_private_blacklist: list[str]
    file_fallback_enabled: bool
    output_retention_days: int
    output_max_files: int
    emotion_routing_enabled: bool
    emotion_contexts: dict[str, str]
    ai_style_director_enabled: bool
    ai_style_director_provider_id: str
    ai_style_director_prompt: str
    ai_style_director_mode: str
    ai_style_director_max_chars: int
    ai_style_director_optimize_text: bool
    ai_style_director_fallback_to_emotion: bool
    ai_style_director_debug_log: bool
    segment_enabled: bool
    segment_threshold_chars: int
    segment_max_segments: int
    segment_delay_per_audio_second_ms: int
    segment_delay_ms: int
    admin_users: list[str]
    replace_url_in_tts: bool
    api_server_enabled: bool
    api_server_host: str
    api_server_port: int
    api_server_token: str
    api_server_rate_limit_per_minute: int
    api_server_max_input_chars: int
    tts_backend: str
    astrbot_tts_provider_id: str
    fishaudio_api_key: str
    fishaudio_api_base: str
    fishaudio_reference_id: str
    fishaudio_character: str
    fishaudio_model: str
    fishaudio_emotion_mode: str
    fishaudio_timeout_seconds: float
    fishaudio_proxy: str
    audio_transport: str
    shared_path_linux: str
    shared_path_windows: str
    base64_max_mb: int
    llm_tts_judge_enabled: bool

    @property
    def max_voice_file_bytes(self) -> int:
        return max(1, self.max_voice_file_mb) * 1024 * 1024


def normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    raw_has_file_fallback = False
    raw_has_trigger_mode = False
    legacy_file_fallback = DEFAULT_CONFIG["file_fallback_enabled"]
    legacy_auto_tts_enabled = DEFAULT_CONFIG["auto_tts_enabled"]
    if isinstance(raw, dict):
        raw_has_file_fallback = "file_fallback_enabled" in raw
        raw_has_trigger_mode = "tts_trigger_mode" in raw
        legacy_file_fallback = _bool_value(raw.get("send_as_file_fallback", True))
        legacy_auto_tts_enabled = _bool_value(raw.get("auto_tts_enabled", False))
        for key in cfg:
            if key in raw:
                cfg[key] = raw[key]

    cfg["api_key"] = str(cfg.get("api_key") or "").strip()
    cfg["base_url"] = str(cfg.get("base_url") or DEFAULT_CONFIG["base_url"]).rstrip("/")
    cfg["model"] = str(cfg.get("model") or DEFAULT_CONFIG["model"]).strip()
    cfg["output_format"] = str(cfg.get("output_format") or "wav").strip().lower()
    cfg["default_context"] = str(cfg.get("default_context") or "")
    cfg["max_text_chars"] = _int_at_least(cfg.get("max_text_chars"), 500, 1)
    cfg["max_voice_file_mb"] = _int_at_least(cfg.get("max_voice_file_mb"), 10, 1)
    cfg["max_concurrency"] = _int_at_least(cfg.get("max_concurrency"), 1, 1)
    reply_mode = str(cfg.get("reply_mode") or "audio_only").strip().lower()
    if reply_mode not in {"audio_only", "text_and_audio", "text_only"}:
        reply_mode = "audio_only"
    cfg["reply_mode"] = reply_mode
    if raw_has_trigger_mode:
        trigger_mode = str(cfg.get("tts_trigger_mode") or "probability").strip().lower()
        if trigger_mode not in {"probability", "llm_decides"}:
            trigger_mode = "probability"
    else:
        trigger_mode = "probability" if legacy_auto_tts_enabled else "llm_decides"
    cfg["tts_trigger_mode"] = trigger_mode
    cfg["auto_tts_enabled"] = trigger_mode == "probability"
    try:
        probability = float(cfg.get("auto_tts_probability") or 0.0)
    except (TypeError, ValueError):
        probability = 0.0
    cfg["auto_tts_probability"] = min(1.0, max(0.0, probability))
    cfg["auto_tts_group_whitelist"] = _string_list(cfg.get("auto_tts_group_whitelist"))
    cfg["auto_tts_group_blacklist"] = _string_list(cfg.get("auto_tts_group_blacklist"))
    cfg["auto_tts_private_whitelist"] = _string_list(
        cfg.get("auto_tts_private_whitelist")
    )
    cfg["auto_tts_private_blacklist"] = _string_list(
        cfg.get("auto_tts_private_blacklist")
    )
    cfg["file_fallback_enabled"] = _bool_value(
        cfg.get("file_fallback_enabled")
        if raw_has_file_fallback
        else legacy_file_fallback
    )
    cfg["output_retention_days"] = _int_at_least(cfg.get("output_retention_days"), 7, 0)
    cfg["output_max_files"] = _int_at_least(cfg.get("output_max_files"), 100, 0)
    cfg["emotion_routing_enabled"] = _bool_value(
        cfg.get("emotion_routing_enabled", True)
    )
    raw_contexts = cfg.get("emotion_contexts") or {}
    if not isinstance(raw_contexts, dict):
        raw_contexts = {}
    cfg["emotion_contexts"] = {
        str(key).strip().lower(): str(value or "").strip()
        for key, value in dict(raw_contexts).items()
        if str(key).strip() and str(value or "").strip()
    }
    cfg["ai_style_director_enabled"] = _bool_value(
        cfg.get("ai_style_director_enabled", False)
    )
    cfg["ai_style_director_provider_id"] = str(
        cfg.get("ai_style_director_provider_id") or ""
    ).strip()
    cfg["ai_style_director_prompt"] = str(
        cfg.get("ai_style_director_prompt") or ""
    ).strip()
    style_mode = str(cfg.get("ai_style_director_mode") or "direct").strip().lower()
    if style_mode not in {"direct", "hybrid"}:
        style_mode = "direct"
    cfg["ai_style_director_mode"] = style_mode
    cfg["ai_style_director_max_chars"] = _int_at_least(
        cfg.get("ai_style_director_max_chars"), 120, 20
    )
    cfg["ai_style_director_optimize_text"] = _bool_value(
        cfg.get("ai_style_director_optimize_text", True)
    )
    cfg["ai_style_director_fallback_to_emotion"] = _bool_value(
        cfg.get("ai_style_director_fallback_to_emotion", True)
    )
    cfg["ai_style_director_debug_log"] = _bool_value(
        cfg.get("ai_style_director_debug_log", True)
    )
    cfg["segment_enabled"] = _bool_value(cfg.get("segment_enabled", True))
    cfg["segment_threshold_chars"] = _int_at_least(
        cfg.get("segment_threshold_chars"), 180, 1
    )
    cfg["segment_max_segments"] = _int_at_least(cfg.get("segment_max_segments"), 6, 1)
    cfg["segment_delay_per_audio_second_ms"] = _int_between(
        cfg.get("segment_delay_per_audio_second_ms"), 700, 0, 2000
    )
    cfg["segment_delay_ms"] = _int_between(cfg.get("segment_delay_ms"), 350, 0, 5000)
    admins = cfg.get("admin_users") or []
    cfg["admin_users"] = _string_list(admins)
    # 兼容 v0.4.4 的 skip_url_tts 配置项，迁移到 replace_url_in_tts
    if "replace_url_in_tts" not in raw and "skip_url_tts" in raw:
        cfg["replace_url_in_tts"] = _bool_value(raw.get("skip_url_tts", True))
    cfg["replace_url_in_tts"] = _bool_value(cfg.get("replace_url_in_tts", True))
    cfg["api_server_enabled"] = _bool_value(cfg.get("api_server_enabled", False))
    cfg["api_server_host"] = str(
        cfg.get("api_server_host") or DEFAULT_CONFIG["api_server_host"]
    ).strip()
    cfg["api_server_port"] = _int_between(
        cfg.get("api_server_port"), 9960, 1, 65535
    )
    cfg["api_server_token"] = str(cfg.get("api_server_token") or "").strip()
    cfg["api_server_rate_limit_per_minute"] = _int_between(
        cfg.get("api_server_rate_limit_per_minute"), 30, 1, 10000
    )
    cfg["api_server_max_input_chars"] = _int_between(
        cfg.get("api_server_max_input_chars"), 500, 1, 10000
    )
    backend = str(cfg.get("tts_backend") or "mimo").strip().lower()
    if backend not in {"mimo", "astrbot", "fishaudio"}:
        backend = "mimo"
    cfg["tts_backend"] = backend
    cfg["astrbot_tts_provider_id"] = str(
        cfg.get("astrbot_tts_provider_id") or ""
    ).strip()
    cfg["fishaudio_api_key"] = str(cfg.get("fishaudio_api_key") or "").strip()
    cfg["fishaudio_api_base"] = (
        str(cfg.get("fishaudio_api_base") or "https://api.fish-audio.cn/v1").strip().rstrip("/")
        or "https://api.fish-audio.cn/v1"
    )
    cfg["fishaudio_reference_id"] = str(cfg.get("fishaudio_reference_id") or "").strip()
    cfg["fishaudio_character"] = str(cfg.get("fishaudio_character") or "").strip()
    fishaudio_model = str(cfg.get("fishaudio_model") or "auto").strip().lower()
    if fishaudio_model not in {"auto", "s2.1-pro-free", "s2.1-pro", "s2-pro", "s1", "drama-3"}:
        fishaudio_model = "auto"
    cfg["fishaudio_model"] = fishaudio_model
    fishaudio_mode = str(cfg.get("fishaudio_emotion_mode") or "balanced").strip().lower()
    if fishaudio_mode not in {"balanced", "expressive", "manual"}:
        fishaudio_mode = "balanced"
    cfg["fishaudio_emotion_mode"] = fishaudio_mode
    try:
        cfg["fishaudio_timeout_seconds"] = max(
            5.0, min(600.0, float(cfg.get("fishaudio_timeout_seconds") or 120))
        )
    except (TypeError, ValueError):
        cfg["fishaudio_timeout_seconds"] = 120.0
    cfg["fishaudio_proxy"] = str(cfg.get("fishaudio_proxy") or "").strip()
    transport = str(cfg.get("audio_transport") or "path").strip().lower()
    if transport not in {"path", "base64", "shared_path"}:
        transport = "path"
    cfg["audio_transport"] = transport
    cfg["shared_path_linux"] = str(cfg.get("shared_path_linux") or "").strip()
    cfg["shared_path_windows"] = str(cfg.get("shared_path_windows") or "").strip()
    try:
        cfg["base64_max_mb"] = max(1, min(500, int(cfg.get("base64_max_mb") or 50)))
    except (TypeError, ValueError):
        cfg["base64_max_mb"] = 50
    cfg["llm_tts_judge_enabled"] = _bool_value(cfg.get("llm_tts_judge_enabled", False))
    return cfg


def build_plugin_config(raw: dict[str, Any] | None) -> PluginConfig:
    cfg = normalize_config(raw)
    return PluginConfig(**cfg)


def _int_at_least(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _int_between(value: Any, default: int, minimum: int, maximum: int) -> int:
    return min(maximum, _int_at_least(value, default, minimum))


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace("，", ",").replace("\n", ",").split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
