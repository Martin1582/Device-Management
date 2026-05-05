import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from dmv2.db.repository import DatabaseRepository
from dmv2.services.importer import build_import_preview, import_preview_rows


class ImporterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.repository = DatabaseRepository(self.work_dir / "assets.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_import_preview_marks_valid_csv_row_importable(self):
        file_path = self._write_csv(
            [
                ["Typ", "SN / IMEI", "Modell", "Hersteller", "Status", "User", "Hostname"],
                ["Notebook", "nb-001", "ThinkPad T14", "Lenovo", "aktiv", "Max Mustermann", "LT-MAX"],
            ]
        )

        preview = build_import_preview(file_path, self.repository)

        self.assertEqual(preview.total_count, 1)
        self.assertEqual(preview.importable_count, 1)
        self.assertEqual(preview.rows[0].asset_tag, "NB-001")
        self.assertEqual(preview.rows[0].inventory_status, "active")

    def test_build_import_preview_marks_existing_asset_as_duplicate(self):
        self.repository.create_asset("Notebook", "NB-001", "ThinkPad T14")
        file_path = self._write_csv(
            [
                ["Typ", "SN / IMEI", "Modell"],
                ["Notebook", "NB-001", "ThinkPad T14"],
            ]
        )

        preview = build_import_preview(file_path, self.repository)

        self.assertEqual(preview.importable_count, 0)
        self.assertEqual(preview.duplicate_count, 1)
        self.assertIn("existiert bereits", preview.rows[0].message_text)

    def test_build_import_preview_marks_missing_required_values_as_error(self):
        file_path = self._write_csv(
            [
                ["Typ", "SN / IMEI", "Modell"],
                ["Notebook", "", "ThinkPad T14"],
            ]
        )

        preview = build_import_preview(file_path, self.repository)

        self.assertEqual(preview.importable_count, 0)
        self.assertEqual(preview.error_count, 1)
        self.assertIn("SN / IMEI fehlt", preview.rows[0].message_text)

    def test_build_import_preview_reads_xlsx_files(self):
        file_path = self.work_dir / "assets.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Typ", "SN / IMEI", "Modell", "Status"])
        worksheet.append(["Smartphone", "359999", "iPhone 15", "inactive"])
        workbook.save(file_path)
        workbook.close()

        preview = build_import_preview(file_path, self.repository)

        self.assertEqual(preview.importable_count, 1)
        self.assertEqual(preview.rows[0].device_type, "Smartphone")
        self.assertEqual(preview.rows[0].inventory_status, "inactive")

    def test_import_preview_rows_creates_assets_people_and_assignments(self):
        file_path = self._write_csv(
            [
                ["Typ", "SN / IMEI", "Modell", "User", "Hostname"],
                ["Notebook", "NB-002", "EliteBook", "Anna Beispiel", "LT-ANNA"],
                ["Smartphone", "PH-002", "iPhone 15", "Anna Beispiel", "IGNORED"],
            ]
        )
        preview = build_import_preview(file_path, self.repository)

        summary = import_preview_rows(preview, self.repository, actor="test-import")

        snapshots = self.repository.list_asset_snapshots()
        self.assertEqual(summary.created_assets, 2)
        self.assertEqual(summary.created_assignments, 2)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["assigned_to"], "Anna Beispiel")
        self.assertEqual(snapshots[1]["assigned_to"], "Anna Beispiel")
        self.assertEqual(snapshots[1]["hostname"], "")

    def test_import_preview_rows_skips_invalid_rows(self):
        file_path = self._write_csv(
            [
                ["Typ", "SN / IMEI", "Modell"],
                ["Notebook", "NB-003", "Latitude"],
                ["Notebook", "", "Latitude"],
            ]
        )
        preview = build_import_preview(file_path, self.repository)

        summary = import_preview_rows(preview, self.repository)

        self.assertEqual(summary.created_assets, 1)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(len(self.repository.list_assets()), 1)

    def _write_csv(self, rows):
        file_path = self.work_dir / "assets.csv"
        with file_path.open("w", encoding="utf-8-sig", newline="") as file_handle:
            writer = csv.writer(file_handle, delimiter=";")
            writer.writerows(rows)
        return file_path


if __name__ == "__main__":
    unittest.main()
