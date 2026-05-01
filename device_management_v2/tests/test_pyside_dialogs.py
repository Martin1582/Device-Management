import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dmv2.ui.dialogs import AssignmentDialog, AssetDialog, PersonDialog


class PySideDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_asset_dialog_returns_clean_values(self):
        dialog = AssetDialog(None, "Test", scanned_identifier=" nb-42 ")
        dialog.model_edit.setText(" ThinkPad ")
        dialog.manufacturer_edit.setText(" Lenovo ")
        dialog.status_combo.setCurrentText("inactive")
        dialog.source_edit.setText(" alt-42 ")
        dialog.notes_edit.setPlainText(" Notiz ")

        values = dialog.values()

        self.assertEqual(values["device_type"], "Notebook")
        self.assertEqual(values["asset_tag"], "nb-42")
        self.assertEqual(values["model_name"], "ThinkPad")
        self.assertEqual(values["manufacturer"], "Lenovo")
        self.assertEqual(values["inventory_status"], "inactive")
        self.assertEqual(values["source_asset_tag"], "alt-42")
        self.assertEqual(values["notes"], "Notiz")

    def test_person_dialog_returns_clean_values(self):
        dialog = PersonDialog(None)
        dialog.name_edit.setText(" Max Mustermann ")
        dialog.email_edit.setText(" max@example.org ")
        dialog.department_edit.setText(" IT ")

        values = dialog.values()

        self.assertEqual(values["display_name"], "Max Mustermann")
        self.assertEqual(values["email"], "max@example.org")
        self.assertEqual(values["department"], "IT")

    def test_assignment_dialog_ignores_hostname_for_smartphones(self):
        asset = {"device_type": "Smartphone", "asset_tag": "PH-1", "model_name": "iPhone"}
        people = [{"id": 7, "display_name": "Anna Beispiel"}]
        dialog = AssignmentDialog(None, asset, people)
        dialog.hostname_edit.setText("LT-IGNORED")
        dialog.notes_edit.setPlainText(" Ausgabe ")

        values = dialog.values()

        self.assertEqual(values["person_id"], 7)
        self.assertEqual(values["hostname"], "")
        self.assertEqual(values["notes"], "Ausgabe")


if __name__ == "__main__":
    unittest.main()
