from __future__ import annotations

import re


_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<(?!#\s*\d{1,2}(?:\.\d{1,2})?\s*#>)[^>\n]{1,80}>")
_CONTROL_LINE_RE = re.compile(r"^\s*(?:\[CQ:[^\]]+\]|\[[A-Z][A-Z0-9_-]{0,24}\])\s*$")
_WHITESPACE_RE = re.compile(r"[ \t\r\n]+")
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?", re.MULTILINE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_NUMBERED_PARAGRAPH_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千万零〇\d]+(?:喵|段|部分)?[、.．:：)]|(?:\d{1,3}|[A-Za-z])[、.．:：)])\s*"
)


def clean_tts_text(text: str, *, preserve_newlines: bool = False) -> str:
    content = str(text or "")
    if not content:
        return ""

    content = _CODE_BLOCK_RE.sub(" ", content)
    content = _INLINE_CODE_RE.sub(" ", content)
    content = _URL_RE.sub(" ", content)
    content = _HTML_TAG_RE.sub(" ", content)
    lines = [
        line
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not _CONTROL_LINE_RE.match(line)
    ]
    if preserve_newlines:
        cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
        content = "\n".join(cleaned_lines)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n[ \t]+", "\n", content)
        return content.strip()

    content = " ".join(lines)
    content = _WHITESPACE_RE.sub(" ", content)
    return content.strip()


def contains_url(text: str) -> bool:
    """检测文本是否包含网址。"""
    return bool(_URL_RE.search(str(text or "")))


def replace_urls_for_tts(text: str, placeholder: str = "这个网址") -> str:
    """将文本中的网址替换为占位词，供 TTS 朗读使用。

    文字回复仍保留原始网址，仅朗读文本中的网址被替换。
    """
    return _URL_RE.sub(placeholder, str(text or ""))


def split_tts_text(
    text: str,
    *,
    max_chars: int = 500,
    max_segments: int = 6,
    preserve_structure: bool = True,
) -> list[str]:
    content = clean_tts_text(text, preserve_newlines=preserve_structure)
    if not content:
        return []

    paragraphs = _split_tts_paragraphs(content) if preserve_structure else [content]
    segments: list[str] = []
    for paragraph in paragraphs:
        if max_chars <= 0 or len(paragraph) <= max_chars:
            segments.append(paragraph)
            continue
        segments.extend(_split_long_tts_paragraph(paragraph, max_chars))

    # An explicit paragraph boundary is a user/model delivery decision. Do not
    # merge those paragraphs merely to satisfy the soft segment-count limit.
    if preserve_structure and len(paragraphs) > 1:
        return segments

    if max_segments > 0 and len(segments) > max_segments:
        head = segments[: max_segments - 1]
        tail = "".join(segments[max_segments - 1 :])
        segments = [*head, tail]
    return segments


def _split_tts_paragraphs(text: str) -> list[str]:
    """Split explicit blank-line and numbered paragraphs without re-chunking prose."""
    paragraphs: list[str] = []
    for block in _PARAGRAPH_SPLIT_RE.split(text):
        current: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if current and _NUMBERED_PARAGRAPH_RE.match(line):
                paragraphs.append(" ".join(current).strip())
                current = []
            current.append(line)
        if current:
            paragraphs.append(" ".join(current).strip())
    return [paragraph for paragraph in paragraphs if paragraph]


def _split_long_tts_paragraph(text: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph at sentence boundaries, then hard-limit residue."""
    raw_parts = [match.group(0).strip() for match in _SENTENCE_RE.finditer(text)]
    raw_parts = [part for part in raw_parts if part] or [text]

    segments: list[str] = []
    current = ""
    for part in raw_parts:
        if len(part) > max_chars:
            if current:
                segments.append(current)
                current = ""
            segments.extend(
                part[index : index + max_chars]
                for index in range(0, len(part), max_chars)
            )
            continue
        if current and len(current) + len(part) > max_chars:
            segments.append(current)
            current = ""
        current += part
    if current:
        segments.append(current)
    return [segment.strip() for segment in segments if segment.strip()]
