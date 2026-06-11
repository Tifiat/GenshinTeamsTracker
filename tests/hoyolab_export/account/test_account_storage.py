from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path

from hoyolab_export.account_storage import (
    AccountGcsimKeyResolution,
    WARNING_CHARACTER_SIDE_ICON_CACHE_FAILED,
    WARNING_CHARACTER_SOURCE_EMPTY_PRESERVED,
    WARNING_WEAPON_OBSERVED_STACK_NOT_FULL_INVENTORY,
    account_side_icon_local_path,
    build_account_gcsim_key_resolver,
    get_account_character,
    get_account_weapon_observed_stack_by_id,
    get_account_weapon_observed_stack,
    list_account_character_constellations,
    list_account_character_talents,
    list_account_characters,
    list_account_weapon_observed_stacks,
    sync_account_storage_from_sources,
    weapon_observed_stack_fingerprint,
)
from hoyolab_export.artifact_db import connect_db, init_db
from hoyolab_export.character_stats_catalog import (
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
)
from hoyolab_export.character_ascension_bonus import (
    MATCHED_BY_BASE_HP,
    WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH,
)
from hoyolab_export.weapon_stats_catalog import WeaponStatsCatalog, WeaponStatsEntry


class AccountStorageTest(unittest.TestCase):
    def test_schema_initializes_with_existing_artifact_db(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                account_objects = {
                    row["name"]
                    for row in conn.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type IN ('table', 'view')
                        """
                    )
                }

        self.assertIn("artifacts", account_objects)
        self.assertIn("artifact_builds", account_objects)
        self.assertIn("account_characters", account_objects)
        self.assertIn("account_character_talents", account_objects)
        self.assertIn("account_character_constellations", account_objects)
        self.assertIn("account_weapon_observed_stacks", account_objects)
        self.assertIn("character_identity", account_objects)
        self.assertNotIn("account_current_equipped_weapons", account_objects)

    def test_sync_enriches_account_character_identity_from_static_catalogs(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(name="Mona")],
                    account_weapons=[fake_account_weapon(character_name="Mona")],
                    account_character_details=fake_account_details(character_name="Mona"),
                    crop_manifest=fake_crop_manifest(),
                    character_region_entries=[
                        {
                            "entry_page_id": "9001",
                            "normalized_name": "mona",
                            "region_key": "mond",
                            "region_name": "Mondstadt",
                        }
                    ],
                )
                character = get_account_character(conn, 1001)

        self.assertIsNotNone(character)
        self.assertEqual(character.region_key, "mond")
        self.assertIn("hexerei", character.traits)

    def test_sync_marks_traveler_as_standard_even_without_name_match(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(character_id=10000007, name="Custom")],
                    account_weapons=[],
                    account_character_details={"data": {"list": []}},
                    crop_manifest=fake_crop_manifest(),
                )
                character = get_account_character(conn, 10000007)

        self.assertIsNotNone(character)
        self.assertTrue(character.is_standard_5_star)
        self.assertIn("standard_5_star", character.traits)

    def test_sync_stores_clean_character_base_values_not_hoyolab_final_stats(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                summary = sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                )
                character = conn.execute(
                    """
                    SELECT *
                    FROM account_characters
                    WHERE character_id = 1001
                    """
                ).fetchone()
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(summary.characters_upserted, 1)
        self.assertEqual(summary.weapon_observations_seen, 1)
        self.assertEqual(summary.weapon_stacks_upserted, 1)

        self.assertEqual(character["base_hp"], 1000)
        self.assertEqual(character["base_atk"], 200)
        self.assertEqual(character["base_def"], 500)
        self.assertNotEqual(character["base_hp"], 9999)
        self.assertNotEqual(character["base_atk"], 9999)
        self.assertEqual(character["portrait_path"], "assets/hoyolab/characters/test.png")
        self.assertEqual(character["side_icon_url"], "https://example.test/detail-side.png")
        self.assertEqual(character["ascension_bonus_stat_type"], "ATK%")
        self.assertEqual(character["ascension_bonus_value"], 24.0)

        metadata = json.loads(character["source_metadata_json"])
        self.assertTrue(metadata["hoyolab_final_rows_are_non_canonical"])
        self.assertEqual(metadata["authoritative_character_source"], "account_characters_json")
        self.assertEqual(metadata["ascension_bonus"]["selected_source"], MATCHED_BY_BASE_HP)
        self.assertEqual(metadata["ascension_bonus"]["selected_phase"], "after")

        self.assertEqual(len(stacks), 1)
        weapon = stacks[0]
        self.assertEqual(weapon.weapon_id, "2001")
        self.assertEqual(weapon.base_atk, 100)
        self.assertEqual(weapon.secondary_property_type, 23)
        self.assertEqual(weapon.secondary_stat_value, 25.2)
        self.assertEqual(weapon.icon_path, "assets/hoyolab/weapons/test.png")
        self.assertEqual(weapon.known_count, 1)
        self.assertIn(WARNING_WEAPON_OBSERVED_STACK_NOT_FULL_INVENTORY, weapon.warnings)

    def test_sync_stores_validated_gcsim_keys_from_catalog_names(self) -> None:
        def resolver(
            entity_type: str,
            project_id: str,
            catalog_english_name: str,
        ) -> AccountGcsimKeyResolution:
            if entity_type == "character":
                self.assertEqual(project_id, "1001")
                self.assertEqual(catalog_english_name, "Test Hero")
                return AccountGcsimKeyResolution(
                    catalog_english_name=catalog_english_name,
                    gcsim_key="testhero",
                    status="ready",
                    method="exact_normalized_name",
                    warnings=("auto_exact_candidate_not_curated_mapping",),
                )
            if entity_type == "weapon":
                self.assertEqual(project_id, "2001")
                self.assertEqual(catalog_english_name, "Test Spear")
                return AccountGcsimKeyResolution(
                    catalog_english_name=catalog_english_name,
                    gcsim_key="testspear",
                    status="ready",
                    method="exact_normalized_name",
                )
            raise AssertionError(entity_type)

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[
                        fake_account_character(name="Локальный герой")
                    ],
                    account_weapons=[
                        fake_account_weapon(
                            character_name="Локальный герой",
                            weapon_name="Локальное копье",
                        )
                    ],
                    account_character_details=fake_account_details(
                        character_name="Локальный герой",
                        weapon_name="Локальное копье",
                    ),
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                    weapon_stats_catalog=fake_weapon_catalog(),
                    gcsim_key_resolver=resolver,
                )
                character = get_account_character(conn, 1001)
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertIsNotNone(character)
        self.assertEqual(character.name, "Локальный герой")
        self.assertEqual(character.catalog_english_name, "Test Hero")
        self.assertEqual(character.gcsim_character_key, "testhero")
        self.assertEqual(character.gcsim_character_key_status, "ready")
        self.assertEqual(character.gcsim_character_key_method, "exact_normalized_name")
        self.assertNotIn("auto_exact_candidate_not_curated_mapping", character.warnings)
        character_metadata = character.source_metadata or {}
        self.assertEqual(
            character_metadata["gcsim_character_key_resolution"]["gcsim_key"],
            "testhero",
        )

        self.assertEqual(len(stacks), 1)
        weapon = stacks[0]
        self.assertEqual(weapon.name, "Локальное копье")
        self.assertEqual(weapon.catalog_english_name, "Test Spear")
        self.assertEqual(weapon.gcsim_weapon_key, "testspear")
        self.assertEqual(weapon.gcsim_weapon_key_status, "ready")
        self.assertEqual(weapon.gcsim_weapon_key_method, "exact_normalized_name")
        weapon_metadata = weapon.source_metadata or {}
        self.assertEqual(
            weapon_metadata["gcsim_weapon_key_resolution"]["gcsim_key"],
            "testspear",
        )

    def test_sync_marks_catalog_names_not_checked_without_gcsim_resolver(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                    weapon_stats_catalog=fake_weapon_catalog(),
                )
                character = get_account_character(conn, 1001)
                weapon = list_account_weapon_observed_stacks(conn)[0]

        self.assertIsNotNone(character)
        self.assertEqual(character.catalog_english_name, "Test Hero")
        self.assertEqual(character.gcsim_character_key, "")
        self.assertEqual(character.gcsim_character_key_status, "not_checked")
        self.assertEqual(weapon.catalog_english_name, "Test Spear")
        self.assertEqual(weapon.gcsim_weapon_key, "")
        self.assertEqual(weapon.gcsim_weapon_key_status, "not_checked")

    def test_default_gcsim_key_resolver_uses_registry_mapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character_source = root / "characters.go"
            weapon_source = root / "weapons.go"
            character_source.write_text(
                'package shortcut\nvar characterMap = map[string]int{\n"mizuki": 1,\n}\n',
                encoding="utf-8",
            )
            weapon_source.write_text(
                'package shortcut\nvar weaponMap = map[string]int{\n"testspear": 1,\n}\n',
                encoding="utf-8",
            )

            resolver = build_account_gcsim_key_resolver(
                character_source_path=character_source,
                weapon_source_path=weapon_source,
            )
            character = resolver("character", "100999", "Yumemizuki Mizuki")
            weapon = resolver("weapon", "2001", "Test Spear")

        self.assertEqual(character.gcsim_key, "mizuki")
        self.assertEqual(character.status, "ready")
        self.assertEqual(character.method, "contiguous_name_span")
        self.assertEqual(weapon.gcsim_key, "testspear")
        self.assertEqual(weapon.status, "ready")
        self.assertEqual(weapon.method, "exact_normalized_name")

    def test_read_adapter_returns_clean_records_without_current_equipped_semantics(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                )
                characters = list_account_characters(conn)
                character = get_account_character(conn, 1001)
                talents = list_account_character_talents(conn, 1001)
                constellations = list_account_character_constellations(conn, 1001)
                stacks = list_account_weapon_observed_stacks(conn)
                stack = get_account_weapon_observed_stack(
                    conn,
                    stacks[0].weapon_fingerprint,
                )
                stack_by_id = get_account_weapon_observed_stack_by_id(
                    conn,
                    stacks[0].id,
                )

        self.assertEqual([item.character_id for item in characters], ["1001"])
        self.assertIsNotNone(character)
        self.assertEqual(character.to_team_builder_character_ref()["source"], "account_sqlite")
        self.assertEqual(character.base_atk, 200)
        self.assertEqual(len(talents), 2)
        self.assertEqual(len(constellations), 2)
        self.assertEqual(
            character.to_team_builder_character_ref()["side_icon_url"],
            "https://example.test/detail-side.png",
        )
        self.assertEqual(character.to_team_builder_character_ref()["base_atk"], 200)
        self.assertEqual(character.source_metadata["destructive_missing_character_pruning"], False)

        self.assertEqual(len(stacks), 1)
        self.assertIsNotNone(stack)
        self.assertIsNotNone(stack_by_id)
        self.assertEqual(
            stack.to_team_builder_weapon_ref()["source"],
            "account_sqlite_observed_weapon_stack",
        )
        self.assertEqual(stack.to_team_builder_weapon_ref()["base_atk"], 100)
        self.assertEqual(stack.to_team_builder_weapon_ref()["secondary_property_type"], 23)
        self.assertEqual(stack.source_metadata["full_inventory_proven"], False)
        self.assertTrue(stack.source_metadata["weapon_id_is_type_id_not_instance_id"])

    def test_ignored_mannequin_records_are_not_synced_as_account_entities(self) -> None:
        mannequin_id = 10000117
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[
                        fake_account_character(character_id=mannequin_id, name="Mannequin")
                    ],
                    account_weapons=[
                        fake_account_weapon(
                            character_id=mannequin_id,
                            character_name="Mannequin",
                        )
                    ],
                    account_character_details=fake_account_details(
                        character_id=mannequin_id,
                        character_name="Mannequin",
                    ),
                    crop_manifest=fake_crop_manifest(),
                )
                counts = account_row_counts(conn)

        self.assertEqual(counts["account_characters"], 0)
        self.assertEqual(counts["account_character_talents"], 0)
        self.assertEqual(counts["account_weapon_observed_stacks"], 0)

    def test_weapon_icon_path_uses_weapon_identity_not_equipped_character_order(self) -> None:
        account_weapon = fake_account_weapon(weapon_id=15304, weapon_name="Slingshot")
        account_weapon["icon"] = "https://example.test/slingshot.png"
        details = fake_account_details(weapon_id=15304, weapon_name="Slingshot")
        detail_weapon = details["json"]["data"]["list"][0]["weapon"]
        detail_weapon["icon"] = "https://example.test/slingshot.png"
        manifest = {
            "weaponAssets": [
                {
                    "crop": "assets/hoyolab/weapons/slingshot.png",
                    "weapon": {
                        "id": 15304,
                        "name": "Slingshot",
                        "icon": "https://example.test/slingshot.png",
                        "equipped_by": {"id": 1001, "name": "Test Hero"},
                    },
                },
                {
                    "crop": "assets/hoyolab/weapons/skyward_harp.png",
                    "weapon": {
                        "id": 15501,
                        "name": "Skyward Harp",
                        "icon": "https://example.test/skyward_harp.png",
                        "equipped_by": {"id": 1001, "name": "Test Hero"},
                    },
                },
            ]
        }

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[account_weapon],
                    account_character_details=details,
                    crop_manifest=manifest,
                )
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].weapon_id, "15304")
        self.assertEqual(stacks[0].icon_path, "assets/hoyolab/weapons/slingshot.png")

    def test_sync_matches_ascension_bonus_by_hoyolab_base_stat_before_row(self) -> None:
        details = fake_account_details()
        detail = details["json"]["data"]["list"][0]
        detail["base_properties"][0]["base"] = "900"
        detail["base_properties"][1]["base"] = "290"
        detail["base_properties"][2]["base"] = "480"

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                summary = sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=details,
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                )
                character = get_account_character(conn, 1001)

        self.assertIsNotNone(character)
        assert character is not None
        self.assertEqual(character.base_hp, 900)
        self.assertEqual(character.base_atk, 190)
        self.assertEqual(character.base_def, 480)
        self.assertEqual(character.ascension_bonus_stat_type, "ATK%")
        self.assertEqual(character.ascension_bonus_value, 18.0)
        self.assertNotIn("character_ascension_phase_assumed", summary.warnings)
        self.assertNotIn("ascension_phase_unknown", summary.warnings)

    def test_sync_does_not_store_guessed_ascension_bonus_when_base_stat_mismatch(self) -> None:
        details = fake_account_details()
        details["json"]["data"]["list"][0]["base_properties"][0]["base"] = "12345"
        details["json"]["data"]["list"][0]["base_properties"][1]["base"] = "99999"
        details["json"]["data"]["list"][0]["base_properties"][2]["base"] = "88888"

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                summary = sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=details,
                    crop_manifest=fake_crop_manifest(),
                    character_stats_catalog=fake_character_catalog(),
                )
                character = get_account_character(conn, 1001)

        self.assertIsNotNone(character)
        assert character is not None
        self.assertEqual(character.ascension_bonus_stat_type, "ATK%")
        self.assertIsNone(character.ascension_bonus_value)
        self.assertIn(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH, summary.warnings)

    def test_repeated_sync_is_idempotent_for_characters_and_weapon_stacks(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                for _ in range(2):
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[fake_account_weapon()],
                        account_character_details=fake_account_details(),
                    )
                counts = account_row_counts(conn)

        self.assertEqual(counts["account_characters"], 1)
        self.assertEqual(counts["account_character_talents"], 2)
        self.assertEqual(counts["account_weapon_observed_stacks"], 1)

    def test_character_fields_update_in_place_and_new_character_inserts(self) -> None:
        updated_character = fake_account_character()
        updated_character["level"] = 80
        updated_character["constellation"] = 4

        updated_details = deepcopy(fake_account_details())
        detail = updated_details["json"]["data"]["list"][0]
        detail["base"]["level"] = 80
        detail["base"]["actived_constellation_num"] = 4
        detail["weapon"]["main_property"]["final"] = "200"
        detail["base_properties"][1]["base"] = "450"

        second_character = fake_account_character(character_id=1002, name="Second Hero")
        second_details = fake_account_details(character_id=1002, character_name="Second Hero")
        updated_details["json"]["data"]["list"].append(
            second_details["json"]["data"]["list"][0]
        )

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[updated_character, second_character],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=updated_details,
                )
                counts = account_row_counts(conn)
                character = get_account_character(conn, 1001)

        self.assertEqual(counts["account_characters"], 2)
        self.assertIsNotNone(character)
        self.assertEqual(character.level, 80)
        self.assertEqual(character.constellation, 4)
        self.assertEqual(character.base_atk, 250)

    def test_empty_character_source_does_not_wipe_existing_rows(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                )
                summary = sync_account_storage_from_sources(
                    conn,
                    account_characters=[],
                    account_weapons=[],
                    account_character_details={"json": {"data": {"list": []}}},
                )
                counts = account_row_counts(conn)
                character = get_account_character(conn, 1001)

        self.assertEqual(counts["account_characters"], 1)
        self.assertIsNotNone(character)
        self.assertIn(WARNING_CHARACTER_SOURCE_EMPTY_PRESERVED, summary.warnings)

    def test_side_icon_existing_local_file_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "side_icons"
            expected_path = account_side_icon_local_path(
                1001,
                "https://example.test/detail-side.png",
                cache_dir=cache_dir,
            )
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            expected_path.write_bytes(b"cached")

            with temp_artifact_db() as db_path:
                with closing(connect_db(db_path)) as conn:
                    init_db(conn)
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[fake_account_weapon()],
                        account_character_details=fake_account_details(),
                        side_icon_cache_dir=cache_dir,
                    )
                    character = get_account_character(conn, 1001)

        self.assertIsNotNone(character)
        self.assertEqual(character.side_icon_path, str(expected_path))
        self.assertEqual(character.side_icon_url, "https://example.test/detail-side.png")
        self.assertTrue(character.source_metadata["side_icon_cache"]["reused_existing"])

    def test_side_icon_missing_path_can_be_populated_by_downloader(self) -> None:
        calls: list[str] = []

        def fake_downloader(url: str, destination: Path) -> None:
            calls.append(url)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"downloaded")

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "side_icons"
            with temp_artifact_db() as db_path:
                with closing(connect_db(db_path)) as conn:
                    init_db(conn)
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[fake_account_weapon()],
                        account_character_details=fake_account_details(),
                        side_icon_cache_dir=cache_dir,
                        side_icon_downloader=fake_downloader,
                    )
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[fake_account_weapon()],
                        account_character_details=fake_account_details(),
                        side_icon_cache_dir=cache_dir,
                        side_icon_downloader=fake_downloader,
                    )
                    character = get_account_character(conn, 1001)
                    side_icon_exists = (
                        Path(character.side_icon_path).is_file()
                        if character is not None
                        else False
                    )

        self.assertIsNotNone(character)
        self.assertEqual(calls, ["https://example.test/detail-side.png"])
        self.assertTrue(side_icon_exists)
        self.assertEqual(character.side_icon_url, "https://example.test/detail-side.png")

    def test_side_icon_download_failure_does_not_crash_sync(self) -> None:
        def failing_downloader(url: str, destination: Path) -> None:
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmp:
            with temp_artifact_db() as db_path:
                with closing(connect_db(db_path)) as conn:
                    init_db(conn)
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[fake_account_weapon()],
                        account_character_details=fake_account_details(),
                        side_icon_cache_dir=Path(tmp),
                        side_icon_downloader=failing_downloader,
                    )
                    character = get_account_character(conn, 1001)

        self.assertIsNotNone(character)
        self.assertEqual(character.side_icon_path, "")
        self.assertEqual(character.side_icon_url, "https://example.test/detail-side.png")
        self.assertIn(WARNING_CHARACTER_SIDE_ICON_CACHE_FAILED, character.warnings)

    def test_talent_rows_sync_update_and_survive_missing_detail(self) -> None:
        changed_details = deepcopy(fake_account_details())
        first_skill = changed_details["json"]["data"]["list"][0]["skills"][0]
        first_skill["level"] = 9

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=changed_details,
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[],
                    account_character_details={"json": {"data": {"list": []}}},
                )
                talents = conn.execute(
                    """
                    SELECT skill_id, skill_type, name, level, icon_url, is_unlock
                    FROM account_character_talents
                    WHERE character_id = 1001
                    ORDER BY skill_id
                    """
                ).fetchall()
                character = get_account_character(conn, 1001)

        self.assertEqual(len(talents), 2)
        self.assertEqual(talents[0]["skill_id"], 3001)
        self.assertEqual(talents[0]["level"], 9)
        self.assertEqual(talents[0]["skill_type"], 1)
        self.assertEqual(talents[0]["is_unlock"], 1)
        self.assertEqual(talents[0]["icon_url"], "https://example.test/skill-normal.png")
        self.assertIsNotNone(character)
        self.assertEqual(len(character.talents), 2)
        self.assertEqual(character.talents[0].level, 9)

    def test_constellation_rows_sync_for_talent_normalization(self) -> None:
        changed_details = deepcopy(fake_account_details())
        first_constellation = changed_details["json"]["data"]["list"][0][
            "constellations"
        ][0]
        first_constellation["effect"] = (
            "Changed <color=#FFD780FF>Normal Skill</color> text."
        )

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                summary = sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=fake_account_details(),
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[fake_account_weapon()],
                    account_character_details=changed_details,
                )
                constellations = list_account_character_constellations(conn, 1001)

        self.assertEqual(summary.constellations_seen, 2)
        self.assertEqual(summary.constellations_upserted, 2)
        self.assertEqual(len(constellations), 2)
        self.assertEqual([item.pos for item in constellations], [3, 5])
        self.assertTrue(constellations[0].is_actived)
        self.assertIn("Changed", constellations[0].effect)
        metadata = constellations[0].source_metadata or {}
        self.assertTrue(metadata["stored_for_gcsim_talent_normalization_only"])

    def test_identical_weapon_fingerprints_in_one_sync_increase_known_count(self) -> None:
        second_character = fake_account_character(character_id=1002, name="Second Hero")
        weapon_one = fake_account_weapon()
        weapon_two = fake_account_weapon(character_id=1002, character_name="Second Hero")
        details = fake_account_details()
        details["json"]["data"]["list"].append(
            fake_account_details(character_id=1002, character_name="Second Hero")[
                "json"
            ]["data"]["list"][0]
        )

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(), second_character],
                    account_weapons=[weapon_one, weapon_two],
                    account_character_details=details,
                )
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].known_count, 2)

    def test_later_lower_or_zero_observed_count_does_not_decrease_known_count(self) -> None:
        second_character = fake_account_character(character_id=1002, name="Second Hero")
        weapon_one = fake_account_weapon()
        weapon_two = fake_account_weapon(character_id=1002, character_name="Second Hero")
        details = fake_account_details()
        details["json"]["data"]["list"].append(
            fake_account_details(character_id=1002, character_name="Second Hero")[
                "json"
            ]["data"]["list"][0]
        )

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(), second_character],
                    account_weapons=[weapon_one, weapon_two],
                    account_character_details=details,
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[weapon_one],
                    account_character_details=fake_account_details(),
                )
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character()],
                    account_weapons=[],
                    account_character_details={"json": {"data": {"list": []}}},
                )
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].known_count, 2)

    def test_different_weapon_fingerprint_creates_separate_stack(self) -> None:
        second_character = fake_account_character(character_id=1002, name="Second Hero")
        weapon_one = fake_account_weapon()
        weapon_two = fake_account_weapon(character_id=1002, character_name="Second Hero")
        details = fake_account_details()
        changed_detail = fake_account_details(character_id=1002, character_name="Second Hero")
        changed_weapon = changed_detail["json"]["data"]["list"][0]["weapon"]
        changed_weapon["level"] = 80
        changed_weapon["promote_level"] = 5
        changed_weapon["main_property"]["final"] = "200"
        details["json"]["data"]["list"].append(changed_detail["json"]["data"]["list"][0])

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(), second_character],
                    account_weapons=[weapon_one, weapon_two],
                    account_character_details=details,
                )
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(len(stacks), 2)
        self.assertEqual(sorted(stack.known_count for stack in stacks), [1, 1])

    def test_detail_fallback_weapon_observations_do_not_multiply_across_syncs(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                for _ in range(2):
                    sync_account_storage_from_sources(
                        conn,
                        account_characters=[fake_account_character()],
                        account_weapons=[],
                        account_character_details=fake_account_details(),
                    )
                counts = account_row_counts(conn)
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(counts["account_weapon_observed_stacks"], 1)
        self.assertEqual(stacks[0].known_count, 1)

    def test_weapon_fingerprint_excludes_equipped_character_and_display_fields(self) -> None:
        first = fake_account_weapon()
        second = fake_account_weapon(
            character_id=1002,
            character_name="Different Owner",
            weapon_name="Localized Other Name",
        )
        details = fake_account_details()
        second_details = fake_account_details(
            character_id=1002,
            character_name="Different Owner",
            weapon_name="Localized Other Name",
        )
        second_detail = second_details["json"]["data"]["list"][0]
        second_detail["weapon"]["desc"] = "Different description text."
        second_detail["weapon"]["icon"] = "https://example.test/different-icon.png"
        details["json"]["data"]["list"].append(second_detail)

        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[
                        fake_account_character(),
                        fake_account_character(character_id=1002, name="Different Owner"),
                    ],
                    account_weapons=[first, second],
                    account_character_details=details,
                )
                stacks = list_account_weapon_observed_stacks(conn)

        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].known_count, 2)

    def test_numeric_canonicalization_prevents_format_duplicate_fingerprints(self) -> None:
        first = weapon_observed_stack_fingerprint(
            weapon_id=2001,
            rarity=4,
            level=70,
            refinement=5,
            promote_level=4,
            base_atk="100.0",
            secondary_property_type=23,
            secondary_stat_value="25.20%",
        )
        second = weapon_observed_stack_fingerprint(
            weapon_id="2001",
            rarity="4",
            level="70",
            refinement="5",
            promote_level="4",
            base_atk="100",
            secondary_property_type="23",
            secondary_stat_value="25.2%",
        )
        self.assertEqual(first, second)


class temp_artifact_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "artifacts.db"

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def account_row_counts(conn) -> dict[str, int]:
    result = {}
    for table in (
        "account_characters",
        "account_character_talents",
        "account_character_constellations",
        "account_weapon_observed_stacks",
    ):
        result[table] = int(
            conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        )
    return result


def fake_account_character(
    *,
    character_id: int = 1001,
    name: str = "Test Hero",
) -> dict:
    return {
        "id": character_id,
        "name": name,
        "element": "Pyro",
        "rarity": 4,
        "level": 70,
        "constellation": 6,
        "weapon_type": 13,
        "weapon_type_name": "polearm",
        "icon": "https://example.test/hero.png",
        "side_icon": "https://example.test/hero-side.png",
    }


def fake_account_weapon(
    *,
    character_id: int = 1001,
    character_name: str = "Test Hero",
    weapon_id: int = 2001,
    weapon_name: str = "Test Spear",
) -> dict:
    return {
        "id": weapon_id,
        "name": weapon_name,
        "rarity": 4,
        "type": 13,
        "type_name": "polearm",
        "level": 70,
        "refinement": 5,
        "icon": "https://example.test/spear.png",
        "equipped_by": {
            "id": character_id,
            "name": character_name,
        },
    }


def fake_account_details(
    *,
    character_id: int = 1001,
    character_name: str = "Test Hero",
    weapon_id: int = 2001,
    weapon_name: str = "Test Spear",
) -> dict:
    return {
        "json": {
            "data": {
                "avatar_wiki": {
                    str(character_id): "https://wiki.example/entry/9001",
                },
                "weapon_wiki": {
                    str(weapon_id): "https://wiki.example/entry/9101",
                },
                "list": [
                    {
                        "base": {
                            "id": character_id,
                            "name": character_name,
                            "element": "Pyro",
                            "level": 70,
                            "rarity": 4,
                            "actived_constellation_num": 6,
                            "weapon_type": 13,
                            "weapon_type_name": "polearm",
                            "icon": "https://example.test/detail-hero.png",
                            "side_icon": "https://example.test/detail-side.png",
                        },
                        "base_properties": [
                            {
                                "property_type": 2000,
                                "base": "1000",
                                "add": "8999",
                                "final": "9999",
                            },
                            {
                                "property_type": 2001,
                                "base": "300",
                                "add": "9699",
                                "final": "9999",
                            },
                            {
                                "property_type": 2002,
                                "base": "500",
                                "add": "9499",
                                "final": "9999",
                            },
                        ],
                        "extra_properties": [
                            {
                                "property_type": 20,
                                "base": "5%",
                                "add": "95%",
                                "final": "100%",
                            }
                        ],
                        "element_properties": [],
                        "selected_properties": [],
                        "weapon": {
                            "id": weapon_id,
                            "name": weapon_name,
                            "rarity": 4,
                            "type": 13,
                            "type_name": "polearm",
                            "level": 70,
                            "affix_level": 5,
                            "promote_level": 4,
                            "icon": "https://example.test/detail-spear.png",
                            "desc": "Reference-only passive text.",
                            "main_property": {
                                "property_type": 4,
                                "base": "",
                                "add": "",
                                "final": "100",
                            },
                            "sub_property": {
                                "property_type": 23,
                                "base": "",
                                "add": "",
                                "final": "25.2%",
                            },
                        },
                        "skills": [
                            {
                                "skill_id": 3001,
                                "name": "Normal Skill",
                                "level": 8,
                                "skill_type": 1,
                                "icon": "https://example.test/skill-normal.png",
                                "is_unlock": True,
                                "desc": "Effect text is source-only and not stored.",
                                "skill_affix_list": [],
                            },
                            {
                                "skill_id": 3002,
                                "name": "Elemental Skill",
                                "level": 6,
                                "skill_type": 2,
                                "icon": "https://example.test/skill-elemental.png",
                                "is_unlock": True,
                                "desc": "Effect text is source-only and not stored.",
                                "skill_affix_list": [],
                            },
                        ],
                        "constellations": [
                            {
                                "pos": 3,
                                "name": "Talent C3",
                                "effect": (
                                    "Increases <color=#FFD780FF>Normal Skill</color> "
                                    "by 3."
                                ),
                                "is_actived": True,
                            },
                            {
                                "pos": 5,
                                "name": "Talent C5",
                                "effect": (
                                    "Increases <color=#FFD780FF>Elemental Skill</color> "
                                    "by 3."
                                ),
                                "is_actived": False,
                            },
                        ],
                    }
                ],
            }
        }
    }


def fake_crop_manifest() -> dict:
    return {
        "characterAssets": [
            {
                "crop": "assets/hoyolab/characters/test.png",
                "character": {
                    "id": 1001,
                    "name": "Test Hero",
                },
            }
        ],
        "weaponAssets": [
            {
                "crop": "assets/hoyolab/weapons/test.png",
                "weapon": {
                    "id": 2001,
                    "name": "Test Spear",
                    "equipped_by": {
                        "id": 1001,
                        "name": "Test Hero",
                    },
                },
            }
        ],
    }


def fake_character_catalog() -> CharacterBaseStatsCatalog:
    return CharacterBaseStatsCatalog(
        entries=(
            CharacterBaseStatsEntry.from_dict(
                {
                    "entry_page_id": "9001",
                    "name": "Test Hero",
                    "lang": "en-us",
                    "rows": [
                        {
                            "level_key": "Lv.70",
                            "base_hp": {
                                "before": "900",
                                "after": "1000",
                            },
                            "base_atk": {
                                "before": "190",
                                "after": "200",
                            },
                            "base_def": {
                                "before": "480",
                                "after": "500",
                            },
                            "ascension_bonus_stat_type": "ATK%",
                            "ascension_bonus": {
                                "before": "18%",
                                "after": "24%",
                            },
                        }
                    ],
                }
            ),
        ),
    )


def fake_weapon_catalog() -> WeaponStatsCatalog:
    return WeaponStatsCatalog(
        entries=(
            WeaponStatsEntry.from_dict(
                {
                    "entry_page_id": "9101",
                    "name": "Test Spear",
                    "lang": "en-us",
                    "rows": [
                        {
                            "level_key": "Lv.70",
                            "base_atk": {
                                "before": "90",
                                "after": "100",
                            },
                            "secondary_stat_type": "Energy Recharge",
                            "secondary_stat_value": "25.2%",
                        }
                    ],
                }
            ),
        ),
    )
