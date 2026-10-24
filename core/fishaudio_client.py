# -*- coding: utf-8 -*-
"""FishAudio 官方 TTS API 客户端。

接口口径与 AstrBot 官方 ``fishaudio_tts_api`` Provider 及 fish-audio-python SDK 一致：

- ``POST {api_base}/tts``，请求体为 msgpack 序列化的请求对象；
- ``model`` 是 HTTP 请求头，不是请求体字段；
- ``Authorization: Bearer <api_key>`` 认证；
- 成功返回 ``audio/*`` 音频流（wav/mp3），失败返回 JSON/文本错误。

本模块只做"纯文本 -> 本地音频文件"，不发送任何消息、不管理事件，
供 voice_hub 的 fishaudio 后端直接调用。
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal

REFERENCE_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")

FishAudioFormat = Literal["wav", "pcm", "mp3"]


class FishAudioError(RuntimeError):
    """FishAudio 合成失败；message 已脱敏，可直接展示给用户。"""

    def __init__(self, message: str, *, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = int(status_code or 0)


def is_valid_reference_id(reference_id: str) -> bool:
    """FishAudio reference_id 是 32 位十六进制字符串。"""
    return bool(REFERENCE_ID_PATTERN.match(str(reference_id or "").strip()))


def sanitize_error_text(value: Any, *, limit: int = 240) -> str:
    """压成单行并截断；调用方必须避免把 api_key/正文回显进错误。"""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


class FishAudioClient:
    """一次合成一个本地音频文件的官方 API 客户端（无状态，可并发复用）。"""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str = "https://api.fish-audio.cn/v1",
        model: str = "",
        reference_id: str = "",
        character: str = "",
        output_format: str = "wav",
        timeout: float = 120.0,
        proxy: str = "",
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.api_base = self._normalize_api_base(api_base)
        # 'auto' 是上层配置语义（由调用方解析成具体模型）；客户端收到时不发送，
        # 避免把字面 'auto' 发给中转导致 model_not_found。
        model_value = str(model or "").strip()
        self.model = "" if model_value.lower() == "auto" else model_value
        self.reference_id = str(reference_id or "").strip()
        self.character = str(character or "").strip()
        self.output_format = output_format if output_format in {"wav", "pcm", "mp3"} else "wav"
        self.timeout = max(5.0, float(timeout or 120.0))
        self.proxy = str(proxy or "").strip()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/msgpack",
        }
        # FishAudio 官方接口把模型放在 HTTP header；自建 fish-speech 服务器
        # 没有 per-request model 字段，空值时不发送，避免覆盖服务器加载的模型。
        if self.model:
            headers["model"] = self.model
        return headers

    @staticmethod
    def _normalize_api_base(api_base: str) -> str:
        """补全 /v1 路径：用户常把 Base URL 填成站点根（如 https://api1.syuan.org），
        缺 /v1 时 POST /tts 会打到网页前端拿到 200 的 HTML 页面。官方/自建/中转
        统一以 /v1 收口；已带 /v1 或其他 API 前缀的原样保留。"""
        base = str(api_base or "https://api.fish-audio.cn/v1").strip().rstrip("/")
        if not base:
            base = "https://api.fish-audio.cn/v1"
        if base.lower().endswith("/v1"):
            return base
        # 已是其他显式 API 前缀（如 /v2、/openai）时不强行改写
        from urllib.parse import urlsplit
        path = urlsplit(base).path.rstrip("/")
        last_segment = path.rsplit("/", 1)[-1] if path else ""
        if last_segment and not last_segment.isdigit() and len(last_segment) <= 8:
            return base
        return f"{base}/v1"

    @staticmethod
    def _is_official_api(api_base: str) -> bool:
        lowered = str(api_base or "").lower()
        return "api.fish.audio" in lowered or "api.fish-audio.cn" in lowered

    async def _resolve_reference_id(self, headers: dict[str, str]) -> str:
        """reference_id 优先；为空且配置了角色名时按官方 /model 接口查询。"""
        if self.reference_id:
            if not is_valid_reference_id(self.reference_id):
                raise FishAudioError(
                    f"无效的 FishAudio 参考模型 ID: '{self.reference_id[:64]}'。"
                    "请确保 ID 是 32 位十六进制字符串，可从 https://fish.audio/zh-CN/discovery 获取。"
                )
            return self.reference_id
        if self._is_official_api(self.api_base) and self.character:
            return await self._lookup_reference_id_by_character(headers)
        return ""

    async def _lookup_reference_id_by_character(self, headers: dict[str, str]) -> str:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - AstrBot 环境已内置 httpx
            raise FishAudioError("缺少 httpx 依赖，无法查询 FishAudio 角色") from exc

        base_root = self.api_base.replace("/v1", "")
        sort_options = ["score", "task_count", "created_at"]
        async with httpx.AsyncClient(
            base_url=base_root,
            timeout=self.timeout,
            proxy=self.proxy or None,
        ) as client:
            for sort_by in sort_options:
                response = await client.get(
                    "/model",
                    params={"title": self.character, "sort_by": sort_by},
                    headers=headers,
                )
                if response.status_code != 200:
                    continue
                try:
                    data = response.json()
                except ValueError:
                    continue
                for item in (data or {}).get("items") or []:
                    title = str((item or {}).get("title") or "")
                    model_id = str((item or {}).get("_id") or "").strip()
                    if self.character in title and is_valid_reference_id(model_id):
                        return model_id
        return ""

    @staticmethod
    def _request_payload(text: str, *, reference_id: str, output_format: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "text": str(text or ""),
            "format": output_format,
            "normalize": True,
        }
        if reference_id:
            request["reference_id"] = reference_id
        return request

    def _error_context(self, *, text: str = "") -> str:
        """拼一段脱敏的请求上下文，帮助定位是哪一个后端/模型/音色失败。"""
        ref_head = self.reference_id[:8] + "…" if self.reference_id else "无"
        text_len = len(str(text or ""))
        return (
            f"base={self.api_base} model={self.model or '（未指定）'} "
            f"ref={ref_head} text_len={text_len}"
        )

    async def synthesize_to_file(
        self,
        text: str,
        *,
        output_path: str | Path,
        reference_audio: tuple[bytes, str] | None = None,
    ) -> Path:
        """合成一段文本并写入 output_path；失败抛 FishAudioError。

        ``reference_audio`` 是 (音频字节, 转写文本)，用于内联参考音频克隆
        （references 字段），与 reference_id 互斥时优先内联参考音频。
        """
        if not self.api_key:
            raise FishAudioError(
                "FishAudio API Key 未配置（FishAudio 设置 → 访问密钥）"
            )
        spoken = str(text or "").strip()
        if not spoken:
            raise FishAudioError("合成文本为空")

        try:
            import ormsgpack
            import httpx
        except ImportError as exc:  # pragma: no cover - AstrBot 环境已内置
            raise FishAudioError(f"缺少 FishAudio 依赖：{type(exc).__name__}") from exc

        headers = self._headers()
        reference_id = await self._resolve_reference_id(headers)
        payload = self._request_payload(spoken, reference_id=reference_id, output_format=self.output_format)
        if reference_audio is not None:
            audio_bytes, transcript = reference_audio
            if audio_bytes:
                payload["references"] = [
                    {"audio": bytes(audio_bytes), "text": str(transcript or "").strip()}
                ]
                payload.pop("reference_id", None)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(
                base_url=self.api_base,
                timeout=self.timeout,
                proxy=self.proxy or None,
            ) as client:
                async with client.stream(
                    "POST",
                    "/tts",
                    headers=headers,
                    content=ormsgpack.packb(payload),
                ) as response:
                    content_type = str(response.headers.get("content-type") or "")
                    if response.status_code == 200 and content_type.startswith("audio/"):
                        with open(out, "wb") as handle:
                            async for chunk in response.aiter_bytes():
                                handle.write(chunk)
                        return out
                    error_bytes = await response.aread()
                    text_head = error_bytes.decode("utf-8", errors="replace")
                    # 200 + HTML 网页 = 请求根本没到 Fish Audio API：
                    # 典型是 DNS 污染/运营商劫持把域名指到别的网站，或 Cloudflare
                    # 质询页。此时不应把网页源码当"错误响应"展示。
                    lowered_head = text_head[:512].lstrip().lower()
                    if response.status_code == 200 and (
                        lowered_head.startswith("<!doctype html")
                        or lowered_head.startswith("<html")
                    ):
                        from urllib.parse import urlsplit as _urlsplit
                        request_url = str(getattr(response, "request", None) and getattr(response.request, "url", "") or "")
                        request_path = _urlsplit(request_url).path.rstrip("/") if request_url else ""
                        if request_path.endswith("/tts") and not request_path.endswith("/v1/tts"):
                            raise FishAudioError(
                                "Fish Audio API 返回的是 HTML 网页而不是音频——Base URL "
                                f"缺少 /v1 路径（当前打到 {request_path}，这是网页前端）。"
                                "请在 FishAudio 设置里把接口地址改为以 /v1 结尾后重试。",
                                status_code=int(response.status_code),
                            )
                        raise FishAudioError(
                            "Fish Audio API 返回的是 HTML 网页而不是音频——请求被"
                            "DNS 污染/运营商劫持或网关拦截，没有到达 Fish Audio 服务器。"
                            "请检查接口地址是否正确，或在 FishAudio 设置里配置可用的"
                            f"代理地址后重试。 | {self._error_context(text=spoken)}",
                            status_code=int(response.status_code),
                        )
                    detail = sanitize_error_text(text_head, limit=240)
                    raise FishAudioError(
                        f"Fish Audio API 请求失败: 状态码 {response.status_code}, "
                        f"响应内容: {detail} | {self._error_context(text=spoken)}",
                        status_code=int(response.status_code),
                    )
        except FishAudioError:
            out.unlink(missing_ok=True)
            raise
        except Exception as exc:
            out.unlink(missing_ok=True)
            raise FishAudioError(
                f"Fish Audio API 请求异常: {type(exc).__name__}: "
                f"{sanitize_error_text(exc, limit=120)} | {self._error_context(text=spoken)}"
            ) from exc

    def output_path_for(self, output_dir: str | Path) -> Path:
        return Path(output_dir) / f"fishaudio_tts_{time.time_ns()}_{uuid.uuid4().hex[:8]}.{self.output_format}"


async def _read_reference_audio(path: str | Path) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)
