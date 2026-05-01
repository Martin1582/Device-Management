from __future__ import annotations

import getpass
import socket
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config, resolve_database_path
from ..db.repository import ConflictError, DatabaseRepository, EditClaimError
from ..services.exporter import (
    build_export_filename,
    export_asset_snapshots_to_csv,
    export_asset_snapshots_to_html,
)
from ..services.scanner import decode_identifier_from_file, scanner_runtime_available
from .dialogs import AssignmentDialog, AssetDialog, PeopleDialog


INVENTORY_STATUSES = ("active", "inactive", "retired")


def _text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _short_date(value) -> str:
    if not value:
        return ""
    return str(value).replace("T", " ")


def _compact_path(path: Path) -> str:
    parts = path.parts
    if len(parts) <= 3:
        return str(path)
    return f"...\\{parts[-2]}\\{parts[-1]}"


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "0"):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("metricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value) -> None:
        self.value_label.setText(str(value))


class DeviceManagementV2Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.db_path = resolve_database_path(self.config_data)
        self.repository = DatabaseRepository(self.db_path)
        self.selected_asset_id: int | None = None
        self.selected_asset_record_version: int | None = None
        self.scanner_available = scanner_runtime_available()
        self.editor_label = f"{getpass.getuser()} @ {socket.gethostname()}"
        self.editor_id = f"{self.editor_label} :: {uuid.uuid4().hex[:8]}"
        self.asset_rows: list[dict] = []
        self.filtered_asset_rows: list[dict] = []

        self.setWindowTitle(self.config_data.get("app_name", "Device Management v2"))
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self._apply_icon()
        self._build_actions()
        self._build_ui()
        self._apply_styles()

        self.refresh_view()
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(lambda: self.refresh_view(origin="auto"))
        self.auto_refresh_timer.start(max(int(self.config_data.get("auto_refresh_seconds", 15)), 5) * 1000)

    def _resource_path(self, filename: str) -> Path:
        local_root = Path(__file__).resolve().parents[2]
        project_root = local_root.parent
        for candidate in (local_root / filename, project_root / filename):
            if candidate.exists():
                return candidate
        return local_root / filename

    def _apply_icon(self) -> None:
        icon_path = self._resource_path("BRNL.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_actions(self) -> None:
        self.refresh_action = QAction("Aktualisieren", self)
        self.refresh_action.triggered.connect(lambda: self.refresh_view(origin="manual"))
        self.new_asset_action = QAction("Asset neu", self)
        self.new_asset_action.triggered.connect(self.create_asset)
        self.edit_asset_action = QAction("Asset bearbeiten", self)
        self.edit_asset_action.triggered.connect(self.edit_asset)
        self.delete_asset_action = QAction("Asset loeschen", self)
        self.delete_asset_action.triggered.connect(self.delete_asset)
        self.people_action = QAction("Personen", self)
        self.people_action.triggered.connect(self.open_people_dialog)
        self.assign_action = QAction("Zuweisen", self)
        self.assign_action.triggered.connect(self.assign_asset)
        self.edit_assignment_action = QAction("Zuweisung bearbeiten", self)
        self.edit_assignment_action.triggered.connect(self.edit_assignment)
        self.return_action = QAction("Rueckgabe", self)
        self.return_action.triggered.connect(self.return_asset)
        self.scan_action = QAction("Code suchen", self)
        self.scan_action.triggered.connect(self.scan_identifier)
        self.export_csv_action = QAction("CSV exportieren", self)
        self.export_csv_action.triggered.connect(self.export_current_view_to_csv)
        self.print_html_action = QAction("Druckansicht", self)
        self.print_html_action.triggered.connect(self.export_current_view_to_html)

        toolbar = QToolBar("Hauptaktionen")
        toolbar.setMovable(False)
        toolbar.addAction(self.refresh_action)
        toolbar.addSeparator()
        toolbar.addAction(self.new_asset_action)
        toolbar.addAction(self.edit_asset_action)
        toolbar.addAction(self.delete_asset_action)
        toolbar.addSeparator()
        toolbar.addAction(self.people_action)
        toolbar.addAction(self.assign_action)
        toolbar.addAction(self.edit_assignment_action)
        toolbar.addAction(self.return_action)
        toolbar.addSeparator()
        toolbar.addAction(self.scan_action)
        toolbar.addSeparator()
        toolbar.addAction(self.export_csv_action)
        toolbar.addAction(self.print_html_action)
        self.addToolBar(toolbar)
        self._update_action_state()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Device Management v2")
        title.setObjectName("pageTitle")
        subtitle = QLabel("PySide6-Oberflaeche auf der bestehenden v2-Repository- und Migrationsschicht")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.db_badge = QLabel(f"Datenbank: {_compact_path(self.db_path)}")
        self.db_badge.setObjectName("badge")
        self.db_badge.setToolTip(str(self.db_path))
        self.scanner_badge = QLabel("Scanner aktiv" if self.scanner_available else "Scanner inaktiv")
        self.scanner_badge.setObjectName("badgeOk" if self.scanner_available else "badgeWarn")
        badges = QVBoxLayout()
        badges.addWidget(self.db_badge, alignment=Qt.AlignRight)
        badges.addWidget(self.scanner_badge, alignment=Qt.AlignRight)
        header.addLayout(title_box, 1)
        header.addLayout(badges)
        root.addLayout(header)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        self.asset_metric = MetricCard("Assets")
        self.people_metric = MetricCard("Personen")
        self.assignment_metric = MetricCard("Zuweisungen")
        self.schema_metric = MetricCard("Schema")
        metrics.addWidget(self.asset_metric, 0, 0)
        metrics.addWidget(self.people_metric, 0, 1)
        metrics.addWidget(self.assignment_metric, 0, 2)
        metrics.addWidget(self.schema_metric, 0, 3)
        root.addLayout(metrics)

        filter_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Suchen nach SN / IMEI, Modell, User oder Hostname")
        self.search_edit.textChanged.connect(self.apply_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Alle Status", *INVENTORY_STATUSES])
        self.status_filter.currentIndexChanged.connect(self.apply_filter)
        filter_bar.addWidget(self.search_edit, 1)
        filter_bar.addWidget(self.status_filter)
        root.addLayout(filter_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_asset_table())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        self.status_label = QLabel("Bereit")
        self.sync_label = QLabel("Noch nicht synchronisiert")
        statusbar.addWidget(self.status_label, 1)
        statusbar.addPermanentWidget(self.sync_label)

        self.setCentralWidget(central)

    def _build_asset_table(self) -> QWidget:
        box = QGroupBox("Asset-Uebersicht")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)
        self.asset_stack = QStackedWidget()
        self.asset_table = QTableWidget(0, 8)
        self.asset_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "SN / IMEI", "Modell", "Hersteller", "Status", "User", "Hostname"]
        )
        self.asset_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.asset_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.asset_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.asset_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.asset_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.asset_table.itemSelectionChanged.connect(self.handle_asset_selection)
        self.asset_table.doubleClicked.connect(self.edit_asset)
        self.asset_stack.addWidget(self.asset_table)
        self.asset_stack.addWidget(self._build_empty_asset_state())
        layout.addWidget(self.asset_stack, 1)
        return box

    def _build_empty_asset_state(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("emptyState")
        frame.setMinimumHeight(360)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(42, 42, 42, 42)
        layout.setSpacing(12)
        layout.addStretch(1)

        self.empty_title = QLabel("Noch keine Assets vorhanden")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_title)

        self.empty_body = QLabel(
            "Lege das erste Geraet an oder scanne einen Barcode/QR-Code, um direkt mit einer SN / IMEI zu starten."
        )
        self.empty_body.setObjectName("emptyBody")
        self.empty_body.setWordWrap(True)
        self.empty_body.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_body)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        new_asset_button = QPushButton("Asset anlegen")
        new_asset_button.setObjectName("primaryButton")
        new_asset_button.clicked.connect(self.create_asset)
        people_button = QPushButton("Personen pflegen")
        people_button.clicked.connect(self.open_people_dialog)
        scan_button = QPushButton("Code suchen")
        scan_button.clicked.connect(self.scan_identifier)
        scan_button.setEnabled(self.scanner_available)
        actions.addWidget(new_asset_button)
        actions.addWidget(people_button)
        actions.addWidget(scan_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(2)
        return frame

    def _build_detail_panel(self) -> QWidget:
        box = QGroupBox("Details")
        layout = QVBoxLayout(box)

        self.notice_label = QLabel("Noch kein Asset ausgewaehlt.")
        self.notice_label.setObjectName("notice")
        self.notice_label.setWordWrap(True)
        layout.addWidget(self.notice_label)

        self.tabs = QTabWidget()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.timeline_text = QTextEdit()
        self.timeline_text.setReadOnly(True)
        self.assignment_text = QTextEdit()
        self.assignment_text.setReadOnly(True)
        self.tabs.addTab(self.detail_text, "Asset")
        self.tabs.addTab(self.assignment_text, "Zuweisung")
        self.tabs.addTab(self.timeline_text, "Timeline")
        layout.addWidget(self.tabs, 1)
        return box

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fb;
                color: #172033;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 10pt;
            }
            QToolBar {
                background: #ffffff;
                border: 0;
                border-bottom: 1px solid #d7dee8;
                spacing: 6px;
                padding: 6px;
            }
            QToolButton, QPushButton {
                background: #17406f;
                color: #ffffff;
                border: 0;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QToolButton:hover, QPushButton:hover {
                background: #123257;
            }
            QToolButton:disabled, QPushButton:disabled {
                background: #c7d2de;
                color: #64748b;
            }
            QLineEdit, QComboBox, QTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #ccd6e2;
                border-radius: 5px;
                padding: 5px;
                selection-background-color: #17406f;
            }
            QHeaderView::section {
                background: #e9eff6;
                color: #243247;
                border: 0;
                border-right: 1px solid #d7dee8;
                padding: 7px;
                font-weight: 600;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 7px;
                margin-top: 20px;
                padding: 12px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            #pageTitle {
                font-size: 23pt;
                font-weight: 700;
                color: #14365d;
            }
            #pageSubtitle {
                color: #5a6f86;
            }
            #metricCard {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 7px;
            }
            #metricTitle {
                color: #5a6f86;
                font-weight: 600;
            }
            #metricValue {
                color: #14365d;
                font-size: 22pt;
                font-weight: 700;
            }
            #badge, #badgeOk, #badgeWarn, #notice {
                border-radius: 5px;
                padding: 6px 8px;
            }
            #badge {
                background: #e9eff6;
                color: #243247;
            }
            #badgeOk {
                background: #dff4e8;
                color: #17603a;
            }
            #badgeWarn {
                background: #f9ebcf;
                color: #8a5a00;
            }
            #notice {
                background: #e9eff6;
                color: #243247;
            }
            #emptyState {
                background: #ffffff;
                border: 1px dashed #b9c7d8;
                border-radius: 7px;
            }
            #emptyTitle {
                color: #14365d;
                font-size: 18pt;
                font-weight: 700;
            }
            #emptyBody {
                color: #5a6f86;
                font-size: 10pt;
            }
            #primaryButton {
                background: #0f766e;
            }
            #primaryButton:hover {
                background: #115e59;
            }
            """
        )

    def refresh_view(self, origin: str = "manual") -> None:
        try:
            status = self.repository.get_status()
            self.asset_rows = self.repository.list_asset_snapshots()
            claims = self.repository.list_edit_claims(
                entity_type="managed_asset",
                entity_ids=[row["id"] for row in self.asset_rows],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Aktualisieren", str(exc))
            return

        self.claims_by_asset_id = {claim["entity_id"]: claim for claim in claims}
        self.asset_metric.set_value(status.asset_count)
        self.people_metric.set_value(status.people_count)
        self.assignment_metric.set_value(status.assignment_count)
        self.schema_metric.set_value(status.schema_version)
        self.db_badge.setText(f"Datenbank: {_compact_path(self.db_path)}")
        self.apply_filter(keep_selection=True)
        self.sync_label.setText(f"Letzte Aktualisierung: {datetime.now().strftime('%H:%M:%S')}")
        if origin != "auto":
            self.status_label.setText("Ansicht aktualisiert.")

    def apply_filter(self, keep_selection: bool = False) -> None:
        selected_id = self.selected_asset_id if keep_selection else None
        query = self.search_edit.text().casefold().strip()
        status_filter = self.status_filter.currentText()

        rows = []
        for row in self.asset_rows:
            if status_filter != "Alle Status" and row["inventory_status"] != status_filter:
                continue
            haystack = " ".join(
                _text(row.get(key))
                for key in ("device_type", "asset_tag", "model_name", "manufacturer", "inventory_status", "assigned_to", "hostname")
            ).casefold()
            if query and query not in haystack:
                continue
            rows.append(row)
        self.filtered_asset_rows = rows

        self.asset_table.setRowCount(len(rows))
        self.asset_stack.setCurrentWidget(self.asset_table if rows else self.asset_stack.widget(1))
        matched_selected = False
        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["device_type"],
                row["asset_tag"],
                row["model_name"],
                row["manufacturer"],
                row["inventory_status"],
                row["assigned_to"] or "",
                row["hostname"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(_text(value))
                item.setData(Qt.UserRole, row["id"])
                if column == 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.asset_table.setItem(row_index, column, item)
            if selected_id == row["id"]:
                self.asset_table.selectRow(row_index)
                matched_selected = True

        if rows and (selected_id is None or not matched_selected):
            self.asset_table.selectRow(0)
            self.selected_asset_id = rows[0]["id"]
            self.update_detail_panel()
        elif not rows:
            self.selected_asset_id = None
            if self.asset_rows:
                self.empty_title.setText("Keine Treffer")
                self.empty_body.setText("Passe Suche oder Statusfilter an, um wieder Assets in der Liste zu sehen.")
            else:
                self.empty_title.setText("Noch keine Assets vorhanden")
                self.empty_body.setText(
                    "Lege das erste Geraet an oder scanne einen Barcode/QR-Code, um direkt mit einer SN / IMEI zu starten."
                )
            self.update_detail_panel()
        self._update_action_state()

    def handle_asset_selection(self) -> None:
        row = self.asset_table.currentRow()
        if row < 0:
            self.selected_asset_id = None
        else:
            self.selected_asset_id = int(self.asset_table.item(row, 0).data(Qt.UserRole))
        self.update_detail_panel()
        self._update_action_state()

    def selected_asset(self) -> dict | None:
        if self.selected_asset_id is None:
            return None
        return self.repository.get_asset(asset_id=self.selected_asset_id)

    def selected_assignment(self) -> dict | None:
        if self.selected_asset_id is None:
            return None
        return self.repository.get_current_assignment_for_asset(self.selected_asset_id)

    def update_detail_panel(self) -> None:
        asset = self.selected_asset()
        if not asset:
            self.notice_label.setText("Noch kein Asset ausgewaehlt.")
            self.detail_text.setPlainText("Bitte links ein Asset auswaehlen.")
            self.assignment_text.setPlainText("")
            self.timeline_text.setPlainText("")
            return

        assignment = self.selected_assignment()
        events = self.repository.list_timeline_for_asset(asset["id"])
        claim = self.claims_by_asset_id.get(asset["id"], None)
        if claim and claim["editor_id"] != self.editor_id:
            self.notice_label.setText(f"Wird gerade von {claim['editor_label']} bearbeitet.")
        else:
            self.notice_label.setText("Auswahl ist synchron.")

        self.selected_asset_record_version = asset["record_version"]
        detail_lines = [
            f"ID: {asset['id']}",
            f"Typ: {asset['device_type']}",
            f"SN / IMEI: {asset['asset_tag']}",
            f"Modell: {asset['model_name']}",
            f"Hersteller: {asset['manufacturer'] or '-'}",
            f"Inventarstatus: {asset['inventory_status']}",
            f"Quelle / Alt-ID: {asset['source_asset_tag'] or '-'}",
            f"Record-Version: {asset['record_version']}",
            f"Erstellt: {_short_date(asset['created_at'])}",
            f"Aktualisiert: {_short_date(asset['updated_at'])}",
            "",
            "Notizen:",
            asset["notes"] or "-",
        ]
        self.detail_text.setPlainText("\n".join(detail_lines))

        if assignment:
            person = self.repository.get_person(assignment["person_id"]) if assignment["person_id"] else None
            assignment_lines = [
                f"Person: {person['display_name'] if person else '-'}",
                f"Hostname: {assignment['hostname'] or '-'}",
                f"Status: {assignment['assignment_status']}",
                f"Zugewiesen am: {_short_date(assignment['assigned_at'])}",
                f"Angelegt von: {assignment['created_by'] or '-'}",
                f"Geaendert von: {assignment['updated_by'] or '-'}",
                f"Record-Version: {assignment['record_version']}",
                "",
                "Notizen:",
                assignment["notes"] or "-",
            ]
        else:
            assignment_lines = ["Keine aktive Zuweisung vorhanden."]
        self.assignment_text.setPlainText("\n".join(assignment_lines))

        if events:
            lines = []
            for event in events:
                lines.append(f"{event['created_at']} | {event['action']} | {event['actor'] or '-'}")
                lines.append(event["payload_json"])
                lines.append("")
            self.timeline_text.setPlainText("\n".join(lines).strip())
        else:
            self.timeline_text.setPlainText("Keine Audit-Ereignisse vorhanden.")

    def _update_action_state(self) -> None:
        has_asset = self.selected_asset_id is not None
        has_assignment = False
        if has_asset:
            try:
                has_assignment = self.selected_assignment() is not None
            except Exception:
                has_assignment = False
        self.edit_asset_action.setEnabled(has_asset)
        self.delete_asset_action.setEnabled(has_asset)
        self.assign_action.setEnabled(has_asset)
        self.edit_assignment_action.setEnabled(has_assignment)
        self.return_action.setEnabled(has_assignment)
        self.scan_action.setEnabled(self.scanner_available)
        has_visible_rows = bool(self.filtered_asset_rows)
        self.export_csv_action.setEnabled(has_visible_rows)
        self.print_html_action.setEnabled(has_visible_rows)

    def acquire_asset_claim(self, asset: dict) -> bool:
        try:
            self.repository.acquire_edit_claim(
                "managed_asset",
                asset["id"],
                editor_id=self.editor_id,
                editor_label=self.editor_label,
            )
            return True
        except EditClaimError as exc:
            QMessageBox.warning(self, "Bearbeitung gesperrt", str(exc))
            return False

    def release_asset_claim(self, asset_id: int) -> None:
        self.repository.release_edit_claim("managed_asset", asset_id, editor_id=self.editor_id)

    def create_asset(self) -> None:
        dialog = AssetDialog(self, "Asset anlegen")
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.repository.create_asset(**dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Asset anlegen", str(exc))
            return
        self.status_label.setText("Asset angelegt.")
        self.refresh_view(origin="local-write")

    def edit_asset(self) -> None:
        asset = self.selected_asset()
        if not asset:
            QMessageBox.information(self, "Asset bearbeiten", "Bitte zuerst ein Asset auswaehlen.")
            return
        if not self.acquire_asset_claim(asset):
            return
        try:
            dialog = AssetDialog(self, "Asset bearbeiten", asset)
            if dialog.exec() != QDialog.Accepted:
                return
            self.repository.update_asset(
                asset["id"],
                **dialog.values(),
                expected_record_version=asset["record_version"],
            )
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Asset bearbeiten", str(exc))
            return
        finally:
            self.release_asset_claim(asset["id"])
        self.status_label.setText("Asset gespeichert.")
        self.refresh_view(origin="local-write")

    def delete_asset(self) -> None:
        asset = self.selected_asset()
        if not asset:
            QMessageBox.information(self, "Asset loeschen", "Bitte zuerst ein Asset auswaehlen.")
            return
        if QMessageBox.question(self, "Asset loeschen", f"{asset['asset_tag']} wirklich loeschen?") != QMessageBox.Yes:
            return
        try:
            self.repository.delete_asset(asset["id"], actor="pyside-ui", expected_record_version=asset["record_version"])
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Asset loeschen", str(exc))
            return
        self.selected_asset_id = None
        self.status_label.setText("Asset geloescht.")
        self.refresh_view(origin="local-write")

    def open_people_dialog(self) -> None:
        dialog = PeopleDialog(self, self.repository)
        dialog.exec()
        self.refresh_view(origin="local-write")

    def assign_asset(self) -> None:
        asset = self.selected_asset()
        if not asset:
            QMessageBox.information(self, "Zuweisung", "Bitte zuerst ein Asset auswaehlen.")
            return
        people = self.repository.list_people()
        if not people:
            QMessageBox.warning(self, "Zuweisung", "Bitte zuerst mindestens eine Person anlegen.")
            return
        if not self.acquire_asset_claim(asset):
            return
        try:
            dialog = AssignmentDialog(self, asset, people)
            if dialog.exec() != QDialog.Accepted:
                return
            self.repository.assign_asset(asset_id=asset["id"], **dialog.values(), actor="pyside-ui")
        except Exception as exc:
            QMessageBox.critical(self, "Zuweisung", str(exc))
            return
        finally:
            self.release_asset_claim(asset["id"])
        self.status_label.setText("Zuweisung gespeichert.")
        self.refresh_view(origin="local-write")

    def edit_assignment(self) -> None:
        asset = self.selected_asset()
        assignment = self.selected_assignment()
        if not asset or not assignment:
            QMessageBox.information(self, "Zuweisung", "Dieses Asset hat keine aktive Zuweisung.")
            return
        people = self.repository.list_people()
        if not self.acquire_asset_claim(asset):
            return
        try:
            dialog = AssignmentDialog(self, asset, people, assignment)
            if dialog.exec() != QDialog.Accepted:
                return
            self.repository.update_current_assignment(
                asset["id"],
                **dialog.values(),
                actor="pyside-ui",
                expected_record_version=assignment["record_version"],
            )
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Zuweisung", str(exc))
            return
        finally:
            self.release_asset_claim(asset["id"])
        self.status_label.setText("Zuweisung gespeichert.")
        self.refresh_view(origin="local-write")

    def return_asset(self) -> None:
        asset = self.selected_asset()
        assignment = self.selected_assignment()
        if not asset or not assignment:
            QMessageBox.information(self, "Rueckgabe", "Dieses Asset hat keine aktive Zuweisung.")
            return
        if QMessageBox.question(self, "Rueckgabe", f"Zuweisung fuer {asset['asset_tag']} beenden?") != QMessageBox.Yes:
            return
        try:
            self.repository.return_asset(
                asset["id"],
                actor="pyside-ui",
                notes="Rueckgabe ueber PySide6 UI",
                expected_record_version=assignment["record_version"],
            )
        except ConflictError as exc:
            QMessageBox.warning(self, "Konflikt", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Rueckgabe", str(exc))
            return
        self.status_label.setText("Rueckgabe verbucht.")
        self.refresh_view(origin="local-write")

    def scan_identifier(self) -> None:
        if not self.scanner_available:
            QMessageBox.warning(self, "Code suchen", "Scanner-Funktion ist nicht verfuegbar. Bitte pillow und zxing-cpp installieren.")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Barcode oder QR-Code auswaehlen",
            "",
            "Bilddateien (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Alle Dateien (*.*)",
        )
        if not file_path:
            return
        try:
            identifier = decode_identifier_from_file(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Code suchen", str(exc))
            return
        self.search_edit.setText(identifier)
        asset = self.repository.get_asset(asset_tag=identifier)
        if asset:
            self.selected_asset_id = asset["id"]
            self.apply_filter(keep_selection=True)
            self.status_label.setText(f"Code gefunden: {identifier}")
        else:
            create = QMessageBox.question(self, "Code suchen", f"Kein Asset fuer {identifier} gefunden. Neues Asset anlegen?")
            if create == QMessageBox.Yes:
                dialog = AssetDialog(self, "Asset anlegen", scanned_identifier=identifier)
                if dialog.exec() == QDialog.Accepted:
                    try:
                        self.repository.create_asset(**dialog.values())
                    except Exception as exc:
                        QMessageBox.critical(self, "Asset anlegen", str(exc))
                        return
                    self.refresh_view(origin="local-write")

    def export_current_view_to_csv(self) -> None:
        if not self.filtered_asset_rows:
            QMessageBox.information(self, "CSV exportieren", "Die aktuelle Ansicht enthaelt keine Assets.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "CSV exportieren",
            build_export_filename("csv"),
            "CSV-Dateien (*.csv);;Alle Dateien (*.*)",
        )
        if not file_path:
            return
        try:
            export_asset_snapshots_to_csv(self.filtered_asset_rows, file_path)
        except Exception as exc:
            QMessageBox.critical(self, "CSV exportieren", str(exc))
            return
        self.status_label.setText(f"CSV exportiert: {Path(file_path).name}")

    def export_current_view_to_html(self) -> None:
        if not self.filtered_asset_rows:
            QMessageBox.information(self, "Druckansicht", "Die aktuelle Ansicht enthaelt keine Assets.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Druckansicht speichern",
            build_export_filename("html", prefix="DeviceManagementV2_Inventarliste"),
            "HTML-Dateien (*.html);;Alle Dateien (*.*)",
        )
        if not file_path:
            return
        try:
            export_asset_snapshots_to_html(self.filtered_asset_rows, file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Druckansicht", str(exc))
            return
        self.status_label.setText(f"Druckansicht gespeichert: {Path(file_path).name}")


def run():
    app = QApplication.instance() or QApplication([])
    window = DeviceManagementV2Window()
    window.show()
    return app.exec()
