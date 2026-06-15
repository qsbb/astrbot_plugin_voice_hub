from __future__ import annotations

import re
import asyncio
from dataclasses import dataclass
from typing import Any


DEFAULT_STYLE_DIRECTOR_PROMPT = """你是语音导演，只为 TTS 生成一段不会被读出的 MiMo 风格控制指令。
请根据待朗读文本、情绪和音色信息，输出一句自然语言风格描述。
要求：
1. 只描述语气、节奏、情绪、停顿、亲近感、场景感。
2. 不要复述或改写待朗读文本。
3. 不要输出括号、引号、编号、解释、Markdown。
4. 不要加入会被误认为正文的台词。
5. 长度控制在 {max_chars} 字以内。"""


@dataclass(slots=True)
class StyleDirectorInput:
    text: str
    emotion: str = "neutral"
    voice_name: str = ""
    voice_description: str = ""
    voice_style_context: str = ""
    existing_context: str = ""
    max_chars: int = 120


def build_style_director_prompt(data: StyleDirectorInput, template: str = "") -> tuple[str, str]:
    max_chars = max(20, int(data.max_chars or 120))
    system_prompt = _render_template(template or DEFAULT_STYLE_DIRECTOR_PROMPT, max_chars=max_chars)
    user_prompt = "\n".join(
        part
        for part in (
            f"待朗读文本：{_clip(data.text, 800)}",
            f"情绪：{data.emotion or 'neutral'}",
            f"音色名称：{data.voice_name}" if data.voice_name else "",
            f"音色说明：{data.voice_description}" if data.voice_description else "",
            f"音色已有风格：{data.voice_style_context}" if data.voice_style_context else "",
            f"已有风格指令：{data.existing_context}" if data.existing_context else "",
            "请输出最终风格控制指令：",
        )
        if part
    )
    return system_prompt, user_prompt


def sanitize_style_director_output(value: Any, max_chars: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^[\s\-\d.、:：]+", "", text)
    text = text.strip().strip("\"'“”‘’`")
    text = re.sub(r"^(风格指令|输出|建议|语气|风格)\s*[:：]\s*", "", text)
    text = text.strip().strip("\"'“”‘’`")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip("，。；、,. ")
    return text


async def generate_style_directive(
    context: Any,
    data: StyleDirectorInput,
    *,
    template: str = "",
    provider_id: str = "",
) -> str:
    llm_generate = getattr(context, "llm_generate", None)
    if not callable(llm_generate):
        return ""
    system_prompt, user_prompt = build_style_director_prompt(data, template)
    kwargs = {
        "prompt": user_prompt,
        "system_prompt": system_prompt,
    }
    if provider_id:
        kwargs["chat_provider_id"] = provider_id
    response = await asyncio.wait_for(llm_generate(**kwargs), timeout=15)
    output = getattr(response, "completion_text", response)
    return sanitize_style_director_output(output, data.max_chars)


def _clip(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def _render_template(template: str, *, max_chars: int) -> str:
    try:
        return str(template or "").format(max_chars=max_chars)
    except Exception:
        return str(template or "")
