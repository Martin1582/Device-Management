import sqlite3
from contextlib import closing
from pathlib import Path

from .config import load_config, resolve_database_path
from .constants import DEVICE_TYPES, STATUS_ACTIVE, STATUS_INACTIVE
from .services import normalize_asset_tag, normalize_extra_info


SORT_FIELDS = {
    "user_name": "user_name COLLATE NOCASE ASC",
    "model": "model COLLATE NOCASE ASC",
    "asset_tag": "asset_tag COLLATE NOCASE ASC",
    "updated_at": "updated_at DESC",
    "status": "status ASC, user_name COLLATE NOCASE ASC",
}


class DatabaseManager:
    def __init__(self, db_path="it_assets.db"):
        config = load_config()
        configured_path = resolve_database_path(config)
        self.db_path = Path(db_path) if db_path != "it_assets.db" else configured_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def init_db(self):
        allowed_types = ", ".join(f"'{device_type}'" for device_type in DEVICE_TYPES)
        with closing(self.connect()) as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK(type IN ({allowed_types})),
                    user_name TEXT NOT NULL,
                    asset_tag TEXT NOT NULL UNIQUE,
                    model TEXT NOT NULL,
                    extra_info TEXT DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '{STATUS_ACTIVE}'
                        CHECK(status IN ('{STATUS_ACTIVE}', '{STATUS_INACTIVE}'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_tag TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
            if "updated_at" not in columns:
                conn.execute(
                    "ALTER TABLE assets ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "updated_by" not in columns:
                conn.execute(
                    "ALTER TABLE assets ADD COLUMN updated_by TEXT NOT NULL DEFAULT ''"
                )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_asset_tag_normalized
                ON assets (UPPER(TRIM(asset_tag)))
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_type_extra_info_normalized
                ON assets (type, UPPER(TRIM(extra_info)))
                WHERE TRIM(extra_info) <> ''
                """
            )
            conn.commit()

    def fetch_assets(
        self,
        device_type=None,
        query="",
        status_filter=None,
        sort_by="status",
        model_filter=None,
        incomplete_only=False,
    ):
        sql = """
            SELECT id, type, user_name, model, asset_tag, extra_info, status, updated_at, updated_by
            FROM assets
            WHERE 1 = 1
        """
        params = []

        if device_type:
            sql += " AND type = ?"
            params.append(device_type)
        if status_filter in {STATUS_ACTIVE, STATUS_INACTIVE}:
            sql += " AND status = ?"
            params.append(status_filter)
        if query:
            sql += """
                AND (
                    user_name LIKE ?
                    OR asset_tag LIKE ?
                    OR model LIKE ?
                    OR extra_info LIKE ?
                    OR type LIKE ?
                )
            """
            wildcard_query = f"%{query}%"
            params.extend([wildcard_query] * 5)
        if model_filter:
            sql += " AND model = ?"
            params.append(model_filter)
        if incomplete_only:
            sql += " AND type = 'Notebook' AND TRIM(extra_info) = ''"

        order_by = SORT_FIELDS.get(sort_by, SORT_FIELDS["status"])
        sql += f" ORDER BY {order_by}"

        with closing(self.connect()) as conn:
            return conn.execute(sql, params).fetchall()

    def fetch_asset_by_tag(self, asset_tag):
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        with closing(self.connect()) as conn:
            return conn.execute(
                """
                SELECT id, type, user_name, asset_tag, model, extra_info, status, updated_at, updated_by
                FROM assets
                WHERE UPPER(TRIM(asset_tag)) = ?
                """,
                (normalized_asset_tag,),
            ).fetchone()

    def fetch_last_updated_at(self):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT MAX(updated_at) AS updated_at FROM assets").fetchone()
            return row["updated_at"] if row and row["updated_at"] else None

    def fetch_counts_by_type(self):
        counts = {device_type: {STATUS_ACTIVE: 0, STATUS_INACTIVE: 0} for device_type in DEVICE_TYPES}
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT type, status, COUNT(*) AS total
                FROM assets
                GROUP BY type, status
                """
            ).fetchall()
        for row in rows:
            counts[row["type"]][row["status"]] = row["total"]
        return counts

    def fetch_distinct_models(self, device_type=None):
        sql = "SELECT DISTINCT model FROM assets WHERE TRIM(model) <> ''"
        params = []
        if device_type:
            sql += " AND type = ?"
            params.append(device_type)
        sql += " ORDER BY model COLLATE NOCASE ASC"
        with closing(self.connect()) as conn:
            return [row["model"] for row in conn.execute(sql, params).fetchall()]

    def fetch_history(self, asset_tag=None, limit=100):
        sql = """
            SELECT asset_tag, action, actor, payload, created_at
            FROM asset_history
            WHERE 1 = 1
        """
        params = []
        if asset_tag:
            sql += " AND UPPER(TRIM(asset_tag)) = ?"
            params.append(normalize_asset_tag(asset_tag))
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with closing(self.connect()) as conn:
            return conn.execute(sql, params).fetchall()

    def create_asset(self, device_type, user_name, model, asset_tag, extra_info, actor=""):
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        normalized_extra_info = self._normalize_extra_info_for_type(device_type, extra_info)
        with closing(self.connect()) as conn:
            conn.execute(
                f"""
                INSERT INTO assets (type, user_name, model, asset_tag, extra_info, status, updated_by)
                VALUES (?, ?, ?, ?, ?, '{STATUS_ACTIVE}', ?)
                """,
                (
                    device_type,
                    user_name.strip(),
                    model.strip(),
                    normalized_asset_tag,
                    normalized_extra_info,
                    actor,
                ),
            )
            self._log_history(
                conn,
                normalized_asset_tag,
                "created",
                actor,
                {
                    "type": device_type,
                    "user_name": user_name.strip(),
                    "model": model.strip(),
                    "extra_info": normalized_extra_info,
                    "status": STATUS_ACTIVE,
                },
            )
            conn.commit()

    def upsert_asset(self, device_type, user_name, model, asset_tag, extra_info, status=STATUS_ACTIVE, actor="Import"):
        normalized_status = status if status in {STATUS_ACTIVE, STATUS_INACTIVE} else STATUS_ACTIVE
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        normalized_extra_info = self._normalize_extra_info_for_type(device_type, extra_info)
        with closing(self.connect()) as conn:
            existing_asset = conn.execute(
                "SELECT asset_tag FROM assets WHERE UPPER(TRIM(asset_tag)) = ?",
                (normalized_asset_tag,),
            ).fetchone()

            if existing_asset:
                conn.execute(
                    """
                    UPDATE assets
                    SET type = ?, user_name = ?, model = ?, extra_info = ?, status = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                    WHERE UPPER(TRIM(asset_tag)) = ?
                    """,
                    (
                        device_type,
                        user_name.strip(),
                        model.strip(),
                        normalized_extra_info,
                        normalized_status,
                        actor,
                        normalized_asset_tag,
                    ),
                )
                self._log_history(
                    conn,
                    normalized_asset_tag,
                    "import-updated",
                    actor,
                    {
                        "type": device_type,
                        "user_name": user_name.strip(),
                        "model": model.strip(),
                        "extra_info": normalized_extra_info,
                        "status": normalized_status,
                    },
                )
                conn.commit()
                return "updated"

            conn.execute(
                """
                INSERT INTO assets (type, user_name, model, asset_tag, extra_info, status, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_type,
                    user_name.strip(),
                    model.strip(),
                    normalized_asset_tag,
                    normalized_extra_info,
                    normalized_status,
                    actor,
                ),
            )
            self._log_history(
                conn,
                normalized_asset_tag,
                "import-created",
                actor,
                {
                    "type": device_type,
                    "user_name": user_name.strip(),
                    "model": model.strip(),
                    "extra_info": normalized_extra_info,
                    "status": normalized_status,
                },
            )
            conn.commit()
            return "created"

    def update_asset(self, original_asset_tag, device_type, user_name, model, asset_tag, extra_info, actor=""):
        normalized_original_asset_tag = normalize_asset_tag(original_asset_tag)
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        normalized_extra_info = self._normalize_extra_info_for_type(device_type, extra_info)
        with closing(self.connect()) as conn:
            cursor = conn.execute(
                f"""
                UPDATE assets
                SET type = ?, user_name = ?, model = ?, asset_tag = ?, extra_info = ?, status = '{STATUS_ACTIVE}', updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE UPPER(TRIM(asset_tag)) = ?
                """,
                (
                    device_type,
                    user_name.strip(),
                    model.strip(),
                    normalized_asset_tag,
                    normalized_extra_info,
                    actor,
                    normalized_original_asset_tag,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Kein Gerät mit Asset-Tag '{original_asset_tag}' gefunden.")
            self._log_history(
                conn,
                normalized_asset_tag,
                "updated",
                actor,
                {
                    "from_asset_tag": normalized_original_asset_tag,
                    "type": device_type,
                    "user_name": user_name.strip(),
                    "model": model.strip(),
                    "extra_info": normalized_extra_info,
                },
            )
            conn.commit()

    def deactivate_asset(self, asset_tag, actor=""):
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        with closing(self.connect()) as conn:
            cursor = conn.execute(
                f"UPDATE assets SET status = '{STATUS_INACTIVE}', updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE UPPER(TRIM(asset_tag)) = ?",
                (actor, normalized_asset_tag),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Kein Gerät mit Asset-Tag '{asset_tag}' gefunden.")
            self._log_history(conn, normalized_asset_tag, "deactivated", actor, {})
            conn.commit()

    def delete_asset(self, asset_tag, actor=""):
        normalized_asset_tag = normalize_asset_tag(asset_tag)
        with closing(self.connect()) as conn:
            asset = conn.execute(
                """
                SELECT type, user_name, model, extra_info, status
                FROM assets
                WHERE UPPER(TRIM(asset_tag)) = ?
                """,
                (normalized_asset_tag,),
            ).fetchone()
            cursor = conn.execute(
                "DELETE FROM assets WHERE UPPER(TRIM(asset_tag)) = ?",
                (normalized_asset_tag,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Kein Gerät mit Asset-Tag '{asset_tag}' gefunden.")
            self._log_history(
                conn,
                normalized_asset_tag,
                "deleted",
                actor,
                dict(asset) if asset else {},
            )
            conn.commit()

    def export_assets(
        self,
        device_type=None,
        query="",
        status_filter=None,
        sort_by="status",
        model_filter=None,
        incomplete_only=False,
    ):
        return self.fetch_assets(device_type, query, status_filter, sort_by, model_filter, incomplete_only)

    def _normalize_extra_info_for_type(self, device_type, extra_info):
        if device_type == "Smartphone":
            return ""
        return normalize_extra_info(extra_info)

    def _log_history(self, conn, asset_tag, action, actor, payload):
        conn.execute(
            """
            INSERT INTO asset_history (asset_tag, action, actor, payload)
            VALUES (?, ?, ?, ?)
            """,
            (asset_tag, action, actor, str(payload)),
        )
