import asyncio
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.style_director import (
    StyleDirectorInput,
    build_style_director_prompt,
    generate_style_directive,
    generate_style_plan,
    parse_style_director_plan,
    sanitize_style_director_output,
)


class _Response:
    completion_text = '{"style_context":"用贴近耳边的轻声、慢一点、带一点安慰感。","speech_text":"晚上好，欢迎回来。"}'


class _Provider:
    def __init__(self):
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return _Response()


class _LegacyProvider:
    """模拟老版本 provider：text_chat 不接受 model 参数。"""

    def __init__(self):
        self.calls = []

    async def text_chat(self, *, prompt, context, system_prompt, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "context": context,
                "system_prompt": system_prompt,
                "extra": dict(kwargs),
            }
        )
        if kwargs:
            raise TypeError("unexpected keyword argument 'model'")
        return _Response()


ROUTER_CONTRACT = {
    "name": "series.model_router@1.0",
    "version": "1.1",
    "read_only": True,
    "capabilities": ("resolve", "status"),
}


class _Router:
    def __init__(self, route):
        self.route = route
        self.kinds = []

    def series_model_router_contract(self):
        return ROUTER_CONTRACT

    def resolve_model_route(self, kind, **_kwargs):
        self.kinds.append(kind)
        return {**self.route, "kind": kind}


class _Context:
    def __init__(self, provider=None, router=None):
        self.calls = []
        self.provider = provider or _Provider()
        self.router = router

    async def llm_generate(self, **kwargs):
        self.calls.append(kwargs)
        return _Response()

    def get_provider_by_id(self, provider_id=None):
        return self.provider if provider_id == "director-provider" else None

    def get_star_instance(self, plugin_name):
        if plugin_name != "astrbot_plugin_update_manager":
            return None
        return self.router


class _DefaultProviderContext(_Context):
    def get_using_provider(self, umo=None):
        return self.provider


def _core_route(**overrides):
    route = {"source": "core", "available": True, "provider_id": "director-provider"}
    route.update(overrides)
    return route


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

        self.assertIn("不会展示给用户", system_prompt)
        self.assertIn("待朗读文本：今晚月亮很好。", user_prompt)
        self.assertIn("请输出最终 JSON", user_prompt)

    def test_parses_json_director_plan(self):
        result = parse_style_director_plan(
            '{"style_context":"自然一点，像真人聊天。","speech_text":"嗯，晚上好。"}',
            max_chars=80,
            max_speech_chars=80,
        )

        self.assertEqual(result.style_context, "自然一点，像真人聊天。")
        self.assertEqual(result.speech_text, "嗯，晚上好。")

    def test_generate_style_plan_uses_specific_provider(self):
        context = _Context()

        result = asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                provider_id="director-provider",
            )
        )

        self.assertEqual(
            result.style_context, "用贴近耳边的轻声、慢一点、带一点安慰感。"
        )
        self.assertEqual(result.speech_text, "晚上好，欢迎回来。")
        self.assertEqual(len(context.calls), 0)
        self.assertEqual(len(context.provider.calls), 1)

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

    def test_generate_style_plan_uses_default_provider_when_available(self):
        context = _DefaultProviderContext()

        result = asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
            )
        )

        self.assertEqual(result.speech_text, "晚上好，欢迎回来。")
        self.assertEqual(len(context.calls), 0)
        self.assertEqual(len(context.provider.calls), 1)


class StyleDirectorModelTests(unittest.TestCase):
    def test_forwards_explicit_model_to_text_chat(self):
        context = _Context()

        asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                provider_id="director-provider",
                model="fast-mini",
            )
        )

        self.assertEqual(len(context.provider.calls), 1)
        self.assertEqual(context.provider.calls[0]["model"], "fast-mini")

    def test_omits_model_when_not_configured(self):
        context = _Context()

        asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                provider_id="director-provider",
            )
        )

        self.assertNotIn("model", context.provider.calls[0])

    def test_local_provider_does_not_take_core_model(self):
        router = _Router(_core_route(model="core-fast-model"))
        context = _Context(router=router)

        result = asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                provider_id="director-provider",
            )
        )

        self.assertEqual(result.speech_text, "晚上好，欢迎回来。")
        self.assertEqual(router.kinds, [])
        self.assertNotIn("model", context.provider.calls[0])

    def test_consumes_core_route_model_without_local_provider(self):
        router = _Router(_core_route(model="core-fast-model"))
        context = _Context(router=router)

        result = asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
            )
        )

        self.assertEqual(router.kinds, ["fast"])
        self.assertEqual(result.style_context, "用贴近耳边的轻声、慢一点、带一点安慰感。")
        self.assertEqual(context.provider.calls[0]["model"], "core-fast-model")

    def test_unavailable_core_route_falls_back_to_llm_generate(self):
        router = _Router(_core_route(available=False))
        context = _Context(router=router)

        result = asyncio.run(
            generate_style_directive(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
            )
        )

        self.assertEqual(result, "用贴近耳边的轻声、慢一点、带一点安慰感。")
        self.assertEqual(context.provider.calls, [])
        self.assertEqual(len(context.calls), 1)

    def test_type_error_falls_back_to_text_chat_without_model(self):
        provider = _LegacyProvider()
        context = _Context(provider=provider)

        result = asyncio.run(
            generate_style_plan(
                context,
                StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                provider_id="director-provider",
                model="fast-mini",
            )
        )

        self.assertEqual(result.speech_text, "晚上好，欢迎回来。")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[0]["extra"], {"model": "fast-mini"})
        self.assertEqual(provider.calls[1]["extra"], {})
        self.assertEqual(provider.calls[0]["prompt"], provider.calls[1]["prompt"])

    def test_type_error_still_propagates_without_model(self):
        class _BrokenProvider:
            async def text_chat(self, **kwargs):
                raise TypeError("provider bug")

        context = _Context(provider=_BrokenProvider())

        with self.assertRaisesRegex(TypeError, "provider bug"):
            asyncio.run(
                generate_style_plan(
                    context,
                    StyleDirectorInput(text="晚上好", emotion="neutral", max_chars=80),
                    provider_id="director-provider",
                    model="fast-mini",
                )
            )


if __name__ == "__main__":
    unittest.main()
