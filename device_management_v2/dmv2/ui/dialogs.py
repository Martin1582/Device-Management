from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from ..db.repository import ConflictError, DatabaseRepository


DEVICE_TYPES = ("Notebook", "Smartphone")
INVENTORY_STATUSES = ("active", "inactive", "retired")


def _text(value) -> str:
    if value is None:
        return ""
    return str(value)


class AssetDialog(QDialog):
    def __init__(self, parent, title: str, asset: dict | None = None, scanned_identifier: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        self.type_combo = QComboBox()
        self.type_combo.addItems(DEVICE_TYPES)
        self.asset_tag_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.manufacturer_edit = QLineEdit()
        self.status_combo = QComboBox()
        self.status_combo.addItems(INVENTORY_STATUSES)
        self.source_edit = QLineEdit()
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(100)

        if asset:
            self.type_combo.setCurrentText(asset["device_type"])
            self.asset_tag_edit.setText(asset["asset_tag"])
            self.model_edit.setText(asset["model_name"])
            self.manufacturer_edit.setText(asset["manufacturer"] or "")
            self.status_combo.setCurrentText(asset["inventory_status"])
            self.source_edit.setText(asset["source_asset_tag"] or "")
            self.notes_edit.setPlainText(asset["notes"] or "")
        elif scanned_identifier:
            self.asset_tag_edit.setText(scanned_identifier)

        form = QFormLayout()
        form.addRow("Typ", self.type_combo)
        form.addRow("SN / IMEI", self.asset_tag_edit)
        form.addRow("Modell", self.model_edit)
        form.addRow("Hersteller", self.manufacturer_edit)
        form.addRow("Inventarstatus", self.status_combo)
        form.addRow("Quelle / Alt-ID", self.source_edit)
        form.addRow("Notizen", self.notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "device_type": self.type_combo.currentText(),
            "asset_tag": self.asset_tag_edit.text().strip(),
            "model_name": self.model_edit.text().strip(),
            "manufacturer": self.manufacturer_edit.text().strip(),
            "inventory_status": self.status_combo.currentText(),
            "source_asset_tag": self.source_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
        }


class PersonDialog(QDialog):
    def __init__(self, parent, person: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Person")
        self.setMinimumWidth(460)

        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.department_edit = QLineEdit()
        if person:
            self.name_edit.setText(person["display_name"])
            self.email_edit.setText(person["email"] or "")
            self.department_edit.setText(person["department"] or "")

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("E-Mail", self.email_edit)
        form.addRow("Abteilung", self.department_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "display_name": self.name_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "department": self.department_edit.text().strip(),
        }


class AssignmentDialog(QDialog):
    def __init__(self, parent, asset: dict, people: list[dict], assignment: dict | None = None):
        super().__init__(parent)
        self.asset = asset
        self.people = people
        self.setWindowTitle("Zuweisung")
        self.setMinimumWidth(520)

        self.person_combo = QComboBox()
        for person in people:
            self.person_combo.addItem(person["display_name"], person["id"])

        self.hostname_edit = QLineEdit()
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(100)

        if assignment:
            index = self.person_combo.findData(assignment["person_id"])
            if index >= 0:
                self.person_combo.setCurrentIndex(index)
            self.hostname_edit.setText(assignment["hostname"] or "")
            self.notes_edit.setPlainText(assignment["notes"] or "")

        if asset["device_type"] == "Smartphone":
            self.hostname_edit.setPlaceholderText("Wird fuer Smartphones ignoriert")
            self.hostname_edit.setEnabled(False)

        form = QFormLayout()
        form.addRow("Asset", QLabel(f"{asset['asset_tag']} | {asset['model_name']}"))
        form.addRow("Person", self.person_combo)
        form.addRow("Hostname", self.hostname_edit)
        form.addRow("Notizen", self.notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "person_id": self.person_combo.currentData(),
            "hostname": "" if self.asset["device_type"] == "Smartphone" else self.hostname_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
        }


class PeopleDialog(QDialog):
    def __init__(self, parent, repository: DatabaseRepository):
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("Personenverwaltung")
        self.resize(820, 560)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "E-Mail", "Abteilung"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        add_button = QPushButton("Neu")
        add_button.clicked.connect(self.add_person)
        edit_button = QPushButton("Bearbeiten")
        edit_button.clicked.connect(self.edit_person)
        delete_button = QPushButton("Loeschen")
        delete_button.clicked.connect(self.delete_person)
        close_button = QPushButton("Schliessen")
        close_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addWidget(add_button)
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        actions.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(actions)
        self.refresh()

    def selected_person(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        person_id = int(self.table.item(row, 0).data(Qt.UserRole))
        for person in self.repository.list_people():
            if person["id"] == person_id:
                return person
        return None

    def refresh(self) -> None:
        people = self.repository.list_people()
        self.table.setRowCount(len(people))
        for row, person in enumerate(people):
            values = [person["id"], person["display_name"], person["email"], person["department"]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(_text(value))
                item.setData(Qt.UserRole, person["id"])
                self.table.setItem(row, column, item)

    def add_person(self) -> None:
        dialog = PersonDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.repository.create_or_update_person(**dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Person", str(exc))
            return
        self.refresh()

    def edit_person(self) -> None:
        person = self.selected_person()
        if not person:
            QMessageBox.information(self, "Person", "Bitte zuerst eine Person auswaehlen.")
            return
        dialog = PersonDialog(self, person)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.repository.update_person(person["id"], **dialog.values(), expected_record_version=person["record_version"])
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Person", str(exc))
            return
        self.refresh()

    def delete_person(self) -> None:
        person = self.selected_person()
        if not person:
            QMessageBox.information(self, "Person", "Bitte zuerst eine Person auswaehlen.")
            return
        if QMessageBox.question(self, "Person loeschen", f"{person['display_name']} wirklich loeschen?") != QMessageBox.Yes:
            return
        try:
            self.repository.delete_person(person["id"], actor="pyside-ui", expected_record_version=person["record_version"])
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Person", str(exc))
            return
        self.refresh()
