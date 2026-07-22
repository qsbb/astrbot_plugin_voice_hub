import importlib
import asyncio
import functools
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _Logger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.debugs = []

    def info(self, *args, **kwargs):
        self.infos.append(args)

    def warning(self, *args, **kwargs):
        self.warnings.append(args)

    def debug(self, *args, **kwargs):
        self.debugs.append(args)


class _Star:
    def __init__(self, context):
        self.context = context


class _StarTools:
    data_dir = ""

    @staticmethod
    def get_data_dir(_name):
        return _StarTools.data_dir


class _Provider:
    def __init__(self, owner=None, provider_id="provider-a", model="model-a"):
        self.owner = owner
        self.provider_config = {"id": provider_id, "type": "openai", "model": model}
        self.calls = []

    def meta(self):
        return types.SimpleNamespace(
            id=self.provider_config["id"], model=self.provider_config["model"]
        )

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.owner is not None and self.owner.fail_llm:
            if getattr(self.owner, "fail_llm_empty", False):
                raise TimeoutError()
            raise RuntimeError("llm failed")
        return types.SimpleNamespace(
            completion_text='{"style_context":"用默认服务商生成的温柔语气。","speech_text":"晚上好，欢迎回来。"}'
        )


class _Context:
    def __init__(self):
        self.routes = []
        self.llm_calls = []
        self.fail_llm = False
        self.fail_llm_empty = False
        self.providers = [_Provider(owner=self)]
        self.provider_manager = types.SimpleNamespace(
            curr_provider_inst=self.providers[0],
            provider_insts=self.providers,
            inst_map={self.providers[0].provider_config["id"]: self.providers[0]},
            providers_config=[self.providers[0].provider_config],
        )

    def register_web_api(self, *args):
        self.routes.append(args)

    async def llm_generate(self, **kwargs):
        self.llm_calls.append(kwargs)
        if self.fail_llm:
            raise RuntimeError("llm failed")
        return types.SimpleNamespace(
            completion_text='{"style_context":"用轻柔、贴近、带一点夜晚陪伴感的语气。","speech_text":"晚上好，欢迎回来。"}'
        )

    def get_all_providers(self):
        return list(self.providers)

    def get_using_provider(self, umo=None):
        return self.provider_manager.curr_provider_inst


def _command_decorator(*_args, **_kwargs):
    def decorate(func):
        return func

    return decorate


def _register_decorator(*_args, **_kwargs):
    def decorate(cls):
        return cls

    return decorate


def _install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = _Logger()

    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    event.filter = types.SimpleNamespace(
        command=_command_decorator,
        llm_tool=_command_decorator,
        on_llm_request=_command_decorator,
        on_decorating_result=_command_decorator,
    )

    message_components = types.ModuleType("astrbot.api.message_components")
    message_components.File = object
    message_components.Plain = type("Plain", (), {})
    message_components.Record = object

    star = types.ModuleType("astrbot.api.star")
    star.Context = _Context
    star.Star = _Star
    star.StarTools = _StarTools
    star.register = _register_decorator

    sys.modules.setdefault("astrbot", astrbot)
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.message_components"] = message_components
    sys.modules["astrbot.api.star"] = star

    # stub star_handlers_registry 用于热重载清理测试
    registry_mod = types.ModuleType("astrbot.core.star.star_handlers_registry")
    registry_mod.star_handlers_registry = types.SimpleNamespace(handlers=[])
    sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    star_core_mod = sys.modules.setdefault(
        "astrbot.core.star", types.ModuleType("astrbot.core.star")
    )
    star_core_mod.star_handlers_registry = registry_mod.star_handlers_registry
    sys.modules["astrbot.core.star.star_handlers_registry"] = registry_mod

    quart = types.ModuleType("quart")
    quart.jsonify = lambda payload: payload
    quart.request = types.SimpleNamespace()
    sys.modules["quart"] = quart


class _FailingNativeConfig(dict):
    def save_config(self):
        raise RuntimeError("native write failed")


class _GetOnlyConfig:
    def __init__(self, values):
        self.values = values

    def get(self, key):
        return self.values.get(key)


class ConfigPersistenceTests(unittest.TestCase):
    def setUp(self):
        _install_astrbot_stubs()
        self.module = importlib.import_module("astrbot_plugin_voice_hub.main")
        self.module.logger = _Logger()
        # 重置 registry stub
        from astrbot.core.star.star_handlers_registry import star_handlers_registry

        star_handlers_registry.handlers = []

    def test_pages_config_persists_locally_when_native_save_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), _FailingNativeConfig())

            persisted = plugin._update_runtime_config(
                {"api_key": "mimo-secret", "max_text_chars": 321}
            )

            self.assertTrue(persisted["local"])
            self.assertFalse(persisted["native"])
            saved = json.loads((Path(tmp) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["api_key"], "mimo-secret")
            self.assertEqual(saved["max_text_chars"], 321)
            self.assertEqual(saved["tts_trigger_mode"], "llm_decides")
            self.assertFalse(saved["auto_tts_enabled"])

            reloaded = self.module.MimoTTSClonePlugin(_Context(), {})
            self.assertEqual(reloaded.config["api_key"], "mimo-secret")
            self.assertEqual(reloaded.config["max_text_chars"], 321)

    def test_pages_lists_astrbot_ai_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})

            providers = plugin._list_ai_providers()

            self.assertEqual(providers[0]["id"], "provider-a")
            self.assertIn("model-a", providers[0]["label"])

    def test_pages_payload_reports_operator_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {"api_key": "mimo-secret", "ai_style_director_enabled": True},
            )
            plugin.voice_store.add_voice("旁白", Path(tmp) / "voice.wav", "", "", True)

            payload = plugin._pages_payload()

            self.assertTrue(payload["readiness"]["api_key"])
            self.assertTrue(payload["readiness"]["voices"])
            self.assertTrue(payload["readiness"]["ai_director"])
            self.assertEqual(payload["readiness"]["providers"], 1)

    def test_plugin_reads_get_only_native_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            config = _GetOnlyConfig(
                {"api_key": "from-native-get", "max_text_chars": 222}
            )

            plugin = self.module.MimoTTSClonePlugin(_Context(), config)

            self.assertEqual(plugin.config["api_key"], "from-native-get")
            self.assertEqual(plugin.config["max_text_chars"], 222)

    def test_tts_chat_commands_and_parsers_are_removed(self):
        plugin_cls = self.module.MimoTTSClonePlugin

        self.assertFalse(hasattr(plugin_cls, "tts_command"))
        self.assertFalse(hasattr(plugin_cls, "list_voices_command"))
        self.assertFalse(hasattr(plugin_cls, "set_user_voice_command"))
        self.assertFalse(hasattr(plugin_cls, "set_global_voice_command"))
        self.assertFalse(hasattr(plugin_cls, "set_group_voice_command"))
        self.assertFalse(hasattr(plugin_cls, "set_emotion_voice_command"))
        self.assertFalse(hasattr(plugin_cls, "status_command"))
        self.assertFalse(hasattr(plugin_cls, "_tail"))
        self.assertFalse(hasattr(plugin_cls, "_tail_any"))
        self.assertFalse(hasattr(plugin_cls, "_parse_tts_args"))

    def test_runtime_config_normalizes_delivery_options(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config(
            {
                "reply_mode": "bad",
                "auto_tts_enabled": "true",
                "auto_tts_probability": 2,
                "file_fallback_enabled": "false",
                "output_retention_days": -1,
                "output_max_files": -5,
                "emotion_routing_enabled": "off",
                "replace_url_in_tts": "off",
            }
        )

        self.assertEqual(cfg["reply_mode"], "audio_only")
        self.assertEqual(cfg["tts_trigger_mode"], "probability")
        self.assertTrue(cfg["auto_tts_enabled"])
        self.assertEqual(cfg["auto_tts_probability"], 1.0)
        self.assertFalse(cfg["file_fallback_enabled"])
        self.assertFalse(cfg["emotion_routing_enabled"])
        self.assertEqual(cfg["output_retention_days"], 0)
        self.assertEqual(cfg["output_max_files"], 0)
        self.assertFalse(cfg["replace_url_in_tts"])

    def test_runtime_config_normalizes_api_server_options(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config(
            {
                "api_server_enabled": "true",
                "api_server_host": "  127.0.0.1  ",
                "api_server_port": "8080",
            }
        )

        self.assertTrue(cfg["api_server_enabled"])
        self.assertEqual(cfg["api_server_host"], "127.0.0.1")
        self.assertEqual(cfg["api_server_port"], 8080)

        # 默认值
        defaults = normalize_config({})
        self.assertFalse(defaults["api_server_enabled"])
        self.assertEqual(defaults["api_server_host"], "0.0.0.0")
        self.assertEqual(defaults["api_server_port"], 9960)

    def test_runtime_config_migrates_legacy_skip_url_tts_to_replace_url_in_tts(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        # 旧配置 skip_url_tts 应迁移到 replace_url_in_tts
        migrated_on = normalize_config({"skip_url_tts": True})
        migrated_off = normalize_config({"skip_url_tts": False})
        # 新配置直接覆盖，旧字段被忽略
        new_off = normalize_config({"skip_url_tts": True, "replace_url_in_tts": False})

        self.assertTrue(migrated_on["replace_url_in_tts"])
        self.assertFalse(migrated_off["replace_url_in_tts"])
        self.assertFalse(new_off["replace_url_in_tts"])

    def test_runtime_config_migrates_legacy_auto_tts_enabled_to_trigger_mode(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        enabled = normalize_config({"auto_tts_enabled": True})
        disabled = normalize_config({"auto_tts_enabled": False})

        self.assertEqual(enabled["tts_trigger_mode"], "probability")
        self.assertTrue(enabled["auto_tts_enabled"])
        self.assertEqual(disabled["tts_trigger_mode"], "llm_decides")
        self.assertFalse(disabled["auto_tts_enabled"])

    def test_runtime_config_trigger_mode_is_authoritative_and_syncs_legacy_field(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        llm_decides = normalize_config(
            {"tts_trigger_mode": " LLM_DECIDES ", "auto_tts_enabled": True}
        )
        probability = normalize_config(
            {"tts_trigger_mode": "probability", "auto_tts_enabled": False}
        )
        unsupported = normalize_config(
            {"tts_trigger_mode": "unsupported", "auto_tts_enabled": False}
        )

        self.assertEqual(llm_decides["tts_trigger_mode"], "llm_decides")
        self.assertFalse(llm_decides["auto_tts_enabled"])
        self.assertEqual(probability["tts_trigger_mode"], "probability")
        self.assertTrue(probability["auto_tts_enabled"])
        self.assertEqual(unsupported["tts_trigger_mode"], "probability")
        self.assertTrue(unsupported["auto_tts_enabled"])

    def test_runtime_config_normalizes_auto_tts_scope_lists(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config(
            {
                "auto_tts_group_whitelist": "123, 456\n123",
                "auto_tts_group_blacklist": ["789", " 789 ", ""],
                "auto_tts_private_whitelist": "alice，bob",
                "auto_tts_private_blacklist": None,
            }
        )

        self.assertEqual(cfg["auto_tts_group_whitelist"], ["123", "456"])
        self.assertEqual(cfg["auto_tts_group_blacklist"], ["789"])
        self.assertEqual(cfg["auto_tts_private_whitelist"], ["alice", "bob"])
        self.assertEqual(cfg["auto_tts_private_blacklist"], [])
        self.assertEqual(cfg["admin_users"], [])

    def test_runtime_config_normalizes_admin_users(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config({"admin_users": "admin-1, admin-2\nadmin-1"})

        self.assertEqual(cfg["admin_users"], ["admin-1", "admin-2"])

    def test_runtime_config_normalizes_ai_style_director_options(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config(
            {
                "ai_style_director_enabled": "true",
                "ai_style_director_provider_id": "  director-a  ",
                "ai_style_director_prompt": "  让语音更像真人  ",
                "ai_style_director_mode": "hybrid",
                "ai_style_director_max_chars": 12,
                "ai_style_director_optimize_text": "on",
                "ai_style_director_fallback_to_emotion": "off",
                "ai_style_director_debug_log": "off",
            }
        )

        self.assertTrue(cfg["ai_style_director_enabled"])
        self.assertEqual(cfg["ai_style_director_provider_id"], "director-a")
        self.assertEqual(cfg["ai_style_director_prompt"], "让语音更像真人")
        self.assertEqual(cfg["ai_style_director_mode"], "hybrid")
        self.assertEqual(cfg["ai_style_director_max_chars"], 20)
        self.assertTrue(cfg["ai_style_director_optimize_text"])
        self.assertFalse(cfg["ai_style_director_fallback_to_emotion"])
        self.assertFalse(cfg["ai_style_director_debug_log"])

    def test_runtime_config_migrates_legacy_file_fallback(self):
        from astrbot_plugin_voice_hub.core.config import normalize_config

        cfg = normalize_config({"send_as_file_fallback": False})

        self.assertFalse(cfg["file_fallback_enabled"])
        self.assertNotIn("send_as_file_fallback", cfg)

    def test_cleanup_outputs_keeps_newest_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {"output_retention_days": 0, "output_max_files": 2},
            )
            output_dir = Path(tmp) / "outputs"
            output_dir.mkdir()
            old = output_dir / "mimo_tts_old.wav"
            mid = output_dir / "mimo_tts_mid.wav"
            new = output_dir / "mimo_tts_new.wav"
            for index, path in enumerate((old, mid, new), start=1):
                path.write_bytes(b"RIFF....WAVE")
                path.touch()
                path.stat()
                os.utime(path, (index, index))

            plugin._cleanup_outputs()

            self.assertFalse(old.exists())
            self.assertTrue(mid.exists())
            self.assertTrue(new.exists())

    def test_text_to_speech_returns_first_output_path_for_generic_callers(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})

            async def fake_synthesize_text(text, **kwargs):
                self.assertEqual(text, "hello")
                self.assertEqual(kwargs["emotion"], "happy")
                self.assertEqual(kwargs["group_id"], "aiocqhttp:FriendMessage:123")
                return [Path(tmp) / "voice.wav"]

            plugin.synthesize_text = fake_synthesize_text
            result = asyncio.run(
                plugin.text_to_speech(
                    "hello",
                    emotion="happy",
                    target_umo="aiocqhttp:FriendMessage:123",
                )
            )

            self.assertEqual(result, str(Path(tmp) / "voice.wav"))

    def test_auto_tts_scope_whitelist_and_blacklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "auto_tts_group_whitelist": [
                        "group-a",
                        "aiocqhttp:GroupMessage:group-b",
                    ],
                    "auto_tts_group_blacklist": ["group-x"],
                    "auto_tts_private_whitelist": ["user-a"],
                    "auto_tts_private_blacklist": ["user-x"],
                },
            )

            def make_event(origin: str, sender: str = "sender"):
                return types.SimpleNamespace(
                    unified_msg_origin=origin,
                    get_extra=lambda key: (
                        types.SimpleNamespace(
                            conversation=types.SimpleNamespace(cid=origin)
                        )
                        if key == "provider_request"
                        else None
                    ),
                    get_sender_id=lambda: sender,
                )

            self.assertTrue(
                plugin._scope_allowed(make_event("aiocqhttp:GroupMessage:group-b"))
            )
            self.assertFalse(
                plugin._scope_allowed(make_event("aiocqhttp:GroupMessage:group-x"))
            )
            self.assertFalse(
                plugin._scope_allowed(make_event("aiocqhttp:GroupMessage:group-z"))
            )
            self.assertTrue(
                plugin._scope_allowed(make_event("aiocqhttp:FriendMessage:user-a"))
            )
            self.assertFalse(
                plugin._scope_allowed(make_event("aiocqhttp:FriendMessage:user-x"))
            )
            self.assertFalse(
                plugin._scope_allowed(make_event("aiocqhttp:FriendMessage:user-z"))
            )

    def test_auto_tts_scope_allows_admins_even_when_blacklisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "admin_users": ["admin-1"],
                    "auto_tts_group_blacklist": ["group-x"],
                    "auto_tts_private_blacklist": ["user-x"],
                },
            )

            def make_event(origin: str, sender: str):
                return types.SimpleNamespace(
                    unified_msg_origin=origin,
                    get_extra=lambda key: (
                        types.SimpleNamespace(
                            conversation=types.SimpleNamespace(cid=origin)
                        )
                        if key == "provider_request"
                        else None
                    ),
                    get_sender_id=lambda: sender,
                )

            self.assertTrue(
                plugin._scope_allowed(
                    make_event("aiocqhttp:GroupMessage:group-x", "admin-1")
                )
            )
            self.assertTrue(
                plugin._scope_allowed(
                    make_event("aiocqhttp:FriendMessage:user-x", "admin-1")
                )
            )
            self.assertFalse(
                plugin._scope_allowed(
                    make_event("aiocqhttp:GroupMessage:group-x", "normal-user")
                )
            )

    def test_auto_tts_access_decision_explains_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "admin_users": ["admin-1"],
                    "auto_tts_group_whitelist": ["group-ok"],
                    "auto_tts_group_blacklist": ["group-block"],
                },
            )

            def make_event(origin: str, sender: str = "normal-user"):
                return types.SimpleNamespace(
                    unified_msg_origin=origin,
                    get_extra=lambda key: (
                        types.SimpleNamespace(
                            conversation=types.SimpleNamespace(cid=origin)
                        )
                        if key == "provider_request"
                        else None
                    ),
                    get_sender_id=lambda: sender,
                )

            admin = plugin._auto_tts_access_decision(
                make_event("aiocqhttp:GroupMessage:group-block", "admin-1")
            )
            blacklisted = plugin._auto_tts_access_decision(
                make_event("aiocqhttp:GroupMessage:group-block")
            )
            whitelist_miss = plugin._auto_tts_access_decision(
                make_event("aiocqhttp:GroupMessage:group-miss")
            )
            unrestricted_private = plugin._auto_tts_access_decision(
                make_event("aiocqhttp:FriendMessage:user-free")
            )

            self.assertTrue(admin["allowed"])
            self.assertIn("admin bypass", admin["reason"])
            self.assertFalse(blacklisted["allowed"])
            self.assertIn("blacklist matched", blacklisted["reason"])
            self.assertFalse(whitelist_miss["allowed"])
            self.assertIn("whitelist missed", whitelist_miss["reason"])
            self.assertTrue(unrestricted_private["allowed"])
            self.assertIn("unrestricted", unrestricted_private["reason"])

    def test_pages_payload_includes_access_control_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "admin_users": ["admin-1"],
                    "auto_tts_group_whitelist": ["group-ok"],
                    "auto_tts_group_blacklist": ["group-block"],
                },
            )

            payload = plugin._pages_payload()

            self.assertIn("access_control", payload)
            preview = payload["access_control"]
            self.assertEqual(preview["admins"]["count"], 1)
            self.assertEqual(preview["group"]["whitelist_count"], 1)
            self.assertEqual(preview["group"]["blacklist_count"], 1)
            self.assertIn("黑名单", preview["summary"])

    def test_probability_mode_filters_only_mimo_tts_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(), {"tts_trigger_mode": "probability"}
            )
            request = types.SimpleNamespace(
                tools=[
                    {"type": "function", "function": {"name": "mimo_tts_speak"}},
                    {"type": "function", "function": {"name": "web_search"}},
                ]
            )

            asyncio.run(plugin.filter_tts_tool_for_probability_mode(object(), request))

            self.assertEqual(
                [tool["function"]["name"] for tool in request.tools], ["web_search"]
            )

    def test_llm_decides_mode_preserves_mimo_tts_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(), {"tts_trigger_mode": "llm_decides"}
            )
            tools = [{"type": "function", "function": {"name": "mimo_tts_speak"}}]
            request = types.SimpleNamespace(tools=list(tools))

            asyncio.run(plugin.filter_tts_tool_for_probability_mode(object(), request))

            self.assertEqual(request.tools, tools)

    def test_mimo_tts_speak_llm_tool_is_available_when_supported(self):
        self.assertTrue(hasattr(self.module.MimoTTSClonePlugin, "mimo_tts_speak"))

    def test_mimo_tts_speak_avoids_reserved_context_argument(self):
        params = inspect.signature(
            self.module.MimoTTSClonePlugin.mimo_tts_speak
        ).parameters

        self.assertNotIn("context", params)
        self.assertIn("style", params)

    def test_mimo_tts_speak_docstring_defines_llm_calling_boundaries(self):
        docstring = inspect.getdoc(self.module.MimoTTSClonePlugin.mimo_tts_speak)

        self.assertIn("Do not call it for an ordinary text reply", docstring)
        self.assertIn(
            "For long text, decide whether voice delivery is suitable", docstring
        )
        self.assertIn("Generate `style` directly", docstring)
        # 防止 LLM 调用工具后再用 send_message_to_user 重发同一音频
        self.assertIn("DO NOT call send_message_to_user", docstring)
        self.assertIn("already in the user's chat", docstring)

    def test_mimo_tts_speak_marks_event_and_disables_secondary_style_director(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})
            extras = {}
            calls = []
            sent = []
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: extras.__setitem__(key, value),
                get_extra=lambda key: extras.get(key),
                clear_result=lambda: None,
            )

            async def fake_synthesize_text(text, **kwargs):
                calls.append((text, kwargs))
                return [Path(tmp) / "voice.wav"]

            async def fake_send_audio_result(current_event, output):
                sent.append((current_event, output))

            plugin.synthesize_text = fake_synthesize_text
            plugin._send_audio_result = fake_send_audio_result

            async def invoke():
                return [
                    item
                    async for item in plugin.mimo_tts_speak(event, "???", style="??")
                ]

            result = asyncio.run(invoke())

            self.assertTrue(extras[plugin.TTS_HANDLED_EVENT_KEY])
            self.assertEqual(calls[0][0], "???")
            self.assertEqual(calls[0][1]["context"], "??")
            self.assertFalse(calls[0][1]["style_director_enabled"])
            self.assertEqual(len(sent), 1)
            # 返回值应是明确的状态陈述而非内部路径，避免 LLM 把路径当成待发送资源
            self.assertEqual(
                result,
                [
                    "audio already sent to user (1 segment); do not resend it via other tools"
                ],
            )

    def test_mimo_tts_speak_does_not_mark_event_when_first_audio_send_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})
            extras = {}
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: extras.__setitem__(key, value),
                get_extra=lambda key: extras.get(key),
            )

            async def fake_synthesize_text(text, **kwargs):
                return [Path(tmp) / "voice.wav"]

            async def fake_send_audio_result(current_event, output):
                raise RuntimeError("send failed")

            plugin.synthesize_text = fake_synthesize_text
            plugin._send_audio_result = fake_send_audio_result

            async def invoke():
                return [item async for item in plugin.mimo_tts_speak(event, "测试")]

            with self.assertRaisesRegex(RuntimeError, "send failed"):
                asyncio.run(invoke())

            self.assertNotIn(plugin.TTS_HANDLED_EVENT_KEY, extras)

    def test_mimo_tts_speak_does_not_mark_event_when_no_audio_is_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})
            extras = {}
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: extras.__setitem__(key, value),
                get_extra=lambda key: extras.get(key),
            )

            async def fake_synthesize_text(text, **kwargs):
                return []

            plugin.synthesize_text = fake_synthesize_text

            async def invoke():
                return [item async for item in plugin.mimo_tts_speak(event, "测试")]

            result = asyncio.run(invoke())

            self.assertEqual(result, ["no audio generated"])
            self.assertNotIn(plugin.TTS_HANDLED_EVENT_KEY, extras)

    def test_mimo_tts_speak_keeps_event_marked_after_later_audio_send_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})
            extras = {}
            sent = []
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: extras.__setitem__(key, value),
                get_extra=lambda key: extras.get(key),
            )

            async def fake_synthesize_text(text, **kwargs):
                return [Path(tmp) / "voice-1.wav", Path(tmp) / "voice-2.wav"]

            async def fake_send_audio_result(current_event, output):
                sent.append(output)
                if len(sent) == 2:
                    raise RuntimeError("send failed")

            plugin.synthesize_text = fake_synthesize_text
            plugin._send_audio_result = fake_send_audio_result

            async def invoke():
                return [item async for item in plugin.mimo_tts_speak(event, "长文本")]

            with self.assertRaisesRegex(RuntimeError, "send failed"):
                asyncio.run(invoke())

            self.assertTrue(extras[plugin.TTS_HANDLED_EVENT_KEY])
            self.assertEqual(len(sent), 2)

    def test_llm_decides_mode_skips_probability_auto_tts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "tts_trigger_mode": "llm_decides",
                    "auto_tts_enabled": True,
                    "auto_tts_probability": 1.0,
                },
            )
            plugin._run_auto_tts = AsyncMock(
                side_effect=AssertionError("must not synthesize")
            )

            asyncio.run(plugin.auto_tts_reply(object()))

            plugin._run_auto_tts.assert_not_awaited()

    def test_auto_tts_skips_event_marked_by_llm_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {"auto_tts_enabled": True, "auto_tts_probability": 1},
            )
            event = types.SimpleNamespace(
                get_extra=lambda key: (
                    True if key == plugin.TTS_HANDLED_EVENT_KEY else None
                ),
            )

            asyncio.run(plugin.auto_tts_reply(event))

            log_args = plugin.logger.infos[-1]
            self.assertIn("event already handled", log_args[0] % log_args[1:])

    def test_auto_tts_replaces_url_in_speech_when_replace_url_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "tts_trigger_mode": "probability",
                    "auto_tts_probability": 1.0,
                    "replace_url_in_tts": True,
                },
            )
            captured = {}
            plugin._send_audio_result = AsyncMock()
            plugin._audio_component = lambda path: None

            async def fake_synthesize(text, **kwargs):
                captured["text"] = text
                return [Path(tmp) / "voice.wav"]

            plugin.synthesize_text = fake_synthesize
            result = types.SimpleNamespace(
                chain=[type("Plain", (), {})()],
                is_llm_result=lambda: True,
                get_plain_text=lambda: "请看 https://example.com 这个网页",
            )
            event = types.SimpleNamespace(
                get_extra=lambda key: None,
                set_extra=lambda key, value: None,
                get_sender_id=lambda: "user-a",
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_result=lambda: result,
            )

            asyncio.run(plugin.auto_tts_reply(event))

            # 网址应被替换为占位词，不出现在朗读文本中
            self.assertIn("这个网址", captured["text"])
            self.assertNotIn("https://example.com", captured["text"])
            self.assertIn("这个网页", captured["text"])

    def test_auto_tts_keeps_url_in_speech_when_replace_url_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {
                    "tts_trigger_mode": "probability",
                    "auto_tts_probability": 1.0,
                    "replace_url_in_tts": False,
                },
            )
            captured = {}
            plugin._send_audio_result = AsyncMock()
            plugin._audio_component = lambda path: None

            async def fake_synthesize(text, **kwargs):
                captured["text"] = text
                return [Path(tmp) / "voice.wav"]

            plugin.synthesize_text = fake_synthesize
            result = types.SimpleNamespace(
                chain=[type("Plain", (), {})()],
                is_llm_result=lambda: True,
                get_plain_text=lambda: "请看 https://example.com 这个网页",
            )
            event = types.SimpleNamespace(
                get_extra=lambda key: None,
                set_extra=lambda key, value: None,
                get_sender_id=lambda: "user-a",
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_result=lambda: result,
            )

            asyncio.run(plugin.auto_tts_reply(event))

            # clean_tts_text 仍会移除网址，但不应做替换
            self.assertNotIn("这个网址", captured["text"])

    def test_mimo_tts_speak_replaces_url_when_replace_url_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {"replace_url_in_tts": True},
            )
            captured = {}

            async def fake_synthesize(text, **kwargs):
                captured["text"] = text
                return [Path(tmp) / "voice.wav"]

            plugin.synthesize_text = fake_synthesize
            plugin._send_audio_result = AsyncMock()
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: None,
                get_extra=lambda key: None,
                clear_result=lambda: None,
            )

            async def invoke():
                return [
                    item
                    async for item in plugin.mimo_tts_speak(
                        event, "请看 https://example.com 这个网页"
                    )
                ]

            result = asyncio.run(invoke())

            self.assertIn("这个网址", captured["text"])
            self.assertNotIn("https://example.com", captured["text"])
            self.assertIn("这个网页", captured["text"])
            self.assertIn("audio already sent", result[0])

    def test_mimo_tts_speak_keeps_url_when_replace_url_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(),
                {"replace_url_in_tts": False},
            )
            captured = {}

            async def fake_synthesize(text, **kwargs):
                captured["text"] = text
                return [Path(tmp) / "voice.wav"]

            plugin.synthesize_text = fake_synthesize
            plugin._send_audio_result = AsyncMock()
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: None,
                get_extra=lambda key: None,
                clear_result=lambda: None,
            )

            async def invoke():
                return [
                    item
                    async for item in plugin.mimo_tts_speak(
                        event, "请看 https://example.com 这个网页"
                    )
                ]

            result = asyncio.run(invoke())

            self.assertNotIn("这个网址", captured["text"])
            self.assertIn("audio already sent", result[0])

    def test_ai_style_director_adds_hidden_mimo_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            ctx = _Context()
            plugin = self.module.MimoTTSClonePlugin(
                ctx,
                {
                    "ai_style_director_enabled": True,
                    "ai_style_director_mode": "hybrid",
                    "default_context": "自然清晰",
                    "emotion_contexts": {"neutral": "平稳"},
                },
            )
            voice = plugin.voice_store.add_voice(
                "旁白",
                Path(tmp) / "voice.wav",
                "温柔音色",
                "test",
                True,
                style_context="靠近一点",
            )

            result = asyncio.run(
                plugin._build_tts_context(
                    voice,
                    "neutral",
                    "",
                    text="晚上好，欢迎回来。",
                    style_director_enabled=True,
                )
            )

            self.assertIn("自然清晰", result.context)
            self.assertIn("平稳", result.context)
            self.assertIn("靠近一点", result.context)
            self.assertIn("默认服务商生成", result.context)
            self.assertEqual(result.speech_text, "晚上好，欢迎回来。")
            self.assertEqual(len(ctx.llm_calls), 0)
            self.assertEqual(len(ctx.providers[0].calls), 1)
            self.assertIn(
                "待朗读文本：晚上好，欢迎回来。", ctx.providers[0].calls[0]["prompt"]
            )
            self.assertIn("请输出最终 JSON", ctx.providers[0].calls[0]["prompt"])
            self.assertEqual(len(plugin.logger.infos), 1)
            log_args = plugin.logger.infos[0]
            log_text = log_args[0] % log_args[1:]
            self.assertIn("[voice-hub] AI导演", log_text)
            self.assertIn("cached=false", log_text)
            self.assertIn("style_context=", log_text)
            self.assertIn("speech_text=", log_text)

    def test_ai_style_director_can_fail_hard_when_fallback_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            ctx = _Context()
            ctx.fail_llm = True
            ctx.fail_llm_empty = True
            plugin = self.module.MimoTTSClonePlugin(
                ctx,
                {
                    "ai_style_director_enabled": True,
                    "ai_style_director_fallback_to_emotion": False,
                },
            )
            voice = plugin.voice_store.add_voice(
                "旁白",
                Path(tmp) / "voice.wav",
                "温柔音色",
                "test",
                True,
            )

            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(
                    plugin._build_tts_context(
                        voice,
                        "neutral",
                        "",
                        text="晚上好",
                        style_director_enabled=True,
                    )
                )
            self.assertIn("TimeoutError", str(caught.exception))

    def test_ai_style_director_failure_log_includes_context_when_fallback_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            ctx = _Context()
            ctx.fail_llm = True
            ctx.fail_llm_empty = True
            plugin = self.module.MimoTTSClonePlugin(
                ctx,
                {
                    "ai_style_director_enabled": True,
                    "ai_style_director_provider_id": "openai/deepseek-v4-flash",
                    "ai_style_director_fallback_to_emotion": True,
                    "default_context": "base",
                },
            )
            voice = plugin.voice_store.add_voice(
                "温柔女生",
                Path(tmp) / "voice.wav",
                "soft",
                "test",
                True,
            )

            result = asyncio.run(
                plugin._build_tts_context(
                    voice,
                    "neutral",
                    "",
                    text="晚上好",
                    style_director_enabled=True,
                )
            )

            self.assertIn("base", result.context)
            self.assertEqual(result.speech_text, "晚上好")
            self.assertEqual(len(plugin.logger.warnings), 1)
            warning_args = plugin.logger.warnings[0]
            warning_text = warning_args[0] % warning_args[1:]
            self.assertIn("style director failed", warning_text)
            self.assertIn("provider=openai/deepseek-v4-flash", warning_text)
            self.assertIn("voice=温柔女生", warning_text)
            self.assertIn("emotion=neutral", warning_text)
            self.assertIn("error_type=TimeoutError", warning_text)
            self.assertIn("fallback=true", warning_text)

    def test_terminate_removes_plugin_handlers_from_registry(self):
        """terminate() 应从 star_handlers_registry 移除本插件 handler，防止热重载 partial 套娃。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})
            from astrbot.core.star.star_handlers_registry import star_handlers_registry

            our_handler = types.SimpleNamespace(
                full_name="astrbot_plugin_voice_hub.main.filter_tts_tool_for_probability_mode",
                handler=functools.partial(plugin.filter_tts_tool_for_probability_mode),
            )
            other_handler = types.SimpleNamespace(
                full_name="other_plugin.main.some_handler",
                handler=lambda event: None,
            )
            star_handlers_registry.handlers = [our_handler, other_handler]

            asyncio.run(plugin.terminate())

            self.assertEqual(len(star_handlers_registry.handlers), 1)
            self.assertIs(star_handlers_registry.handlers[0], other_handler)

    def test_terminate_removes_mimo_tts_tool_from_func_tool_manager(self):
        """terminate() 应从 func_tool_manager 移除 mimo_tts_speak 工具。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            ctx = _Context()
            mimo_tool = types.SimpleNamespace(name="mimo_tts_speak", handler=None)
            other_tool = types.SimpleNamespace(name="web_search", handler=None)
            ctx._func_tool_manager = types.SimpleNamespace(
                tools=[mimo_tool, other_tool]
            )
            plugin = self.module.MimoTTSClonePlugin(ctx, {})

            asyncio.run(plugin.terminate())

            self.assertEqual(len(ctx._func_tool_manager.tools), 1)
            self.assertEqual(ctx._func_tool_manager.tools[0].name, "web_search")

    def test_terminate_cleans_via_context_remove_llm_tools(self):
        """terminate() 优先使用 context.remove_llm_tool 方法清理工具。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            ctx = _Context()
            removed = []
            ctx.remove_llm_tool = lambda name: removed.append(name)
            plugin = self.module.MimoTTSClonePlugin(ctx, {})

            asyncio.run(plugin.terminate())

            self.assertIn("mimo_tts_speak", removed)

    def test_terminate_silently_skips_when_registry_not_importable(self):
        """registry 不可导入时 terminate() 应静默跳过，不抛异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})

            # 临时破坏 registry 属性，模拟 handlers 列表不可用
            reg_mod = sys.modules["astrbot.core.star.star_handlers_registry"]
            original_obj = reg_mod.star_handlers_registry
            reg_mod.star_handlers_registry = None

            try:
                asyncio.run(plugin.terminate())
            finally:
                reg_mod.star_handlers_registry = original_obj

    def test_handler_survives_partial_stacking(self):
        """模拟 9 层 partial 套娃，验证 *args 签名能正确提取真实参数。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(), {"tts_trigger_mode": "probability"}
            )
            request = types.SimpleNamespace(
                tools=[{"type": "function", "function": {"name": "mimo_tts_speak"}}]
            )

            # 模拟 9 层 partial 套娃（类似生产环境中 11 were given 的情况）
            stacked = plugin.filter_tts_tool_for_probability_mode
            for _ in range(9):
                stacked = functools.partial(stacked, plugin)

            # 框架调用时传入 (event, request)
            asyncio.run(stacked(object(), request))

            self.assertEqual(len(request.tools), 0)

    def test_auto_tts_reply_survives_partial_stacking(self):
        """模拟 partial 套娃，验证 auto_tts_reply 能正确提取 event。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(
                _Context(), {"tts_trigger_mode": "llm_decides"}
            )

            stacked = plugin.auto_tts_reply
            for _ in range(5):
                stacked = functools.partial(stacked, plugin)

            event = types.SimpleNamespace(
                get_extra=lambda key: (
                    True if key == plugin.TTS_HANDLED_EVENT_KEY else None
                ),
            )

            # 不应抛出 TypeError
            asyncio.run(stacked(event))

    def test_mimo_tts_speak_redirects_none_self_to_current_instance(self):
        """self=None 时，LLM 工具应重定向到 _current_instance。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            plugin = self.module.MimoTTSClonePlugin(_Context(), {})

            # 模拟 self=None 的调用（通过 unbound function）
            unbound = (
                self.module.MimoTTSClonePlugin.mimo_tts_speak.__wrapped__
                if hasattr(self.module.MimoTTSClonePlugin.mimo_tts_speak, "__wrapped__")
                else self.module.MimoTTSClonePlugin.mimo_tts_speak
            )

            extras = {}
            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:user-a",
                get_sender_id=lambda: "user-a",
                set_extra=lambda key, value: extras.__setitem__(key, value),
                get_extra=lambda key: extras.get(key),
                clear_result=lambda: None,
            )

            async def fake_synthesize_text(text, **kwargs):
                return [Path(tmp) / "voice.wav"]

            async def fake_send_audio_result(current_event, output):
                pass

            plugin.synthesize_text = fake_synthesize_text
            plugin._send_audio_result = fake_send_audio_result

            # 用 None 作为 self 调用
            async def invoke():
                return [item async for item in unbound(None, event, "测试")]

            result = asyncio.run(invoke())
            self.assertEqual(
                result,
                [
                    "audio already sent to user (1 segment); do not resend it via other tools"
                ],
            )

    def test_init_unwraps_stale_partials_from_registry(self):
        """__init__ 应将 registry 中已套娃的 handler 重置为原始函数。"""
        with tempfile.TemporaryDirectory() as tmp:
            _StarTools.data_dir = tmp
            from astrbot.core.star.star_handlers_registry import star_handlers_registry

            # 模拟已套娃的 handler
            original_func = (
                self.module.MimoTTSClonePlugin.filter_tts_tool_for_probability_mode
            )
            stacked = functools.partial(
                functools.partial(original_func, "old"), "older"
            )
            fake_handler = types.SimpleNamespace(
                full_name="astrbot_plugin_voice_hub.main.filter_tts_tool_for_probability_mode",
                handler=stacked,
            )
            star_handlers_registry.handlers = [fake_handler]

            # 创建新插件实例，__init__ 应解包
            self.module.MimoTTSClonePlugin(_Context(), {})

            # handler 应被重置为原始未绑定函数
            unwrapped = star_handlers_registry.handlers[0].handler
            self.assertFalse(isinstance(unwrapped, functools.partial))


if __name__ == "__main__":
    unittest.main()
