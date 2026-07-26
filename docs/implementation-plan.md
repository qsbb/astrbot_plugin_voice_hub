# 凝心溯溪-声 Implementation Plan（历史设计归档）

> **归档声明（2026-07-27）**：本文是早期实现计划，仅供历史追溯，不是当前实现规范，不应继续指导开发、配置或验收。当前事实以插件根目录 `README.md`、`metadata.yaml`、`main.py`、`pages_api.py`、`pages/settings/` 和测试代码为准。
>
> 文档中的任务清单、命令设想和架构描述可能早于当前实现；当前插件不注册 TTS 聊天命令，实际入口以 README 为准。

Goal: build an AstrBot plugin that supports dual TTS backends (MiMo voiceclone + AstrBot built-in TTS), manages local voice samples, calls the official MiMo `mimo-v2.5-tts-voiceclone` API, and supports multi-voice switching from Pages.

Architecture: the plugin stores voice sample metadata locally and sends the selected sample as a Data URL on each synthesis request. Pages handles configuration, upload, preview, and default voice management. Commands resolve voice priority from temporary command choice, user default, group default, and global default.

Tech stack: AstrBot plugin APIs, Quart request handlers for Pages APIs, official OpenAI-compatible MiMo chat completions API, pytest for core unit tests.

## Tasks（历史任务清单，非当前待办）

> 状态修正：核心模块、Pages API、设置页面和测试已在后续版本实现；历史设想中的 `/tts`、`/tts音色列表`、`/tts设置音色` 等聊天命令已明确取消，当前通过 Pages、LLM 工具和插件服务调用。以下复选框保留原始计划形态，不表示当前未完成状态。

- [x] Add core tests for voice storage, voice selection priority, audio Data URL encoding, and MiMo payload building.（后续已实现）
- [x] Implement focused core modules: `config.py`, `voice_store.py`, `audio_codec.py`, `mimo_official_client.py`.（后续已实现）
- [ ] Add AstrBot plugin entrypoint and command handlers for `/tts`, `/tts音色列表`, `/tts设置音色`, and admin defaults.（历史方案已取消，不再实现聊天命令）
- [x] Add Pages APIs for config, voice list, upload, preview, delete, and default switching.（后续已实现）
- [x] Add `pages/Settings` frontend for configuration, multi-voice management, upload, and preview playback.（后续已实现，实际目录以 README 为准）
- [x] Verify with unit tests and Python compilation.（后续版本已有验证命令）
