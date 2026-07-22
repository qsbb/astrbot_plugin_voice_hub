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
        self.assertEqual(schema["auto_tts_probability"]["default"], "0.0")
