"""Test guard koneksi DB eksternal (N5/S12). Murni stdlib, jalan di CI tanpa frappe."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from aios_v1.data_access.guard import is_public_ip, validate_external_db_config


class TestExternalDbGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aios-db-")

    def test_sqlite_path_inside_root_allowed(self):
        path = os.path.join(self.root, "client.db")
        validate_external_db_config("sqlite", {"path": path}, sqlite_root=self.root)

    def test_sqlite_path_outside_root_rejected(self):
        with self.assertRaises(ValueError):
            validate_external_db_config("sqlite", {"path": "/etc/passwd"}, sqlite_root=self.root)

    def test_sqlite_traversal_rejected(self):
        path = os.path.join(self.root, "..", "outside.db")
        with self.assertRaises(ValueError):
            validate_external_db_config("sqlite", {"path": path}, sqlite_root=self.root)

    def test_mysql_private_host_rejected(self):
        with self.assertRaises(ValueError):
            validate_external_db_config("mysql", {"host": "127.0.0.1", "port": 3306})

    def test_mysql_link_local_metadata_rejected(self):
        with self.assertRaises(ValueError):
            validate_external_db_config("mysql", {"host": "169.254.169.254", "port": 3306})

    def test_mysql_public_ip_allowed(self):
        validate_external_db_config("mysql", {"host": "8.8.8.8", "port": 3306})

    def test_mysql_disallowed_port_rejected(self):
        with self.assertRaises(ValueError):
            validate_external_db_config("mysql", {"host": "8.8.8.8", "port": 3307})

    def test_mysql_missing_host_rejected(self):
        with self.assertRaises(ValueError):
            validate_external_db_config("mysql", {"port": 3306})

    def test_is_public_ip(self):
        self.assertTrue(is_public_ip("8.8.8.8"))
        self.assertFalse(is_public_ip("10.0.0.1"))
        self.assertFalse(is_public_ip("127.0.0.1"))
        self.assertFalse(is_public_ip("169.254.169.254"))
        self.assertFalse(is_public_ip("::ffff:127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
