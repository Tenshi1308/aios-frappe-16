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
MODULE_DIR = DESK_SRC / "components" / "module"
DOMAIN_DIR = DESK_SRC / "components" / "domain"
SHELL_DIR = DESK_SRC / "components" / "shell"
WINDOWS_DIR = DESK_SRC / "components" / "windows"
BASE_CSS = DESK_SRC / "styles" / "base.css"
SETTINGS_WINDOW = WINDOWS_DIR / "SettingsWindow.vue"
DOMAIN_WINDOW = DOMAIN_DIR / "DomainWindow.vue"
START_MENU = SHELL_DIR / "StartMenu.vue"
DESKTOP_VIEW = DESK_SRC / "views" / "DesktopView.vue"
STORES_DIR = DESK_SRC / "stores"
CHAT_STORE = STORES_DIR / "chat.ts"

FORBIDDEN_SETTING_FIELDS = (
    "api_key",
    "company_context_persona",
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
    "Purchase Invoice",
    "Payment Entry",
    "Customer",
    "Supplier",
    "Item",
)

DOCTYPE_LITERAL_RE = re.compile(
    r"""(['"`])\s*(?:"""
    + "|".join(re.escape(dt) for dt in CATALOG_DOCTYPES)
    + r""")\s*\1|\b(?:Sales\s+Invoice|Sales\s+Order|Purchase\s+Invoice|Payment\s+Entry)\b"""
)

ACTIVE_DOMAINS = ("Sales", "Finance")
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
        self.assertIsNotNone(FORBIDDEN_SETTING_RE.search("<span>{{ company_context_persona }}</span>"))
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


if __name__ == "__main__":
    unittest.main()
