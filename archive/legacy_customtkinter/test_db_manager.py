import sqlite3
import tempfile
import unittest
from pathlib import Path

from asset_manager.db import DatabaseManager


class DatabaseManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_assets.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_fetch_asset(self):
        self.db.create_asset("Notebook", "Max Mustermann", "Dell Latitude", "NB-001", "LT-MAX")

        asset = self.db.fetch_asset_by_tag("NB-001")

        self.assertIsNotNone(asset)
        self.assertEqual(asset["user_name"], "Max Mustermann")
        self.assertEqual(asset["extra_info"], "LT-MAX")
        self.assertEqual(asset["status"], "Aktiv")

    def test_update_asset_changes_fields_without_duplicate(self):
        self.db.create_asset("Smartphone", "Anna", "iPhone", "PH-001", "01701234567")

        self.db.update_asset("PH-001", "Smartphone", "Anna Schmidt", "iPhone 15", "PH-002", "01707654321")

        self.assertIsNone(self.db.fetch_asset_by_tag("PH-001"))
        updated_asset = self.db.fetch_asset_by_tag("PH-002")
        self.assertEqual(updated_asset["user_name"], "Anna Schmidt")
        self.assertEqual(updated_asset["model"], "iPhone 15")
        self.assertEqual(updated_asset["extra_info"], "")

    def test_deactivate_asset_sets_status(self):
        self.db.create_asset("Notebook", "Chris", "HP EliteBook", "NB-010", "LT-CHRIS")

        self.db.deactivate_asset("NB-010")

        asset = self.db.fetch_asset_by_tag("NB-010")
        self.assertEqual(asset["status"], "Inaktiv")

    def test_duplicate_asset_tag_raises_integrity_error(self):
        self.db.create_asset("Notebook", "User A", "Dell", "DUP-1", "HOST-A")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.create_asset("Notebook", "User B", "Dell", "DUP-1", "HOST-B")

    def test_duplicate_asset_tag_is_case_insensitive(self):
        self.db.create_asset("Notebook", "User A", "Dell", "dup-2", "HOST-A")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.create_asset("Notebook", "User B", "Dell", " DUP-2 ", "HOST-B")

    def test_duplicate_extra_info_raises_integrity_error_per_device_type(self):
        self.db.create_asset("Notebook", "User A", "Dell", "NB-100", "HOST-X")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.create_asset("Notebook", "User B", "HP", "NB-101", " host-x ")

    def test_smartphone_extra_info_is_ignored(self):
        self.db.create_asset("Smartphone", "User A", "iPhone", "PH-300", "0170111222")

        asset = self.db.fetch_asset_by_tag("PH-300")

        self.assertEqual(asset["extra_info"], "")

    def test_delete_asset_removes_record(self):
        self.db.create_asset("Notebook", "Chris", "HP EliteBook", "NB-020", "LT-DEL")

        self.db.delete_asset("nb-020")

        self.assertIsNone(self.db.fetch_asset_by_tag("NB-020"))

    def test_fetch_last_updated_at_returns_value_after_create(self):
        self.db.create_asset("Notebook", "Chris", "HP EliteBook", "NB-030", "LT-TIME")

        updated_at = self.db.fetch_last_updated_at()

        self.assertIsNotNone(updated_at)

    def test_history_is_written_for_create_and_delete(self):
        self.db.create_asset("Notebook", "Chris", "HP EliteBook", "NB-040", "LT-HIST", actor="tester")
        self.db.delete_asset("NB-040", actor="tester")

        history = self.db.fetch_history("NB-040")

        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "deleted")


if __name__ == "__main__":
    unittest.main()
