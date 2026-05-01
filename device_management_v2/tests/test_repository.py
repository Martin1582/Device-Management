import gc
import sqlite3
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from dmv2.db.repository import ConflictError, DatabaseRepository, EditClaimError


class RepositoryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "repository.db"
        self.repository = DatabaseRepository(self.db_path)

    def tearDown(self):
        self.repository = None
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_or_update_person_reuses_normalized_name(self):
        created = self.repository.create_or_update_person("Max Mustermann", email="max@example.org")
        updated = self.repository.create_or_update_person("  max   mustermann  ", department="IT")

        people = self.repository.list_people()

        self.assertEqual(created["id"], updated["id"])
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["department"], "IT")

    def test_update_person_changes_master_data(self):
        person = self.repository.create_or_update_person("Anna Alt", email="alt@example.org", department="Sales")

        updated = self.repository.update_person(
            person["id"],
            display_name="Anna Neu",
            email="neu@example.org",
            department="IT",
        )

        self.assertEqual(updated["display_name"], "Anna Neu")
        self.assertEqual(updated["email"], "neu@example.org")
        self.assertEqual(updated["department"], "IT")

    def test_update_person_detects_record_version_conflict(self):
        person = self.repository.create_or_update_person("Version User", email="one@example.org")

        self.repository.update_person(person["id"], email="two@example.org", expected_record_version=person["record_version"])

        with self.assertRaises(ConflictError):
            self.repository.update_person(
                person["id"],
                department="Ops",
                expected_record_version=person["record_version"],
            )

    def test_delete_person_fails_with_active_assignment(self):
        person = self.repository.create_or_update_person("Blocked User")
        asset = self.repository.create_asset("Notebook", "NB-PER-1", "Dell 5500")
        self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-BLOCK")

        with self.assertRaises(ValueError):
            self.repository.delete_person(person["id"])

    def test_delete_person_succeeds_without_active_assignment(self):
        person = self.repository.create_or_update_person("Cleanup User")

        self.repository.delete_person(person["id"], actor="test-delete")

        self.assertIsNone(self.repository.get_person(person["id"]))

    def test_create_asset_and_lookup_by_asset_tag(self):
        created = self.repository.create_asset(
            "Notebook",
            "nb-001",
            "Dell Latitude 7450",
            manufacturer="Dell",
            notes="Pilotgeraet",
        )

        fetched = self.repository.get_asset(asset_tag=" NB-001 ")

        self.assertEqual(created["id"], fetched["id"])
        self.assertEqual(fetched["asset_tag_normalized"], "NB-001")
        self.assertEqual(fetched["manufacturer"], "Dell")

    def test_update_asset_can_change_identifier_type_and_source(self):
        asset = self.repository.create_asset("Notebook", "NB-009", "Dell 5400", source_asset_tag="ALT-1")
        self.repository.assign_asset(asset_id=asset["id"], hostname="LT-OLD")

        updated = self.repository.update_asset(
            asset["id"],
            device_type="Smartphone",
            asset_tag="PH-009",
            model_name="iPhone 15",
            inventory_status="inactive",
            source_asset_tag="IMEI-NEW",
        )
        assignment = self.repository.get_current_assignment_for_asset(asset["id"])

        self.assertEqual(updated["device_type"], "Smartphone")
        self.assertEqual(updated["asset_tag"], "PH-009")
        self.assertEqual(updated["inventory_status"], "inactive")
        self.assertEqual(updated["source_asset_tag"], "IMEI-NEW")
        self.assertEqual(assignment["hostname"], "")

    def test_update_asset_detects_record_version_conflict(self):
        asset = self.repository.create_asset("Notebook", "NB-CONFLICT", "Dell 5430")

        self.repository.update_asset(
            asset["id"],
            model_name="Dell 5440",
            expected_record_version=asset["record_version"],
        )

        with self.assertRaises(ConflictError):
            self.repository.update_asset(
                asset["id"],
                notes="Spaete Aenderung",
                expected_record_version=asset["record_version"],
            )

    def test_assign_asset_creates_current_assignment_snapshot(self):
        person = self.repository.create_or_update_person("Anna Beispiel")
        asset = self.repository.create_asset("Notebook", "NB-100", "HP EliteBook")

        assignment = self.repository.assign_asset(
            asset_id=asset["id"],
            person_id=person["id"],
            hostname="LT-ANNA",
            actor="tester",
        )
        current = self.repository.get_current_assignment_for_asset(asset["id"])
        snapshots = self.repository.list_asset_snapshots()

        self.assertEqual(assignment["id"], current["id"])
        self.assertEqual(current["hostname"], "LT-ANNA")
        self.assertEqual(snapshots[0]["assigned_to"], "Anna Beispiel")
        self.assertEqual(snapshots[0]["hostname"], "LT-ANNA")

    def test_list_current_assets_for_person_returns_current_assignments(self):
        person = self.repository.create_or_update_person("Asset User")
        asset = self.repository.create_asset("Notebook", "NB-LIST-1", "Dell 7410")
        self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-LIST")

        rows = self.repository.list_current_assets_for_person(person["id"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_tag"], "NB-LIST-1")

    def test_reassign_asset_returns_previous_assignment(self):
        first_person = self.repository.create_or_update_person("Max")
        second_person = self.repository.create_or_update_person("Julia")
        asset = self.repository.create_asset("Notebook", "NB-200", "Lenovo X1")

        first = self.repository.assign_asset(asset_id=asset["id"], person_id=first_person["id"], hostname="LT-MAX")
        second = self.repository.assign_asset(asset_id=asset["id"], person_id=second_person["id"], hostname="LT-JULIA")

        current = self.repository.get_current_assignment_for_asset(asset["id"])
        old = self.repository.get_assignment(first["id"])

        self.assertEqual(current["id"], second["id"])
        self.assertEqual(current["person_id"], second_person["id"])
        self.assertEqual(old["is_current"], 0)
        self.assertEqual(old["assignment_status"], "returned")

    def test_return_asset_closes_current_assignment(self):
        person = self.repository.create_or_update_person("Chris")
        asset = self.repository.create_asset("Notebook", "NB-300", "ThinkPad")
        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-CHRIS")

        returned = self.repository.return_asset(asset["id"], actor="tester", notes="Zurueck im Lager")
        current = self.repository.get_current_assignment_for_asset(asset["id"])

        self.assertEqual(returned["id"], assignment["id"])
        self.assertEqual(returned["is_current"], 0)
        self.assertEqual(returned["assignment_status"], "returned")
        self.assertIsNone(current)

    def test_update_current_assignment_changes_person_hostname_and_notes(self):
        first_person = self.repository.create_or_update_person("First User")
        second_person = self.repository.create_or_update_person("Second User")
        asset = self.repository.create_asset("Notebook", "NB-UPD-1", "Dell 7420")
        self.repository.assign_asset(asset_id=asset["id"], person_id=first_person["id"], hostname="LT-OLD", notes="Alt")

        updated = self.repository.update_current_assignment(
            asset["id"],
            person_id=second_person["id"],
            hostname="LT-NEW",
            notes="Neu",
            actor="test-update",
        )

        self.assertEqual(updated["person_id"], second_person["id"])
        self.assertEqual(updated["hostname"], "LT-NEW")
        self.assertEqual(updated["notes"], "Neu")

    def test_update_current_assignment_detects_record_version_conflict(self):
        first_person = self.repository.create_or_update_person("Conflict First")
        second_person = self.repository.create_or_update_person("Conflict Second")
        asset = self.repository.create_asset("Notebook", "NB-ASSIGN-CONFLICT", "Dell 7330")
        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=first_person["id"], hostname="LT-C1")

        self.repository.update_current_assignment(
            asset["id"],
            person_id=second_person["id"],
            hostname="LT-C2",
            expected_record_version=assignment["record_version"],
        )

        with self.assertRaises(ConflictError):
            self.repository.update_current_assignment(
                asset["id"],
                notes="Zu spaet",
                expected_record_version=assignment["record_version"],
            )

    def test_return_asset_detects_record_version_conflict(self):
        person = self.repository.create_or_update_person("Return Conflict")
        asset = self.repository.create_asset("Notebook", "NB-RETURN-CONFLICT", "ThinkPad T14")
        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-RC")

        self.repository.update_current_assignment(
            asset["id"],
            notes="Zwischenupdate",
            expected_record_version=assignment["record_version"],
        )

        with self.assertRaises(ConflictError):
            self.repository.return_asset(
                asset["id"],
                expected_record_version=assignment["record_version"],
            )

    def test_delete_asset_removes_asset_and_assignments(self):
        person = self.repository.create_or_update_person("Delete User")
        asset = self.repository.create_asset("Notebook", "NB-DEL", "Dell 7490")
        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-DEL")

        self.repository.delete_asset(asset["id"], actor="test-delete")

        self.assertIsNone(self.repository.get_asset(asset_id=asset["id"]))
        self.assertIsNone(self.repository.get_current_assignment_for_asset(asset["id"]))
        timeline = self.repository.list_audit_events(entity_type="managed_asset", entity_id=asset["id"])
        self.assertTrue(any(event["action"] == "asset-deleted" for event in timeline))
        self.assertIsNone(self.repository.get_assignment(assignment["id"]))

    def test_smartphone_assignment_ignores_hostname(self):
        person = self.repository.create_or_update_person("Phone User")
        asset = self.repository.create_asset("Smartphone", "PH-010", "iPhone 15")

        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="IGNORED")

        self.assertEqual(assignment["hostname"], "")

    def test_audit_events_are_written_for_asset_and_assignment_changes(self):
        person = self.repository.create_or_update_person("Audit User")
        asset = self.repository.create_asset("Notebook", "NB-500", "Dell 5450")
        self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-AUDIT", actor="audit")
        self.repository.update_asset(asset["id"], inventory_status="inactive", notes="Pruefung")

        asset_events = self.repository.list_audit_events(entity_type="managed_asset", entity_id=asset["id"])
        assignment_events = self.repository.list_audit_events(entity_type="asset_assignment")

        self.assertTrue(any(event["action"] == "asset-created" for event in asset_events))
        self.assertTrue(any(event["action"] == "asset-updated" for event in asset_events))
        self.assertTrue(any(event["action"] == "assignment-created" for event in assignment_events))

    def test_asset_timeline_contains_asset_and_assignment_events(self):
        person = self.repository.create_or_update_person("Timeline User")
        asset = self.repository.create_asset("Notebook", "NB-700", "Dell 7350")
        assignment = self.repository.assign_asset(asset_id=asset["id"], person_id=person["id"], hostname="LT-TIME")

        timeline = self.repository.list_timeline_for_asset(asset["id"])

        self.assertTrue(any(event["entity_type"] == "managed_asset" for event in timeline))
        self.assertTrue(any(event["entity_type"] == "asset_assignment" and event["entity_id"] == assignment["id"] for event in timeline))

    def test_acquire_edit_claim_blocks_other_editor(self):
        asset = self.repository.create_asset("Notebook", "NB-CLAIM-1", "Dell 5550")

        claim = self.repository.acquire_edit_claim(
            "managed_asset",
            asset["id"],
            editor_id="editor-a",
            editor_label="Editor A",
        )

        self.assertEqual(claim["editor_id"], "editor-a")
        with self.assertRaises(EditClaimError):
            self.repository.acquire_edit_claim(
                "managed_asset",
                asset["id"],
                editor_id="editor-b",
                editor_label="Editor B",
            )

    def test_release_edit_claim_allows_next_editor(self):
        asset = self.repository.create_asset("Notebook", "NB-CLAIM-2", "Dell 5560")

        self.repository.acquire_edit_claim(
            "managed_asset",
            asset["id"],
            editor_id="editor-a",
            editor_label="Editor A",
        )
        released = self.repository.release_edit_claim("managed_asset", asset["id"], editor_id="editor-a")
        next_claim = self.repository.acquire_edit_claim(
            "managed_asset",
            asset["id"],
            editor_id="editor-b",
            editor_label="Editor B",
        )

        self.assertTrue(released)
        self.assertEqual(next_claim["editor_id"], "editor-b")

    def test_expired_edit_claim_is_ignored(self):
        asset = self.repository.create_asset("Notebook", "NB-CLAIM-3", "Dell 5570")
        self.repository.acquire_edit_claim(
            "managed_asset",
            asset["id"],
            editor_id="editor-a",
            editor_label="Editor A",
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE edit_claims
                SET expires_at = '2000-01-01 00:00:00'
                WHERE entity_type = 'managed_asset' AND entity_id = ?
                """,
                (asset["id"],),
            )
            conn.commit()

        claim = self.repository.acquire_edit_claim(
            "managed_asset",
            asset["id"],
            editor_id="editor-b",
            editor_label="Editor B",
        )

        self.assertEqual(claim["editor_id"], "editor-b")


if __name__ == "__main__":
    unittest.main()
