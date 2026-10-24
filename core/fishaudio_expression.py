# -*- coding: utf-8 -*-
"""FishAudio 表现力控制（从 astrbot_plugin_private_companion 的 TTS 强化模块移植）。

语义与上游保持一致：
- S2/S2.1 使用方括号自然语言控制（如 ``[开心]``、``[whispering]``），S1 旧版只放行
  官方固定英文圆括号标签（如 ``(joyful)``）；
- 自动模式不给强呼吸效果（喘息/喘气/呻吟），普通语气词不当作叹气；
- 每句最多保留 3 个控制词，连续堆叠的相邻控制只保留第一个；
- 手动模式不自动补标，并保留已有合法控制词；
- 上游用实例方法读取配置，这里改为纯函数 + ``emotion_mode`` 参数，
  便于 voice_hub 无事件环境复用与单测。
"""
from __future__ import annotations

import re

S1_CUE_PATTERN = re.compile(r"\(([^()\n]{1,24})\)", re.IGNORECASE)
S2_CUE_PATTERN = re.compile(r"\[([^\[\]\n]{1,40})\]")
FISH_AUDIO_MODELS = {"s1", "s2-pro", "s2.1-pro", "s2.1-pro-free"}
EMOTION_MODES = {"balanced", "expressive", "manual"}

S1_CUES = frozenset({
    "angry", "sad", "excited", "surprised", "satisfied", "delighted",
    "scared", "worried", "upset", "nervous", "frustrated", "depressed",
    "empathetic", "embarrassed", "disgusted", "moved", "proud", "relaxed",
    "grateful", "confident", "interested", "curious", "confused", "joyful",
    "disdainful", "unhappy", "anxious", "hysterical", "indifferent",
    "impatient", "guilty", "scornful", "panicked", "furious", "reluctant",
    "keen", "disapproving", "negative", "denying", "astonished", "serious",
    "sarcastic", "conciliative", "comforting", "sincere", "sneering",
    "hesitating", "yielding", "painful", "awkward", "amused",
    "in a hurry tone", "shouting", "screaming", "whispering", "soft tone",
    "laughing", "chuckling", "sobbing", "crying loudly", "sighing", "panting",
    "groaning", "crowd laughing", "background laughter", "audience laughing",
})
CUE_ALIASES = {
    "开心": "happy", "高兴": "happy", "快乐": "happy", "嬉しい": "happy",
    "喜び": "happy", "难过": "sad", "難過": "sad", "悲しい": "sad",
    "伤心": "sad", "傷心": "sad", "生气": "angry", "生氣": "angry",
    "怒り": "angry", "兴奋": "excited", "興奮": "excited",
    "惊讶": "surprised", "驚訝": "surprised", "驚き": "surprised",
    "平静": "calm", "平靜": "calm", "落ち着く": "calm",
    "紧张": "nervous", "緊張": "nervous", "害怕": "scared", "怖い": "scared",
    "担心": "worried", "擔心": "worried", "心配": "worried",
    "委屈": "upset", "拗ねる": "upset", "沮丧": "frustrated",
    "沮喪": "frustrated", "害羞": "embarrassed", "照れ": "embarrassed",
    "恥ずかしい": "embarrassed", "厌恶": "disgusted", "嫌悪": "disgusted",
    "感动": "moved", "感動": "moved", "骄傲": "proud", "誇らしい": "proud",
    "放松": "relaxed", "放鬆": "relaxed", "感谢": "grateful",
    "感謝": "grateful", "自信": "confident", "好奇": "curious",
    "困惑": "confused", "懐かしい": "nostalgic", "怀旧": "nostalgic",
    "懷舊": "nostalgic", "眠い": "sleepy", "困倦": "sleepy",
    "考え込む": "thoughtful", "沉思": "thoughtful", "耳语": "whispering",
    "耳語": "whispering", "囁き": "whispering", "小声": "soft tone",
    "小聲": "soft tone", "大喊": "shouting", "叫ぶ": "shouting",
    "笑": "laughing", "笑う": "laughing", "轻笑": "chuckling",
    "輕笑": "chuckling", "叹气": "sighing", "嘆氣": "sighing",
    "ため息": "sighing", "叹息": "sighing", "嘆息": "sighing",
    "sigh": "sighing", "哭泣": "sobbing", "すすり泣く": "sobbing",
    "喘气": "panting", "喘氣": "panting", "喘息": "panting",
    "喘ぎ": "panting", "breathing": "panting", "heavy breathing": "panting",
    "gasping": "panting", "呻吟": "groaning", "うめき声": "groaning",
    "あくび": "yawning",
    "哈欠": "yawning", "停顿": "break", "停頓": "break", "間": "break",
}
AUTO_BLOCKED_EFFECTS = frozenset({"panting", "groaning"})
EXPLICIT_SIGH_PATTERN = re.compile(
    r"叹(?:了)?(?:一口|口)?气|嘆(?:了)?(?:一口|口)?氣|叹息|嘆息|"
    r"ため息(?:を)?|sigh(?:ed|ing|s)?\b",
    flags=re.IGNORECASE,
)
S1_ALIAS_OVERRIDES = {
    "happy": "joyful",
    "calm": "relaxed",
    "sleepy": "soft tone",
    "thoughtful": "hesitating",
    "nostalgic": "moved",
    "yawning": "soft tone",
    "break": "hesitating",
}
# voice_hub 的 emotion 参数（happy/sad/angry/neutral）到控制词的映射
EMOTION_TO_CUE = {"happy": "happy", "sad": "sad", "angry": "angry", "neutral": ""}


def normalize_emotion_mode(value: str) -> str:
    mode = str(value or "balanced").strip().lower()
    return mode if mode in EMOTION_MODES else "balanced"


def canonical_cue(label: str, *, s1: bool) -> str:
    """把任意写法的控制词规范为 Fish 官方可接受的形态；非法返回空串。"""
    raw = re.sub(r"\s+", " ", str(label or "").strip())
    if not raw:
        return ""
    if s1:
        canonical = CUE_ALIASES.get(raw, raw.lower() if raw.isascii() else raw)
        canonical = S1_ALIAS_OVERRIDES.get(canonical, canonical)
        return canonical if canonical in S1_CUES else ""
    # S2 官方接受简短自然语言控制；中日文标签按朗读语言保留，不强行翻译成英文。
    canonical = raw.lower() if raw.isascii() else raw
    if (
        len(canonical) > 40
        or re.fullmatch(r"[\d\W_]+", canonical, flags=re.UNICODE)
        or re.search(r"(?:https?://|www\.|<|>|=|\{|\}|\[|\])", canonical, flags=re.IGNORECASE)
        or re.match(r"^(?:at|qq|pctts|ttsblock)\s*:", canonical, flags=re.IGNORECASE)
    ):
        return ""
    return canonical


def _cue_effect_key(label: str) -> str:
    raw = re.sub(r"\s+", " ", str(label or "").strip())
    if not raw:
        return ""
    return CUE_ALIASES.get(raw, raw.lower() if raw.isascii() else raw)


def _auto_cue_allowed(label: str, *, context: str, mode: str) -> bool:
    if mode == "manual":
        return True
    effect = _cue_effect_key(label)
    if effect in AUTO_BLOCKED_EFFECTS:
        return False
    if effect == "sighing" and not EXPLICIT_SIGH_PATTERN.search(str(context or "")):
        return False
    return True


def normalize_s2_cues(text: str, *, mode: str = "balanced") -> str:
    """规范 S2 文本里的方括号控制词：限每句 3 个、去堆叠、去强呼吸效果。"""
    source = str(text or "")
    segments = re.split(r"([。！？.!?]+)", source)
    normalized: list[str] = []
    mode = normalize_emotion_mode(mode)
    for segment in segments:
        if not segment or re.fullmatch(r"[。！？.!?]+", segment):
            normalized.append(segment)
            continue
        cue_count = 0
        last_cue_end = -1
        cue_run_has_kept = False
        segment_context = S2_CUE_PATTERN.sub("", segment)

        def repl(match: re.Match[str]) -> str:
            nonlocal cue_count, last_cue_end, cue_run_has_kept
            if match.end() < len(segment) and segment[match.end()] == "(":
                return ""
            adjacent = last_cue_end >= 0 and not segment[last_cue_end:match.start()].strip()
            if not adjacent:
                cue_run_has_kept = False
            last_cue_end = match.end()
            canonical = canonical_cue(match.group(1), s1=False)
            if not canonical or cue_count >= 3:
                return ""
            if not _auto_cue_allowed(canonical, context=segment_context, mode=mode):
                return ""
            if mode != "manual" and adjacent and cue_run_has_kept:
                return ""
            cue_count += 1
            cue_run_has_kept = True
            return f"[{canonical}]"

        normalized_segment = S2_CUE_PATTERN.sub(repl, segment)
        normalized_segment = re.sub(r"\[[^\[\]\n]{41,200}\]", "", normalized_segment)
        normalized.append(normalized_segment)
    return "".join(normalized)


def normalize_s1_cues(text: str) -> str:
    """S1 只放行官方固定圆括号标签；别名映射后不合法的控制词直接移除。"""
    source = str(text or "")

    def repl(match: re.Match[str]) -> str:
        canonical = canonical_cue(match.group(1), s1=True)
        return f"({canonical})" if canonical else ""

    source = S1_CUE_PATTERN.sub(repl, source)
    source = S2_CUE_PATTERN.sub(repl, source)
    return source


def normalize_cues(text: str, *, s1: bool, mode: str = "balanced") -> str:
    return normalize_s1_cues(text) if s1 else normalize_s2_cues(text, mode=mode)


def context_emotion_cues(text: str, *, mode: str) -> list[str]:
    """从上下文推断一个兜底控制词（与上游规则一致，最多返回 1 个）。"""
    source = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not source:
        return []

    emotion_rules = (
        ("angry", ((r"气死|氣死|生气|生氣|火大|滚开|滾開|混蛋|ふざけ|むかつ|怒って|怒る", 4),)),
        ("upset", (
            (r"笨蛋|ばか|バカ|都说了|都說了|怎么还|怎麼還|不许|不許|不准|烦死|煩死|讨厌啦|討厭啦|やめて|って言った|しつこい|ひどい", 3),
            (r"(?:^|[\s，,。.!！?？…~～])(哼|ふん|むぅ|まったく)(?:[\s，,。.!！?？…~～]|$)", 1),
        )),
        ("sad", ((r"难过|難過|伤心|傷心|想哭|泪|淚|悲しい|つらい|寂しい|泣きたい", 3),)),
        ("worried", ((r"担心|擔心|小心一点|小心一點|没事吧|沒事吧|还好吗|還好嗎|心配|大丈夫[？?]|気をつけ", 3),)),
        ("surprised", ((r"竟然|居然|真的吗|真的嗎|真的假的|没想到|沒想到|えっ|ええっ|まさか|本当[？?]", 3),)),
        ("excited", ((r"好期待|太棒了|好耶|冲冲冲|衝衝衝|迫不及待|楽しみ|わくわく|最高|やった", 3),)),
        ("happy", ((r"开心|開心|高兴|高興|喜欢你|喜歡你|爱你|愛你|太好了|嬉しい|楽しい|大好き|よかった", 3),)),
        ("grateful", ((r"谢谢你|謝謝你|感谢|感謝|多亏你|多虧你|ありがとう|助かった", 3),)),
        ("comforting", ((r"别怕|別怕|没关系|沒關係|我陪你|我在呢|慢慢来|慢慢來|そばにいる|無理しないで|安心して", 3),)),
        ("sleepy", ((r"好困|困死|想睡|睡着|睡著|打哈欠|眠い|眠たい|寝たい|あくび", 3),)),
        ("embarrassed", ((r"害羞|羞死|脸红|臉紅|不好意思|别看|別看|被发现|被發現|恥ずか|照れ|顔が赤|見ないで", 3),)),
    )
    scores: dict[str, int] = {}
    for cue, patterns in emotion_rules:
        scores[cue] = sum(
            weight for pattern, weight in patterns if re.search(pattern, source, flags=re.IGNORECASE)
        )

    playful_complaint = bool(re.search(r"嘛|啦|呀|哦|呜|嗚|唔|じゃん|だもん|バカ|ばか|[~～]", source))
    if scores.get("upset", 0) >= 3 and scores.get("angry", 0) < scores["upset"] and playful_complaint:
        scores["embarrassed"] = max(scores.get("embarrassed", 0), 2)

    priority = (
        "angry", "upset", "sad", "worried", "surprised", "excited",
        "happy", "grateful", "comforting", "sleepy", "embarrassed",
    )
    primary_candidates = [cue for cue in priority if scores.get(cue, 0) >= 3]
    primary = (
        max(primary_candidates, key=lambda cue: (scores[cue], -priority.index(cue)))
        if primary_candidates
        else ""
    )

    tone_rules = (
        ("sighing", EXPLICIT_SIGH_PATTERN.pattern),
        ("whispering", r"悄悄|小声|小聲|耳边|耳邊|こっそり|囁|小声で"),
        ("laughing", r"哈哈|嘿嘿|嘻嘻|笑死|ふふ|はは|あはは|笑っ"),
        ("sobbing", r"哭了|哭泣|抽泣|泣いて|すすり泣|しくしく"),
        ("soft tone", r"晚安|慢慢说|慢慢說|轻声|輕聲|おやすみ|優しく|そっと"),
    )
    tones = [cue for cue, pattern in tone_rules if re.search(pattern, source, flags=re.IGNORECASE)]
    # 兜底只能给整句加前缀，所以刻意只选一个控制词；更细的句级表现力
    # 应由上游转换/导演模型逐句产出，在这里堆标签会造成呼吸声副作用。
    if tones:
        return tones[:1]
    return [primary] if primary else []


def apply_emotion_control(
    text: str,
    *,
    s1: bool,
    mode: str = "balanced",
    source_text: str = "",
    emotion: str = "",
) -> tuple[str, list[str]]:
    """合成前兜底：已有合法控制词时保持原样，否则推断/映射一个前缀控制词。

    返回 (处理后的文本, 实际应用的控制词列表)。
    """
    spoken = str(text or "").strip()
    if not spoken:
        return spoken, []
    mode = normalize_emotion_mode(mode)
    if mode == "manual":
        return spoken, []

    cue_pattern = S1_CUE_PATTERN if s1 else S2_CUE_PATTERN
    for match in cue_pattern.finditer(spoken):
        if canonical_cue(match.group(1), s1=s1):
            return spoken, []

    context = f"{source_text}\n{spoken}".strip()
    context = S2_CUE_PATTERN.sub("", context)
    context = S1_CUE_PATTERN.sub("", context)
    inferred = list(context_emotion_cues(context, mode=mode))
    mapped = EMOTION_TO_CUE.get(str(emotion or "").strip().lower(), "")
    if mapped:
        inferred.insert(0, mapped)
    canonical: list[str] = []
    for cue in inferred:
        normalized = canonical_cue(cue, s1=s1)
        if normalized and normalized not in canonical:
            canonical.append(normalized)
    if not canonical:
        return spoken, []

    if s1:
        prefix = "".join(f"({cue})" for cue in canonical)
    else:
        prefix = "".join(f"[{cue}]" for cue in canonical)
    return f"{prefix}{spoken}", canonical


# Drama 3（自建 fish-speech 服务器侧新模型）表演指令：方括号自然语言 +
# 成对的局部语气标签；仅 model=drama-3 时注入（移植自临 astrbot_host/fish_audio.py）。
DRAMA3_DIRECTION = (
    "本轮朗读引擎支持 Drama 3 表演指令。只在朗读文本内根据角色此刻的情绪和对话，"
    "自然地添加少量方括号指令，例如 [温柔地，像贴近对方说话]、[轻笑]、[pause]；"
    "指令可用中文或朗读语种，不必每句话都加，也不要把动作描写当成要念的台词。"
    "局部语气可用成对的 <whisper>、<emphasis>、<soft>、<fast>、<slow>、<stress>、<forceful> "
    "包住对应词句，例如 [轻声安慰]没关系，<soft>慢慢来。</soft>。"
    "这些表演指令仅交给语音合成，不会显示在聊天正文里；"
    "保持本轮指定的朗读语种、角色声线和原意，不自行添加其他说话人。"
)

S2_DIRECTION = (
    "Fish Audio S2/S2.1 使用简短方括号自然语言情绪控制，如 [开心]、[难过]、[轻笑]、"
    "[whispering]；控制词优先使用朗读语言，并紧贴放在实际生效的短语前。"
    "同一位置只放一个标签，不要在句首连续堆叠多个标签。"
    "停顿词、拖音以及“唔、呜、うーん”等普通语气词不要写成控制词。"
)

S1_DIRECTION = (
    "Fish Audio S1 旧版只使用官方英文圆括号固定控制标记，如 (joyful)、(sad)、"
    "(whispering)、(sighing)；句级情绪放在句首，每句只选一个主要情绪，"
    "避免冲突和滥用。"
)

MANUAL_MODE_NOTE = "当前为手动模式：只保留你写出的合法控制词，系统不会自动补标。"


def expression_direction(*, model: str, mode: str) -> str:
    """按模型与情绪档位返回给主模型的控制词语法说明；非 fishaudio 返回空串。"""
    mode = normalize_emotion_mode(mode)
    model = str(model or "").strip().lower()
    if model == "s1":
        base = S1_DIRECTION
    elif model == "drama-3":
        return DRAMA3_DIRECTION + (
            f" {MANUAL_MODE_NOTE}" if mode == "manual" else ""
        )
    else:
        base = S2_DIRECTION
    if mode == "manual":
        return f"{base} {MANUAL_MODE_NOTE}"
    return base


def emotion_tag_syntax_note(*, s1: bool) -> str:
    return "英文圆括号" if s1 else "方括号"
