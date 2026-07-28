from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import hmac
import logging
import time
from typing import Any

from aiohttp import web

from .audio_codec import AudioMergeError, merge_wav_bytes


class MimoTTSApiServer:
    """OpenAI 兼容的 TTS HTTP 服务。

    暴露 POST /v1/audio/speech 接口，body 与 OpenAI TTS 对齐：
      - model: 必须与插件当前 TTS 模型一致
      - input: 待合成文本
      - voice: 音色名或音色 ID，匹配不到时使用默认音色
      - response_format: 固定 wav

    除公开的根路径外，请求必须携带 Bearer token。
    """

    def __init__(
        self,
        plugin: Any,
        *,
        host: str = "127.0.0.1",
        port: int = 9960,
        api_token: str = "",
        rate_limit_per_minute: int = 30,
        max_input_chars: int = 500,
        logger: logging.Logger | None = None,
    ) -> None:
        self.plugin = plugin
        self.host = host
        self.port = port
        self.api_token = str(api_token or "")
        self.rate_limit_per_minute = max(1, int(rate_limit_per_minute))
        self.max_input_chars = max(1, int(max_input_chars))
        self.logger = logger or logging.getLogger(__name__)
        self._request_times: dict[str, deque[float]] = defaultdict(deque)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._app: web.Application | None = None
        self._task: asyncio.Task | None = None

    def _build_app(self) -> web.Application:
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_post("/v1/audio/speech", self._handle_audio_speech)
        app.router.add_get("/v1/models", self._handle_list_models)
        app.router.add_get("/", self._handle_root)
        return app

    async def start(self) -> None:
        if self._runner is not None:
            return
        if not self.api_token:
            raise RuntimeError("api server token is required")
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
        auth_error = self._authenticate(request)
        if auth_error is not None:
            return auth_error
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
        auth_error = self._authenticate(request)
        if auth_error is not None:
            return auth_error
        rate_error = self._check_rate_limit(request)
        if rate_error is not None:
            return rate_error
        plugin = self.plugin
        if plugin is None:
            return _error_response(
                "plugin not ready", 503, "plugin_not_ready", "server_error"
            )
        if request.content_type != "application/json":
            return _error_response(
                "content type must be application/json",
                415,
                "unsupported_media_type",
            )
        try:
            body = await request.json()
        except Exception:
            return _error_response("invalid JSON request body", 400, "invalid_json")

        if not isinstance(body, dict):
            return _error_response(
                "request body must be a JSON object", 400, "invalid_request_body"
            )

        expected_model = str(getattr(plugin.plugin_config, "model", "") or "").strip()
        requested_model = str(body.get("model") or "").strip()
        if not requested_model:
            return _error_response("field 'model' is required", 400, "model_required")
        if expected_model and requested_model != expected_model:
            return _error_response("requested model is not available", 404, "model_not_found")

        text = str(body.get("input") or body.get("text") or "").strip()
        if not text:
            return _error_response("field 'input' is required", 400, "input_required")
        if len(text) > self.max_input_chars:
            return _error_response(
                f"field 'input' exceeds {self.max_input_chars} characters",
                400,
                "input_too_long",
            )

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
            return _error_response(
                "speech synthesis failed", 502, "synthesis_failed", "server_error"
            )

        if not outputs:
            return _error_response(
                "speech synthesis returned no audio",
                502,
                "empty_audio",
                "server_error",
            )

        try:
            data = _concat_wav([_read_bytes(path) for path in outputs])
        except (AudioMergeError, OSError) as exc:
            self.logger.warning("[voice-hub] api server invalid WAV output: %s", exc)
            return _error_response(
                "speech provider returned invalid or incompatible WAV audio",
                502,
                "invalid_audio",
                "server_error",
            )

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

    def _authenticate(self, request: web.Request) -> web.Response | None:
        authorization = str(request.headers.get("Authorization") or "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(
            supplied.strip(), self.api_token
        ):
            response = _error_response(
                "invalid or missing bearer token",
                401,
                "invalid_api_key",
                "authentication_error",
            )
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return None

    def _check_rate_limit(self, request: web.Request) -> web.Response | None:
        now = time.monotonic()
        key = request.remote or "unknown"
        timestamps = self._request_times[key]
        while timestamps and now - timestamps[0] >= 60:
            timestamps.popleft()
        if len(timestamps) >= self.rate_limit_per_minute:
            response = _error_response(
                "rate limit exceeded", 429, "rate_limit_exceeded", "rate_limit_error"
            )
            response.headers["Retry-After"] = "60"
            return response
        timestamps.append(now)
        return None


def _error_response(
    message: str,
    status: int,
    code: str = "invalid_request",
    error_type: str = "invalid_request_error",
) -> web.Response:
    return web.json_response(
        {"error": {"message": message, "type": error_type, "code": code}},
        status=status,
    )


def _read_bytes(path: Any) -> bytes:
    from pathlib import Path

    path = Path(path)
    return path.read_bytes()


def _concat_wav(chunks: list[bytes]) -> bytes:
    """Compatibility wrapper around the shared validated WAV merger."""
    return merge_wav_bytes(chunks)
