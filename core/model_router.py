"""Optional adapter for the series model-router contract.

The adapter is deliberately one-way and fail-closed: voice-hub keeps its
existing provider settings as the first choice, and only asks the optional
update-manager contract for a provider when the caller has no local override.
Missing, incompatible, or failing contracts return an empty provider id (or an
empty route) so the caller can continue with AstrBot's native fallback.
The core instance itself is looked up through AstrBot's official
``get_registered_star`` registry (with the optional, non-official
``get_star_instance`` shortcut tried first).
Callers that also need the core-configured ``model``/``voice`` use
:func:`resolve_model_route`, which shares the exact same validation.
"""

from __future__ import annotations

import inspect
from typing import Any


ROUTER_PLUGIN_NAME = "astrbot_plugin_update_manager"
ROUTER_CONTRACT_NAME = "series.model_router@1.0"
ROUTER_CONTRACT_MAJOR = "1"
ROUTER_INSTANCE_ATTRIBUTES = ("star_cls", "star", "instance", "star_instance", "plugin")


async def resolve_provider_id(context: Any, kind: str) -> str:
    """Return a core-routed provider id, or ``""`` when unavailable."""
    route = await _resolve_validated_route(context, kind)
    if route is None:
        return ""
    return route["provider_id"]


async def resolve_model_route(context: Any, kind: str) -> dict[str, Any]:
    """Return the core route for ``kind``, or ``{}`` when unavailable.

    Validation is exactly the same as :func:`resolve_provider_id` (contract
    name/major version, read-only, ``resolve`` capability, ``source ==
    "core"``, ``available is True``, matching kind, provider registered in
    AstrBot). The difference is that the whole route is returned, so callers
    can also honor the core-configured ``model`` and ``voice``.
    """
    route = await _resolve_validated_route(context, kind)
    if route is None:
        return {}
    return {
        "provider_id": route["provider_id"],
        "model": _text(route.get("model")),
        "voice": _text(route.get("voice")),
        "source": "core",
        "available": True,
        "fallback_from": _text(route.get("fallback_from")),
    }


async def _resolve_validated_route(context: Any, kind: str) -> dict[str, Any] | None:
    """Fetch and validate one core route, or ``None`` when unusable."""
    if not isinstance(kind, str) or not kind.strip():
        return None
    kind = kind.strip()
    plugin = await _resolve_router_plugin(context)
    if plugin is None or not _compatible(plugin):
        return None
    resolver = getattr(plugin, "resolve_model_route", None)
    if not callable(resolver):
        return None
    try:
        try:
            route = resolver(kind, plugin_override=None)
        except TypeError:
            route = resolver(kind)
        if inspect.isawaitable(route):
            route = await route
    except Exception:
        return None
    if not isinstance(route, dict):
        return None
    if (
        route.get("kind") != kind
        or route.get("source") != "core"
        or route.get("available") is not True
    ):
        return None
    provider_id = _text(route.get("provider_id"))
    if not provider_id:
        return None
    getter = getattr(context, "get_provider_by_id", None)
    if callable(getter):
        try:
            if getter(provider_id) is None:
                return None
        except Exception:
            return None
    return {**route, "provider_id": provider_id}


def _text(value: Any, limit: int = 256) -> str:
    """Return a trimmed string field, ignoring non-string values."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


async def _resolve_router_plugin(context: Any) -> Any | None:
    """Best-effort resolve the core plugin instance, never raising.

    ``Context.get_star_instance`` is not part of AstrBot's public API (4.x
    exposes ``get_registered_star`` / ``get_all_stars`` instead), so it is
    only the first, optional shortcut; the official registry lookup below is
    what actually finds the core on a stock AstrBot. A missing or broken step
    is treated as "not found" so callers keep their native fallback.
    """
    instance = await _call_star_lookup(context, "get_star_instance")
    if instance is not None and not isinstance(instance, type):
        return instance
    metadata = await _call_star_lookup(context, "get_registered_star")
    if metadata is None:
        return None
    for attribute in ROUTER_INSTANCE_ATTRIBUTES:
        candidate = _star_metadata_attribute(metadata, attribute)
        if candidate is not None:
            return candidate
    return None


async def _call_star_lookup(context: Any, method_name: str) -> Any | None:
    """Call one optional star lookup on ``context``; any failure yields ``None``."""
    try:
        getter = getattr(context, method_name, None)
    except Exception:
        return None
    if not callable(getter):
        return None
    try:
        value = getter(ROUTER_PLUGIN_NAME)
        if inspect.isawaitable(value):
            value = await value
    except Exception:
        return None
    return value


def _star_metadata_attribute(metadata: Any, attribute: str) -> Any | None:
    """Read one ``StarMetadata`` instance attribute, skipping classes."""
    try:
        value = getattr(metadata, attribute, None)
    except Exception:
        return None
    if value is None or isinstance(value, type):
        # AstrBot 4.x keeps the running instance on ``star_cls``; a class (or
        # nothing at all) means there is no live instance to hand out.
        return None
    return value


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
