"""``series.webui@2.0`` 统一管理面适配层（声）。

核 WebUI 只负责鉴权、动作表单、文件上传和结果展示；音色状态仍由
``VoiceStore`` 独占，参考音频仍由 ``store_voice_sample`` 校验和落盘，
试听仍复用 ``PagesAPIMixin._synthesize_preview_audio``，连接测试复用
``synthesize_text``。本模块只做参数验证、风险元数据和公开字段投影，绝不
把音频路径、API Key、provider 错误正文或本地文件信息返回给核。
"""

from __future__ import annotations

import asyncio
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from .core.audio_codec import AudioValidationError
from .core.emotion import SUPPORTED_EMOTIONS, normalize_emotion
from .core.pages_upload import store_voice_sample
from .pages_api import VoicePreviewError

CONTRACT_NAME = "series.webui@2.0"
CONTRACT_VERSION = "2.0"
PLUGIN_ID = "astrbot_plugin_voice_hub"
SERIES_ID = "ningxin_suxi"

VOICES_PANEL_ID = "voices"
CONFIG_PANEL_ID = "config"

PREVIEW_ACTION_ID = "preview_voice"
CREATE_ACTION_ID = "create_voice"
UPDATE_ACTION_ID = "update_voice"
DELETE_ACTION_ID = "delete_voice"
SET_DEFAULT_ACTION_ID = "set_default_voice"
SET_EMOTION_ACTION_ID = "set_emotion_voice"
SAVE_CONFIG_ACTION_ID = "save_tts_config"
TEST_CONNECTION_ACTION_ID = "test_connection"

MAX_VOICE_ID_CHARS = 128
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 1_000
MAX_STYLE_CONTEXT_CHARS = 2_000
MAX_STYLE_TAGS_CHARS = 500
MAX_SCOPE_ID_CHARS = 128
MAX_API_KEY_CHARS = 4_096
MAX_BASE_URL_CHARS = 2_048
MAX_MODEL_CHARS = 256
MAX_PROVIDER_ID_CHARS = 256
MAX_DEFAULT_CONTEXT_CHARS = 2_000
MAX_TEST_TEXT_CHARS = 500

_VOICE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SCOPE_ID = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")
_TTS_BACKENDS = {"mimo", "astrbot"}
_OUTPUT_FORMATS = {"wav"}
_TTS_TRIGGER_MODES = {"probability", "llm_decides"}
_REPLY_MODES = {"audio_only", "text_and_audio", "text_only"}
_DIRECTOR_MODES = {"direct", "hybrid"}
_ROLE_LEVELS = {"viewer": 0, "admin": 1, "owner": 2}

_ALLOWED_CONFIG_FIELDS = {
    "tts_backend",
    "astrbot_tts_provider_id",
    "api_key",
    "base_url",
    "model",
    "output_format",
    "auto_tts_enabled",
    "tts_trigger_mode",
    "reply_mode",
    "max_text_chars",
    "max_concurrency",
    "emotion_routing_enabled",
    "default_context",
    "segment_enabled",
    "segment_threshold_chars",
    "segment_max_segments",
    "segment_delay_ms",
    "segment_delay_per_audio_second_ms",
    "ai_style_director_enabled",
    "ai_style_director_provider_id",
    "ai_style_director_mode",
    "ai_style_director_max_chars",
    "ai_style_director_optimize_text",
    "ai_style_director_fallback_to_emotion",
}


def _failure(code: str, message: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"success": False, "error": code}
    if message:
        payload["message"] = message
    return payload


def _success(message: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"success": True}
    if message:
        payload["message"] = message
    payload.update(extra)
    return payload


def _public_voice(voice: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(voice, "id", "") or ""),
        "name": str(getattr(voice, "name", "") or ""),
        "description": str(getattr(voice, "description", "") or ""),
        "enabled": bool(getattr(voice, "enabled", False)),
        "consent_confirmed": bool(getattr(voice, "consent_confirmed", False)),
        "style_context": str(getattr(voice, "style_context", "") or ""),
        "style_tags": str(getattr(voice, "style_tags", "") or ""),
        "emotion": str(getattr(voice, "emotion", "") or ""),
    }


def _default_summary(defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "global_default_voice_id": str(
            defaults.get("global_default_voice_id") or ""
        ),
        "user_default_count": len(defaults.get("user_defaults") or {}),
        "group_default_count": len(defaults.get("group_defaults") or {}),
        "emotion_default_count": len(defaults.get("emotion_defaults") or {}),
    }


class SeriesWebUIPanels:
    """实现声插件侧的 ``series.webui@2.0`` 面板与动作契约。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    # ---------- 契约声明 ----------

    def contract(self) -> dict[str, Any]:
        return {
            "name": CONTRACT_NAME,
            "version": CONTRACT_VERSION,
            "plugin_id": PLUGIN_ID,
            "series_id": SERIES_ID,
            "state_owner": "plugin",
            "managed": {
                "supported": True,
                "level": "actions",
                "preferred_surface": "kernel",
            },
            "standalone": {"available": True, "pages": ["settings"]},
            "capabilities": [
                "artifacts",
                "audio_preview",
                "file_upload",
                "generic_actions",
                "generic_table",
                "idempotency",
                "revision",
            ],
            "module_capabilities": ["control", "diagnostics"],
            "panels": [
                {
                    "id": VOICES_PANEL_ID,
                    "title": "音色管理",
                    "description": "管理音色、参考音频、默认映射并生成受控试听",
                    "actions": self._voice_actions(),
                },
                {
                    "id": CONFIG_PANEL_ID,
                    "title": "语音与 AI 配置",
                    "description": "保存常用 TTS / AI 导演设置并测试连接",
                    "actions": self._config_actions(),
                },
            ],
        }

    def _voice_options(self, *, include_disabled: bool = True) -> list[list[str]]:
        try:
            voices = self.plugin.voice_store.list_voices(
                include_disabled=include_disabled
            )
        except Exception:
            return []
        return [
            [str(voice.id), str(voice.name or voice.id)]
            for voice in voices
            if str(voice.id or "")
        ]

    def _preview_action(self) -> dict[str, Any]:
        try:
            max_text_chars = max(
                1, int(getattr(self.plugin.plugin_config, "max_text_chars", 500) or 500)
            )
        except (TypeError, ValueError):
            max_text_chars = 500
        return {
            "id": PREVIEW_ACTION_ID,
            "label": "生成试听",
            "confirm": "使用所选音色生成试听音频？",
            "effect": "idempotent",
            "revision_required": False,
            "idempotency_required": False,
            "min_role": "admin",
            "payload_fields": [
                {
                    "name": "text",
                    "label": "试听文本",
                    "type": "text",
                    "required": True,
                    "max_length": max_text_chars,
                    "hint": f"最多 {max_text_chars} 字",
                },
                {
                    "name": "voice",
                    "label": "音色",
                    "type": "select",
                    "required": True,
                    "options": self._voice_options(include_disabled=False),
                },
                {
                    "name": "emotion",
                    "label": "情绪",
                    "type": "select",
                    "required": False,
                    "options": [["", "自动"]]
                    + [[emotion, emotion] for emotion in SUPPORTED_EMOTIONS],
                },
            ],
        }

    def _voice_actions(self) -> list[dict[str, Any]]:
        voice_field = {
            "name": "voice_id",
            "label": "音色",
            "type": "select",
            "required": True,
            "options": self._voice_options(include_disabled=True),
        }
        scope_field = {
            "name": "scope",
            "label": "默认范围",
            "type": "select",
            "required": True,
            "options": [
                ["global", "全局默认"],
                ["user", "指定用户"],
                ["group", "指定群组"],
            ],
        }
        return [
            self._preview_action(),
            {
                "id": CREATE_ACTION_ID,
                "label": "上传参考音频并创建音色",
                "effect": "non_idempotent",
                "idempotency_required": True,
                "revision_required": False,
                "min_role": "admin",
                "timeout_seconds": 30,
                "confirm": "确认上传参考音频并创建新音色？请确保已获得音频所有者授权。",
                "payload_fields": [
                    {
                        "name": "file",
                        "label": "参考音频（mp3 / wav）",
                        "type": "file",
                        "required": True,
                        "hint": "文件会先经过核制品传输，再由声现有音频校验逻辑落盘。",
                    },
                    {
                        "name": "name",
                        "label": "音色名称",
                        "type": "text",
                        "required": True,
                        "max_length": MAX_NAME_CHARS,
                    },
                    {
                        "name": "description",
                        "label": "说明",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_DESCRIPTION_CHARS,
                    },
                    {
                        "name": "style_context",
                        "label": "风格提示",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_STYLE_CONTEXT_CHARS,
                    },
                    {
                        "name": "style_tags",
                        "label": "风格标签",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_STYLE_TAGS_CHARS,
                    },
                    {
                        "name": "emotion",
                        "label": "默认情绪",
                        "type": "select",
                        "required": False,
                        "options": [["", "不指定"]]
                        + [[emotion, emotion] for emotion in SUPPORTED_EMOTIONS],
                    },
                    {
                        "name": "consent_confirmed",
                        "label": "已获得声音所有者授权",
                        "type": "bool",
                        "required": True,
                    },
                ],
            },
            {
                "id": UPDATE_ACTION_ID,
                "label": "更新音色设置",
                "effect": "idempotent",
                "idempotency_required": False,
                "revision_required": False,
                "min_role": "admin",
                "confirm": "确认更新所选音色的公开设置？",
                "payload_fields": [
                    voice_field,
                    {
                        "name": "name",
                        "label": "新名称（留空保持不变）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_NAME_CHARS,
                    },
                    {
                        "name": "description",
                        "label": "新说明（留空保持不变）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_DESCRIPTION_CHARS,
                    },
                    {
                        "name": "enabled",
                        "label": "启用状态",
                        "type": "select",
                        "required": False,
                        "options": [
                            ["", "保持不变"],
                            ["true", "启用"],
                            ["false", "停用"],
                        ],
                    },
                    {
                        "name": "style_context",
                        "label": "风格提示（留空保持不变）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_STYLE_CONTEXT_CHARS,
                    },
                    {
                        "name": "style_tags",
                        "label": "风格标签（留空保持不变）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_STYLE_TAGS_CHARS,
                    },
                    {
                        "name": "emotion",
                        "label": "默认情绪",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["__clear__", "清除"]]
                        + [[emotion, emotion] for emotion in SUPPORTED_EMOTIONS],
                    },
                ],
            },
            {
                "id": DELETE_ACTION_ID,
                "label": "永久删除音色",
                "effect": "non_idempotent",
                "idempotency_required": True,
                "revision_required": False,
                "min_role": "owner",
                "confirm": "确认永久删除该音色及其参考音频？此操作不可撤销。",
                "payload_fields": [voice_field],
            },
            {
                "id": SET_DEFAULT_ACTION_ID,
                "label": "设置默认音色",
                "effect": "idempotent",
                "idempotency_required": False,
                "revision_required": False,
                "min_role": "admin",
                "confirm": "确认修改该范围的默认音色？",
                "payload_fields": [
                    scope_field,
                    voice_field,
                    {
                        "name": "user_id",
                        "label": "用户 ID（scope=user）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_SCOPE_ID_CHARS,
                    },
                    {
                        "name": "group_id",
                        "label": "群组 ID（scope=group）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_SCOPE_ID_CHARS,
                    },
                ],
            },
            {
                "id": SET_EMOTION_ACTION_ID,
                "label": "设置情绪映射",
                "effect": "idempotent",
                "idempotency_required": False,
                "revision_required": False,
                "min_role": "admin",
                "confirm": "确认修改该情绪的默认音色映射？",
                "payload_fields": [
                    {
                        "name": "emotion",
                        "label": "情绪",
                        "type": "select",
                        "required": True,
                        "options": [
                            [emotion, emotion] for emotion in SUPPORTED_EMOTIONS
                        ],
                    },
                    {
                        "name": "voice_id",
                        "label": "音色（留空清除映射）",
                        "type": "select",
                        "required": False,
                        "options": [["", "清除映射"]]
                        + self._voice_options(include_disabled=False),
                    },
                ],
            },
        ]

    def _config_actions(self) -> list[dict[str, Any]]:
        tts_provider_options = [
            ["__keep__", "保持不变"],
            ["", "使用默认或核模型路由"],
        ]
        try:
            tts_provider_options.extend(
                [
                    [str(item.get("id") or ""), str(item.get("id") or "")]
                    for item in self.plugin.list_astrbot_tts_providers()
                    if isinstance(item, dict) and item.get("id")
                ]
            )
        except Exception:
            pass

        director_provider_options = [
            ["__keep__", "保持不变"],
            ["", "使用默认或核模型路由"],
        ]
        try:
            director_provider_options.extend(
                [
                    [str(item.get("id") or ""), str(item.get("label") or item.get("id") or "")]
                    for item in self.plugin._list_ai_providers()
                    if isinstance(item, dict) and item.get("id")
                ]
            )
        except Exception:
            pass

        return [
            {
                "id": SAVE_CONFIG_ACTION_ID,
                "label": "保存常用语音配置",
                "effect": "idempotent",
                "idempotency_required": False,
                "revision_required": False,
                "min_role": "admin",
                "timeout_seconds": 10,
                "confirm": "确认保存语音与 AI 导演配置？留空字段保持不变。",
                "payload_fields": [
                    {
                        "name": "tts_backend",
                        "label": "TTS 后端",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["mimo", "MiMo 音色克隆"], ["astrbot", "AstrBot TTS"]],
                    },
                    {
                        "name": "astrbot_tts_provider_id",
                        "label": "AstrBot TTS 提供商",
                        "type": "select",
                        "required": False,
                        "options": tts_provider_options,
                    },
                    {
                        "name": "api_key",
                        "label": "MiMo API Key（留空保持不变）",
                        "type": "text",
                        "required": False,
                        "secret": True,
                        "max_length": MAX_API_KEY_CHARS,
                    },
                    {
                        "name": "base_url",
                        "label": "MiMo Base URL",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_BASE_URL_CHARS,
                    },
                    {
                        "name": "model",
                        "label": "MiMo 模型",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_MODEL_CHARS,
                    },
                    {
                        "name": "output_format",
                        "label": "输出格式",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["wav", "WAV"]],
                    },
                    {
                        "name": "auto_tts_enabled",
                        "label": "自动语音",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                    {
                        "name": "tts_trigger_mode",
                        "label": "触发方式",
                        "type": "select",
                        "required": False,
                        "options": [
                            ["", "保持不变"],
                            ["probability", "概率过滤"],
                            ["llm_decides", "由 LLM 决定"],
                        ],
                    },
                    {
                        "name": "reply_mode",
                        "label": "回复模式",
                        "type": "select",
                        "required": False,
                        "options": [
                            ["", "保持不变"],
                            ["audio_only", "仅音频"],
                            ["text_and_audio", "文本与音频"],
                            ["text_only", "仅文本"],
                        ],
                    },
                    {
                        "name": "max_text_chars",
                        "label": "单条文本上限",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "max_concurrency",
                        "label": "最大并发合成数",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "emotion_routing_enabled",
                        "label": "情绪路由",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                    {
                        "name": "default_context",
                        "label": "默认 TTS 上下文",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_DEFAULT_CONTEXT_CHARS,
                    },
                    {
                        "name": "segment_enabled",
                        "label": "分段输出",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                    {
                        "name": "segment_threshold_chars",
                        "label": "分段阈值字数",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "segment_max_segments",
                        "label": "最大分段数",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "segment_delay_ms",
                        "label": "基础分段延迟（毫秒）",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "segment_delay_per_audio_second_ms",
                        "label": "每秒音频延迟（毫秒）",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "ai_style_director_enabled",
                        "label": "AI 语音导演",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                    {
                        "name": "ai_style_director_provider_id",
                        "label": "AI 导演模型",
                        "type": "select",
                        "required": False,
                        "options": director_provider_options,
                    },
                    {
                        "name": "ai_style_director_mode",
                        "label": "AI 导演模式",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["direct", "仅导演指令"], ["hybrid", "混合风格"]],
                    },
                    {
                        "name": "ai_style_director_max_chars",
                        "label": "AI 导演最大字数",
                        "type": "number",
                        "required": False,
                    },
                    {
                        "name": "ai_style_director_optimize_text",
                        "label": "AI 优化朗读文本",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                    {
                        "name": "ai_style_director_fallback_to_emotion",
                        "label": "导演失败回退情绪路由",
                        "type": "select",
                        "required": False,
                        "options": [["", "保持不变"], ["true", "启用"], ["false", "关闭"]],
                    },
                ],
            },
            {
                "id": TEST_CONNECTION_ACTION_ID,
                "label": "测试 TTS 连接",
                "effect": "idempotent",
                "idempotency_required": False,
                "revision_required": False,
                "min_role": "admin",
                "timeout_seconds": 30,
                "confirm": "确认执行一次真实的 TTS 连接测试？",
                "payload_fields": [
                    {
                        "name": "text",
                        "label": "测试文本（留空使用默认）",
                        "type": "text",
                        "required": False,
                        "max_length": MAX_TEST_TEXT_CHARS,
                    },
                    {
                        "name": "voice_id",
                        "label": "测试音色（可选）",
                        "type": "select",
                        "required": False,
                        "options": [["", "自动选择"]]
                        + self._voice_options(include_disabled=False),
                    },
                ],
            },
        ]

    # ---------- 只读面板 ----------

    def panel_data(self, panel: str) -> dict[str, Any]:
        if panel == VOICES_PANEL_ID:
            return self._voices_panel()
        if panel == CONFIG_PANEL_ID:
            return self._config_panel()
        return _failure("UNKNOWN_PANEL")

    def _voices_panel(self) -> dict[str, Any]:
        try:
            voices = self.plugin.voice_store.list_voices(include_disabled=True)
            defaults = self.plugin.voice_store.defaults()
        except Exception:
            return _failure("VOICE_STORE_UNAVAILABLE", "音色存储暂不可用")
        default_ids = {
            str(value)
            for value in dict(defaults).values()
            if isinstance(value, str) and value
        }
        rows = [
            {
                "name": str(voice.name or voice.id or "未命名"),
                "id": str(voice.id or ""),
                "enabled": "是" if voice.enabled else "否",
                "default": "是" if str(voice.id or "") in default_ids else "",
            }
            for voice in voices
        ]
        try:
            readiness = {
                "api_key": bool(getattr(self.plugin.plugin_config, "api_key", "")),
                "voices": any(voice.enabled for voice in voices),
                "tts_backend": str(
                    getattr(self.plugin.plugin_config, "tts_backend", "mimo") or "mimo"
                ),
            }
        except Exception:
            readiness = {"api_key": False, "voices": False, "tts_backend": "unknown"}
        description = (
            f"{len(rows)} 个音色 · API Key={'已配置' if readiness['api_key'] else '未配置'} · "
            f"音色就绪={'是' if readiness['voices'] else '否'}"
        )
        response: dict[str, Any] = {
            "success": True,
            "title": "音色管理",
            "description": description,
            "columns": [
                {"key": "name", "label": "音色"},
                {"key": "id", "label": "ID"},
                {"key": "enabled", "label": "启用"},
                {"key": "default", "label": "默认"},
            ],
            "rows": rows,
            "actions": self._voice_actions(),
            "footer": (
                "创建与删除动作分别要求 admin/owner；参考音频经核制品传输后由插件校验，"
                "结果不会返回文件路径、API Key 或 provider 秘密。"
            ),
        }
        preview_audio = getattr(self.plugin, "_webui_voice_preview", None)
        if isinstance(preview_audio, dict) and isinstance(
            preview_audio.get("data"), (bytes, bytearray)
        ):
            response["audio"] = dict(preview_audio)
        return response

    def _public_config_snapshot(self) -> dict[str, Any]:
        config = getattr(self.plugin, "config", {}) or {}
        plugin_config = getattr(self.plugin, "plugin_config", None)
        if not isinstance(config, dict):
            config = {}
        return {
            "tts_backend": str(
                getattr(plugin_config, "tts_backend", config.get("tts_backend", "mimo"))
                or "mimo"
            ),
            "astrbot_tts_provider_id": str(
                getattr(
                    plugin_config,
                    "astrbot_tts_provider_id",
                    config.get("astrbot_tts_provider_id", ""),
                )
                or ""
            ),
            "api_key_configured": bool(getattr(plugin_config, "api_key", "")),
            "model": str(getattr(plugin_config, "model", config.get("model", "")) or ""),
            "base_url_configured": bool(
                getattr(plugin_config, "base_url", config.get("base_url", ""))
            ),
            "output_format": str(
                getattr(
                    plugin_config,
                    "output_format",
                    config.get("output_format", "wav"),
                )
                or "wav"
            ),
            "auto_tts_enabled": bool(
                getattr(plugin_config, "auto_tts_enabled", False)
            ),
            "tts_trigger_mode": str(
                getattr(
                    plugin_config,
                    "tts_trigger_mode",
                    config.get("tts_trigger_mode", "probability"),
                )
                or "probability"
            ),
            "reply_mode": str(
                getattr(plugin_config, "reply_mode", config.get("reply_mode", "audio_only"))
                or "audio_only"
            ),
            "emotion_routing_enabled": bool(
                getattr(plugin_config, "emotion_routing_enabled", True)
            ),
            "segment_enabled": bool(
                getattr(plugin_config, "segment_enabled", True)
            ),
            "ai_style_director_enabled": bool(
                getattr(plugin_config, "ai_style_director_enabled", False)
            ),
            "ai_style_director_provider_id": str(
                getattr(plugin_config, "ai_style_director_provider_id", "") or ""
            ),
        }

    def _config_panel(self) -> dict[str, Any]:
        config = self._public_config_snapshot()
        rows = [
            {"item": "TTS 后端", "value": config["tts_backend"]},
            {
                "item": "MiMo API Key",
                "value": "已配置" if config["api_key_configured"] else "未配置",
            },
            {"item": "MiMo 模型", "value": config["model"] or "未配置"},
            {
                "item": "AstrBot TTS 提供商",
                "value": config["astrbot_tts_provider_id"] or "默认或核模型路由",
            },
            {
                "item": "自动语音 / 触发",
                "value": (
                    f"{'开启' if config['auto_tts_enabled'] else '关闭'} / "
                    f"{config['tts_trigger_mode']}"
                ),
            },
            {
                "item": "分段输出",
                "value": "开启" if config["segment_enabled"] else "关闭",
            },
            {
                "item": "AI 语音导演",
                "value": (
                    f"开启（{config['ai_style_director_provider_id'] or '默认或核模型路由'}）"
                    if config["ai_style_director_enabled"]
                    else "关闭"
                ),
            },
        ]
        return {
            "success": True,
            "title": "语音与 AI 配置",
            "description": "常用配置面板；空白字段不会覆盖现有值，密钥永不回显。",
            "columns": [
                {"key": "item", "label": "项目"},
                {"key": "value", "label": "当前值"},
            ],
            "rows": rows,
            "actions": self._config_actions(),
        }

    # ---------- 动作 ----------

    async def panel_action(
        self,
        panel: str,
        action: str,
        payload: Mapping[str, Any] | None,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = dict(payload) if isinstance(payload, Mapping) else {}
        if panel == VOICES_PANEL_ID:
            if action == PREVIEW_ACTION_ID:
                return await self._preview_voice(data, context)
            if action == CREATE_ACTION_ID:
                return await self._create_voice(data, context)
            if action == UPDATE_ACTION_ID:
                return await self._update_voice(data, context)
            if action == DELETE_ACTION_ID:
                return await self._delete_voice(data, context)
            if action == SET_DEFAULT_ACTION_ID:
                return await self._set_default_voice(data, context)
            if action == SET_EMOTION_ACTION_ID:
                return await self._set_emotion_voice(data, context)
            return _failure("UNKNOWN_ACTION", "未知动作")
        if panel == CONFIG_PANEL_ID:
            if action == SAVE_CONFIG_ACTION_ID:
                return await self._save_config(data, context)
            if action == TEST_CONNECTION_ACTION_ID:
                return await self._test_connection(data, context)
            return _failure("UNKNOWN_ACTION", "未知动作")
        return _failure("UNKNOWN_PANEL", "未知面板")

    def _role_forbidden(self, action: str, context: Mapping[str, Any] | None) -> bool:
        if not isinstance(context, Mapping):
            return False
        role = str(context.get("role") or "").strip().lower()
        if not role:
            return False
        required = {
            DELETE_ACTION_ID: "owner",
        }.get(action, "admin")
        return _ROLE_LEVELS.get(role, -1) < _ROLE_LEVELS.get(required, 1)

    @staticmethod
    def _require_fields(
        payload: Mapping[str, Any],
        *,
        allowed: set[str],
        required: set[str],
    ) -> dict[str, Any] | None:
        keys = set(payload)
        if not keys <= allowed or not required <= keys:
            return _failure("INVALID_PAYLOAD", "动作参数无效")
        return None

    @staticmethod
    def _bounded_text(
        value: Any,
        *,
        maximum: int,
        allow_empty: bool = True,
    ) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not allow_empty and not normalized:
            return None
        if len(normalized) > maximum:
            return None
        if any(ord(char) < 0x20 and char not in "\n\t" for char in normalized):
            return None
        return normalized

    @staticmethod
    def _tri_state(value: Any) -> bool | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        raise ValueError("not a tri-state value")

    async def _preview_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(PREVIEW_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload,
            allowed={"text", "voice", "emotion"},
            required={"text", "voice"},
        )
        if failure is not None:
            return failure
        try:
            preview = await self.plugin._synthesize_preview_audio(
                text=payload.get("text"),
                voice_selector=payload.get("voice"),
                emotion=payload.get("emotion", ""),
            )
        except VoicePreviewError as exc:
            return _failure(exc.code, exc.message)
        except Exception:
            self._log_failure(PREVIEW_ACTION_ID)
            return _failure("PREVIEW_FAILED", "试听生成失败")
        audio = dict(preview["audio"])
        self.plugin._webui_voice_preview = audio
        voice = preview.get("voice")
        return _success(
            "试听已生成",
            audio=audio,
            voice={
                "id": str(voice.get("id") or "") if isinstance(voice, dict) else "",
                "name": str(voice.get("name") or "") if isinstance(voice, dict) else "",
            },
            emotion=str(preview.get("emotion") or "neutral"),
        )

    async def _create_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(CREATE_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        allowed = {
            "file",
            "name",
            "description",
            "style_context",
            "style_tags",
            "emotion",
            "consent_confirmed",
        }
        failure = self._require_fields(
            payload,
            allowed=allowed,
            required={"file", "name", "consent_confirmed"},
        )
        if failure is not None:
            return failure
        artifact = payload.get("file")
        if not isinstance(artifact, Mapping):
            return _failure("FILE_REQUIRED", "请选择参考音频")
        data = artifact.get("data")
        filename = str(artifact.get("filename") or "")
        if not isinstance(data, (bytes, bytearray)) or not data:
            return _failure("FILE_REQUIRED", "参考音频为空")
        if not filename:
            return _failure("INVALID_FILE", "参考音频文件名无效")
        consent = payload.get("consent_confirmed")
        if consent is not True:
            return _failure("CONSENT_REQUIRED", "必须确认已获得声音所有者授权")
        name = self._bounded_text(
            payload.get("name"), maximum=MAX_NAME_CHARS, allow_empty=False
        )
        if name is None:
            return _failure("INVALID_NAME", "音色名称无效")
        description = self._bounded_text(
            payload.get("description", ""), maximum=MAX_DESCRIPTION_CHARS
        )
        style_context = self._bounded_text(
            payload.get("style_context", ""), maximum=MAX_STYLE_CONTEXT_CHARS
        )
        style_tags = self._bounded_text(
            payload.get("style_tags", ""), maximum=MAX_STYLE_TAGS_CHARS
        )
        if description is None or style_context is None or style_tags is None:
            return _failure("INVALID_PAYLOAD", "音色元数据无效")
        raw_emotion = payload.get("emotion", "")
        if not isinstance(raw_emotion, str):
            return _failure("INVALID_EMOTION", "不支持的情绪")
        emotion = normalize_emotion(raw_emotion) or ""
        if raw_emotion.strip() and not emotion:
            return _failure("INVALID_EMOTION", "不支持的情绪")
        try:
            voice = await store_voice_sample(
                voice_store=self.plugin.voice_store,
                data_dir=self.plugin.data_dir,
                max_voice_file_bytes=self.plugin.plugin_config.max_voice_file_bytes,
                data=bytes(data),
                filename=filename,
                metadata={
                    "name": name,
                    "description": description,
                    "created_by": "series.webui",
                    "style_context": style_context,
                    "style_tags": style_tags,
                    "emotion": emotion,
                    "consent_confirmed": "true",
                },
            )
        except AudioValidationError:
            return _failure("INVALID_AUDIO", "参考音频不可用")
        except Exception:
            self._log_failure(CREATE_ACTION_ID)
            return _failure("VOICE_CREATE_FAILED", "音色创建失败")
        return _success("音色已创建", voice=_public_voice(voice))

    async def _update_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(UPDATE_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        allowed = {
            "voice_id",
            "name",
            "description",
            "enabled",
            "style_context",
            "style_tags",
            "emotion",
        }
        failure = self._require_fields(
            payload, allowed=allowed, required={"voice_id"}
        )
        if failure is not None:
            return failure
        voice_id = self._validate_voice_id(payload.get("voice_id"))
        if voice_id is None:
            return _failure("INVALID_VOICE", "音色参数无效")
        if self.plugin.voice_store.get_voice(voice_id) is None:
            return _failure("VOICE_NOT_FOUND", "音色不存在")
        changes: dict[str, Any] = {}
        string_fields = {
            "name": MAX_NAME_CHARS,
            "description": MAX_DESCRIPTION_CHARS,
            "style_context": MAX_STYLE_CONTEXT_CHARS,
            "style_tags": MAX_STYLE_TAGS_CHARS,
        }
        for name, maximum in string_fields.items():
            if name not in payload:
                continue
            value = self._bounded_text(payload.get(name), maximum=maximum)
            if value is None:
                return _failure("INVALID_PAYLOAD", "音色参数无效")
            if value != "":
                changes[name] = value
        if "enabled" in payload:
            try:
                enabled = self._tri_state(payload.get("enabled"))
            except ValueError:
                return _failure("INVALID_PAYLOAD", "启用状态无效")
            if enabled is not None:
                changes["enabled"] = enabled
        if "emotion" in payload:
            raw_emotion = payload.get("emotion")
            if raw_emotion == "__clear__":
                changes["emotion"] = ""
            elif raw_emotion not in (None, ""):
                if not isinstance(raw_emotion, str):
                    return _failure("INVALID_EMOTION", "不支持的情绪")
                emotion = normalize_emotion(raw_emotion) or ""
                if not emotion:
                    return _failure("INVALID_EMOTION", "不支持的情绪")
                changes["emotion"] = emotion
        if not changes:
            return _failure("NO_CHANGES", "没有可更新的字段")
        try:
            voice = self.plugin.voice_store.update_voice(voice_id, **changes)
        except Exception:
            self._log_failure(UPDATE_ACTION_ID)
            return _failure("VOICE_UPDATE_FAILED", "音色更新失败")
        if voice is None:
            return _failure("VOICE_NOT_FOUND", "音色不存在")
        return _success("音色已更新", voice=_public_voice(voice))

    async def _delete_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(DELETE_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload, allowed={"voice_id"}, required={"voice_id"}
        )
        if failure is not None:
            return failure
        voice_id = self._validate_voice_id(payload.get("voice_id"))
        if voice_id is None:
            return _failure("INVALID_VOICE", "音色参数无效")
        voice = self.plugin.voice_store.get_voice(voice_id)
        if voice is None:
            return _failure("VOICE_NOT_FOUND", "音色不存在")
        try:
            deleted = self.plugin.voice_store.delete_voice(voice_id)
            if deleted:
                pathlib.Path(str(getattr(voice, "audio_path", "") or "")).unlink(
                    missing_ok=True
                )
        except Exception:
            self._log_failure(DELETE_ACTION_ID)
            return _failure("VOICE_DELETE_FAILED", "音色删除失败")
        if not deleted:
            return _failure("VOICE_NOT_FOUND", "音色不存在")
        return _success(
            "音色已永久删除",
            deleted_voice_id=voice_id,
            defaults=_default_summary(self.plugin.voice_store.defaults()),
        )

    async def _set_default_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(SET_DEFAULT_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload,
            allowed={"scope", "voice_id", "user_id", "group_id"},
            required={"scope", "voice_id"},
        )
        if failure is not None:
            return failure
        scope = str(payload.get("scope") or "").strip().lower()
        if scope not in {"global", "user", "group"}:
            return _failure("INVALID_SCOPE", "默认范围无效")
        voice_id = self._validate_voice_id(payload.get("voice_id"))
        if voice_id is None:
            return _failure("INVALID_VOICE", "音色参数无效")
        if self.plugin.voice_store.get_voice(voice_id) is None:
            return _failure("VOICE_NOT_FOUND", "音色不存在")
        try:
            if scope == "user":
                scope_id = self._validate_scope_id(payload.get("user_id"))
                if scope_id is None:
                    return _failure("INVALID_SCOPE_ID", "用户 ID 无效")
                self.plugin.voice_store.set_user_default(scope_id, voice_id)
            elif scope == "group":
                scope_id = self._validate_scope_id(payload.get("group_id"))
                if scope_id is None:
                    return _failure("INVALID_SCOPE_ID", "群组 ID 无效")
                self.plugin.voice_store.set_group_default(scope_id, voice_id)
            else:
                self.plugin.voice_store.set_global_default(voice_id)
        except Exception:
            self._log_failure(SET_DEFAULT_ACTION_ID)
            return _failure("DEFAULT_UPDATE_FAILED", "默认音色保存失败")
        return _success(
            "默认音色已更新",
            defaults=_default_summary(self.plugin.voice_store.defaults()),
        )

    async def _set_emotion_voice(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(SET_EMOTION_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload,
            allowed={"emotion", "voice_id"},
            required={"emotion"},
        )
        if failure is not None:
            return failure
        raw_emotion = payload.get("emotion")
        if not isinstance(raw_emotion, str):
            return _failure("INVALID_EMOTION", "不支持的情绪")
        emotion = normalize_emotion(raw_emotion) or ""
        if emotion not in SUPPORTED_EMOTIONS:
            return _failure("INVALID_EMOTION", "不支持的情绪")
        raw_voice_id = payload.get("voice_id", "")
        if raw_voice_id in (None, ""):
            voice_id = ""
        else:
            voice_id = self._validate_voice_id(raw_voice_id)
            if voice_id is None:
                return _failure("INVALID_VOICE", "音色参数无效")
            if self.plugin.voice_store.get_voice(voice_id) is None:
                return _failure("VOICE_NOT_FOUND", "音色不存在")
        try:
            self.plugin.voice_store.set_emotion_default(emotion, voice_id)
        except Exception:
            self._log_failure(SET_EMOTION_ACTION_ID)
            return _failure("EMOTION_UPDATE_FAILED", "情绪映射保存失败")
        return _success(
            "情绪映射已更新",
            emotion=emotion,
            voice_id=voice_id,
            defaults=_default_summary(self.plugin.voice_store.defaults()),
        )

    async def _save_config(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(SAVE_CONFIG_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload, allowed=_ALLOWED_CONFIG_FIELDS, required=set()
        )
        if failure is not None:
            return failure
        changes: dict[str, Any] = {}
        try:
            self._normalize_config_changes(payload, changes)
        except ValueError as exc:
            return _failure(str(exc), "配置参数无效")
        if not changes:
            return _failure("NO_CHANGES", "没有可保存的配置")
        try:
            persisted = self.plugin._update_runtime_config(changes)
        except Exception:
            self._log_failure(SAVE_CONFIG_ACTION_ID)
            return _failure("CONFIG_SAVE_FAILED", "配置保存失败")
        if not persisted.get("local") and not persisted.get("native"):
            return _failure("CONFIG_SAVE_FAILED", "配置保存失败")
        return _success(
            "语音配置已保存",
            persisted={
                "local": bool(persisted.get("local")),
                "native": bool(persisted.get("native")),
            },
            config=self._public_config_snapshot(),
        )

    def _normalize_config_changes(
        self, payload: Mapping[str, Any], changes: dict[str, Any]
    ) -> None:
        bool_fields = {
            "auto_tts_enabled",
            "emotion_routing_enabled",
            "segment_enabled",
            "ai_style_director_enabled",
            "ai_style_director_optimize_text",
            "ai_style_director_fallback_to_emotion",
        }
        choice_fields = {
            "tts_backend": _TTS_BACKENDS,
            "output_format": _OUTPUT_FORMATS,
            "tts_trigger_mode": _TTS_TRIGGER_MODES,
            "reply_mode": _REPLY_MODES,
            "ai_style_director_mode": _DIRECTOR_MODES,
        }
        int_ranges = {
            "max_text_chars": (1, 10_000),
            "max_concurrency": (1, 32),
            "segment_threshold_chars": (1, 10_000),
            "segment_max_segments": (1, 100),
            "segment_delay_ms": (0, 5_000),
            "segment_delay_per_audio_second_ms": (0, 2_000),
            "ai_style_director_max_chars": (20, 2_000),
        }
        text_fields = {
            "base_url": MAX_BASE_URL_CHARS,
            "model": MAX_MODEL_CHARS,
            "default_context": MAX_DEFAULT_CONTEXT_CHARS,
            "api_key": MAX_API_KEY_CHARS,
        }
        provider_fields = {
            "astrbot_tts_provider_id",
            "ai_style_director_provider_id",
        }
        for name in bool_fields:
            if name not in payload:
                continue
            try:
                value = self._tri_state(payload.get(name))
            except ValueError:
                raise ValueError("INVALID_CONFIG_VALUE") from None
            if value is not None:
                changes[name] = value
        for name, allowed in choice_fields.items():
            if name not in payload:
                continue
            value = payload.get(name)
            if value in (None, ""):
                continue
            if not isinstance(value, str) or value.strip().lower() not in allowed:
                raise ValueError("INVALID_CONFIG_VALUE")
            changes[name] = value.strip().lower()
        for name, (minimum, maximum) in int_ranges.items():
            if name not in payload:
                continue
            value = payload.get(name)
            if value is None:
                continue
            if isinstance(value, bool):
                raise ValueError("INVALID_CONFIG_VALUE")
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                raise ValueError("INVALID_CONFIG_VALUE") from None
            if not minimum <= parsed <= maximum:
                raise ValueError("INVALID_CONFIG_VALUE")
            changes[name] = parsed
        for name in provider_fields:
            if name not in payload:
                continue
            value = payload.get(name)
            if value is None or value == "__keep__":
                continue
            if not isinstance(value, str) or len(value.strip()) > MAX_PROVIDER_ID_CHARS:
                raise ValueError("INVALID_CONFIG_VALUE")
            changes[name] = value.strip()
        for name, maximum in text_fields.items():
            if name not in payload:
                continue
            value = payload.get(name)
            if value in (None, ""):
                continue
            if not isinstance(value, str) or len(value.strip()) > maximum:
                raise ValueError("INVALID_CONFIG_VALUE")
            changes[name] = value.strip()

    async def _test_connection(
        self,
        payload: dict[str, Any],
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if self._role_forbidden(TEST_CONNECTION_ACTION_ID, context):
            return _failure("ROLE_FORBIDDEN", "当前角色无权执行该动作")
        failure = self._require_fields(
            payload,
            allowed={"text", "voice_id"},
            required=set(),
        )
        if failure is not None:
            return failure
        raw_text = payload.get("text") or "连接测试，声音工作正常。"
        if not isinstance(raw_text, str):
            return _failure("INVALID_TEXT", "测试文本无效")
        from .core.text_processing import clean_tts_text

        text = clean_tts_text(raw_text)
        if not text:
            return _failure("INVALID_TEXT", "测试文本不能为空")
        try:
            max_text_chars = max(
                1, int(getattr(self.plugin.plugin_config, "max_text_chars", 500) or 500)
            )
        except (TypeError, ValueError):
            max_text_chars = 500
        if len(text) > max_text_chars:
            return _failure("TEXT_TOO_LONG", f"测试文本最多 {max_text_chars} 字")
        backend = str(
            getattr(self.plugin.plugin_config, "tts_backend", "mimo") or "mimo"
        )
        voice_id: str | None = None
        raw_voice = payload.get("voice_id")
        if raw_voice not in (None, ""):
            voice_id = self._validate_voice_id(raw_voice)
            if voice_id is None or self.plugin.voice_store.get_voice(voice_id) is None:
                return _failure("VOICE_NOT_AVAILABLE", "所选音色不可用")
        if backend == "mimo":
            if not str(getattr(self.plugin.plugin_config, "api_key", "") or "").strip():
                return _failure("PROVIDER_UNAVAILABLE", "TTS 服务未配置或不可用")
            if voice_id is None:
                enabled = self.plugin.voice_store.list_voices(include_disabled=False)
                if not enabled:
                    return _failure("VOICE_NOT_AVAILABLE", "暂无可用音色")
                voice_id = str(enabled[0].id)
        started = asyncio.get_running_loop().time()
        try:
            outputs = await self.plugin.synthesize_text(
                text,
                voice_id=voice_id if backend == "mimo" else None,
                split=False,
            )
        except Exception as exc:
            return self._connection_failure(exc)
        elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
        for output in outputs or []:
            try:
                pathlib.Path(str(output)).unlink(missing_ok=True)
            except OSError:
                pass
        return _success(
            "TTS 连接测试成功",
            backend=backend,
            elapsed_ms=elapsed_ms,
            output_count=len(outputs or []),
        )

    @staticmethod
    def _connection_failure(exc: Exception) -> dict[str, Any]:
        raw = str(exc or "")
        lowered = raw.lower()
        if any(
            token in lowered
            for token in ("api key", "provider", "unauthorized", "forbidden")
        ) or "提供商" in raw:
            return _failure("PROVIDER_UNAVAILABLE", "TTS 服务未配置或不可用")
        if "文本过长" in raw:
            return _failure("TEXT_TOO_LONG", "测试文本过长")
        return _failure("CONNECTION_FAILED", "TTS 连接测试失败")

    @staticmethod
    def _validate_voice_id(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip()
        if len(normalized) > MAX_VOICE_ID_CHARS or not _VOICE_ID.fullmatch(normalized):
            return None
        return normalized

    @staticmethod
    def _validate_scope_id(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip()
        if len(normalized) > MAX_SCOPE_ID_CHARS or not _SCOPE_ID.fullmatch(normalized):
            return None
        return normalized

    def _log_failure(self, action: str) -> None:
        logger = getattr(self.plugin, "logger", None)
        warning = getattr(logger, "warning", None)
        if callable(warning):
            try:
                warning("[voice-hub] series webui action failed: %s", action)
            except Exception:
                pass
