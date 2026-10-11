"""Isolated source-first import fixtures; no account files, network or engine."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from hoyolab_export.account_storage import init_account_storage, list_account_characters, refresh_account_reference_fields
from hoyolab_export.character_stat_snapshot import build_character_stat_snapshot, WARNING_TRAVELER_SPECIAL_DEFERRED
from hoyolab_export.artifact_db import connect_db
from hoyolab_export.import_store import (
    commit_import_snapshot, prepare_import_store, read_equipment_revision, stage_import_attempt,
)
from hoyolab_export.traveler import (
    TRAVELER_ELEMENTS, traveler_element, traveler_source_id, traveler_variant_id,
)
from hoyolab_export.traveler_variants import backfill_traveler_variants, ensure_traveler_variants
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_details, fake_account_weapon,
)


class TravelerImportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / "account.db"
        prepare_import_store(self.db)
        self.serial = 0
        self.refs = {"character_stats_catalog": None, "weapon_stats_catalog": None,
                     "gcsim_key_resolver": None, "character_region_entries": (), "character_trait_entries": ()}

    def source(self, element="Cryo", *, source_id=10000007, constellation=4, level=90):
        character = fake_account_character(character_id=source_id, name="Custom name")
        character.update(element=element, rarity=5, level=level, constellation=constellation,
                         weapon_type=1, weapon_type_name="sword")
        details = fake_account_details(character_id=source_id, character_name="Custom name")
        details["json"]["retcode"] = 0
        row = details["json"]["data"]["list"][0]
        row["base"].update(character)
        row["base"]["actived_constellation_num"] = constellation
        index = TRAVELER_ELEMENTS.index(element) if element in TRAVELER_ELEMENTS else 0
        row["skills"] = [dict(skill_id=9000 + index * 10 + number, skill_type=1, level=number + constellation,
                              name=f"{element} skill {number}", is_unlock=True) for number in (1, 2, 3)]
        row["constellations"] = [dict(pos=number, is_actived=number <= constellation,
                                     name=f"{element} C{number}", effect=f"{element} fixture") for number in range(1, 7)]
        row["weapon"].update(type=1, type_name="sword")
        row["relics"] = [dict(id=1, name="Fixture flower", pos=1, rarity=5, level=20,
                             set={"id": 2150451, "name": "Unmapped fixture set"},
                             main_property={"property_type": 2000, "value": "4780"}, sub_property_list=[])]
        weapon = fake_account_weapon(character_id=source_id)
        weapon.update(type=1, type_name="sword")
        return dict(account_uid="600000001", server="os_euro", account_characters=[character],
                    account_weapons=[weapon], account_character_details=details, content_language="en-us", manifest={})

    def stage(self, source, *, apply=True):
        self.serial += 1
        return stage_import_attempt(self.db, **source, attempt_id=f"traveler-{self.serial}",
                                    change_equipment=apply, expected_equipment_revision=read_equipment_revision(self.db))

    def commit(self, attempt):
        with patch("hoyolab_export.account_storage._download_url_to_file", side_effect=AssertionError("network")):
            return commit_import_snapshot(self.db, attempt_id=attempt, account_sync_context=self.refs,
                                          side_icon_cache_dir=self.root / "missing-icons")

    def rows(self):
        with closing(connect_db(self.db)) as conn:
            return {row.element: row for row in list_account_characters(conn)}

    def equipment(self):
        with closing(connect_db(self.db)) as conn:
            return {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("artifacts", "account_weapon_observed_stacks", "account_character_equipped_weapons",
                              "account_character_equipped_artifacts", "account_character_applied_build_presets")
            }

    def test_first_import_clones_character_data_and_only_real_variant_has_gear(self):
        self.commit(self.stage(self.source()))
        rows = self.rows()
        self.assertEqual(set(rows), set(TRAVELER_ELEMENTS))
        original = rows["Cryo"]
        self.assertEqual(original.character_id, "10000007")
        for element, row in rows.items():
            self.assertEqual((row.level, row.constellation, row.base_hp, row.base_atk, row.base_def),
                             (original.level, original.constellation, original.base_hp, original.base_atk, original.base_def))
            self.assertEqual([(t.skill_id, t.level) for t in row.talents], [(t.skill_id, t.level) for t in original.talents])
            self.assertEqual(row.source_character_id, "10000007")
            self.assertTrue(row.is_standard_5_star)
            self.assertIn("standard_5_star", row.traits)
            self.assertEqual(row.catalog_english_name, f"Traveler ({element})")
            self.assertEqual(row.gcsim_character_key, "")
            self.assertEqual(row.gcsim_character_key_status, "unsupported_traveler")
            self.assertIn(WARNING_TRAVELER_SPECIAL_DEFERRED,
                          build_character_stat_snapshot(account_character=row.to_dict()).warnings)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_character_constellations").fetchone()[0], 42)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT known_count FROM account_weapon_observed_stacks").fetchone()[0], 1)
            for table in ("account_character_equipped_artifacts", "account_character_equipped_weapons"):
                self.assertEqual([row[0] for row in conn.execute(f"SELECT character_id FROM {table}")], [10000007])

    def test_repeat_and_receipt_replay_preserve_seven_variants_and_copy_counts(self):
        attempt = self.stage(self.source())
        first = self.commit(attempt)
        before = self.equipment()
        self.assertEqual(self.commit(attempt), first)
        self.assertEqual(self.equipment(), before)
        self.commit(self.stage(self.source()))
        self.assertEqual(len(self.rows()), 7)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT SUM(known_count) FROM account_weapon_observed_stacks").fetchone()[0], 1)

    def test_new_element_replaces_copied_talents_only_and_moves_existing_gear(self):
        self.commit(self.stage(self.source()))
        before = {e: row.to_dict() for e, row in self.rows().items()}
        self.commit(self.stage(self.source("Pyro", constellation=6, level=80)))
        rows = self.rows()
        pyro = rows["Pyro"]
        self.assertEqual(pyro.character_id, str(traveler_variant_id(10000007, "Pyro")))
        self.assertEqual((pyro.level, pyro.constellation), (80, 6))
        self.assertEqual({t.skill_id for t in pyro.talents}, {"9051", "9052", "9053"})
        self.assertEqual({t.level for t in pyro.talents}, {7, 8, 9})
        for element in set(TRAVELER_ELEMENTS) - {"Pyro"}:
            self.assertEqual(rows[element].to_dict(), before[element])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT SUM(known_count) FROM account_weapon_observed_stacks").fetchone()[0], 1)
            for table in ("account_character_equipped_artifacts", "account_character_equipped_weapons"):
                self.assertEqual([row[0] for row in conn.execute(f"SELECT character_id FROM {table}")], [int(pyro.character_id)])
            self.assertEqual(conn.execute("SELECT SUM(is_actived) FROM account_character_constellations WHERE character_id=?",
                                          (int(pyro.character_id),)).fetchone()[0], 6)

    def test_disabled_or_stale_equipment_keeps_user_gear_and_still_updates_variant(self):
        self.commit(self.stage(self.source()))
        before = self.equipment()
        self.commit(self.stage(self.source("Pyro", constellation=6), apply=False))
        after = self.equipment()
        self.assertEqual([row[0] for row in before["artifacts"]], [row[0] for row in after["artifacts"]])
        for table in ("account_character_equipped_weapons", "account_character_equipped_artifacts"):
            self.assertEqual(before[table], after[table])
        attempt = self.stage(self.source("Hydro", constellation=2))
        with closing(connect_db(self.db)) as conn:
            conn.execute("UPDATE account_character_equipped_weapons SET character_id=?, source='manual', updated_at='user-edit'",
                         (traveler_variant_id(10000007, "Pyro"),))
            conn.commit()
        result = self.commit(attempt)
        self.assertEqual(result["equipment"]["reason"], "stale_equipment_revision")
        self.assertEqual(self.rows()["Hydro"].constellation, 2)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(tuple(conn.execute("SELECT character_id, source FROM account_character_equipped_weapons").fetchone()),
                             (traveler_variant_id(10000007, "Pyro"), "manual"))

    def test_all_elements_update_independently_with_stable_original_id(self):
        self.commit(self.stage(self.source("Anemo", source_id=10000005)))
        for index, element in enumerate(TRAVELER_ELEMENTS):
            self.commit(self.stage(self.source(element, source_id=10000005, constellation=index)))
        rows = self.rows()
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows["Anemo"].character_id, "10000005")
        for index, element in enumerate(TRAVELER_ELEMENTS):
            self.assertEqual(rows[element].constellation, index)
            self.assertEqual(rows[element].source_character_id, "10000005")

    def test_core_failure_rolls_back_clones_skills_equipment_and_identity(self):
        attempt = self.stage(self.source())
        with closing(connect_db(self.db)) as conn:
            conn.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE OF status ON hoyolab_import_attempts "
                         "BEGIN SELECT RAISE(FAIL, 'fixture rollback'); END")
            conn.commit()
        with self.assertRaisesRegex(Exception, "fixture rollback"):
            self.commit(attempt)
        with closing(connect_db(self.db)) as conn:
            for table in ("account_characters", "account_character_talents", "account_character_constellations",
                          "character_identity", "artifacts", "account_weapon_observed_stacks",
                          "account_character_equipped_weapons", "account_character_equipped_artifacts"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
            conn.execute("DROP TRIGGER fail_receipt")
            conn.commit()
        self.commit(attempt)
        self.assertEqual(len(self.rows()), 7)

    def test_missing_skills_preserved_until_real_element_skills_arrive(self):
        self.commit(self.stage(self.source()))
        source = self.source("Pyro")
        del source["account_character_details"]["json"]["data"]["list"][0]["skills"]
        prior = [t.to_dict() for t in self.rows()["Pyro"].talents]
        self.commit(self.stage(source))
        self.assertEqual([t.to_dict() for t in self.rows()["Pyro"].talents], prior)
        self.commit(self.stage(self.source("Pyro")))
        self.assertEqual({t.skill_id for t in self.rows()["Pyro"].talents}, {"9051", "9052", "9053"})

    def test_partial_skills_neither_prune_observed_rows_nor_mix_copied_elements(self):
        self.commit(self.stage(self.source()))
        for element in ("Cryo", "Pyro"):
            source = self.source(element)
            skills = source["account_character_details"]["json"]["data"]["list"][0]["skills"]
            source["account_character_details"]["json"]["data"]["list"][0]["skills"] = skills[:1]
            before = [(row.skill_id, row.level, row.name) for row in self.rows()[element].talents]
            self.commit(self.stage(source))
            self.assertEqual([(row.skill_id, row.level, row.name) for row in self.rows()[element].talents], before)

    def test_legacy_key_metadata_does_not_override_explicit_variant_status(self):
        self.commit(self.stage(self.source()))
        with closing(connect_db(self.db)) as conn:
            metadata = {"gcsim_character_key_resolution": {"status": "ready", "gcsim_key": "lumineanemo"}}
            conn.execute("UPDATE account_characters SET source_metadata_json=? WHERE character_id=10000007", (json.dumps(metadata),))
            conn.commit()
        self.commit(self.stage(self.source()))
        row = self.rows()["Cryo"]
        self.assertEqual(row.source_metadata["gcsim_character_key_resolution"]["status"], "unsupported_traveler")
        self.assertEqual(row.source_metadata["gcsim_character_key_resolution"]["gcsim_key"], "")

    def test_active_only_source_preserves_missing_passives_until_observed(self):
        source = self.source()
        source["account_character_details"]["json"]["data"]["list"][0]["skills"] += [
            dict(skill_id=9100 + i, skill_type=2 if i < 3 else 3, level=1) for i in range(4)
        ]
        self.commit(self.stage(source))
        self.commit(self.stage(self.source("Pyro")))
        self.assertEqual({t.skill_id for t in self.rows()["Pyro"].talents},
                         {"9051", "9052", "9053", "9100", "9101", "9102", "9103"})
        source = self.source("Pyro")
        source["account_character_details"]["json"]["data"]["list"][0]["skills"] += [
            dict(skill_id=9200 + i, skill_type=2 if i < 3 else 3, level=1) for i in range(4)
        ]
        self.commit(self.stage(source))
        self.assertEqual({t.skill_id for t in self.rows()["Pyro"].talents},
                         {"9051", "9052", "9053", "9200", "9201", "9202", "9203"})

    def test_backfill_is_idempotent_and_reference_refresh_cannot_map_wrong_element(self):
        self.commit(self.stage(self.source()))
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM account_characters WHERE character_id < 0")
            conn.execute("DELETE FROM character_identity WHERE character_id < 0")
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            self.assertEqual(ensure_traveler_variants(conn, now="fixture-backfill"), 6)
            self.assertEqual(ensure_traveler_variants(conn, now="fixture-backfill"), 0)
            gear = conn.execute("SELECT character_id FROM account_character_equipped_weapons").fetchone()[0]
            self.assertEqual(gear, 10000007)
            refresh_account_reference_fields(conn, gcsim_key_resolver=Mock(side_effect=AssertionError("generic resolver")))
            conn.commit()

    def test_identity_rejects_arbitrary_negative_or_conflicting_element(self):
        self.assertIsNone(traveler_source_id(-42))
        self.assertEqual(traveler_element(traveler_variant_id(10000007, "Pyro"), "Cryo"), "")
        attempt = self.stage(self.source("Unknown"))
        with self.assertRaisesRegex(ValueError, "explicit element"):
            self.commit(attempt)
        self.assertEqual(self.rows(), {})

    def test_startup_backfill_preserves_recoverable_originals_and_does_not_repeat(self):
        self.commit(self.stage(self.source()))
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM account_characters WHERE character_id < 0")
            conn.execute("DELETE FROM character_identity WHERE character_id < 0")
            conn.execute("UPDATE account_characters SET source_metadata_json='{}', catalog_english_name='', "
                         "gcsim_character_key_status='', gcsim_character_key_method=''")
            conn.commit()
            original = dict(conn.execute("SELECT * FROM account_characters").fetchone())
            identity = dict(conn.execute("SELECT * FROM character_identity").fetchone())
            init_account_storage(conn)
            conn.commit()
            rows = list_account_characters(conn)
            self.assertEqual(len(rows), 7)
            anchor = next(row for row in rows if row.character_id == "10000007")
            recovery = anchor.source_metadata["traveler_variant"]["legacy_original"]
            self.assertEqual(recovery, {"account_character": original, "character_identity": identity})
            total = conn.total_changes
            self.assertEqual(backfill_traveler_variants(conn, now="second-startup"), 0)
            self.assertEqual(conn.total_changes, total)
        self.commit(self.stage(self.source("Cryo", constellation=5)))
        self.assertEqual(self.rows()["Cryo"].source_metadata["traveler_variant"]["legacy_original"], recovery)

    def test_backfill_failure_rolls_back_whole_migration(self):
        self.commit(self.stage(self.source()))
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM account_characters WHERE character_id < 0")
            conn.execute("DELETE FROM character_identity WHERE character_id < 0")
            conn.execute("UPDATE account_characters SET source_metadata_json='{}'")
            conn.commit()
            original = dict(conn.execute("SELECT * FROM account_characters").fetchone())
            conn.execute("CREATE TRIGGER fail_clone BEFORE INSERT ON account_characters WHEN NEW.element='Pyro' "
                         "BEGIN SELECT RAISE(FAIL, 'clone failure'); END")
            with self.assertRaisesRegex(Exception, "clone failure"):
                backfill_traveler_variants(conn, now="failed")
            self.assertEqual([dict(row) for row in conn.execute("SELECT * FROM account_characters")], [original])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM character_identity").fetchone()[0], 1)
