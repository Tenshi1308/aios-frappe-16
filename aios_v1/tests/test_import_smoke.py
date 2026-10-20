"""Import smoke test: seluruh modul dalam paket aios_v1 harus bisa di-import.

Target #0 (K10/K11): baseline terukur. Modul di KNOWN_BROKEN diharapkan gagal
(xfail), kegagalan di luar daftar = FAIL biasa. Denominator dihitung dinamis
via Path.rglob — tidak di-hardcode (setup_poc/ untracked, demo_tahap* dihapus #3).
"""

import importlib
import unittest
from pathlib import Path

try:
    import frappe

    HAVE_FRAPPE = True
except Exception:
    HAVE_FRAPPE = False

import aios_v1  # dipakai untuk menentukan akar paket

# 11 modul yang diketahui rusak (nama modul, bukan jumlah):
# ImportError: cannot import name 'chat_completion' from 'aios_v1.lib.llm_client'
KNOWN_BROKEN = frozenset(
    f"aios_v1.lib.demo_tahap{i}"
    for i in (["1"] + [f"6m_{n}" for n in range(2, 12)])
)


def iter_module_names():
    """Kembalikan nama modul unik dari seluruh file .py di dalam paket aios_v1."""
    root = Path(aios_v1.__file__).parent
    seen = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root.parent)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(parts)
        if name and name not in seen:  # dedupe: api.py + api/__init__.py -> aios_v1.api
            seen.add(name)
            yield name


class TestImportSmoke(unittest.TestCase):
    maxDiff = None

    @unittest.skipUnless(HAVE_FRAPPE, "frappe tidak importable (CI tanpa frappe) — jalankan via bench")
    def test_all_modules_importable(self):
        import sys

        failures = []
        for name in iter_module_names():
            snapshot_path = list(sys.path)
            try:
                importlib.import_module(name)
            except Exception as exc:  # kumpulkan, jangan raise di tengah loop
                failures.append((name, f"{type(exc).__name__}: {exc}"))
            finally:
                # wajib: check_db.py mengeksekusi sys.path.insert(...) saat import
                sys.path[:] = snapshot_path

        unexpected = [f for f in failures if f[0] not in KNOWN_BROKEN]
        self.assertEqual(
            unexpected,
            [],
            "Modul gagal import di luar KNOWN_BROKEN:\n"
            + "\n".join(f"  {n}: {msg}" for n, msg in unexpected),
        )

    @unittest.skipUnless(HAVE_FRAPPE, "frappe tidak importable (CI tanpa frappe) — jalankan via bench")
    def test_known_broken_modules_fail(self):
        """Guard kebalikan: anggota KNOWN_BROKEN memang gagal (mencegah daftar basi)."""
        import sys

        for name in sorted(KNOWN_BROKEN):
            snapshot_path = list(sys.path)
            try:
                importlib.import_module(name)
            except Exception:
                continue  # sesuai ekspektasi (xfail)
            finally:
                sys.path[:] = snapshot_path
            self.fail(f"{name} masuk KNOWN_BROKEN tapi berhasil di-import — hapus dari daftar")
