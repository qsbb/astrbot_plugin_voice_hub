import asyncio
import json
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

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
        server = MimoTTSApiServer(
            plugin,
            logger=types.SimpleNamespace(
                info=lambda *a, **k: None, warning=lambda *a, **k: None
            ),
            **kwargs,
        )
        return TestServer(server._build_app())

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
                            {"model": "any", "input": "你好", "voice": "旁白"}
                        ),
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(resp.headers["Content-Type"], "audio/wav")
                    body = await resp.read()
                    self.assertTrue(body.startswith(b"RIFF"))
                    self.assertEqual(len(plugin.synthesize_calls), 1)
                    self.assertEqual(plugin.synthesize_calls[0]["text"], "你好")
                    self.assertEqual(plugin.synthesize_calls[0]["voice_name"], "旁白")

            asyncio.run(run())

    def test_audio_speech_missing_input_returns_400(self):
        plugin = _FakePlugin()

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.post(
                    "/v1/audio/speech",
                    data=json.dumps({"model": "any", "voice": "x"}),
                    headers={"Content-Type": "application/json"},
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
                    data=json.dumps({"input": "你好"}),
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(resp.status, 500)
                body = await resp.json()
                self.assertIn("upstream down", body["error"]["message"])

        asyncio.run(run())

    def test_audio_speech_no_auth_required(self):
        """token 和 model 均不校验，不带 Authorization 也能调用。"""
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "voice.wav"
            wav_path.write_bytes(_make_wav())
            plugin = _FakePlugin(outputs=[wav_path])

            async def run():
                test_server = self._make_server(plugin)
                async with TestClient(test_server) as client:
                    resp = await client.post(
                        "/v1/audio/speech",
                        data=json.dumps({"input": "测试", "model": "whatever"}),
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(resp.status, 200)

            asyncio.run(run())

    def test_list_models_returns_model_info(self):
        plugin = _FakePlugin(model="mimo-custom")

        async def run():
            test_server = self._make_server(plugin)
            async with TestClient(test_server) as client:
                resp = await client.get("/v1/models")
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertEqual(body["object"], "list")
                self.assertEqual(body["data"][0]["id"], "mimo-custom")

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
