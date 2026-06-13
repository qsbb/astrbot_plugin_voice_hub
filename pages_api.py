from __future__ import annotations

import asyncio
import base64
import inspect
import pathlib
import re
import time

from quart import jsonify, request

from .core.audio_codec import AudioValidationError, SUPPORTED_AUDIO_MIME, validate_voice_file


class PagesAPIMixin:
    def _register_pages_web_api(self) -> None:
        register_web_api = getattr(self.context, "register_web_api", None)
        if not callable(register_web_api):
            self.logger.warning("[mimo-tts] context.register_web_api unavailable")
            return
        plugin_id = "astrbot_plugin_mimo_tts_clone"
        routes = [
            ("get_config", self._pages_get_config, ["GET"], "获取 MiMo TTS 配置"),
            ("save_config", self._pages_save_config, ["POST"], "保存 MiMo TTS 配置"),
            ("list_voices", self._pages_list_voices, ["GET"], "列出音色"),
            ("upload_voice_sample", self._pages_upload_voice_sample, ["POST"], "上传音色样本"),
            ("update_voice", self._pages_update_voice, ["POST"], "更新音色"),
            ("delete_voice", self._pages_delete_voice, ["POST"], "删除音色"),
            ("set_default_voice", self._pages_set_default_voice, ["POST"], "设置默认音色"),
            ("synthesize_preview", self._pages_synthesize_preview, ["POST"], "试听音色"),
        ]
        for name, handler, methods, desc in routes:
            register_web_api(f"/{plugin_id}/{name}", handler, methods, desc)

    async def _pages_get_config(self):
        return jsonify(
            {
                "success": True,
                "config": dict(self.config),
                "voices": [voice.to_dict() for voice in self.voice_store.list_voices()],
                "defaults": self.voice_store.defaults(),
            }
        )

    async def _pages_save_config(self):
        data = await request.get_json(force=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Invalid JSON payload"}), 400
        self._update_runtime_config(data)
        return jsonify({"success": True, "config": dict(self.config)})

    async def _pages_list_voices(self):
        return jsonify(
            {
                "success": True,
                "voices": [voice.to_dict() for voice in self.voice_store.list_voices()],
                "defaults": self.voice_store.defaults(),
            }
        )

    async def _pages_upload_voice_sample(self):
        files = await request.files
        form = await request.form
        file = files.get("file")
        if file is None:
            return jsonify({"success": False, "error": "未收到音频文件"}), 400

        data = file.read()
        if inspect.isawaitable(data):
            data = await data
        filename = pathlib.Path(file.filename or "voice.wav").name
        ext = pathlib.Path(filename).suffix.lower()
        if ext not in SUPPORTED_AUDIO_MIME:
            return jsonify({"success": False, "error": "仅支持 mp3 / wav 音频"}), 400
        if len(data) > self.plugin_config.max_voice_file_bytes:
            return jsonify({"success": False, "error": "音频文件超过大小限制"}), 400

        voice_dir = pathlib.Path(self.data_dir) / "voice_refs"
        voice_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^\w.-]+", "_", pathlib.Path(filename).stem).strip("._") or "voice"
        save_path = voice_dir / f"{time.time_ns()}_{stem[:60]}{ext}"
        await asyncio.to_thread(save_path.write_bytes, data)
        try:
            validate_voice_file(save_path, max_bytes=self.plugin_config.max_voice_file_bytes)
        except AudioValidationError as exc:
            save_path.unlink(missing_ok=True)
            return jsonify({"success": False, "error": str(exc)}), 400

        name = str(form.get("name") or pathlib.Path(filename).stem or "新音色").strip()
        description = str(form.get("description") or "").strip()
        created_by = str(form.get("created_by") or "pages").strip()
        consent = str(form.get("consent_confirmed") or "true").lower() in {"1", "true", "yes", "on"}
        voice = self.voice_store.add_voice(name, save_path, description, created_by, consent)
        return jsonify({"success": True, "voice": voice.to_dict()})

    async def _pages_update_voice(self):
        data = await request.get_json(force=True) or {}
        voice_id = str(data.get("voice_id") or data.get("id") or "").strip()
        if not voice_id:
            return jsonify({"success": False, "error": "缺少 voice_id"}), 400
        changes = {}
        for key in ("name", "description", "enabled"):
            if key in data:
                changes[key] = data[key]
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
        return jsonify({"success": deleted})

    async def _pages_set_default_voice(self):
        data = await request.get_json(force=True) or {}
        scope = str(data.get("scope") or "global").strip().lower()
        voice_id = str(data.get("voice_id") or "").strip()
        if self.voice_store.get_voice(voice_id) is None:
            return jsonify({"success": False, "error": "音色不存在"}), 404
        if scope == "user":
            self.voice_store.set_user_default(str(data.get("user_id") or ""), voice_id)
        elif scope == "group":
            self.voice_store.set_group_default(str(data.get("group_id") or ""), voice_id)
        else:
            self.voice_store.set_global_default(voice_id)
        return jsonify({"success": True, "defaults": self.voice_store.defaults()})

    async def _pages_synthesize_preview(self):
        data = await request.get_json(force=True) or {}
        text = str(data.get("text") or "").strip()
        voice_selector = str(data.get("voice_id") or data.get("voice") or "").strip()
        context = str(data.get("context") or self.config.get("default_context") or "")
        if not text:
            return jsonify({"success": False, "error": "请输入试听文本"}), 400
        voice = self.voice_store.find_voice(voice_selector) or self.voice_store.get_voice(
            self.voice_store.resolve_voice_id(None, "", "") or ""
        )
        if voice is None:
            return jsonify({"success": False, "error": "没有可用音色"}), 400
        try:
            output_path = await self._synthesize_text_to_file(text, voice, context=context)
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500
        raw = await asyncio.to_thread(pathlib.Path(output_path).read_bytes)
        return jsonify(
            {
                "success": True,
                "audio_data": "data:audio/wav;base64," + base64.b64encode(raw).decode("utf-8"),
                "voice": voice.to_dict(),
            }
        )
