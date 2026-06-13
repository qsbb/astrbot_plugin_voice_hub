from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_mimo_tts_clone.core.voice_store import VoiceStore


class VoiceStoreTests(unittest.TestCase):
    def test_voice_store_adds_and_lists_voice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = VoiceStore(root)

            voice = store.add_voice(
                name="旁白女声",
                audio_path=root / "voice.wav",
                description="适合播报",
                created_by="admin",
                consent_confirmed=True,
            )

            self.assertEqual(voice.name, "旁白女声")
            self.assertTrue(voice.enabled)
            self.assertEqual(store.list_voices()[0].id, voice.id)

    def test_voice_store_resolves_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = VoiceStore(root)
            global_voice = store.add_voice("全局", root / "g.wav", "", "admin", True)
            group_voice = store.add_voice("群默认", root / "group.wav", "", "admin", True)
            user_voice = store.add_voice("用户默认", root / "user.wav", "", "admin", True)
            temp_voice = store.add_voice("临时", root / "temp.wav", "", "admin", True)
            store.set_global_default(global_voice.id)
            store.set_group_default("group-1", group_voice.id)
            store.set_user_default("user-1", user_voice.id)

            self.assertEqual(
                store.resolve_voice_id("临时", "user-1", "group-1"),
                temp_voice.id,
            )
            self.assertEqual(
                store.resolve_voice_id(None, "user-1", "group-1"),
                user_voice.id,
            )
            store.set_emotion_default("happy", temp_voice.id)
            self.assertEqual(
                store.resolve_voice_id(None, "user-1", "group-1", emotion="happy"),
                temp_voice.id,
            )
            store.set_emotion_default("happy", "")
            self.assertNotIn("happy", store.defaults()["emotion_defaults"])
            self.assertEqual(
                store.resolve_voice_id(None, "user-1", "group-1", emotion="happy"),
                user_voice.id,
            )
            self.assertEqual(
                store.resolve_voice_id(None, "user-2", "group-1"),
                group_voice.id,
            )
            self.assertEqual(
                store.resolve_voice_id(None, "user-2", "group-2"),
                global_voice.id,
            )

    def test_voice_store_ignores_disabled_voice_when_resolving(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = VoiceStore(root)
            voice = store.add_voice("禁用", root / "disabled.wav", "", "admin", True)
            store.update_voice(voice.id, enabled=False)
            store.set_global_default(voice.id)

            self.assertIsNone(store.resolve_voice_id(None, "user", "group"))
