from __future__ import annotations

import base64
import io
import mimetypes
import wave
from pathlib import Path


class AudioValidationError(ValueError):
    """Raised when a voice sample cannot be sent to the MiMo API."""


class AudioMergeError(RuntimeError):
    """Raised when segmented audio cannot be merged without data loss."""


class PCMOutputValidationError(ValueError):
    """Raised when synthesized output is not a complete PCM16 WAV file."""


SUPPORTED_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


def sniff_audio_format(header: bytes) -> str:
    """按文件内容识别真实音频格式，不信任扩展名。

    平台侧语音（QQ/微信）常把 silk/amr 命名成 .wav 或 .mp3，
    仅凭扩展名判断会把「格式不支持」误报成「文件损坏」。
    返回小写格式名；无法识别时返回 "unknown"。
    """
    if not header:
        return "unknown"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"ID3"):
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "mp3"
    if header.startswith(b"#!SILK") or header[1:8] == b"#!SILK_":
        return "silk"
    if header.startswith(b"#!AMR"):
        return "amr"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"fLaC"):
        return "flac"
    if header[4:8] == b"ftyp":
        return "m4a"
    return "unknown"


def detect_audio_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_AUDIO_MIME:
        return SUPPORTED_AUDIO_MIME[suffix]
    guessed = mimetypes.guess_type(str(path))[0] or ""
    if guessed in SUPPORTED_AUDIO_MIME.values():
        return guessed
    raise AudioValidationError("Unsupported audio format. Use mp3 or wav.")


def estimate_base64_chars(byte_count: int) -> int:
    return 4 * ((max(0, int(byte_count)) + 2) // 3)


def validate_audio_header(path: Path, mime_type: str) -> None:
    header = path.read_bytes()[:12]
    actual = sniff_audio_format(header)
    if mime_type == "audio/wav":
        if actual != "wav":
            raise AudioValidationError(
                f"Invalid wav audio header ({_describe_actual(actual)})."
            )
        return
    if mime_type == "audio/mpeg":
        if actual != "mp3":
            raise AudioValidationError(
                f"Invalid mp3 audio header ({_describe_actual(actual)})."
            )
        return


def _describe_actual(actual: str) -> str:
    """把嗅探结果转成可读提示，帮助定位「扩展名对但编码不支持」。"""
    if actual == "unknown":
        return "content not recognised as mp3 or wav"
    return f"file content looks like {actual}; convert it to mp3 or wav"


def validate_voice_file(
    path: Path,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    max_base64_chars: int | None = None,
) -> None:
    if not path.is_file():
        raise AudioValidationError(f"Voice file not found: {path}")
    mime_type = detect_audio_mime(path)
    size = path.stat().st_size
    if size <= 0:
        raise AudioValidationError("Voice file is empty.")
    if size > max_bytes:
        raise AudioValidationError(f"Voice file too large (max {max_bytes} bytes).")
    validate_audio_header(path, mime_type)
    base64_limit = max_base64_chars if max_base64_chars is not None else max_bytes
    if estimate_base64_chars(size) > base64_limit:
        raise AudioValidationError(
            f"Base64 audio payload too large (max {base64_limit} chars)."
        )


def inspect_pcm16_wav(path: Path | str) -> dict[str, int]:
    """Validate a complete uncompressed PCM16 WAV and return its metadata."""
    audio_path = Path(path)
    if not audio_path.is_file():
        raise PCMOutputValidationError(f"Audio output not found: {audio_path}")

    try:
        with audio_path.open("rb") as stream:
            header = stream.read(12)
        if not header.startswith(b"RIFF") or header[8:12] != b"WAVE":
            raise PCMOutputValidationError("Audio output is not a RIFF/WAVE file.")

        with wave.open(str(audio_path), "rb") as reader:
            compression = reader.getcomptype()
            sample_width = reader.getsampwidth()
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            frame_count = reader.getnframes()
            if compression != "NONE":
                raise PCMOutputValidationError(
                    "Audio output is a compressed WAV, not PCM."
                )
            if sample_width != 2:
                raise PCMOutputValidationError("Audio output is not 16-bit PCM.")
            if channels <= 0 or sample_rate <= 0 or frame_count <= 0:
                raise PCMOutputValidationError(
                    "Audio output has invalid channel, rate, or frame metadata."
                )

            bytes_per_frame = channels * sample_width
            frames_read = 0
            while frames_read < frame_count:
                chunk = reader.readframes(min(8192, frame_count - frames_read))
                if not chunk or len(chunk) % bytes_per_frame:
                    raise PCMOutputValidationError(
                        "Audio output contains truncated PCM frames."
                    )
                frames_read += len(chunk) // bytes_per_frame
            if frames_read != frame_count:
                raise PCMOutputValidationError(
                    "Audio output frame count does not match its WAV header."
                )
    except PCMOutputValidationError:
        raise
    except (EOFError, OSError, wave.Error) as exc:
        raise PCMOutputValidationError(f"Invalid PCM WAV output: {exc}") from exc

    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "duration_ms": round(frame_count * 1000 / sample_rate),
    }


def encode_voice_file_data_url(
    path: Path | str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    max_base64_chars: int | None = None,
) -> str:
    audio_path = Path(path)
    validate_voice_file(
        audio_path,
        max_bytes=max_bytes,
        max_base64_chars=max_base64_chars,
    )
    mime_type = detect_audio_mime(audio_path)
    data = audio_path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def merge_wav_files(paths: list[Path | str], output_path: Path | str) -> Path:
    """Merge compatible PCM WAV files and return the single output path.

    Every segment is parsed instead of assuming a fixed-size WAV header.  A
    mismatch is reported explicitly so callers never mistake the first segment
    for the complete recording.
    """
    inputs = [Path(path) for path in paths]
    if not inputs:
        raise AudioMergeError("No WAV segments to merge.")

    chunks: list[bytes] = []
    try:
        chunks = [path.read_bytes() for path in inputs]
    except OSError as exc:
        raise AudioMergeError(f"Unable to read WAV segment: {exc}") from exc

    data = merge_wav_bytes(chunks)
    destination = Path(output_path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise AudioMergeError(f"Unable to write merged WAV: {exc}") from exc
    return destination


def merge_wav_bytes(chunks: list[bytes]) -> bytes:
    """Merge compatible PCM WAV byte strings without assuming header layout."""
    if not chunks:
        raise AudioMergeError("No WAV segments to merge.")

    expected: tuple[int, int, int, str] | None = None
    frames: list[bytes] = []

    try:
        for index, chunk in enumerate(chunks, start=1):
            with wave.open(io.BytesIO(chunk), "rb") as reader:
                signature = (
                    reader.getnchannels(),
                    reader.getsampwidth(),
                    reader.getframerate(),
                    reader.getcomptype(),
                )
                if signature[3] != "NONE":
                    raise AudioMergeError(
                        f"Unsupported compressed WAV segment {index}."
                    )
                if expected is None:
                    expected = signature
                elif signature != expected:
                    raise AudioMergeError(
                        "WAV segments use incompatible channel, sample-width, "
                        "sample-rate, or compression settings."
                    )
                frames.append(reader.readframes(reader.getnframes()))

        assert expected is not None
        if len(chunks) == 1:
            return chunks[0]
        channels, sample_width, frame_rate, _ = expected
        destination = io.BytesIO()
        with wave.open(destination, "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(sample_width)
            writer.setframerate(frame_rate)
            writer.setcomptype("NONE", "not compressed")
            for chunk in frames:
                writer.writeframes(chunk)
        return destination.getvalue()
    except AudioMergeError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioMergeError(f"Invalid WAV segment: {exc}") from exc
