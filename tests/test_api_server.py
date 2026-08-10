import asyncio
import json
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiohttp.test_utils import TestClient, TestServer

from astrbot_plugin_voice_hub.core.api_server import (
    MimoTTSApiServer,
    _concat_wav,
    _read_bytes,
)


class _FakePlugin:
    def __init__(self, outputs=None, error=None, model="mimo-v2.5-tts-voiceclone"):
        self.plugin_config = types.SimpleNamespace(model=model)
        self._outputs = outputs
        self._error = error
        self.synthesize_calls = []

    async def synthesize_text(self, text, **kwargs):
        self.synthesize_calls.append({"text": text, **kwargs})
        if self._error is not None:
            raise self._error
        return list(self._outputs or [])


def _make_wav(data: bytes = b"\x00\x01\x02\x03") -> bytes:
    """构造一个最小的 44 字节 header WAV。"""
    num_channels = 1
    sample_rate = 16000
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + data


class ApiServerTests(unittest.TestCase):
    def _make_server(self, plugin, **kwargs):
        kwargs.setdefault("api_token", "test-token")
        server = MimoTTSApiServer(
            plugin,
            logger=types.SimpleNamespace(
                info=lambda *a, **k: None, warning=lambda *a, **k: None
            ),
            **kwargs,
        )
        return TestServer(server._build_app())

    @staticmethod
    def _headers(token="test-token"):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def test_running_waits_until_socket_bind_completes(self):
        async def run():
            server = MimoTTSApiServer(_FakePlugin(), api_token="test-token")
            bind_gate = asyncio.Event()

            async def delayed_start():
                await bind_gate.wait()

            runner = types.SimpleNamespace(
                setup=AsyncMock(), cleanup=AsyncMock()
            )
            site = types.SimpleNamespace(
                start=delayed_start, stop=AsyncMock()
            )
            with patch(
                "astrbot_plugin_voice_hub.core.api_server.web.AppRunner",
                return_value=runner,
            ), patch(
                "astrbot_plugin_voice_hub.core.api_server.web.TCPSite",
                return_value=site,
            ):
                start_task = asyncio.create_task(server.start())
                while server._site is None:
                    await asyncio.sleep(0)
                self.assertFalse(server.running)

                wait_task = asyncio.create_task(server.wait_until_started(timeout=1.0))
                bind_gate.set()
                await start_task

                self.assertTrue(await wait_task)
                self.assertTrue(server.running)
                await server.stop()
                self.assertFalse(server.running)

        asyncio.run(run())

    def test_bind_failure_completes_wait_with_error(self):
        async def run():
            server = MimoTTSApiServer(_FakePlugin(), api_token="test-token")
            runner = types.SimpleNamespace(
                setup=AsyncMock(), cleanup=AsyncMock()
            )
            site = types.SimpleNamespace(
                start=AsyncMock(side_effect=OSError("address already in use")),
                stop=AsyncMock(),
            )
            with patch(
                "astrbot_plugin_voice_hub.core.api_server.web.AppRunner",
                return_value=runner,
            ), patch(
                "astrbot_plugin_voice_hub.core.api_server.web.TCPSite",
                return_value=site,
            ):
                await server.start()

            self.assertFalse(server.running)
            self.assertFalse(await server.wait_until_started(timeout=0.1))
            self.assertIn("address already in use", server.start_error)

        asyncio.run(run())

    def test_audio_speech_returns_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "voice.wav"
            wav_path.write_bytes(_make_wav(b"\x00\x01\x02\x03"))
            plugin = _FakePlugin(outputs=[wav_path])

            async def run():
                test_server = self._make_server(plugin)
                async with TestClient(test_server) as client:
                    resp = await client.post(
                        "/v1/audio/speech",
                        data=json.dumps(
                            {
                                "model": "mimo-v2.5-tts-voiceclone",
                                "input": "你好",
                                "voice": "旁白",
                            }
                        ),
                        headers=self._headers(),
                    )
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(resp.headers["Content-Type"], "audio/wav")
                    body = await resp.read()
                    self.assertTrue(body.startswith(b"RIFF"))
                    self.assertEqual(len(plugin.synthesize_calls), 1)
                    self.assertEqual(plugin.synthesize_calls[0]["text"], "你好")
                    self.assertEqual(plugin.synthesize_calls[0]["voice_name"], "旁白")

            asyncio.run(run())

    def test_audio_speech_rejects_provider_output_that_is_not_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp3_path = Path(tmp) / "voice.mp3"
            mp3_path.write_bytes(b"ID3\x04\x00\x00audio")
            plugin = _FakePlugin(outputs=[mp3_path])

            async def run():
                test_server = self._make_server(plugin)
                async with TestClient(test_server) as client:
                    resp = await client.post(
                        "/v1/audio/speech",
                        data=json.dumps(
                            {
                                "model": "mimo-v2.5-tts-voiceclone",
                                "input": "hello",
                                "voice": "voice-a",
                            }
                        ),
                        headers=self._headers(),
                    )
                    self.assertEqual(resp.status, 502)
                    body = await resp.json()
                    self.assertEqual(body["error"]["code"], "invalid_audio")

            asyncio.run(run())

    def test_audio_speech_missing_input_returns_400(self):
        plugin = _FakePlugin()

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.post(
                    "/v1/audio/speech",
                    data=json.dumps(
                        {"model": "mimo-v2.5-tts-voiceclone", "voice": "x"}
                    ),
                    headers=self._headers(),
                )
                self.assertEqual(resp.status, 400)
                body = await resp.json()
                self.assertIn("input", body["error"]["message"])

        asyncio.run(run())

    def test_audio_speech_synthesis_failure_returns_500(self):
        plugin = _FakePlugin(error=RuntimeError("upstream down"))

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.post(
                    "/v1/audio/speech",
                    data=json.dumps(
                        {"model": "mimo-v2.5-tts-voiceclone", "input": "你好"}
                    ),
                    headers=self._headers(),
                )
                self.assertEqual(resp.status, 502)
                body = await resp.json()
                self.assertEqual(body["error"]["code"], "synthesis_failed")
                self.assertNotIn("upstream down", body["error"]["message"])

        asyncio.run(run())

    def test_audio_speech_requires_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "voice.wav"
            wav_path.write_bytes(_make_wav())
            plugin = _FakePlugin(outputs=[wav_path])

            async def run():
                test_server = self._make_server(plugin)
                async with TestClient(test_server) as client:
                    resp = await client.post(
                        "/v1/audio/speech",
                        data=json.dumps(
                            {
                                "input": "测试",
                                "model": "mimo-v2.5-tts-voiceclone",
                            }
                        ),
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(resp.status, 401)
                    body = await resp.json()
                    self.assertEqual(body["error"]["code"], "invalid_api_key")
                    self.assertEqual(plugin.synthesize_calls, [])

            asyncio.run(run())

    def test_list_models_returns_model_info(self):
        plugin = _FakePlugin(model="mimo-custom")

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.get(
                    "/v1/models", headers={"Authorization": "Bearer test-token"}
                )
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertEqual(body["object"], "list")
                self.assertEqual(body["data"][0]["id"], "mimo-custom")

        asyncio.run(run())

    def test_audio_speech_rejects_unknown_model(self):
        plugin = _FakePlugin()

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.post(
                    "/v1/audio/speech",
                    data=json.dumps({"model": "unknown", "input": "测试"}),
                    headers=self._headers(),
                )
                self.assertEqual(resp.status, 404)
                body = await resp.json()
                self.assertEqual(body["error"]["code"], "model_not_found")

        asyncio.run(run())

    def test_audio_speech_enforces_input_limit(self):
        plugin = _FakePlugin()

        async def run():
            test_server = self._make_server(plugin, max_input_chars=2)
            async with TestClient(test_server) as client:
                resp = await client.post(
                    "/v1/audio/speech",
                    data=json.dumps(
                        {"model": "mimo-v2.5-tts-voiceclone", "input": "三个字"}
                    ),
                    headers=self._headers(),
                )
                self.assertEqual(resp.status, 400)
                body = await resp.json()
                self.assertEqual(body["error"]["code"], "input_too_long")

        asyncio.run(run())

    def test_audio_speech_enforces_rate_limit(self):
        plugin = _FakePlugin()

        async def run():
            test_server = self._make_server(plugin, rate_limit_per_minute=1)
            async with TestClient(test_server) as client:
                payload = json.dumps(
                    {"model": "mimo-v2.5-tts-voiceclone", "input": "测试"}
                )
                first = await client.post(
                    "/v1/audio/speech", data=payload, headers=self._headers()
                )
                self.assertEqual(first.status, 502)
                second = await client.post(
                    "/v1/audio/speech", data=payload, headers=self._headers()
                )
                self.assertEqual(second.status, 429)
                body = await second.json()
                self.assertEqual(body["error"]["code"], "rate_limit_exceeded")

        asyncio.run(run())

    def test_concat_wav_merges_multiple_segments(self):
        seg1 = _make_wav(b"\x00\x01")
        seg2 = _make_wav(b"\x02\x03\x04\x05")
        merged = _concat_wav([seg1, seg2])
        self.assertTrue(merged.startswith(b"RIFF"))
        # header 之后应是两段 PCM 拼接
        self.assertEqual(merged[44:], b"\x00\x01\x02\x03\x04\x05")

    def test_concat_wav_single_chunk_passthrough(self):
        seg = _make_wav(b"\x00\x01")
        self.assertEqual(_concat_wav([seg]), seg)

    def test_read_bytes_reads_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.bin"
            p.write_bytes(b"hello")
            self.assertEqual(_read_bytes(p), b"hello")


if __name__ == "__main__":
    unittest.main()
