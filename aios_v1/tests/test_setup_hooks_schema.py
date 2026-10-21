"""Kontrak statis setup identitas Frappe (#4b fondasi).

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
Bukti runtime (tabCustom Field, Role, Role Profile) butuh `bench --site ... run-tests`.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPO_ROOT / "aios_v1" / "hooks.py"
SETUP = REPO_ROOT / "aios_v1" / "setup.py"


class TestSetupHooks(unittest.TestCase):
    def test_hooks_registered(self):
        src = HOOKS.read_text(encoding="utf-8")
        self.assertIn('after_install = "aios_v1.setup.after_install"', src)
        self.assertIn('after_migrate = "aios_v1.setup.after_migrate"', src)
        self.assertIn('on_login = "aios_v1.setup.on_login"', src)
        self.assertIn('auth_hooks = ["aios_v1.setup.validate_aios_status"]', src)
        self.assertIn('"validate": "aios_v1.setup.sync_aios_status_enabled"', src)

    def test_no_fixtures(self):
        src = HOOKS.read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^\s*fixtures\s*=")

    def test_custom_fields_use_official_api(self):
        src = SETUP.read_text(encoding="utf-8")
        self.assertIn("create_custom_fields(USER_CUSTOM_FIELDS, update=True)", src)
        self.assertNotIn('doc.append("fields"', src)

    def test_six_user_custom_fields(self):
        src = SETUP.read_text(encoding="utf-8")
        fields = re.findall(r'"fieldname": "(aios_[a-z_]+)"', src)
        self.assertEqual(
            sorted(fields),
            sorted(
                [
                    "aios_persona",
                    "aios_persona_context",
                    "aios_status",
                    "aios_company_name",
                    "aios_token_limit",
                    "aios_tokens_used",
                ]
            ),
        )

    def test_roles_and_profiles(self):
        src = SETUP.read_text(encoding="utf-8")
        self.assertIn('"AIOS Admin": 1', src)
        self.assertIn('"AIOS Client": 0', src)
        self.assertIn("AIOS Admin Profile", src)
        self.assertIn("AIOS Client Profile", src)
        self.assertIn("role.desk_access = desk_access", src)

    def test_auth_guards(self):
        src = SETUP.read_text(encoding="utf-8")
        self.assertIn("def _is_aios_user(user: str)", src)
        self.assertIn("def on_login(login_manager)", src)
        self.assertIn("def validate_aios_status()", src)
        self.assertIn("def sync_aios_status_enabled(doc, method=None)", src)
        self.assertIn('{"AIOS Admin", "AIOS Client"}', src)


if __name__ == "__main__":
    unittest.main()
