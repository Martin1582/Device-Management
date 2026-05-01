import shutil
from datetime import datetime
from pathlib import Path


def create_database_backup(source_path, destination_path):
    source = Path(source_path)
    destination = Path(destination_path)
    if not source.exists():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Backup-Ziel darf nicht die aktive Datenbankdatei sein.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def build_backup_filename(prefix="DeviceManagementV2_Backup"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{prefix}_{timestamp}.db"
