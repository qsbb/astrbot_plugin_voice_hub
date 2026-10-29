# -*- coding: utf-8 -*-
"""WAV -> 腾讯 Silk 编码。

为什么要自己转 silk：

NapCat 收到 WAV 语音会先判断是否需要转成 silk（看前 10 字节有没有
``#!SILK``）。需要转换时它用 ``/usr/bin/ffmpeg -f ntsilk_s16le``，而
Ubuntu 22.04 的 ffmpeg 4.4.2 根本没有这个 muxer，命令必然失败：

    Requested output format 'ntsilk_s16le' is not a suitable output format

于是用户一条语音都收不到。绕开的办法是让插件自己产出 silk —— NapCat
的 ``isSilk`` 只看前 10 字节，命中 ``\\x02#!SILK_V3`` 就跳过转换，直接走
它本来就正常工作的发送路径。

silk 只接受 8/12/16/24 kHz 输入，直接喂 44.1 kHz 的 PCM 会报
``ENC_INPUT_INVALID_NO_OF_SAMPLES``；而把 44.1 kHz 的数据谎报成 24 kHz
虽然能编码成功，播放出来却慢 1.84 倍（语速全错）。所以必须先重采样到
24 kHz，这里用 ffmpeg 做。
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:  # pragma: no cover - 取决于运行环境是否装了 pysilk
    import pysilk as _pysilk
except Exception:  # pragma: no cover
    _pysilk = None

#: silk 内部采样率上限，QQ 语音固定用 24 kHz。
SILK_SAMPLE_RATE = 24000
#: silk 码率（bps）。
SILK_BIT_RATE = 24000
#: 腾讯 silk 文件头，NapCat 的 isSilk 就是在前 10 字节里找它。
SILK_MAGIC = b"#!SILK"


class SilkEncodeError(RuntimeError):
    """silk 编码失败；message 可直接展示。"""


def silk_available() -> bool:
    """当前环境能否编码 silk（需要 pysilk 与 ffmpeg 都在）。"""
    return _pysilk is not None and shutil.which("ffmpeg") is not None


def _load_pysilk() -> Any:
    module = _pysilk
    if module is None:
        raise SilkEncodeError(
            "运行环境缺少 pysilk，无法自行编码 silk；请安装 pysilk 后重试。"
        )
    return module


def _resample_to_pcm(audio_path: Path, sample_rate: int = SILK_SAMPLE_RATE) -> bytes:
    """用 ffmpeg 把任意音频重采样成单声道 16 位小端 PCM。"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SilkEncodeError("运行环境缺少 ffmpeg，无法把音频重采样成 silk 需要的 24 kHz。")
    command = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(audio_path),
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-f",
        "s16le",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.SubprocessError as exc:
        raise SilkEncodeError(f"ffmpeg 重采样失败：{exc}") from exc
    pcm = completed.stdout
    if completed.returncode != 0 or not pcm:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SilkEncodeError(f"ffmpeg 重采样失败：{detail or '没有输出 PCM'}")
    return pcm


def wav_to_silk(
    audio_path: Path | str,
    *,
    sample_rate: int = SILK_SAMPLE_RATE,
    bit_rate: int = SILK_BIT_RATE,
) -> bytes:
    """把音频文件编码成腾讯 silk 字节。

    返回值可以直接塞进 OneBot 的 ``{"type": "record", "data": {"file":
    "base64://..."}}``。
    """
    module = _load_pysilk()
    path = Path(audio_path)
    if not path.is_file():
        raise SilkEncodeError(f"音频文件不存在：{path.name}")
    pcm = _resample_to_pcm(path, sample_rate)
    buffer = io.BytesIO()
    try:
        module.encode(
            io.BytesIO(pcm),
            buffer,
            sample_rate,
            bit_rate,
            tencent=True,
        )
    except Exception as exc:
        raise SilkEncodeError(f"silk 编码失败：{exc}") from exc
    data = buffer.getvalue()
    if not data:
        raise SilkEncodeError("silk 编码没有产生数据。")
    if SILK_MAGIC not in data[:10]:
        raise SilkEncodeError("silk 编码结果缺少腾讯文件头，napcat 会再次尝试转换。")
    return data


def looks_like_silk(data: bytes) -> bool:
    """按 napcat 的口径判断字节串是否为 silk。"""
    return SILK_MAGIC in bytes(data[:10])
