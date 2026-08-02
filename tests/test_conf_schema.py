import json
from pathlib import Path
import unittest


class ConfigSchemaTests(unittest.TestCase):
    def test_list_and_object_fields_define_items(self):
        schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        missing = [
            key
            for key, value in schema.items()
            if value.get("type") in {"list", "object"} and "items" not in value
        ]

        self.assertEqual(missing, [])

    def test_tts_defaults(self):
        schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["reply_mode"]["default"], "audio_only")
        self.assertTrue(schema["auto_tts_enabled"]["default"])
        self.assertIn(
            "由 tts_trigger_mode 自动同步", schema["auto_tts_enabled"]["hint"]
        )
        self.assertEqual(schema["tts_trigger_mode"]["default"], "probability")
        self.assertEqual(
            schema["tts_trigger_mode"]["options"],
            ["probability", "llm_decides"],
        )
        self.assertEqual(schema["auto_tts_probability"]["type"], "float")
        self.assertEqual(schema["auto_tts_probability"]["default"], 0.0)
        self.assertFalse(schema["llm_tts_judge_enabled"]["default"])
        self.assertEqual(schema["llm_tts_judge_enabled"]["type"], "bool")
        self.assertEqual(schema["api_server_host"]["default"], "127.0.0.1")
        self.assertEqual(schema["api_server_token"]["default"], "")
        self.assertTrue(schema["api_key"]["secret"])
        self.assertTrue(schema["api_server_token"]["secret"])
        self.assertEqual(schema["api_server_rate_limit_per_minute"]["default"], 30)
        self.assertEqual(schema["api_server_max_input_chars"]["default"], 500)

    def test_backend_is_primary_and_provider_fields_are_scoped(self):
        schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(next(iter(schema)), "tts_backend")
        self.assertEqual(schema["tts_backend"]["options"], ["mimo", "astrbot"])
        self.assertIn("仅 AstrBot 后端", schema["astrbot_tts_provider_id"]["description"])
        for key in (
            "api_key",
            "base_url",
            "model",
            "output_format",
            "default_context",
            "emotion_routing_enabled",
            "max_text_chars",
            "max_voice_file_mb",
            "max_concurrency",
        ):
            self.assertIn("仅 MiMo 后端", schema[key]["description"])
