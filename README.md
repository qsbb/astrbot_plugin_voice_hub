# MiMo TTS Voice Clone for AstrBot

基于 MiMo 官方 `mimo-v2.5-tts-voiceclone` 的 AstrBot TTS 音色克隆插件，支持 Pages 管理、多音色切换、情绪音色路由、文本清洗和长文本分段。

## 功能

- 插件 Pages 管理页：配置 MiMo API Key、模型、并发、情绪路由和分段参数。
- 上传 `mp3` / `wav` 参考音频并保存为本地音色库。
- 支持全局、群、用户、情绪四类默认音色。
- 支持每个音色配置风格指令和 MiMo assistant 文本标签。
- `/tts` 命令支持 `-v` 指定音色、`-e` 指定情绪、`-c` 临时风格指令。
- 生成前自动清理 URL、代码块和控制杂质，保留 MiMo 可用风格标签。
- 长文本可按标点自动分段，逐段合成发送。

## MiMo 调用约束

插件按 MiMo v2.5 TTS 官方文档的 voiceclone 方式调用：

- 模型默认使用 `mimo-v2.5-tts-voiceclone`。
- 待朗读文本放在 `messages[].role = assistant` 的 `content` 中。
- 风格、语气、情绪等自然语言控制放在 `role = user` 的消息中。
- 参考音频通过 `audio.voice = data:{MIME_TYPE};base64,{BASE64_AUDIO}` 传入。
- 参考音频仅支持 `mp3` / `wav`，默认限制为 10MB。
- voiceclone 的低延迟流式能力官方暂未开放，因此插件保持非流式合成。

参考文档：[MiMo Speech Synthesis v2.5](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/multimodal-understanding/speech-synthesis-v2.5)

## 命令

```text
/tts 文本
/tts -v 音色名 文本
/tts -e happy 文本
/tts -v 音色名 -e sad -c "轻声、慢速" 文本
/tts音色列表
/tts设置音色 音色名
/tts默认音色 音色名
/tts群默认音色 音色名
/tts情绪音色 happy 音色名
/tts状态
```

情绪支持：`happy`、`sad`、`angry`、`neutral`。如果没有手动指定 `-e`，插件会用关键词做轻量级情绪判断。

## 安装

1. 将本插件目录放入 AstrBot 插件目录。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 在插件配置或 Pages 管理页填写 MiMo API Key。
4. 在 Pages 上传已获授权的 `mp3` 或 `wav` 声音样本。
5. 可选：为 `happy`、`sad`、`angry`、`neutral` 分别设置默认音色。

## 验证

```bash
python -B -m unittest discover -s tests -v
```

## 合规提示

请只上传你本人或已获得明确授权的声音样本。不要使用该插件冒充他人、生成未授权语音，或用于欺骗、骚扰、诈骗等用途。
