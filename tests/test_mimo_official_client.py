from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_mimo_tts_clone.core.mimo_official_client import (
    MimoOfficialClient,
    MimoTTSConfig,
)


class MimoOfficialClientTests(unittest.TestCase):
    def test_build_payload_uses_assistant_text_and_voice_data_url(self):
        client = MimoOfficialClient(MimoTTSConfig(api_key="token"))

        payload = client.build_payload(
            text="今天也要好好吃饭。",
            voice_data_url="data:audio/wav;base64,AAAA",
            context="温柔、自然地朗读",
        )

        self.assertEqual(payload["model"], "mimo-v2.5-tts-voiceclone")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "user", "content": "温柔、自然地朗读"},
                {"role": "assistant", "content": "今天也要好好吃饭。"},
            ],
        )
        self.assertEqual(
            payload["audio"],
            {
                "format": "wav",
                "voice": "data:audio/wav;base64,AAAA",
            },
        )


    def test_build_payload_omits_empty_context(self):
        client = MimoOfficialClient(MimoTTSConfig(api_key="token"))

        payload = client.build_payload(
            text="测试",
            voice_data_url="data:audio/mpeg;base64,AAAA",
            context="",
        )

        self.assertEqual(payload["messages"], [{"role": "assistant", "content": "测试"}])
