from datetime import datetime
import getpass
from pathlib import Path
import socket
from tkinter import PhotoImage, filedialog, messagebox
import uuid

import customtkinter as ctk

from ..config import load_config, resolve_database_path
from ..constants import (
    APP_HEIGHT,
    APP_MIN_HEIGHT,
    APP_MIN_WIDTH,
    APP_WIDTH,
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_CARD,
    COLOR_DANGER,
    COLOR_DANGER_TEXT,
    COLOR_MUTED,
    COLOR_PANEL,
    COLOR_PRIMARY,
    COLOR_PRIMARY_DARK,
    COLOR_SUCCESS,
    COLOR_SUCCESS_TEXT,
    COLOR_TEXT,
    COLOR_WARNING,
    COLOR_WARNING_TEXT,
)
from ..db.repository import ConflictError, DatabaseRepository, EditClaimError
from ..services.scanner import SUPPORTED_IMAGE_TYPES, decode_identifier_from_file, scanner_runtime_available
from .theme import apply_theme


class DeviceManagementV2App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        apply_theme(self.config_data["theme"])
        self.db_path = resolve_database_path(self.config_data)
        self.repository = DatabaseRepository(self.db_path)
        self._icon_image = None
        self.selected_asset_id = None
        self.scanner_available = scanner_runtime_available()
        self.editor_label = f"{getpass.getuser()} @ {socket.gethostname()}"
        self.editor_id = f"{self.editor_label} :: {uuid.uuid4().hex[:8]}"
        self.edit_claim_ttl_seconds = 120
        self.auto_refresh_ms = max(int(self.config_data.get("auto_refresh_seconds", 15)), 5) * 1000
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self.refresh_view(origin="search"))
        self.status_var = ctk.StringVar(value="Bereit")
        self.last_sync_var = ctk.StringVar(value="Noch nicht synchronisiert")
        self.change_var = ctk.StringVar(value="Noch keine Aenderungen erkannt")
        self.detail_notice_var = ctk.StringVar(value="Auswahl ist synchron.")
        self.previous_snapshot_map = {}
        self.recent_change_asset_ids = set()
        self.selected_asset_baseline = None
        self.asset_claim_map = {}

        self.title(self.config_data["app_name"])
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)
        self.configure(fg_color=COLOR_BG)
        self._apply_window_icon()

        self.shell = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=24)
        self.shell.pack(fill="both", expand=True, padx=18, pady=18)
        self.shell.grid_columnconfigure(0, weight=1)
        self.shell.grid_rowconfigure(2, weight=1)

        self._build_header(self.shell)
        self._build_summary(self.shell)
        self._build_body(self.shell)
        self._build_statusbar(self.shell)
        self.refresh_view()
        self.after(self.auto_refresh_ms, self.auto_refresh_loop)

    def _resource_path(self, filename):
        local_root = Path(__file__).resolve().parents[2]
        project_root = local_root.parent
        for candidate in (local_root / filename, project_root / filename):
            if candidate.exists():
                return candidate
        return local_root / filename

    def _apply_window_icon(self):
        icon_path = self._resource_path("BRNL.ico")
        png_path = self._resource_path("BRNL.png")
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except Exception:
                pass
        if png_path.exists():
            try:
                self._icon_image = PhotoImage(file=str(png_path))
                self.iconphoto(True, self._icon_image)
            except Exception:
                pass

    def _build_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, padx=24, pady=(24, 14), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Device Management v2",
            font=("Arial", 30, "bold"),
            text_color=COLOR_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block,
            text="Erste v2-Oberflaeche mit Asset-Uebersicht, Zuweisungen und Audit-Timeline.",
            font=("Arial", 14),
            text_color=COLOR_MUTED,
        ).pack(anchor="w", pady=(6, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            actions,
            text="Aktualisieren",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=120,
            command=lambda: self.refresh_view(origin="manual"),
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Light",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=90,
            command=lambda: self.change_theme("Light"),
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            actions,
            text="Dark",
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_DARK,
            width=90,
            command=lambda: self.change_theme("Dark"),
        ).pack(side="left", padx=(8, 0))

        meta_row = ctk.CTkFrame(header, fg_color="transparent")
        meta_row.grid(row=1, column=1, sticky="e", pady=(8, 0))
        self._create_meta_badge(meta_row, self._database_badge_text(), COLOR_ACCENT, COLOR_TEXT).pack(side="left")
        self._create_meta_badge(
            meta_row,
            "Scanner aktiv" if self.scanner_available else "Scanner inaktiv",
            COLOR_SUCCESS if self.scanner_available else COLOR_WARNING,
            COLOR_SUCCESS_TEXT if self.scanner_available else COLOR_WARNING_TEXT,
        ).pack(side="left", padx=(8, 0))

    def _build_summary(self, parent):
        summary = ctk.CTkFrame(parent, fg_color="transparent")
        summary.grid(row=1, column=0, padx=24, pady=(0, 14), sticky="ew")
        for index in range(4):
            summary.grid_columnconfigure(index, weight=1)

        self.summary_cards = {
            "assets": self._create_summary_card(summary, 0, "Assets", "0"),
            "people": self._create_summary_card(summary, 1, "Personen", "0"),
            "assignments": self._create_summary_card(summary, 2, "Aktive Zuweisungen", "0"),
            "schema": self._create_summary_card(summary, 3, "Schema-Version", "0"),
        }

    def _create_summary_card(self, parent, column, title, value):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=18, border_width=1, border_color=COLOR_BORDER)
        card.grid(row=0, column=column, padx=(0 if column == 0 else 8, 0), sticky="ew")
        stripe = ctk.CTkFrame(card, fg_color=COLOR_PRIMARY, height=8, corner_radius=10)
        stripe.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(card, text=title, font=("Arial", 12), text_color=COLOR_MUTED).pack(anchor="w", padx=16)
        value_label = ctk.CTkLabel(card, text=value, font=("Arial", 28, "bold"), text_color=COLOR_TEXT)
        value_label.pack(anchor="w", padx=16, pady=(2, 14))
        return value_label

    def _create_meta_badge(self, parent, text, fg_color, text_color):
        return ctk.CTkLabel(
            parent,
            text=text,
            fg_color=fg_color,
            text_color=text_color,
            corner_radius=999,
            padx=12,
            pady=6,
            font=("Arial", 11, "bold"),
        )

    def _build_statusbar(self, parent):
        statusbar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=16, border_width=1, border_color=COLOR_BORDER)
        statusbar.grid(row=3, column=0, padx=24, pady=(0, 24), sticky="ew")
        statusbar.grid_columnconfigure(0, weight=1)
        statusbar.grid_columnconfigure(1, weight=0)
        statusbar.grid_columnconfigure(2, weight=0)
        ctk.CTkLabel(statusbar, textvariable=self.status_var, text_color=COLOR_MUTED, font=("Arial", 11)).grid(
            row=0, column=0, sticky="w", padx=14, pady=10
        )
        ctk.CTkLabel(
            statusbar,
            textvariable=self.last_sync_var,
            text_color=COLOR_MUTED,
            font=("Arial", 11),
        ).grid(row=0, column=1, sticky="e", padx=14, pady=10)
        ctk.CTkLabel(
            statusbar,
            textvariable=self.change_var,
            text_color=COLOR_MUTED,
            font=("Arial", 11),
        ).grid(row=0, column=2, sticky="e", padx=14, pady=10)

    def _build_body(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=2, column=0, padx=24, pady=(0, 24), sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.asset_panel = ctk.CTkFrame(body, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        self.asset_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.asset_panel.grid_rowconfigure(4, weight=1)
        self.asset_panel.grid_columnconfigure(0, weight=1)

        asset_header = ctk.CTkFrame(self.asset_panel, fg_color="transparent")
        asset_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        asset_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            asset_header,
            text="Asset-Uebersicht",
            font=("Arial", 22, "bold"),
            text_color=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w")
        action_row = ctk.CTkFrame(asset_header, fg_color="transparent")
        action_row.grid(row=0, column=1, rowspan=2, sticky="e")
        ctk.CTkButton(
            action_row,
            text="Asset anlegen",
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_DARK,
            width=130,
            command=self.open_create_asset_dialog,
        ).pack(side="left")
        ctk.CTkButton(
            action_row,
            text="Personen",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=130,
            command=self.open_people_management_dialog,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            action_row,
            text="Zuweisung",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=110,
            command=self.open_assignment_dialog,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            action_row,
            text="Bearbeiten",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=110,
            command=self.open_edit_asset_dialog,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            action_row,
            text="Loeschen",
            fg_color=COLOR_DANGER,
            hover_color="#ebc2c7",
            text_color=COLOR_DANGER_TEXT,
            width=100,
            command=self.delete_selected_asset,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            asset_header,
            text="Erste Eingabedialoge fuer Assets, Personen und Zuweisungen sind aktiv.",
            font=("Arial", 12),
            text_color=COLOR_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        filter_row = ctk.CTkFrame(self.asset_panel, fg_color="transparent")
        filter_row.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        filter_row.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            filter_row,
            textvariable=self.search_var,
            placeholder_text="Suche nach SN, IMEI, Modell, User oder Hostname...",
            fg_color=COLOR_PANEL,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
            height=42,
            corner_radius=16,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            filter_row,
            text="Code suchen",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=120,
            command=self.search_by_code_image,
            state="normal" if self.scanner_available else "disabled",
        ).grid(row=0, column=1, padx=(12, 0), sticky="e")
        self.asset_count_label = ctk.CTkLabel(filter_row, text="0 Eintraege", text_color=COLOR_MUTED, font=("Arial", 12))
        self.asset_count_label.grid(row=0, column=2, padx=(12, 0), sticky="e")
        self.asset_hint_label = ctk.CTkLabel(
            self.asset_panel,
            text="Tipp: Suche nach SN/IMEI, scanne einen Code oder lege direkt ein neues Asset an.",
            text_color=COLOR_MUTED,
            font=("Arial", 11),
        )
        self.asset_hint_label.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 8))

        self.asset_scroll = ctk.CTkScrollableFrame(self.asset_panel, fg_color=COLOR_PANEL, corner_radius=18)
        self.asset_scroll.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 20))

        self.detail_panel = ctk.CTkFrame(body, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        self.detail_panel.grid(row=0, column=1, sticky="nsew")
        self.detail_panel.grid_rowconfigure(3, weight=1)
        self.detail_panel.grid_rowconfigure(6, weight=1)
        self._build_detail_panel()

    def _build_detail_panel(self):
        ctk.CTkLabel(
            self.detail_panel,
            text="Detailansicht",
            font=("Arial", 22, "bold"),
            text_color=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 8))

        self.detail_intro_label = ctk.CTkLabel(
            self.detail_panel,
            text="Waehle links ein Asset aus, um Stammdaten, aktuelle Zuweisung und Audit-Ereignisse zu sehen.",
            font=("Arial", 12),
            text_color=COLOR_MUTED,
            justify="left",
            wraplength=420,
        )
        self.detail_intro_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        self.detail_notice_label = ctk.CTkLabel(
            self.detail_panel,
            textvariable=self.detail_notice_var,
            font=("Arial", 11, "bold"),
            text_color=COLOR_WARNING_TEXT,
            fg_color=COLOR_WARNING,
            corner_radius=999,
            padx=12,
            pady=6,
        )
        self.detail_notice_label.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 10))

        self.asset_detail_box = ctk.CTkTextbox(self.detail_panel, fg_color=COLOR_PANEL, corner_radius=16, text_color=COLOR_TEXT)
        self.asset_detail_box.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 12))

        assignment_actions = ctk.CTkFrame(self.detail_panel, fg_color="transparent")
        assignment_actions.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(
            assignment_actions,
            text="Zuweisung bearbeiten",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=160,
            command=self.open_edit_assignment_dialog,
        ).pack(side="left")
        ctk.CTkButton(
            assignment_actions,
            text="Rueckgabe",
            fg_color=COLOR_DANGER,
            hover_color="#ebc2c7",
            text_color=COLOR_DANGER_TEXT,
            width=120,
            command=self.return_selected_asset,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            self.detail_panel,
            text="Audit-Timeline",
            font=("Arial", 18, "bold"),
            text_color=COLOR_TEXT,
        ).grid(row=5, column=0, sticky="w", padx=20, pady=(0, 8))

        self.audit_box = ctk.CTkTextbox(self.detail_panel, fg_color=COLOR_PANEL, corner_radius=16, text_color=COLOR_TEXT)
        self.audit_box.grid(row=6, column=0, sticky="nsew", padx=20, pady=(0, 20))

    def change_theme(self, theme_name):
        apply_theme(theme_name)
        self.config_data["theme"] = theme_name
        self.set_status(f"Theme gewechselt: {theme_name}")

    def _identifier_label(self, device_type):
        return "SN / IMEI" if device_type == "Smartphone" else "SN"

    def set_status(self, text):
        self.status_var.set(text)

    def _database_badge_text(self):
        db_path = str(self.db_path)
        scope = "Netzwerk" if db_path.startswith("\\\\") else "Lokal"
        return f"DB: {scope}"

    def _claim_text(self, claim):
        if not claim:
            return None
        if claim["editor_id"] == self.editor_id:
            return "wird gerade von dir bearbeitet"
        return f"wird gerade bearbeitet von {claim['editor_label']}"

    def _current_time_text(self):
        return datetime.now().strftime("%H:%M:%S")

    def _snapshot_signature(self, row):
        return (
            row["updated_at"],
            row["assigned_to"] or "",
            row["hostname"] or "",
            row["inventory_status"],
            row["device_type"],
            row["model_name"],
        )

    def _detect_snapshot_changes(self, snapshots):
        current_map = {row["id"]: self._snapshot_signature(row) for row in snapshots}
        if not self.previous_snapshot_map:
            changed_ids = set()
        else:
            changed_ids = {
                asset_id
                for asset_id, signature in current_map.items()
                if asset_id not in self.previous_snapshot_map or self.previous_snapshot_map[asset_id] != signature
            }
        self.previous_snapshot_map = current_map
        self.recent_change_asset_ids = changed_ids
        return changed_ids

    def _capture_selected_asset_baseline(self, asset=None, assignment=None):
        if asset is None:
            self.selected_asset_baseline = None
            return
        self.selected_asset_baseline = {
            "asset_id": asset["id"],
            "asset_record_version": asset["record_version"],
            "assignment_id": assignment["id"] if assignment else None,
            "assignment_record_version": assignment["record_version"] if assignment else None,
        }

    def _selected_asset_change_notice(self, asset, assignment):
        baseline = self.selected_asset_baseline
        if not baseline or baseline["asset_id"] != asset["id"]:
            return None

        messages = []
        if baseline["asset_record_version"] != asset["record_version"]:
            messages.append(
                f"Asset-Version {baseline['asset_record_version']} -> {asset['record_version']}"
            )

        current_assignment_id = assignment["id"] if assignment else None
        current_assignment_version = assignment["record_version"] if assignment else None
        if baseline["assignment_id"] != current_assignment_id:
            messages.append("aktive Zuweisung wurde gewechselt")
        elif baseline["assignment_record_version"] != current_assignment_version:
            messages.append(
                f"Zuweisung-Version {baseline['assignment_record_version']} -> {current_assignment_version}"
            )

        if not messages:
            return None
        return "Seit deiner Auswahl aktualisiert: " + ", ".join(messages)

    def _latest_event_actor(self, events):
        for event in events:
            actor = (event.get("actor") or "").strip()
            if actor:
                return actor
        return "-"

    def auto_refresh_loop(self):
        try:
            self.refresh_view(origin="auto")
        except Exception:
            pass
        finally:
            self.after(self.auto_refresh_ms, self.auto_refresh_loop)

    def handle_conflict(self, title, exc, parent=None):
        messagebox.showwarning(title, str(exc), parent=parent or self)
        self.refresh_view()
        self.set_status("Konflikt erkannt. Ansicht aktualisiert.")

    def _try_acquire_asset_claim(self, asset, *, parent, purpose):
        try:
            claim = self.repository.acquire_edit_claim(
                "managed_asset",
                asset["id"],
                editor_id=self.editor_id,
                editor_label=self.editor_label,
                ttl_seconds=self.edit_claim_ttl_seconds,
            )
        except EditClaimError as exc:
            messagebox.showwarning(purpose, str(exc), parent=parent)
            self.refresh_view(origin="claim-blocked")
            self.set_status(f"Bearbeitungsindikator aktiv: {asset['asset_tag']}")
            return None
        self.asset_claim_map[asset["id"]] = claim
        return claim

    def _bind_claim_to_modal(self, modal_shell, *, entity_type, entity_id):
        top_level = modal_shell.master
        released = {"done": False}

        def heartbeat():
            if not top_level.winfo_exists():
                return
            renewed = self.repository.renew_edit_claim(
                entity_type,
                entity_id,
                editor_id=self.editor_id,
                ttl_seconds=self.edit_claim_ttl_seconds,
            )
            if renewed:
                self.asset_claim_map[entity_id] = self.repository.get_edit_claim(entity_type, entity_id)
            top_level.after(30000, heartbeat)

        def release_claim():
            if released["done"]:
                return
            released["done"] = True
            self.repository.release_edit_claim(entity_type, entity_id, editor_id=self.editor_id)
            self.asset_claim_map.pop(entity_id, None)
            if self.selected_asset_id == entity_id:
                self.refresh_view(origin="claim-release")

        existing_close = top_level.protocol("WM_DELETE_WINDOW")

        def on_close():
            release_claim()
            if callable(existing_close):
                existing_close()
            else:
                top_level.destroy()

        top_level.protocol("WM_DELETE_WINDOW", on_close)
        top_level.bind(
            "<Destroy>",
            lambda event: release_claim() if event.widget == top_level else None,
            add="+",
        )
        top_level.after(30000, heartbeat)

    def refresh_view(self, origin="manual"):
        status = self.repository.get_status()
        snapshots = self.repository.list_asset_snapshots()
        self.asset_claim_map = {
            claim["entity_id"]: claim
            for claim in self.repository.list_edit_claims(
                entity_type="managed_asset",
                entity_ids=[row["id"] for row in snapshots],
            )
        }
        changed_ids = self._detect_snapshot_changes(snapshots)
        filtered = self._filter_snapshots(snapshots, self.search_var.get().strip())

        self.summary_cards["assets"].configure(text=str(status.asset_count))
        self.summary_cards["people"].configure(text=str(status.people_count))
        current_assignments = sum(1 for row in snapshots if row["is_current"] == 1)
        self.summary_cards["assignments"].configure(text=str(current_assignments))
        self.summary_cards["schema"].configure(text=str(status.schema_version))

        self.asset_count_label.configure(text=f"{len(filtered)} Eintraege")
        if changed_ids:
            self.change_var.set(f"{len(changed_ids)} Aenderung(en) seit letzter Synchronisierung")
        else:
            self.change_var.set("Keine neuen Aenderungen erkannt")
        self.last_sync_var.set(
            f"{'Auto-Sync' if origin == 'auto' else 'Synchronisiert'}: {self._current_time_text()}"
        )

        if filtered and changed_ids:
            self.asset_hint_label.configure(
                text=f"{len(changed_ids)} Datensatz/Datensaetze wurden seit der letzten Ansicht aktualisiert."
            )
        elif filtered:
            self.asset_hint_label.configure(
                text="Waehle links ein Asset oder nutze Bearbeiten, Zuweisung und Rueckgabe direkt aus der Detailansicht."
            )
        else:
            self.asset_hint_label.configure(text="Keine Treffer. Passe die Suche an oder lege ein neues Asset an.")
        self._render_asset_list(filtered)

        if self.selected_asset_id and not any(row["id"] == self.selected_asset_id for row in snapshots):
            self.selected_asset_id = None
            self.selected_asset_baseline = None
        if self.selected_asset_id is None and filtered:
            self.selected_asset_id = filtered[0]["id"]
            asset = self.repository.get_asset(asset_id=self.selected_asset_id)
            assignment = self.repository.get_current_assignment_for_asset(self.selected_asset_id)
            self._capture_selected_asset_baseline(asset, assignment)
        self._update_detail_panel()

    def _filter_snapshots(self, rows, query):
        if not query:
            return rows
        lowered = query.casefold()
        filtered = []
        for row in rows:
            haystack = " ".join(
                str(row.get(field) or "")
                for field in ("asset_tag", "model_name", "assigned_to", "hostname", "manufacturer", "device_type")
            ).casefold()
            if lowered in haystack:
                filtered.append(row)
        return filtered

    def _render_asset_list(self, rows):
        for child in self.asset_scroll.winfo_children():
            child.destroy()

        if not rows:
            empty = ctk.CTkFrame(self.asset_scroll, fg_color=COLOR_CARD, corner_radius=18, border_width=1, border_color=COLOR_BORDER)
            empty.pack(fill="x", padx=4, pady=4)
            ctk.CTkLabel(empty, text="Keine Assets gefunden", font=("Arial", 18, "bold"), text_color=COLOR_TEXT).pack(pady=(24, 6))
            ctk.CTkLabel(
                empty,
                text="Lege Daten an oder passe den Suchbegriff an.",
                font=("Arial", 12),
                text_color=COLOR_MUTED,
            ).pack(pady=(0, 24))
            return

        for row in rows:
            self._create_asset_card(row)

    def _create_asset_card(self, row):
        is_selected = row["id"] == self.selected_asset_id
        has_recent_change = row["id"] in self.recent_change_asset_ids
        claim = self.asset_claim_map.get(row["id"])
        card = ctk.CTkFrame(
            self.asset_scroll,
            fg_color=COLOR_CARD,
            corner_radius=18,
            border_width=2 if is_selected else 1,
            border_color=COLOR_PRIMARY if is_selected else COLOR_BORDER,
        )
        card.pack(fill="x", padx=4, pady=6)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        top.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(top, fg_color=COLOR_ACCENT, width=52, height=52, corner_radius=16)
        badge.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
        badge.grid_propagate(False)
        ctk.CTkLabel(
            badge,
            text="SP" if row["device_type"] == "Smartphone" else "NB",
            font=("Arial", 14, "bold"),
            text_color=COLOR_PRIMARY,
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            top,
            text=f"{self._identifier_label(row['device_type'])}: {row['asset_tag']}",
            font=("Arial", 16, "bold"),
            text_color=COLOR_TEXT,
        ).grid(row=0, column=1, sticky="w")
        status_text = row["inventory_status"].upper()
        status_label = status_text
        if has_recent_change:
            status_label += "  |  AKTUALISIERT"
        ctk.CTkLabel(
            top,
            text=status_label,
            font=("Arial", 11, "bold"),
            text_color=COLOR_WARNING_TEXT if has_recent_change else COLOR_PRIMARY,
        ).grid(row=0, column=2, sticky="e")
        ctk.CTkLabel(top, text=row["model_name"], font=("Arial", 13), text_color=COLOR_MUTED).grid(row=1, column=1, sticky="w", pady=(4, 0))
        assignee = row["assigned_to"] or "Nicht zugewiesen"
        hostname = row["hostname"] or "-"
        meta = f"{row['device_type']}   |   User: {assignee}   |   Hostname: {hostname}"
        claim_text = self._claim_text(claim)
        if claim_text:
            meta = f"{meta}   |   Edit: {claim_text}"
        ctk.CTkLabel(card, text=meta, font=("Arial", 12), text_color=COLOR_MUTED).pack(anchor="w", padx=16, pady=(0, 16))

        for widget in (card, top, badge):
            widget.bind("<Button-1>", lambda _event, asset_id=row["id"]: self._select_asset(asset_id))

    def _select_asset(self, asset_id):
        self.selected_asset_id = asset_id
        self.refresh_view(origin="selection")
        asset = self.repository.get_asset(asset_id=asset_id)
        assignment = self.repository.get_current_assignment_for_asset(asset_id)
        if asset:
            self._capture_selected_asset_baseline(asset, assignment)
            self._update_detail_panel()
            self.set_status(f"Ausgewaehlt: {asset['asset_tag']} | {asset['model_name']}")

    def open_create_asset_dialog(self):
        modal = self._build_modal(
            "Asset anlegen",
            "Neues Asset im v2-Datenmodell erfassen. SN bzw. SN / IMEI kann auch aus einem Barcode- oder QR-Code-Bild gelesen werden.",
        )

        device_type_var = ctk.StringVar(value="Notebook")
        status_var = ctk.StringVar(value="active")

        form = ctk.CTkFrame(modal, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 20))
        form.grid_columnconfigure(1, weight=1)

        self._modal_label(form, 0, "Geraetetyp")
        identifier_label = ctk.CTkLabel(form, text=self._identifier_label(device_type_var.get()), text_color=COLOR_MUTED, font=("Arial", 12))
        identifier_label.grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 10))
        source_label = ctk.CTkLabel(
            form,
            text=f"Quelle ({self._identifier_label(device_type_var.get())})",
            text_color=COLOR_MUTED,
            font=("Arial", 12),
        )
        source_label.grid(row=5, column=0, sticky="w", padx=(0, 12), pady=(0, 10))
        def sync_identifier_labels(_selected):
            identifier_label.configure(text=self._identifier_label(device_type_var.get()))
            source_label.configure(text=f"Quelle ({self._identifier_label(device_type_var.get())})")
        ctk.CTkOptionMenu(form, values=["Notebook", "Smartphone"], variable=device_type_var, command=sync_identifier_labels).grid(row=0, column=1, sticky="ew", pady=(0, 10))
        asset_identifier_row = ctk.CTkFrame(form, fg_color="transparent")
        asset_identifier_row.grid(row=1, column=1, sticky="ew", pady=(0, 10))
        asset_identifier_row.grid_columnconfigure(0, weight=1)
        asset_tag_entry = ctk.CTkEntry(
            asset_identifier_row,
            fg_color=COLOR_PANEL,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
            height=40,
            corner_radius=14,
        )
        asset_tag_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            asset_identifier_row,
            text="Barcode / QR",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=118,
            command=lambda: self._fill_identifier_from_code(asset_tag_entry, modal),
            state="normal" if self.scanner_available else "disabled",
        ).grid(row=0, column=1, padx=(8, 0))
        self._modal_label(form, 2, "Modell")
        model_entry = self._modal_entry(form, 2)
        self._modal_label(form, 3, "Hersteller")
        manufacturer_entry = self._modal_entry(form, 3)
        self._modal_label(form, 4, "Inventarstatus")
        ctk.CTkOptionMenu(form, values=["active", "inactive", "retired"], variable=status_var).grid(row=4, column=1, sticky="ew", pady=(0, 10))
        source_entry = self._modal_entry(form, 5)
        self._modal_label(form, 6, "Notizen")
        notes_box = ctk.CTkTextbox(form, height=110, fg_color=COLOR_PANEL, text_color=COLOR_TEXT, corner_radius=14)
        notes_box.grid(row=6, column=1, sticky="ew", pady=(0, 10))

        def save():
            try:
                asset = self.repository.create_asset(
                    device_type_var.get(),
                    asset_tag_entry.get(),
                    model_entry.get(),
                    manufacturer=manufacturer_entry.get(),
                    inventory_status=status_var.get(),
                    notes=notes_box.get("1.0", "end").strip(),
                    source_asset_tag=source_entry.get(),
                )
            except Exception as exc:
                messagebox.showerror("Asset anlegen", str(exc), parent=modal)
                return

            self.selected_asset_id = asset["id"]
            modal.destroy()
            self.refresh_view(origin="local-write")
            self._capture_selected_asset_baseline(asset)
            self.set_status(f"Asset gespeichert: {asset['asset_tag']}")

        self._modal_actions(modal, save)

    def _fill_identifier_from_code(self, target_entry, modal):
        if not self.scanner_available:
            messagebox.showwarning(
                "Code lesen",
                "Scanner-Funktion ist auf diesem Python-Startweg nicht verfuegbar. Bitte in der .venv starten oder die Scanner-Abhaengigkeiten installieren.",
                parent=modal,
            )
            return
        file_path = filedialog.askopenfilename(
            title="Barcode- oder QR-Code-Bild auswaehlen",
            filetypes=SUPPORTED_IMAGE_TYPES,
            parent=modal,
        )
        if not file_path:
            return
        try:
            decoded_value = decode_identifier_from_file(file_path)
        except Exception as exc:
            messagebox.showerror("Code lesen", str(exc), parent=modal)
            return

        target_entry.delete(0, "end")
        target_entry.insert(0, decoded_value)
        self.set_status(f"Code erkannt: {decoded_value}")

    def search_by_code_image(self):
        if not self.scanner_available:
            messagebox.showwarning(
                "Code suchen",
                "Scanner-Funktion ist auf diesem Python-Startweg nicht verfuegbar. Bitte in der .venv starten oder die Scanner-Abhaengigkeiten installieren.",
                parent=self,
            )
            return
        file_path = filedialog.askopenfilename(
            title="Barcode- oder QR-Code-Bild fuer die Suche auswaehlen",
            filetypes=SUPPORTED_IMAGE_TYPES,
            parent=self,
        )
        if not file_path:
            return
        try:
            decoded_value = decode_identifier_from_file(file_path)
        except Exception as exc:
            messagebox.showerror("Code suchen", str(exc), parent=self)
            return

        asset = self.repository.get_asset(asset_tag=decoded_value)
        self.search_var.set(decoded_value)
        if asset:
            self.selected_asset_id = asset["id"]
            self.refresh_view(origin="search")
            refreshed_asset = self.repository.get_asset(asset_id=asset["id"])
            refreshed_assignment = self.repository.get_current_assignment_for_asset(asset["id"])
            self._capture_selected_asset_baseline(refreshed_asset, refreshed_assignment)
            self.set_status(f"Code-Suche erfolgreich: {decoded_value}")
            return

        self.selected_asset_id = None
        self.selected_asset_baseline = None
        self.refresh_view(origin="search")
        messagebox.showinfo(
            "Code suchen",
            f"Kein Asset mit der Kennung '{decoded_value}' gefunden.",
            parent=self,
        )
        self.set_status(f"Code-Suche ohne Treffer: {decoded_value}")

    def open_create_person_dialog(self):
        modal = self._build_modal("Person anlegen", "Neue Person fuer spaetere Zuweisungen erfassen.")

        form = ctk.CTkFrame(modal, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 20))
        form.grid_columnconfigure(1, weight=1)

        self._modal_label(form, 0, "Name")
        name_entry = self._modal_entry(form, 0)
        self._modal_label(form, 1, "E-Mail")
        email_entry = self._modal_entry(form, 1)
        self._modal_label(form, 2, "Abteilung")
        department_entry = self._modal_entry(form, 2)

        def save():
            try:
                self.repository.create_or_update_person(
                    name_entry.get(),
                    email=email_entry.get(),
                    department=department_entry.get(),
                )
            except Exception as exc:
                messagebox.showerror("Person anlegen", str(exc), parent=modal)
                return

            modal.destroy()
            self.refresh_view(origin="local-write")
            self.set_status(f"Person gespeichert: {name_entry.get().strip()}")

        self._modal_actions(modal, save)

    def open_people_management_dialog(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Personenverwaltung")
        modal.geometry("980x660")
        modal.configure(fg_color=COLOR_PANEL)
        modal.grab_set()

        shell = ctk.CTkFrame(modal, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=2)
        shell.grid_columnconfigure(1, weight=3)
        shell.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(shell, text="Personenverwaltung", font=("Arial", 24, "bold"), text_color=COLOR_TEXT).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 6)
        )
        ctk.CTkLabel(
            shell,
            text="Verwalte Personenstammdaten und sehe direkt die aktuell zugewiesenen Geraete.",
            font=("Arial", 12),
            text_color=COLOR_MUTED,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(52, 14))

        left = ctk.CTkFrame(shell, fg_color=COLOR_PANEL, corner_radius=18)
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(shell, fg_color=COLOR_PANEL, corner_radius=18)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))
        right.grid_rowconfigure(3, weight=1)
        right.grid_rowconfigure(5, weight=1)
        right.grid_columnconfigure(1, weight=1)

        people = self.repository.list_people()
        state = {
            "selected_person_id": people[0]["id"] if people else None,
            "cards": {},
        }
        search_var = ctk.StringVar()

        ctk.CTkLabel(left, text="Personen", font=("Arial", 20, "bold"), text_color=COLOR_TEXT).grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 8)
        )
        search_entry = ctk.CTkEntry(
            left,
            textvariable=search_var,
            placeholder_text="Suche nach Name, E-Mail oder Abteilung...",
            fg_color=COLOR_CARD,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
            height=40,
            corner_radius=14,
        )
        search_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        people_scroll = ctk.CTkScrollableFrame(left, fg_color=COLOR_CARD, corner_radius=16)
        people_scroll.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))

        ctk.CTkLabel(right, text="Details", font=("Arial", 20, "bold"), text_color=COLOR_TEXT).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 8)
        )
        self._modal_label(right, 1, "Name")
        name_entry = self._modal_entry(right, 1)
        self._modal_label(right, 2, "E-Mail")
        email_entry = self._modal_entry(right, 2)
        self._modal_label(right, 3, "Abteilung")
        department_entry = self._modal_entry(right, 3)

        ctk.CTkLabel(right, text="Aktuelle Geraete", font=("Arial", 16, "bold"), text_color=COLOR_TEXT).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(8, 8)
        )
        assigned_assets_box = ctk.CTkTextbox(right, fg_color=COLOR_CARD, corner_radius=14, text_color=COLOR_TEXT)
        assigned_assets_box.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 12))

        ctk.CTkLabel(right, text="Personen-Historie", font=("Arial", 16, "bold"), text_color=COLOR_TEXT).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 8)
        )
        timeline_box = ctk.CTkTextbox(right, height=120, fg_color=COLOR_CARD, corner_radius=14, text_color=COLOR_TEXT)
        timeline_box.grid(row=7, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))

        def select_person(person_id):
            state["selected_person_id"] = person_id
            refresh_people_list()
            load_person_details()

        def filtered_people():
            query = search_var.get().strip().casefold()
            if not query:
                return self.repository.list_people()
            rows = []
            for person in self.repository.list_people():
                haystack = " ".join(
                    [
                        person["display_name"] or "",
                        person["email"] or "",
                        person["department"] or "",
                    ]
                ).casefold()
                if query in haystack:
                    rows.append(person)
            return rows

        def refresh_people_list():
            for child in people_scroll.winfo_children():
                child.destroy()

            rows = filtered_people()
            if state["selected_person_id"] and not any(item["id"] == state["selected_person_id"] for item in rows):
                state["selected_person_id"] = rows[0]["id"] if rows else None

            if not rows:
                ctk.CTkLabel(
                    people_scroll,
                    text="Keine Personen gefunden",
                    text_color=COLOR_MUTED,
                    font=("Arial", 13),
                ).pack(anchor="w", padx=8, pady=12)
                return

            for person in rows:
                selected = person["id"] == state["selected_person_id"]
                card = ctk.CTkFrame(
                    people_scroll,
                    fg_color=COLOR_PANEL,
                    corner_radius=14,
                    border_width=2 if selected else 1,
                    border_color=COLOR_PRIMARY if selected else COLOR_BORDER,
                )
                card.pack(fill="x", padx=4, pady=4)
                ctk.CTkLabel(card, text=person["display_name"], font=("Arial", 14, "bold"), text_color=COLOR_TEXT).pack(
                    anchor="w", padx=12, pady=(10, 2)
                )
                meta = " | ".join(part for part in [person["department"], person["email"]] if part)
                ctk.CTkLabel(card, text=meta or "Keine Zusatzinfos", font=("Arial", 11), text_color=COLOR_MUTED).pack(
                    anchor="w", padx=12, pady=(0, 10)
                )
                card.bind("<Button-1>", lambda _event, pid=person["id"]: select_person(pid))
                for child in card.winfo_children():
                    child.bind("<Button-1>", lambda _event, pid=person["id"]: select_person(pid))

        def load_person_details():
            person_id = state["selected_person_id"]
            for entry in (name_entry, email_entry, department_entry):
                entry.delete(0, "end")
            assigned_assets_box.configure(state="normal")
            assigned_assets_box.delete("1.0", "end")
            timeline_box.configure(state="normal")
            timeline_box.delete("1.0", "end")

            if person_id is None:
                assigned_assets_box.insert("1.0", "Keine Person ausgewaehlt.")
                timeline_box.insert("1.0", "Keine Historie sichtbar.")
                assigned_assets_box.configure(state="disabled")
                timeline_box.configure(state="disabled")
                return

            person = self.repository.get_person(person_id)
            if person is None:
                assigned_assets_box.insert("1.0", "Person nicht mehr vorhanden.")
                timeline_box.insert("1.0", "Keine Historie sichtbar.")
                assigned_assets_box.configure(state="disabled")
                timeline_box.configure(state="disabled")
                return

            name_entry.insert(0, person["display_name"] or "")
            email_entry.insert(0, person["email"] or "")
            department_entry.insert(0, person["department"] or "")

            current_assets = self.repository.list_current_assets_for_person(person_id)
            if current_assets:
                lines = [
                    f"{self._identifier_label(item['device_type'])}: {item['asset_tag']} | {item['model_name']} | Hostname: {item['hostname'] or '-'}"
                    for item in current_assets
                ]
                assigned_assets_box.insert("1.0", "\n".join(lines))
            else:
                assigned_assets_box.insert("1.0", "Keine aktiven Geraete zugewiesen.")

            timeline = self.repository.list_person_timeline(person_id)
            if timeline:
                lines = [
                    f"{item['created_at']} | {item['action']} | {item['payload_json']}"
                    for item in timeline
                ]
                timeline_box.insert("1.0", "\n".join(lines))
            else:
                timeline_box.insert("1.0", "Keine Personen-Historie vorhanden.")

            assigned_assets_box.configure(state="disabled")
            timeline_box.configure(state="disabled")

        def create_person():
            try:
                person = self.repository.create_or_update_person(
                    name_entry.get(),
                    email=email_entry.get(),
                    department=department_entry.get(),
                )
            except Exception as exc:
                messagebox.showerror("Personenverwaltung", str(exc), parent=modal)
                return
            state["selected_person_id"] = person["id"]
            refresh_people_list()
            load_person_details()
            self.refresh_view()
            self.set_status(f"Person angelegt: {person['display_name']}")

        def save_person():
            person_id = state["selected_person_id"]
            if person_id is None:
                create_person()
                return
            current_person = self.repository.get_person(person_id)
            try:
                self.repository.update_person(
                    person_id,
                    display_name=name_entry.get(),
                    email=email_entry.get(),
                    department=department_entry.get(),
                    expected_record_version=current_person["record_version"],
                )
            except ConflictError as exc:
                self.handle_conflict("Personenverwaltung", exc, parent=modal)
                return
            except Exception as exc:
                messagebox.showerror("Personenverwaltung", str(exc), parent=modal)
                return
            refresh_people_list()
            load_person_details()
            self.refresh_view()
            self.set_status("Person aktualisiert")

        def new_person_form():
            state["selected_person_id"] = None
            refresh_people_list()
            for entry in (name_entry, email_entry, department_entry):
                entry.delete(0, "end")
            assigned_assets_box.configure(state="normal")
            assigned_assets_box.delete("1.0", "end")
            assigned_assets_box.insert("1.0", "Noch keine Person gespeichert.")
            assigned_assets_box.configure(state="disabled")
            timeline_box.configure(state="normal")
            timeline_box.delete("1.0", "end")
            timeline_box.insert("1.0", "Nach dem Speichern erscheint hier die Historie.")
            timeline_box.configure(state="disabled")

        def delete_person():
            person_id = state["selected_person_id"]
            if person_id is None:
                messagebox.showinfo("Personenverwaltung", "Waehle zuerst eine Person aus.", parent=modal)
                return
            person = self.repository.get_person(person_id)
            confirm = messagebox.askyesno(
                "Person loeschen",
                f"Soll die Person '{person['display_name']}' wirklich geloescht werden?\n\nDas ist nur moeglich, wenn keine aktive Zuweisung mehr besteht.",
                parent=modal,
            )
            if not confirm:
                return
            try:
                self.repository.delete_person(
                    person_id,
                    actor="ui-delete",
                    expected_record_version=person["record_version"],
                )
            except ConflictError as exc:
                self.handle_conflict("Personenverwaltung", exc, parent=modal)
                return
            except Exception as exc:
                messagebox.showerror("Personenverwaltung", str(exc), parent=modal)
                return
            rows = self.repository.list_people()
            state["selected_person_id"] = rows[0]["id"] if rows else None
            refresh_people_list()
            load_person_details()
            self.refresh_view()
            self.set_status("Person geloescht")

        action_bar = ctk.CTkFrame(right, fg_color="transparent")
        action_bar.grid(row=8, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))
        ctk.CTkButton(action_bar, text="Neu", fg_color=COLOR_ACCENT, hover_color=COLOR_PRIMARY_DARK, text_color=COLOR_TEXT, width=100, command=new_person_form).pack(side="left")
        ctk.CTkButton(action_bar, text="Speichern", fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_DARK, width=110, command=save_person).pack(side="left", padx=(8, 0))
        ctk.CTkButton(action_bar, text="Anlegen", fg_color=COLOR_ACCENT, hover_color=COLOR_PRIMARY_DARK, text_color=COLOR_TEXT, width=100, command=create_person).pack(side="left", padx=(8, 0))
        ctk.CTkButton(action_bar, text="Loeschen", fg_color=COLOR_DANGER, hover_color="#ebc2c7", text_color=COLOR_DANGER_TEXT, width=100, command=delete_person).pack(side="right")

        search_var.trace_add("write", lambda *_args: (refresh_people_list(), load_person_details()))
        refresh_people_list()
        load_person_details()

    def open_edit_asset_dialog(self):
        if self.selected_asset_id is None:
            messagebox.showinfo("Bearbeiten", "Waehle zuerst links ein Asset aus.")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        if asset is None:
            messagebox.showwarning("Bearbeiten", "Das ausgewaehlte Asset ist nicht mehr vorhanden.")
            self.selected_asset_id = None
            self.refresh_view()
            return

        modal = self._build_modal(
            "Asset bearbeiten",
            f"Ausgewaehltes Asset: {self._identifier_label(asset['device_type'])} {asset['asset_tag']} | {asset['model_name']}",
        )
        if self._try_acquire_asset_claim(asset, parent=modal.master, purpose="Asset bearbeiten") is None:
            modal.master.destroy()
            return
        self._bind_claim_to_modal(modal, entity_type="managed_asset", entity_id=asset["id"])

        device_type_var = ctk.StringVar(value=asset["device_type"])
        status_var = ctk.StringVar(value=asset["inventory_status"])

        form = ctk.CTkFrame(modal, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 20))
        form.grid_columnconfigure(1, weight=1)

        self._modal_label(form, 0, "Geraetetyp")
        identifier_label = ctk.CTkLabel(form, text=self._identifier_label(device_type_var.get()), text_color=COLOR_MUTED, font=("Arial", 12))
        identifier_label.grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 10))
        source_label = ctk.CTkLabel(
            form,
            text=f"Quelle ({self._identifier_label(device_type_var.get())})",
            text_color=COLOR_MUTED,
            font=("Arial", 12),
        )
        source_label.grid(row=5, column=0, sticky="w", padx=(0, 12), pady=(0, 10))

        def sync_identifier_labels(_selected):
            identifier_label.configure(text=self._identifier_label(device_type_var.get()))
            source_label.configure(text=f"Quelle ({self._identifier_label(device_type_var.get())})")

        ctk.CTkOptionMenu(form, values=["Notebook", "Smartphone"], variable=device_type_var, command=sync_identifier_labels).grid(row=0, column=1, sticky="ew", pady=(0, 10))
        identifier_entry = self._modal_entry(form, 1)
        identifier_entry.insert(0, asset["asset_tag"])
        self._modal_label(form, 2, "Modell")
        model_entry = self._modal_entry(form, 2)
        model_entry.insert(0, asset["model_name"])
        self._modal_label(form, 3, "Hersteller")
        manufacturer_entry = self._modal_entry(form, 3)
        manufacturer_entry.insert(0, asset["manufacturer"] or "")
        self._modal_label(form, 4, "Inventarstatus")
        ctk.CTkOptionMenu(form, values=["active", "inactive", "retired"], variable=status_var).grid(row=4, column=1, sticky="ew", pady=(0, 10))
        source_entry = self._modal_entry(form, 5)
        source_entry.insert(0, asset["source_asset_tag"] or "")
        self._modal_label(form, 6, "Notizen")
        notes_box = ctk.CTkTextbox(form, height=110, fg_color=COLOR_PANEL, text_color=COLOR_TEXT, corner_radius=14)
        notes_box.grid(row=6, column=1, sticky="ew", pady=(0, 10))
        notes_box.insert("1.0", asset["notes"] or "")

        def save():
            try:
                self.repository.update_asset(
                    asset["id"],
                    device_type=device_type_var.get(),
                    asset_tag=identifier_entry.get(),
                    model_name=model_entry.get(),
                    manufacturer=manufacturer_entry.get(),
                    inventory_status=status_var.get(),
                    notes=notes_box.get("1.0", "end").strip(),
                    source_asset_tag=source_entry.get(),
                    expected_record_version=asset["record_version"],
                )
            except ConflictError as exc:
                self.handle_conflict("Asset bearbeiten", exc, parent=modal)
                return
            except Exception as exc:
                messagebox.showerror("Asset bearbeiten", str(exc), parent=modal)
                return

            modal.destroy()
            self.refresh_view(origin="local-write")
            refreshed_asset = self.repository.get_asset(asset_id=asset["id"])
            refreshed_assignment = self.repository.get_current_assignment_for_asset(asset["id"])
            self._capture_selected_asset_baseline(refreshed_asset, refreshed_assignment)
            self.set_status(f"Asset aktualisiert: {identifier_entry.get().strip()}")

        self._modal_actions(modal, save)

    def delete_selected_asset(self):
        if self.selected_asset_id is None:
            messagebox.showinfo("Loeschen", "Waehle zuerst links ein Asset aus.")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        if asset is None:
            messagebox.showwarning("Loeschen", "Das ausgewaehlte Asset ist nicht mehr vorhanden.")
            self.selected_asset_id = None
            self.refresh_view()
            return

        confirm = messagebox.askyesno(
            "Asset loeschen",
            f"Soll das Asset '{asset['asset_tag']}' wirklich geloescht werden?\n\nAktuelle Zuweisungen und Historie im Asset-Kontext werden dabei ebenfalls entfernt.",
            parent=self,
        )
        if not confirm:
            return

        try:
            self.repository.delete_asset(
                asset["id"],
                actor="ui-delete",
                expected_record_version=asset["record_version"],
            )
        except ConflictError as exc:
            self.handle_conflict("Loeschen", exc, parent=self)
            return
        except Exception as exc:
            messagebox.showerror("Loeschen", str(exc), parent=self)
            return

        self.selected_asset_id = None
        self.selected_asset_baseline = None
        self.refresh_view(origin="local-write")
        self.set_status(f"Asset geloescht: {asset['asset_tag']}")

    def open_edit_assignment_dialog(self):
        if self.selected_asset_id is None:
            messagebox.showinfo("Zuweisung bearbeiten", "Waehle zuerst links ein Asset aus.")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        assignment = self.repository.get_current_assignment_for_asset(self.selected_asset_id)
        if asset is None:
            messagebox.showwarning("Zuweisung bearbeiten", "Das ausgewaehlte Asset ist nicht mehr vorhanden.")
            self.selected_asset_id = None
            self.refresh_view()
            return
        if assignment is None:
            messagebox.showinfo("Zuweisung bearbeiten", "Fuer dieses Asset gibt es aktuell keine aktive Zuweisung.")
            return

        people = self.repository.list_people()
        if not people:
            messagebox.showwarning("Zuweisung bearbeiten", "Es sind keine Personen vorhanden.")
            return

        modal = self._build_modal(
            "Zuweisung bearbeiten",
            f"Aktuelle Auswahl: {self._identifier_label(asset['device_type'])} {asset['asset_tag']} | {asset['model_name']}",
        )
        if self._try_acquire_asset_claim(asset, parent=modal.master, purpose="Zuweisung bearbeiten") is None:
            modal.master.destroy()
            return
        self._bind_claim_to_modal(modal, entity_type="managed_asset", entity_id=asset["id"])

        form = ctk.CTkFrame(modal, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 20))
        form.grid_columnconfigure(1, weight=1)

        people_map = {f"{person['display_name']} ({person['id']})": person["id"] for person in people}
        selected_person_label = next(
            (label for label, person_id in people_map.items() if person_id == assignment["person_id"]),
            next(iter(people_map)),
        )
        person_var = ctk.StringVar(value=selected_person_label)

        self._modal_label(form, 0, self._identifier_label(asset["device_type"]))
        ctk.CTkLabel(form, text=f"{asset['asset_tag']} | {asset['device_type']}", text_color=COLOR_TEXT).grid(row=0, column=1, sticky="w", pady=(0, 10))
        self._modal_label(form, 1, "Person")
        ctk.CTkOptionMenu(form, values=list(people_map.keys()), variable=person_var).grid(row=1, column=1, sticky="ew", pady=(0, 10))
        self._modal_label(form, 2, "Hostname")
        hostname_entry = self._modal_entry(form, 2)
        hostname_entry.insert(0, assignment["hostname"] or "")
        if asset["device_type"] == "Smartphone":
            hostname_entry.delete(0, "end")
            hostname_entry.insert(0, "wird fuer Smartphones ignoriert")
            hostname_entry.configure(state="disabled")
        self._modal_label(form, 3, "Notizen")
        notes_box = ctk.CTkTextbox(form, height=110, fg_color=COLOR_PANEL, text_color=COLOR_TEXT, corner_radius=14)
        notes_box.grid(row=3, column=1, sticky="ew", pady=(0, 10))
        notes_box.insert("1.0", assignment["notes"] or "")

        def save():
            try:
                self.repository.update_current_assignment(
                    asset["id"],
                    person_id=people_map[person_var.get()],
                    hostname="" if asset["device_type"] == "Smartphone" else hostname_entry.get(),
                    notes=notes_box.get("1.0", "end").strip(),
                    actor="ui-dialog",
                    expected_record_version=assignment["record_version"],
                )
            except ConflictError as exc:
                self.handle_conflict("Zuweisung bearbeiten", exc, parent=modal)
                return
            except Exception as exc:
                messagebox.showerror("Zuweisung bearbeiten", str(exc), parent=modal)
                return

            modal.destroy()
            self.refresh_view(origin="local-write")
            refreshed_asset = self.repository.get_asset(asset_id=asset["id"])
            refreshed_assignment = self.repository.get_current_assignment_for_asset(asset["id"])
            self._capture_selected_asset_baseline(refreshed_asset, refreshed_assignment)
            self.set_status(f"Zuweisung aktualisiert: {asset['asset_tag']}")

        self._modal_actions(modal, save)

    def return_selected_asset(self):
        if self.selected_asset_id is None:
            messagebox.showinfo("Rueckgabe", "Waehle zuerst links ein Asset aus.")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        assignment = self.repository.get_current_assignment_for_asset(self.selected_asset_id)
        if asset is None:
            messagebox.showwarning("Rueckgabe", "Das ausgewaehlte Asset ist nicht mehr vorhanden.")
            self.selected_asset_id = None
            self.refresh_view()
            return
        if assignment is None:
            messagebox.showinfo("Rueckgabe", "Fuer dieses Asset gibt es aktuell keine aktive Zuweisung.")
            return

        confirm = messagebox.askyesno(
            "Rueckgabe",
            f"Soll die aktuelle Zuweisung fuer '{asset['asset_tag']}' wirklich beendet werden?",
            parent=self,
        )
        if not confirm:
            return

        try:
            self.repository.return_asset(
                asset["id"],
                actor="ui-return",
                notes="Rueckgabe ueber UI",
                expected_record_version=assignment["record_version"],
            )
        except ConflictError as exc:
            self.handle_conflict("Rueckgabe", exc, parent=self)
            return
        except Exception as exc:
            messagebox.showerror("Rueckgabe", str(exc), parent=self)
            return

        self.refresh_view(origin="local-write")
        refreshed_asset = self.repository.get_asset(asset_id=asset["id"])
        self._capture_selected_asset_baseline(refreshed_asset, None)
        self.set_status(f"Rueckgabe verbucht: {asset['asset_tag']}")

    def open_assignment_dialog(self):
        if self.selected_asset_id is None:
            messagebox.showinfo("Zuweisung", "Waehle zuerst links ein Asset aus.")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        people = self.repository.list_people()
        if not people:
            messagebox.showwarning("Zuweisung", "Lege zuerst mindestens eine Person an.")
            return

        modal = self._build_modal(
            "Zuweisung erstellen",
            f"Aktuelle Auswahl: {self._identifier_label(asset['device_type'])} {asset['asset_tag']} | {asset['model_name']}",
        )
        if self._try_acquire_asset_claim(asset, parent=modal.master, purpose="Zuweisung erstellen") is None:
            modal.master.destroy()
            return
        self._bind_claim_to_modal(modal, entity_type="managed_asset", entity_id=asset["id"])

        form = ctk.CTkFrame(modal, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 20))
        form.grid_columnconfigure(1, weight=1)

        people_map = {f"{person['display_name']} ({person['id']})": person["id"] for person in people}
        person_var = ctk.StringVar(value=next(iter(people_map)))

        self._modal_label(form, 0, self._identifier_label(asset["device_type"]))
        ctk.CTkLabel(form, text=f"{asset['asset_tag']} | {asset['device_type']}", text_color=COLOR_TEXT).grid(row=0, column=1, sticky="w", pady=(0, 10))
        self._modal_label(form, 1, "Person")
        ctk.CTkOptionMenu(form, values=list(people_map.keys()), variable=person_var).grid(row=1, column=1, sticky="ew", pady=(0, 10))
        self._modal_label(form, 2, "Hostname")
        hostname_entry = self._modal_entry(form, 2)
        if asset["device_type"] == "Smartphone":
            hostname_entry.insert(0, "wird fuer Smartphones ignoriert")
            hostname_entry.configure(state="disabled")
        self._modal_label(form, 3, "Notizen")
        notes_box = ctk.CTkTextbox(form, height=110, fg_color=COLOR_PANEL, text_color=COLOR_TEXT, corner_radius=14)
        notes_box.grid(row=3, column=1, sticky="ew", pady=(0, 10))

        def save():
            try:
                self.repository.assign_asset(
                    asset_id=asset["id"],
                    person_id=people_map[person_var.get()],
                    hostname="" if asset["device_type"] == "Smartphone" else hostname_entry.get(),
                    notes=notes_box.get("1.0", "end").strip(),
                    actor="ui-dialog",
                )
            except Exception as exc:
                messagebox.showerror("Zuweisung erstellen", str(exc), parent=modal)
                return

            modal.destroy()
            self.refresh_view(origin="local-write")
            refreshed_asset = self.repository.get_asset(asset_id=asset["id"])
            refreshed_assignment = self.repository.get_current_assignment_for_asset(asset["id"])
            self._capture_selected_asset_baseline(refreshed_asset, refreshed_assignment)
            self.set_status(f"Zuweisung erstellt: {asset['asset_tag']}")

        self._modal_actions(modal, save)

    def _build_modal(self, title, subtitle):
        modal = ctk.CTkToplevel(self)
        modal.title(title)
        modal.geometry("640x640")
        modal.configure(fg_color=COLOR_PANEL)
        modal.grab_set()

        shell = ctk.CTkFrame(modal, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(shell, text=title, font=("Arial", 24, "bold"), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(20, 6))
        ctk.CTkLabel(shell, text=subtitle, font=("Arial", 12), text_color=COLOR_MUTED, wraplength=560, justify="left").pack(anchor="w", padx=20, pady=(0, 12))
        return shell

    def _modal_label(self, parent, row, text):
        ctk.CTkLabel(parent, text=text, text_color=COLOR_MUTED, font=("Arial", 12)).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(0, 10))

    def _modal_entry(self, parent, row):
        entry = ctk.CTkEntry(parent, fg_color=COLOR_PANEL, border_color=COLOR_BORDER, text_color=COLOR_TEXT, height=40, corner_radius=14)
        entry.grid(row=row, column=1, sticky="ew", pady=(0, 10))
        return entry

    def _modal_actions(self, modal_shell, save_callback):
        actions = ctk.CTkFrame(modal_shell, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(
            actions,
            text="Abbrechen",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_PRIMARY_DARK,
            text_color=COLOR_TEXT,
            width=130,
            command=modal_shell.master.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Speichern",
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_DARK,
            width=130,
            command=save_callback,
        ).pack(side="right")

    def _update_detail_panel(self):
        self.asset_detail_box.configure(state="normal")
        self.asset_detail_box.delete("1.0", "end")
        self.audit_box.configure(state="normal")
        self.audit_box.delete("1.0", "end")

        if self.selected_asset_id is None:
            self.detail_notice_var.set("Auswahl ist synchron.")
            self.asset_detail_box.insert("1.0", "Noch kein Asset ausgewaehlt.")
            self.audit_box.insert("1.0", "Noch keine Ereignisse sichtbar.")
            self.asset_detail_box.configure(state="disabled")
            self.audit_box.configure(state="disabled")
            return

        asset = self.repository.get_asset(asset_id=self.selected_asset_id)
        assignment = self.repository.get_current_assignment_for_asset(self.selected_asset_id)
        events = self.repository.list_timeline_for_asset(self.selected_asset_id)

        if asset is None:
            self.detail_notice_var.set("Das ausgewaehlte Asset wurde zwischenzeitlich entfernt.")
            self.detail_notice_label.configure(fg_color=COLOR_DANGER, text_color=COLOR_DANGER_TEXT)
            self.asset_detail_box.insert("1.0", "Das ausgewaehlte Asset ist nicht mehr vorhanden.")
            self.audit_box.insert("1.0", "Keine Ereignisse verfuegbar.")
        else:
            claim = self.asset_claim_map.get(asset["id"])
            change_notice = self._selected_asset_change_notice(asset, assignment)
            claim_notice = self._claim_text(claim)
            if claim_notice and claim["editor_id"] != self.editor_id:
                self.detail_notice_var.set(f"{asset['asset_tag']} {claim_notice}.")
                self.detail_notice_label.configure(fg_color=COLOR_DANGER, text_color=COLOR_DANGER_TEXT)
            elif claim_notice:
                self.detail_notice_var.set(f"{asset['asset_tag']} {claim_notice}.")
                self.detail_notice_label.configure(fg_color=COLOR_WARNING, text_color=COLOR_WARNING_TEXT)
            elif change_notice:
                self.detail_notice_var.set(change_notice)
                self.detail_notice_label.configure(fg_color=COLOR_WARNING, text_color=COLOR_WARNING_TEXT)
            else:
                self.detail_notice_var.set("Auswahl ist synchron.")
                self.detail_notice_label.configure(fg_color=COLOR_SUCCESS, text_color=COLOR_SUCCESS_TEXT)

            latest_actor = self._latest_event_actor(events)
            detail_lines = [
                f"Asset-ID: {asset['id']}",
                f"Geraetetyp: {asset['device_type']}",
                f"{self._identifier_label(asset['device_type'])}: {asset['asset_tag']}",
                f"Modell: {asset['model_name']}",
                f"Hersteller: {asset['manufacturer'] or '-'}",
                f"Inventarstatus: {asset['inventory_status']}",
                f"Notizen: {asset['notes'] or '-'}",
                f"Quelle ({self._identifier_label(asset['device_type'])}): {asset['source_asset_tag'] or '-'}",
                f"Record-Version: {asset['record_version']}",
                f"Erstellt: {asset['created_at']}",
                f"Aktualisiert: {asset['updated_at']}",
                f"Letzter bekannter Bearbeiter: {latest_actor}",
                "",
                "Aktuelle Zuweisung:",
            ]
            if assignment:
                person = self.repository.get_person(assignment["person_id"]) if assignment["person_id"] else None
                detail_lines.extend(
                    [
                        f"User: {person['display_name'] if person else '-'}",
                        f"Hostname: {assignment['hostname'] or '-'}",
                        f"Status: {assignment['assignment_status']}",
                        f"Assigned at: {assignment['assigned_at']}",
                        f"Created by: {assignment['created_by'] or '-'}",
                        f"Updated by: {assignment['updated_by'] or '-'}",
                        f"Notes: {assignment['notes'] or '-'}",
                    ]
                )
            else:
                detail_lines.append("Keine aktive Zuweisung vorhanden.")
            self.asset_detail_box.insert("1.0", "\n".join(detail_lines))

            if events:
                lines = []
                for event in events:
                    payload = event["payload_json"]
                    lines.append(f"{event['created_at']} | {event['action']} | {event['actor'] or '-'}")
                    lines.append(payload)
                    lines.append("")
                self.audit_box.insert("1.0", "\n".join(lines).strip())
            else:
                self.audit_box.insert("1.0", "Keine Audit-Ereignisse vorhanden.")

        self.asset_detail_box.configure(state="disabled")
        self.audit_box.configure(state="disabled")
