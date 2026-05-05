from __future__ import annotations

import json
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = BASE_DIR / "config.json"


DEFAULT_CONFIG = {
    "app_name": "Device Management v2",
    "database_path": "data/device_management_v2.db",
    "auto_refresh_seconds": 15,
    "theme": "Light",
}


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else CONFIG_PATH
    if not path.exists():
        return DEFAULT_CONFIG.copy()

    with path.open("r", encoding="utf-8-sig") as handle:
        raw_data = json.load(handle)

    config = DEFAULT_CONFIG.copy()
    config.update(raw_data)
    return config


def save_config(config: dict, config_path: str | Path | None = None) -> Path:
    path = Path(config_path) if config_path else CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    merged_config = DEFAULT_CONFIG.copy()
    merged_config.update(config)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(merged_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def normalize_database_path_for_config(db_path: str | Path) -> str:
    path = Path(db_path).expanduser()
    if not path.is_absolute():
        return path.as_posix()

    try:
        relative_path = path.resolve().relative_to(BASE_DIR.resolve())
    except ValueError:
        return str(path)
    return relative_path.as_posix()


def resolve_database_path(config: dict) -> Path:
    db_path = Path(config["database_path"])
    if db_path.is_absolute():
        return db_path
    return (BASE_DIR / db_path).resolve()
