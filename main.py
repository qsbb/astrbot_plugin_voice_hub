from __future__ import annotations

import asyncio
import pathlib
import re
import shlex
import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api.message_components import File

try:
    from astrbot.api.message_components import Record
except Exception:  # pragma: no cover - AstrBot versions differ here.
    Record = None

from .core.audio_codec import encode_voice_file_data_url
from .core.config import build_plugin_config, normalize_config
from .core.mimo_official_client import MimoOfficialClient, MimoTTSConfig
from .core.voice_store import VoiceProfile, VoiceStore
from .pages_api import PagesAPIMixin


@register(
    "astrbot_plugin_mimo_tts_clone",
    "Justice-ocr",
    "MiMo 官方 TTS 音色克隆与多音色切换",
    "0.1.0",
)
class MimoTTSClonePlugin(PagesAPIMixin, Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.context = context
        self.logger = logger
        self._native_config = config if hasattr(config, "save_config") else None
        self.config = normalize_config(dict(config) if isinstance(config, dict) else {})
        self.plugin_config = build_plugin_config(self.config)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_mimo_tts_clone")
        pathlib.Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        self.voice_store = VoiceStore(self.data_dir)
        self._tts_sem = asyncio.Semaphore(self.plugin_config.max_concurrency)
        self._register_pages_web_api()

    def _update_runtime_config(self, changes: dict[str, Any]) -> None:
        merged = dict(self.config)
        for key in normalize_config({}):
            if key in changes:
                merged[key] = changes[key]
        self.config = normalize_config(merged)
        self.plugin_config = build_plugin_config(self.config)
        self._tts_sem = asyncio.Semaphore(self.plugin_config.max_concurrency)
        if self._native_config is not None:
            try:
                self._native_config.update(self.config)
                self._native_config.save_config()
            except Exception as exc:
                self.logger.warning("[mimo-tts] failed to persist native config: %s", exc)

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
        if len(text) > self.plugin_config.max_text_chars:
            raise RuntimeError(f"文本过长，最多 {self.plugin_config.max_text_chars} 字")
        voice_data_url = await asyncio.to_thread(
            encode_voice_file_data_url,
            pathlib.Path(voice.audio_path),
            max_bytes=self.plugin_config.max_voice_file_bytes,
        )
        output_dir = pathlib.Path(self.data_dir) / "outputs"
        output_path = output_dir / f"mimo_tts_{time.time_ns()}.wav"
        async with self._tts_sem:
            return await self._client().synthesize_to_file(
                text=text,
                voice_data_url=voice_data_url,
                output_path=output_path,
                context=context or self.plugin_config.default_context,
            )

    @staticmethod
    def _conversation_id(event: AstrMessageEvent) -> str:
        try:
            provider_request = event.get_extra("provider_request")
            conversation = getattr(provider_request, "conversation", None)
            return str(getattr(conversation, "cid", "") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _tail(message: str, command: str) -> str:
        text = str(message or "").strip()
        for prefix in ("/", "!", "！", ".", "。", "．"):
            token = f"{prefix}{command}"
            if text.startswith(token):
                return text[len(token) :].strip()
        return text

    @classmethod
    def _tail_any(cls, message: str, commands: tuple[str, ...]) -> str:
        text = str(message or "").strip()
        for command in commands:
            tail = cls._tail(text, command)
            if tail != text:
                return tail
        return text

    @staticmethod
    def _parse_tts_args(raw: str) -> tuple[str | None, str, str]:
        voice = None
        context = ""
        try:
            parts = shlex.split(raw)
        except Exception:
            parts = raw.split()
        text_parts: list[str] = []
        i = 0
        while i < len(parts):
            item = parts[i]
            if item in {"-v", "--voice"} and i + 1 < len(parts):
                voice = parts[i + 1]
                i += 2
                continue
            if item in {"-c", "--context"} and i + 1 < len(parts):
                context = parts[i + 1]
                i += 2
                continue
            text_parts.append(item)
            i += 1
        return voice, " ".join(text_parts).strip(), context

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        user_id = str(event.get_sender_id() or "").strip()
        return user_id in set(self.plugin_config.admin_users)

    async def _send_audio_result(self, event: AstrMessageEvent, audio_path: pathlib.Path) -> None:
        if Record is not None:
            try:
                await event.send(event.chain_result([Record(file=str(audio_path))]))
                return
            except Exception as exc:
                self.logger.warning("[mimo-tts] Record send failed, fallback to file: %s", exc)
        await event.send(event.chain_result([File(name=audio_path.name, file=str(audio_path))]))

    @filter.command("tts", alias={"朗读", "语音"})
    async def tts_command(self, event: AstrMessageEvent):
        raw = self._tail_any(event.message_str, ("tts", "朗读", "语音"))
        voice_name, text, context = self._parse_tts_args(raw)
        if not text:
            yield event.plain_result("用法：/tts [-v 音色名] [-c 风格指令] 文本")
            return
        user_id = str(event.get_sender_id() or "").strip()
        group_id = self._conversation_id(event)
        voice_id = self.voice_store.resolve_voice_id(voice_name, user_id, group_id)
        if not voice_id:
            yield event.plain_result("暂无可用音色，请先在插件 Pages 上传参考音频。")
            return
        voice = self.voice_store.get_voice(voice_id)
        if voice is None:
            yield event.plain_result("音色不存在或已被禁用。")
            return
        try:
            output = await self._synthesize_text_to_file(text, voice, context=context)
        except Exception as exc:
            yield event.plain_result(f"语音生成失败：{exc}")
            return
        await self._send_audio_result(event, output)

    @filter.command("tts音色列表", alias={"音色列表"})
    async def list_voices_command(self, event: AstrMessageEvent):
        voices = self.voice_store.list_voices(include_disabled=False)
        if not voices:
            yield event.plain_result("暂无可用音色，请先在插件 Pages 上传参考音频。")
            return
        defaults = self.voice_store.defaults()
        lines = ["可用音色："]
        for voice in voices:
            marker = " *" if voice.id == defaults.get("global_default_voice_id") else ""
            desc = f" - {voice.description}" if voice.description else ""
            lines.append(f"{voice.name}{marker} ({voice.id}){desc}")
        yield event.plain_result("\n".join(lines))

    @filter.command("tts设置音色", alias={"设置音色"})
    async def set_user_voice_command(self, event: AstrMessageEvent):
        selector = self._tail_any(event.message_str, ("tts设置音色", "设置音色"))
        voice = self.voice_store.find_voice(selector)
        if voice is None:
            yield event.plain_result("找不到该音色，可发送 /tts音色列表 查看。")
            return
        self.voice_store.set_user_default(str(event.get_sender_id() or ""), voice.id)
        yield event.plain_result(f"已将你的默认音色设为：{voice.name}")

    @filter.command("tts默认音色", alias={"默认音色"})
    async def set_global_voice_command(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("只有插件管理员可以设置全局默认音色。")
            return
        selector = self._tail_any(event.message_str, ("tts默认音色", "默认音色"))
        voice = self.voice_store.find_voice(selector)
        if voice is None:
            yield event.plain_result("找不到该音色，可发送 /tts音色列表 查看。")
            return
        self.voice_store.set_global_default(voice.id)
        yield event.plain_result(f"已将全局默认音色设为：{voice.name}")

    @filter.command("tts群默认音色", alias={"群默认音色"})
    async def set_group_voice_command(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("只有插件管理员可以设置群默认音色。")
            return
        group_id = self._conversation_id(event)
        if not group_id:
            yield event.plain_result("当前会话无法识别群/会话 ID。")
            return
        selector = self._tail_any(event.message_str, ("tts群默认音色", "群默认音色"))
        voice = self.voice_store.find_voice(selector)
        if voice is None:
            yield event.plain_result("找不到该音色，可发送 /tts音色列表 查看。")
            return
        self.voice_store.set_group_default(group_id, voice.id)
        yield event.plain_result(f"已将本会话默认音色设为：{voice.name}")

    async def terminate(self):
        pass
