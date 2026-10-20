"""Saat `frappe` tidak tersedia (CI), hanya test murni-statis yang dikumpulkan.

14 file di direktori ini meng-`import frappe` di module level. Tanpa frappe, pytest
berhenti di fase collect (`Interrupted: ... errors during collection`, exit 2) —
`@unittest.skip` tidak pernah dievaluasi. Karena itu suite integrasi dibuang dari
collection, bukan di-skip.
"""

import importlib.util
from pathlib import Path

if importlib.util.find_spec("frappe") is None:
    STATIC = {"test_app_structure.py", "test_repo_hygiene.py", "test_import_smoke.py"}
    collect_ignore = [
        p.name for p in Path(__file__).parent.glob("test_*.py") if p.name not in STATIC
    ]
