# Changelog

## v0.4.5 - 2026-07-22

### Changed

- 网址处理从"跳过整条 TTS"改为"替换网址为占位词"：开启后 TTS 会把网址替换为"这个网址"再朗读，原始网址仍随文字回复发送，不再缺失语音内容。
- 配置项 `skip_url_tts`（v0.4.4）改名为 `replace_url_in_tts`，旧配置会自动迁移。
- Pages 面板开关文案更新为"朗读时把网址替换为'这个网址'"。
- `mimo_tts_speak` 工具 docstring 更新：说明网址会被替换为占位词而非拒绝合成。

## v0.4.4 - 2026-07-22

### Added

- 新增 `skip_url_tts` 设置开关（默认开启）。开启后当 LLM 回复中包含网址时跳过 TTS 朗读，网址只随文字发送，不会出现在语音里。
- LLM 工具 `mimo_tts_speak` 在 `skip_url_tts` 开启时遇到含网址的文本会拒绝合成，提示 LLM 改用纯文本发送。
- Pages 面板新增"跳过含网址回复的语音化"开关。

## v0.4.3 - 2026-07-22

### Fixed

- 修复 LLM 调用 `mimo_tts_speak` 后误以为只生成不发送，又用 `send_message_to_user` 重发同一音频导致用户收到重复语音的问题。
- 重写 `mimo_tts_speak` 工具 docstring，明确强调"本工具自动发送音频给用户，禁止再用其他工具重发"。
- 工具返回值从内部 wav 路径改为明确的状态陈述（如 `audio already sent to user (1 segment); do not resend it via other tools`），避免 LLM 把路径当成待发送资源。

## v0.4.2 - 2026-07-22

### Fixed

- 彻底修复 AstrBot 热重载后 `functools.partial` 套娃导致 `TypeError: takes N positional arguments but N+1 were given` 的问题。
- 事件钩子 `filter_tts_tool_for_probability_mode` 和 `auto_tts_reply` 改用 `*args` 签名，从参数末尾提取真实 `event`/`request`，无论套娃多少层都能正确工作。
- LLM 工具 `mimo_tts_speak` 在入口处将 `self` 重定向到 `_current_instance`，修复热重载后 `self=None` 导致 `'NoneType' object has no attribute 'synthesize_text'` 的问题。
- 新增 `_current_instance` 类变量，始终指向最新的插件实例，确保热重载后使用最新配置。
- 新增 `_unwrap_stale_partials()`，在 `__init__` 中尝试将 registry 中已套娃的 handler 重置为原始函数，从根源阻止后续套娃。

### Notes

- 本版本不依赖 `terminate()` 清理，而是从方法签名层面兼容任意深度的 partial 套娃。
- 首次升级后建议完全重启 AstrBot 一次以清理已有的套娃绑定。

## v0.4.1 - 2026-07-20

### Fixed

- 修复 AstrBot 热重载后事件钩子 `filter_tts_tool_for_probability_mode` 和 `auto_tts_reply` 因 `functools.partial` 套娃导致 `TypeError: takes N positional arguments but N+1 were given` 的问题。
- 修复热重载后 LLM 工具 `mimo_tts_speak` 的插件实例引用失效为 `None`，导致 `'NoneType' object has no attribute 'synthesize_text'` 的问题。
- `terminate()` 现在会主动从 `star_handlers_registry` 移除本插件旧 handler metadata，并清理 `func_tool_manager` 中残留的 LLM 工具，使框架 reload 时重新创建干净的绑定。

### Notes

- 首次升级到本版本后，建议**完全重启 AstrBot 进程一次**以确保 registry 干净；之后的热重载也应能正常工作。

## v0.4.0 - 2026-06-16

### Added

- 新增普通 LLM 回复自动语音化的群聊/私聊黑白名单访问控制，并支持管理员 ID 绕过名单限制。
- Pages 新增自动语音访问控制规则预览，展示管理员、群聊、私聊三类规则当前生效状态。
- 新增自动语音访问控制日志，记录 allow / skip / denied 的具体原因，便于在真实 AstrBot 环境确认规则是否命中。
- README 新增黑白名单、管理员、UMO/纯 ID 填写说明和真实 AstrBot 环境测试清单。

### Changed

- `/tts状态` 增加自动语音访问控制摘要，便于命令行侧快速确认当前规则。
- 自动语音访问控制规则说明统一为“管理员优先、黑名单优先、白名单非空才收紧”。
- Pages 保存配置成功后会重新拉取最新状态，确保 readiness、访问控制预览和 provider 信息不滞后。

### Fixed

- 修复 Pages 访问控制预览在未配置私聊名单时可能触发未定义变量异常的问题。
- 修复 AstrBot WebUI iframe sandbox 环境下原生 `confirm()` 被拦截，导致删除音色按钮无响应的问题。
- 修复 AstrBot Pages iframe 环境下文档外链弹窗、试听自动播放失败提示和音色操作连点竞态的体验问题。
- 增强 AI 导演失败日志，空异常信息也会显示异常类型、provider、音色、情绪、fallback 状态和超时说明。

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
