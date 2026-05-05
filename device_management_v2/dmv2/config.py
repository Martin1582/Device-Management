import json
import sys
from pathlib import Path


def get_base_dir():
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


def load_config(config_path=None):
    path = Path(config_path) if config_path else CONFIG_PATH
    if not path.exists():
        return DEFAULT_CONFIG.copy()

    with path.open("r", encoding="utf-8-sig") as handle:
        raw_data = json.load(handle)

    config = DEFAULT_CONFIG.copy()
    config.update(raw_data)
    return config


def resolve_database_path(config):
    db_path = Path(config["database_path"])
    if db_path.is_absolute():
        return db_path
    return (BASE_DIR / db_path).resolve()
