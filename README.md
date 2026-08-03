# 凝心溯溪-声

> 凝心溯溪系列统一语音中心：集中管理朗读触发、结构化分段、发送节奏、取消语义、输出清理和 TTS 后端；MiMo 音色克隆与 AstrBot 内置 TTS 作为可切换的后端能力按需展开。

> **凝心溯溪系列** 当前完整插件清单为知、言、序、情、境、声、核：各插件职责独立、互不冲突，可按需组合使用，覆盖知识学习、对话调节、身份管理、关系状态、环境感知、语音与更新管理。

| 字 | 模块 | 说明 |
|----|------|------|
| [知](https://github.com/qsbb/astrbot_plugin_active_learner) | 知识学习 | 自动检索注入、多源学习、交叉验证 |
| [言](https://github.com/qsbb/astrbot_plugin_conversation_flow) | 对话调节 | 沉默判断、智能分段、插话衔接 |
| [序](https://github.com/qsbb/astrbot_plugin_identity_guardian) | 身份管理 | 关系感知、权限边界、群组行动 |
| [情](https://github.com/qsbb/astrbot_plugin_relationship) | 关系状态 | 情绪、好感、信任、熟悉度状态记录与只读建议 |
| [境](https://github.com/qsbb/astrbot_plugin_environment_awareness) | 环境感知 | 时间、天气、空气质量、预警与环境关心候选 |
| [声](https://github.com/qsbb/astrbot_plugin_voice_hub) | 语音合成 | 双 TTS 后端、多音色管理、AI 导演（本插件） |
| [核](https://github.com/qsbb/astrbot_plugin_update_manager) | 更新管理 | 安全检查、计划、串行更新与回滚 |

- 仓库：<https://github.com/qsbb/astrbot_plugin_voice_hub>
- MiMo 官方文档：<https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/multimodal-understanding/speech-synthesis-v2.5>

## 项目来源

本版本基于 Justice-ocr 开源的 [astrbot_plugin_mimo_tts_clone](https://github.com/Justice-ocr/astrbot_plugin_mimo_tts_clone) 修改，沿用原项目的 MiMo v2.5 voiceclone 接入、音色管理、概率自动语音、情绪路由、AI 风格导演、Pages 管理和插件服务能力。

在原项目基础上，当前版本主要新增：

- **双 TTS 后端切换**：支持在 MiMo 音色克隆和 AstrBot 内置 TTS 提供商之间切换，无需上传音频即可使用 AstrBot 已配置的 TTS。
- **统一语音中心界面**：通用朗读、触发、分段、延迟、取消和清理设置始终可见；MiMo Key、模型、导演、情绪、迁移、音色与试听仅在 MiMo 后端下显示。
- **OpenAI 兼容外部 API**：开启后插件启动带 Bearer 认证、模型校验、频率限制和输入长度限制的 `POST /v1/audio/speech` 服务；默认仅监听 `127.0.0.1`。
- **一键迁移旧插件配置**：Pages 面板提供按钮，自动读取旧插件 `astrbot_plugin_mimo_tts_clone` 的配置和音色数据并合并到本插件。
- 保留原版概率语音的权限检查、概率抽取、文本清洗、音色与情绪路由、分段合成及回复链处理。
- 增加"概率触发 / LLM 自主决定"互斥模式；概率模式不向 LLM 提供 TTS 工具，LLM 模式不执行概率自动 TTS。
- 移除 `/tts`、`/朗读`、`/语音` 及聊天内音色管理命令，统一通过 Pages、LLM 工具或插件服务调用。

原项目版权归原作者所有，本版本继续遵循 [MIT License](./LICENSE)。

## 适合谁

- 想在 AstrBot 里接入 MiMo 官方 voiceclone TTS 或切换使用 AstrBot 内置 TTS 的用户。
- 想用 Pages 页面管理多个授权音色、默认音色和试听流程的机器人管理员。
- 想通过 LLM 工具按需生成语音，或让普通 LLM 回复按概率转为语音的群聊/私聊场景。
- 想通过 OpenAI 兼容 API 给外部应用提供 TTS 服务的用户。
- 想给其他插件复用统一 TTS 服务能力的插件开发者。

## 功能概览

| 模块 | 能力 |
| --- | --- |
| 双 TTS 后端切换 | 支持在 MiMo 音色克隆和 AstrBot 内置 TTS 提供商之间切换，可在 Pages 面板选择 |
| 官方 API 接入 | 支持 MiMo v2.5 voiceclone，OpenAI-compatible 调用方式 |
| 音色库 | 上传 `mp3` / `wav` 授权样本，本地保存音色元数据 |
| 多音色路由 | 支持全局、群、用户、情绪四类默认音色 |
| 情绪控制 | 支持 `happy`、`sad`、`angry`、`neutral`，可自动轻量识别 |
| 发送前 AI 导演 | 可指定 AstrBot AI 服务商，为每段文本生成隐藏风格指令，并可优化只用于音频的朗读文本 |
| 发送策略 | 支持只发音频、文字+音频、只发文字 |
| TTS 触发方式 | 支持概率触发与 LLM 自主决定，两种模式互斥 |
| 自动语音化 | 概率模式下普通 LLM 回复可按概率转语音，支持群聊/私聊黑白名单和管理员绕过，默认关闭 |
| 后端诊断 | Pages 按当前后端检查 MiMo 链路或 AstrBot TTS 提供商，并自动清理测试音频 |
| 输出清理 | 按保留天数和最大文件数自动清理生成音频 |
| LLM 工具与插件复用 | 统一提供 `voice_hub_speak` 工具，并暴露 `synthesize_text()`、`list_available_voices()`、`resolve_voice_id()` 方法 |
| 可取消交付 | 消费言的交付令牌，在合成前后和逐段发送前检查中断；取消时停止尚未发送的旧语音，并把状态交回当前 LLM，不由声终止整轮。 |
| 完整长音频 | 插件服务与外部 API 会校验并合并全部兼容 WAV 分段，不再只返回第一段 |

## 取消与长文本保证

与“言”同时安装时，声优先消费 `conversation_flow.delivery_plan@1` 中的逻辑分段和可取消
令牌。用户在合成或分段发送期间补充新消息后，言会取消旧令牌；声在开始合成、每段合成完成、
每段发送前后都检查状态，尚未发送的旧语音会停止发送，并将取消状态回传给当前 LLM；声不会主动清空或终止整轮。已经发送的音频无法撤回，Provider 服务端
已经开始的推理也不一定能被取消。

逐段发送时，第一条语音立即发送；第二条及以后会读取当前即将发送的 WAV 时长，并按
“每 1 秒语音等待多少毫秒”模拟 Bot 准备这一条语音所需的时间。默认值 700 表示下一条 10 秒，
发送前严格等待 7 秒。“备用固定等待（毫秒）”只在关闭智能等待或无法读取 WAV 时使用，
不会叠加到正常公式中；两个值都设为 0 即关闭等待。等待期间仍会检查言的取消令牌，
新消息到来时只取消尚未发出的旧语音，不会由声清空或终止整轮对话；取消状态会回传给当前 LLM，
由它决定继续用文字回答、重新调用语音，还是结束本轮。这个过程不额外发起一次 LLM 请求，因此不会为普通回复增加固定延迟。

`text_to_speech()`、`/v1/audio/speech` 等只允许返回单文件的接口在长文本产生多个 WAV 时，会
逐段解析声道数、采样宽度、采样率和压缩类型，全部兼容才合并。格式无效或参数不一致会明确失败；
AstrBot 内置 TTS 路径可关闭分段重试一次。插件不会静默返回第一段，也不会把截断音频报告为成功。

## 界面导览

插件 Pages 以统一语音能力为主线，后端专属设置按选择展开：

```mermaid
flowchart LR
  A["选择语音后端"] --> B["设置统一朗读与触发"]
  B --> C["调整分段 / 等待 / 取消"]
  C --> D["配置当前后端"]
  D --> E["保存并诊断"]
```

页面重点区域：

- `语音后端`：独立选择 MiMo 或 AstrBot TTS；切换后立即收起无关后端字段。
- `统一朗读与触发`：管理 `voice_hub_speak`、回复模式、概率触发或 LLM 自主决定。
- `分段、等待与取消`：显式段落优先，单段过长才按句界兜底；统一设置逐段等待、取消说明和输出清理。
- `外部语音接口`：复用当前后端并集中管理监听、令牌和限流。
- `MiMo 设置`：仅 MiMo 模式显示 Key、模型、AI 导演、情绪路由、旧配置迁移、音色库和试听工作台。
- `AstrBot 设置`：仅 AstrBot 模式显示 TTS 提供商选择，不占用 MiMo 配置区域。

页面采用“凝心溯溪”系列的深色低干扰样式，栏目、运行状态和内置情绪名称优先显示中文；`happy`、`sad`、`angry`、`neutral` 等内部值保持不变，不影响旧配置。打开或刷新页面时，插件配置、AI 服务商和 TTS 提供商会在同一轮并行读取，单个可选列表读取失败不会阻断主配置展示。

## 安装

1. 将本仓库放入 AstrBot 插件目录。

```bash
git clone https://github.com/qsbb/astrbot_plugin_voice_hub.git
```

2. 安装依赖。

```bash
pip install -r requirements.txt
```

3. 在 AstrBot 插件管理中启用本插件。

4. 打开插件 Pages，选择 MiMo 或 AstrBot TTS 后端并设置统一朗读策略。

5. 使用 MiMo 时填写 API Key 并上传已授权的 `mp3` / `wav` 音色样本；使用 AstrBot 时选择已有 TTS 提供商。

6. 保存后点击 `诊断当前后端`；MiMo 模式还可在试听工作台测试音色。

## 调用方式

插件不注册 TTS 聊天命令，也不解析 `/tts`、`/朗读`、`/语音` 或音色管理命令。语音生成通过概率自动 TTS、`voice_hub_speak` LLM 工具、Pages 试听工作台或插件服务方法触发。

`tts_trigger_mode` 是聊天 TTS 的唯一运行模式，两种模式互斥：

- `probability`：从当前 LLM 请求中过滤 `voice_hub_speak`，普通 LLM 回复完成后沿用原版 `auto_tts_probability` 自动语音流程。权限判断、概率抽取、结果识别、文本清洗、音色与情绪路由、分段合成和回复链处理均保持原版逻辑。
- `llm_decides`：向 LLM 保留唯一的 `voice_hub_speak`，由主 LLM 判断是否适合发送语音，并直接提供文本、结构化段落、情绪、音色和风格；该模式完全跳过概率自动 TTS。

`auto_tts_enabled` 仅作为旧配置兼容字段，不再是独立开关。旧配置缺少 `tts_trigger_mode` 时，`auto_tts_enabled=true` 迁移为 `probability`，`auto_tts_enabled=false` 迁移为 `llm_decides`；新配置保存时会自动同步该兼容字段。

`voice_hub_speak` 是唯一的模型可见朗读工具。它兼容旧的 `text` 参数，并支持 `segments` 数组；每个元素包含 `text`，可选覆盖 `emotion`、`voice`、`style`。传入完整 `text` 时，必须保留内部换行和空行。声会优先按显式空行或编号段落分别合成和发送，只有单个段落过长时才按句界兜底。工具直接使用主 LLM 给出的风格并关闭插件的二次 AI 风格导演；至少成功发送一段音频后才标记当前事件，避免自动 TTS 重复处理，同时确保合成或首次发送失败时不会错误阻止后续处理。

工具示例：

```json
{
  "segments": [
    {"text": "第一喵：先说第一部分。", "emotion": "happy"},
    {"text": "第二喵：再说第二部分。", "style": "放慢一点"}
  ]
}
```

## 推荐配置

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| `reply_mode` | `audio_only` | 自动语音化时只保留音频输出 |
| `tts_trigger_mode` | `probability` 或 `llm_decides` | 唯一触发开关；前者沿用原版概率逻辑，后者由 LLM 调用工具 |
| `auto_tts_probability` | `0.1` - `0.3` | 仅概率模式生效，避免群聊中过度刷屏 |
| `llm_tts_judge_enabled` | `false` | 仅概率模式生效。开启后让主 LLM 在回复开头输出朗读意愿标记（`<TTS:yes>`/`<TTS:no:原因>`），太长、含代码、羞耻尴尬或纯功能性内容主动跳过，适合朗读的简短口语直接转语音（不再受概率限制）；标记自动剥离对用户不可见；LLM 未输出标记时退回概率逻辑 |
| `max_voice_file_mb` | `10` | 越大请求体越大，速度也可能变慢 |
| `segment_enabled` | `true` | 启用单段超长时的句界兜底；显式段落仍保持独立 |
| `output_retention_days` | `7` | 防止长期运行占用磁盘 |
| `output_max_files` | `100` | 小型机器人通常足够 |

## MiMo 调用约束

插件按 MiMo v2.5 TTS 官方文档的 voiceclone 方式调用：

- 模型默认使用 `mimo-v2.5-tts-voiceclone`。
- 待朗读文本放在 `messages[].role = assistant` 的 `content` 中。
- 风格、语气、情绪等自然语言控制放在 `role = user` 的消息中。
- 参考音频通过 `audio.voice = data:{MIME_TYPE};base64,{BASE64_AUDIO}` 传入。
- 参考音频仅支持 `mp3` / `wav`，默认限制为 10MB。
- voiceclone 的低延迟流式能力官方暂未开放，因此插件保持非流式合成。

## 发送前 AI 导演

开启后，插件会先调用 AstrBot LLM，为待朗读文本生成一份隐藏的音频导演方案：`style_context` 会作为 MiMo `user` 消息参与合成，`speech_text` 只作为音频朗读文本使用。最终聊天文字仍保持原样，不会被改写。

可以在 Pages 中填写 `AI 服务商 ID`，指定某个 AstrBot AI 服务商专门负责音频导演；留空则使用当前默认 LLM。开启“优化音频朗读文本”后，AI 可以在不改变原意的前提下剔除“嗯、啊、呃、那个、就是说”等无意义填充，并用标点整理停顿，让音频更自然。

建议先在少量群聊/私聊里测试，再开启自动语音化；它会额外消耗一次 LLM 调用。`voice_hub_speak` LLM 工具不会再次调用该导演，避免工具链中的二次风格改写。

## 自动语音访问控制

访问控制只作用于“普通 LLM 回复自动语音化”，不会影响 `voice_hub_speak` LLM 工具或其他插件主动调用 `text_to_speech()`。LLM 工具处理过的事件会被标记，自动语音化会跳过该事件。

规则顺序如下：

- 管理员 ID 永远放行，不受群聊/私聊黑白名单影响。
- 普通用户先匹配黑名单，命中即跳过自动语音化。
- 未命中黑名单后，如果对应范围的白名单非空，则必须命中白名单才会自动语音化。
- 如果对应范围的白名单为空，则该范围默认放行。
- 群聊白名单/黑名单与私聊白名单/黑名单互相独立；只填群聊白名单不会启用私聊白名单限制。
- 名单支持纯 ID 或完整 UMO，例如 `123456789`、`aiocqhttp:GroupMessage:123456789`、`aiocqhttp:FriendMessage:3325363511`。

示例配置：

```text
admin_users:
3325363511

auto_tts_group_whitelist:
123456789

auto_tts_group_blacklist:
aiocqhttp:GroupMessage:987654321

auto_tts_private_whitelist:

auto_tts_private_blacklist:
10001
```

Pages 会在“自动语音访问控制”模块显示当前规则预览；AstrBot 日志中也会显示自动语音化被放行、跳过或拦截的原因，便于确认规则是否生效。

## 给其他插件复用

插件内部提供了面向复用的服务方法：

```python
outputs = await plugin.synthesize_text(
    "晚上好，欢迎回来。",
    voice_name="温柔旁白",
    emotion="neutral",
    context="自然、轻柔、清晰",
)

voices = plugin.list_available_voices()
voice_id = plugin.resolve_voice_id("温柔旁白", user_id="123", group_id="456")
audio_path = await plugin.text_to_speech(
    "晚上好，欢迎回来。",
    emotion="happy",
    target_umo="aiocqhttp:FriendMessage:123",
)
```

这些方法会复用同一套清洗、情绪解析、默认音色优先级、分段和输出清理逻辑。

### PCM WAV 跨插件契约

Quest Bridge 等需要自己负责传输、取消和播放的消费方，应使用事件无关的
`voice.audio_output@1.0`，不要使用会参与 AstrBot 消息交付的 `voice.delivery@1.0`。
消费方按插件 ID `astrbot_plugin_voice_hub` 取得实例后，必须先校验
`voice_audio_output_contract()` 的契约名、主版本和 `render_pcm_wav` capability，再调用：

```python
result = await plugin.render_pcm_wav(
    "晚上好，欢迎回来。",
    emotion="happy",
    voice="心夏",
    context="自然、轻柔、清晰",
    session_id="quest-session-123",
)
```

1.0 请求中 `text` 是唯一必填字段；`emotion`、`voice`、`context`、`session_id`
均为可选字符串，不接受未知字段。提供方固定使用 60 秒超时，外部取消会原样传播
`asyncio.CancelledError`。成功响应示例：

```json
{
  "contract_name": "voice.audio_output",
  "contract_version": "1.0",
  "capability": "render_pcm_wav",
  "status": "ok",
  "error_code": "",
  "path": ".../outputs/mimo_tts_contract_123.wav",
  "container": "wav",
  "encoding": "pcm_s16le",
  "sample_rate": 24000,
  "channels": 1,
  "sample_width": 2,
  "frame_count": 24000,
  "duration_ms": 1000,
  "ownership": "provider_managed",
  "consumer_may_delete": false
}
```

成功前会按文件内容校验 RIFF/WAVE、无压缩 PCM、16-bit 采样和完整帧数据；
`sample_rate` 与 `channels` 是实际值，不保证已经是 Quest 所需的 mono/24000Hz，消费方应在读取后
自行下混与重采样。文件由声复制或保存在自己的 `outputs` 目录，并沿用现有保留天数与数量清理；
消费方只读，不得移动或删除。

失败响应仍包含同一组固定字段，音频字段为空或为 0：

- `unavailable/no_audio_output`：后端没有产生可读文件，可以降级为文字；
- `unavailable/timeout`：60 秒内未完成，可以降级为文字并稍后重试；
- `error/invalid_request`：请求字段类型或必填文本错误；
- `error/unsupported_audio_format`：返回了 MP3、压缩/非 16-bit/损坏或截断 WAV；
- `error/output_storage_error`：无法把外部临时文件纳入声的输出目录；
- `error/synthesis_failed`：TTS 后端、分段合并或其他合成步骤失败。

旧 `text_to_speech()` 为兼容接口，返回值只有文件路径，AstrBot TTS 后端可能返回 MP3，
因此不能把它当作 PCM 保证。契约缺失、主版本不兼容、声明畸形、调用异常或响应字段不完整时，
消费方应把语音能力视为不可用并保留文字回复，不得猜测其他方法。

如果配合 `astrbot_plugin_daily_sharing` 使用，可以在每日分享 Pages 里选择语音 provider：

- `calibrated_tool`：点击“校准语音”，让每日分享自动命中本插件的 `voice_hub_speak` LLM 工具。工具参数为 `text`、`segments`、`emotion`、`voice`、`style`；工具会关闭二次 AI 风格导演并标记事件，防止自动 TTS 重复处理。
- `generic_plugin`：手动配置插件名 `astrbot_plugin_voice_hub`，方法路径 `text_to_speech`，文本参数 `text`，结果字段留空即可。

## 插件信息

| 项目 | 内容 |
| --- | --- |
| 插件名 | `astrbot_plugin_voice_hub` |
| 展示名 | 凝心溯溪-声 |
| 当前版本 | 见 `metadata.yaml`（唯一事实源） |
| 当前维护者 | 凌溪（GitHub：`qsbb`） |
| 原项目作者 | Justice-ocr；原始版权与致谢保留在 LICENSE 和本文末尾 |
| AstrBot 版本 | `>=4.16,<5` |
| 支持平台 | `aiocqhttp` |
| WebUI 图标 | `logo.png`（插件根目录） |
| README 图标 | `assets/icon.svg`（README 资源图标）；横幅为 `assets/readme-hero.svg` |
| Pages 页面目录 | `pages/settings/` |
| 许可证 | `MIT` |

## 系列诊断日志

- 诊断会捕获本插件自有 logger 的 `DEBUG` 到 `CRITICAL` 事件；内存缓冲最多保留 1000 条，日志页单次最多读取 1000 条、浏览器最多暂存 10000 条。每条记录由“核”先显示插件中文名，再显示时间、级别和事件。
本插件提供 `series.diagnostics@1.0` 诊断接口。简单说，它会在内存里留下一小段“出了什么状况”的记录，只保留启动状态、明确标记的关键运行节点和异常告警等真正有检修价值的事件，不把每次普通语音处理都写成流水账。

安装“核”后，可以在“核”的日志页统一查看本插件的诊断记录；没有安装或没有运行“核”也没关系，语音合成、分段发送和外部 API 等功能都会照常工作。诊断通道只读取本插件自身日志，不读取或输出 AstrBot 全局日志；写入前会自动脱敏敏感标识并截断过长内容。记录只存在内存中，插件重载或 AstrBot 重启后会自动清空。

自动捕获事件会保留模块、函数、行号、异常类型，以及最长 2000 字符的脱敏日志正文；在“核”的日志页点击事件即可展开。插件不会额外读取聊天消息，但若本插件原有日志本身含有用户文本片段，该片段会在脱敏、截断后进入内存详情。AI 导演的明确诊断事件仍只记录文本长度；清空或热重载会更换流标识。

## 开发与验证

```bash
python -B -m unittest discover -s tests -v
python -B -m py_compile main.py pages_api.py core/audio_codec.py core/config.py core/emotion.py core/mimo_official_client.py core/pages_upload.py core/style_director.py core/synthesis_context.py core/text_processing.py core/voice_store.py
node --check pages/settings/app.js
```

真实 AstrBot 环境建议测试清单：

- 群聊白名单命中：普通 LLM 回复可以按概率转语音。
- 群聊黑名单命中：普通 LLM 回复保持文字，不触发自动语音。
- 私聊白名单为空：私聊默认不受白名单限制。
- 私聊白名单非空但未命中：私聊普通 LLM 回复不会自动语音化。
- 管理员在黑名单命中场景下仍可自动语音化。
- `voice_hub_speak` 工具生成语音时不触发二次 AI 风格导演，并会让自动 TTS 跳过同一事件。
- 用户在工具合成或逐段发送期间补充消息后，旧语音停止继续交付且不留下已合成临时结果。
- 长文本经 `text_to_speech()` 与外部 API 调用时包含完整内容；不兼容 WAV 分段返回明确错误而非首段。
- `/tts`、`/朗读`、`/语音` 及 TTS 音色管理聊天命令均不会被插件注册或解析。
- 开启 AI 导演调试日志后，日志只显示 provider、音色、情绪、缓存命中和各段文本长度，不显示任何正文。
- 自动语音访问控制日志能看到 allow / skip / denied 的具体原因。

## 维护约定

任何可观察功能、配置项或安全边界的增删改，必须在同一批变更中同步 README、CHANGELOG 的
`Unreleased`、配置 schema 与回归测试。版本号在实现、文档和验证完成后由发布者确认。

## 免责声明

请在使用前认真阅读并确认：

- 本插件仅用于合法、授权、合规的语音合成场景。
- 请只上传你本人声音或已获得明确授权的声音样本。
- 不得使用本插件冒充他人、误导他人、生成未授权语音、实施诈骗、骚扰、诽谤、绕过平台风控或其他违法违规行为。
- 使用者应自行确认音频样本来源、授权范围、使用场景、平台规则和当地法律法规要求。
- MiMo API 的服务能力、计费方式、地区可用性、内容安全规则、模型行为和接口格式以官方平台为准。
- 插件作者不对第三方服务变更、接口不可用、账号封禁、费用支出、数据合规风险、生成内容风险或任何滥用后果承担责任。
- 如果你不确定某个声音样本是否允许使用，请不要上传或合成。

## 致谢

- 特别感谢 [Justice-ocr](https://github.com/Justice-ocr) 开源原项目 [astrbot_plugin_mimo_tts_clone](https://github.com/Justice-ocr/astrbot_plugin_mimo_tts_clone)。本项目基于其代码和设计继续开发，原项目提供了 MiMo voiceclone 接入、概率语音、音色管理、情绪路由、AI 风格导演、Pages 管理及插件复用能力等核心基础。
- 本项目在原项目基础上新增了双 TTS 后端切换（MiMo + AstrBot 内置 TTS）、OpenAI 兼容外部 API 等功能，并更名为 `astrbot_plugin_voice_hub`。
- 感谢 [MiMo Speech Synthesis v2.5](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/multimodal-understanding/speech-synthesis-v2.5) 提供语音合成与 voiceclone 服务及官方文档。
- 感谢 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 提供插件系统、LLM Tool、事件钩子与 Pages 能力。
- Pages 前端视觉参考了 [Firefly](https://github.com/CuteLeaf/Firefly) 的清新玻璃卡片、柔和主题色与轻动效设计思路；未直接引入其 Astro/Tailwind/Svelte 技术栈。

如果你基于本版本继续分发或修改，请保留原项目版权与 MIT License 声明，并在适当位置注明上游项目来源。
