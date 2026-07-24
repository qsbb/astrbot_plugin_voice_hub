from __future__ import annotations

import asyncio
import functools
import json
import pathlib
import random
import re
import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File
from astrbot.api.star import Context, Star, StarTools, register

try:
    from astrbot.api.message_components import Plain, Record
except Exception:  # pragma: no cover - AstrBot versions differ here.
    Plain = None
    Record = None

try:  # TextPart 用于不破坏 prompt 缓存的动态上下文注入
    from astrbot.core.agent.message import TextPart
except Exception:  # pragma: no cover
    TextPart = None

from .core.audio_codec import encode_voice_file_data_url, estimate_base64_chars
from .core.api_server import MimoTTSApiServer
from .core.config import build_plugin_config, normalize_config
from .core.emotion import EmotionRouter, normalize_emotion
from .core.mimo_official_client import MimoOfficialClient, MimoTTSConfig
from .core.style_director import StyleDirectorInput, generate_style_plan
from .core.synthesis_context import (
    TTSContextResult,
    build_style_director_cache_key,
    clip_log_text,
    merge_directed_context,
)
from .core.text_processing import (
    clean_tts_text,
    contains_url,
    replace_urls_for_tts,
    split_tts_text,
)
from .core.voice_store import VoiceProfile, VoiceStore
from .pages_api import PagesAPIMixin

__version__ = "0.7.1"


@register(
    "astrbot_plugin_voice_hub",
    "Justice-ocr",
    "凝心溯溪-声，双 TTS 后端、多音色管理、AI 语音导演与外部 API",
    __version__,
)
class MimoTTSClonePlugin(PagesAPIMixin, Star):
    TTS_HANDLED_EVENT_KEY = "mimo_tts_handled"
    _current_instance: Any = None
    _api_server: Any = None
    # LLM 朗读意愿判断标记：<TTS:yes> 或 <TTS:no:原因>，仅匹配回复开头
    _TTS_JUDGE_MARKER_RE = re.compile(
        r"^\s*<TTS:(yes|no)(?::[^>]*?)?>\s*", re.IGNORECASE
    )
    _TTS_JUDGE_PROMPT = (
        "【语音朗读意愿判断】\n"
        "请在回复最开头输出一个朗读意愿标记，紧跟实际回复内容。"
        "标记会被系统自动剥离，对用户不可见，不要解释标记的存在。\n"
        "- 适合朗读：<TTS:yes>\n"
        "- 不适合朗读：<TTS:no:简短原因>\n\n"
        "适合朗读：简短自然的口语对话、问候、关心、情绪表达、有温度的回应。\n"
        "不适合朗读：回复过长（超过约80字）、含代码块/表格/列表等结构化内容、"
        "纯链接或命令说明、内容羞耻尴尬不适合开口朗读、纯功能性的确认或否认。\n"
        "不确定时默认输出 <TTS:no:不确定>。标记之后直接跟回复正文。"
    )

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.context = context
        self.logger = logger
        self._native_config = config if hasattr(config, "save_config") else None
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_voice_hub")
        pathlib.Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        # 从旧插件名迁移数据（如果存在）
        old_data_dir = (
            pathlib.Path(self.data_dir).parent / "astrbot_plugin_mimo_tts_clone"
        )
        if (
            old_data_dir.is_dir()
            and not (pathlib.Path(self.data_dir) / "config.json").exists()
        ):
            import shutil

            try:
                for item in old_data_dir.iterdir():
                    dest = pathlib.Path(self.data_dir) / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                logger.info("[voice-hub] migrated data from %s", old_data_dir)
            except Exception as exc:
                logger.warning(
                    "[voice-hub] failed to migrate data from %s: %s", old_data_dir, exc
                )
        self._config_file = pathlib.Path(self.data_dir) / "config.json"
        native_config = self._coerce_config(config)
        persisted_config = self._load_persisted_config()
        self.config = normalize_config({**native_config, **persisted_config})
        self.plugin_config = build_plugin_config(self.config)
        self.emotion_router = EmotionRouter(
            emotion_contexts=self.plugin_config.emotion_contexts
        )
        self.voice_store = VoiceStore(self.data_dir)
        self._tts_sem = asyncio.Semaphore(self.plugin_config.max_concurrency)
        self._style_director_cache: dict[Any, TTSContextResult] = {}
        MimoTTSClonePlugin._current_instance = self
        self._unwrap_stale_partials()
        self._register_pages_web_api()
        self._ensure_api_server()

    @staticmethod
    def _coerce_config(config: Any) -> dict[str, Any]:
        if isinstance(config, dict):
            return dict(config)
        items = getattr(config, "items", None)
        if callable(items):
            try:
                return dict(items())
            except Exception:
                return {}
        getter = getattr(config, "get", None)
        if callable(getter):
            values = {}
            for key in normalize_config({}):
                try:
                    value = getter(key)
                except Exception:
                    continue
                if value is not None:
                    values[key] = value
            return values
        return {}

    def _load_persisted_config(self) -> dict[str, Any]:
        try:
            if not self._config_file.is_file():
                return {}
            data = json.loads(self._config_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self.logger.warning("[voice-hub] failed to read persisted config: %s", exc)
            return {}

    def _persist_local_config(self) -> None:
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._config_file.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._config_file)

    def _update_runtime_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self.config)
        for key in normalize_config({}):
            if key in changes:
                merged[key] = changes[key]
        self.config = normalize_config(merged)
        self.plugin_config = build_plugin_config(self.config)
        self.emotion_router = EmotionRouter(
            emotion_contexts=self.plugin_config.emotion_contexts
        )
        self._tts_sem = asyncio.Semaphore(self.plugin_config.max_concurrency)
        self._style_director_cache.clear()
        persisted = {"local": False, "native": False, "warning": ""}
        try:
            self._persist_local_config()
            persisted["local"] = True
        except Exception as exc:
            persisted["warning"] = f"failed to persist local config: {exc}"
            self.logger.warning("[voice-hub] failed to persist local config: %s", exc)
        if self._native_config is not None:
            try:
                self._native_config.update(self.config)
                self._native_config.save_config()
                persisted["native"] = True
            except Exception as exc:
                persisted["warning"] = f"failed to persist native config: {exc}"
                self.logger.warning(
                    "[voice-hub] failed to persist native config: %s", exc
                )
        self._ensure_api_server()
        return persisted

    def _client(self) -> MimoOfficialClient:
        return MimoOfficialClient(
            MimoTTSConfig(
                api_key=self.plugin_config.api_key,
                base_url=self.plugin_config.base_url,
                model=self.plugin_config.model,
                output_format=self.plugin_config.output_format,
            )
        )

    async def _synthesize_text_to_file(
        self,
        text: str,
        voice: VoiceProfile,
        *,
        context: str = "",
    ) -> pathlib.Path:
        assistant_text = text.strip()
        if voice.style_tags.strip():
            assistant_text = f"{voice.style_tags.strip()} {assistant_text}".strip()
        if len(assistant_text) > self.plugin_config.max_text_chars:
            raise RuntimeError(f"文本过长，最大 {self.plugin_config.max_text_chars} 字")

        voice_data_url = await asyncio.to_thread(
            encode_voice_file_data_url,
            pathlib.Path(voice.audio_path),
            max_bytes=self.plugin_config.max_voice_file_bytes,
            max_base64_chars=estimate_base64_chars(
                self.plugin_config.max_voice_file_bytes
            ),
        )
        output_dir = pathlib.Path(self.data_dir) / "outputs"
        output_path = output_dir / f"mimo_tts_{time.time_ns()}.wav"
        async with self._tts_sem:
            result = await self._client().synthesize_to_file(
                text=assistant_text,
                voice_data_url=voice_data_url,
                output_path=output_path,
                context=context or self.plugin_config.default_context,
            )
        await asyncio.to_thread(self._cleanup_outputs)
        return result

    def _cleanup_outputs(self) -> None:
        output_dir = pathlib.Path(self.data_dir) / "outputs"
        if not output_dir.is_dir():
            return
        files = [path for path in output_dir.glob("mimo_tts_*") if path.is_file()]
        now = time.time()
        retention_days = self.plugin_config.output_retention_days
        if retention_days > 0:
            cutoff = now - retention_days * 86400
            for path in files:
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
            files = [path for path in files if path.exists()]
        max_files = self.plugin_config.output_max_files
        if max_files > 0 and len(files) > max_files:
            files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            for path in files[max_files:]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def list_available_voices(
        self, *, include_disabled: bool = False
    ) -> list[dict[str, Any]]:
        """Public service helper for other plugins that need voice metadata."""
        return [
            voice.to_dict()
            for voice in self.voice_store.list_voices(include_disabled=include_disabled)
        ]

    def resolve_voice_id(
        self,
        voice_selector: str | None = None,
        *,
        user_id: str = "",
        group_id: str = "",
        emotion: str | None = None,
    ) -> str | None:
        """Resolve the effective voice id using the same priority as chat commands."""
        return self.voice_store.resolve_voice_id(
            voice_selector,
            user_id,
            group_id,
            emotion=emotion,
        )

    def _select_voice(
        self,
        voice_selector: str | None = None,
        *,
        user_id: str = "",
        group_id: str = "",
        emotion: str | None = None,
    ) -> VoiceProfile | None:
        voice = (
            self.voice_store.find_voice(voice_selector or "")
            if voice_selector
            else None
        )
        if voice is not None:
            return voice
        resolved_voice_id = self.resolve_voice_id(
            voice_selector,
            user_id=user_id,
            group_id=group_id,
            emotion=emotion,
        )
        return (
            self.voice_store.get_voice(resolved_voice_id or "")
            if resolved_voice_id
            else None
        )

    async def synthesize_text(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        voice_name: str | None = None,
        emotion: str | None = None,
        context: str = "",
        user_id: str = "",
        group_id: str = "",
        split: bool = True,
        style_director_enabled: bool | None = None,
    ) -> list[pathlib.Path]:
        """Public service helper for Pages and other plugins."""
        cleaned = clean_tts_text(text)
        if not cleaned:
            raise RuntimeError("请输入要合成的文本")

        # 双后端分发：astrbot 模式下走 AstrBot 内置 TTS，跳过 MiMo 链路
        if self.plugin_config.tts_backend == "astrbot":
            return await self._synthesize_with_astrbot_tts(cleaned, split=split)

        resolved_emotion = self._resolve_emotion(cleaned, emotion)
        selector = voice_id or voice_name
        voice = self._select_voice(
            selector,
            user_id=user_id,
            group_id=group_id,
            emotion=resolved_emotion,
        )
        if voice is None:
            raise RuntimeError("暂无可用音色，请先在插件 Pages 中上传参考音频。")
        tts_result = await self._build_tts_context(
            voice,
            resolved_emotion,
            context,
            text=cleaned,
            style_director_enabled=style_director_enabled,
        )
        final_text = tts_result.speech_text or cleaned
        segments = self._split_for_tts(final_text) if split else [final_text]
        return [
            await self._synthesize_text_to_file(
                segment, voice, context=tts_result.context
            )
            for segment in segments
        ]

    async def _synthesize_with_astrbot_tts(
        self,
        text: str,
        *,
        split: bool = True,
    ) -> list[pathlib.Path]:
        """通过 AstrBot 内置 TTS 提供商合成语音。"""
        try:
            from astrbot.core.provider.entities import ProviderType
        except ImportError as exc:
            raise RuntimeError("当前 AstrBot 版本不支持 TTS 提供商调用") from exc

        provider = None
        provider_id = self.plugin_config.astrbot_tts_provider_id.strip()
        if provider_id:
            provider = self.context.get_provider_by_id(provider_id)
            if provider is None:
                raise RuntimeError(f"未找到 TTS 提供商：{provider_id}")
        else:
            provider = self.context.provider_manager.get_using_provider(
                ProviderType.TEXT_TO_SPEECH
            )
            if provider is None:
                raise RuntimeError(
                    "AstrBot 未配置默认 TTS 提供商，请在插件设置中指定提供商 ID "
                    "或在 AstrBot 中启用 TTS"
                )

        segments = self._split_for_tts(text) if split else [text]
        results: list[pathlib.Path] = []
        for segment in segments:
            audio_path = await provider.get_audio(segment)
            results.append(pathlib.Path(audio_path))
        return results

    def list_astrbot_tts_providers(self) -> list[dict[str, str]]:
        """列出 AstrBot 已配置的 TTS 提供商。

        优先读取 provider 配置（providers_config），这样即使提供商实例化失败
        （如 Missing credentials）也能列出来供用户选择。再补充已实例化的列表。
        """
        result: list[dict[str, str]] = []
        seen_ids: set[str] = set()

        # 优先从配置读取（覆盖实例化失败的情况）
        try:
            providers_config = self.context.provider_manager.providers_config or []
        except Exception:
            providers_config = []
        for cfg in providers_config:
            if not isinstance(cfg, dict):
                continue
            ptype = str(cfg.get("type", "") or "")
            # 只保留 TTS 类型：openai_tts / edge_tts / fish_speech 等
            if not ptype.endswith("_tts") and ptype not in {
                "edge_tts",
                "fish_speech_tts",
            }:
                continue
            pid = str(cfg.get("id", "") or "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            model_config = cfg.get("model_config", {}) if isinstance(cfg, dict) else {}
            model_value = ""
            if isinstance(model_config, dict):
                model_value = str(model_config.get("model", "") or "")
            result.append(
                {
                    "id": pid,
                    "type": ptype,
                    "model": model_value,
                }
            )

        # 补充已实例化但配置读取不到的提供商
        try:
            insts = self.context.provider_manager.tts_provider_insts
        except Exception:
            insts = []
        for prov in insts:
            cfg = getattr(prov, "provider_config", {}) or {}
            pid = str(cfg.get("id", "") or "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            model_config = cfg.get("model_config", {}) if isinstance(cfg, dict) else {}
            model_value = str(getattr(prov, "model_name", "") or "")
            if not model_value and isinstance(model_config, dict):
                model_value = str(model_config.get("model", "") or "")
            result.append(
                {
                    "id": pid,
                    "type": str(cfg.get("type", "") or ""),
                    "model": model_value,
                }
            )
        return result

    def migrate_from_old_plugin(self) -> dict:
        """从旧插件 astrbot_plugin_mimo_tts_clone 读取配置并迁移到本插件。

        读取旧插件的 config.json 和音色数据，合并到当前插件。已存在的配置不会被覆盖。
        """
        import shutil

        old_data_dir = (
            pathlib.Path(self.data_dir).parent / "astrbot_plugin_mimo_tts_clone"
        )
        if not old_data_dir.is_dir():
            return {
                "success": False,
                "error": f"未找到旧插件数据目录：{old_data_dir}",
            }

        migrated: list[str] = []
        errors: list[str] = []

        # 迁移 config.json（合并而非覆盖）
        old_config_file = old_data_dir / "config.json"
        if old_config_file.is_file():
            try:
                old_config = json.loads(old_config_file.read_text(encoding="utf-8"))
                if isinstance(old_config, dict):
                    merged = dict(self.config)
                    # 只迁移旧配置中存在且当前不存在的键
                    for key, value in old_config.items():
                        if key not in merged or merged.get(key) in (None, "", [], {}):
                            merged[key] = value
                    self.config = normalize_config(merged)
                    self.plugin_config = build_plugin_config(self.config)
                    self.emotion_router = EmotionRouter(
                        emotion_contexts=self.plugin_config.emotion_contexts
                    )
                    self._persist_local_config()
                    migrated.append("config.json")
            except Exception as exc:
                errors.append(f"config.json: {exc}")

        # 迁移音色目录（voices）
        old_voices_dir = old_data_dir / "voices"
        new_voices_dir = pathlib.Path(self.data_dir) / "voices"
        if old_voices_dir.is_dir():
            try:
                new_voices_dir.mkdir(parents=True, exist_ok=True)
                for item in old_voices_dir.iterdir():
                    dest = new_voices_dir / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                migrated.append("voices/")
            except Exception as exc:
                errors.append(f"voices/: {exc}")

        # 迁移音色库索引文件
        old_index = old_data_dir / "voices.json"
        if old_index.is_file():
            try:
                dest = pathlib.Path(self.data_dir) / "voices.json"
                if not dest.exists():
                    shutil.copy2(old_index, dest)
                migrated.append("voices.json")
            except Exception as exc:
                errors.append(f"voices.json: {exc}")

        # 刷新内存中的音色库
        self.voice_store = VoiceStore(self.data_dir)

        if not migrated:
            return {
                "success": False,
                "error": "旧插件目录中没有可迁移的数据",
            }

        return {
            "success": True,
            "migrated": migrated,
            "errors": errors,
            "message": f"已迁移 {', '.join(migrated)}",
        }

    async def text_to_speech(
        self,
        text: str,
        *,
        emotion: str = "",
        target_umo: str = "",
        session: str = "",
        session_id: str = "",
        voice: str = "",
        voice_name: str = "",
        context: str = "",
        session_state: Any = None,
    ) -> str:
        """Compatibility helper for generic TTS callers such as daily_sharing."""
        del session_state
        group_id = str(target_umo or session or session_id or "").strip()
        outputs = await self.synthesize_text(
            text,
            voice_name=voice_name or voice or None,
            emotion=emotion or None,
            context=context,
            group_id=group_id,
        )
        return str(outputs[0]) if outputs else ""

    @staticmethod
    def _llm_tool_name(tool: Any) -> str:
        if isinstance(tool, dict):
            function = tool.get("function")
            if isinstance(function, dict):
                return str(function.get("name") or "").strip()
            return str(tool.get("name") or "").strip()
        function = getattr(tool, "function", None)
        if isinstance(function, dict):
            return str(function.get("name") or "").strip()
        return str(
            getattr(function, "name", None) or getattr(tool, "name", None) or ""
        ).strip()

    def _filter_tts_llm_tool(self, request: Any) -> int:
        tools = getattr(request, "tools", None)
        if not tools:
            return 0
        original = list(tools)
        request.tools = [
            tool for tool in original if self._llm_tool_name(tool) != "mimo_tts_speak"
        ]
        return len(original) - len(request.tools)

    if hasattr(filter, "on_llm_request"):

        @filter.on_llm_request()
        async def filter_tts_tool_for_probability_mode(self, *args):
            # AstrBot 热重载时 functools.partial 可能套娃，导致额外实例参数被前置。
            # 真实参数 (event, request) 始终在 args 末尾，从末尾提取即可。
            plugin = MimoTTSClonePlugin._current_instance or self
            if not isinstance(plugin, MimoTTSClonePlugin):
                return
            # fallback：确保 __init__ 时未能启动的 API server 在事件循环中补启动
            plugin._ensure_api_server()
            if len(args) < 2:
                return
            request = args[-1]
            if plugin.plugin_config.tts_trigger_mode != "probability":
                return
            removed = plugin._filter_tts_llm_tool(request)
            if removed:
                plugin.logger.info(
                    "[voice-hub] probability mode filtered %s TTS LLM tool(s)", removed
                )
            # probability 模式下可选：引导主 LLM 在回复开头输出朗读意愿标记
            if plugin.plugin_config.llm_tts_judge_enabled:
                plugin._inject_tts_judge_prompt(request)

    if hasattr(filter, "llm_tool"):

        @filter.llm_tool(name="mimo_tts_speak")
        async def mimo_tts_speak(
            self,
            event: AstrMessageEvent,
            text: str,
            emotion: str = "neutral",
            voice: str = "",
            style: str = "",
        ):
            """Generate AND automatically send MiMo TTS audio to the user.

            This tool handles the full delivery: it synthesizes speech and directly sends the
            audio message to the user. After calling it, DO NOT call send_message_to_user (or
            any other send tool) to resend the same audio — that would produce a duplicate.
            The audio is already in the user's chat when this tool returns.

            Call this tool when the user explicitly requests speech or audio, or when voice
            delivery clearly improves the response. Do not call it for an ordinary text reply.
            For long text, decide whether voice delivery is suitable before calling; the plugin
            handles any required segmentation. Generate `style` directly from the requested
            delivery and text instead of asking the user to provide a style. URLs in the text
            are replaced with a spoken placeholder (e.g. "这个网址") before synthesis when
            replace_url_in_tts is on, so the audio says "this URL" instead of reading out
            the raw address; the original URL is still sent to the user via the text reply.

            Args:
                text(string): Complete text to convert to speech.
                emotion(string): Optional emotion, one of happy, sad, angry, neutral.
                voice(string): Optional voice name or voice id.
                style(string): Temporary delivery instruction authored directly by the LLM.

            Returns:
                string: A short status line confirming the audio has been sent, e.g.
                "audio already sent to user (1 segment)". The audio file path is internal
                and must NOT be re-sent via other tools.
            """
            # AstrBot 热重载后 self 可能是旧实例或 None，重定向到当前实例
            plugin = MimoTTSClonePlugin._current_instance or self
            if not isinstance(plugin, MimoTTSClonePlugin):
                yield "tts plugin is initializing, please try again"
                return
            content = str(text or "").strip()
            if not content:
                yield "empty text"
                return
            if plugin.plugin_config.replace_url_in_tts and contains_url(content):
                content = replace_urls_for_tts(content)
            try:
                outputs = await plugin.synthesize_text(
                    content,
                    voice_name=str(voice or "").strip() or None,
                    emotion=emotion,
                    context=style,
                    user_id=str(
                        getattr(event, "get_sender_id", lambda: "")() or ""
                    ).strip(),
                    group_id=str(getattr(event, "unified_msg_origin", "") or "").strip()
                    or plugin._conversation_id(event),
                    style_director_enabled=False,
                )
            except Exception as exc:
                yield f"tts failed: {exc}"
                return
            sent = 0
            for output in outputs:
                await plugin._send_audio_result(event, output)
                sent += 1
                if sent == 1:
                    plugin._mark_tts_handled(event)
            if hasattr(event, "clear_result"):
                event.clear_result()
            if sent == 0:
                yield "no audio generated"
            else:
                yield (
                    f"audio already sent to user ({sent} segment"
                    + ("s" if sent != 1 else "")
                    + "); do not resend it via other tools"
                )
            return

    @classmethod
    def _mark_tts_handled(cls, event: AstrMessageEvent) -> None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            setter(cls.TTS_HANDLED_EVENT_KEY, True)
            return
        setattr(event, cls.TTS_HANDLED_EVENT_KEY, True)

    @classmethod
    def _is_tts_handled(cls, event: AstrMessageEvent) -> bool:
        getter = getattr(event, "get_extra", None)
        if callable(getter):
            try:
                if getter(cls.TTS_HANDLED_EVENT_KEY):
                    return True
            except Exception:
                pass
        return bool(getattr(event, cls.TTS_HANDLED_EVENT_KEY, False))

    @staticmethod
    def _conversation_id(event: AstrMessageEvent) -> str:
        try:
            provider_request = event.get_extra("provider_request")
            conversation = getattr(provider_request, "conversation", None)
            return str(getattr(conversation, "cid", "") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _chat_scope(event: AstrMessageEvent) -> tuple[str, str]:
        conversation_id = MimoTTSClonePlugin._conversation_id(event)
        origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if "FriendMessage" in origin or "FriendMessage" in conversation_id:
            return "private", origin or conversation_id
        if "GroupMessage" in origin or "GroupMessage" in conversation_id:
            return "group", origin or conversation_id
        return "unknown", origin or conversation_id

    @staticmethod
    def _matches_scope(target: str, candidate: str) -> bool:
        target = str(target or "").strip()
        candidate = str(candidate or "").strip()
        if not target or not candidate:
            return False
        return target == candidate or target in candidate or candidate in target

    def _auto_tts_access_preview(self) -> dict[str, Any]:
        group_whitelist = list(self.plugin_config.auto_tts_group_whitelist)
        group_blacklist = list(self.plugin_config.auto_tts_group_blacklist)
        private_whitelist = list(self.plugin_config.auto_tts_private_whitelist)
        private_blacklist = list(self.plugin_config.auto_tts_private_blacklist)
        admins = list(self.plugin_config.admin_users)

        def describe_scope(
            whitelist: list[str], blacklist: list[str], scope_name: str
        ) -> str:
            if whitelist and blacklist:
                return (
                    f"白名单 {len(whitelist)} 条，黑名单 {len(blacklist)} 条，"
                    "黑名单优先拦截，未命中黑名单后需命中白名单才放行"
                )
            if whitelist:
                return f"白名单 {len(whitelist)} 条，未设置黑名单，仅命中后放行"
            if blacklist:
                return f"未设置白名单，黑名单 {len(blacklist)} 条，默认放行，命中即拦截"
            return f"未设置{scope_name}名单，默认放行"

        return {
            "admins": {
                "count": len(admins),
                "detail": f"{len(admins)} 个管理员，始终放行"
                if admins
                else "未配置管理员",
            },
            "group": {
                "whitelist_count": len(group_whitelist),
                "blacklist_count": len(group_blacklist),
                "detail": describe_scope(group_whitelist, group_blacklist, "群聊"),
            },
            "private": {
                "whitelist_count": len(private_whitelist),
                "blacklist_count": len(private_blacklist),
                "detail": describe_scope(private_whitelist, private_blacklist, "私聊"),
            },
            "summary": "管理员始终放行；黑名单优先于白名单；白名单留空表示不限制。",
        }

    def _auto_tts_access_decision(self, event: AstrMessageEvent) -> dict[str, Any]:
        user_id = str(event.get_sender_id() or "").strip()
        if self._is_admin(event):
            return {
                "allowed": True,
                "reason": f"admin bypass: {clip_log_text(user_id)}",
                "scope": "admin",
                "scope_id": user_id,
                "matched_rule": "admin",
            }

        scope, scope_id = self._chat_scope(event)
        if scope not in {"group", "private"}:
            return {
                "allowed": True,
                "reason": f"scope bypass: {clip_log_text(scope or 'unknown')}",
                "scope": scope,
                "scope_id": scope_id,
                "matched_rule": "scope",
            }

        whitelist = (
            self.plugin_config.auto_tts_group_whitelist
            if scope == "group"
            else self.plugin_config.auto_tts_private_whitelist
        )
        blacklist = (
            self.plugin_config.auto_tts_group_blacklist
            if scope == "group"
            else self.plugin_config.auto_tts_private_blacklist
        )

        for item in blacklist:
            if self._matches_scope(scope_id, item):
                return {
                    "allowed": False,
                    "reason": f"{scope} blacklist matched: {clip_log_text(item)}",
                    "scope": scope,
                    "scope_id": scope_id,
                    "matched_rule": item,
                }

        if whitelist:
            for item in whitelist:
                if self._matches_scope(scope_id, item):
                    return {
                        "allowed": True,
                        "reason": f"{scope} whitelist matched: {clip_log_text(item)}",
                        "scope": scope,
                        "scope_id": scope_id,
                        "matched_rule": item,
                    }
            return {
                "allowed": False,
                "reason": f"{scope} whitelist missed: {clip_log_text(scope_id)}",
                "scope": scope,
                "scope_id": scope_id,
                "matched_rule": "",
            }

        return {
            "allowed": True,
            "reason": f"{scope} unrestricted: {clip_log_text(scope_id)}",
            "scope": scope,
            "scope_id": scope_id,
            "matched_rule": "",
        }

    def _scope_allowed(self, event: AstrMessageEvent) -> bool:
        return bool(self._auto_tts_access_decision(event)["allowed"])

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        user_id = str(event.get_sender_id() or "").strip()
        return user_id in set(self.plugin_config.admin_users)

    def _resolve_emotion(self, text: str, requested: str | None) -> str:
        if not self.plugin_config.emotion_routing_enabled:
            return normalize_emotion(requested) or "neutral"
        return self.emotion_router.resolve(text, requested=requested)

    async def _build_tts_context(
        self,
        voice: VoiceProfile,
        emotion: str,
        command_context: str,
        *,
        text: str = "",
        style_director_enabled: bool | None = None,
    ) -> TTSContextResult:
        base_context = self.emotion_router.build_context(
            base_context=self.plugin_config.default_context,
            emotion=emotion,
            voice_context=voice.style_context,
            command_context=command_context,
        )
        use_style_director = (
            self.plugin_config.ai_style_director_enabled
            if style_director_enabled is None
            else bool(style_director_enabled)
        )
        if not use_style_director:
            return TTSContextResult(context=base_context, speech_text=text)

        cache_key = build_style_director_cache_key(
            voice_id=voice.id,
            emotion=emotion,
            text=text,
            optimize_text=self.plugin_config.ai_style_director_optimize_text,
        )
        cached = self._style_director_cache.get(cache_key)
        if cached:
            result = TTSContextResult(
                context=self._merge_directed_context(
                    base_context, cached.style_context
                ),
                speech_text=cached.speech_text or text,
                style_context=cached.style_context,
                cached=True,
            )
            self._log_style_director_plan(
                voice=voice,
                emotion=emotion,
                text=text,
                style_context=result.style_context,
                speech_text=result.speech_text,
                cached=True,
            )
            return result

        directive = ""
        speech_text = text
        try:
            plan = await generate_style_plan(
                self.context,
                StyleDirectorInput(
                    text=text,
                    emotion=emotion,
                    voice_name=voice.name,
                    voice_description=voice.description,
                    voice_style_context=voice.style_context,
                    existing_context=command_context or base_context,
                    max_chars=self.plugin_config.ai_style_director_max_chars,
                    optimize_speech_text=self.plugin_config.ai_style_director_optimize_text,
                    max_speech_chars=self.plugin_config.max_text_chars,
                ),
                template=self.plugin_config.ai_style_director_prompt,
                provider_id=self.plugin_config.ai_style_director_provider_id,
            )
            directive = plan.style_context
            speech_text = plan.speech_text or text
        except Exception as exc:
            error_type, error_message = self._style_director_error_summary(exc)
            fallback_enabled = self.plugin_config.ai_style_director_fallback_to_emotion
            self.logger.warning(
                "[voice-hub] style director failed: provider=%s voice=%s(%s) emotion=%s text=%s error_type=%s error=%s fallback=%s",
                self.plugin_config.ai_style_director_provider_id or "default",
                clip_log_text(voice.name),
                clip_log_text(voice.id),
                clip_log_text(emotion or "neutral"),
                clip_log_text(text),
                error_type,
                clip_log_text(error_message),
                str(bool(fallback_enabled)).lower(),
            )
            if not self.plugin_config.ai_style_director_fallback_to_emotion:
                raise RuntimeError(
                    f"AI 风格导演失败：{error_type}: {error_message}"
                ) from exc

        if directive:
            result = TTSContextResult(
                context=self._merge_directed_context(base_context, directive),
                speech_text=speech_text,
                style_context=directive,
            )
            self._style_director_cache[cache_key] = result
            self._log_style_director_plan(
                voice=voice,
                emotion=emotion,
                text=text,
                style_context=result.style_context,
                speech_text=result.speech_text,
                cached=False,
            )
            return result
        return TTSContextResult(context=base_context, speech_text=speech_text)

    def _log_style_director_plan(
        self,
        *,
        voice: VoiceProfile,
        emotion: str,
        text: str,
        style_context: str,
        speech_text: str,
        cached: bool,
    ) -> None:
        if not self.plugin_config.ai_style_director_debug_log:
            return
        self.logger.info(
            "[voice-hub] AI导演 provider=%s voice=%s(%s) emotion=%s cached=%s text=%s style_context=%s speech_text=%s",
            self.plugin_config.ai_style_director_provider_id or "default",
            clip_log_text(voice.name),
            clip_log_text(voice.id),
            clip_log_text(emotion or "neutral"),
            str(bool(cached)).lower(),
            clip_log_text(text),
            clip_log_text(style_context),
            clip_log_text(speech_text),
        )

    @staticmethod
    def _style_director_error_summary(exc: Exception) -> tuple[str, str]:
        error_type = type(exc).__name__
        message = str(exc).strip()
        if not message:
            message = "empty exception message"
        if isinstance(exc, TimeoutError):
            message = "timeout while waiting for AstrBot AI provider"
        return error_type, message

    def _merge_directed_context(self, base_context: str, directive: str) -> str:
        return merge_directed_context(
            base_context,
            directive,
            self.plugin_config.ai_style_director_mode,
        )

    def _split_for_tts(self, text: str) -> list[str]:
        if not self.plugin_config.segment_enabled:
            return [text]
        if len(text) < self.plugin_config.segment_threshold_chars:
            return [text]
        return split_tts_text(
            text,
            max_chars=self.plugin_config.segment_threshold_chars,
            max_segments=self.plugin_config.segment_max_segments,
        )

    def _audio_component(self, audio_path: pathlib.Path):
        if Record is not None:
            return Record(file=str(audio_path))
        if self.plugin_config.file_fallback_enabled:
            return File(name=audio_path.name, file=str(audio_path))
        return None

    @staticmethod
    def _is_plain_component(component: Any) -> bool:
        if Plain is not None and isinstance(component, Plain):
            return True
        return component.__class__.__name__ == "Plain"

    def _inject_tts_judge_prompt(self, request: Any) -> None:
        """向 LLM 请求注入朗读意愿判断指令。

        优先追加到 extra_user_content_parts（不破坏 prompt 缓存），
        回退到 system_prompt 拼接。
        """
        prompt = self._TTS_JUDGE_PROMPT
        injected = False
        extra = getattr(request, "extra_user_content_parts", None)
        if extra is not None and TextPart is not None:
            try:
                extra.append(TextPart(text=prompt))
                injected = True
            except Exception as exc:
                self.logger.debug("[voice-hub] TextPart inject failed: %s", exc)
        if not injected:
            current = getattr(request, "system_prompt", "") or ""
            try:
                request.system_prompt = (
                    (current + "\n\n" + prompt) if current else prompt
                )
            except Exception as exc:
                self.logger.debug("[voice-hub] system_prompt inject failed: %s", exc)

    def _strip_tts_judge_marker(self, result: Any) -> str | None:
        """从结果链开头剥离 <TTS:yes/no> 标记。

        返回 'yes'/'no' 表示命中并已剥离；None 表示首个 Plain 组件无标记
        （LLM 未遵循指令，调用方应退回概率逻辑）。
        """
        chain = getattr(result, "chain", None)
        if not chain:
            return None
        for idx, comp in enumerate(chain):
            if not self._is_plain_component(comp):
                continue
            text = getattr(comp, "text", "") or ""
            match = self._TTS_JUDGE_MARKER_RE.match(text)
            if not match:
                return None
            decision = match.group(1).lower()
            new_text = text[match.end() :]
            # 优先原地更新 text 属性（兼容真实 Plain 与动态类实例）
            try:
                comp.text = new_text
            except Exception:
                # 原地更新失败（如 slots 限制）则重建 Plain 组件
                rebuilt = False
                if Plain is not None:
                    try:
                        chain[idx] = Plain(text=new_text)
                        rebuilt = True
                    except Exception:
                        pass
                if not rebuilt:
                    self.logger.debug("[voice-hub] failed to strip TTS judge marker")
            return decision
        return None

    async def _send_audio_result(
        self, event: AstrMessageEvent, audio_path: pathlib.Path
    ) -> None:
        if Record is not None:
            try:
                await event.send(event.chain_result([Record(file=str(audio_path))]))
                return
            except Exception as exc:
                self.logger.warning(
                    "[voice-hub] Record send failed, fallback to file: %s", exc
                )
        if self.plugin_config.file_fallback_enabled:
            await event.send(
                event.chain_result([File(name=audio_path.name, file=str(audio_path))])
            )

    @filter.on_decorating_result()
    async def auto_tts_reply(self, *args):
        # AstrBot 热重载时 functools.partial 可能套娃，额外实例参数被前置。
        # 真实 event 始终是 args 末尾参数。
        plugin = MimoTTSClonePlugin._current_instance or self
        if not isinstance(plugin, MimoTTSClonePlugin):
            return
        if not args:
            return
        event = args[-1]
        if plugin._is_tts_handled(event):
            plugin.logger.info("[voice-hub] auto tts skipped: event already handled")
            return
        if plugin.plugin_config.tts_trigger_mode != "probability":
            plugin.logger.info("[voice-hub] auto tts skipped: trigger mode llm_decides")
            return
        if plugin.plugin_config.reply_mode == "text_only":
            plugin.logger.info("[voice-hub] auto tts skipped: reply mode text_only")
            return
        access_decision = plugin._auto_tts_access_decision(event)
        if not access_decision["allowed"]:
            plugin.logger.info(
                "[voice-hub] auto tts skipped: %s", access_decision["reason"]
            )
            return
        plugin.logger.info(
            "[voice-hub] auto tts allowed: %s", access_decision["reason"]
        )
        result = event.get_result()
        if result is None or not getattr(result, "chain", None):
            plugin.logger.info("[voice-hub] auto tts skipped: no result chain")
            return
        is_llm_result = getattr(result, "is_llm_result", None)
        if callable(is_llm_result) and not is_llm_result():
            plugin.logger.info("[voice-hub] auto tts skipped: non-LLM result")
            return
        # LLM 情绪化朗读判断：解析回复开头标记，yes 必读、no 跳过、无标记退回概率
        judge_decision: str | None = None
        if plugin.plugin_config.llm_tts_judge_enabled:
            judge_decision = plugin._strip_tts_judge_marker(result)
            if judge_decision == "no":
                plugin.logger.info("[voice-hub] auto tts skipped: llm judge no")
                return
            if judge_decision == "yes":
                plugin.logger.info("[voice-hub] auto tts forced: llm judge yes")
        if judge_decision != "yes":
            roll = random.random()
            if roll > plugin.plugin_config.auto_tts_probability:
                plugin.logger.info(
                    "[voice-hub] auto tts skipped: probability gate roll=%.3f threshold=%.3f scope=%s matched=%s",
                    roll,
                    plugin.plugin_config.auto_tts_probability,
                    access_decision["scope"],
                    clip_log_text(access_decision["matched_rule"] or "none"),
                )
                return
        raw_plain_text = result.get_plain_text()
        if plugin.plugin_config.replace_url_in_tts and contains_url(raw_plain_text):
            raw_plain_text = replace_urls_for_tts(raw_plain_text)
        text = clean_tts_text(raw_plain_text)
        if not text:
            plugin.logger.info("[voice-hub] auto tts skipped: empty plain text")
            return
        try:
            outputs = await plugin.synthesize_text(
                text,
                user_id=str(event.get_sender_id() or "").strip(),
                group_id=plugin._conversation_id(event),
            )
        except Exception as exc:
            plugin.logger.warning("[voice-hub] auto tts failed: %s", exc)
            return

        plugin.logger.info(
            "[voice-hub] auto tts generated: scope=%s matched=%s text=%s outputs=%s",
            access_decision["scope"],
            clip_log_text(access_decision["matched_rule"] or "none"),
            clip_log_text(text),
            len(outputs),
        )

        audio_components = [
            component
            for component in (plugin._audio_component(output) for output in outputs)
            if component is not None
        ]
        if not audio_components:
            return
        if plugin.plugin_config.reply_mode == "audio_only":
            result.chain = [
                comp for comp in result.chain if not plugin._is_plain_component(comp)
            ]
        result.chain.extend(audio_components)

    async def terminate(self):
        await self._stop_api_server()
        self._cleanup_plugin_handlers()

    def _ensure_api_server(self) -> None:
        """根据配置启动或停止外部 API 服务。

        如果调用时事件循环尚未运行（如 __init__ 阶段），仍然创建 task；
        task 会在循环开始运行后自动执行。异步钩子里也会再次调用本方法作为 fallback。
        """
        if not self.plugin_config.api_server_enabled:
            return

        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            self.logger.warning("[voice-hub] api server: no event loop available")
            return

        # 已在运行且端口/host 未变则不重启
        server = MimoTTSClonePlugin._api_server
        if (
            server is not None
            and server.running
            and server.host == self.plugin_config.api_server_host
            and server.port == self.plugin_config.api_server_port
        ):
            server.plugin = self
            return

        # 配置变化，先停旧的
        if server is not None and server.running:
            asyncio.ensure_future(server.stop(), loop=loop)

        new_server = MimoTTSApiServer(
            self,
            host=self.plugin_config.api_server_host,
            port=self.plugin_config.api_server_port,
            logger=self.logger,
        )
        MimoTTSClonePlugin._api_server = new_server
        asyncio.ensure_future(new_server.start(), loop=loop)
        if not loop.is_running():
            self.logger.info(
                "[voice-hub] api server pending: will start when event loop runs"
            )

    async def _stop_api_server(self) -> None:
        server = MimoTTSClonePlugin._api_server
        MimoTTSClonePlugin._api_server = None
        if server is not None and server.running:
            try:
                await server.stop()
                self.logger.info("[voice-hub] api server stopped")
            except Exception as exc:
                self.logger.warning("[voice-hub] api server stop failed: %s", exc)

    def _unwrap_stale_partials(self) -> None:
        """在 __init__ 中调用：尝试将 registry 中本插件的 handler 重置为原始未绑定函数。

        AstrBot 加载流程：import 模块(装饰器注册) → 实例化(__init__) → 应用 partial 绑定。
        如果热重载时旧 handler 已被 partial 套娃，在 __init__ 中重置为原始函数，
        之后 AstrBot 只会应用一层 partial，避免套娃。

        所有操作 best-effort，失败时静默跳过。
        """
        try:
            self._unwrap_registry_handlers()
            self._unwrap_func_tool_handlers()
        except Exception as exc:
            self.logger.debug("[voice-hub] _unwrap_stale_partials skipped: %s", exc)

    def _unwrap_registry_handlers(self) -> None:
        registry = None
        for module_path in (
            "astrbot.core.star.star_handlers_registry",
            "astrbot.core.star",
        ):
            try:
                mod = __import__(module_path, fromlist=["star_handlers_registry"])
                registry = getattr(mod, "star_handlers_registry", None)
                if registry is not None:
                    break
            except Exception:
                continue

        if registry is None:
            return

        handlers = getattr(registry, "handlers", None)
        if not isinstance(handlers, list):
            return

        unwrapped = 0
        for handler in handlers:
            full_name = str(getattr(handler, "full_name", "") or "")
            if not any(ident in full_name for ident in self._PLUGIN_IDENTIFIERS):
                continue
            original = getattr(handler, "handler", None)
            while isinstance(original, functools.partial):
                original = original.func
            if original is not getattr(handler, "handler", None):
                try:
                    handler.handler = original
                    unwrapped += 1
                except Exception:
                    pass

        if unwrapped:
            self.logger.info(
                "[voice-hub] unwrapped %d stale partial(s) from registry handlers",
                unwrapped,
            )

    def _unwrap_func_tool_handlers(self) -> None:
        func_tool_manager = getattr(
            self.context, "_func_tool_manager", None
        ) or getattr(self.context, "func_tool_manager", None)
        if func_tool_manager is None:
            return

        tools = getattr(func_tool_manager, "tools", None)
        if not isinstance(tools, list):
            return

        unwrapped = 0
        for tool in tools:
            if getattr(tool, "name", "") != "mimo_tts_speak":
                continue
            original = getattr(tool, "handler", None)
            while isinstance(original, functools.partial):
                original = original.func
            if original is not getattr(tool, "handler", None):
                try:
                    tool.handler = original
                    unwrapped += 1
                except Exception:
                    pass

        if unwrapped:
            self.logger.info(
                "[voice-hub] unwrapped %d stale partial(s) from func_tool_manager",
                unwrapped,
            )

    _PLUGIN_IDENTIFIERS = (
        "astrbot_plugin_voice_hub",
        "MimoTTSClonePlugin",
    )

    def _cleanup_plugin_handlers(self) -> None:
        """Best-effort 清理本插件在 registry 中的旧 handler 和 LLM 工具绑定。

        AstrBot 热重载时，star_handlers_registry 可能复用旧 metadata，
        导致 functools.partial 套娃（partial(partial(func, old), new)），
        引发 ``TypeError: takes N positional arguments but N+1 were given``，
        或 LLM 工具的旧实例引用失效导致 ``self=None``。

        在 terminate() 中主动移除本插件相关条目，让框架 reload 时
        重新创建干净的 metadata，避免重复 partial 绑定。
        所有操作均包裹在 try/except 中，失败时静默跳过，不影响正常卸载。
        """
        self._cleanup_star_handlers_registry()
        self._cleanup_llm_tools()

    def _cleanup_star_handlers_registry(self) -> None:
        try:
            from astrbot.core.star.star_handlers_registry import (
                star_handlers_registry,
            )
        except Exception:
            try:
                from astrbot.core.star import star_handlers_registry  # type: ignore[import-not-found]
            except Exception:
                self.logger.debug(
                    "[voice-hub] star_handlers_registry not importable, skip cleanup"
                )
                return

        handlers = getattr(star_handlers_registry, "handlers", None)
        if not isinstance(handlers, list):
            self.logger.debug(
                "[voice-hub] star_handlers_registry.handlers is not a list, skip cleanup"
            )
            return

        def _is_our_handler(handler: Any) -> bool:
            full_name = str(getattr(handler, "full_name", "") or "")
            if not full_name:
                return False
            return any(ident in full_name for ident in self._PLUGIN_IDENTIFIERS)

        stale = [h for h in handlers if _is_our_handler(h)]
        if not stale:
            return

        try:
            star_handlers_registry.handlers = [
                h for h in handlers if not _is_our_handler(h)
            ]
            self.logger.info(
                "[voice-hub] cleanup: removed %d stale handler(s) from registry",
                len(stale),
            )
        except Exception as exc:
            self.logger.debug("[voice-hub] failed to reassign handlers list: %s", exc)

    def _cleanup_llm_tools(self) -> None:
        tool_names = {"mimo_tts_speak"}

        for method_name in (
            "remove_llm_tool",
            "remove_llm_tools",
            "unregister_llm_tool",
        ):
            method = getattr(self.context, method_name, None)
            if not callable(method):
                continue
            try:
                for name in tool_names:
                    method(name)
                self.logger.info(
                    "[voice-hub] cleanup: removed LLM tools via %s", method_name
                )
                return
            except Exception as exc:
                self.logger.debug("[voice-hub] %s failed: %s", method_name, exc)

        try:
            func_tool_manager = getattr(
                self.context, "_func_tool_manager", None
            ) or getattr(self.context, "func_tool_manager", None)
            if func_tool_manager is None:
                return
            tools = getattr(func_tool_manager, "tools", None)
            if not isinstance(tools, list):
                return
            before = len(tools)
            func_tool_manager.tools = [
                t for t in tools if getattr(t, "name", "") not in tool_names
            ]
            after = len(func_tool_manager.tools)
            if before != after:
                self.logger.info(
                    "[voice-hub] cleanup: removed %d stale LLM tool(s) from func_tool_manager",
                    before - after,
                )
        except Exception as exc:
            self.logger.debug("[voice-hub] func_tool_manager cleanup skipped: %s", exc)
