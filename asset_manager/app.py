import getpass
import sqlite3
import sys
from ctypes import windll
from pathlib import Path
from tkinter import PhotoImage, filedialog, messagebox

import customtkinter as ctk

from .config import load_config, resolve_database_path
from .constants import (
    CARD_BG,
    CARD_BORDER,
    CUSTOM_BG_COLOR,
    DELETE_BG,
    DELETE_HOVER,
    DELETE_TEXT,
    DEVICE_TYPES,
    EMPTY_STATE_BG,
    INACTIVE_BG,
    INACTIVE_TEXT,
    NEUTRAL_BG,
    NEUTRAL_HOVER,
    PANEL_BG,
    PRIMARY_ACCENT,
    PRIMARY_BLUE,
    PRIMARY_BLUE_DARK,
    RESTORE_BG,
    RESTORE_HOVER,
    SEARCH_BG,
    SEARCH_BORDER,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    SUCCESS_BG,
    SUCCESS_TEXT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_WHITE,
    WARNING_BG,
    WARNING_HOVER,
)
from .db import DatabaseManager
from .services import (
    build_backup_filename,
    build_duplicate_report,
    build_export_filename,
    build_import_filename,
    build_import_preview,
    build_print_filename,
    create_backup,
    export_assets_to_csv,
    export_assets_to_printable_html,
    import_assets_from_workbook,
    restore_backup,
    write_import_protocol,
)


class DeviceManagementApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.db = DatabaseManager()
        self.selected_asset_tag = None
        self.selected_asset_type = None
        self.summary_cards = {}
        self.icon_path = self._resource_path("assets/app_icon.ico")
        self.icon_png_path = self._resource_path("assets/app_icon.png")
        self._window_icon_image = None
        self.last_seen_update = None
        self.last_sync_text = ctk.StringVar(value="Letzte Aktualisierung: noch nicht synchronisiert")
        self.actor = f"{getpass.getuser()}@{Path.home().name}"
        self.auto_refresh_ms = max(int(self.config_data.get("auto_refresh_seconds", 15)), 5) * 1000
        self.global_search_var = ctk.StringVar()
        self.global_search_var.trace_add("write", lambda *_args: self.refresh_data())

        self.title("Device Management")
        self.geometry("1460x920")
        self.minsize(1260, 820)
        self.configure(fg_color=CUSTOM_BG_COLOR)
        self._apply_window_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=22)
        shell.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)
        shell.grid_rowconfigure(3, weight=0)

        self._build_topbar(shell)
        self._build_summary(shell)
        self._build_workspace(shell)
        self._build_statusbar(shell)

        self.refresh_data()
        self.after(self.auto_refresh_ms, self.auto_refresh_loop)

    def _resource_path(self, filename):
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        else:
            base_path = Path(__file__).resolve().parent.parent
        return base_path / filename

    def _apply_window_icon(self):
        try:
            windll.shell32.SetCurrentProcessExplicitAppUserModelID("device.management")
        except Exception:
            pass
        if self.icon_path and self.icon_path.exists():
            try:
                self.iconbitmap(default=str(self.icon_path))
            except Exception:
                pass
        if self.icon_png_path and self.icon_png_path.exists():
            try:
                self._window_icon_image = PhotoImage(file=str(self.icon_png_path))
                self.iconphoto(True, self._window_icon_image)
            except Exception:
                pass

    def _build_topbar(self, parent):
        topbar = ctk.CTkFrame(parent, fg_color="transparent")
        topbar.grid(row=0, column=0, padx=22, pady=(22, 14), sticky="ew")
        for column in range(7):
            topbar.grid_columnconfigure(column, weight=0)
        topbar.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(topbar, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Device Management",
            font=("Arial", 30, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")
        search_entry = ctk.CTkEntry(
            topbar,
            placeholder_text="Globale Suche über alle Geräte...",
            textvariable=self.global_search_var,
            width=290,
            height=42,
            corner_radius=18,
            fg_color=SEARCH_BG,
            border_color=SEARCH_BORDER,
            text_color=TEXT_WHITE,
        )
        search_entry.grid(row=0, column=1, padx=(12, 0), sticky="e")

        ctk.CTkButton(
            topbar,
            text="Import-Vorschau",
            fg_color=PRIMARY_ACCENT,
            hover_color="#d6e2ee",
            text_color=TEXT_PRIMARY,
            width=145,
            height=42,
            font=("Arial", 13, "bold"),
            command=self.preview_import_from_excel,
        ).grid(row=0, column=2, padx=(12, 0))

        ctk.CTkButton(
            topbar,
            text="Export",
            fg_color=PRIMARY_BLUE,
            hover_color=PRIMARY_BLUE_DARK,
            width=100,
            height=42,
            font=("Arial", 13, "bold"),
            command=self.export_current_view,
        ).grid(row=0, column=3, padx=(12, 0))

        ctk.CTkButton(
            topbar,
            text="Backup",
            fg_color=NEUTRAL_BG,
            hover_color=NEUTRAL_HOVER,
            text_color=TEXT_PRIMARY,
            width=95,
            height=42,
            font=("Arial", 13, "bold"),
            command=self.backup_database,
        ).grid(row=0, column=4, padx=(12, 0))

        ctk.CTkButton(
            topbar,
            text="Restore",
            fg_color=RESTORE_BG,
            hover_color=RESTORE_HOVER,
            text_color=DELETE_TEXT,
            width=95,
            height=42,
            font=("Arial", 13, "bold"),
            command=self.restore_database,
        ).grid(row=0, column=5, padx=(12, 0))

        theme_switch = ctk.CTkSegmentedButton(
            topbar,
            values=["Light", "Dark"],
            command=self.change_theme,
            width=140,
        )
        theme_switch.grid(row=0, column=6, padx=(12, 0))
        theme_switch.set("Light")

    def _build_summary(self, parent):
        summary = ctk.CTkFrame(parent, fg_color="transparent")
        summary.grid(row=1, column=0, padx=22, pady=(0, 12), sticky="ew")
        for index in range(4):
            summary.grid_columnconfigure(index, weight=1)
        self.summary_cards["total"] = self._create_summary_card(summary, 0, "Assets gesamt", "0", PRIMARY_ACCENT)
        self.summary_cards["active"] = self._create_summary_card(summary, 1, "Aktiv", "0", SUCCESS_BG)
        self.summary_cards["inactive"] = self._create_summary_card(summary, 2, "Inaktiv", "0", INACTIVE_BG)
        self.summary_cards["incomplete"] = self._create_summary_card(summary, 3, "Ohne Hostname", "0", WARNING_BG)

    def _create_summary_card(self, parent, column, title, value, accent_color):
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card.grid(row=0, column=column, padx=(0 if column == 0 else 8, 0), sticky="ew")
        stripe = ctk.CTkFrame(card, fg_color=accent_color, height=8, corner_radius=10)
        stripe.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(card, text=title, font=("Arial", 13), text_color=TEXT_MUTED).pack(anchor="w", padx=16)
        value_label = ctk.CTkLabel(card, text=value, font=("Arial", 28, "bold"), text_color=TEXT_PRIMARY)
        value_label.pack(anchor="w", padx=16, pady=(2, 14))
        return value_label

    def _build_workspace(self, parent):
        workspace = ctk.CTkFrame(parent, fg_color="transparent")
        workspace.grid(row=2, column=0, padx=22, pady=(0, 12), sticky="nsew")
        workspace.grid_columnconfigure(0, weight=3)
        workspace.grid_columnconfigure(1, weight=2)
        workspace.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            workspace,
            segmented_button_selected_color=PRIMARY_BLUE,
            segmented_button_selected_hover_color=PRIMARY_BLUE_DARK,
            segmented_button_unselected_color="#cad4df",
            segmented_button_unselected_hover_color="#bac6d3",
            text_color=TEXT_PRIMARY,
            fg_color="transparent",
        )
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        self.tabs = {}
        for device_type in DEVICE_TYPES:
            tab_obj = self.tabview.add(device_type)
            self.tabs[device_type] = self._setup_tab(tab_obj, device_type)

        self.detail_panel = ctk.CTkFrame(workspace, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        self.detail_panel.grid(row=0, column=1, sticky="nsew")
        self.detail_panel.grid_rowconfigure(2, weight=1)
        self.detail_panel.grid_rowconfigure(4, weight=1)
        self._build_detail_panel()

    def _setup_tab(self, tab, device_type):
        container = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=20)
        container.pack(fill="both", expand=True)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 12))
        header.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text=device_type, font=("Arial", 22, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(left, text=self._build_type_hint(device_type), font=("Arial", 12), text_color=TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.pack(anchor="w", pady=(12, 0))
        self._create_action_button(actions, "Onboarding", PRIMARY_BLUE, lambda: self.action_popup("Onboarding", device_type))
        self._create_action_button(actions, "Change", PRIMARY_ACCENT, lambda: self.action_popup("Change", device_type), text_color=TEXT_PRIMARY)
        self._create_action_button(actions, "Offboarding", "#f3d7d8", lambda: self.action_offboarding(device_type), text_color="#7b1d20")
        self._create_action_button(actions, "Löschen", DELETE_BG, lambda: self.action_delete(device_type), text_color=DELETE_TEXT)

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        status_var = ctk.StringVar(value="Alle")
        sort_var = ctk.StringVar(value="Zuletzt geändert")
        model_var = ctk.StringVar(value="Alle Modelle")
        incomplete_var = ctk.BooleanVar(value=False)

        ctk.CTkLabel(right, text="Status", text_color=TEXT_MUTED, font=("Arial", 11)).grid(row=0, column=0, sticky="w")
        status_menu = ctk.CTkOptionMenu(
            right,
            values=["Alle", STATUS_ACTIVE, STATUS_INACTIVE],
            variable=status_var,
            width=120,
            command=lambda _choice, current_type=device_type: self.refresh_data(current_type),
        )
        status_menu.grid(row=1, column=0, padx=(0, 8))

        ctk.CTkLabel(right, text="Sortierung", text_color=TEXT_MUTED, font=("Arial", 11)).grid(row=0, column=1, sticky="w")
        sort_menu = ctk.CTkOptionMenu(
            right,
            values=["Status", "User", "Modell", "Asset-Tag", "Zuletzt geändert"],
            variable=sort_var,
            width=150,
            command=lambda _choice, current_type=device_type: self.refresh_data(current_type),
        )
        sort_menu.grid(row=1, column=1, padx=(0, 8))

        ctk.CTkLabel(right, text="Modell", text_color=TEXT_MUTED, font=("Arial", 11)).grid(row=0, column=2, sticky="w")
        model_menu = ctk.CTkOptionMenu(
            right,
            values=["Alle Modelle"],
            variable=model_var,
            width=160,
            command=lambda _choice, current_type=device_type: self.refresh_data(current_type),
        )
        model_menu.grid(row=1, column=2, padx=(0, 8))

        incomplete_check = ctk.CTkCheckBox(
            right,
            text="Nur unvollständig",
            variable=incomplete_var,
            command=lambda current_type=device_type: self.refresh_data(current_type),
        )
        incomplete_check.grid(row=1, column=3, sticky="e")
        if device_type != "Notebook":
            incomplete_check.configure(state="disabled")

        info_bar = ctk.CTkFrame(container, fg_color=EMPTY_STATE_BG, corner_radius=14)
        info_bar.pack(fill="x", padx=18, pady=(0, 10))
        info_label = ctk.CTkLabel(info_bar, text="0 Einträge", font=("Arial", 12, "bold"), text_color=TEXT_MUTED)
        info_label.pack(anchor="w", padx=14, pady=10)

        scroll = ctk.CTkScrollableFrame(container, fg_color=PANEL_BG, corner_radius=18)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        return {
            "scroll_frame": scroll,
            "count_label": info_label,
            "status_var": status_var,
            "sort_var": sort_var,
            "model_var": model_var,
            "model_menu": model_menu,
            "incomplete_var": incomplete_var,
        }

    def _build_detail_panel(self):
        ctk.CTkLabel(self.detail_panel, text="Detailansicht", font=("Arial", 24, "bold"), text_color=TEXT_PRIMARY).grid(
            row=0, column=0, sticky="w", padx=20, pady=(20, 8)
        )
        self.detail_text = ctk.CTkTextbox(self.detail_panel, corner_radius=16, fg_color=PANEL_BG, text_color=TEXT_PRIMARY)
        self.detail_text.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))

        history_header = ctk.CTkFrame(self.detail_panel, fg_color="transparent")
        history_header.grid(row=2, column=0, sticky="ew", padx=20)
        ctk.CTkLabel(history_header, text="Änderungshistorie", font=("Arial", 18, "bold"), text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(
            history_header,
            text="Duplikat-Check",
            width=120,
            fg_color=NEUTRAL_BG,
            hover_color=NEUTRAL_HOVER,
            text_color=TEXT_PRIMARY,
            command=self.show_duplicate_report,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            history_header,
            text="Hinweise",
            width=95,
            fg_color=WARNING_BG,
            hover_color=WARNING_HOVER,
            text_color=TEXT_PRIMARY,
            command=self.show_incomplete_report,
        ).pack(side="right")

        self.history_text = ctk.CTkTextbox(self.detail_panel, corner_radius=16, fg_color=PANEL_BG, text_color=TEXT_PRIMARY)
        self.history_text.grid(row=3, column=0, sticky="nsew", padx=20, pady=(8, 12))

    def _build_statusbar(self, parent):
        statusbar = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=CARD_BORDER)
        statusbar.grid(row=3, column=0, padx=22, pady=(0, 22), sticky="ew")
        statusbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(statusbar, textvariable=self.last_sync_text, text_color=TEXT_MUTED, font=("Arial", 11)).grid(
            row=0, column=0, sticky="w", padx=14, pady=10
        )
        self.status_right_text = ctk.CTkLabel(statusbar, text="Bereit", text_color=TEXT_MUTED, font=("Arial", 11))
        self.status_right_text.grid(row=0, column=1, sticky="e", padx=14, pady=10)

    def _create_action_button(self, parent, text, fg_color, command, text_color=TEXT_WHITE):
        ctk.CTkButton(
            parent,
            text=text,
            fg_color=fg_color,
            hover_color=PRIMARY_BLUE_DARK if fg_color == PRIMARY_BLUE else "#d6e2ee",
            text_color=text_color,
            font=("Arial", 13, "bold"),
            width=120,
            height=38,
            corner_radius=16,
            command=command,
        ).pack(side="left", padx=(0, 8))

    def _build_type_hint(self, device_type):
        return "Verwalte Smartphones ohne Rufnummernpflege." if device_type == "Smartphone" else "Verwalte Geräte und Hostnamen."

    def _sort_key_for_label(self, label):
        mapping = {
            "Status": "status",
            "User": "user_name",
            "Modell": "model",
            "Asset-Tag": "asset_tag",
            "Zuletzt geändert": "updated_at",
        }
        return mapping.get(label, "status")

    def current_view_rows(self, device_type=None):
        device_type = device_type or self.tabview.get()
        tab_state = self.tabs[device_type]
        status_filter = tab_state["status_var"].get()
        model_filter = tab_state["model_var"].get()
        return self.db.fetch_assets(
            device_type=device_type,
            query=self.global_search_var.get().strip(),
            status_filter=None if status_filter == "Alle" else status_filter,
            sort_by=self._sort_key_for_label(tab_state["sort_var"].get()),
            model_filter=None if model_filter == "Alle Modelle" else model_filter,
            incomplete_only=bool(tab_state["incomplete_var"].get()),
        )

    def all_rows(self):
        return self.db.fetch_assets(
            device_type=None,
            query=self.global_search_var.get().strip(),
            sort_by="updated_at",
        )

    def change_theme(self, theme_name):
        ctk.set_appearance_mode(theme_name)

    def export_current_view(self):
        rows = self.current_view_rows()
        if not rows:
            messagebox.showwarning("Export", "Keine Daten zum Exportieren vorhanden.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=build_export_filename(),
            filetypes=[("CSV Datei", "*.csv")],
            title="Aktuelle Ansicht exportieren",
        )
        if not file_path:
            return
        export_assets_to_csv(rows, file_path)
        self.status_right_text.configure(text=f"Exportiert: {Path(file_path).name}")

    def print_inventory(self):
        rows = self.current_view_rows()
        if not rows:
            messagebox.showwarning("Druckansicht", "Keine Daten für die Inventarliste vorhanden.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".html",
            initialfile=build_print_filename(),
            filetypes=[("HTML Datei", "*.html")],
            title="Druckansicht speichern",
        )
        if not file_path:
            return
        export_assets_to_printable_html(rows, file_path)
        self.status_right_text.configure(text=f"Druckansicht erstellt: {Path(file_path).name}")

    def preview_import_from_excel(self):
        file_path = filedialog.askopenfilename(
            title="Excel-Datei auswählen",
            filetypes=[("Excel Datei", "*.xlsx"), ("Alle Dateien", "*.*")],
        )
        if not file_path:
            return
        default_type = self.tabview.get() if self.tabview.get() in DEVICE_TYPES else None
        try:
            preview = build_import_preview(file_path, default_type=default_type)
        except ValueError as exc:
            messagebox.showwarning("Import nicht möglich", str(exc))
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Import-Vorschau")
        modal.geometry("760x620")
        modal.configure(fg_color=PANEL_BG)
        modal.grab_set()

        container = ctk.CTkFrame(modal, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        container.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(container, text=f"Import-Vorschau: {build_import_filename(file_path)}", font=("Arial", 22, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(20, 10))

        summary = ctk.CTkTextbox(container, height=180, fg_color=PANEL_BG, text_color=TEXT_PRIMARY, corner_radius=14)
        summary.pack(fill="x", padx=20, pady=(0, 10))
        summary.insert(
            "1.0",
            "\n".join(
                [
                    f"Gültige Zeilen: {preview['counts']['total_valid']}",
                    f"Fehlerhafte Zeilen: {preview['counts']['total_errors']}",
                    f"Smartphones: {preview['counts']['by_type']['Smartphone']}",
                    f"Notebooks: {preview['counts']['by_type']['Notebook']}",
                    "",
                    "Erste gültige Zeilen:",
                ]
                + [f"{row['type']} | {row['user_name']} | {row['model']} | {row['asset_tag']}" for row in preview["rows"]]
                + (["", "Erste Hinweise:"] + preview["errors"] if preview["errors"] else [])
            ),
        )
        summary.configure(state="disabled")

        button_row = ctk.CTkFrame(container, fg_color="transparent")
        button_row.pack(fill="x", padx=20, pady=(0, 20))

        def run_import():
            summary_data = import_assets_from_workbook(file_path, self.db, default_type=default_type, actor=self.actor)
            protocol_path = write_import_protocol(file_path, summary_data, default_type=default_type)
            self.refresh_data()
            self.status_right_text.configure(text=f"Import abgeschlossen: {Path(protocol_path).name}")
            modal.destroy()
            messagebox.showinfo(
                "Import abgeschlossen",
                "\n".join(
                    [
                        f"Datei: {build_import_filename(file_path)}",
                        f"Neu angelegt: {summary_data['created']}",
                        f"Aktualisiert: {summary_data['updated']}",
                        f"Übersprungen: {summary_data['skipped']}",
                        f"Protokoll: {protocol_path}",
                    ]
                ),
            )

        ctk.CTkButton(
            button_row,
            text="Abbrechen",
            fg_color=NEUTRAL_BG,
            hover_color=NEUTRAL_HOVER,
            text_color=TEXT_PRIMARY,
            width=140,
            command=modal.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            button_row,
            text="Import ausführen",
            fg_color=PRIMARY_BLUE,
            hover_color=PRIMARY_BLUE_DARK,
            width=160,
            command=run_import,
        ).pack(side="right")

    def backup_database(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            initialfile=build_backup_filename(),
            filetypes=[("SQLite Backup", "*.db")],
            title="Backup speichern",
        )
        if not file_path:
            return
        backup_path = create_backup(self.db.db_path, file_path)
        self.status_right_text.configure(text=f"Backup erstellt: {backup_path.name}")
        messagebox.showinfo("Backup", f"Backup gespeichert unter:\n{backup_path}")

    def restore_database(self):
        file_path = filedialog.askopenfilename(
            title="Backup-Datei auswählen",
            filetypes=[("SQLite Backup", "*.db"), ("Alle Dateien", "*.*")],
        )
        if not file_path:
            return
        if not messagebox.askyesno("Restore", "Aktuelle Datenbank wirklich durch das Backup ersetzen?"):
            return
        restore_backup(file_path, self.db.db_path)
        self.refresh_data()
        self.status_right_text.configure(text=f"Restore durchgeführt: {Path(file_path).name}")

    def show_duplicate_report(self):
        issues = build_duplicate_report(self.all_rows())
        self._show_text_modal(
            "Duplikat- und Qualitätsbericht",
            issues if issues else ["Keine Dubletten oder Qualitätsprobleme gefunden."],
        )

    def show_incomplete_report(self):
        rows = self.db.fetch_assets(device_type="Notebook", incomplete_only=True, sort_by="user_name")
        lines = [f"{row['asset_tag']} | {row['user_name']} | {row['model']}" for row in rows]
        self._show_text_modal(
            "Hinweise zu unvollständigen Einträgen",
            lines if lines else ["Alle Notebooks haben aktuell einen Hostname."],
        )

    def _show_text_modal(self, title, lines):
        modal = ctk.CTkToplevel(self)
        modal.title(title)
        modal.geometry("720x520")
        modal.configure(fg_color=PANEL_BG)
        modal.grab_set()
        box = ctk.CTkTextbox(modal, fg_color=CARD_BG, text_color=TEXT_PRIMARY, corner_radius=16)
        box.pack(fill="both", expand=True, padx=18, pady=18)
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")

    def create_card(self, parent, row, device_type):
        tag = row["asset_tag"]
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        card.pack(fill="x", padx=4, pady=6)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=16)
        content.grid_columnconfigure(1, weight=1)

        status_pill = self._create_status_pill(content, row["status"])
        status_pill.grid(row=0, column=2, rowspan=2, sticky="e")

        icon_frame = ctk.CTkFrame(content, fg_color=PRIMARY_ACCENT, width=54, height=54, corner_radius=18)
        icon_frame.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        icon_frame.grid_propagate(False)
        ctk.CTkLabel(icon_frame, text="SP" if device_type == "Smartphone" else "NB", font=("Arial", 15, "bold"), text_color=PRIMARY_BLUE).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(content, text=row["user_name"], font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(content, text=row["model"], font=("Arial", 13), text_color=TEXT_MUTED).grid(row=1, column=1, sticky="w", pady=(4, 0))

        meta_text = f"S/N / IMEI: {row['asset_tag']}"
        if row["extra_info"] and device_type == "Notebook":
            meta_text += f"    Hostname: {row['extra_info']}"
        meta_text += f"    Zuletzt: {row['updated_at']}"
        ctk.CTkLabel(card, text=meta_text, font=("Arial", 12), text_color=TEXT_MUTED).pack(anchor="w", padx=18, pady=(0, 14))

        for widget in (card, content, status_pill, icon_frame):
            widget.bind("<Button-1>", lambda _event, c=card, a=tag, t=device_type: self.select_card(c, a, t))

    def _create_status_pill(self, parent, status):
        fg_color = SUCCESS_BG if status == STATUS_ACTIVE else INACTIVE_BG
        text_color = SUCCESS_TEXT if status == STATUS_ACTIVE else INACTIVE_TEXT
        return ctk.CTkLabel(
            parent,
            text=status.upper(),
            fg_color=fg_color,
            text_color=text_color,
            font=("Arial", 11, "bold"),
            corner_radius=999,
            padx=14,
            pady=6,
        )

    def _update_summary(self):
        counts = self.db.fetch_counts_by_type()
        active = sum(item[STATUS_ACTIVE] for item in counts.values())
        inactive = sum(item[STATUS_INACTIVE] for item in counts.values())
        total = active + inactive
        incomplete = len(self.db.fetch_assets(device_type="Notebook", incomplete_only=True))
        self.summary_cards["total"].configure(text=str(total))
        self.summary_cards["active"].configure(text=str(active))
        self.summary_cards["inactive"].configure(text=str(inactive))
        self.summary_cards["incomplete"].configure(text=str(incomplete))

    def _update_model_filters(self):
        for device_type, tab_state in self.tabs.items():
            models = ["Alle Modelle"] + self.db.fetch_distinct_models(device_type)
            tab_state["model_menu"].configure(values=models)
            if tab_state["model_var"].get() not in models:
                tab_state["model_var"].set("Alle Modelle")

    def _update_detail_panel(self):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", "end")

        if not self.selected_asset_tag:
            self.detail_text.insert("1.0", "Kein Gerät ausgewählt.\n\nWähle links eine Karte aus, um Details und Historie zu sehen.")
            self.history_text.insert("1.0", "Noch keine Historie sichtbar.")
        else:
            asset = self.db.fetch_asset_by_tag(self.selected_asset_tag)
            history = self.db.fetch_history(self.selected_asset_tag, limit=50)
            if asset:
                lines = [
                    f"Typ: {asset['type']}",
                    f"User: {asset['user_name']}",
                    f"Modell: {asset['model']}",
                    f"S/N / IMEI: {asset['asset_tag']}",
                    f"Hostname: {asset['extra_info'] or '-'}",
                    f"Status: {asset['status']}",
                    f"Zuletzt geändert: {asset['updated_at']}",
                    f"Geändert von: {asset['updated_by'] or '-'}",
                ]
                self.detail_text.insert("1.0", "\n".join(lines))
            if history:
                history_lines = [
                    f"{row['created_at']} | {row['action']} | {row['actor'] or '-'} | {row['payload']}"
                    for row in history
                ]
                self.history_text.insert("1.0", "\n".join(history_lines))
            else:
                self.history_text.insert("1.0", "Keine Historie vorhanden.")

        self.detail_text.configure(state="disabled")
        self.history_text.configure(state="disabled")

    def select_card(self, card_widget, tag, device_type):
        for tab_data in self.tabs.values():
            for child in tab_data["scroll_frame"].winfo_children():
                child.configure(border_color=CARD_BORDER, border_width=1)
        card_widget.configure(border_color=PRIMARY_BLUE, border_width=2)
        self.selected_asset_tag = tag
        self.selected_asset_type = device_type
        self._update_detail_panel()

    def _render_empty_state(self, parent, device_type, query):
        empty = ctk.CTkFrame(parent, fg_color=EMPTY_STATE_BG, corner_radius=18)
        empty.pack(fill="x", padx=4, pady=8)
        message = f"Keine Treffer für '{query}'." if query else f"Noch keine {device_type}-Einträge vorhanden."
        ctk.CTkLabel(empty, text="Leerer Bereich", font=("Arial", 18, "bold"), text_color=TEXT_PRIMARY).pack(pady=(26, 4))
        ctk.CTkLabel(empty, text=message, font=("Arial", 12), text_color=TEXT_MUTED).pack(pady=(0, 26))

    def refresh_data(self, specific_type=None):
        types = [specific_type] if specific_type else DEVICE_TYPES
        try:
            self._update_model_filters()
            for device_type in types:
                scroll = self.tabs[device_type]["scroll_frame"]
                for child in scroll.winfo_children():
                    child.destroy()

                results = self.current_view_rows(device_type)
                self.tabs[device_type]["count_label"].configure(text=f"{len(results)} Einträge")
                if not results:
                    self._render_empty_state(scroll, device_type, self.global_search_var.get().strip())
                    continue
                for row in results:
                    self.create_card(scroll, row, device_type)

            self.last_seen_update = self.db.fetch_last_updated_at()
            self.last_sync_text.set(f"Letzte Aktualisierung: {datetime_now_string()}")
            self._update_summary()
            self._update_detail_panel()
        except sqlite3.Error as exc:
            messagebox.showerror("Datenbankfehler", str(exc))

    def auto_refresh_loop(self):
        try:
            latest_update = self.db.fetch_last_updated_at()
            if latest_update != self.last_seen_update:
                self.refresh_data()
        except sqlite3.Error:
            pass
        finally:
            self.after(self.auto_refresh_ms, self.auto_refresh_loop)

    def get_selected_asset(self):
        if not self.selected_asset_tag:
            return None
        return self.db.fetch_asset_by_tag(self.selected_asset_tag)

    def validate_asset_input(self, user_name, model, asset_tag):
        missing_fields = []
        if not user_name.strip():
            missing_fields.append("User Name")
        if not model.strip():
            missing_fields.append("Geräte Modell")
        if not asset_tag.strip():
            missing_fields.append("S/N / IMEI")
        if missing_fields:
            raise ValueError(f"Bitte folgende Felder ausfüllen: {', '.join(missing_fields)}")

    def action_popup(self, action, device_type):
        selected_asset = None
        if action == "Change":
            selected_asset = self.get_selected_asset()
            if not selected_asset:
                messagebox.showwarning("Device Management", "Bitte erst ein Gerät auswählen.")
                return

        modal = ctk.CTkToplevel(self)
        modal.title(f"Device Management - {action}")
        modal.geometry("500x580")
        modal.configure(fg_color=PANEL_BG)
        modal.attributes("-topmost", True)
        modal.grab_set()

        container = ctk.CTkFrame(modal, fg_color=CARD_BG, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(container, text=f"{action} Workflow", font=("Arial", 24, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(24, 6))
        ctk.CTkLabel(container, text=f"{device_type} erfassen oder aktualisieren.", font=("Arial", 12), text_color=TEXT_MUTED).pack(anchor="w", padx=24, pady=(0, 18))

        form = ctk.CTkFrame(container, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24)
        ent_user = self.create_input(form, "User Name")
        ent_model = self.create_input(form, "Geräte Modell")
        ent_tag = self.create_input(form, "S/N / IMEI")
        ent_extra = self.create_input(form, "Hostname") if device_type == "Notebook" else None

        if selected_asset:
            ent_user.insert(0, selected_asset["user_name"])
            ent_model.insert(0, selected_asset["model"])
            ent_tag.insert(0, selected_asset["asset_tag"])
            if ent_extra is not None:
                ent_extra.insert(0, selected_asset["extra_info"] or "")

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(8, 24))
        buttons.grid_columnconfigure((0, 1), weight=1)

        def save():
            user_name = ent_user.get().strip()
            model = ent_model.get().strip()
            asset_tag = ent_tag.get().strip()
            extra_info = ent_extra.get().strip() if ent_extra is not None else ""
            try:
                self.validate_asset_input(user_name, model, asset_tag)
                if action == "Onboarding":
                    self.db.create_asset(device_type, user_name, model, asset_tag, extra_info, actor=self.actor)
                else:
                    self.db.update_asset(
                        selected_asset["asset_tag"],
                        device_type,
                        user_name,
                        model,
                        asset_tag,
                        extra_info,
                        actor=self.actor,
                    )
                    self.selected_asset_tag = asset_tag
                self.refresh_data(device_type)
                modal.destroy()
            except ValueError as exc:
                messagebox.showwarning("Device Management", str(exc))
            except sqlite3.IntegrityError as exc:
                messagebox.showwarning("Device Management", self.build_integrity_message(asset_tag, extra_info, exc))
            except sqlite3.Error as exc:
                messagebox.showerror("Datenbankfehler", str(exc))

        ctk.CTkButton(buttons, text="Abbrechen", fg_color=NEUTRAL_BG, hover_color=NEUTRAL_HOVER, text_color=TEXT_PRIMARY, height=42, corner_radius=16, command=modal.destroy).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(buttons, text="Speichern", fg_color=PRIMARY_BLUE, hover_color=PRIMARY_BLUE_DARK, height=42, corner_radius=16, command=save).grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def create_input(self, master, label):
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(wrapper, text=label, font=("Arial", 12, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w")
        entry = ctk.CTkEntry(wrapper, height=42, corner_radius=14, fg_color=CARD_BG, border_color=CARD_BORDER, text_color=TEXT_PRIMARY)
        entry.pack(fill="x", pady=(6, 0))
        return entry

    def action_offboarding(self, device_type):
        asset = self.get_selected_asset()
        if not asset:
            messagebox.showwarning("Device Management", "Bitte erst ein Gerät auswählen.")
            return
        if messagebox.askyesno("Abmeldung", f"Gerät {asset['asset_tag']} deaktivieren?"):
            try:
                self.db.deactivate_asset(asset["asset_tag"], actor=self.actor)
                self.refresh_data(device_type)
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Device Management", str(exc))

    def action_delete(self, device_type):
        asset = self.get_selected_asset()
        if not asset:
            messagebox.showwarning("Device Management", "Bitte erst ein Gerät auswählen.")
            return
        if messagebox.askyesno("Löschen", f"Gerät {asset['asset_tag']} wirklich dauerhaft löschen?\nDiese Aktion kann nicht rückgängig gemacht werden."):
            try:
                self.db.delete_asset(asset["asset_tag"], actor=self.actor)
                self.selected_asset_tag = None
                self.refresh_data(device_type)
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Device Management", str(exc))

    def build_integrity_message(self, asset_tag, extra_info, error):
        error_message = str(error).lower()
        if "idx_assets_type_extra_info_normalized" in error_message:
            return f"Der Hostname '{extra_info}' ist bereits für ein anderes Notebook vergeben."
        return f"Ein Gerät mit dem Asset-Tag '{asset_tag}' existiert bereits."


def datetime_now_string():
    from datetime import datetime

    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")
