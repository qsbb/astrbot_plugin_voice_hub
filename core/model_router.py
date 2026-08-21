"""Optional adapter for the series model-router contract.

The adapter is deliberately one-way and fail-closed: voice-hub keeps its
existing provider settings as the first choice, and only asks the optional
update-manager contract for a provider when the caller has no local override.
Missing, incompatible, or failing contracts return an empty provider id so
the caller can continue with AstrBot's native fallback.
"""

from __future__ import annotations

import inspect
from typing import Any


ROUTER_PLUGIN_NAME = "astrbot_plugin_update_manager"
ROUTER_CONTRACT_NAME = "series.model_router@1.0"
ROUTER_CONTRACT_MAJOR = "1"


async def resolve_provider_id(context: Any, kind: str) -> str:
    """Return a core-routed provider id, or ``""`` when unavailable."""
    if not isinstance(kind, str) or not kind.strip():
        return ""
    kind = kind.strip()
    plugin = _get_router_plugin(context)
    if inspect.isawaitable(plugin):
        try:
            plugin = await plugin
        except Exception:
            return ""
    if plugin is None or not _compatible(plugin):
        return ""
    resolver = getattr(plugin, "resolve_model_route", None)
    if not callable(resolver):
        return ""
    try:
        try:
            route = resolver(kind, plugin_override=None)
        except TypeError:
            route = resolver(kind)
        if inspect.isawaitable(route):
            route = await route
    except Exception:
        return ""
    if not isinstance(route, dict):
        return ""
    if (
        route.get("kind") != kind
        or route.get("source") != "core"
        or route.get("available") is not True
    ):
        return ""
    provider_id = route.get("provider_id")
    if not isinstance(provider_id, str) or not provider_id.strip():
        return ""
    getter = getattr(context, "get_provider_by_id", None)
    if callable(getter):
        try:
            if getter(provider_id.strip()) is None:
                return ""
        except Exception:
            return ""
    return provider_id.strip()[:256]


def _get_router_plugin(context: Any) -> Any | None:
    getter = getattr(context, "get_star_instance", None)
    if not callable(getter):
        return None
    try:
        return getter(ROUTER_PLUGIN_NAME)
    except Exception:
        return None


def _compatible(plugin: Any) -> bool:
    declare = getattr(plugin, "series_model_router_contract", None)
    if not callable(declare):
        return False
    try:
        contract = declare()
    except Exception:
        return False
    if not isinstance(contract, dict):
        return False
    version = str(contract.get("version") or "")
    return (
        contract.get("name") == ROUTER_CONTRACT_NAME
        and version.split(".", 1)[0] == ROUTER_CONTRACT_MAJOR
        and contract.get("read_only") is True
        and isinstance(contract.get("capabilities"), (list, tuple, set))
        and "resolve" in contract["capabilities"]
    )
