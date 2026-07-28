# Changelog

> 当前系列归属：知、言、序、情、声、核；下方版本号与日期均为真实历史记录，不因当前文档整改而改写。

## 0.7.7 - 2026-07-28

### Security

- OpenAI 兼容 API 默认只监听 `127.0.0.1`，强制独立 Bearer Token，并加入模型白名单、每 IP 限流、1 MiB 请求体和输入长度限制；错误响应不再泄露上游异常。
- MiMo API Key 与外部 API Token 在 Pages 和 AstrBot 原生配置中均按秘密字段处理，读取接口只返回是否已配置；空白保存保留旧密钥。

### Added

- 接入 `voice.delivery` 1.0 与 `ningxin.request_context` 1.0：消费言发布的逻辑分段和中断令牌，合成前后检查取消状态，失败时保留原文字回复。
- 声明 `plugin.health@1.0` 供核执行更新后业务健康检查。

### Fixed

- 外部 API 配置热更新改为等待旧监听完全停止后再启动新实例，并忽略快速连续保存留下的过期启动任务，避免端口绑定竞态。

### Tests

- 新增认证、模型、限流、输入限制、错误脱敏、密钥遮罩、交付取消及 API 串行重启测试。

## 0.7.6 - 2026-07-28

### Changed

- 音频校验改为按文件内容嗅探真实格式：新增 `sniff_audio_format()`，可识别 wav、mp3、silk、amr、ogg、flac、m4a。平台侧语音（QQ/微信常见的 silk、amr）被命名成 `.wav`/`.mp3` 时，报错会指出真实格式并提示需转码，不再笼统报「音频头无效」而误导为文件损坏。
- README 插件信息表不再登记具体版本号，改为指向 `metadata.yaml`（本次整改前停留在 `0.7.5`）；`AstrBot 版本` 一栏由 `>=4.16.0,<5` 统一为系列写法 `>=4.16,<5`。两种写法在 PEP 440 下语义等价，但六个仓库不一致时，读者会误以为下界差异是有意为之，从而推断出错误的兼容性结论。

### Tests

- `tests/test_audio_codec.py` 新增格式嗅探用例与两个诊断用例：silk 内容伪装 `.wav` 应提示真实格式，内容完全无法识别时应给出明确说明。

## 0.7.5 - 2026-07-27

### Changed

- `on_decorating_result` 钩子显式声明 `priority=400`，配合言插件（`astrbot_plugin_conversation_flow`，`priority=600`）先分段后合成的顺序约束，并加注释说明；上游已分段发送并停止事件时安全降级为不合成，异常先执行时也只在现有回复链上追加音频，不与分段逻辑冲突。
- 核对 `metadata.yaml` 的 `icon` 字段：插件根目录 `logo.png` 真实存在且为有效 PNG（256x256），声明保持不变；README 插件信息表中的 WebUI 图标说明与实际一致。
- 修正 README「开发与验证」一节：确认 Pages 目录实际为 `pages/settings/`，统一说明测试框架为 Python 标准库 `unittest`，测试命令精简为 `unittest discover`、`ruff check` 与 `node --check`。
- 版本号从 `v0.7.4` 迁移为三段式无 `v` 前缀格式，升为 `0.7.5`；同步 `metadata.yaml`、`main.py` 的 `__version__` 与 README 当前版本。

## v0.7.4 - 2026-07-27

### Changed

- 设置页视觉风格参考「凝心溯溪-核」更新管理页面，统一为深蓝暗色背景、青绿色强调色和紧凑实色卡片。
- 移除原有玻璃拟态、强装饰渐变和大面积柔和彩色背景，改用细边框、低对比度面板和更紧凑的圆角层级。
- 保留现有三类后端区块、响应式布局和交互状态，未改变设置字段及业务逻辑。
- 版本号从 `0.7.3` 提升至 `0.7.4`。

### Tests

- 更新设置页主题回归断言，覆盖暗色模式、深蓝面板、青绿色强调色及无模糊玻璃效果。

## v0.7.3 - 2026-07-24

### Fixed

- 修复情绪路由与长文本分段被放入两个独立网格后各自只占部分列宽、造成大面积右侧留白的问题。
- MiMo 模式下情绪路由与长文本分段改为同一行的 7/5 栅格；AstrBot 模式下分段卡片自动铺满整行。
- 桌面端分段开关、分段阈值和最大分段数改为横向排列，平板与移动端继续使用响应式单列布局。
- 版本号从 `0.7.2` 提升至 `0.7.3`。

### Tests

- 更新页面布局回归测试，覆盖合并栅格、后端作用域下移与 AstrBot 单卡全宽规则。

## v0.7.2 - 2026-07-24

### Changed

- 设置页按「共用」「MiMo」「AstrBot」三类重新组织：共用设置始终显示，后端专属配置与能力区块随当前 TTS 后端切换并直接隐藏不适用内容。
- 将情绪路由与长文本分段拆分为独立卡片；情绪路由归入 MiMo 专属，双后端均使用的长文本分段归入共用设置。
- AstrBot 模式下不再以灰化但可交互的方式展示 MiMo 音色库、AI 风格导演和试听工作台。
- 版本号从 `0.7.1` 提升至 `0.7.2`。

### Tests

- 新增三类后端作用域、统一显隐和混合卡片拆分的页面回归测试。

## v0.7.1 - 2026-07-24

### Added

- 音色库区块在选择「AstrBot 内置 TTS」后端时，标题下方新增说明条，明确提示当前后端下音色库不生效、音色仅在切换回「MiMo TTS」后端时使用；弱化范围限定在上传面板、音色列表与上传提示，标题区和说明条保持清晰可读。

### Changed

- 设置页「发送策略」卡片移动到「连接配置」卡片下方，两张卡片改为整行全宽、纵向堆叠布局；新增 `.span-12` 栅格全宽规则。
- 版本号从 `0.7.0` 提升至 `0.7.1`。

## v0.7.0 - 2026-07-25

### Added

- 新增 LLM 情绪化朗读判断（`llm_tts_judge_enabled`，默认关闭）。仅在 `probability` 触发方式下生效，开启后引导主 LLM 在回复开头输出 `<TTS:yes>` 或 `<TTS:no:原因>` 标记，太长/含代码/羞耻尴尬/纯功能性内容主动跳过，适合朗读的简短口语直接转语音（不再受概率限制）；标记自动剥离对用户不可见，LLM 未输出标记时退回概率逻辑。
- 新增 `_inject_tts_judge_prompt` 与 `_strip_tts_judge_marker` 辅助方法，分别负责在 `on_llm_request` 注入判断提示词、在 `auto_tts_reply` 中解析标记并执行对应决策。
- Pages 面板新增「LLM 情绪化朗读判断」开关，与触发方式联动，非 probability 模式下自动禁用弱化。
- 104 个单元测试全部通过，覆盖配置解析、提示词注入、标记剥离、yes/no/none 三个分支。

### Changed

- 版本号从 `0.6.2` 提升至 `0.7.0`。
- `main.py` 增加 `__version__` 模块变量，`@register` 版本改为引用该变量。

### Fixed

- 修复在 AstrBot 插件设置页保存配置时出现的 `AxiosError: Request failed with status code 400`：`_pages_save_config` 兼容 Bridge 传入的 JSON 字符串请求体，非法或非对象载荷返回明确的 400；前端对返回的 JSON 字符串做兼容解析。
- 群聊/私聊黑白名单与管理员名单改为在前端统一拆分为数组后提交，支持逗号、中文逗号与换行分隔并自动去重。
- `_conf_schema.json` 中 `auto_tts_probability` 的类型从 `string` 修正为 `float`，默认值同步为数值 `0.0`。
- 修复设置页布局问题：状态区迁移操作横跨整行、API 地址/端口双列排布、长开关说明文案不再被裁切，并补齐 761–1020px 平板断点响应式。

## v0.6.2 - 2026-07-22

### Fixed

- 全面修正品牌名称残留：Pages 页面标题从「MiMo Sound Studio」改为「Voice Hub 语音中枢」，eyebrow 文案从「Firefly Inspired Voice Console」改为「Dual Backend Voice Console」。
- metadata.yaml 的 `display_name` 改为「Voice Hub 语音中枢」，`short_desc` 同步更新。
- `core/api_server.py` 日志前缀和服务名从 `[mimo-tts]`/`mimo-tts` 改为 `[voice-hub]`/`voice-hub`。
- `pages_api.py` 日志前缀和路由描述从「MiMo TTS」改为「Voice Hub」。
- README 横幅 alt、项目来源、适合谁等章节更新，反映双 TTS 后端和外部 API 等新功能。
- `assets/readme-hero.svg` 标题和描述更新为「Voice Hub」。
- `docs/implementation-plan.md` 标题更新。
- 测试断言同步更新。

## v0.6.1 - 2026-07-22

### Added

- Pages 面板「工作台状态」区块新增「从旧插件迁移配置」按钮，一键读取旧插件 `astrbot_plugin_mimo_tts_clone` 的 config.json 和音色数据并合并到本插件，已存在的数据不会被覆盖。

### Fixed

- 修复 AstrBot TTS 提供商下拉列表为空的问题：`list_astrbot_tts_providers` 改为优先从 `providers_config` 读取配置，即使提供商实例化失败（如 Missing credentials）也能列出来供选择。
- 修正 TTS 后端选择器提示：明确说明只有「MiMo TTS」后端需要上传授权参考音频，「AstrBot 内置 TTS」无需上传音频；切换到 AstrBot 后端时音色库区块会自动弱化显示。

## v0.6.0 - 2026-07-22

### Added

- 新增双 TTS 后端切换：支持在 MiMo 音色克隆和 AstrBot 内置 TTS 提供商之间切换。
- 新增 `tts_backend` 配置项（`mimo` / `astrbot`），可在 Pages 面板选择。
- 新增 `astrbot_tts_provider_id` 配置项，可指定使用哪个 AstrBot TTS 提供商。
- Pages 面板新增 TTS 后端选择器和提供商下拉列表。
- 项目更名为 `astrbot_plugin_voice_hub`，旧数据目录自动迁移。

### Changed

- 项目从 `astrbot_plugin_mimo_tts_clone` 更名为 `astrbot_plugin_voice_hub`。
- 日志前缀从 `[mimo-tts]` 改为 `[voice-hub]`。
- 仓库地址改为 `https://github.com/qsbb/astrbot_plugin_voice_hub`。

## v0.5.3 - 2026-07-22

### Changed

- Pages 面板「API 调用地址」改用 `127.0.0.1` 而非 `window.location.hostname`，复制后可直接粘贴到本机 AstrBot openai_tts 提供商的 Base URL。
- 「一键诊断」在外部 TTS API 开启时，会顺带通过 HTTP 调用本地 `/v1/audio/speech` 接口验证可达性和响应，诊断结果（含耗时）追加到提示消息中。

## v0.5.2 - 2026-07-22

### Fixed

- 修复 `api_server_enabled` 开启后重启 AstrBot 时 API server 不自动启动的问题：`_ensure_api_server` 不再因事件循环未运行而跳过，改为创建 task 排队，循环开始运行后自动执行。
- 在 `on_llm_request` 钩子开头增加 `_ensure_api_server()` fallback 调用，确保 `__init__` 阶段未能启动的 server 在事件循环中补启动。
- `api_server.py` 的 `start()` 方法增加端口冲突保护，避免 `__init__` task 与钩子 fallback 竞态时重复绑定端口导致崩溃。

## v0.5.1 - 2026-07-22

### Added

- Pages 面板在 API 服务开关下方新增「API 调用地址」只读输入框和「复制链接」按钮，开启开关后自动生成 `http://当前主机:端口/v1` 地址，一键复制到剪贴板（带 `document.execCommand` 兜底）。
- 新增 API Key 填写提示：说明在 AstrBot 的 openai_tts 提供商配置中 API Key 填任意字符串（如 `sk-anything`）即可，避免触发 `Missing credentials` 实例化错误。

## v0.5.0 - 2026-07-22

### Added

- 新增 OpenAI 兼容的外部 TTS API 功能：开启 `api_server_enabled` 后插件启动独立 HTTP 服务，暴露 `POST /v1/audio/speech` 接口，可被任意 OpenAI TTS 客户端直接调用。
- 新增 `GET /v1/models` 接口，返回当前模型信息（兼容 OpenAI SDK 的模型列表请求）。
- 新增 `api_server_host` / `api_server_port` 配置项，默认监听 `0.0.0.0:9960`。
- Pages 面板新增 API 服务开关和监听地址/端口配置。
- `requirements.txt` 新增 `aiohttp>=3.9` 依赖。

### Notes

- API 不校验 Authorization 头和 model 字段，方便外部工具直接调用；`voice` 字段填插件音色名或 ID，匹配不到时使用默认音色。
- 响应为 `audio/wav` 二进制流，兼容 OpenAI Python SDK 的 `client.audio.speech.create(...)` 调用方式。
- 服务在插件 `terminate` 时自动关闭，热重载时若端口/host 未变则不重启。
- 默认关闭，需在 Pages 面板或配置中手动开启。

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
