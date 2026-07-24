from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
import pathlib
from typing import Any

from quart import jsonify, request

from .core.audio_codec import (
    AudioValidationError,
)
from .core.emotion import SUPPORTED_EMOTIONS, normalize_emotion
from .core.pages_upload import store_voice_sample
from .core.text_processing import clean_tts_text


class PagesAPIMixin:
    @staticmethod
    def _pages_error(message: str, status: int = 400, detail: str = ""):
        payload = {"success": False, "error": message}
        if detail:
            payload["detail"] = detail
        return jsonify(payload), status

    def _register_pages_web_api(self) -> None:
        register_web_api = getattr(self.context, "register_web_api", None)
        if not callable(register_web_api):
            self.logger.warning("[voice-hub] context.register_web_api unavailable")
            return
        plugin_id = "astrbot_plugin_voice_hub"
        routes = [
            ("get_config", self._pages_get_config, ["GET"], "获取凝心溯溪-声配置"),
            ("save_config", self._pages_save_config, ["POST"], "保存凝心溯溪-声配置"),
            ("list_voices", self._pages_list_voices, ["GET"], "列出音色"),
            (
                "list_ai_providers",
                self._pages_list_ai_providers,
                ["GET"],
                "列出 AstrBot AI 服务商",
            ),
            (
                "upload_voice_sample",
                self._pages_upload_voice_sample,
                ["POST"],
                "上传音色样本",
            ),
            (
                "upload_voice_sample_json",
                self._pages_upload_voice_sample_json,
                ["POST"],
                "上传音色样本(JSON)",
            ),
            ("update_voice", self._pages_update_voice, ["POST"], "更新音色"),
            ("delete_voice", self._pages_delete_voice, ["POST"], "删除音色"),
            (
                "set_default_voice",
                self._pages_set_default_voice,
                ["POST"],
                "设置默认音色",
            ),
            (
                "set_emotion_voice",
                self._pages_set_emotion_voice,
                ["POST"],
                "设置情绪默认音色",
            ),
            (
                "synthesize_preview",
                self._pages_synthesize_preview,
                ["POST"],
                "试听音色",
            ),
            (
                "test_connection",
                self._pages_test_connection,
                ["POST"],
                "测试凝心溯溪-声连接",
            ),
            (
                "list_tts_providers",
                self._pages_list_tts_providers,
                ["GET"],
                "列出 AstrBot TTS 提供商",
            ),
            (
                "migrate_old_plugin",
                self._pages_migrate_old_plugin,
                ["POST"],
                "从旧插件迁移配置",
            ),
        ]
        for name, handler, methods, desc in routes:
            register_web_api(f"/{plugin_id}/{name}", handler, methods, desc)

    def _pages_payload(self) -> dict:
        voices = self.voice_store.list_voices()
        enabled_voices = [voice for voice in voices if voice.enabled]
        providers = self._list_ai_providers()
        return {
            "success": True,
            "config": dict(self.config),
            "voices": [voice.to_dict() for voice in voices],
            "defaults": self.voice_store.defaults(),
            "emotions": list(SUPPORTED_EMOTIONS),
            "access_control": self._auto_tts_access_preview(),
            "readiness": {
                "api_key": bool(self.plugin_config.api_key),
                "voices": bool(enabled_voices),
                "ai_director": bool(
                    self.plugin_config.ai_style_director_enabled
                    and (providers or self.plugin_config.ai_style_director_provider_id)
                ),
                "providers": len(providers),
            },
        }

    async def _pages_get_config(self):
        return jsonify(self._pages_payload())

    async def _pages_save_config(self):
        data = await request.get_json(force=True) or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return jsonify({"success": False, "error": "Invalid JSON payload"}), 400
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Invalid JSON payload"}), 400
        persisted = self._update_runtime_config(data)
        if not persisted.get("local") and not persisted.get("native"):
            return jsonify(
                {
                    "success": False,
                    "error": "配置保存失败：无法写入 AstrBot 配置或插件本地配置文件。",
                    "detail": persisted.get("warning") or "",
                }
            ), 500
        response = {
            "success": True,
            "config": dict(self.config),
            "persisted": persisted,
        }
        if persisted.get("warning"):
            response["warning"] = (
                "配置已保存到插件本地文件，但 AstrBot 原生配置同步失败。"
            )
            response["detail"] = persisted["warning"]
        return jsonify(response)

    async def _pages_list_voices(self):
        return jsonify(self._pages_payload())

    async def _pages_list_ai_providers(self):
        return jsonify(
            {
                "success": True,
                "providers": self._list_ai_providers(),
            }
        )

    def _list_ai_providers(self) -> list[dict[str, str]]:
        candidates: list[Any] = []

        getter = getattr(self.context, "get_all_providers", None)
        if callable(getter):
            try:
                candidates.extend(list(getter() or []))
            except Exception as exc:
                self.logger.warning(
                    "[voice-hub] failed to list AstrBot AI providers: %s", exc
                )

        provider_manager = getattr(self.context, "provider_manager", None)
        if provider_manager is not None:
            candidates.extend(
                list(getattr(provider_manager, "provider_insts", []) or [])
            )
            inst_map = getattr(provider_manager, "inst_map", None)
            if isinstance(inst_map, dict):
                candidates.extend(list(inst_map.values()))
            provider_configs = getattr(provider_manager, "providers_config", None)
            if isinstance(provider_configs, list):
                candidates.extend(
                    cfg
                    for cfg in provider_configs
                    if isinstance(cfg, dict)
                    and str(cfg.get("provider_type") or cfg.get("type") or "").strip()
                    in {"", "chat_completion"}
                )

        seen: set[tuple[str, str]] = set()
        items: list[dict[str, str]] = []
        for provider in candidates:
            item = self._normalize_ai_provider(provider)
            if item is None:
                continue
            key = (item["id"], item["model"])
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

        items.sort(key=lambda item: (item["label"], item["id"]))
        return items

    @staticmethod
    def _normalize_ai_provider(provider: Any) -> dict[str, str] | None:
        if isinstance(provider, dict):
            provider_id = str(provider.get("id") or "").strip()
            model = str(provider.get("model") or "").strip()
            if not provider_id:
                return None
            label = provider_id if not model else f"{provider_id} / {model}"
            return {
                "id": provider_id,
                "name": provider_id,
                "model": model,
                "label": label,
            }

        meta_fn = getattr(provider, "meta", None)
        meta = None
        if callable(meta_fn):
            try:
                meta = meta_fn()
            except Exception:
                meta = None

        provider_id = ""
        model = ""
        if meta is not None:
            provider_id = str(getattr(meta, "id", "") or "").strip()
            model = str(getattr(meta, "model", "") or "").strip()

        provider_config = getattr(provider, "provider_config", None)
        if not provider_id and isinstance(provider_config, dict):
            provider_id = str(provider_config.get("id") or "").strip()
        if not model and isinstance(provider_config, dict):
            model = str(provider_config.get("model") or "").strip()

        if not provider_id:
            return None

        label = provider_id if not model else f"{provider_id} / {model}"
        return {"id": provider_id, "name": provider_id, "model": model, "label": label}

    async def _pages_upload_voice_sample(self):
        files = await request.files
        form = await request.form
        file = files.get("file")
        if file is None:
            return jsonify({"success": False, "error": "未收到音频文件"}), 400

        data = file.read()
        if inspect.isawaitable(data):
            data = await data
        try:
            voice = await store_voice_sample(
                voice_store=self.voice_store,
                data_dir=self.data_dir,
                max_voice_file_bytes=self.plugin_config.max_voice_file_bytes,
                data=data,
                filename=file.filename or "voice.wav",
                metadata=form,
            )
        except AudioValidationError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        return jsonify({"success": True, "voice": voice.to_dict()})

    async def _pages_upload_voice_sample_json(self):
        payload = await request.get_json(force=True) or {}
        filename = str(payload.get("filename") or "voice.wav")
        encoded = str(payload.get("audio_base64") or "")
        if "," in encoded and encoded.strip().lower().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"success": False, "error": "音频 Base64 数据无效"}), 400

        try:
            voice = await store_voice_sample(
                voice_store=self.voice_store,
                data_dir=self.data_dir,
                max_voice_file_bytes=self.plugin_config.max_voice_file_bytes,
                data=data,
                filename=filename,
                metadata=payload,
            )
        except AudioValidationError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        return jsonify({"success": True, "voice": voice.to_dict()})

    async def _pages_update_voice(self):
        data = await request.get_json(force=True) or {}
        voice_id = str(data.get("voice_id") or data.get("id") or "").strip()
        if not voice_id:
            return jsonify({"success": False, "error": "缺少 voice_id"}), 400
        changes = {}
        for key in (
            "name",
            "description",
            "enabled",
            "style_context",
            "style_tags",
            "emotion",
        ):
            if key in data:
                changes[key] = data[key]
        if "emotion" in changes:
            changes["emotion"] = normalize_emotion(changes["emotion"]) or ""
        voice = self.voice_store.update_voice(voice_id, **changes)
        if voice is None:
            return jsonify({"success": False, "error": "音色不存在"}), 404
        return jsonify({"success": True, "voice": voice.to_dict()})

    async def _pages_delete_voice(self):
        data = await request.get_json(force=True) or {}
        voice_id = str(data.get("voice_id") or data.get("id") or "").strip()
        voice = self.voice_store.get_voice(voice_id)
        deleted = self.voice_store.delete_voice(voice_id)
        if voice is not None:
            pathlib.Path(voice.audio_path).unlink(missing_ok=True)
        return jsonify({"success": deleted, "defaults": self.voice_store.defaults()})

    async def _pages_set_default_voice(self):
        data = await request.get_json(force=True) or {}
        scope = str(data.get("scope") or "global").strip().lower()
        voice_id = str(data.get("voice_id") or "").strip()
        if self.voice_store.get_voice(voice_id) is None:
            return jsonify({"success": False, "error": "音色不存在"}), 404
        if scope == "user":
            self.voice_store.set_user_default(str(data.get("user_id") or ""), voice_id)
        elif scope == "group":
            self.voice_store.set_group_default(
                str(data.get("group_id") or ""), voice_id
            )
        else:
            self.voice_store.set_global_default(voice_id)
        return jsonify({"success": True, "defaults": self.voice_store.defaults()})

    async def _pages_set_emotion_voice(self):
        data = await request.get_json(force=True) or {}
        emotion = normalize_emotion(str(data.get("emotion") or ""))
        voice_id = str(data.get("voice_id") or "").strip()
        if emotion not in SUPPORTED_EMOTIONS:
            return jsonify({"success": False, "error": "不支持的情绪"}), 400
        if not voice_id:
            self.voice_store.set_emotion_default(emotion, "")
            return jsonify({"success": True, "defaults": self.voice_store.defaults()})
        if self.voice_store.get_voice(voice_id) is None:
            return jsonify({"success": False, "error": "音色不存在"}), 404
        self.voice_store.set_emotion_default(emotion, voice_id)
        return jsonify({"success": True, "defaults": self.voice_store.defaults()})

    async def _pages_synthesize_preview(self):
        data = await request.get_json(force=True) or {}
        text = clean_tts_text(str(data.get("text") or ""))
        voice_selector = str(data.get("voice_id") or data.get("voice") or "").strip()
        requested_emotion = str(data.get("emotion") or "").strip()
        command_context = str(data.get("context") or "")
        if not text:
            return jsonify({"success": False, "error": "请输入试听文本"}), 400

        emotion = self._resolve_emotion(text, requested_emotion)
        voice = self._select_voice(voice_selector or None, emotion=emotion)
        if voice is None:
            return jsonify({"success": False, "error": "没有可用音色"}), 400

        try:
            outputs = await self.synthesize_text(
                text,
                voice_id=voice.id,
                emotion=emotion,
                context=command_context,
                split=False,
            )
        except AudioValidationError as exc:
            return self._pages_error(f"参考音频不可用：{exc}", 400, str(exc))
        except RuntimeError as exc:
            message = str(exc)
            if "API Key" in message:
                return self._pages_error(
                    "MiMo API Key 未配置或未成功保存，请先在页面顶部保存配置。",
                    400,
                    message,
                )
            if "文本过长" in message or "鏂囨湰杩囬暱" in message:
                return self._pages_error(message, 400, message)
            return self._pages_error(f"MiMo 试听生成失败：{message}", 502, message)
        except Exception as exc:
            return self._pages_error(f"试听生成异常：{exc}", 502, str(exc))
        output_path = outputs[0]
        raw = await asyncio.to_thread(pathlib.Path(output_path).read_bytes)
        return jsonify(
            {
                "success": True,
                "audio_data": "data:audio/wav;base64,"
                + base64.b64encode(raw).decode("utf-8"),
                "voice": voice.to_dict(),
                "emotion": emotion,
            }
        )

    async def _pages_test_connection(self):
        data = await request.get_json(force=True) or {}
        text = clean_tts_text(str(data.get("text") or "连接测试，声音工作正常。"))
        voice_selector = str(data.get("voice_id") or data.get("voice") or "").strip()
        if not self.plugin_config.api_key:
            return self._pages_error("MiMo API Key 未配置，请先保存配置。", 400)
        if not self.voice_store.list_voices(include_disabled=False):
            return self._pages_error("暂无可用音色，请先上传参考音频。", 400)
        started = asyncio.get_running_loop().time()
        try:
            outputs = await self.synthesize_text(
                text,
                voice_id=voice_selector or None,
                split=False,
            )
        except Exception as exc:
            return self._pages_error(f"连接测试失败：{exc}", 502, str(exc))
        elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
        for output in outputs:
            pathlib.Path(output).unlink(missing_ok=True)

        # 若外部 TTS API 已开启，顺带诊断其可达性
        api_status = None
        if self.plugin_config.api_server_enabled:
            api_status = await self._diagnose_api_server(text, voice_selector)

        message = "连接测试成功，MiMo 已返回音频。"
        if api_status:
            if api_status["ok"]:
                message += f" 外部 API 诊断通过（{api_status['elapsed_ms']}ms）。"
            else:
                message += f" 外部 API 诊断失败：{api_status['error']}。"
        return jsonify(
            {
                "success": True,
                "message": message,
                "elapsed_ms": elapsed_ms,
                "api_server": api_status,
            }
        )

    async def _diagnose_api_server(self, text: str, voice_selector: str) -> dict:
        """通过 HTTP 调用本地 API server，验证可达性和响应。"""
        import aiohttp

        port = self.plugin_config.api_server_port
        url = f"http://127.0.0.1:{port}/v1/audio/speech"
        started = asyncio.get_running_loop().time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        "model": "diagnostic",
                        "input": text,
                        "voice": voice_selector or "",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    elapsed_ms = round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    )
                    if resp.status != 200:
                        body = await resp.text()
                        return {
                            "ok": False,
                            "elapsed_ms": elapsed_ms,
                            "error": f"HTTP {resp.status}: {body[:200]}",
                        }
                    audio_bytes = await resp.read()
                    if not audio_bytes or len(audio_bytes) < 44:
                        return {
                            "ok": False,
                            "elapsed_ms": elapsed_ms,
                            "error": "返回的音频数据为空或过短",
                        }
                    return {
                        "ok": True,
                        "elapsed_ms": elapsed_ms,
                        "size": len(audio_bytes),
                    }
        except Exception as exc:
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
            return {
                "ok": False,
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
            }

    async def _pages_list_tts_providers(self):
        providers = self.list_astrbot_tts_providers()
        return jsonify({"success": True, "providers": providers})

    async def _pages_migrate_old_plugin(self):
        result = self.migrate_from_old_plugin()
        return jsonify(result)
