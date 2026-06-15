# Changelog

## v0.3.0 - 2026-06-15

### Added

- 新增发送前 AI 语音导演，可调用 AstrBot 已配置的 AI 服务商生成隐藏 MiMo 风格指令。
- 新增 AI 优化朗读文本能力，可剔除无意义口头填充并整理自然停顿，且不改写最终聊天文本。
- 新增 AI 服务商下拉选择、手填 provider id、导演模式、失败回退和调试日志开关。
- 新增 AstrBot 日志输出 AI 导演结果摘要，便于确认 `style_context` 与 `speech_text` 是否生效。
- 新增工作台 readiness 状态，提示 API Key、音色库、AI 导演、试听链路是否就绪。
- 新增面向其他插件复用的 `mimo_tts_speak` LLM 工具兼容链路和通用 TTS helper。

### Changed

- Pages 前端重构为 Firefly-inspired 清新玻璃卡片风格，保留原 AstrBot Pages 原生实现，不引入额外前端框架。
- 试听交互增强：不可用时显示明确原因，试听音色下拉仅展示启用中的音色。
- 后端合成上下文结构化，新增 `core/synthesis_context.py` 管理 AI 导演缓存键、上下文合并和日志裁剪。
- Pages AI provider 列表兼容更多 AstrBot provider manager 结构。

### Fixed

- 修复 `mimo_tts_speak` 工具参数与 AstrBot reserved `context` 参数冲突的问题。
- 修复 API Key 通过 Pages 填写后无法稳定持久化的问题。
- 修复上传/试听等 Pages 操作出现成功但前端误报 500 的部分场景。

## v0.2.0 - 2026-06-13

### Added

- 接入 MiMo v2.5 voiceclone 官方 TTS API。
- 新增 Pages 音色上传、音色库管理、试听诊断、多音色切换和默认音色设置。
- 新增情绪路由、长文本分段、输出文件清理、回复模式和自动语音化概率。
- 新增 README、metadata、插件图标、免责声明和基础测试覆盖。
