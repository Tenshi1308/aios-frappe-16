"""Higienitas repo (K1/K4/K8/K9) — AST + git ls-files. Merah di #0, hijau di #3."""

import ast
import re
import subprocess
import unittest
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # apps/aios_v1/
INNER_PKG = Path(__file__).resolve().parent.parent  # apps/aios_v1/aios_v1/
FRONTEND_DIR = REPO_ROOT / "frontend"
ADMIN_DIR = REPO_ROOT / "admin"

# Seluruh source frontend wajib bebas emoji dekoratif (docs/01, docs/08 aturan Zero Emoji)
FRONTEND_SRC = FRONTEND_DIR / "src"
ADMIN_SRC = ADMIN_DIR / "src"
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF]"
)

# Batch 1 hanya modul PoC aktif; modul dormant menyusul #3.
# `telegram_service.py` dan `order_service.py` dihapus bersama pensiun kanal lama
# (F2 konektor Telegram); modul hidup baru wajib lolos aturan except.
DORMANT_MODULES = {
    "skills_loader.py",
    "pdf_extractor.py",
    "inspect_setting.py",
    "read_setting.py",
}


def _git_ls_files(subpath):
    out = subprocess.run(
        ["git", "ls-files", subpath], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _iter_frontend_sources(directory: Path):
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in {".vue", ".ts", ".css"}:
            yield path


def _iter_production_modules():
    """Semua modul .py di dalam package, kecuali test dan __pycache__."""
    for path in INNER_PKG.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("test_"):
            continue
        if path.name in DORMANT_MODULES:
            continue
        yield path


def _has_log_error_or_raise(handler):
    calls = [n for n in ast.walk(handler) if isinstance(n, ast.Call)]
    has_log = any(
        (
            isinstance(c.func, ast.Attribute)
            and c.func.attr in ("log_error", "log_exception")
        )
        or (isinstance(c.func, ast.Name) and c.func.id == "log_exception")
        for c in calls
    )
    has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
    exception_name = handler.name if isinstance(handler.name, str) else None
    forwards_exception = exception_name and any(
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        and node.value.id == exception_name
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "result"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "error"
            for target in node.targets
        )
        for node in ast.walk(handler)
    )
    return has_log or has_raise or bool(forwards_exception)


class TestRepoHygiene(unittest.TestCase):
    @pytest.mark.xfail(reason="target #3 (K1/K4/K8/K9)", strict=False)
    def test_no_tracked_frontend_artifacts(self):
        self.assertEqual(_git_ls_files("aios_v1/public/frontend"), [], "K1: 396 file artifact ter-track")

    def test_no_demo_tahap_modules(self):
        demos = list((INNER_PKG / "lib").glob("demo_tahap*.py"))
        self.assertEqual(demos, [], f"K4: {len(demos)} demo_tahap* masih ada")

    def test_no_emoji_in_frontend(self):
        if not FRONTEND_SRC.exists() and not ADMIN_SRC.exists():
            self.skipTest("frontend/src dan admin/src belum tersedia")
        offenders = []
        for directory in (FRONTEND_SRC, ADMIN_SRC):
            for path in _iter_frontend_sources(directory):
                text = path.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), start=1):
                    for match in EMOJI_RE.finditer(line):
                        rel = path.relative_to(REPO_ROOT).as_posix()
                        offenders.append(f"{rel}:{lineno}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Emoji dekoratif di: {offenders}")

    def test_emoji_regex_detects_samples_and_ignores_plain_text(self):
        self.assertIsNotNone(EMOJI_RE.search("Performa: 📊"))
        self.assertIsNotNone(EMOJI_RE.search("Total: 💰"))
        self.assertIsNotNone(EMOJI_RE.search("Icon ✨"))
        self.assertIsNone(
            EMOJI_RE.search("Halo, client. AIOS · online · Mengirim… — Rp 363.000")
        )

    def test_no_silent_except_in_production_modules(self):
        """Setiap ExceptHandler log, raise, atau teruskan exception ke caller (AST).

        Modul dormant dikecualikan sementara (batch 1 = PoC aktif); #3 membersihkannya.
        """
        offenders = []
        for path in _iter_production_modules():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                continue  # modul lain yang gagal-parse bukan domain test ini
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and not _has_log_error_or_raise(node):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], f"Except tanpa log_error/raise: {offenders}")

    def test_no_db_commit_in_test_files(self):
        """Tidak ada frappe.db.commit() di file test_*.py (AST, docs/05.2 §G)."""
        offenders = []
        for path in INNER_PKG.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "commit"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "db"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], f"frappe.db.commit() di file test: {offenders}")
