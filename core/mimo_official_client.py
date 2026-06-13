from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MimoTTSConfig:
    api_key: str
    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = "mimo-v2.5-tts-voiceclone"
    output_format: str = "wav"
    timeout: float = 120.0


class MimoOfficialClient:
    def __init__(self, config: MimoTTSConfig):
        self.config = config

    def build_payload(
        self,
        *,
        text: str,
        voice_data_url: str,
        context: str = "",
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if context.strip():
            messages.append({"role": "user", "content": context.strip()})
        messages.append({"role": "assistant", "content": text})
        return {
            "model": self.config.model,
            "messages": messages,
            "audio": {
                "format": self.config.output_format,
                "voice": voice_data_url,
            },
        }

    async def synthesize_to_file(
        self,
        *,
        text: str,
        voice_data_url: str,
        output_path: str | Path,
        context: str = "",
    ) -> Path:
        if not self.config.api_key:
            raise RuntimeError("MIMO API Key is not configured.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required. Install requirements.txt.") from exc

        payload = self.build_payload(
            text=text,
            voice_data_url=voice_data_url,
            context=context,
        )
        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        completion = await client.chat.completions.create(**payload)
        message = completion.choices[0].message
        audio = getattr(message, "audio", None)
        audio_data = getattr(audio, "data", None)
        if not audio_data:
            raise RuntimeError("MiMo API returned no audio data.")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        raw = base64.b64decode(audio_data)
        await asyncio.to_thread(out.write_bytes, raw)
        return out
