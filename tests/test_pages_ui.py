from pathlib import Path
import unittest


PAGES_DIR = Path(__file__).resolve().parents[1] / "pages" / "settings"
MOJIBAKE_MARKERS = ("闂", "闁", "閻", "濮", "閸", "濞", "缂", "閺")


class PagesUITests(unittest.TestCase):
    def test_settings_page_uses_glass_aurora_shared_shell(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        shared = (PAGES_DIR / "series-ui.css").read_text(encoding="utf-8")

        self.assertIn("凝心溯溪-声", html)
        self.assertIn("凝心溯溪 · 声", html)
        self.assertIn("声 · 统一语音中心", html)
        self.assertIn('data-series-ui="1"', html)
        self.assertIn('<link rel="stylesheet" href="./series-ui.css?v=', html)
        self.assertIn('<link rel="stylesheet" href="./style.css?v=', html)
        self.assertLess(
            html.index('<link rel="stylesheet" href="./style.css?v='),
            html.index('<link rel="stylesheet" href="./series-ui.css?v='),
        )
        self.assertIn('<script src="./series-ui.js?v=', html)
        self.assertRegex(shared, r"凝心 UI 1\.0(\.\d+)? — Glass Aurora")
        self.assertIn("studio-shell", html)
        self.assertIn("studio-hero", html)
        self.assertIn("workflow-strip", html)
        self.assertIn("top-gradient-highlight", html)
        self.assertIn("统一朗读与触发", html)
        self.assertIn("诊断当前后端", html)
        self.assertIn("var(--si-", css)
        self.assertNotIn("color-scheme: dark", css)
        self.assertIn("card-rise", css)
        self.assertIn("wave-breathe", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertNotIn("backdrop-filter: blur", css)
        self.assertIn("upload-fields", html)
        self.assertIn("voice-upload-actions", html)
        self.assertIn("repeat(auto-fit", css)
        self.assertIn("save-state", html)
        self.assertIn("readiness-list", html)
        self.assertIn("ai-style-director-provider-select", html)
        self.assertIn("ai-style-director-debug-log", html)

    def test_settings_page_loads_astrbot_bridge_before_app(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        bridge_script = '<script src="/api/plugin/page/bridge-sdk.js"></script>'
        app_script = '<script src="./app.js?v='

        self.assertIn(bridge_script, html)
        self.assertIn(app_script, html)
        self.assertLess(html.index(bridge_script), html.index(app_script))

    def test_settings_frontend_copy_is_not_mojibake(self):
        combined = "\n".join(
            (PAGES_DIR / name).read_text(encoding="utf-8")
            for name in ("index.html", "app.js")
        )

        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, combined)
        self.assertIn("自动", combined)
        self.assertIn("未设置", combined)
        self.assertIn("请在 AstrBot 插件管理页中打开", combined)
        self.assertNotIn("AstrBot Pages bridge unavailable", combined)

    def test_settings_app_waits_for_late_bridge_injection(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("async function resolveBridge", js)
        self.assertIn("waitForAstrBotBridge", js)
        self.assertNotIn("const bridge = window.AstrBotPluginPage ||", js)

    def test_settings_app_guides_user_actions(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("function markDirty", js)
        self.assertIn("function setBusy", js)
        self.assertIn("function validateVoiceUpload", js)
        self.assertIn("function uploadVoiceSample", js)
        self.assertIn("function readFileAsBase64", js)
        self.assertIn("function voiceMetadataPayload", js)
        self.assertIn("function syncVoiceMetadata", js)
        self.assertIn("元数据同步失败", js)
        self.assertIn("音色已上传，但刷新列表失败", js)
        self.assertIn("upload_voice_sample_json", js)
        self.assertIn("兼容上传", js)
        self.assertIn("function updateActionAvailability", js)
        self.assertIn("function renderReadiness", js)
        self.assertIn("function previewDisabledReason", js)
        self.assertIn("function setPreviewHint", js)
        self.assertIn("readiness", js)
        self.assertIn("function testConnection", js)
        self.assertIn("test_connection", js)
        self.assertIn("reply_mode", js)
        self.assertIn("tts_trigger_mode", js)
        self.assertIn("auto_tts_probability", js)
        self.assertIn("llm_tts_judge_enabled", js)
        self.assertIn("auto_tts_group_whitelist", js)
        self.assertIn("auto_tts_private_blacklist", js)
        self.assertIn("list_ai_providers", js)
        self.assertIn("function renderProviderSelect", js)
        self.assertIn("function bindProviderSelect", js)
        self.assertIn("ai_style_director_provider_id", js)
        self.assertIn("ai_style_director_debug_log", js)
        self.assertLess(
            js.index("updateActionAvailability();"), js.index("await refresh();")
        )
        self.assertIn("lastUploadedVoiceId", js)
        self.assertIn("请填写音色名称", js)
        self.assertIn("只支持 mp3 / wav 音频", js)
        self.assertIn("aria-busy", js)
        self.assertIn("is-busy", css)
        self.assertIn("is-dirty", css)
        self.assertIn("field-hint", css)
        self.assertIn("readiness-item", css)
        self.assertIn("policy-grid", html)
        self.assertIn("access-card", html)
        self.assertIn("access-summary", html)
        self.assertIn("admin-users", html)
        self.assertIn('name="tts-trigger-mode" value="probability"', html)
        self.assertIn('name="tts-trigger-mode" value="llm_decides"', html)
        self.assertIn("不向 LLM 提供语音工具", html)
        self.assertIn("只允许 LLM 调用语音工具", html)
        self.assertIn("当前按概率把普通回复转成语音", html)
        self.assertIn('id="llm-tts-judge-enabled"', html)
        self.assertIn("让 LLM 判断这条回复适不适合朗读", html)
        self.assertIn("llm-tts-judge-field", css)
        self.assertNotIn('id="auto-tts-enabled"', html)
        self.assertNotIn("auto-tts-enabled", js)
        self.assertIn("auto-tts-group-whitelist", html)
        self.assertIn("auto-tts-private-blacklist", html)
        self.assertIn("function renderAccessControl", js)
        self.assertIn("access_control", js)
        self.assertIn("access-summary-list", js)
        self.assertIn("access-summary-core", css)
        self.assertIn("access-summary-list", css)

    def test_settings_serializes_lists_and_accepts_json_string_responses(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("function parseJsonResponse", js)
        self.assertIn("return JSON.parse(value);", js)
        self.assertIn("function listValue", js)
        self.assertIn(r".split(/[,\r\n]/)", js)
        self.assertIn("auto_tts_group_whitelist: listValue", js)
        self.assertIn("admin_users: listValue", js)
        self.assertIn("parseJsonResponse(await bridge.apiPost", js)

    def test_settings_uses_chinese_labels_and_safe_dynamic_attributes(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("运行状态", html)
        self.assertIn("合成后端", html)
        self.assertIn("音色管理", html)
        self.assertNotIn(">READY<", html)
        self.assertIn("const EMOTION_LABELS", js)
        self.assertIn("option.textContent = emotionLabel(emotion)", js)
        self.assertIn('data-id="${safeVoiceId}"', js)
        self.assertIn('data-emotion="${safeEmotion}"', js)

    def test_settings_loads_all_provider_lists_in_one_refresh(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

        refresh = js.split("async function refresh()", 1)[1].split(
            "async function saveConfig()", 1
        )[0]
        self.assertIn("bridge.apiGet('list_ai_providers')", refresh)
        self.assertIn("bridge.apiGet('list_tts_providers')", refresh)
        self.assertNotIn("async function loadTtsProviders", js)
        self.assertIn("function renderTtsProviders", js)

    def test_settings_layout_covers_status_and_api_fields(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"\.status-board \.status-hint\s*\{[^}]*grid-column:\s*1 / -1;",
        )
        self.assertRegex(
            css,
            r"\.field-row\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);",
        )
        mobile = css.split("@media (max-width: 760px)", 1)[1]
        self.assertIn(".field-row", mobile)

    def test_settings_css_keeps_large_cards_stable_on_hover(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertNotIn(".workflow-strip article:hover,\n.studio-card:hover", css)
        self.assertIn(
            'input:not([type="checkbox"]):not([type="radio"]):not([type="file"])', css
        )
        self.assertRegex(css, r"\.studio-card\s*\{[^}]*isolation:\s*isolate;")
        self.assertRegex(css, r"\.studio-card::before\s*\{[^}]*z-index:\s*0;")
        self.assertRegex(css, r"\.studio-card > \*\s*\{[^}]*z-index:\s*1;")
        self.assertRegex(css, r"\.studio-card:hover\s*\{[^}]*box-shadow:")
        self.assertRegex(css, r"\.studio-switch input\s*\{[^}]*width:\s*16px;")
        self.assertRegex(css, r"\.studio-switch input\s*\{[^}]*transition:\s*none;")
        studio_hover = css.split(".studio-card:hover", 1)[1].split("}", 1)[0]
        self.assertNotIn("transform", studio_hover)

    def test_settings_motion_and_focus_are_input_aware(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("@media (hover: hover) and (pointer: fine)", css)
        self.assertIn("button:active:not(:disabled)", css)
        self.assertIn("button:focus-visible", css)
        self.assertIn(".drop-zone:focus-within", css)
        self.assertIn(".audio-frame.is-playing .wave-bars span", css)
        self.assertNotRegex(css, r"(?m)^\.wave-bars span\s*\{[^}]*animation:")
        self.assertIn("function bindPreviewPlaybackState", js)
        self.assertIn("frame.classList.add('is-playing')", js)
        self.assertIn("frame.classList.remove('is-playing')", js)

    def test_settings_binds_controls_before_bounded_bridge_ready(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        init = js.split("async function init()", 1)[1]

        self.assertIn("async function waitForBridgeReady", js)
        self.assertIn("页面连接超时，请刷新后重试", js)
        self.assertLess(init.index("bindPageEvents();"), init.index("await waitForBridgeReady(bridge);"))

    def test_settings_switch_copy_wraps_without_clipping(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        switch = css.split(".studio-switch {", 1)[1].split("}", 1)[0]

        self.assertIn("min-width: 0;", switch)
        self.assertIn("white-space: normal;", switch)
        self.assertNotIn("white-space: nowrap;", switch)
        self.assertRegex(css, r"\.studio-switch span\s*\{[^}]*min-width:\s*0;")
        self.assertRegex(
            css, r"\.studio-switch span\s*\{[^}]*overflow-wrap:\s*anywhere;"
        )
        self.assertRegex(css, r"\.studio-switch small\s*\{[^}]*display:\s*block;")

    def test_settings_has_tablet_layout_from_761_to_1020(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        tablet = css.split(
            "@media (min-width: 761px) and (max-width: 1020px)", 1
        )[1].split("@media (max-width: 1020px)", 1)[0]

        self.assertIn(".studio-hero", tablet)
        self.assertIn(".workflow-strip", tablet)
        self.assertIn(".readiness-list", tablet)
        self.assertIn(".form-grid", tablet)
        self.assertIn(".switch-grid", tablet)
        self.assertIn(".emotion-grid", tablet)
        self.assertIn(".upload-panel", tablet)
        self.assertIn(".voice-upload-actions", tablet)
        self.assertIn(".preview-row", tablet)
        self.assertIn("repeat(2, minmax(0, 1fr))", tablet)

    def test_settings_groups_cards_by_backend_scope(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn('data-backend-scope="shared"', html)
        # MiMo 专属块：MiMo 设置 / AI 风格导演（含情绪路由）/ 音色库 / 试听
        self.assertEqual(html.count('data-backend-scope="mimo"'), 4)
        self.assertIn('data-backend-scope="astrbot"', html)
        self.assertIn('id="backend-selection"', html)
        self.assertIn("voice-core-grid", html)
        self.assertIn("统一朗读与触发", html)
        self.assertIn("分段、等待与取消", html)
        self.assertIn("外部语音接口", html)
        self.assertIn("MiMo 设置", html)
        self.assertIn("AstrBot 设置", html)
        self.assertIn("document.querySelectorAll('[data-backend-scope]')", js)
        self.assertIn("element.dataset.backendScope", js)
        self.assertIn("scopes.includes('shared')", js)
        self.assertRegex(
            css, r"\[data-backend-scope\]\[hidden\]\s*\{[^}]*display:\s*none;"
        )
        self.assertNotIn("voiceBackendNotice", js)
        self.assertNotIn("voice-workbench.is-muted", css)
        self.assertIn("$('test-connection').textContent", js)
        self.assertIn("renderReadiness();", js)

    def test_settings_hides_inactive_advanced_fields_and_reports_failures(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn('data-backend-scope="astrbot" hidden', html)
        self.assertIn('id="probability-settings" class="conditional-settings"', html)
        self.assertIn('id="api-server-settings" class="conditional-settings" hidden', html)
        self.assertIn('id="ai-style-director-settings" class="conditional-settings" hidden', html)
        self.assertIn("$('probability-settings').hidden = !probabilityMode", js)
        self.assertIn("$('api-server-settings').hidden = !enabled", js)
        self.assertIn("$('ai-style-director-settings').hidden = !enabled", js)
        self.assertIn("function setPageLoading", js)
        self.assertIn("保存失败，改动仍未保存", js)
        self.assertIn("读取失败，请刷新页面重试", js)
        self.assertRegex(
            css,
            r"\.conditional-settings\[hidden\]\s*\{[^}]*display:\s*none;",
        )

    def test_settings_mobile_layout_stacks_api_link_without_page_toast(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 760px)", 1)[1]
        self.assertRegex(
            mobile, r"\.api-link-row\s*\{[^}]*flex-direction:\s*column;"
        )
        self.assertNotIn("#toast", css)
        self.assertNotRegex(css, r"(?<![-\w])\.toast\s*(?:[,{])")

    def test_settings_separates_shared_delivery_from_mimo_emotion(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn("情绪路由", html)
        self.assertIn("分段、等待与取消", html)
        self.assertNotIn("情绪与分段", html)
        # 情绪路由并入「AI 风格导演」卡片，与分段交付仍然分开
        emotion_card = html.split('id="voice-style"', 1)[1].split("</section>", 1)[0]
        delivery_card = html.split('class="studio-card delivery-card span-5" data-backend-scope="shared"', 1)[1].split(
            "</article>", 1
        )[0]
        self.assertIn('id="emotion-routing-enabled"', emotion_card)
        self.assertIn('id="emotion-defaults"', emotion_card)
        self.assertIn("style-routing-block", emotion_card)
        self.assertNotIn('class="studio-card routing-card"', html)
        self.assertNotIn('id="segment-enabled"', emotion_card)
        self.assertIn('id="segment-enabled"', delivery_card)
        self.assertIn('id="segment-threshold-chars"', delivery_card)
        self.assertIn('id="segment-max-segments"', delivery_card)
        self.assertIn('id="segment-delay-ms"', delivery_card)
        self.assertIn("取消语义", delivery_card)
        self.assertIn('id="output-retention-days"', delivery_card)
        self.assertRegex(
            css,
            r"\.delivery-settings-grid\s*\{[^}]*grid-template-columns:\s*1fr;",
        )

    def test_mimo_specific_controls_are_not_global_entry_content(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        hero = html.split('<header class="studio-hero studio-hero-compact">', 1)[1].split("</header>", 1)[0]
        status = html.split('id="voice-overview"', 1)[1].split(
            "</section>", 1
        )[0]
        mimo_card = html.split('data-backend-scope="mimo"', 1)[1].split(
            "</article>", 1
        )[0]

        self.assertNotIn("MiMo 文档", hero)
        self.assertNotIn("API Key", hero)
        self.assertNotIn("migrate-old-plugin", status)
        self.assertIn('id="api-key"', mimo_card)
        self.assertIn('id="migrate-old-plugin"', mimo_card)
        self.assertIn("data-backend-scope=\"mimo\"", html)

    def test_settings_delete_voice_uses_sandbox_safe_confirmation(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertNotIn("confirm(", js)
        self.assertIn("function resetDeleteConfirmation", js)
        self.assertIn("button.dataset.confirming", js)
        self.assertIn("setTimeout", js)
        self.assertIn(
            "voiceAction(button.dataset.action, button.dataset.id, button)", js
        )
        self.assertIn(".voice-actions button.confirming", css)

    def test_settings_handles_astrbot_pages_runtime_constraints(self):
        js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")

        save_config = js.split("async function saveConfig()", 1)[1].split(
            "function validateVoiceUpload", 1
        )[0]
        preview = js.split("async function preview()", 1)[1].split(
            "async function testConnection", 1
        )[0]
        voice_action = js.split("async function voiceAction", 1)[1].split(
            "async function setEmotionDefault", 1
        )[0]

        self.assertIn("await refresh();", save_config)
        self.assertNotIn('target="_blank"', html)
        self.assertIn("playPromise", preview)
        self.assertIn("请手动点击播放器播放", preview)
        self.assertIn("lockedButton", voice_action)
        self.assertIn("setBusy(lockedButton, true", voice_action)
        self.assertIn("setBusy(lockedButton, false", voice_action)


def test_settings_page_p1_regressions():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

    assert '<details class="workflow-fold" id="workflow-help" data-voice-panel="overview">' in html
    assert '<summary>推荐配置流程（4 步）</summary>' in html
    assert '<details class="manual-provider">' in html
    for label in (
        "上传参考音频（mp3 / wav）",
        "音色名称",
        "音色说明",
        "建议情绪",
        "MiMo 风格标签",
        "音色风格指令",
        "试听音色",
        "试听情绪",
        "试听文本",
    ):
        assert f'aria-label="{label}"' in html
    assert "const host = $('api-server-host').value.trim();" in js
    assert "location.hostname || '127.0.0.1'" in js
    assert "urlField.value = `http://127.0.0.1:${port}/v1`;" not in js
    assert ".workflow-fold > summary" in css
    assert "body[data-series-ui] .hero-panel {\n    display: none;" in css
    assert "min-height: 78px" in css


def test_settings_mobile_long_sections_are_collapsible():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
    css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

    assert html.count('class="mobile-fold"') == 3
    assert 'data-mobile-fold' not in html
    assert "const mobileFoldMedia = window.matchMedia(\"(max-width: 760px)\");" in js
    assert "function syncMobileFolds(" in js
    assert "bindMobileFolds();" in js
    init = js.split("async function init()", 1)[1]
    assert init.index("bindMobileFolds();") < init.index("await resolveBridge()")
    assert 'data-toast-fallback' in html
    assert ".mobile-fold > summary" in css
    assert "@media (min-width: 761px)" in css


def test_settings_page_uses_task_tabs_and_composed_panel_visibility():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
    css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

    # 真实二级 tab 取代锚点导航
    assert "section-nav" not in html
    assert '<div id="voice-task-tabs" class="si-tabbar" role="tablist"' in html
    for task in ("overview", "backend", "dialogue", "interface"):
        assert f'data-voice-tab="{task}"' in html
        assert f'data-voice-panel="{task}"' in html
    assert html.count("data-voice-tab=") == 4
    assert "data-goto-tab=" in html

    # 后端选择是常驻作用域切换器：首屏可见，且不属于任何 tab 面板
    assert 'id="backend-selection"' in html
    assert 'data-voice-panel="overview" id="backend-selection"' not in html
    assert html.index('id="backend-selection"') < html.index('id="voice-overview"')
    assert 'data-voice-panel="backend"' in html  # 后端专属设置仍在后端 tab
    assert 'id="voice-library"' in html
    assert 'data-voice-panel="backend" id="voice-library"' in html

    # tab 显隐与后端 scope 组合，而不是互相覆盖
    assert "function applyPanelVisibility()" in js
    assert "const task = currentVoiceTask();" in js
    assert "panel.hidden = !(inTask && inBackend);" in js
    assert "if (element.dataset.voicePanel) return;" in js
    assert "applyPanelVisibility();" in js
    assert "body[data-series-ui] [data-voice-panel][hidden] { display: none; }" in css
    assert "#voice-task-tabs" in css


def test_settings_access_rule_summary_counts_follow_textareas():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

    assert 'class="access-rules-table"' in html
    for key in ("admin", "group-allow", "group-deny", "private-allow", "private-deny"):
        assert f'id="access-count-{key}"' in html
    assert '<details id="access-editor" class="si-disclosure">' in html
    assert 'id="admin-users"' in html

    assert "function updateAccessCounts()" in js
    assert r'.split(/[,\n]/)' in js
    assert "node.textContent = String(value);" in js
    assert "updateAccessCounts();" in js
    assert "$(id).addEventListener('input', updateAccessCounts);" in js


def test_settings_compact_command_header_and_backend_runbar():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

    assert 'class="studio-hero studio-hero-compact"' in html
    assert 'class="hero-actions hero-actions-sticky"' in html
    assert 'id="backend-run-summary"' in html
    assert "常驻，所有分区跟随" in html
    assert html.index('id="backend-selection"') < html.index('id="voice-task-tabs"')
    assert ".studio-hero-compact {" in css
    assert "position: sticky;" in css
    assert ".backend-selector-card {" in css
    assert ".overview-grid {" in css


def test_settings_overview_has_backend_voice_preview_and_switch_summaries():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="overview-backend-summary"' in html
    assert 'data-focus-target="#voice-library"' in html
    assert 'data-focus-target="#voice-preview-card"' in html
    assert 'id="overview-director-status"' in html
    assert 'id="overview-api-status"' in html
    assert "button.dataset.focusTarget" in js
    assert "overview-backend-summary" in js


def test_settings_each_workspace_keeps_progressive_disclosure_and_fields():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

    assert html.count('class="section-disclosure') >= 5
    for marker in (
        'id="voice-file"',
        'id="preview-btn"',
        'id="ai-style-director-enabled"',
        'id="emotion-routing-enabled"',
        'id="admin-users"',
        'id="api-server-token"',
        'id="output-retention-days"',
        'id="migrate-old-plugin"',
    ):
        assert marker in html
    assert ".section-disclosure > summary" in css
    assert ".section-disclosure-body" in css


def test_settings_page_uses_incremented_asset_cache_busters():
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    for asset in ("style.css", "series-ui.css", "series-ui.js", "app.js"):
        assert f"{asset}?v=0.12.4-1" in html
