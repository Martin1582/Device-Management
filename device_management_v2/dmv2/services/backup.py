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


def restore_database_backup(backup_path, database_path, safety_backup_path):
    backup = Path(backup_path)
    database = Path(database_path)
    safety_backup = Path(safety_backup_path)
    if not backup.exists():
        raise FileNotFoundError(f"Backup-Datei nicht gefunden: {backup}")
    if not database.exists():
        raise FileNotFoundError(f"Aktive Datenbank nicht gefunden: {database}")
    if backup.resolve() == database.resolve():
        raise ValueError("Restore-Quelle darf nicht die aktive Datenbankdatei sein.")
    if safety_backup.resolve() == database.resolve():
        raise ValueError("Sicherheitsbackup darf nicht die aktive Datenbankdatei sein.")
    safety_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database, safety_backup)
    shutil.copy2(backup, database)
    return safety_backup


def build_backup_filename(prefix="DeviceManagementV2_Backup"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{prefix}_{timestamp}.db"


def build_restore_safety_backup_filename(prefix="DeviceManagementV2_PreRestore"):
    return build_backup_filename(prefix=prefix)
