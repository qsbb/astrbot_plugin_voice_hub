from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import web


class MimoTTSApiServer:
    """OpenAI 兼容的 TTS HTTP 服务。

    暴露 POST /v1/audio/speech 接口，body 与 OpenAI TTS 对齐：
      - model: 任意值，不校验
      - input: 待合成文本
      - voice: 音色名或音色 ID，匹配不到时使用默认音色
      - response_format: 固定 wav

    Authorization 头和 model 字段均不做校验，方便外部工具直接调用。
    """

    def __init__(
        self,
        plugin: Any,
        *,
        host: str = "0.0.0.0",
        port: int = 9960,
        logger: logging.Logger | None = None,
    ) -> None:
        self.plugin = plugin
        self.host = host
        self.port = port
        self.logger = logger or logging.getLogger(__name__)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._app: web.Application | None = None
        self._task: asyncio.Task | None = None

    def _build_app(self) -> web.Application:
        app = web.Application(client_max_size=8 * 1024 * 1024)
        app.router.add_post("/v1/audio/speech", self._handle_audio_speech)
        app.router.add_get("/v1/models", self._handle_list_models)
        app.router.add_get("/", self._handle_root)
        return app

    async def start(self) -> None:
        if self._runner is not None:
            return
        self._app = self._build_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        try:
            await self._site.start()
        except OSError as exc:
            # 端口可能已被另一个 server 实例占用（__init__ task 与钩子 fallback 竞态）
            self.logger.warning(
                "[voice-hub] api server failed to bind %s:%s: %s",
                self.host,
                self.port,
                exc,
            )
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            return
        self.logger.info(
            "[voice-hub] api server listening on http://%s:%s/v1/audio/speech",
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        site = self._site
        runner = self._runner
        self._site = None
        self._runner = None
        self._app = None
        if site is not None:
            try:
                await site.stop()
            except Exception:
                pass
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception:
                pass

    @property
    def running(self) -> bool:
        return self._runner is not None and self._site is not None

    # ----- handlers -----

    async def _handle_root(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": "voice-hub",
                "endpoints": ["/v1/audio/speech", "/v1/models"],
            }
        )

    async def _handle_list_models(self, request: web.Request) -> web.Response:
        plugin = self.plugin
        if plugin is None:
            return web.json_response({"data": []})
        model = getattr(plugin.plugin_config, "model", "mimo-v2.5-tts-voiceclone")
        return web.json_response(
            {
                "object": "list",
                "data": [
                    {
                        "id": model,
                        "object": "model",
                        "owned_by": "voice-hub",
                    }
                ],
            }
        )

    async def _handle_audio_speech(self, request: web.Request) -> web.StreamResponse:
        plugin = self.plugin
        if plugin is None:
            return web.json_response(
                {"error": {"message": "plugin not ready", "type": "server_error"}},
                status=503,
            )
        try:
            body = await request.json()
        except Exception:
            try:
                body = dict(await request.post())
            except Exception:
                return _error_response("invalid request body", 400)

        if not isinstance(body, dict):
            return _error_response("request body must be a JSON object", 400)

        text = str(body.get("input") or body.get("text") or "").strip()
        if not text:
            return _error_response("field 'input' is required", 400)

        voice_selector = str(body.get("voice") or "").strip()
        emotion = str(body.get("emotion") or "").strip() or None

        try:
            outputs = await plugin.synthesize_text(
                text,
                voice_name=voice_selector or None,
                emotion=emotion,
                style_director_enabled=False,
            )
        except Exception as exc:
            self.logger.warning("[voice-hub] api server synthesis failed: %s", exc)
            return _error_response(f"synthesis failed: {exc}", 500)

        if not outputs:
            return _error_response("no audio generated", 500)

        # 多段音频时，拼接为单个 wav；大多数情况只有一段
        if len(outputs) == 1:
            data = _read_bytes(outputs[0])
        else:
            data = _concat_wav([_read_bytes(p) for p in outputs])

        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "audio/wav",
                "Content-Disposition": 'inline; filename="speech.wav"',
            },
        )
        await resp.prepare(request)
        await resp.write(data)
        await resp.write_eof()
        return resp


def _error_response(message: str, status: int) -> web.Response:
    return web.json_response(
        {"error": {"message": message, "type": "invalid_request_error"}},
        status=status,
    )


def _read_bytes(path: Any) -> bytes:
    from pathlib import Path

    path = Path(path)
    return path.read_bytes()


def _concat_wav(chunks: list[bytes]) -> bytes:
    """简易 WAV 拼接：解析首个 header，拼接 PCM 数据并重写长度。"""
    if not chunks:
        return b""
    if len(chunks) == 1:
        return chunks[0]

    import struct

    header = bytearray(chunks[0][:44])
    # 解析声道数、采样率、位深
    try:
        num_channels = struct.unpack_from("<H", header, 22)[0]
        sample_rate = struct.unpack_from("<I", header, 24)[0]
        bits_per_sample = struct.unpack_from("<H", header, 34)[0]
    except struct.error:
        # header 不标准，退回返回首段
        return chunks[0]

    pcm_parts: list[bytes] = []
    for chunk in chunks:
        if len(chunk) <= 44:
            continue
        pcm_parts.append(chunk[44:])
    pcm = b"".join(pcm_parts)

    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm)

    struct.pack_into("<I", header, 4, 36 + data_size)  # RIFF chunk size
    struct.pack_into("<I", header, 28, byte_rate)
    struct.pack_into("<H", header, 32, block_align)
    struct.pack_into("<I", header, 40, data_size)  # data chunk size

    return bytes(header) + pcm
