from __future__ import annotations

from dataclasses import dataclass
from typing import Any


StyleDirectorCacheKey = tuple[str, str, str, bool]


@dataclass(slots=True)
class TTSContextResult:
    context: str
    speech_text: str
    style_context: str = ""
    cached: bool = False


def build_style_director_cache_key(
    *,
    voice_id: str,
    emotion: str,
    text: str,
    optimize_text: bool,
) -> StyleDirectorCacheKey:
    return (
        str(voice_id or ""),
        str(emotion or ""),
        str(text[:128] if text else ""),
        bool(optimize_text),
    )


def merge_directed_context(base_context: str, directive: str, mode: str) -> str:
    if str(mode or "").strip().lower() == "direct":
        return str(directive or "").strip() or base_context
    return "\n".join(
        part for part in (str(base_context or "").strip(), str(directive or "").strip()) if part
    )


def clip_log_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."
