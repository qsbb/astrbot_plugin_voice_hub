from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.audio_codec import (
    AudioMergeError,
    AudioValidationError,
    PCMOutputValidationError,
    encode_voice_file_data_url,
    estimate_base64_chars,
    inspect_pcm16_wav,
    merge_wav_files,
    repair_streamed_wav_header,
    sniff_audio_format,
)


class AudioCodecTests(unittest.TestCase):
    @staticmethod
    def _write_wav(path, frames, *, frame_rate=16000):
        import wave

        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(frame_rate)
            writer.writeframes(frames)

    def test_encode_voice_file_data_url_accepts_mp3(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.mp3"
            sample.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00mp3-data")

            data_url = encode_voice_file_data_url(sample, max_bytes=100)

        self.assertTrue(data_url.startswith("data:audio/mpeg;base64,SUQz"))

    def test_encode_voice_file_data_url_rejects_unsupported_format(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.ogg"
            sample.write_bytes(b"ogg-data")

            with self.assertRaisesRegex(
                AudioValidationError, "Unsupported audio format"
            ):
                encode_voice_file_data_url(sample, max_bytes=100)

    def test_encode_voice_file_data_url_rejects_large_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.wav"
            sample.write_bytes(b"RIFF" + b"0" * 4 + b"WAVE" + b"0" * 89)

            with self.assertRaisesRegex(AudioValidationError, "Voice file too large"):
                encode_voice_file_data_url(sample, max_bytes=100)

    def test_encode_voice_file_data_url_rejects_invalid_audio_header(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.mp3"
            sample.write_bytes(b"not really an mp3")

            with self.assertRaisesRegex(
                AudioValidationError, "Invalid mp3 audio header"
            ):
                encode_voice_file_data_url(sample, max_bytes=100)

    def test_encode_voice_file_data_url_rejects_large_base64_payload(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.wav"
            sample.write_bytes(b"RIFF" + b"0" * 4 + b"WAVE" + b"0" * 20)

            with self.assertRaisesRegex(
                AudioValidationError, "Base64 audio payload too large"
            ):
                encode_voice_file_data_url(sample, max_bytes=100, max_base64_chars=40)

    def test_base64_limit_can_be_derived_from_byte_limit(self):
        self.assertEqual(estimate_base64_chars(10), 16)

    def test_sniff_audio_format_identifies_platform_voice_codecs(self):
        self.assertEqual(sniff_audio_format(b"RIFF\x00\x00\x00\x00WAVE"), "wav")
        self.assertEqual(sniff_audio_format(b"ID3\x04\x00\x00"), "mp3")
        self.assertEqual(sniff_audio_format(b"\xff\xfb\x90\x00"), "mp3")
        self.assertEqual(sniff_audio_format(b"\x02#!SILK_V3"), "silk")
        self.assertEqual(sniff_audio_format(b"#!AMR\n"), "amr")
        self.assertEqual(sniff_audio_format(b"OggS\x00\x02"), "ogg")
        self.assertEqual(sniff_audio_format(b"fLaC\x00\x00"), "flac")
        self.assertEqual(sniff_audio_format(b"\x00\x00\x00 ftypM4A "), "m4a")
        self.assertEqual(sniff_audio_format(b""), "unknown")

    def test_silk_voice_renamed_to_wav_reports_real_format(self):
        """QQ 语音（silk）被命名成 .wav 时，错误应指出真实格式而非只说损坏。"""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.wav"
            sample.write_bytes(b"\x02#!SILK_V3" + b"0" * 20)

            with self.assertRaisesRegex(AudioValidationError, "looks like silk"):
                encode_voice_file_data_url(sample, max_bytes=1024)

    def test_unrecognised_content_named_mp3_is_reported_clearly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.mp3"
            sample.write_bytes(b"not really an mp3")

            with self.assertRaisesRegex(
                AudioValidationError, "content not recognised"
            ):
                encode_voice_file_data_url(sample, max_bytes=1024)

    def test_merge_wav_files_preserves_all_segment_frames(self):
        import tempfile
        import wave

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.wav"
            second = Path(temp_dir) / "second.wav"
            merged = Path(temp_dir) / "merged.wav"
            self._write_wav(first, b"\x00\x01\x02\x03")
            self._write_wav(second, b"\x04\x05\x06\x07")

            result = merge_wav_files([first, second], merged)

            self.assertEqual(result, merged)
            with wave.open(str(merged), "rb") as reader:
                self.assertEqual(
                    reader.readframes(reader.getnframes()),
                    b"\x00\x01\x02\x03\x04\x05\x06\x07",
                )

    def test_merge_wav_files_rejects_incompatible_segments(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.wav"
            second = Path(temp_dir) / "second.wav"
            merged = Path(temp_dir) / "merged.wav"
            self._write_wav(first, b"\x00\x01", frame_rate=16000)
            self._write_wav(second, b"\x02\x03", frame_rate=24000)

            with self.assertRaisesRegex(AudioMergeError, "incompatible"):
                merge_wav_files([first, second], merged)

            self.assertFalse(merged.exists())

    def test_inspect_pcm16_wav_returns_actual_metadata(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.wav"
            self._write_wav(sample, b"\x00\x01" * 240, frame_rate=24000)

            metadata = inspect_pcm16_wav(sample)

            self.assertEqual(metadata["sample_rate"], 24000)
            self.assertEqual(metadata["channels"], 1)
            self.assertEqual(metadata["sample_width"], 2)
            self.assertEqual(metadata["frame_count"], 240)
            self.assertEqual(metadata["duration_ms"], 10)

    def test_inspect_pcm16_wav_rejects_non_pcm16_and_truncated_frames(self):
        import tempfile
        import wave

        with tempfile.TemporaryDirectory() as temp_dir:
            eight_bit = Path(temp_dir) / "eight-bit.wav"
            with wave.open(str(eight_bit), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(1)
                writer.setframerate(16000)
                writer.writeframes(b"\x00" * 8)
            with self.assertRaisesRegex(PCMOutputValidationError, "16-bit"):
                inspect_pcm16_wav(eight_bit)

            truncated = Path(temp_dir) / "truncated.wav"
            self._write_wav(truncated, b"\x00\x01" * 8)
            truncated.write_bytes(truncated.read_bytes()[:-3])
            with self.assertRaisesRegex(PCMOutputValidationError, "truncated"):
                inspect_pcm16_wav(truncated)


class RepairStreamedWavHeaderTests(unittest.TestCase):
    """FishAudio 流式输出的 WAV 头是占位值，必须按实际大小回填。

    真实事故：合成产物头里 data size = 0xFFFFFF00、RIFF size = 0xFFFFFF24，
    解析出来时长是 48695 秒（约 13.5 小时），多段语音的第二段因此在
    发送阶段失败，用户只听得到第一段。
    """

    @staticmethod
    def _write_wav(path: Path, *, frames: int = 800) -> None:
        import wave as wave_module

        with wave_module.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * frames)

    def _poison_header(self, path: Path) -> None:
        """把长度字段改成流式占位值（模拟服务端未回填）。"""
        raw = bytearray(path.read_bytes())
        raw[4:8] = (0xFFFFFF24).to_bytes(4, "little")
        # 标准 44 字节头：data size 在偏移 40
        assert raw[36:40] == b"data"
        raw[40:44] = (0xFFFFFF00).to_bytes(4, "little")
        path.write_bytes(bytes(raw))

    def test_repairs_dashscope_placeholders_too(self):
        """上游 AstrBotDevs/AstrBot#10706 报的占位值是 0x7FFFFFFE / 0x7FFFFFDB。

        qq_official 转 SILK 时按头长度分配内存会抛 MemoryError，整条消息静默
        丢失。回填逻辑只认「实际字节数」，与占位值具体是多少无关，这里锁定
        它对 DashScope 的取值同样有效。
        """
        import tempfile
        import wave

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dashscope_tts.wav"
            self._write_wav(path, frames=2400)
            raw = bytearray(path.read_bytes())
            raw[4:8] = (0x7FFFFFFE).to_bytes(4, "little")
            raw[40:44] = (0x7FFFFFDB).to_bytes(4, "little")
            path.write_bytes(bytes(raw))

            self.assertTrue(repair_streamed_wav_header(path))
            with wave.open(str(path), "rb") as handle:
                self.assertEqual(handle.getnframes(), 2400)
            self.assertEqual(
                int.from_bytes(path.read_bytes()[40:44], "little"),
                path.stat().st_size - 44,
            )

    def test_repairs_placeholder_length_fields(self):
        import tempfile
        import wave as wave_module

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "poisoned.wav"
            self._write_wav(path)
            self._poison_header(path)

            with wave_module.open(str(path), "rb") as broken:
                # 占位值会解析成十几小时的时长
                self.assertGreater(broken.getnframes(), 16_000 * 3600)

            self.assertTrue(repair_streamed_wav_header(path))

            with wave_module.open(str(path), "rb") as fixed:
                self.assertEqual(fixed.getnframes(), 800)
                self.assertEqual(fixed.getframerate(), 16000)

    def test_is_idempotent_and_skips_healthy_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "healthy.wav"
            self._write_wav(path)
            self.assertFalse(repair_streamed_wav_header(path))
            size_before = path.stat().st_size
            self.assertFalse(repair_streamed_wav_header(path))
            self.assertEqual(path.stat().st_size, size_before)

    def test_ignores_non_wav_and_tiny_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            not_wav = Path(tmp) / "a.bin"
            not_wav.write_bytes(b"ID3\x03\x00" + b"\x00" * 200)
            self.assertFalse(repair_streamed_wav_header(not_wav))

            tiny = Path(tmp) / "tiny.wav"
            tiny.write_bytes(b"RIFF")
            self.assertFalse(repair_streamed_wav_header(tiny))

            missing = Path(tmp) / "missing.wav"
            self.assertFalse(repair_streamed_wav_header(missing))
