"""Kontrak statis anti-hardcode Ekasa Desk (#12 fase 3a/3b/3d-2 - docs/08 §7-§8).

Test ini berjalan tanpa Frappe dan tanpa `frontend/node_modules`:
1. Komponen `frontend/src/components/{module,domain,shell,windows}` dan `frontend/src/styles/base.css`
   bebas warna literal hex (`#rgb`..`#rrggbbaa`) atau `rgb()`/`rgba()`.
2. Komponen `frontend/src/components/module` bebas literal nama DocType katalog
   ("Sales Invoice", "Purchase Invoice", dst.).
3. `DomainWindow.vue` dan `StartMenu.vue` bebas literal nama bidang ("Sales", "Finance") di template.
4. Jalur produksi `frontend/src/` (di luar `api/mock`) bebas impor/referensi `api/mock`.
5. Kasus positif buatan membuktikan regex benar-benar menangkap pelanggaran.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESK_SRC = REPO_ROOT / "frontend" / "src"
ADMIN_SRC = REPO_ROOT / "admin" / "src"
BASE_DIR = DESK_SRC / "components" / "base"
AGENT_DIR = DESK_SRC / "components" / "agent"
VIEWS_DIR = DESK_SRC / "views"
MODULE_DIR = DESK_SRC / "components" / "module"
DOMAIN_DIR = DESK_SRC / "components" / "domain"
SHELL_DIR = DESK_SRC / "components" / "shell"
WINDOWS_DIR = DESK_SRC / "components" / "windows"
BASE_CSS = DESK_SRC / "styles" / "base.css"
TOKENS_CSS = DESK_SRC / "styles" / "tokens.css"
THEME_TS = DESK_SRC / "utils" / "theme.ts"
TYPES_TS = DESK_SRC / "types" / "index.ts"
SETTINGS_WINDOW = WINDOWS_DIR / "SettingsWindow.vue"
ABOUT_WINDOW = WINDOWS_DIR / "AboutWindow.vue"
BOOT_SCREEN = SHELL_DIR / "BootScreen.vue"
SEARCH_FLYOUT = SHELL_DIR / "SearchFlyout.vue"
WINDOW_HOST = SHELL_DIR / "WindowHost.vue"
DOMAIN_WINDOW = DOMAIN_DIR / "DomainWindow.vue"
START_MENU = SHELL_DIR / "StartMenu.vue"
AGENT_PANEL = AGENT_DIR / "AgentPanel.vue"
DESKTOP_VIEW = DESK_SRC / "views" / "DesktopView.vue"
LOGIN_VIEW = DESK_SRC / "views" / "LoginView.vue"
REGISTER_VIEW = DESK_SRC / "views" / "RegisterView.vue"
PENDING_VIEW = DESK_SRC / "views" / "PendingView.vue"
INDEX_HTML = REPO_ROOT / "frontend" / "index.html"
STORES_DIR = DESK_SRC / "stores"
CHAT_STORE = STORES_DIR / "chat.ts"

FORBIDDEN_SETTING_FIELDS = (
    "api_key",
    "system_ethos",
    "model_name",
    "base_url",
)
FORBIDDEN_SETTING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(field) for field in FORBIDDEN_SETTING_FIELDS) + r")\b"
)

COLOR_LITERAL_RE = re.compile(
    r"(?<![\w-])#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(",
    re.IGNORECASE,
)

CATALOG_DOCTYPES = (
    "Sales Invoice",
    "Sales Order",
    "Quotation",
    "Delivery Note",
    "Purchase Invoice",
    "Payment Entry",
    "Journal Entry",
    "GL Entry",
    "Customer",
    "Supplier",
    "Item",
    "Item Price",
    "Account",
    "Company",
    "Purchase Order",
    "Purchase Receipt",
    "Supplier Quotation",
)

DOCTYPE_LITERAL_RE = re.compile(
    r"""(['"`])\s*(?:"""
    + "|".join(re.escape(dt) for dt in CATALOG_DOCTYPES)
    + r""")\s*\1|\b(?:Sales\s+Invoice|Sales\s+Order|Purchase\s+Invoice|Payment\s+Entry)\b"""
)

ACTIVE_DOMAINS = ("Sales", "Finance", "Accounting", "Purchasing")
DOMAIN_LITERAL_RE = re.compile(
    r"""(['"`])\s*(?:"""
    + "|".join(re.escape(d) for d in ACTIVE_DOMAINS)
    + r""")\s*\1|\b(?:Sales|Finance)\b"""
)

API_MOCK_RE = re.compile(r"api/mock\b")
EMPTY_CATCH_RE = re.compile(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}")


def _extract_function_block(text: str, func_name: str) -> str | None:
    match = re.search(rf"function\s+{re.escape(func_name)}\s*\([^)]*\)\s*\{{", text)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start() : i + 1]
    return text[match.start() :]


def _iter_source_files(directory: Path):
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in {".vue", ".ts", ".css"}:
            yield path


def _extract_vue_template(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<template>(.*)</template>", text, re.DOTALL)
    return match.group(1) if match else text


def _extract_css_block(text: str, selector: str) -> str | None:
    pattern = re.compile(re.escape(selector) + r"\s*\{")
    match = pattern.search(text)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start() : i + 1]
    return text[match.start() :]


@unittest.skipUnless(DESK_SRC.exists(), "frontend/src belum tersedia")
class TestFrontendNoHardcode(unittest.TestCase):
    def test_no_hex_or_rgba_in_module_and_shell_components(self):
        self.assertTrue(MODULE_DIR.exists(), "frontend/src/components/module belum ada")
        self.assertTrue(DOMAIN_DIR.exists(), "frontend/src/components/domain belum ada")
        self.assertTrue(SHELL_DIR.exists(), "frontend/src/components/shell belum ada")
        self.assertTrue(WINDOWS_DIR.exists(), "frontend/src/components/windows belum ada")
        self.assertTrue(BASE_CSS.exists(), "frontend/src/styles/base.css belum ada")
        offenders = []
        paths = [
            *(_iter_source_files(BASE_DIR)),
            *(_iter_source_files(AGENT_DIR)),
            *(_iter_source_files(VIEWS_DIR)),
            *(_iter_source_files(MODULE_DIR)),
            *(_iter_source_files(DOMAIN_DIR)),
            *(_iter_source_files(SHELL_DIR)),
            *(_iter_source_files(WINDOWS_DIR)),
            BASE_CSS,
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for match in COLOR_LITERAL_RE.finditer(text):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            f"Warna literal di komponen module/shell/windows atau base.css: {offenders}",
        )

    def test_no_secret_field_literals_in_settings_window(self):
        self.assertTrue(SETTINGS_WINDOW.exists(), "frontend/src/components/windows/SettingsWindow.vue belum ada")
        text = SETTINGS_WINDOW.read_text(encoding="utf-8")
        offenders = [match.group(0) for match in FORBIDDEN_SETTING_RE.finditer(text)]
        self.assertEqual(offenders, [], f"Field sensitif literal di SettingsWindow.vue: {offenders}")

    def test_no_color_literals_in_admin_src(self):
        """Dashboard admin (admin/src) bebas warna literal; token dari tokens.css."""
        self.assertTrue(ADMIN_SRC.exists(), "admin/src belum tersedia")
        offenders = []
        for path in _iter_source_files(ADMIN_SRC):
            text = path.read_text(encoding="utf-8")
            for match in COLOR_LITERAL_RE.finditer(text):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Warna literal di admin/src: {offenders}")

    def test_no_api_credential_literal_in_admin_src(self):
        """api_credential tidak pernah disebut/dirender di kode dashboard admin."""
        self.assertTrue(ADMIN_SRC.exists(), "admin/src belum tersedia")
        offenders = []
        for path in _iter_source_files(ADMIN_SRC):
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bapi_credential\b", text):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], f"Literal api_credential di admin/src: {offenders}")


    def test_no_literal_doctype_names_in_module_components(self):
        self.assertTrue(MODULE_DIR.exists(), "frontend/src/components/module belum ada")
        offenders = []
        for path in _iter_source_files(MODULE_DIR):
            text = path.read_text(encoding="utf-8")
            for match in DOCTYPE_LITERAL_RE.finditer(text):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Nama DocType literal di komponen modul: {offenders}")

    def test_no_literal_domain_names_in_domain_window_and_start_menu_templates(self):
        self.assertTrue(DOMAIN_WINDOW.exists(), "frontend/src/components/domain/DomainWindow.vue belum ada")
        self.assertTrue(START_MENU.exists(), "frontend/src/components/shell/StartMenu.vue belum ada")
        offenders = []
        for target in (DOMAIN_WINDOW, START_MENU):
            template_text = _extract_vue_template(target)
            for match in DOMAIN_LITERAL_RE.finditer(template_text):
                rel = target.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            f"Nama bidang literal di template DomainWindow.vue atau StartMenu.vue: {offenders}",
        )

    def test_no_api_mock_in_production_paths(self):
        offenders = []
        for path in _iter_source_files(DESK_SRC):
            rel = path.relative_to(DESK_SRC).as_posix()
            if rel.startswith("api/mock/"):
                continue
            text = path.read_text(encoding="utf-8")
            if API_MOCK_RE.search(text):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], f"Referensi api/mock di jalur produksi: {offenders}")

    def test_desktop_icon_click_does_not_call_run_directly(self):
        self.assertTrue(DESKTOP_VIEW.exists(), "frontend/src/views/DesktopView.vue belum ada")
        text = DESKTOP_VIEW.read_text(encoding="utf-8")
        block = _extract_function_block(text, "iconClick")
        self.assertIsNotNone(block, "Fungsi iconClick tidak ditemukan di DesktopView.vue")
        self.assertNotIn(".run()", block)
        self.assertNotIn(".run(", block)

    def test_no_empty_catch_in_stores(self):
        self.assertTrue(STORES_DIR.exists(), "frontend/src/stores belum ada")
        offenders = []
        for path in sorted(STORES_DIR.glob("*.ts")):
            text = path.read_text(encoding="utf-8")
            for match in EMPTY_CATCH_RE.finditer(text):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Blok catch {{}} kosong di stores: {offenders}")

    def test_no_silent_draft_load_error_in_chat_store(self):
        self.assertTrue(CHAT_STORE.exists(), "frontend/src/stores/chat.ts belum ada")
        text = CHAT_STORE.read_text(encoding="utf-8")
        silent_pattern = re.compile(
            r"catch\s*(?:\([^)]*\))?\s*\{(?![^}]*pendingDraftsError)[^}]*pendingDrafts\s*=\s*\[\][^}]*\}"
        )
        self.assertIsNone(
            silent_pattern.search(text),
            "loadPendingDrafts di chat.ts masih menelan error tanpa menetapkan pendingDraftsError",
        )
        self.assertIn("pendingDraftsError", text)
        self.assertIn("pendingDraftsLoading", text)

    def test_regex_detectors_catch_synthetic_violations(self):
        self.assertIsNotNone(COLOR_LITERAL_RE.search("color: #1a2b3c;"))
        self.assertIsNotNone(COLOR_LITERAL_RE.search("background: rgba(20, 30, 40, 0.5);"))
        self.assertIsNone(COLOR_LITERAL_RE.search("color: var(--fg); background: var(--surface-2);"))

        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search("const dt = 'Sales Invoice';"))
        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search("<h4>Purchase Invoice</h4>"))
        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search('label: "Customer"'))
        self.assertIsNone(DOCTYPE_LITERAL_RE.search("<h4>{{ meta?.label }}</h4>"))

        self.assertIsNotNone(DOMAIN_LITERAL_RE.search("<h4>Sales</h4>"))
        self.assertIsNotNone(DOMAIN_LITERAL_RE.search("<span>Finance</span>"))
        self.assertIsNone(DOMAIN_LITERAL_RE.search("<h4>{{ meta?.label }}</h4>"))

        self.assertIsNotNone(API_MOCK_RE.search("import { rows } from '../api/mock/sales';"))
        self.assertIsNone(API_MOCK_RE.search("import { fetchModule } from '@modules-api';"))

        self.assertIsNotNone(FORBIDDEN_SETTING_RE.search("const key = data.api_key;"))
        self.assertIsNotNone(FORBIDDEN_SETTING_RE.search("<span>{{ system_ethos }}</span>"))
        self.assertIsNone(FORBIDDEN_SETTING_RE.search("<span>{{ data.quota.limit }}</span>"))

        self.assertIsNotNone(EMPTY_CATCH_RE.search("try { await load(); } catch {}"))
        self.assertIsNotNone(EMPTY_CATCH_RE.search("try { await load(); } catch (e) { }"))
        self.assertIsNone(EMPTY_CATCH_RE.search("try { await load(); } catch (e) { handleError(e); }"))

        synthetic_buggy_func = "function iconClick(d) { selectedIcon.value = d.id; d.run(); }"
        synthetic_block = _extract_function_block(synthetic_buggy_func, "iconClick")
        self.assertIsNotNone(synthetic_block)
        self.assertIn(".run()", synthetic_block)

        silent_draft_pattern = re.compile(
            r"catch\s*(?:\([^)]*\))?\s*\{(?![^}]*pendingDraftsError)[^}]*pendingDrafts\s*=\s*\[\][^}]*\}"
        )
        self.assertIsNotNone(
            silent_draft_pattern.search("try { await fetch(); } catch { this.pendingDrafts = []; }")
        )
        self.assertIsNone(
            silent_draft_pattern.search(
                "try { await fetch(); } catch (e) { this.pendingDrafts = []; this.pendingDraftsError = 'err'; }"
            )
        )

    def test_vite_config_has_no_hardcoded_backend_or_site(self):
        """vite.config.ts tidak boleh hardcode host, port, atau nama site."""
        config = REPO_ROOT / "frontend" / "vite.config.ts"
        self.assertTrue(config.exists(), "frontend/vite.config.ts tidak ditemukan")
        source = config.read_text(encoding="utf-8")

        # Nilai hardcode yang dilarang
        for banned in (
            "127.0.0.1:8001",
            "aios-v16.localhost",
            "localhost:5173",
        ):
            self.assertNotIn(
                banned,
                source,
                f"vite.config.ts masih hardcode {banned!r}",
            )

        # Override Host header dilarang (mekanisme resmi Frappe memakai Host asli)
        self.assertNotIn(
            "headers: { Host:",
            source,
            "vite.config.ts menimpa Host header; Frappe memilih site dari Host asli",
        )

        # Wajib membaca dari env
        self.assertIn("VITE_BACKEND_TARGET", source)
        self.assertIn("VITE_DEV_PORT", source)

    def test_env_example_documents_required_vars(self):
        env_example = REPO_ROOT / "frontend" / ".env.example"
        self.assertTrue(env_example.exists(), "frontend/.env.example belum ada")
        source = env_example.read_text(encoding="utf-8")
        for key in ("VITE_BACKEND_TARGET", "VITE_DEV_PORT", "VITE_DESKTOP_ADAPTER"):
            self.assertIn(key, source, f".env.example tidak mendokumentasikan {key}")

    def test_brand_dimension_0c_contract_in_frontend(self):
        """Dimensi desain 0C (SettingsBrand, tokens.css Finto, halaman Desain Settings) terpenuhi."""
        types_src = TYPES_TS.read_text(encoding="utf-8")
        self.assertRegex(types_src, r"export\s+type\s+SettingsBrand\s*=.*'ekasa'")
        self.assertRegex(types_src, r"export\s+type\s+SettingsBrand\s*=.*'finto'")

        theme_src = THEME_TS.read_text(encoding="utf-8")
        self.assertIn("BRAND_STORAGE_KEY = 'aios.desk.brand'", theme_src)
        self.assertIn("DEFAULT_BRAND: SettingsBrand = 'finto'", theme_src)
        self.assertIn("ALLOWED_BRANDS", theme_src)
        self.assertIn("dataset.brand", theme_src)

        tokens_src = TOKENS_CSS.read_text(encoding="utf-8")
        for token in (
            "--fos-navy:",
            "--fos-blue:",
            "--fos-cyan:",
            "--fos-lime:",
            "--fos-violet:",
            "--fos-light:",
            "[data-brand='finto']",
        ):
            self.assertIn(token, tokens_src, f"tokens.css belum mendefinisikan {token}")

        settings_src = SETTINGS_WINDOW.read_text(encoding="utf-8")
        self.assertIn("'Finto Desk'", settings_src)
        self.assertIn("'Ekasa Desk'", settings_src)

    def test_finto_desktop_wallpaper_follows_color_mode(self):
        """Wallpaper desktop dan taskbar Finto mengikuti Mode Warna (Light terang/pastel, Dark navy)."""
        tokens_src = TOKENS_CSS.read_text(encoding="utf-8")
        light_block = _extract_css_block(tokens_src, ":root[data-brand='finto']")
        auto_dark_block = _extract_css_block(tokens_src, ":root[data-brand='finto']:not([data-theme='light'])")
        dark_block = _extract_css_block(tokens_src, ":root[data-brand='finto'][data-theme='dark']")
        self.assertIsNotNone(light_block)
        self.assertIsNotNone(auto_dark_block)
        self.assertIsNotNone(dark_block)

        # Light Mode: desktop wallpaper pastel + teks desktop gelap + taskbar terang
        self.assertIn("--desk-wall-base: #e8f0fa;", light_block)
        self.assertIn("--desk-fg: #0b1f3b;", light_block)
        self.assertIn("--desk-muted: #64708a;", light_block)
        self.assertIn("--tb-bg: rgba(243, 247, 251, 0.88);", light_block)
        self.assertIn("--tb-fg: #0b1f3b;", light_block)
        self.assertIn("--tb-muted: #64708a;", light_block)

        # Dark Mode (auto & explicit): desktop wallpaper navy + teks desktop terang + taskbar navy
        for block in (auto_dark_block, dark_block):
            self.assertIn("--desk-wall-base: #06111f;", block)
            self.assertIn("--desk-fg: #f3f7fb;", block)
            self.assertIn("--desk-muted: #9fb3c8;", block)
            self.assertIn("--tb-bg: rgba(11, 31, 59, 0.92);", block)
            self.assertIn("--tb-fg: #f3f7fb;", block)
            self.assertIn("--tb-muted: #9fb3c8;", block)

        # Token Ekasa tetap utuh
        ekasa_root = _extract_css_block(tokens_src, ":root")
        self.assertIsNotNone(ekasa_root)
        self.assertIn("--wall-base: #dce6ea;", ekasa_root)

    def test_lock_register_pending_use_liquid_glass_tokens(self):
        """Kartu lock, register, dan pending memakai kelas & token Liquid Glass adaptif Light/Dark."""
        for view_path in (LOGIN_VIEW, REGISTER_VIEW, PENDING_VIEW):
            src = view_path.read_text(encoding="utf-8")
            self.assertIn('class="lock wall"', src)
            self.assertIn('class="lock-card"', src)

        base_src = BASE_CSS.read_text(encoding="utf-8")
        lock_card_css = _extract_css_block(base_src, ".lock-card")
        self.assertIsNotNone(lock_card_css)
        self.assertIn("var(--lock-card-bg", lock_card_css)
        self.assertIn("var(--lock-card-line", lock_card_css)
        self.assertIn("var(--lock-card-shadow", lock_card_css)
        self.assertIn("backdrop-filter: var(--lock-card-blur", lock_card_css)

        tokens_src = TOKENS_CSS.read_text(encoding="utf-8")
        light_block = _extract_css_block(tokens_src, ":root[data-brand='finto']")
        auto_dark_block = _extract_css_block(tokens_src, ":root[data-brand='finto']:not([data-theme='light'])")
        dark_block = _extract_css_block(tokens_src, ":root[data-brand='finto'][data-theme='dark']")

        # Tidak lagi kartu putih solid (0.94 / 0.95) maupun field putih solid (#ffffff)
        for block in (light_block, auto_dark_block, dark_block):
            self.assertNotIn("rgba(255, 255, 255, 0.94)", block)
            self.assertNotIn("rgba(255, 255, 255, 0.95)", block)
            self.assertNotIn("--lock-field-bg: #ffffff;", block)

        # Light Mode kartu & field kaca terang, teks gelap
        self.assertIn("--lock-card-fg: #0b1f3b;", light_block)
        # Dark Mode kartu & field kaca gelap, teks terang
        for block in (auto_dark_block, dark_block):
            self.assertIn("--lock-card-fg: #f3f7fb;", block)
            self.assertIn("--lock-card-bg:", block)
            self.assertIn("--lock-field-bg:", block)

    def test_about_title_and_desktop_icon_use_finto_os(self):
        """Judul jendela Tentang dan ikon desktop memakai Tentang Finto OS saat brand finto."""
        host_src = WINDOW_HOST.read_text(encoding="utf-8")
        desk_src = DESKTOP_VIEW.read_text(encoding="utf-8")
        self.assertIn("'Tentang Finto OS'", host_src)
        self.assertIn("'Tentang Finto OS'", desk_src)

    def test_agent_panel_greeting_uses_outfit_avatar_without_welcome_mascot(self):
        """Sapaan AgentPanel memakai AgentAvatar outfit tanpa gambar finto-welcome-transparent.png."""
        ap_src = AGENT_PANEL.read_text(encoding="utf-8")
        self.assertNotIn("finto-welcome-transparent.png", ap_src)
        self.assertNotIn("ap-welcome-mascot", ap_src)
        self.assertIn("<AgentAvatar", ap_src)

    def test_start_menu_footer_buttons_follow_color_mode(self):
        """Ikon gear dan power di footer StartMenu mengikuti --fg, bukan putih tetap --tb-fg."""
        start_src = START_MENU.read_text(encoding="utf-8")
        base_src = BASE_CSS.read_text(encoding="utf-8")
        self.assertIn("start-foot", start_src)
        foot_btn_css = _extract_css_block(base_src, ".start-foot .tb-btn")
        self.assertIsNotNone(foot_btn_css)
        self.assertIn("color: var(--fg);", foot_btn_css)

    def test_favicon_files_and_index_link_exist(self):
        """index.html merujuk favicon Finto dan aset /favicon.svg + /favicon.ico tersedia di public/."""
        index_html = REPO_ROOT / "frontend" / "index.html"
        favicon_svg = REPO_ROOT / "frontend" / "public" / "favicon.svg"
        favicon_ico = REPO_ROOT / "frontend" / "public" / "favicon.ico"
        self.assertTrue(index_html.exists(), "frontend/index.html tidak ditemukan")
        html_src = index_html.read_text(encoding="utf-8")
        self.assertIn('rel="icon"', html_src)
        self.assertIn('href="/favicon.svg"', html_src)
        self.assertIn('href="/favicon.ico"', html_src)

        self.assertTrue(favicon_svg.exists(), "frontend/public/favicon.svg belum ada")
        svg_src = favicon_svg.read_text(encoding="utf-8")
        self.assertIn("<svg", svg_src)
        self.assertNotIn("c2pa:manifest", svg_src)

        self.assertTrue(favicon_ico.exists(), "frontend/public/favicon.ico belum ada")
        ico_bytes = favicon_ico.read_bytes()
        self.assertTrue(ico_bytes.startswith(b"\x00\x00\x01\x00"), "favicon.ico bukan format ICO valid")

    def test_desktop_icons_wrap_to_next_column_and_keep_narrow_grid(self):
        """Ikon desktop mengalir ke kolom berikutnya saat penuh dan mode narrow tetap grid 4 kolom."""
        base_src = BASE_CSS.read_text(encoding="utf-8")
        desk_icons_css = _extract_css_block(base_src, ".desk-icons")
        desk_icon_css = _extract_css_block(base_src, ".desk-icon")
        narrow_icons_css = _extract_css_block(base_src, ".os.narrow .desk-icons")
        narrow_icon_css = _extract_css_block(base_src, ".os.narrow .desk-icon")

        self.assertIsNotNone(desk_icons_css)
        self.assertIn("bottom: 14px;", desk_icons_css)
        self.assertIn("display: flex;", desk_icons_css)
        self.assertIn("flex-direction: column;", desk_icons_css)
        self.assertIn("flex-wrap: wrap;", desk_icons_css)
        self.assertIn("align-content: flex-start;", desk_icons_css)
        self.assertNotIn("width: 88px;", desk_icons_css)

        self.assertIsNotNone(desk_icon_css)
        self.assertIn("width: 88px;", desk_icon_css)

        self.assertIsNotNone(narrow_icons_css)
        self.assertIn("display: grid;", narrow_icons_css)
        self.assertIn("grid-template-columns: repeat(4, 1fr);", narrow_icons_css)
        self.assertIsNotNone(narrow_icon_css)
        self.assertIn("width: auto;", narrow_icon_css)

    def test_purchasing_agent_accent_tokens_and_settings_option_exist(self):
        """Token aksen Purchasing di tokens.css dan opsi persona Purchasing di SettingsWindow tersedia."""
        tokens_src = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn("--agent-accent-purchasing: var(--domain-purchasing);", tokens_src)
        self.assertIn("[data-branch='purchasing']", tokens_src)
        self.assertIn("--agent-accent: var(--agent-accent-purchasing);", tokens_src)

        settings_src = SETTINGS_WINDOW.read_text(encoding="utf-8")
        self.assertIn("{ value: 'purchasing', label: 'Purchasing' }", settings_src)

    def test_boot_screen_uses_finto_mark_and_wordmark_without_pill_lockups(self):
        """Layar boot Finto memakai mark F (<FintoMark>) + FINTO OS tanpa pill/lockup horizontal maupun versi SPI."""
        self.assertTrue(BOOT_SCREEN.exists(), "frontend/src/components/shell/BootScreen.vue belum ada")
        boot_src = BOOT_SCREEN.read_text(encoding="utf-8")

        self.assertIn("FintoMark", boot_src)
        self.assertIn("<FintoMark", boot_src)
        self.assertIn("FINTO OS", boot_src)

        for forbidden in (
            "finto-logo-pill-blue.png",
            "finto-logo-utama-nobg.png",
            "boot-lockup",
            "light-lockup",
            "v1.0",
            "build 2026.11",
        ):
            self.assertNotIn(forbidden, boot_src, f"BootScreen.vue masih mengandung {forbidden!r}")

        self.assertIn('@click="skip"', boot_src)
        self.assertIn('@keydown="skip"', boot_src)
        self.assertIn("Tekan sembarang tombol atau klik untuk melewati", boot_src)
        self.assertIn("boot-bar", boot_src)
        self.assertIn("boot-pct", boot_src)
        self.assertIn("boot-log", boot_src)

    def test_finto_brand_followup_avatars_and_titles(self):
        """Follow-up B2: title Finto Desk di index.html, identitas brand-conditional, dan AgentAvatar di DomainWindow/SearchFlyout/DesktopView."""
        index_src = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Finto Desk</title>", index_src)
        self.assertNotIn("<title>Ekasa Desk</title>", index_src)

        about_src = ABOUT_WINDOW.read_text(encoding="utf-8")
        self.assertIn('v-if="isFintoBrand"', about_src)
        self.assertIn('alt="Finto OS"', about_src)
        self.assertLess(about_src.index('alt="Finto OS"'), about_src.index("Ekasa Desk"))

        login_src = LOGIN_VIEW.read_text(encoding="utf-8")
        self.assertIn('v-if="isFintoBrand"', login_src)
        self.assertIn('alt="Finto OS"', login_src)
        self.assertLess(login_src.index('alt="Finto OS"'), login_src.index("Ekasa Desk"))

        domain_src = DOMAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("AgentAvatar", domain_src)
        self.assertIn("<AgentAvatar", domain_src)
        self.assertNotIn('class="agent-dot"', domain_src)

        search_src = SEARCH_FLYOUT.read_text(encoding="utf-8")
        self.assertIn("AgentAvatar", search_src)
        self.assertIn("<AgentAvatar", search_src)
        self.assertNotIn('class="agent-dot"', search_src)

        desk_src = DESKTOP_VIEW.read_text(encoding="utf-8")
        self.assertIn("AgentAvatar", desk_src)
        self.assertIn("<AgentAvatar", desk_src)
        self.assertIn("domainKey", desk_src)


if __name__ == "__main__":
    unittest.main()
