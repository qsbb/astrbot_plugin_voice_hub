from pathlib import Path
import unittest


PAGES_DIR = Path(__file__).resolve().parents[1] / "pages" / "settings"
MOJIBAKE_MARKERS = ("闂", "闁", "閻", "濮", "閸", "濞", "缂", "閺")


class PagesUITests(unittest.TestCase):
    def test_settings_page_uses_firefly_inspired_studio_shell(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn("凝心溯溪-声", html)
        self.assertIn("Dual Backend Voice Console", html)
        self.assertIn("studio-shell", html)
        self.assertIn("studio-hero", html)
        self.assertIn("workflow-strip", html)
        self.assertIn("top-gradient-highlight", html)
        self.assertIn("通用设置", html)
        self.assertIn("一键诊断", html)
        self.assertIn("--studio-gold", css)
        self.assertIn("--hue", css)
        self.assertIn("--primary", css)
        self.assertIn("card-rise", css)
        self.assertIn("wave-breathe", css)
        self.assertIn("backdrop-filter", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("radial-gradient", css)
        self.assertIn("--amber", css)
        self.assertIn("upload-fields", html)
        self.assertIn("voice-upload-actions", html)
        self.assertIn("repeat(auto-fit", css)
        self.assertIn("save-state", html)
        self.assertIn("upload-hint", html)
        self.assertIn("readiness-list", html)
        self.assertIn("preview-hint", html)
        self.assertIn("ai-style-director-provider-select", html)
        self.assertIn("ai-style-director-debug-log", html)

    def test_settings_page_loads_astrbot_bridge_before_app(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        bridge_script = '<script src="/api/plugin/page/bridge-sdk.js"></script>'
        app_script = '<script src="./app.js"></script>'

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
        self.assertIn("触发方式是唯一开关", html)
        self.assertIn('id="llm-tts-judge-enabled"', html)
        self.assertIn("LLM 情绪化朗读判断", html)
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

    def test_settings_layout_covers_status_and_api_fields(self):
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"\.status-board \.migration-row\s*\{[^}]*grid-column:\s*1 / -1;",
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
        self.assertGreaterEqual(html.count('data-backend-scope="mimo"'), 5)
        self.assertIn('data-backend-scope="astrbot"', html)
        self.assertIn(
            'class="studio-card access-card" data-backend-scope="shared"', html
        )
        self.assertRegex(
            html,
            r'<section class="studio-grid routing-settings-grid">\s*<article class="studio-card routing-card span-7" data-backend-scope="mimo">[\s\S]*</article>\s*<article class="studio-card routing-card span-5" data-backend-scope="shared">',
        )
        self.assertIn("通用设置", html)
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
        routing_section = html.split(
            '<section class="studio-grid routing-settings-grid">', 1
        )[1].split("</section>", 1)[0]
        self.assertNotIn("data-backend-scope", routing_section.split("<article", 1)[0])
        self.assertIn(
            'class="studio-card routing-card span-7" data-backend-scope="mimo"',
            routing_section,
        )
        self.assertIn(
            'class="studio-card routing-card span-5" data-backend-scope="shared"',
            routing_section,
        )

    def test_settings_splits_emotion_and_segment_cards(self):
        html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
        css = (PAGES_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn("routing-settings-grid", html)
        self.assertIn("情绪路由", html)
        self.assertIn("长文本分段", html)
        self.assertNotIn("情绪与分段", html)
        emotion_card = html.split('class="studio-card routing-card span-7"', 1)[1].split(
            "</article>", 1
        )[0]
        segment_card = html.split('class="studio-card routing-card span-5"', 1)[1].split(
            "</article>", 1
        )[0]
        self.assertIn('id="emotion-routing-enabled"', emotion_card)
        self.assertIn('id="emotion-defaults"', emotion_card)
        self.assertNotIn('id="segment-enabled"', emotion_card)
        self.assertIn('id="segment-enabled"', segment_card)
        self.assertIn('id="segment-threshold-chars"', segment_card)
        self.assertIn('id="segment-max-segments"', segment_card)
        self.assertRegex(
            css,
            r"\.segment-settings-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.4fr\) repeat\(2, minmax\(0, 1fr\)\);",
        )
        self.assertRegex(
            css,
            r"\.routing-settings-grid:has\(> \.span-7\[hidden\]\) > \.span-5:not\(\[hidden\]\)\s*\{[^}]*grid-column:\s*1 / -1;",
        )

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
