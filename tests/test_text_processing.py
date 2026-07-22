from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.text_processing import (
    clean_tts_text,
    contains_url,
    replace_urls_for_tts,
    split_tts_text,
)


class TextProcessingTests(unittest.TestCase):
    def test_clean_tts_text_removes_urls_and_code_blocks(self):
        text = (
            "请看 https://example.com\n```python\nprint('x')\n```\n（开心）今天真棒！"
        )

        self.assertEqual(clean_tts_text(text), "请看 （开心）今天真棒！")

    def test_clean_tts_text_keeps_mimo_style_tags(self):
        text = "[whisper] 这里低声说。 (笑) 然后正常说。"

        self.assertEqual(
            clean_tts_text(text), "[whisper] 这里低声说。 (笑) 然后正常说。"
        )

    def test_split_tts_text_keeps_punctuation_and_limits_segments(self):
        parts = split_tts_text(
            "第一句很短。第二句也很短！第三句继续？第四句结束。",
            max_chars=8,
            max_segments=3,
        )

        self.assertEqual(
            parts, ["第一句很短。", "第二句也很短！", "第三句继续？第四句结束。"]
        )

    def test_contains_url_detects_http_and_www(self):
        self.assertTrue(contains_url("请看 https://example.com"))
        self.assertTrue(contains_url("访问 www.example.com 试试"))
        self.assertTrue(contains_url("http://foo.bar/baz"))

    def test_contains_url_returns_false_for_plain_text(self):
        self.assertFalse(contains_url("今天天气不错"))
        self.assertFalse(contains_url(""))
        self.assertFalse(contains_url(None))

    def test_replace_urls_for_tts_substitutes_placeholder(self):
        self.assertEqual(
            replace_urls_for_tts("请看 https://example.com 这个网页"),
            "请看 这个网址 这个网页",
        )
        self.assertEqual(
            replace_urls_for_tts("访问 www.foo.bar 试试"),
            "访问 这个网址 试试",
        )

    def test_replace_urls_for_tts_keeps_plain_text(self):
        self.assertEqual(replace_urls_for_tts("今天天气不错"), "今天天气不错")
        self.assertEqual(replace_urls_for_tts(""), "")
