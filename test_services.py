import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from asset_manager.db import DatabaseManager
from asset_manager.services import (
    build_duplicate_report,
    create_backup,
    import_assets_from_workbook,
    parse_asset_rows_from_workbook,
    restore_backup,
    write_import_protocol,
)


class ExcelImportServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_workbook(self, rows, filename="import.xlsx"):
        workbook = Workbook()
        worksheet = workbook.active
        for row in rows:
            worksheet.append(row)
        file_path = self.base_path / filename
        workbook.save(file_path)
        workbook.close()
        return file_path

    def test_parse_rows_with_alias_headers_and_default_type(self):
        workbook_path = self.create_workbook(
            [
                ["User", "Modell", "S/N / IMEI", "Hostname", "Status"],
                ["Max Mustermann", "Dell 7440", "NB-100", "LT-MAX", "Aktiv"],
            ]
        )

        rows, errors = parse_asset_rows_from_workbook(workbook_path, default_type="Notebook")

        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["type"], "Notebook")
        self.assertEqual(rows[0]["asset_tag"], "NB-100")

    def test_import_creates_and_updates_assets(self):
        db_path = self.base_path / "assets.db"
        db = DatabaseManager(db_path)
        db.create_asset("Notebook", "Alt", "Dell", "NB-001", "OLD-HOST")

        workbook_path = self.create_workbook(
            [
                ["Typ", "User", "Modell", "S/N / IMEI", "Rufnummer / Hostname", "Status"],
                ["Notebook", "Neu", "Dell 7450", "NB-001", "NEW-HOST", "Aktiv"],
                ["Smartphone", "Anna", "iPhone 15", "PH-010", "01701234567", "Inaktiv"],
            ]
        )

        summary = import_assets_from_workbook(workbook_path, db)

        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(db.fetch_asset_by_tag("NB-001")["user_name"], "Neu")
        self.assertEqual(db.fetch_asset_by_tag("PH-010")["status"], "Inaktiv")
        self.assertEqual(db.fetch_asset_by_tag("PH-010")["extra_info"], "")

    def test_import_collects_row_errors(self):
        workbook_path = self.create_workbook(
            [
                ["Typ", "User", "Modell", "S/N / IMEI"],
                ["Notebook", "", "Dell 7450", "NB-001"],
                ["Unknown", "Anna", "iPhone 15", "PH-010"],
            ]
        )

        with self.assertRaises(ValueError) as context:
            parse_asset_rows_from_workbook(workbook_path)

        self.assertIn("Zeile 2", str(context.exception))
        self.assertIn("Zeile 3", str(context.exception))

    def test_import_skips_duplicate_asset_tags_inside_excel(self):
        workbook_path = self.create_workbook(
            [
                ["Typ", "User", "Modell", "S/N / IMEI"],
                ["Notebook", "Max", "Dell", "NB-001"],
                ["Notebook", "Julia", "HP", " nb-001 "],
            ]
        )

        rows, errors = parse_asset_rows_from_workbook(workbook_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Doppeltes Asset-Tag", errors[0])

    def test_write_import_protocol_creates_text_file(self):
        workbook_path = self.create_workbook(
            [
                ["Typ", "User", "Modell", "S/N / IMEI"],
                ["Notebook", "Max", "Dell", "NB-001"],
            ]
        )

        protocol_path = write_import_protocol(
            workbook_path,
            {"created": 1, "updated": 0, "skipped": 0, "errors": []},
            default_type="Notebook",
        )

        self.assertTrue(protocol_path.exists())
        self.assertIn("Importprotokoll", protocol_path.read_text(encoding="utf-8"))

    def test_backup_and_restore_copy_database(self):
        source = self.base_path / "source.db"
        source.write_text("db-content", encoding="utf-8")
        backup = self.base_path / "backup.db"
        restored = self.base_path / "restored.db"

        create_backup(source, backup)
        restore_backup(backup, restored)

        self.assertEqual(restored.read_text(encoding="utf-8"), "db-content")

    def test_duplicate_report_detects_missing_hostname(self):
        rows = [
            {
                "type": "Notebook",
                "user_name": "Max",
                "model": "Dell",
                "asset_tag": "NB-1",
                "extra_info": "",
                "status": "Aktiv",
                "updated_at": "",
                "updated_by": "",
            }
        ]

        issues = build_duplicate_report(rows)

        self.assertEqual(len(issues), 1)
        self.assertIn("ohne Hostname", issues[0])


if __name__ == "__main__":
    unittest.main()
