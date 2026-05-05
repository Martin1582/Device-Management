import gc
import sqlite3
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from dmv2.config import load_config, resolve_database_path
from dmv2.db.migrations import SCHEMA_VERSION
from dmv2.db.repository import DatabaseRepository


class ConfigAndRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_config_uses_defaults_when_file_is_missing(self):
        config = load_config(Path(tempfile.gettempdir()) / "missing_v2_config.json")

        self.assertEqual(config["app_name"], "Device Management v2")
        self.assertEqual(config["theme"], "Light")

    def test_load_config_accepts_utf8_bom(self):
        config_path = self.temp_dir / "config.json"
        config_path.write_text('{"app_name": "BOM Test"}', encoding="utf-8-sig")

        config = load_config(config_path)

        self.assertEqual(config["app_name"], "BOM Test")

    def test_resolve_database_path_returns_absolute_path(self):
        config = {"database_path": "data/example.db"}

        path = resolve_database_path(config)

        self.assertTrue(path.is_absolute())
        self.assertEqual(path.name, "example.db")

    def test_repository_creates_database_and_schema_version(self):
        db_path = self.temp_dir / "data" / "v2.db"

        repository = DatabaseRepository(db_path)
        status = repository.get_status()

        self.assertTrue(db_path.exists())
        self.assertEqual(status.schema_version, SCHEMA_VERSION)
        self.assertEqual(status.asset_count, 0)
        self.assertEqual(status.people_count, 0)
        self.assertEqual(status.assignment_count, 0)

    def test_repository_migrates_legacy_assets_into_new_tables(self):
        db_path = self.temp_dir / "legacy.db"
        self._create_legacy_database(db_path)

        repository = DatabaseRepository(db_path)
        status = repository.get_status()

        self.assertEqual(status.schema_version, SCHEMA_VERSION)
        self.assertEqual(status.asset_count, 2)
        self.assertEqual(status.people_count, 2)
        self.assertEqual(status.assignment_count, 2)

    def test_repository_status_counts_existing_rows(self):
        db_path = self.temp_dir / "status.db"
        repository = DatabaseRepository(db_path)
        self._seed_v2_rows(db_path)

        status = repository.get_status()

        self.assertEqual(status.asset_count, 1)
        self.assertEqual(status.people_count, 1)
        self.assertEqual(status.assignment_count, 1)

    def test_repository_migrates_v3_people_table_to_record_version(self):
        db_path = self.temp_dir / "v3_people.db"
        self._create_v3_style_database(db_path)

        repository = DatabaseRepository(db_path)
        status = repository.get_status()

        self.assertEqual(status.schema_version, SCHEMA_VERSION)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            columns = {
                row["name"]: row
                for row in conn.execute("PRAGMA table_info(people)").fetchall()
            }
            self.assertIn("record_version", columns)
            self.assertEqual(columns["record_version"]["dflt_value"], "1")

    def test_repository_migrates_v4_database_to_edit_claims_table(self):
        db_path = self.temp_dir / "v4_claims.db"
        self._create_v4_style_database(db_path)

        repository = DatabaseRepository(db_path)
        status = repository.get_status()

        self.assertEqual(status.schema_version, SCHEMA_VERSION)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            self.assertIn("edit_claims", tables)

    def _create_legacy_database(self, db_path):
        import sqlite3

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    user_name TEXT,
                    asset_tag TEXT UNIQUE,
                    model TEXT,
                    extra_info TEXT,
                    status TEXT DEFAULT 'Aktiv'
                )
                """
            )
            conn.execute(
                """
                INSERT INTO assets (type, user_name, asset_tag, model, extra_info, status)
                VALUES
                    ('Notebook', 'Max Mustermann', 'NB-001', 'Dell 7450', 'LT-MAX', 'Aktiv'),
                    ('Smartphone', 'Anna Beispiel', 'PH-010', 'iPhone 15', '0170111222', 'Inaktiv')
                """
            )
            conn.commit()

    def _seed_v2_rows(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO people (display_name, display_name_normalized)
                VALUES ('Chris Admin', 'chris admin')
                """
            )
            conn.execute(
                """
                INSERT INTO managed_assets (
                    device_type,
                    asset_tag,
                    asset_tag_normalized,
                    model_name,
                    inventory_status
                )
                VALUES ('Notebook', 'NB-200', 'NB-200', 'HP EliteBook', 'active')
                """
            )
            conn.execute(
                """
                INSERT INTO asset_assignments (
                    asset_id,
                    person_id,
                    hostname,
                    hostname_normalized,
                    assignment_status,
                    created_by,
                    updated_by
                )
                VALUES (1, 1, 'LT-CHRIS', 'lt-chris', 'active', 'test', 'test')
                """
            )
            conn.commit()

    def _create_v3_style_database(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_version (version) VALUES (3)")
            conn.execute(
                """
                CREATE TABLE people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    display_name_normalized TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE managed_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_type TEXT NOT NULL,
                    asset_tag TEXT NOT NULL,
                    asset_tag_normalized TEXT NOT NULL UNIQUE,
                    model_name TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    inventory_status TEXT NOT NULL DEFAULT 'active',
                    notes TEXT NOT NULL DEFAULT '',
                    source_asset_tag TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE asset_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    person_id INTEGER,
                    hostname TEXT NOT NULL DEFAULT '',
                    hostname_normalized TEXT NOT NULL DEFAULT '',
                    assignment_status TEXT NOT NULL DEFAULT 'active',
                    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    returned_at TEXT,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def _create_v4_style_database(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_version (version) VALUES (4)")
            conn.execute(
                """
                CREATE TABLE people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    display_name_normalized TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE managed_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_type TEXT NOT NULL,
                    asset_tag TEXT NOT NULL,
                    asset_tag_normalized TEXT NOT NULL UNIQUE,
                    model_name TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    inventory_status TEXT NOT NULL DEFAULT 'active',
                    notes TEXT NOT NULL DEFAULT '',
                    source_asset_tag TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE asset_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    person_id INTEGER,
                    hostname TEXT NOT NULL DEFAULT '',
                    hostname_normalized TEXT NOT NULL DEFAULT '',
                    assignment_status TEXT NOT NULL DEFAULT 'active',
                    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    returned_at TEXT,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()


if __name__ == "__main__":
    unittest.main()
