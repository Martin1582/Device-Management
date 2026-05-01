import tempfile
import unittest
from pathlib import Path

from dmv2.services.backup import build_backup_filename, create_database_backup


class BackupServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_database_backup_copies_source_file(self):
        source = self.root / "source.db"
        destination = self.root / "backups" / "backup.db"
        source.write_bytes(b"sqlite-data")

        created = create_database_backup(source, destination)

        self.assertEqual(created, destination)
        self.assertEqual(destination.read_bytes(), b"sqlite-data")

    def test_create_database_backup_rejects_same_source_and_destination(self):
        source = self.root / "source.db"
        source.write_bytes(b"sqlite-data")

        with self.assertRaises(ValueError):
            create_database_backup(source, source)

    def test_create_database_backup_fails_for_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            create_database_backup(self.root / "missing.db", self.root / "backup.db")

    def test_build_backup_filename_uses_db_extension(self):
        filename = build_backup_filename()

        self.assertTrue(filename.startswith("DeviceManagementV2_Backup_"))
        self.assertTrue(filename.endswith(".db"))


if __name__ == "__main__":
    unittest.main()
