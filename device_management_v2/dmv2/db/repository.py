import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

from .migrations import (
    ASSIGNMENT_STATUS_VALUES,
    DEVICE_TYPE_VALUES,
    INVENTORY_STATUS_VALUES,
    ensure_database,
    get_schema_version,
    normalize_asset_tag,
    normalize_person_name,
)


class ConflictError(ValueError):
    """Raised when a record changed in the meantime."""


class EditClaimError(ValueError):
    """Raised when another user currently edits the same record."""


@dataclass
class RepositoryStatus:
    database_path: str
    schema_version: int
    asset_count: int
    people_count: int
    assignment_count: int


class DatabaseRepository:
    def __init__(self, db_path):
        self.db_path = db_path
        ensure_database(self.db_path)

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def get_status(self):
        with closing(self.connect()) as conn:
            asset_count = conn.execute("SELECT COUNT(*) FROM managed_assets").fetchone()[0]
            people_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            assignment_count = conn.execute("SELECT COUNT(*) FROM asset_assignments").fetchone()[0]

        return RepositoryStatus(
            database_path=str(self.db_path),
            schema_version=get_schema_version(self.db_path),
            asset_count=asset_count,
            people_count=people_count,
            assignment_count=assignment_count,
        )

    def _raise_conflict(self, entity_name):
        raise ConflictError(
            f"{entity_name} wurde zwischenzeitlich von einem anderen Nutzer geaendert. Bitte Ansicht aktualisieren und erneut versuchen."
        )

    def _raise_edit_claim(self, entity_name, editor_label):
        raise EditClaimError(
            f"{entity_name} wird gerade von {editor_label} bearbeitet. Bitte spaeter erneut versuchen oder kurz abstimmen."
        )

    def _utc_now(self):
        return datetime.now(UTC)

    def _utc_iso(self, value):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _purge_expired_edit_claims(self, conn):
        conn.execute(
            """
            DELETE FROM edit_claims
            WHERE expires_at <= ?
            """,
            (self._utc_iso(self._utc_now()),),
        )

    def acquire_edit_claim(self, entity_type, entity_id, *, editor_id, editor_label, ttl_seconds=120):
        entity_name = "Datensatz"
        if entity_type == "managed_asset":
            entity_name = "Asset"
        elif entity_type == "person":
            entity_name = "Person"

        now = self._utc_now()
        expires_at = now + timedelta(seconds=max(int(ttl_seconds), 30))
        with closing(self.connect()) as conn:
            self._purge_expired_edit_claims(conn)
            existing = conn.execute(
                """
                SELECT entity_type, entity_id, editor_id, editor_label, claimed_at, heartbeat_at, expires_at
                FROM edit_claims
                WHERE entity_type = ? AND entity_id = ?
                """,
                (entity_type, entity_id),
            ).fetchone()
            if existing and existing["editor_id"] != editor_id:
                self._raise_edit_claim(entity_name, existing["editor_label"] or "einem anderen Nutzer")

            if existing:
                conn.execute(
                    """
                    UPDATE edit_claims
                    SET editor_label = ?, heartbeat_at = ?, expires_at = ?
                    WHERE entity_type = ? AND entity_id = ? AND editor_id = ?
                    """,
                    (
                        editor_label.strip(),
                        self._utc_iso(now),
                        self._utc_iso(expires_at),
                        entity_type,
                        entity_id,
                        editor_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO edit_claims (
                        entity_type,
                        entity_id,
                        editor_id,
                        editor_label,
                        claimed_at,
                        heartbeat_at,
                        expires_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_type,
                        entity_id,
                        editor_id,
                        editor_label.strip(),
                        self._utc_iso(now),
                        self._utc_iso(now),
                        self._utc_iso(expires_at),
                    ),
                )
            conn.commit()
            return self.get_edit_claim(entity_type, entity_id)

    def renew_edit_claim(self, entity_type, entity_id, *, editor_id, ttl_seconds=120):
        now = self._utc_now()
        expires_at = now + timedelta(seconds=max(int(ttl_seconds), 30))
        with closing(self.connect()) as conn:
            self._purge_expired_edit_claims(conn)
            cursor = conn.execute(
                """
                UPDATE edit_claims
                SET heartbeat_at = ?, expires_at = ?
                WHERE entity_type = ? AND entity_id = ? AND editor_id = ?
                """,
                (
                    self._utc_iso(now),
                    self._utc_iso(expires_at),
                    entity_type,
                    entity_id,
                    editor_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def release_edit_claim(self, entity_type, entity_id, *, editor_id):
        with closing(self.connect()) as conn:
            cursor = conn.execute(
                """
                DELETE FROM edit_claims
                WHERE entity_type = ? AND entity_id = ? AND editor_id = ?
                """,
                (entity_type, entity_id, editor_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_edit_claim(self, entity_type, entity_id):
        with closing(self.connect()) as conn:
            self._purge_expired_edit_claims(conn)
            row = conn.execute(
                """
                SELECT entity_type, entity_id, editor_id, editor_label, claimed_at, heartbeat_at, expires_at
                FROM edit_claims
                WHERE entity_type = ? AND entity_id = ?
                """,
                (entity_type, entity_id),
            ).fetchone()
            conn.commit()
            return self._row_to_dict(row)

    def list_edit_claims(self, entity_type=None, entity_ids=None):
        sql = """
            SELECT entity_type, entity_id, editor_id, editor_label, claimed_at, heartbeat_at, expires_at
            FROM edit_claims
            WHERE 1 = 1
        """
        params = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        if entity_ids:
            placeholders = ", ".join("?" for _ in entity_ids)
            sql += f" AND entity_id IN ({placeholders})"
            params.extend(entity_ids)
        sql += " ORDER BY expires_at DESC, entity_type ASC, entity_id ASC"

        with closing(self.connect()) as conn:
            self._purge_expired_edit_claims(conn)
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return [self._row_to_dict(row) for row in rows]

    def create_or_update_person(self, display_name, email="", department=""):
        normalized_name = normalize_person_name(display_name)
        if not normalized_name:
            raise ValueError("Der Personenname darf nicht leer sein.")

        with closing(self.connect()) as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM people
                WHERE display_name_normalized = ?
                """,
                (normalized_name,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE people
                    SET display_name = ?, email = ?, department = ?, updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                    WHERE id = ?
                    """,
                    (display_name.strip(), email.strip(), department.strip(), existing["id"]),
                )
                person_id = existing["id"]
                action = "updated"
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO people (display_name, display_name_normalized, email, department)
                    VALUES (?, ?, ?, ?)
                    """,
                    (display_name.strip(), normalized_name, email.strip(), department.strip()),
                )
                person_id = cursor.lastrowid
                action = "created"

            self._write_audit_event(
                conn,
                entity_type="person",
                entity_id=person_id,
                action=f"person-{action}",
                actor="repository",
                payload={
                    "display_name": display_name.strip(),
                    "email": email.strip(),
                    "department": department.strip(),
                },
            )
            conn.commit()
            return self.get_person(person_id)

    def get_person(self, person_id):
        with closing(self.connect()) as conn:
            row = conn.execute(
                """
                SELECT id, display_name, display_name_normalized, email, department, created_at, updated_at, record_version
                FROM people
                WHERE id = ?
                """,
                (person_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def update_person(self, person_id, *, display_name=None, email=None, department=None, expected_record_version=None):
        updates = []
        values = []

        if display_name is not None:
            normalized_name = normalize_person_name(display_name)
            if not normalized_name:
                raise ValueError("Der Personenname darf nicht leer sein.")
            updates.append("display_name = ?")
            values.append(display_name.strip())
            updates.append("display_name_normalized = ?")
            values.append(normalized_name)
        if email is not None:
            updates.append("email = ?")
            values.append(email.strip())
        if department is not None:
            updates.append("department = ?")
            values.append(department.strip())

        if not updates:
            return self.get_person(person_id)

        values.append(person_id)
        if expected_record_version is not None:
            values.append(expected_record_version)

        with closing(self.connect()) as conn:
            cursor = conn.execute(
                f"""
                UPDATE people
                SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                WHERE id = ?
                {"AND record_version = ?" if expected_record_version is not None else ""}
                """,
                values,
            )
            if cursor.rowcount == 0:
                exists = conn.execute("SELECT id FROM people WHERE id = ?", (person_id,)).fetchone()
                if exists is None:
                    raise ValueError(f"Keine Person mit ID {person_id} gefunden.")
                self._raise_conflict("Person")

            self._write_audit_event(
                conn,
                entity_type="person",
                entity_id=person_id,
                action="person-updated",
                actor="repository",
                payload={
                    "display_name": display_name.strip() if display_name is not None else None,
                    "email": email.strip() if email is not None else None,
                    "department": department.strip() if department is not None else None,
                },
            )
            conn.commit()
            return self.get_person(person_id)

    def list_people(self):
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, display_name, display_name_normalized, email, department, created_at, updated_at, record_version
                FROM people
                ORDER BY display_name_normalized ASC
                """
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def delete_person(self, person_id, actor="repository", expected_record_version=None):
        with closing(self.connect()) as conn:
            person = conn.execute(
                """
                SELECT id, display_name, email, department, record_version
                FROM people
                WHERE id = ?
                """,
                (person_id,),
            ).fetchone()
            if person is None:
                raise ValueError(f"Keine Person mit ID {person_id} gefunden.")
            if expected_record_version is not None and person["record_version"] != expected_record_version:
                self._raise_conflict("Person")

            active_assignments = conn.execute(
                """
                SELECT COUNT(*)
                FROM asset_assignments
                WHERE person_id = ? AND is_current = 1
                """,
                (person_id,),
            ).fetchone()[0]
            if active_assignments:
                raise ValueError("Person kann nicht geloescht werden, solange aktive Zuweisungen bestehen.")

            self._write_audit_event(
                conn,
                entity_type="person",
                entity_id=person_id,
                action="person-deleted",
                actor=actor,
                payload={
                    "display_name": person["display_name"],
                    "email": person["email"],
                    "department": person["department"],
                },
            )
            conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
            conn.commit()

    def list_current_assets_for_person(self, person_id):
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    asset.id,
                    asset.device_type,
                    asset.asset_tag,
                    asset.model_name,
                    asset.inventory_status,
                    assignment.hostname,
                    assignment.assigned_at
                FROM asset_assignments AS assignment
                INNER JOIN managed_assets AS asset
                    ON asset.id = assignment.asset_id
                WHERE assignment.person_id = ? AND assignment.is_current = 1
                ORDER BY asset.asset_tag_normalized ASC
                """,
                (person_id,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def list_person_timeline(self, person_id):
        return self.list_audit_events(entity_type="person", entity_id=person_id)

    def create_asset(
        self,
        device_type,
        asset_tag,
        model_name,
        manufacturer="",
        inventory_status="active",
        notes="",
        source_asset_tag="",
    ):
        self._validate_device_type(device_type)
        self._validate_inventory_status(inventory_status)

        normalized_asset_tag = normalize_asset_tag(asset_tag)
        if not normalized_asset_tag:
            raise ValueError("Der Asset-Tag darf nicht leer sein.")
        if not str(model_name or "").strip():
            raise ValueError("Das Modell darf nicht leer sein.")

        with closing(self.connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO managed_assets (
                    device_type,
                    asset_tag,
                    asset_tag_normalized,
                    model_name,
                    manufacturer,
                    inventory_status,
                    notes,
                    source_asset_tag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_type,
                    str(asset_tag).strip(),
                    normalized_asset_tag,
                    str(model_name).strip(),
                    str(manufacturer or "").strip(),
                    inventory_status,
                    str(notes or "").strip(),
                    str(source_asset_tag or "").strip(),
                ),
            )
            asset_id = cursor.lastrowid
            self._write_audit_event(
                conn,
                entity_type="managed_asset",
                entity_id=asset_id,
                action="asset-created",
                actor="repository",
                payload={
                    "device_type": device_type,
                    "asset_tag": str(asset_tag).strip(),
                    "model_name": str(model_name).strip(),
                    "inventory_status": inventory_status,
                },
            )
            conn.commit()
            return self.get_asset(asset_id=asset_id)

    def update_asset(
        self,
        asset_id,
        *,
        device_type=None,
        asset_tag=None,
        model_name=None,
        manufacturer=None,
        inventory_status=None,
        notes=None,
        source_asset_tag=None,
        expected_record_version=None,
    ):
        updates = []
        values = []

        if device_type is not None:
            self._validate_device_type(device_type)
            updates.append("device_type = ?")
            values.append(device_type)
        if asset_tag is not None:
            normalized_asset_tag = normalize_asset_tag(asset_tag)
            if not normalized_asset_tag:
                raise ValueError("Der Asset-Tag darf nicht leer sein.")
            updates.append("asset_tag = ?")
            values.append(str(asset_tag).strip())
            updates.append("asset_tag_normalized = ?")
            values.append(normalized_asset_tag)
        if model_name is not None:
            if not str(model_name).strip():
                raise ValueError("Das Modell darf nicht leer sein.")
            updates.append("model_name = ?")
            values.append(str(model_name).strip())
        if manufacturer is not None:
            updates.append("manufacturer = ?")
            values.append(str(manufacturer).strip())
        if inventory_status is not None:
            self._validate_inventory_status(inventory_status)
            updates.append("inventory_status = ?")
            values.append(inventory_status)
        if notes is not None:
            updates.append("notes = ?")
            values.append(str(notes).strip())
        if source_asset_tag is not None:
            updates.append("source_asset_tag = ?")
            values.append(str(source_asset_tag).strip())

        if not updates:
            return self.get_asset(asset_id=asset_id)

        values.append(asset_id)
        if expected_record_version is not None:
            values.append(expected_record_version)

        with closing(self.connect()) as conn:
            existing_asset = conn.execute(
                """
                SELECT id, device_type
                FROM managed_assets
                WHERE id = ?
                """,
                (asset_id,),
            ).fetchone()
            if existing_asset is None:
                raise ValueError(f"Kein Asset mit ID {asset_id} gefunden.")

            cursor = conn.execute(
                f"""
                UPDATE managed_assets
                SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                WHERE id = ?
                {"AND record_version = ?" if expected_record_version is not None else ""}
                """,
                values,
            )
            if cursor.rowcount == 0:
                exists = conn.execute("SELECT id FROM managed_assets WHERE id = ?", (asset_id,)).fetchone()
                if exists is None:
                    raise ValueError(f"Kein Asset mit ID {asset_id} gefunden.")
                self._raise_conflict("Asset")

            effective_device_type = device_type if device_type is not None else existing_asset["device_type"]
            if effective_device_type == "Smartphone":
                conn.execute(
                    """
                    UPDATE asset_assignments
                    SET hostname = '',
                        hostname_normalized = '',
                        updated_at = CURRENT_TIMESTAMP,
                        record_version = record_version + 1
                    WHERE asset_id = ? AND is_current = 1
                    """,
                    (asset_id,),
                )

            self._write_audit_event(
                conn,
                entity_type="managed_asset",
                entity_id=asset_id,
                action="asset-updated",
                actor="repository",
                payload={
                    "device_type": device_type,
                    "asset_tag": str(asset_tag).strip() if asset_tag is not None else None,
                    "model_name": model_name,
                    "manufacturer": manufacturer,
                    "inventory_status": inventory_status,
                    "notes": notes,
                    "source_asset_tag": str(source_asset_tag).strip() if source_asset_tag is not None else None,
                },
            )
            conn.commit()
            return self.get_asset(asset_id=asset_id)

    def delete_asset(self, asset_id, actor="repository", expected_record_version=None):
        with closing(self.connect()) as conn:
            asset = conn.execute(
                """
                SELECT id, device_type, asset_tag, model_name, record_version
                FROM managed_assets
                WHERE id = ?
                """,
                (asset_id,),
            ).fetchone()
            if asset is None:
                raise ValueError(f"Kein Asset mit ID {asset_id} gefunden.")
            if expected_record_version is not None and asset["record_version"] != expected_record_version:
                self._raise_conflict("Asset")

            self._write_audit_event(
                conn,
                entity_type="managed_asset",
                entity_id=asset_id,
                action="asset-deleted",
                actor=actor,
                payload={
                    "device_type": asset["device_type"],
                    "asset_tag": asset["asset_tag"],
                    "model_name": asset["model_name"],
                },
            )
            conn.execute("DELETE FROM managed_assets WHERE id = ?", (asset_id,))
            conn.commit()

    def get_asset(self, *, asset_id=None, asset_tag=None):
        if asset_id is None and asset_tag is None:
            raise ValueError("Es muss asset_id oder asset_tag uebergeben werden.")

        sql = """
            SELECT
                id,
                device_type,
                asset_tag,
                asset_tag_normalized,
                model_name,
                manufacturer,
                inventory_status,
                notes,
                source_asset_tag,
                created_at,
                updated_at,
                record_version
            FROM managed_assets
        """
        params = ()
        if asset_id is not None:
            sql += " WHERE id = ?"
            params = (asset_id,)
        else:
            sql += " WHERE asset_tag_normalized = ?"
            params = (normalize_asset_tag(asset_tag),)

        with closing(self.connect()) as conn:
            row = conn.execute(sql, params).fetchone()
            return self._row_to_dict(row)

    def list_assets(self, inventory_status=None):
        sql = """
            SELECT
                id,
                device_type,
                asset_tag,
                asset_tag_normalized,
                model_name,
                manufacturer,
                inventory_status,
                notes,
                source_asset_tag,
                created_at,
                updated_at,
                record_version
            FROM managed_assets
        """
        params = []
        if inventory_status:
            self._validate_inventory_status(inventory_status)
            sql += " WHERE inventory_status = ?"
            params.append(inventory_status)
        sql += " ORDER BY asset_tag_normalized ASC"

        with closing(self.connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def assign_asset(
        self,
        *,
        asset_id,
        person_id=None,
        hostname="",
        assignment_status="active",
        notes="",
        actor="repository",
    ):
        self._validate_assignment_status(assignment_status)
        asset = self.get_asset(asset_id=asset_id)
        if not asset:
            raise ValueError(f"Kein Asset mit ID {asset_id} gefunden.")

        normalized_hostname = self._normalize_hostname_for_asset(asset["device_type"], hostname)

        with closing(self.connect()) as conn:
            if person_id is not None:
                person = conn.execute("SELECT id FROM people WHERE id = ?", (person_id,)).fetchone()
                if person is None:
                    raise ValueError(f"Keine Person mit ID {person_id} gefunden.")

            current_assignment = conn.execute(
                """
                SELECT id
                FROM asset_assignments
                WHERE asset_id = ? AND is_current = 1
                """,
                (asset_id,),
            ).fetchone()
            if current_assignment:
                conn.execute(
                    """
                    UPDATE asset_assignments
                    SET is_current = 0,
                        assignment_status = 'returned',
                        returned_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = ?
                    WHERE id = ?
                    """,
                    (actor, current_assignment["id"]),
                )

            cursor = conn.execute(
                """
                INSERT INTO asset_assignments (
                    asset_id,
                    person_id,
                    hostname,
                    hostname_normalized,
                    assignment_status,
                    notes,
                    created_by,
                    updated_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    person_id,
                    normalized_hostname,
                    normalized_hostname.casefold(),
                    assignment_status,
                    str(notes or "").strip(),
                    actor,
                    actor,
                ),
            )
            assignment_id = cursor.lastrowid
            conn.execute(
                """
                UPDATE managed_assets
                SET updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                WHERE id = ?
                """,
                (asset_id,),
            )
            self._write_audit_event(
                conn,
                entity_type="asset_assignment",
                entity_id=assignment_id,
                action="assignment-created",
                actor=actor,
                payload={
                    "asset_id": asset_id,
                    "person_id": person_id,
                    "hostname": normalized_hostname,
                    "assignment_status": assignment_status,
                },
            )
            conn.commit()
            return self.get_assignment(assignment_id)

    def update_current_assignment(
        self,
        asset_id,
        *,
        person_id=None,
        hostname=None,
        notes=None,
        actor="repository",
        expected_record_version=None,
    ):
        with closing(self.connect()) as conn:
            current_assignment = conn.execute(
                """
                SELECT assignment.id, assignment.person_id, assignment.hostname, assignment.notes, assignment.record_version, asset.device_type
                FROM asset_assignments AS assignment
                INNER JOIN managed_assets AS asset
                    ON asset.id = assignment.asset_id
                WHERE assignment.asset_id = ? AND assignment.is_current = 1
                """,
                (asset_id,),
            ).fetchone()
            if current_assignment is None:
                raise ValueError(f"Kein aktiver Einsatz fuer Asset {asset_id} gefunden.")

            updates = []
            values = []

            if person_id is not None:
                person = conn.execute("SELECT id FROM people WHERE id = ?", (person_id,)).fetchone()
                if person is None:
                    raise ValueError(f"Keine Person mit ID {person_id} gefunden.")
                updates.append("person_id = ?")
                values.append(person_id)

            if hostname is not None:
                normalized_hostname = self._normalize_hostname_for_asset(current_assignment["device_type"], hostname)
                updates.append("hostname = ?")
                values.append(normalized_hostname)
                updates.append("hostname_normalized = ?")
                values.append(normalized_hostname.casefold())

            if notes is not None:
                updates.append("notes = ?")
                values.append(str(notes).strip())

            if not updates:
                return self.get_assignment(current_assignment["id"])

            values.extend([actor, current_assignment["id"]])
            if expected_record_version is not None:
                values.append(expected_record_version)
            cursor = conn.execute(
                f"""
                UPDATE asset_assignments
                SET {", ".join(updates)},
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = ?,
                    record_version = record_version + 1
                WHERE id = ?
                {"AND record_version = ?" if expected_record_version is not None else ""}
                """,
                values,
            )
            if cursor.rowcount == 0:
                self._raise_conflict("Zuweisung")
            conn.execute(
                """
                UPDATE managed_assets
                SET updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                WHERE id = ?
                """,
                (asset_id,),
            )
            self._write_audit_event(
                conn,
                entity_type="asset_assignment",
                entity_id=current_assignment["id"],
                action="assignment-updated",
                actor=actor,
                payload={
                    "person_id": person_id,
                    "hostname": hostname,
                    "notes": notes,
                },
            )
            conn.commit()
            return self.get_assignment(current_assignment["id"])

    def return_asset(self, asset_id, actor="repository", notes="", expected_record_version=None):
        with closing(self.connect()) as conn:
            current_assignment = conn.execute(
                """
                SELECT id, record_version
                FROM asset_assignments
                WHERE asset_id = ? AND is_current = 1
                """,
                (asset_id,),
            ).fetchone()
            if current_assignment is None:
                raise ValueError(f"Kein aktiver Einsatz fuer Asset {asset_id} gefunden.")
            if expected_record_version is not None and current_assignment["record_version"] != expected_record_version:
                self._raise_conflict("Zuweisung")

            conn.execute(
                """
                UPDATE asset_assignments
                SET is_current = 0,
                    assignment_status = 'returned',
                    returned_at = CURRENT_TIMESTAMP,
                    notes = CASE
                        WHEN ? = '' THEN notes
                        WHEN notes = '' THEN ?
                        ELSE notes || ' | ' || ?
                    END,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = ?
                WHERE id = ?
                """,
                (str(notes).strip(), str(notes).strip(), str(notes).strip(), actor, current_assignment["id"]),
            )
            conn.execute(
                """
                UPDATE managed_assets
                SET updated_at = CURRENT_TIMESTAMP, record_version = record_version + 1
                WHERE id = ?
                """,
                (asset_id,),
            )
            self._write_audit_event(
                conn,
                entity_type="managed_asset",
                entity_id=asset_id,
                action="assignment-returned",
                actor=actor,
                payload={"notes": str(notes).strip()},
            )
            conn.commit()
            return self.get_assignment(current_assignment["id"])

    def get_assignment(self, assignment_id):
        with closing(self.connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    person_id,
                    hostname,
                    hostname_normalized,
                    assignment_status,
                    assigned_at,
                    returned_at,
                    is_current,
                    notes,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at,
                    record_version
                FROM asset_assignments
                WHERE id = ?
                """,
                (assignment_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def get_current_assignment_for_asset(self, asset_id):
        with closing(self.connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    person_id,
                    hostname,
                    hostname_normalized,
                    assignment_status,
                    assigned_at,
                    returned_at,
                    is_current,
                    notes,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at,
                    record_version
                FROM asset_assignments
                WHERE asset_id = ? AND is_current = 1
                """,
                (asset_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def list_asset_snapshots(self):
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    asset.id,
                    asset.device_type,
                    asset.asset_tag,
                    asset.model_name,
                    asset.manufacturer,
                    asset.inventory_status,
                    asset.notes,
                    asset.updated_at,
                    person.display_name AS assigned_to,
                    assignment.hostname,
                    assignment.assignment_status,
                    assignment.is_current
                FROM managed_assets AS asset
                LEFT JOIN asset_assignments AS assignment
                    ON assignment.asset_id = asset.id AND assignment.is_current = 1
                LEFT JOIN people AS person
                    ON person.id = assignment.person_id
                ORDER BY asset.asset_tag_normalized ASC
                """
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def list_assignments_for_asset(self, asset_id):
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    person_id,
                    hostname,
                    hostname_normalized,
                    assignment_status,
                    assigned_at,
                    returned_at,
                    is_current,
                    notes,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at,
                    record_version
                FROM asset_assignments
                WHERE asset_id = ?
                ORDER BY assigned_at DESC, id DESC
                """,
                (asset_id,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def list_audit_events(self, entity_type=None, entity_id=None):
        sql = """
            SELECT id, entity_type, entity_id, action, actor, payload_json, created_at
            FROM audit_events
            WHERE 1 = 1
        """
        params = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id is not None:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        sql += " ORDER BY created_at DESC, id DESC"

        with closing(self.connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def list_timeline_for_asset(self, asset_id):
        asset_events = self.list_audit_events(entity_type="managed_asset", entity_id=asset_id)
        assignment_ids = [item["id"] for item in self.list_assignments_for_asset(asset_id)]
        assignment_events = []
        for assignment_id in assignment_ids:
            assignment_events.extend(
                self.list_audit_events(entity_type="asset_assignment", entity_id=assignment_id)
            )
        events = asset_events + assignment_events
        return sorted(events, key=lambda item: (item["created_at"], item["id"]), reverse=True)

    def _write_audit_event(self, conn, *, entity_type, entity_id, action, actor, payload):
        conn.execute(
            """
            INSERT INTO audit_events (entity_type, entity_id, action, actor, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, action, actor, json.dumps(payload, ensure_ascii=True, sort_keys=True)),
        )

    def _validate_device_type(self, device_type):
        if device_type not in DEVICE_TYPE_VALUES:
            raise ValueError(f"Unbekannter Geraetetyp: {device_type}")

    def _validate_inventory_status(self, inventory_status):
        if inventory_status not in INVENTORY_STATUS_VALUES:
            raise ValueError(f"Unbekannter Inventarstatus: {inventory_status}")

    def _validate_assignment_status(self, assignment_status):
        if assignment_status not in ASSIGNMENT_STATUS_VALUES:
            raise ValueError(f"Unbekannter Zuweisungsstatus: {assignment_status}")

    def _normalize_hostname_for_asset(self, device_type, hostname):
        hostname = str(hostname or "").strip()
        if device_type == "Smartphone":
            return ""
        return hostname

    def _row_to_dict(self, row):
        return dict(row) if row is not None else None
