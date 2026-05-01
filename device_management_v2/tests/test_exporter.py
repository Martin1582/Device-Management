import csv
import tempfile
import unittest
from pathlib import Path

from dmv2.services.exporter import (
    build_export_filename,
    export_asset_snapshots_to_csv,
    export_asset_snapshots_to_html,
)


class ExporterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.rows = [
            {
                "device_type": "Notebook",
                "asset_tag": "NB-001",
                "model_name": "ThinkPad",
                "manufacturer": "Lenovo",
                "inventory_status": "active",
                "assigned_to": "Max Mustermann",
                "hostname": "LT-MAX",
                "assignment_status": "active",
                "updated_at": "2026-05-01 10:00:00",
                "notes": "Pilot",
            }
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_asset_snapshots_to_csv_writes_expected_columns(self):
        output_path = self.output_dir / "assets.csv"

        export_asset_snapshots_to_csv(self.rows, output_path)

        with output_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
            rows = list(csv.reader(file_handle, delimiter=";"))

        self.assertEqual(rows[0][:4], ["Typ", "SN / IMEI", "Modell", "Hersteller"])
        self.assertEqual(rows[1][:4], ["Notebook", "NB-001", "ThinkPad", "Lenovo"])
        self.assertIn("Max Mustermann", rows[1])

    def test_export_asset_snapshots_to_html_escapes_values(self):
        output_path = self.output_dir / "assets.html"
        rows = [self.rows[0] | {"notes": "<script>alert(1)</script>"}]

        export_asset_snapshots_to_html(rows, output_path, title="Inventar <Test>")

        html = output_path.read_text(encoding="utf-8")
        self.assertIn("Inventar &lt;Test&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_export_asset_snapshots_to_html_handles_empty_rows(self):
        output_path = self.output_dir / "empty.html"

        export_asset_snapshots_to_html([], output_path)

        html = output_path.read_text(encoding="utf-8")
        self.assertIn("Keine Assets in der aktuellen Ansicht.", html)
        self.assertIn("Eintraege: 0", html)

    def test_build_export_filename_uses_extension_without_double_dot(self):
        filename = build_export_filename(".csv")

        self.assertTrue(filename.startswith("DeviceManagementV2_Assets_"))
        self.assertTrue(filename.endswith(".csv"))
        self.assertNotIn("..csv", filename)


if __name__ == "__main__":
    unittest.main()
