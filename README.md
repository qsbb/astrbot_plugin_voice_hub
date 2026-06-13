# MiMo TTS Voice Clone for AstrBot

基于 MiMo 官方 `mimo-v2.5-tts-voiceclone` API 的 AstrBot TTS 音色克隆插件。

## 功能

- 插件 Pages 管理页
- MiMo API Key、模型和并发配置
- `mp3` / `wav` 参考音频上传
- 本地多音色库
- 全局、群、用户默认音色切换
- 页面试听
- 聊天命令朗读

## 命令

```text
/tts 文本
/tts -v 音色名 文本
/tts -v 音色名 -c 风格指令 文本
/tts音色列表
/tts设置音色 音色名
/tts默认音色 音色名
/tts群默认音色 音色名
```

## 安装

1. 将本插件目录放入 AstrBot 插件目录。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 在插件配置或 Pages 管理页填写 MiMo API Key。
4. 在 Pages 上传已获授权的 `mp3` 或 `wav` 声音样本。

## 验证

```bash
python -B -m unittest discover -s tests -v
```

## 合规提示

请只上传你本人或已获得明确授权的声音样本。不要使用该插件冒充他人或生成未经授权的语音内容。
