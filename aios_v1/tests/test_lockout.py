"""P3: lockout login Frappe aktif (threshold + reset).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Mekanisme: `frappe.auth.LoginAttemptTracker` (System Settings:
`allow_consecutive_login_attempts`, `allow_login_after_fail`).
"""

import unittest

import frappe
from frappe.auth import get_login_attempt_tracker

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestLockout(IntegrationTestCase):
    EMAIL = "_test.lockout.user@example.com"

    def setUp(self):
        super().setUp()
        self.tracker = get_login_attempt_tracker(
            self.EMAIL, raise_locked_exception=False
        )
        self.tracker.add_success_attempt()

    def tearDown(self):
        tracker = get_login_attempt_tracker(self.EMAIL, raise_locked_exception=False)
        tracker.add_success_attempt()
        frappe.db.rollback()

    def test_locks_after_threshold(self):
        settings = frappe.get_doc("System Settings")
        max_attempts = settings.allow_consecutive_login_attempts
        self.assertGreater(
            max_attempts, 0, "lockout Frappe harus aktif (allow_consecutive_login_attempts > 0)"
        )

        tracker = get_login_attempt_tracker(self.EMAIL, raise_locked_exception=False)
        for _ in range(max_attempts + 1):
            tracker.add_failure_attempt()

        self.assertFalse(tracker.is_user_allowed())
        with self.assertRaises(frappe.SecurityException):
            get_login_attempt_tracker(self.EMAIL)

    def test_success_resets_failures(self):
        tracker = get_login_attempt_tracker(self.EMAIL, raise_locked_exception=False)
        for _ in range(3):
            tracker.add_failure_attempt()
        self.assertTrue(tracker.is_user_allowed())

        tracker.add_success_attempt()
        self.assertIsNone(tracker.login_failed_count)
        self.assertTrue(tracker.is_user_allowed())
