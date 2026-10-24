# -*- coding: utf-8 -*-
"""FishAudio client + expression layer unit tests (no network access)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.fishaudio_client import (
    FishAudioClient,
    FishAudioError,
    is_valid_reference_id,
)
from astrbot_plugin_voice_hub.core.fishaudio_expression import (
    apply_emotion_control,
    canonical_cue,
    context_emotion_cues,
    normalize_cues,
    normalize_s1_cues,
    normalize_s2_cues,
)


def _fake_msgpack_module():
    import types

    module = types.ModuleType("ormsgpack")

    class _FakeBytes(bytes):
        pass

    def packb(payload, option=None):
        import json

        return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    module.packb = packb
    return module


class FishAudioClientPayloadTests(unittest.TestCase):
    def test_headers_put_model_in_http_header_not_body(self):
        client = FishAudioClient(
            api_key="fish-key",
            api_base="https://api.fish.audio/v1",
            model="s2.1-pro",
        )
        headers = client._headers()
        self.assertEqual(headers["Authorization"], "Bearer fish-key")
        self.assertEqual(headers["Content-Type"], "application/msgpack")
        self.assertEqual(headers["model"], "s2.1-pro")

    def test_selfhosted_auto_model_sends_no_model_header(self):
        client = FishAudioClient(
            api_key="fish-key",
            api_base="http://127.0.0.1:8080/v1",
            model="",
        )
        self.assertNotIn("model", client._headers())

    def test_request_payload_uses_reference_id_and_format(self):
        payload = FishAudioClient._request_payload(
            "你好呀", reference_id="a" * 32, output_format="wav"
        )
        self.assertEqual(payload["text"], "你好呀")
        self.assertEqual(payload["format"], "wav")
        self.assertEqual(payload["reference_id"], "a" * 32)
        self.assertTrue(payload["normalize"])
        self.assertNotIn("model", payload)

    def test_invalid_reference_id_is_rejected(self):
        self.assertTrue(is_valid_reference_id("626bb6d3f3364c9cbc3aa6a67300a664"))
        self.assertFalse(is_valid_reference_id("not-an-id"))
        client = FishAudioClient(api_key="k", reference_id="bad-id")
        import asyncio

        with self.assertRaises(FishAudioError):
            asyncio.run(
                client.synthesize_to_file("text", output_path="/tmp/never.wav")
            )

    def test_missing_api_key_is_rejected(self):
        client = FishAudioClient(api_key="")
        import asyncio

        with self.assertRaises(FishAudioError):
            asyncio.run(
                client.synthesize_to_file("text", output_path="/tmp/never.wav")
            )

    def test_inline_reference_audio_overrides_reference_id(self):
        payload = FishAudioClient._request_payload(
            "你好", reference_id="a" * 32, output_format="wav"
        )
        payload["references"] = [{"audio": b"RIFF", "text": "转写"}]
        payload.pop("reference_id", None)
        self.assertNotIn("reference_id", payload)
        self.assertEqual(payload["references"][0]["text"], "转写")

    def test_official_api_base_detection(self):
        self.assertTrue(
            FishAudioClient._is_official_api("https://api.fish-audio.cn/v1")
        )
        self.assertTrue(FishAudioClient._is_official_api("https://api.fish.audio/v1"))
        self.assertFalse(FishAudioClient._is_official_api("http://127.0.0.1:8080/v1"))


class FishAudioExpressionTests(unittest.TestCase):
    def test_s2_keeps_canonical_cues_and_drops_metadata(self):
        self.assertEqual(
            normalize_s2_cues("好耶！[兴奋]冲呀。"),
            "好耶！[兴奋]冲呀。",
        )
        # 超长元数据标签被移除
        long_tag = "[" + "x" * 60 + "]"
        self.assertNotIn(long_tag, normalize_s2_cues(f"好耶！{long_tag}"))

    def test_s2_auto_mode_drops_high_impact_breath_effects(self):
        self.assertNotIn("[panting]", normalize_s2_cues("[panting]你好呀。"))
        self.assertNotIn("[groaning]", normalize_s2_cues("[groaning]好痛。"))

    def test_s2_sigh_requires_explicit_action(self):
        self.assertNotIn("[sighing]", normalize_s2_cues("[sighing]嗯……好吧。"))
        self.assertIn("[sighing]", normalize_s2_cues("[sighing]轻轻叹了口气。"))

    def test_s2_limits_cues_per_sentence_and_removes_stacking(self):
        stacked = "[开心][兴奋]太棒了！"
        normalized = normalize_s2_cues(stacked)
        self.assertIn("[开心]", normalized)
        self.assertNotIn("[兴奋]", normalized)

    def test_s1_converts_aliases_and_drops_unknown(self):
        self.assertEqual(normalize_s1_cues("(开心)你好。"), "(joyful)你好。")
        self.assertEqual(normalize_s1_cues("(非官方标签)你好。"), "你好。")
        # S2 方括号写法在 S1 下统一转为圆括号
        self.assertEqual(normalize_s1_cues("[happy]你好。"), "(joyful)你好。")

    def test_manual_mode_keeps_existing_breath_cues(self):
        self.assertEqual(
            normalize_s2_cues("[panting]你好呀。", mode="manual"),
            "[panting]你好呀。",
        )

    def test_canonical_cue_s2_keeps_cjk(self):
        self.assertEqual(canonical_cue("くすくす笑い", s1=False), "くすくす笑い")
        self.assertEqual(canonical_cue("HAPPY", s1=False), "happy")

    def test_context_emotion_cues_prefers_tone_over_primary(self):
        self.assertEqual(
            context_emotion_cues("晚安，做个好梦。", mode="balanced"),
            ["soft tone"],
        )
        self.assertEqual(
            context_emotion_cues("你个大笨蛋！哼！", mode="balanced"),
            ["upset"],
        )
        self.assertEqual(context_emotion_cues("今天天气不错。", mode="balanced"), [])

    def test_apply_emotion_control_keeps_existing_valid_cues(self):
        spoken, applied = apply_emotion_control(
            "[开心]今天也一起加油哦。",
            s1=False,
            mode="balanced",
            source_text="",
        )
        self.assertEqual(spoken, "[开心]今天也一起加油哦。")
        self.assertEqual(applied, [])

    def test_apply_emotion_control_adds_prefix_from_context(self):
        spoken, applied = apply_emotion_control(
            "太棒了，好期待！",
            s1=False,
            mode="balanced",
            source_text="",
        )
        self.assertEqual(spoken, "[excited]太棒了，好期待！")
        self.assertEqual(applied, ["excited"])

    def test_apply_emotion_control_maps_explicit_emotion(self):
        spoken, applied = apply_emotion_control(
            "今天也要好好吃饭。",
            s1=False,
            mode="balanced",
            source_text="",
            emotion="happy",
        )
        self.assertEqual(spoken, "[happy]今天也要好好吃饭。")
        self.assertEqual(applied, ["happy"])

    def test_apply_emotion_control_s1_uses_parentheses(self):
        spoken, applied = apply_emotion_control(
            "谢谢你陪着我。",
            s1=True,
            mode="balanced",
            source_text="",
        )
        self.assertEqual(spoken, "(grateful)谢谢你陪着我。")
        self.assertEqual(applied, ["grateful"])

    def test_apply_emotion_control_manual_never_infers(self):
        spoken, applied = apply_emotion_control(
            "太棒了，好期待！",
            s1=False,
            mode="manual",
            source_text="",
        )
        self.assertEqual(spoken, "太棒了，好期待！")
        self.assertEqual(applied, [])

    def test_normalize_cues_dispatch(self):
        self.assertEqual(
            normalize_cues("(开心)你好。", s1=True, mode="balanced"),
            "(joyful)你好。",
        )
        # S2 官方接受朗读语言的自然语言控制：中日文标签原样保留
        self.assertEqual(
            normalize_cues("[开心]你好。", s1=False, mode="balanced"),
            "[开心]你好。",
        )
        self.assertEqual(
            normalize_cues("[happy]你好。", s1=False, mode="balanced"),
            "[happy]你好。",
        )


class HijackedResponseTests(unittest.TestCase):
    """上游场景：NAS 直连被 DNS 污染/劫持时 200 返回 HTML 网页而不是音频。"""

    def test_html_response_raises_guidance_error(self):
        import asyncio
        import sys
        import types
        from astrbot_plugin_voice_hub.core import fishaudio_client as fc

        class _FakeResponse:
            status_code = 200
            headers = {"content-type": "text/html"}

            def __init__(self):
                self._sent = False

            async def aiter_bytes(self):
                self._sent = True
                yield b"<!doctype html><html lang=\"en\">..."

            async def aread(self):
                return b"<!doctype html><html lang=\"en\">..."

        class _FakeStreamCtx:
            async def __aenter__(self):
                return _FakeResponse()

            async def __aexit__(self, *args):
                return False

        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def stream(self, method, path, *, headers, content):
                return _FakeStreamCtx()

        fake_httpx = types.ModuleType("httpx")
        fake_httpx.AsyncClient = _FakeAsyncClient
        fake_orm = types.ModuleType("ormsgpack")
        fake_orm.packb = lambda payload, option=None: b"msgpack-bytes"

        saved = {name: sys.modules.get(name) for name in ("httpx", "ormsgpack")}
        sys.modules["httpx"] = fake_httpx
        sys.modules["ormsgpack"] = fake_orm
        try:
            client = fc.FishAudioClient(
                api_key="k",
                api_base="https://api.fish.audio/v1",
                reference_id="a" * 32,
            )
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(FishAudioError) as caught:
                    asyncio.run(client.synthesize_to_file("text", output_path=f"{tmp}/out.wav"))
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        self.assertIn("HTML 网页", str(caught.exception))
        self.assertIn("代理", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
