import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core import silk_codec
from astrbot_plugin_voice_hub.core.silk_codec import (
    SILK_MAGIC,
    SILK_SAMPLE_RATE,
    SilkEncodeError,
    looks_like_silk,
    silk_available,
    wav_to_silk,
)


class _FakePysilk:
    """记录调用参数的 pysilk 替身。"""

    def __init__(self, magic: bytes = b"\x02#!SILK_V3", payload: bytes = b"silkdata"):
        self.magic = magic
        self.payload = payload
        self.calls = []

    def encode(self, source, target, sample_rate, bit_rate, tencent=False):
        self.calls.append((sample_rate, bit_rate, tencent))
        self.source_pcm = source.getvalue()
        target.write(self.magic + self.payload)


class SilkCodecTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.audio = Path(self._tmp.name) / "voice.wav"
        self.audio.write_bytes(b"RIFF0000WAVE")

    def tearDown(self):
        self._tmp.cleanup()

    def test_encode_uses_24k_and_tencent_header(self):
        fake = _FakePysilk()
        pcm = b"\x00\x01" * 24000

        with mock.patch.object(silk_codec, "_pysilk", fake), mock.patch.object(
            silk_codec, "_resample_to_pcm", return_value=pcm
        ):
            data = wav_to_silk(self.audio)

        self.assertTrue(data.startswith(b"\x02#!SILK_V3"))
        self.assertEqual(fake.calls, [(SILK_SAMPLE_RATE, 24000, True)])
        self.assertEqual(fake.source_pcm, pcm)

    def test_missing_pysilk_raises_readable_error(self):
        with mock.patch.object(silk_codec, "_pysilk", None):
            with self.assertRaises(SilkEncodeError) as ctx:
                wav_to_silk(self.audio)
        self.assertIn("pysilk", str(ctx.exception))

    def test_missing_file_raises(self):
        fake = _FakePysilk()
        with mock.patch.object(silk_codec, "_pysilk", fake):
            with self.assertRaises(SilkEncodeError) as ctx:
                wav_to_silk(Path("/nonexistent/voice.wav"))
        self.assertIn("不存在", str(ctx.exception))

    def test_missing_tencent_header_is_rejected(self):
        """头不对时 napcat 会再尝试 ffmpeg 转换，等于没修，必须报错。"""
        fake = _FakePysilk(magic=b"plain-wav!")
        with mock.patch.object(silk_codec, "_pysilk", fake), mock.patch.object(
            silk_codec, "_resample_to_pcm", return_value=b"\x00\x00" * 100
        ):
            with self.assertRaises(SilkEncodeError) as ctx:
                wav_to_silk(self.audio)
        self.assertIn("腾讯文件头", str(ctx.exception))

    def test_empty_encode_result_is_rejected(self):
        class Empty(_FakePysilk):
            def encode(self, source, target, sample_rate, bit_rate, tencent=False):
                self.calls.append((sample_rate, bit_rate, tencent))

        with mock.patch.object(silk_codec, "_pysilk", Empty()), mock.patch.object(
            silk_codec, "_resample_to_pcm", return_value=b"\x00\x00" * 100
        ):
            with self.assertRaises(SilkEncodeError) as ctx:
                wav_to_silk(self.audio)
        self.assertIn("没有产生数据", str(ctx.exception))


class ResampleTests(unittest.TestCase):
    def test_resample_passes_24k_mono_s16le(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(command, 0, b"\x00\x00" * 100, b"")

        with mock.patch.object(silk_codec.shutil, "which", return_value="/usr/bin/ffmpeg"):
            with mock.patch.object(silk_codec.subprocess, "run", fake_run):
                pcm = silk_codec._resample_to_pcm(Path("voice.wav"))

        self.assertEqual(len(pcm), 200)
        command = captured["command"]
        self.assertIn("-ar", command)
        self.assertEqual(command[command.index("-ar") + 1], "24000")
        self.assertEqual(command[command.index("-ac") + 1], "1")
        self.assertEqual(command[command.index("-f") + 1], "s16le")

    def test_resample_failure_reports_stderr(self):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"", b"Invalid data found")

        with mock.patch.object(silk_codec.shutil, "which", return_value="/usr/bin/ffmpeg"):
            with mock.patch.object(silk_codec.subprocess, "run", fake_run):
                with self.assertRaises(SilkEncodeError) as ctx:
                    silk_codec._resample_to_pcm(Path("voice.wav"))
        self.assertIn("Invalid data found", str(ctx.exception))

    def test_resample_without_ffmpeg_explains(self):
        with mock.patch.object(silk_codec.shutil, "which", return_value=None):
            with self.assertRaises(SilkEncodeError) as ctx:
                silk_codec._resample_to_pcm(Path("voice.wav"))
        self.assertIn("ffmpeg", str(ctx.exception))


class AvailabilityTests(unittest.TestCase):
    def test_available_requires_both(self):
        with mock.patch.object(silk_codec, "_pysilk", object()), mock.patch.object(
            silk_codec.shutil, "which", return_value="/usr/bin/ffmpeg"
        ):
            self.assertTrue(silk_available())
        with mock.patch.object(silk_codec, "_pysilk", None), mock.patch.object(
            silk_codec.shutil, "which", return_value="/usr/bin/ffmpeg"
        ):
            self.assertFalse(silk_available())
        with mock.patch.object(silk_codec, "_pysilk", object()), mock.patch.object(
            silk_codec.shutil, "which", return_value=None
        ):
            self.assertFalse(silk_available())

    def test_looks_like_silk_matches_napcat_rule(self):
        self.assertTrue(looks_like_silk(b"\x02#!SILK_V3" + b"payload"))
        self.assertTrue(looks_like_silk(b"#!SILK_V3" + b"payload"))
        self.assertFalse(looks_like_silk(b"RIFF1234WAVE"))
        # napcat 只看前 10 字节
        self.assertFalse(looks_like_silk(b"0123456789" + SILK_MAGIC))


if __name__ == "__main__":
    unittest.main()
