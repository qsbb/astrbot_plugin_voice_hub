from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_mimo_tts_clone.core.audio_codec import (
    AudioValidationError,
    encode_voice_file_data_url,
)


class AudioCodecTests(unittest.TestCase):
    def test_encode_voice_file_data_url_accepts_mp3(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.mp3"
            sample.write_bytes(b"mp3-data")

            data_url = encode_voice_file_data_url(sample, max_bytes=100)

        self.assertEqual(data_url, "data:audio/mpeg;base64,bXAzLWRhdGE=")

    def test_encode_voice_file_data_url_rejects_unsupported_format(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.ogg"
            sample.write_bytes(b"ogg-data")

            with self.assertRaisesRegex(AudioValidationError, "Unsupported audio format"):
                encode_voice_file_data_url(sample, max_bytes=100)

    def test_encode_voice_file_data_url_rejects_large_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "voice.wav"
            sample.write_bytes(b"0" * 101)

            with self.assertRaisesRegex(AudioValidationError, "Voice file too large"):
                encode_voice_file_data_url(sample, max_bytes=100)
