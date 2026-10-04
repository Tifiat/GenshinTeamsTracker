"""Fixture-only checks for durable HoYoLAB account publication."""

from __future__ import annotations

from copy import deepcopy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.artifact_db import connect_db
from hoyolab_export.import_store import (
    AccountBindingMismatch,
    ImportStoreError,
    LegacyAccountBindingRequired,
    adopt_legacy_account_binding,
    commit_import_snapshot,
    get_active_account_binding,
    get_import_attempt,
    get_import_result,
    latest_committed_import,
    list_pending_import_attempts,
    prepare_import_store,
    read_equipment_revision,
    refresh_import_references,
    stage_import_attempt,
    update_import_enrichment,
)
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_details, fake_account_weapon,
)


class ImportStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / "fixture.db"
        prepare_import_store(self.db)
        self.details = fake_account_details()
        self.details["json"]["retcode"] = 0
        self.details["json"]["data"]["list"][0]["relics"] = []
        self.source = {
            "account_uid": "600000001", "server": "os_euro",
            "account_characters": [fake_account_character()],
            "account_weapons": [fake_account_weapon()],
            "account_character_details": self.details,
            "content_language": "en-us", "manifest": {},
        }
        self.empty_refs = {
            "character_stats_catalog": None,
            "weapon_stats_catalog": None,
            "gcsim_key_resolver": None,
            "character_region_entries": (),
            "character_trait_entries": (),
        }

    def stage(self, **changes) -> str:
        return stage_import_attempt(self.db, **(self.source | changes))

    def commit(self, attempt_id: str) -> dict:
        return commit_import_snapshot(
            self.db, attempt_id=attempt_id, account_sync_context=self.empty_refs,
            side_icon_cache_dir=Path(self.temporary.name) / "icons",
        )

    def test_core_receipt_replay_and_enrichment_do_not_repeat_observations(self):
        attempt_id = self.stage(attempt_id="fixture-once", change_equipment=False)
        with patch("hoyolab_export.account_storage._download_url_to_file", side_effect=AssertionError("network")):
            first = self.commit(attempt_id)
        self.assertEqual(first["status"], "committed")
        self.assertEqual(first["account_uid"], "600000001")
        self.assertEqual(first["account_storage"]["characters_seen"], 1)
        self.assertEqual(first["equipment"], {"applied": False, "reason": "disabled"})
        self.assertEqual(get_active_account_binding(self.db)["account_uid"], "600000001")
        self.assertEqual(get_import_attempt(self.db, attempt_id)["enrichment"]["assets"]["status"], "pending")
        with closing(connect_db(self.db)) as conn:
            before = conn.execute(
                "SELECT last_seen_at, known_count FROM account_weapon_observed_stacks"
            ).fetchone()
            before_rows = conn.execute("SELECT COUNT(*) FROM account_characters").fetchone()[0]
        self.assertEqual(self.commit(attempt_id), first)
        self.assertEqual(get_import_result(self.db, attempt_id), first)
        enrichment = update_import_enrichment(
            self.db, attempt_id=attempt_id, kind="assets", status="failed",
            result={"error": "fixture"},
        )
        self.assertEqual(enrichment["assets"]["status"], "failed")
        self.assertEqual(refresh_import_references(
            self.db, attempt_id=attempt_id, account_sync_context=self.empty_refs,
        ), {"characters": 0, "weapons": 0})
        self.assertEqual(get_import_attempt(self.db, attempt_id)["enrichment"]["references"]["status"], "pending")
        self.assertEqual(get_import_result(self.db, attempt_id), first)
        with closing(connect_db(self.db)) as conn:
            after = conn.execute(
                "SELECT last_seen_at, known_count FROM account_weapon_observed_stacks"
            ).fetchone()
            self.assertEqual(tuple(after), tuple(before))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_characters").fetchone()[0], before_rows)
        self.assertEqual(latest_committed_import(self.db)["attempt_id"], attempt_id)

    def test_recovery_does_not_offer_another_role_staged_before_first_binding(self):
        selected = self.stage(attempt_id="selected-role")
        deferred = self.stage(attempt_id="other-role", account_uid="600000002")
        self.commit(selected)
        self.assertEqual(list_pending_import_attempts(self.db), [])
        self.assertEqual(get_import_attempt(self.db, deferred)["status"], "pending")
        with self.assertRaises(AccountBindingMismatch):
            self.commit(deferred)

    def test_stage_is_idempotent_but_rejects_changed_snapshot_and_credentials(self):
        attempt_id = self.stage(attempt_id="fixed")
        self.assertEqual(self.stage(attempt_id="fixed"), attempt_id)
        with self.assertRaises(ImportStoreError):
            self.stage(attempt_id="fixed", account_uid="600000002")
        with self.assertRaises(ValueError):
            self.stage(attempt_id="secret", manifest={"cookie": "never stored"})
        self.assertIsNone(get_import_attempt(self.db, "secret"))

    def test_rejects_partial_or_mixed_account_source_before_staging(self):
        with self.assertRaisesRegex(ValueError, "detail IDs"):
            self.stage(account_characters=[
                fake_account_character(), fake_account_character(character_id=1002),
            ])
        with self.assertRaisesRegex(ValueError, "source role ID"):
            self.stage(account_character_details=self.details | {"role_id": "600000002"})
        malformed = fake_account_details()
        malformed["json"]["retcode"] = 0
        malformed["json"]["data"]["list"][0]["relics"] = [{
            "id": 1, "pos": 1, "rarity": 5, "level": 20,
            "set": {"id": 2150451},
            "main_property": {"property_type": 2000},
            "sub_property_list": [],
        }]
        with self.assertRaisesRegex(ValueError, "property value"):
            self.stage(account_character_details=malformed)
        without_relics = fake_account_details()
        without_relics["json"]["retcode"] = 0
        with self.assertRaisesRegex(ValueError, "relic rows"):
            self.stage(account_character_details=without_relics)
        self.assertEqual(list_pending_import_attempts(self.db), [])

    def test_missing_relic_substats_cannot_replace_previous_observation(self):
        relic = {
            "id": 1, "name": "Fixture flower", "pos": 1, "rarity": 5, "level": 20,
            "set": {"id": 2150451, "name": "Unmapped fixture set"},
            "main_property": {"property_type": 2000, "value": "4780"},
            "sub_property_list": [{"property_type": 20, "value": "3.1%"}],
        }
        self.details["json"]["data"]["list"][0]["relics"] = [relic]
        self.commit(self.stage(attempt_id="complete-relic"))
        with closing(connect_db(self.db)) as conn:
            before = [tuple(row) for row in conn.execute(
                "SELECT artifact_id, slot_index, property_type, value FROM artifact_substats"
            )]
        incomplete = deepcopy(self.details)
        del incomplete["json"]["data"]["list"][0]["relics"][0]["sub_property_list"]
        with self.assertRaisesRegex(ValueError, "substats"):
            self.stage(attempt_id="partial-relic", account_character_details=incomplete)
        self.assertIsNone(get_import_attempt(self.db, "partial-relic"))
        with closing(connect_db(self.db)) as conn:
            self.assertEqual([tuple(row) for row in conn.execute(
                "SELECT artifact_id, slot_index, property_type, value FROM artifact_substats"
            )], before)

    def test_failure_rolls_back_all_account_mutations_and_leaves_source_pending(self):
        self.details["json"]["data"]["list"][0]["relics"] = [{
            "id": 1, "name": "Fixture flower", "pos": 1, "rarity": 5, "level": 20,
            "set": {"id": 2150451, "name": "Unmapped fixture set"},
            "main_property": {"property_type": 2000, "value": "4780"},
            "sub_property_list": [],
        }]
        attempt_id = self.stage(attempt_id="retry-after-fault")
        with patch(
            "hoyolab_export.import_store.sync_account_storage_from_sources",
            side_effect=RuntimeError("injected after artifact work"),
        ), self.assertRaisesRegex(RuntimeError, "injected"):
            self.commit(attempt_id)
        self.assertEqual(get_import_attempt(self.db, attempt_id)["status"], "pending")
        self.assertEqual([item["attempt_id"] for item in list_pending_import_attempts(self.db)], [attempt_id])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_characters").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM hoyolab_account_binding").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)
        result = self.commit(attempt_id)
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["artifacts"]["artifacts_inserted"], 1)
        self.assertEqual(result["artifacts"]["relics_unresolved_set"], 1)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)

    def test_mismatch_and_unbound_legacy_rows_preserve_existing_account(self):
        with closing(connect_db(self.db)) as conn:
            conn.execute("INSERT INTO account_characters(character_id, name) VALUES (999, 'legacy')")
            conn.commit()
        attempt_id = self.stage(attempt_id="legacy")
        with self.assertRaises(LegacyAccountBindingRequired):
            self.commit(attempt_id)
        self.assertEqual(get_import_attempt(self.db, attempt_id)["status"], "pending")
        with self.assertRaises(LegacyAccountBindingRequired):
            adopt_legacy_account_binding(self.db, account_uid="600000001", server="os_euro")
        adopt_legacy_account_binding(
            self.db, account_uid="600000001", server="os_euro", verified=True,
        )
        self.commit(attempt_id)
        with self.assertRaises(AccountBindingMismatch):
            self.stage(attempt_id="other", account_uid="600000002")
        self.assertIsNone(get_import_attempt(self.db, "other"))
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT name FROM account_characters WHERE character_id = 999").fetchone()[0], "legacy")

    def test_connected_cleanup_keeps_current_and_recoverable_pending(self):
        ids = []
        for number in range(11):
            attempt_id = self.stage(attempt_id=f"receipt-{number}")
            ids.append(attempt_id)
            self.commit(attempt_id)
        self.assertIsNone(get_import_attempt(self.db, ids[0]))
        self.assertEqual(latest_committed_import(self.db)["attempt_id"], ids[-1])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM hoyolab_import_attempts WHERE status = 'committed'"
            ).fetchone()[0], 10)
        oldest = self.stage(attempt_id="old-pending")
        with closing(connect_db(self.db)) as conn:
            conn.execute(
                "UPDATE hoyolab_import_attempts SET created_at = '2000-01-01T00:00:00+00:00' "
                "WHERE attempt_id = ?", (oldest,),
            )
            conn.commit()
        self.assertIsNotNone(get_import_attempt(self.db, oldest))
        newest = self.stage(attempt_id="new-pending")
        self.assertIsNone(get_import_attempt(self.db, oldest))
        self.assertEqual(list_pending_import_attempts(self.db)[0]["attempt_id"], newest)
        for number in range(12):
            self.stage(attempt_id=f"extra-pending-{number}")
        self.assertEqual(len(list_pending_import_attempts(self.db)), 10)

    def test_receipt_failure_rolls_back_equipment_and_observations(self):
        self.details["json"]["data"]["list"][0]["relics"] = [{
            "id": 1, "name": "Fixture flower", "pos": 1, "rarity": 5, "level": 20,
            "set": {"id": 2150451, "name": "Unmapped fixture set"},
            "main_property": {"property_type": 2000, "value": "4780"},
            "sub_property_list": [],
        }]
        attempt_id = self.stage(
            attempt_id="receipt-trigger", change_equipment=True,
            expected_equipment_revision=read_equipment_revision(self.db),
        )
        with closing(connect_db(self.db)) as conn:
            conn.execute(
                """CREATE TRIGGER fail_import_receipt BEFORE UPDATE OF status
                   ON hoyolab_import_attempts BEGIN SELECT RAISE(FAIL, 'receipt blocked'); END"""
            )
            conn.commit()
        with self.assertRaisesRegex(Exception, "receipt blocked"):
            self.commit(attempt_id)
        with closing(connect_db(self.db)) as conn:
            for table in (
                "artifacts", "artifact_equipment", "account_characters",
                "account_character_equipped_artifacts", "account_character_equipped_weapons",
                "hoyolab_account_binding",
            ):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
            conn.execute("DROP TRIGGER fail_import_receipt")
            conn.commit()
        result = self.commit(attempt_id)
        self.assertTrue(result["equipment"]["applied"])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM account_character_equipped_artifacts"
            ).fetchone()[0], 1)

    def test_changed_equipment_revision_keeps_user_assignment(self):
        initial = self.stage(attempt_id="base-account")
        self.commit(initial)
        before = read_equipment_revision(self.db)
        attempt_id = self.stage(
            attempt_id="stale-gear", change_equipment=True,
            expected_equipment_revision=before,
        )
        with closing(connect_db(self.db)) as conn:
            fingerprint = conn.execute(
                "SELECT weapon_fingerprint FROM account_weapon_observed_stacks"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO account_character_equipped_weapons
                   (character_id, weapon_fingerprint, source, updated_at)
                   VALUES (1001, ?, 'manual', '2026-01-01T00:00:00+00:00')""",
                (fingerprint,),
            )
            conn.commit()
        result = self.commit(attempt_id)
        self.assertEqual(result["equipment"], {
            "applied": False, "reason": "stale_equipment_revision",
        })
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT source FROM account_character_equipped_weapons WHERE character_id = 1001"
            ).fetchone()[0], "manual")

    def test_equipment_revision_read_does_not_create_missing_database(self):
        absent = Path(self.temporary.name) / "absent.db"
        self.assertEqual(len(read_equipment_revision(absent)), 64)
        self.assertIsNone(get_import_attempt(absent, "x"))
        self.assertIsNone(get_import_result(absent, "x"))
        self.assertIsNone(latest_committed_import(absent))
        self.assertIsNone(get_active_account_binding(absent))
        self.assertEqual(list_pending_import_attempts(absent), [])
        self.assertFalse(absent.exists())
        legacy = Path(self.temporary.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as conn:
            conn.execute("CREATE TABLE unrelated (id INTEGER)")
            conn.commit()
        self.assertIsNone(get_import_attempt(legacy, "x"))
        self.assertIsNone(latest_committed_import(legacy))
        self.assertIsNone(get_active_account_binding(legacy))
        self.assertEqual(list_pending_import_attempts(legacy), [])

    def test_older_pending_snapshot_cannot_overwrite_newer_commit(self):
        older = self.stage(attempt_id="older")
        newer = self.stage(attempt_id="newer")
        self.commit(newer)
        with self.assertRaisesRegex(ImportStoreError, "superseded"):
            self.commit(older)
        self.assertEqual(get_import_attempt(self.db, older)["status"], "pending")
        self.assertEqual(list_pending_import_attempts(self.db), [])
        self.assertEqual(latest_committed_import(self.db)["attempt_id"], newer)

    def test_level_change_without_base_reference_clears_stale_values(self):
        first = self.stage(attempt_id="level-70")
        self.commit(first)
        with closing(connect_db(self.db)) as conn:
            conn.execute(
                "UPDATE account_characters SET ascension_bonus_stat_type = 'CRIT_RATE', "
                "ascension_bonus_value = 0.1 WHERE character_id = 1001"
            )
            conn.commit()
        changed_details = deepcopy(self.details)
        detail = changed_details["json"]["data"]["list"][0]
        detail["base"]["level"] = 80
        detail["base_properties"] = []
        changed_character = fake_account_character()
        changed_character["level"] = 80
        second = self.stage(
            attempt_id="level-80", account_characters=[changed_character],
            account_character_details=changed_details,
        )
        self.commit(second)
        with closing(connect_db(self.db)) as conn:
            row = conn.execute(
                "SELECT level, base_hp, base_atk, base_def, ascension_bonus_stat_type, "
                "ascension_bonus_value FROM account_characters WHERE character_id = 1001"
            ).fetchone()
        self.assertEqual(row["level"], 80)
        self.assertIsNone(row["base_hp"])
        self.assertIsNone(row["base_atk"])
        self.assertIsNone(row["base_def"])
        self.assertEqual(row["ascension_bonus_stat_type"], "")
        self.assertIsNone(row["ascension_bonus_value"])


if __name__ == "__main__":
    unittest.main()
