from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.audio_codec import (
    AudioMergeError,
    AudioValidationError,
    encode_voice_file_data_url,
    estimate_base64_chars,
    merge_wav_files,
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
