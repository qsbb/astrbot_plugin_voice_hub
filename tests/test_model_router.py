import asyncio
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_voice_hub.core.model_router import resolve_provider_id


CONTRACT = {
    "name": "series.model_router@1.0",
    "version": "1.0",
    "read_only": True,
    "capabilities": ("resolve", "status"),
}


class _Router:
    def __init__(self, route, contract=None):
        self.route = route
        self.contract = contract if contract is not None else CONTRACT

    def series_model_router_contract(self):
        return self.contract

    def resolve_model_route(self, kind, **_kwargs):
        return {**self.route, "kind": kind}


class _Context:
    def __init__(self, router, providers=()):
        self.router = router
        self.providers = set(providers)

    def get_star_instance(self, plugin_name):
        return self.router if plugin_name == "astrbot_plugin_update_manager" else None

    def get_provider_by_id(self, provider_id):
        return object() if provider_id in self.providers else None


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


if __name__ == "__main__":
    unittest.main()
