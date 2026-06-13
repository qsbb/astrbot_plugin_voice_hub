from __future__ import annotations

import base64
import mimetypes
from pathlib import Path


class AudioValidationError(ValueError):
    """Raised when a voice sample cannot be sent to the MiMo API."""


SUPPORTED_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


def detect_audio_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_AUDIO_MIME:
        return SUPPORTED_AUDIO_MIME[suffix]
    guessed = mimetypes.guess_type(str(path))[0] or ""
    if guessed in SUPPORTED_AUDIO_MIME.values():
        return guessed
    raise AudioValidationError("Unsupported audio format. Use mp3 or wav.")


def validate_voice_file(path: Path, *, max_bytes: int = 10 * 1024 * 1024) -> None:
    if not path.is_file():
        raise AudioValidationError(f"Voice file not found: {path}")
    detect_audio_mime(path)
    size = path.stat().st_size
    if size <= 0:
        raise AudioValidationError("Voice file is empty.")
    if size > max_bytes:
        raise AudioValidationError(f"Voice file too large (max {max_bytes} bytes).")


def encode_voice_file_data_url(path: Path | str, *, max_bytes: int = 10 * 1024 * 1024) -> str:
    audio_path = Path(path)
    validate_voice_file(audio_path, max_bytes=max_bytes)
    mime_type = detect_audio_mime(audio_path)
    data = audio_path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"
