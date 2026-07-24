# 凝心溯溪-声 Implementation Plan

Goal: build an AstrBot plugin that supports dual TTS backends (MiMo voiceclone + AstrBot built-in TTS), manages local voice samples, calls the official MiMo `mimo-v2.5-tts-voiceclone` API, and supports multi-voice switching from Pages.

Architecture: the plugin stores voice sample metadata locally and sends the selected sample as a Data URL on each synthesis request. Pages handles configuration, upload, preview, and default voice management. Commands resolve voice priority from temporary command choice, user default, group default, and global default.

Tech stack: AstrBot plugin APIs, Quart request handlers for Pages APIs, official OpenAI-compatible MiMo chat completions API, pytest for core unit tests.

## Tasks

- [ ] Add core tests for voice storage, voice selection priority, audio Data URL encoding, and MiMo payload building.
- [ ] Implement focused core modules: `config.py`, `voice_store.py`, `audio_codec.py`, `mimo_official_client.py`.
- [ ] Add AstrBot plugin entrypoint and command handlers for `/tts`, `/tts音色列表`, `/tts设置音色`, and admin defaults.
- [ ] Add Pages APIs for config, voice list, upload, preview, delete, and default switching.
- [ ] Add `pages/Settings` frontend for configuration, multi-voice management, upload, and preview playback.
- [ ] Verify with unit tests and Python compilation.
