import asyncio
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_mimo_tts_clone.core.style_director import (
    StyleDirectorInput,
    build_style_director_prompt,
    generate_style_directive,
    sanitize_style_director_output,
)


class _Response:
    completion_text = "风格指令：用贴近耳边的轻声、慢一点、带一点安慰感。"


class _Context:
    def __init__(self):
        self.calls = []

    async def llm_generate(self, **kwargs):
        self.calls.append(kwargs)
        return _Response()


class StyleDirectorTests(unittest.TestCase):
    def test_sanitizes_director_output(self):
        result = sanitize_style_director_output(
            '风格指令："用轻柔、克制、带一点笑意的语气朗读。"',
            max_chars=12,
        )

        self.assertEqual(result, "用轻柔、克制、带一点笑意")

    def test_build_prompt_keeps_text_as_context_not_output(self):
        system_prompt, user_prompt = build_style_director_prompt(
            StyleDirectorInput(
                text="今晚月亮很好。",
                emotion="happy",
                voice_name="旁白",
                max_chars=80,
            )
        )

        self.assertIn("不会被读出", system_prompt)
        self.assertIn("待朗读文本：今晚月亮很好。", user_prompt)
        self.assertIn("请输出最终风格控制指令", user_prompt)

    def test_generate_style_directive_uses_llm_generate(self):
        context = _Context()

        result = asyncio.run(
            generate_style_directive(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
            )
        )

        self.assertEqual(result, "用贴近耳边的轻声、慢一点、带一点安慰感。")
        self.assertEqual(context.calls[0]["prompt"].count("晚上好"), 1)


if __name__ == "__main__":
    unittest.main()
