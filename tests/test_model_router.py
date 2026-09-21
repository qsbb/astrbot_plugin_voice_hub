import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.model_router import (
    resolve_model_route,
    resolve_provider_id,
)


CONTRACT = {
    "name": "series.model_router@1.0",
    "version": "1.0",
    "read_only": True,
    "capabilities": ("resolve", "status"),
}

# 核把契约 version 从 1.0 升到 1.1（name 不变），主版本比较仍应接受。
CONTRACT_1_1 = {**CONTRACT, "version": "1.1"}


class _Router:
    def __init__(self, route, contract=None):
        self.route = route
        self.contract = contract if contract is not None else CONTRACT
        self.kinds = []

    def series_model_router_contract(self):
        return self.contract

    def resolve_model_route(self, kind, **_kwargs):
        self.kinds.append(kind)
        return {**self.route, "kind": kind}


class _Context:
    def __init__(self, router, providers=()):
        self.router = router
        self.providers = set(providers)

    def get_star_instance(self, plugin_name):
        return self.router if plugin_name == "astrbot_plugin_update_manager" else None

    def get_provider_by_id(self, provider_id):
        return object() if provider_id in self.providers else None


class _OfficialOnlyContext:
    """只实现 AstrBot 官方 API 的 Context：没有 get_star_instance。"""

    def __init__(self, metadata=None, providers=()):
        self.metadata = metadata
        self.providers = set(providers)
        self.lookups = []

    def get_registered_star(self, plugin_name):
        self.lookups.append(plugin_name)
        return self.metadata

    def get_provider_by_id(self, provider_id):
        return object() if provider_id in self.providers else None


def _core_route(**overrides):
    route = {"source": "core", "available": True, "provider_id": "core-chat"}
    route.update(overrides)
    return route


class ModelRouterTests(unittest.TestCase):
    def test_accepts_compatible_core_route(self):
        context = _Context(
            _Router({"source": "core", "provider_id": "core-chat", "available": True}),
            providers=("core-chat",),
        )
        self.assertEqual(asyncio.run(resolve_provider_id(context, "conversation")), "core-chat")

    def test_rejects_astrbot_fallback_route(self):
        context = _Context(
            _Router({"source": "astrbot", "provider_id": "native", "available": True}),
            providers=("native",),
        )
        self.assertEqual(asyncio.run(resolve_provider_id(context, "tts")), "")

    def test_rejects_incompatible_contract_and_stale_provider(self):
        bad_contract = {**CONTRACT, "name": "series.other@1.0"}
        context = _Context(
            _Router({"source": "core", "provider_id": "missing", "available": True}, bad_contract),
            providers=(),
        )
        self.assertEqual(asyncio.run(resolve_provider_id(context, "tts")), "")

    def test_accepts_legacy_resolver_signature(self):
        class LegacyRouter(_Router):
            def resolve_model_route(self, kind):
                return {"kind": kind, "source": "core", "provider_id": "core-tts", "available": True}

        context = _Context(LegacyRouter({}), providers=("core-tts",))
        self.assertEqual(asyncio.run(resolve_provider_id(context, "tts")), "core-tts")


class ModelRouteTests(unittest.TestCase):
    def test_returns_full_core_route_for_1_1_contract(self):
        router = _Router(
            _core_route(
                provider_id="core-fast",
                model="fast-mini",
                voice="旁白",
                fallback_from="plugin",
            ),
            CONTRACT_1_1,
        )
        context = _Context(router, providers=("core-fast",))

        route = asyncio.run(resolve_model_route(context, "fast"))

        self.assertEqual(
            route,
            {
                "provider_id": "core-fast",
                "model": "fast-mini",
                "voice": "旁白",
                "source": "core",
                "available": True,
                "fallback_from": "plugin",
            },
        )
        self.assertEqual(router.kinds, ["fast"])

    def test_returns_empty_route_when_core_omits_optional_fields(self):
        context = _Context(_Router(_core_route()), providers=("core-chat",))

        route = asyncio.run(resolve_model_route(context, "conversation"))

        self.assertEqual(
            route,
            {
                "provider_id": "core-chat",
                "model": "",
                "voice": "",
                "source": "core",
                "available": True,
                "fallback_from": "",
            },
        )

    def test_ignores_non_string_model_and_voice_fields(self):
        context = _Context(
            _Router(_core_route(model={"name": "m"}, voice=["v"])),
            providers=("core-chat",),
        )

        route = asyncio.run(resolve_model_route(context, "tts"))

        self.assertEqual(route["model"], "")
        self.assertEqual(route["voice"], "")

    def test_rejects_incompatible_contract(self):
        bad_contracts = {
            "other name": {**CONTRACT, "name": "series.other@1.0"},
            "other major version": {**CONTRACT, "version": "2.0"},
            "not read only": {**CONTRACT, "read_only": False},
            "missing resolve capability": {**CONTRACT, "capabilities": ("status",)},
            "capabilities not a list": {**CONTRACT, "capabilities": "resolve"},
        }
        for label, contract in bad_contracts.items():
            with self.subTest(label=label):
                context = _Context(_Router(_core_route(), contract), providers=("core-chat",))
                self.assertEqual(asyncio.run(resolve_model_route(context, "conversation")), {})

    def test_rejects_non_core_source(self):
        for source in ("plugin", "astrbot", "unavailable", ""):
            with self.subTest(source=source):
                context = _Context(
                    _Router(_core_route(source=source)), providers=("core-chat",)
                )
                self.assertEqual(asyncio.run(resolve_model_route(context, "conversation")), {})

    def test_rejects_unavailable_route(self):
        for available in (False, "true", None, 1):
            with self.subTest(available=available):
                context = _Context(
                    _Router(_core_route(available=available)), providers=("core-chat",)
                )
                self.assertEqual(asyncio.run(resolve_model_route(context, "conversation")), {})

    def test_rejects_kind_mismatch(self):
        class WrongKindRouter(_Router):
            def resolve_model_route(self, kind, **_kwargs):
                return {**self.route, "kind": "tts"}

        context = _Context(WrongKindRouter(_core_route()), providers=("core-chat",))

        self.assertEqual(asyncio.run(resolve_model_route(context, "fast")), {})

    def test_rejects_blank_and_stale_routes(self):
        context = _Context(_Router(_core_route()), providers=("core-chat",))

        self.assertEqual(asyncio.run(resolve_model_route(context, "")), {})
        self.assertEqual(asyncio.run(resolve_model_route(context, "   ")), {})
        self.assertEqual(asyncio.run(resolve_model_route(context, None)), {})
        stale_context = _Context(_Router(_core_route(provider_id="missing")), providers=())
        self.assertEqual(asyncio.run(resolve_model_route(stale_context, "fast")), {})

    def test_returns_empty_route_when_core_rejects_kind(self):
        class RejectingRouter(_Router):
            def resolve_model_route(self, kind, **_kwargs):
                if kind not in {"fast", "tts"}:
                    raise ValueError("UNKNOWN_MODEL_KIND")
                return {**self.route, "kind": kind}

        context = _Context(RejectingRouter(_core_route()), providers=("core-chat",))

        self.assertEqual(asyncio.run(resolve_model_route(context, "chat")), {})
        self.assertEqual(asyncio.run(resolve_provider_id(context, "chat")), "")
        self.assertEqual(
            asyncio.run(resolve_model_route(context, "fast"))["provider_id"], "core-chat"
        )

    def test_rejects_missing_router_and_broken_resolver(self):
        class RaisingRouter(_Router):
            def resolve_model_route(self, kind, **_kwargs):
                raise RuntimeError("router failed")

        class NonDictRouter(_Router):
            def resolve_model_route(self, kind, **_kwargs):
                return ["not", "a", "dict"]

        without_router = _Context(None, providers=("core-chat",))
        self.assertEqual(asyncio.run(resolve_model_route(without_router, "fast")), {})
        self.assertEqual(
            asyncio.run(resolve_model_route(_Context(RaisingRouter({}), ("core-chat",)), "fast")),
            {},
        )
        self.assertEqual(
            asyncio.run(resolve_model_route(_Context(NonDictRouter({}), ("core-chat",)), "fast")),
            {},
        )

    def test_supports_async_resolver_and_legacy_signature(self):
        class AsyncRouter(_Router):
            async def resolve_model_route(self, kind, **_kwargs):
                return {**self.route, "kind": kind}

        class LegacyRouter(_Router):
            def resolve_model_route(self, kind):
                return {**self.route, "kind": kind}

        async_context = _Context(AsyncRouter(_core_route(model="m1")), providers=("core-chat",))
        legacy_context = _Context(LegacyRouter(_core_route(model="m2")), providers=("core-chat",))

        self.assertEqual(
            asyncio.run(resolve_model_route(async_context, "fast"))["model"], "m1"
        )
        self.assertEqual(
            asyncio.run(resolve_model_route(legacy_context, "fast"))["model"], "m2"
        )

    def test_provider_id_resolution_matches_route_resolution(self):
        context = _Context(_Router(_core_route(provider_id="core-chat")), providers=("core-chat",))

        async def run():
            return (
                await resolve_provider_id(context, "conversation"),
                await resolve_model_route(context, "conversation"),
            )

        provider_id, route = asyncio.run(run())
        self.assertEqual(provider_id, route["provider_id"])


class RouterInstanceResolutionTests(unittest.TestCase):
    """核实例解析：get_star_instance 优先，官方 get_registered_star 兜底。"""

    def test_resolves_core_instance_from_official_registry(self):
        router = _Router(_core_route(model="core-model"))
        context = _OfficialOnlyContext(
            SimpleNamespace(star_cls=router), providers=("core-chat",)
        )

        self.assertEqual(
            asyncio.run(resolve_provider_id(context, "conversation")), "core-chat"
        )
        self.assertEqual(
            asyncio.run(resolve_model_route(context, "fast"))["model"], "core-model"
        )
        self.assertEqual(
            context.lookups,
            ["astrbot_plugin_update_manager", "astrbot_plugin_update_manager"],
        )

    def test_prefers_get_star_instance_over_official_registry(self):
        preferred = _Router(_core_route(provider_id="core-preferred"))
        registry_router = _Router(_core_route(provider_id="core-registry"))
        context = _Context(preferred, providers=("core-preferred", "core-registry"))
        context.get_registered_star = lambda _name: SimpleNamespace(
            star_cls=registry_router
        )

        route = asyncio.run(resolve_model_route(context, "fast"))

        self.assertEqual(route["provider_id"], "core-preferred")
        self.assertEqual(preferred.kinds, ["fast"])
        self.assertEqual(registry_router.kinds, [])

    def test_reads_legacy_metadata_attributes(self):
        for attribute in ("star", "instance", "star_instance", "plugin"):
            with self.subTest(attribute=attribute):
                router = _Router(_core_route())
                context = _OfficialOnlyContext(
                    SimpleNamespace(**{attribute: router}), providers=("core-chat",)
                )
                self.assertEqual(
                    asyncio.run(resolve_provider_id(context, "conversation")),
                    "core-chat",
                )

    def test_skips_class_attribute_and_keeps_looking(self):
        """star_cls 是 class 时跳过，继续用后面真正的实例属性。"""

        class _CoreClass:
            @staticmethod
            def series_model_router_contract():
                return CONTRACT

        router = _Router(_core_route())
        context = _OfficialOnlyContext(
            SimpleNamespace(star_cls=_CoreClass, star=router),
            providers=("core-chat",),
        )

        self.assertEqual(
            asyncio.run(resolve_provider_id(context, "conversation")), "core-chat"
        )

    def test_official_registry_failures_are_fail_closed(self):
        class _RaisingRegistry(_OfficialOnlyContext):
            def get_registered_star(self, plugin_name):
                raise RuntimeError("star registry unavailable")

        class _CoreClass:
            @staticmethod
            def series_model_router_contract():
                return CONTRACT

        class _DeclareRaisesClass:
            @staticmethod
            def series_model_router_contract():
                raise RuntimeError("contract unavailable")

        contexts = {
            "registry returns None": _OfficialOnlyContext(None),
            "registry raises": _RaisingRegistry(),
            "star_cls is a class": _OfficialOnlyContext(SimpleNamespace(star_cls=_CoreClass)),
            "all attributes are classes": _OfficialOnlyContext(
                SimpleNamespace(
                    star_cls=_DeclareRaisesClass,
                    star=_DeclareRaisesClass,
                    instance=_DeclareRaisesClass,
                    star_instance=_DeclareRaisesClass,
                    plugin=_DeclareRaisesClass,
                )
            ),
            "no instance attributes": _OfficialOnlyContext(SimpleNamespace()),
        }
        for label, context in contexts.items():
            with self.subTest(label=label):
                self.assertEqual(
                    asyncio.run(resolve_provider_id(context, "conversation")), ""
                )
                self.assertEqual(
                    asyncio.run(resolve_model_route(context, "conversation")), {}
                )

    def test_accepts_awaitable_lookups(self):
        class _AsyncContext:
            def __init__(self, router, metadata):
                self.router = router
                self.metadata = metadata

            async def get_star_instance(self, _plugin_name):
                return self.router

            async def get_registered_star(self, _plugin_name):
                return self.metadata

            def get_provider_by_id(self, provider_id):
                return object() if provider_id == "core-chat" else None

        router = _Router(_core_route())
        context = _AsyncContext(router, SimpleNamespace(star_cls=None))

        self.assertEqual(
            asyncio.run(resolve_provider_id(context, "conversation")), "core-chat"
        )

        metadata_only = _AsyncContext(None, SimpleNamespace(star=router))
        self.assertEqual(
            asyncio.run(resolve_provider_id(metadata_only, "conversation")), "core-chat"
        )

    def test_survives_broken_context_attributes(self):
        class _BrokenContext:
            @property
            def get_star_instance(self):
                raise RuntimeError("attribute exploded")

            @property
            def get_registered_star(self):
                raise RuntimeError("attribute exploded")

            def get_provider_by_id(self, _provider_id):
                return object()

        self.assertEqual(
            asyncio.run(resolve_provider_id(_BrokenContext(), "conversation")), ""
        )


if __name__ == "__main__":
    unittest.main()
