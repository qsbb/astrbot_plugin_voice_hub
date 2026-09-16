"""series.control@1.0 原生值读取与一键固化（write_native）测试。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

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
    def __init__(self):
        self.provider_config = {"id": "provider-a", "type": "openai", "model": "model-a"}

    def meta(self):
        return types.SimpleNamespace(
            id=self.provider_config["id"], model=self.provider_config["model"]
        )


class _Context:
    def __init__(self):
        self.routes = []
        self.providers = [_Provider()]
        self.provider_manager = types.SimpleNamespace(
            curr_provider_inst=self.providers[0],
            provider_insts=self.providers,
            inst_map={self.providers[0].provider_config["id"]: self.providers[0]},
            providers_config=[self.providers[0].provider_config],
        )

    def register_web_api(self, *args):
        self.routes.append(args)

    def get_all_providers(self):
        return list(self.providers)

    def get_using_provider(self, umo=None):
        return self.provider_manager.curr_provider_inst

    async def llm_generate(self, **_kwargs):
        return types.SimpleNamespace(completion_text="{}")


def _command_decorator(*_args, **_kwargs):
    def decorate(func):
        return func

    return decorate


def _register_decorator(*_args, **_kwargs):
    def decorate(cls):
        return cls

    return decorate


def _install_astrbot_stubs() -> None:
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


class SeriesControlNativeWriteTests(unittest.TestCase):
    def setUp(self):
        _install_astrbot_stubs()
        self.module = importlib.import_module("astrbot_plugin_voice_hub.main")
        self.module.logger = _Logger()
        # 同进程内其它测试模块可能已导入过 main；显式把数据目录桩绑定到
        # 本模块，避免 StarTools 全局指向别处导致写入错误的临时目录。
        self.module.StarTools = _StarTools
        from astrbot.core.star.star_handlers_registry import star_handlers_registry

        star_handlers_registry.handlers = []

    def _plugin(self, tmp: str):
        _StarTools.data_dir = tmp
        return self.module.MimoTTSClonePlugin(_Context(), {})

    def test_contract_and_snapshot_expose_native_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._plugin(tmp)

            contract = plugin.series_control_contract()
            self.assertIn("read_native", contract["capabilities"])
            self.assertIn("write_native", contract["capabilities"])

            snapshot = plugin.series_control_snapshot()
            item = snapshot["fields"]["segment_threshold_chars"]
            self.assertEqual(item["native_value"], 180)
            self.assertFalse(item.get("secret", False))

    def test_native_write_persists_config_json_and_backs_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._plugin(tmp)

            result = plugin.series_control_native_write(
                {"segment_threshold_chars": 120}, expected_revision=0
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["reason"], "APPLIED")
            self.assertEqual(result["written"], ["segment_threshold_chars"])
            self.assertTrue(result["backup_id"])

            config_file = Path(tmp) / "config.json"
            persisted = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["segment_threshold_chars"], 120)
            self.assertEqual(plugin.plugin_config.segment_threshold_chars, 120)

            backup = Path(tmp) / f"native-backup-{result['backup_id']}.json"
            self.assertTrue(backup.is_file())
            self.assertEqual(
                json.loads(backup.read_text(encoding="utf-8"))[
                    "segment_threshold_chars"
                ],
                180,
            )

            snapshot = plugin.series_control_snapshot()
            self.assertEqual(
                snapshot["fields"]["segment_threshold_chars"]["native_value"], 120
            )

    def test_native_write_survives_overlay_reset_without_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._plugin(tmp)
            plugin.series_control_set_mode("managed")
            applied = plugin.apply_series_control_patch(
                {"segment_threshold_chars": 120}, expected_revision=0
            )
            self.assertTrue(applied["success"])
            self.assertEqual(plugin.plugin_config.segment_threshold_chars, 120)

            frozen = plugin.series_control_native_write(
                {"segment_threshold_chars": 120}, expected_revision=1
            )
            self.assertEqual(frozen["status"], "ok")

            # 模拟核「一键固化」后清空覆盖层：行为必须保持固化值。
            reset = plugin.reset_series_control_override(
                ["segment_threshold_chars"], expected_revision=None
            )
            self.assertTrue(reset["success"])
            self.assertEqual(plugin.plugin_config.segment_threshold_chars, 120)
            persisted = json.loads(
                (Path(tmp) / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["segment_threshold_chars"], 120)

    def test_native_write_rejects_unknown_invalid_and_stale_patches(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._plugin(tmp)

            unknown = plugin.series_control_native_write(
                {"api_key": "x"}, expected_revision=0
            )
            self.assertEqual(unknown["status"], "error")
            self.assertEqual(unknown["reason"], "UNKNOWN_FIELD")

            invalid_type = plugin.series_control_native_write(
                {"segment_enabled": "yes"}, expected_revision=0
            )
            self.assertEqual(invalid_type["status"], "error")
            self.assertEqual(invalid_type["reason"], "INVALID_TYPE")

            invalid_value = plugin.series_control_native_write(
                {"segment_threshold_chars": 0}, expected_revision=0
            )
            self.assertEqual(invalid_value["status"], "error")
            self.assertEqual(invalid_value["reason"], "INVALID_VALUE")

            stale = plugin.series_control_native_write(
                {"segment_threshold_chars": 120}, expected_revision=5
            )
            self.assertEqual(stale["status"], "error")
            self.assertEqual(stale["reason"], "REVISION_CONFLICT")

            self.assertFalse((Path(tmp) / "config.json").exists())

    def test_native_write_rolls_back_memory_when_persist_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._plugin(tmp)
            original = plugin._persist_local_config

            def fail() -> None:
                raise OSError("read-only")

            plugin._persist_local_config = fail
            try:
                result = plugin.series_control_native_write(
                    {"segment_threshold_chars": 120}, expected_revision=0
                )
            finally:
                plugin._persist_local_config = original

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["reason"].startswith("PERSIST_FAILED:"))
            self.assertEqual(plugin.config["segment_threshold_chars"], 180)
            self.assertEqual(plugin.plugin_config.segment_threshold_chars, 180)
            self.assertFalse((Path(tmp) / "config.json").exists())


if __name__ == "__main__":
    unittest.main()
