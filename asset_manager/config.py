import json
from pathlib import Path


DEFAULT_CONFIG = {
    "database_path": "it_assets.db",
    "auto_refresh_seconds": 15,
}


def get_project_root():
    return Path(__file__).resolve().parent.parent


def get_config_path():
    return get_project_root() / "config.json"


def load_config():
    config_path = get_config_path()
    if not config_path.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with config_path.open("r", encoding="utf-8") as file_handle:
        loaded = json.load(file_handle)

    config = DEFAULT_CONFIG.copy()
    config.update(loaded)
    return config


def save_config(config):
    config_path = get_config_path()
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    with config_path.open("w", encoding="utf-8") as file_handle:
        json.dump(merged, file_handle, indent=2, ensure_ascii=False)


def resolve_database_path(config):
    db_path = Path(config["database_path"])
    if not db_path.is_absolute():
        db_path = get_project_root() / db_path
    return db_path
