import json
import sqlite3
from contextlib import closing
from pathlib import Path


SCHEMA_VERSION = 5

DEVICE_TYPE_VALUES = ("Smartphone", "Notebook")
INVENTORY_STATUS_VALUES = ("active", "inactive", "retired")
ASSIGNMENT_STATUS_VALUES = ("active", "returned")


def ensure_database(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema_version_table(conn)
        _apply_pending_migrations(conn)
        conn.commit()


def get_schema_version(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema_version_table(conn)
        row = conn.execute("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1").fetchone()
        return row["version"] if row else 0


def _ensure_schema_version_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """
    )
    row = conn.execute("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")


def _set_schema_version(conn, version):
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def _apply_pending_migrations(conn):
    current_version = get_current_version(conn)
    current_version = normalize_bootstrap_version(conn, current_version)
    migrations = {
        1: migration_001_create_v2_core_schema,
        2: migration_002_add_assignment_indexes,
        3: migration_003_import_legacy_assets,
        4: migration_004_add_people_record_version,
        5: migration_005_add_edit_claims,
    }
    for version in range(current_version + 1, SCHEMA_VERSION + 1):
        migration = migrations[version]
        migration(conn)
        _set_schema_version(conn, version)


def get_current_version(conn):
    row = conn.execute("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1").fetchone()
    return row["version"] if row else 0


def normalize_bootstrap_version(conn, current_version):
    if current_version != 1:
        return current_version
    required_tables = {"people", "managed_assets", "asset_assignments", "audit_events"}
    existing_tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if required_tables.issubset(existing_tables):
        return current_version
    _set_schema_version(conn, 0)
    return 0


def migration_001_create_v2_core_schema(conn):
    allowed_types = ", ".join(f"'{value}'" for value in DEVICE_TYPE_VALUES)
    inventory_statuses = ", ".join(f"'{value}'" for value in INVENTORY_STATUS_VALUES)
    assignment_statuses = ", ".join(f"'{value}'" for value in ASSIGNMENT_STATUS_VALUES)

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS people (
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
        f"""
        CREATE TABLE IF NOT EXISTS managed_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT NOT NULL CHECK(device_type IN ({allowed_types})),
            asset_tag TEXT NOT NULL,
            asset_tag_normalized TEXT NOT NULL UNIQUE,
            model_name TEXT NOT NULL,
            manufacturer TEXT NOT NULL DEFAULT '',
            inventory_status TEXT NOT NULL DEFAULT 'active'
                CHECK(inventory_status IN ({inventory_statuses})),
            notes TEXT NOT NULL DEFAULT '',
            source_asset_tag TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            record_version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS asset_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            person_id INTEGER,
            hostname TEXT NOT NULL DEFAULT '',
            hostname_normalized TEXT NOT NULL DEFAULT '',
            assignment_status TEXT NOT NULL DEFAULT 'active'
                CHECK(assignment_status IN ({assignment_statuses})),
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            returned_at TEXT,
            is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
            notes TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            record_version INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (asset_id) REFERENCES managed_assets(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
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


def migration_002_add_assignment_indexes(conn):
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_managed_assets_asset_tag_normalized
        ON managed_assets(asset_tag_normalized)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_assignments_current_asset
        ON asset_assignments(asset_id)
        WHERE is_current = 1
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_assignments_current_hostname
        ON asset_assignments(hostname_normalized)
        WHERE is_current = 1 AND hostname_normalized <> ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_assignments_person
        ON asset_assignments(person_id, is_current)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_entity
        ON audit_events(entity_type, entity_id, created_at DESC)
        """
    )


def migration_003_import_legacy_assets(conn):
    if not _legacy_assets_table_exists(conn):
        return
    if conn.execute("SELECT COUNT(*) FROM managed_assets").fetchone()[0] > 0:
        return

    legacy_rows = conn.execute(
        """
        SELECT type, user_name, asset_tag, model, extra_info, status
        FROM assets
        ORDER BY id ASC
        """
    ).fetchall()

    for row in legacy_rows:
        asset_id = _insert_managed_asset_from_legacy(conn, row)
        person_id = _find_or_create_person(conn, row["user_name"])
        hostname = _normalize_legacy_hostname(row["type"], row["extra_info"])
        conn.execute(
            """
            INSERT INTO asset_assignments (
                asset_id,
                person_id,
                hostname,
                hostname_normalized,
                assignment_status,
                assigned_at,
                is_current,
                notes,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, 1, ?, 'legacy-migration', 'legacy-migration')
            """,
            (
                asset_id,
                person_id,
                hostname,
                hostname.casefold(),
                "Automatisch aus dem Altbestand migriert.",
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_events (entity_type, entity_id, action, actor, payload_json)
            VALUES ('managed_asset', ?, 'legacy-import', 'migration', ?)
            """,
            (
                asset_id,
                json.dumps(
                    {
                        "legacy_type": row["type"],
                        "legacy_asset_tag": row["asset_tag"],
                        "legacy_status": row["status"],
                    },
                    ensure_ascii=True,
                ),
            ),
        )


def migration_004_add_people_record_version(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)").fetchall()}
    if "record_version" not in columns:
        conn.execute(
            """
            ALTER TABLE people
            ADD COLUMN record_version INTEGER NOT NULL DEFAULT 1
            """
        )


def migration_005_add_edit_claims(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edit_claims (
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            editor_id TEXT NOT NULL,
            editor_label TEXT NOT NULL DEFAULT '',
            claimed_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_edit_claims_expires_at
        ON edit_claims(expires_at)
        """
    )


def _legacy_assets_table_exists(conn):
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'assets'
        """
    ).fetchone()
    if row is None:
        return False

    columns = {item["name"] for item in conn.execute("PRAGMA table_info(assets)").fetchall()}
    required_columns = {"type", "user_name", "asset_tag", "model", "extra_info", "status"}
    return required_columns.issubset(columns)


def _insert_managed_asset_from_legacy(conn, row):
    normalized_tag = normalize_asset_tag(row["asset_tag"])
    conn.execute(
        """
        INSERT INTO managed_assets (
            device_type,
            asset_tag,
            asset_tag_normalized,
            model_name,
            inventory_status,
            source_asset_tag,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["type"],
            str(row["asset_tag"]).strip(),
            normalized_tag,
            str(row["model"]).strip(),
            map_legacy_status(row["status"]),
            str(row["asset_tag"]).strip(),
            "Aus v1-Bestand uebernommen.",
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _find_or_create_person(conn, display_name):
    normalized_name = normalize_person_name(display_name)
    if not normalized_name:
        return None

    existing = conn.execute(
        """
        SELECT id
        FROM people
        WHERE display_name_normalized = ?
        """,
        (normalized_name,),
    ).fetchone()
    if existing:
        return existing["id"]

    conn.execute(
        """
        INSERT INTO people (display_name, display_name_normalized)
        VALUES (?, ?)
        """,
        (str(display_name).strip(), normalized_name),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def normalize_asset_tag(value):
    return str(value or "").strip().upper()


def normalize_person_name(value):
    return " ".join(str(value or "").strip().casefold().split())


def _normalize_legacy_hostname(device_type, extra_info):
    if device_type != "Notebook":
        return ""
    return str(extra_info or "").strip()


def map_legacy_status(value):
    text = str(value or "").strip().casefold()
    if text == "inaktiv":
        return "inactive"
    return "active"
