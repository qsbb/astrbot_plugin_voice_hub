# -*- coding: utf-8 -*-
"""FishAudio 后端在 voice_hub 主链路的分发/试听/连接测试行为。"""
import base64
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.config import build_plugin_config


class _RecordingFishClient:
    """替身：记录调用并返回固定 wav 文件。"""

    instances: list["_RecordingFishClient"] = []

    def __init__(self, *, output_dir: Path, reference_id: str = "") -> None:
        self.output_dir = Path(output_dir)
        self.reference_id = reference_id
        self.calls: list[dict] = []
        _RecordingFishClient.instances.append(self)

    @property
    def model(self) -> str:
        return "s2.1-pro-free"

    def output_path_for(self, output_dir) -> Path:
        return self.output_dir / "fishaudio_tts_test.wav"

    async def synthesize_to_file(self, text: str, *, output_path, reference_audio=None):
        # 与真实 FishAudioClient 一致：先创建输出目录再写文件
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.calls.append(
            {"text": text, "reference_audio": reference_audio, "reference_id": self.reference_id}
        )
        Path(output_path).write_bytes(b"RIFF-fake")
        return Path(output_path)


class FishAudioBackendTests(unittest.TestCase):
    def _make_plugin(self, config_overrides: dict, tmp: Path):
        import test_config_persistence as t

        t._install_astrbot_stubs()
        module = t.importlib.import_module("astrbot_plugin_voice_hub.main")
        t._StarTools.data_dir = str(tmp)
        plugin = module.MimoTTSClonePlugin(t._Context(), config_overrides)
        return module, plugin

    def test_synthesize_dispatches_to_fishaudio_backend(self):
        import asyncio
        import test_config_persistence as t

        _RecordingFishClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._make_plugin(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "fish-key",
                    "fishaudio_reference_id": "a" * 32,
                },
                Path(tmp),
            )
            plugin._fishaudio_client = lambda: _RecordingFishClient(
                output_dir=Path(tmp) / "outputs",
                reference_id=plugin.plugin_config.fishaudio_reference_id,
            )
            outputs = asyncio.run(
                plugin.synthesize_text("你好呀，今天也要加油。", split=False)
            )
            self.assertEqual(len(outputs), 1)
            client = _RecordingFishClient.instances[-1]
            self.assertEqual(len(client.calls), 1)
            spoken = client.calls[0]["text"]
            # fishaudio 分支不做 MiMo 音色克隆链路
            self.assertTrue(spoken)

    def test_fishaudio_readiness_requires_key(self):
        import test_config_persistence as t

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._make_plugin(
                {"tts_backend": "fishaudio", "fishaudio_api_key": ""},
                Path(tmp),
            )
            self.assertIn("API Key", plugin._fishaudio_readiness())
            plugin.plugin_config = build_plugin_config(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "k",
                    "fishaudio_reference_id": "bad",
                }
            )
            self.assertIn("格式无效", plugin._fishaudio_readiness())

    def test_model_resolution_official_vs_selfhosted(self):
        import test_config_persistence as t

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._make_plugin(
                {"tts_backend": "fishaudio", "fishaudio_api_key": "k"},
                Path(tmp),
            )
            self.assertEqual(plugin._fishaudio_model_for_request(), "s2.1-pro-free")
            plugin.plugin_config = build_plugin_config(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "k",
                    "fishaudio_api_base": "http://127.0.0.1:8080/v1",
                }
            )
            # auto 在自建/中转接口也统一补 s2.1-pro：空 model 头会让部分中转挂起，
            # fish-speech 服务器会忽略该头，不会破坏自建直连。
            self.assertEqual(plugin._fishaudio_model_for_request(), "s2.1-pro-free")
            plugin.plugin_config = build_plugin_config(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "k",
                    "fishaudio_model": "s1",
                }
            )
            self.assertEqual(plugin._fishaudio_model_for_request(), "s1")

    def test_prepared_text_applies_fish_emotion(self):
        import test_config_persistence as t

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._make_plugin(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "k",
                    "fishaudio_emotion_mode": "balanced",
                },
                Path(tmp),
            )
            spoken = plugin._fishaudio_prepared_text("太棒了，好期待！", emotion="happy")
            self.assertTrue(spoken.startswith("["))
            # S1 模型使用圆括号
            plugin.plugin_config = build_plugin_config(
                {
                    "tts_backend": "fishaudio",
                    "fishaudio_api_key": "k",
                    "fishaudio_model": "s1",
                    "fishaudio_emotion_mode": "balanced",
                }
            )
            spoken_s1 = plugin._fishaudio_prepared_text("谢谢你陪着我。", emotion="")
            self.assertTrue(spoken_s1.startswith("("))

    def test_pages_payload_redacts_fishaudio_key(self):
        import test_config_persistence as t

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._make_plugin(
                {"tts_backend": "fishaudio", "fishaudio_api_key": "fish-secret"},
                Path(tmp),
            )
            payload = plugin._pages_payload()
            self.assertEqual(payload["config"]["fishaudio_api_key"], "")
            self.assertTrue(payload["readiness"]["fishaudio_api_key"])


class FishAudioExpressionNoteTests(unittest.TestCase):
    """fishaudio 后端给主模型的控制词语法说明（上游 drama-3 指令移植）。"""

    def _plugin(self, overrides: dict, tmp):
        import test_config_persistence as t

        module, plugin = FishAudioBackendTests._make_plugin(
            FishAudioBackendTests(), {"tts_backend": "fishaudio", "fishaudio_api_key": "k", **overrides}, tmp
        )
        return module, plugin

    def test_note_empty_for_non_fishaudio_backend(self):
        import tempfile
        import test_config_persistence as t

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = FishAudioBackendTests._make_plugin(
                FishAudioBackendTests(), {"tts_backend": "mimo", "api_key": "k"}, Path(tmp)
            )
            self.assertEqual(plugin._fishaudio_expression_note(), "")

    def test_note_describes_s2_bracket_syntax(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({}, tmp)
            note = plugin._fishaudio_expression_note()
            self.assertIn("方括号", note)
            self.assertIn("[开心]", note)

    def test_note_describes_s1_parenthesis_syntax(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({"fishaudio_model": "s1"}, tmp)
            note = plugin._fishaudio_expression_note()
            self.assertIn("圆括号", note)
            self.assertIn("(joyful)", note)

    def test_note_describes_drama3_directives(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({"fishaudio_model": "drama-3"}, tmp)
            note = plugin._fishaudio_expression_note()
            self.assertIn("Drama 3", note)
            self.assertIn("<soft>", note)

    def test_prepared_text_allows_drama3_paired_tags(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({"fishaudio_model": "drama-3"}, tmp)
            spoken = plugin._fishaudio_prepared_text(
                "[轻声安慰]没关系，<soft>慢慢来。</soft>", emotion=""
            )
            # 方括号指令与成对局部标签都应原样保留
            self.assertIn("[轻声安慰]", spoken)
            self.assertIn("<soft>慢慢来。</soft>", spoken)

    def test_judge_prompt_appends_expression_note(self):
        import tempfile
        import types

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({}, tmp)
            request = types.SimpleNamespace(
                extra_user_content_parts=None, system_prompt=""
            )
            plugin._inject_tts_judge_prompt(request)
            # 测试 stub 里 TextPart=None，走 system_prompt 回退路径
            self.assertIn("方括号", str(request.system_prompt))


class AudioTransportTests(unittest.TestCase):
    """上游 0.7.x 传输层移植：path / base64 / shared_path + 平台门禁。"""

    def _plugin(self, overrides: dict, tmp):
        import test_config_persistence as t

        module, plugin = FishAudioBackendTests._make_plugin(
            FishAudioBackendTests(), {"api_key": "k", **overrides}, tmp
        )
        return module, plugin

    def _wav(self, tmp: Path, *, size: int = 64) -> Path:
        import wave

        path = tmp / "segment.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * (size // 2))
        return path

    def test_path_transport_returns_local_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({"audio_transport": "path"}, Path(tmp))
            wav = self._wav(Path(tmp))
            self.assertEqual(plugin._audio_source(wav), str(wav))

    def test_base64_transport_embeds_payload(self):
        import base64 as b64
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({"audio_transport": "base64"}, Path(tmp))
            wav = self._wav(Path(tmp))
            source = plugin._audio_source(wav)
            self.assertTrue(source.startswith("base64://"))
            self.assertEqual(
                base64.b64decode(source[len("base64://"):]), wav.read_bytes()
            )

    def test_base64_transport_rejects_oversized_audio(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin(
                {"audio_transport": "base64", "base64_max_mb": 1}, Path(tmp)
            )
            big = Path(tmp) / "big.wav"
            big.write_bytes(b"\x00" * (1024 * 1024 + 1))
            with self.assertRaisesRegex(RuntimeError, "Base64 上限"):
                plugin._audio_source(big)

    def test_shared_path_stages_windows_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            linux_root = Path(tmp) / "shared"
            windows_root = "C:\\Users\\Public\\voice_hub_audio"
            module, plugin = self._plugin(
                {
                    "audio_transport": "shared_path",
                    "shared_path_linux": str(linux_root),
                    "shared_path_windows": windows_root,
                },
                Path(tmp),
            )
            wav = self._wav(Path(tmp))
            source = plugin._audio_source(wav)
            self.assertTrue(
                PureWindowsPath(source).is_relative_to(PureWindowsPath(windows_root))
            )
            self.assertTrue(linux_root.exists())
            self.assertEqual(len(list(linux_root.iterdir())), 1)

    def test_shared_path_requires_both_roots(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin(
                {
                    "audio_transport": "shared_path",
                    "shared_path_linux": str(Path(tmp) / "shared"),
                    "shared_path_windows": "",
                },
                Path(tmp),
            )
            wav = self._wav(Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "同时配置"):
                plugin._audio_source(wav)

    def test_shared_path_gate_rejects_non_aiocqhttp(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin(
                {"audio_transport": "shared_path"}, Path(tmp)
            )
            with self.assertRaisesRegex(RuntimeError, "仅支持 aiocqhttp"):
                plugin._ensure_shared_path_platform("qq_official:FriendMessage:123")
            with self.assertRaisesRegex(RuntimeError, "仅支持 aiocqhttp"):
                plugin._ensure_shared_path_platform("websearch:GroupMessage:456")
            # aiocqhttp 与空 UMO 不报错
            plugin._ensure_shared_path_platform("aiocqhttp:GroupMessage:789")
            plugin._ensure_shared_path_platform("")

    def test_parse_session_variants(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin({}, Path(tmp))
            self.assertEqual(
                plugin._parse_aiocqhttp_session("aiocqhttp:GroupMessage:123"),
                (True, 123),
            )
            self.assertEqual(
                plugin._parse_aiocqhttp_session("aiocqhttp:FriendMessage:456"),
                (False, 456),
            )
            with self.assertRaisesRegex(RuntimeError, "会话类型"):
                plugin._parse_aiocqhttp_session("aiocqhttp:Other:123")
            with self.assertRaisesRegex(RuntimeError, "目标 ID"):
                plugin._parse_aiocqhttp_session("aiocqhttp:GroupMessage:abc")

    def test_send_audio_result_base64_failure_does_not_silently_pass(self):
        import asyncio
        import tempfile
        import types

        with tempfile.TemporaryDirectory() as tmp:
            module, plugin = self._plugin(
                {
                    "audio_transport": "base64",
                    "file_fallback_enabled": True,
                },
                Path(tmp),
            )
            big = self._wav(Path(tmp))
            sent = []

            def _fail_source(_path):
                raise RuntimeError("Base64 上限测试")

            def _fake_send(chain):
                sent.append(chain)

            event = types.SimpleNamespace(
                unified_msg_origin="aiocqhttp:FriendMessage:123",
                chain_result=lambda components: components,
                send=_fake_send,
            )
            # Record 构建失败（模拟超大音频）时必须向上抛，不能静默回退成假确认
            with patch.object(plugin, "_audio_source", side_effect=_fail_source):
                with self.assertRaisesRegex(RuntimeError, "Base64 上限"):
                    asyncio.run(plugin._send_audio_result(event, big))
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
