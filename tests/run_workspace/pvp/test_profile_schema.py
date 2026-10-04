from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

from hoyolab_export.account_storage import (
    list_account_characters,
    list_account_weapon_observed_stacks,
)
from hoyolab_export.artifact_db import (
    get_artifact_build_slots,
    get_artifact_build_targets,
    init_db,
    list_build_presets,
)
from hoyolab_export.display_stat_effects import (
    get_weapon_passive_tooltip,
    list_weapon_display_stat_effects,
)
from run_workspace.pvp.deck_preset import PvpDeckPreset
from run_workspace.pvp import profile_schema as profile_schema_module
from run_workspace.pvp.profile_schema import (
    ProfileSchemaError,
    create_profile_slice,
    materialize_runtime_db,
    validate_profile_slice,
)
from run_workspace.pvp.weapon_identity import WeaponObservedStackRef


class PvpProfileSchemaTest(unittest.TestCase):
    def test_slice_is_narrow_remaps_local_ids_and_filters_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            preset = _preset()

            counts = create_profile_slice(source, portable, (preset,))

            self.assertEqual(counts["character_count"], 12)
            self.assertEqual(counts["weapon_stack_count"], 1)
            self.assertEqual(counts["weapon_effect_count"], 1)
            self.assertEqual(counts["weapon_tooltip_count"], 2)
            self.assertEqual(counts["artifact_count"], 2)
            self.assertEqual(counts["build_count"], 2)
            self.assertNotIn("artifact_set_piece_icon_count", counts)
            self.assertEqual(validate_profile_slice(portable, (preset,), counts), counts)

            with closing(sqlite3.connect(portable)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    if not str(row[0]).startswith("sqlite_")
                }
                self.assertEqual(
                    tables,
                    {
                        "account_characters", "account_character_talents",
                        "account_character_constellations", "account_weapon_observed_stacks",
                        "weapon_display_stat_effects", "weapon_passive_tooltips",
                        "character_identity", "artifact_sets", "artifact_set_names",
                        "artifact_set_bonus_descriptions", "artifacts", "artifact_substats",
                        "artifact_builds", "artifact_build_slots", "artifact_build_targets",
                        "artifact_build_gcsim_targets",
                    },
                )
                for table in tables:
                    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                    self.assertFalse(
                        cols & {
                            "icon_url", "side_icon_url", "local_path", "portrait_path",
                            "source_metadata_json", "warnings_json", "notes", "tags_json",
                            "first_seen_at", "last_seen_at", "updated_at",
                        },
                        table,
                    )
                self.assertEqual(
                    conn.execute("SELECT id,relic_id,set_id FROM artifacts ORDER BY id").fetchall(),
                    [(1, 701, 203), (2, None, None)],
                )
                self.assertEqual(
                    conn.execute("SELECT hoyolab_set_id,artiscan_set_key FROM artifact_sets").fetchall(),
                    [(3001, "set-key-fixture")],
                )
                self.assertEqual(
                    conn.execute("SELECT id,weapon_fingerprint FROM account_weapon_observed_stacks").fetchall(),
                    [(1, "fp-a")],
                )
                self.assertEqual(
                    conn.execute("SELECT weapon_id,refinement,stat_key,value FROM weapon_display_stat_effects").fetchall(),
                    [(11501, 1, "ATK_PERCENT", 12.0)],
                )
                self.assertEqual(
                    conn.execute("SELECT weapon_id,lang,passive_text FROM weapon_passive_tooltips ORDER BY lang").fetchall(),
                    [(11501, "en-us", "ATK is increased by 12%."),
                     (11501, "ru-ru", "Сила атаки повышается на 12%.")],
                )
                self.assertEqual(
                    conn.execute("SELECT id,name FROM artifact_builds ORDER BY id").fetchall(),
                    [(1, "Build Direct"), (2, "Build GCSIM")],
                )
                self.assertEqual(
                    conn.execute("SELECT character_id FROM artifact_build_targets").fetchall(),
                    [(3000,)],
                )
                self.assertEqual(
                    conn.execute("SELECT gcsim_character_key FROM artifact_build_gcsim_targets").fetchall(),
                    [("sim-3001",)],
                )
                self.assertEqual(
                    conn.execute("SELECT value FROM artifact_substats ORDER BY artifact_id").fetchall(),
                    [("5.8%",), ("21",)],
                )
                ddl = " ".join(
                    str(row[0] or "")
                    for row in conn.execute("SELECT sql FROM sqlite_master")
                ).casefold()
                self.assertNotIn("icon_url", ddl)
                self.assertNotIn("raw", ddl)
                self.assertNotIn("history", ddl)
                db_bytes = portable.read_bytes()
                for secret in (b"signed-character-url", b"signed-talent-url", b"signed-weapon-url", b"signed-piece-url"):
                    self.assertNotIn(secret, db_bytes)

    def test_materialized_runtime_db_has_reader_defaults_and_managed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            runtime = root / "runtime.db"
            _create_source(source)
            preset = _preset()
            create_profile_slice(source, portable, (preset,))
            char_asset = root / "assets" / "character-3000.png"
            weapon_asset = root / "assets" / "weapon-11501.png"

            materialize_runtime_db(
                portable,
                runtime,
                {str(value): char_asset for value in range(3000, 3012)},
                {"11501": weapon_asset},
            )

            with closing(sqlite3.connect(runtime)) as conn:
                conn.row_factory = sqlite3.Row
                runtime_characters = list_account_characters(conn)
                runtime_weapons = list_account_weapon_observed_stacks(conn)
                runtime_builds = list_build_presets(conn)
                character_record = next(item for item in runtime_characters if item.character_id == "3000")
                weapon_record = runtime_weapons[0]
                direct_build = next(item for item in runtime_builds if item["name"] == "Build Direct")
                direct_build_id = direct_build["id"]
                self.assertEqual(character_record.name, "Fixture 3000")
                self.assertEqual(character_record.icon_url, "")
                self.assertEqual(character_record.side_icon_path, str(char_asset.resolve()))
                self.assertEqual(len(character_record.talents), 1)
                self.assertEqual(weapon_record.weapon_id, "11501")
                self.assertEqual(weapon_record.icon_url, "")
                self.assertEqual(weapon_record.icon_path, str(weapon_asset.resolve()))
                self.assertEqual(
                    list_weapon_display_stat_effects(conn, weapon_id=11501, refinement=1)[0]["value"],
                    12.0,
                )
                self.assertEqual(
                    get_weapon_passive_tooltip(conn, weapon_id=11501, language="ru-ru")["passive_name"],
                    "Пассивный эффект",
                )
                self.assertEqual(len(runtime_builds), 2)
                self.assertEqual(get_artifact_build_slots(conn, direct_build_id)[0]["artifact_id"], 1)
                self.assertEqual(get_artifact_build_targets(conn, direct_build_id)[0]["character_id"], 3000)
                character = conn.execute(
                    "SELECT * FROM account_characters WHERE character_id=3000"
                ).fetchone()
                weapon = conn.execute(
                    "SELECT * FROM account_weapon_observed_stacks WHERE weapon_id='11501'"
                ).fetchone()
                identity = conn.execute(
                    "SELECT * FROM character_identity WHERE character_id=3000"
                ).fetchone()
                artifact = conn.execute("SELECT * FROM artifacts ORDER BY id LIMIT 1").fetchone()
                self.assertEqual(character["icon_url"], "")
                self.assertEqual(character["side_icon_url"], "")
                self.assertEqual(character["side_icon_path"], str(char_asset.resolve()))
                self.assertEqual(character["source_metadata_json"], "{}")
                self.assertEqual(character["warnings_json"], "[]")
                self.assertEqual(weapon["icon_url"], "")
                self.assertEqual(weapon["icon_path"], str(weapon_asset.resolve()))
                self.assertEqual(weapon["base_atk_raw"], "")
                self.assertEqual(weapon["warnings_json"], "[]")
                self.assertEqual(identity["source_metadata_json"], "{}")
                self.assertEqual(artifact["relic_id"], 701)
                self.assertEqual(artifact["set_id"], 203)
                self.assertEqual(
                    conn.execute("SELECT count(*) FROM artifact_set_piece_icons").fetchone()[0],
                    0,
                )
            for private_marker in (b"PRIVATE-NOTE", b"source_metadata_json", b"auth", b"first_seen_at"):
                self.assertNotIn(private_marker, portable.read_bytes())

    def test_validation_rejects_extra_sqlite_objects_and_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            preset = _preset()
            create_profile_slice(source, portable, (preset,))

            with closing(sqlite3.connect(portable)) as conn:
                conn.execute("ANALYZE")
                conn.commit()
            with self.assertRaises(ProfileSchemaError):
                validate_profile_slice(portable, (preset,))

    def test_validation_rejects_invalid_storage_ranges_and_row_population(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            preset = _preset()

            mutations = (
                ("UPDATE account_characters SET base_hp=? WHERE character_id=3000", (float("inf"),)),
                ("UPDATE account_characters SET name=CAST(x'ff' AS BLOB) WHERE character_id=3000", ()),
                ("UPDATE account_characters SET base_hp=-1 WHERE character_id=3000", ()),
                (
                    "INSERT INTO account_character_constellations(character_id,pos) VALUES (3000,7)",
                    (),
                ),
                ("UPDATE artifact_substats SET slot_index=4 WHERE artifact_id=1", ()),
            )
            for index, (statement, values) in enumerate(mutations):
                with self.subTest(mutation=index):
                    create_profile_slice(source, portable, (preset,))
                    with closing(sqlite3.connect(portable)) as conn:
                        conn.execute(statement, values)
                        conn.commit()
                    with self.assertRaises(ProfileSchemaError):
                        validate_profile_slice(portable, (preset,))

            create_profile_slice(source, portable, (preset,))
            with patch.dict(profile_schema_module._ROW_LIMITS, {"account_characters": 11}):
                with self.assertRaises(ProfileSchemaError):
                    validate_profile_slice(portable, (preset,))

            create_profile_slice(source, portable, (preset,))
            with closing(sqlite3.connect(portable)) as conn:
                conn.execute("UPDATE account_characters SET name=? WHERE character_id=3000", (r"C:\\Users\\private\\Alice",))
                conn.commit()
            with self.assertRaises(ProfileSchemaError):
                validate_profile_slice(portable, (preset,))

    def test_deck_validation_rejects_unknown_rulesets_and_duplicate_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            _create_source(source)
            preset = _preset()
            with self.assertRaises(ProfileSchemaError):
                create_profile_slice(
                    source,
                    root / "bad-ruleset.db",
                    (replace(preset, ruleset_id="future"),),
                )
            duplicate_ref = WeaponObservedStackRef(weapon_fingerprint="fp-a")
            duplicate = PvpDeckPreset(
                deck_id="duplicate-ref",
                name="Duplicate ref",
                character_ids=preset.character_ids,
                weapon_refs=(duplicate_ref, duplicate_ref),
            )
            with self.assertRaises(ProfileSchemaError):
                create_profile_slice(source, root / "duplicate.db", (duplicate,))

    def test_slice_rejects_unreferenced_weapon_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            preset = _preset()
            create_profile_slice(source, portable, (preset,))
            with closing(sqlite3.connect(portable)) as conn:
                conn.execute(
                    """
                    INSERT INTO account_weapon_observed_stacks (
                        id,weapon_fingerprint,weapon_id,name,weapon_type,weapon_type_name,
                        rarity,level,refinement,known_count
                    ) VALUES (2,'unreferenced','13501','Other Weapon',1,'Sword',5,90,1,1)
                    """
                )
                conn.commit()
            with self.assertRaises(ProfileSchemaError):
                validate_profile_slice(portable, (preset,))

    def test_weapon_derived_rows_reject_foreign_nonfinite_unknown_and_private_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            preset = _preset()
            statements = (
                ("UPDATE weapon_display_stat_effects SET weapon_id=13501", ()),
                ("UPDATE weapon_display_stat_effects SET refinement=2", ()),
                ("UPDATE weapon_display_stat_effects SET value=?", (float("inf"),)),
                ("UPDATE weapon_display_stat_effects SET stat_key='UNKNOWN_STAT'", ()),
                ("UPDATE weapon_passive_tooltips SET weapon_id=13501", ()),
                ("UPDATE weapon_passive_tooltips SET passive_text='C:\\private\\secret' WHERE lang='en-us'", ()),
                ("UPDATE weapon_passive_tooltips SET lang='invalid language' WHERE lang='ru-ru'", ()),
            )
            for statement, values in statements:
                with self.subTest(statement=statement):
                    create_profile_slice(source, portable, (preset,))
                    with closing(sqlite3.connect(portable)) as conn:
                        conn.execute(statement, values)
                        conn.commit()
                    with self.assertRaises(ProfileSchemaError):
                        validate_profile_slice(portable, (preset,))

    def test_missing_source_weapon_derived_tables_export_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.db"
            portable = root / "profile.db"
            _create_source(source)
            with closing(sqlite3.connect(source)) as conn:
                conn.execute("DROP TABLE weapon_display_stat_effects")
                conn.execute("DROP TABLE weapon_passive_tooltips")
                conn.commit()
            counts = create_profile_slice(source, portable, (_preset(),))
            self.assertEqual(counts["weapon_effect_count"], 0)
            self.assertEqual(counts["weapon_tooltip_count"], 0)


def _preset() -> PvpDeckPreset:
    return PvpDeckPreset(
        deck_id="fixture-deck",
        name="Fixture Deck",
        character_ids=tuple(str(value) for value in range(3000, 3012)),
        weapon_refs=(WeaponObservedStackRef(weapon_fingerprint="fp-a"),),
    )


def _create_source(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        for character_id in range(3000, 3012):
            gcsim = "sim-3001" if character_id == 3001 else ""
            status = "ready" if gcsim else ""
            conn.execute(
                """
                INSERT INTO account_characters (
                    character_id,name,element,rarity,level,constellation,weapon_type,
                    weapon_type_name,icon_url,side_icon_url,gcsim_character_key,
                    gcsim_character_key_status
                ) VALUES (?,?, 'Electro',5,90,0,1,NULL,?,?,?,?)
                """,
                (character_id, f"Fixture {character_id}", "signed-character-url", "signed-side-url", gcsim, status),
            )
            conn.execute(
                """
                INSERT INTO account_character_talents (
                    character_id,skill_id,skill_type,name,level,icon_url
                ) VALUES (?,1,1,'Normal Attack',9,'signed-talent-url')
                """,
                (character_id,),
            )
            conn.execute(
                """
                INSERT INTO character_identity (
                    character_id,region_key,traits_json,is_standard_5_star
                ) VALUES (?, 'fixture', '["hexerei"]', 1)
                """,
                (character_id,),
            )

        conn.execute(
            """
            INSERT INTO account_weapon_observed_stacks (
                weapon_fingerprint,weapon_id,name,weapon_type,weapon_type_name,
                rarity,level,refinement,known_count,icon_url
            ) VALUES ('fp-a',11501,'Fixture Sword',1,'Sword',5,90,1,2,'signed-weapon-url')
            """
        )
        conn.execute(
            """
            INSERT INTO account_weapon_observed_stacks (
                weapon_fingerprint,weapon_id,name,weapon_type,weapon_type_name,
                rarity,level,refinement,known_count
            ) VALUES ('bad-unselected',13501,'',1,'Polearm',5,90,1,0)
            """
        )
        conn.executemany(
            """INSERT INTO weapon_display_stat_effects (
                weapon_id, refinement, stat_key, value, value_type
            ) VALUES (?,?,?,?,?)""",
            [
                (11501, 1, "ATK_PERCENT", 12.0, "percent_points"),
                (11501, 2, "ATK_PERCENT", 15.0, "percent_points"),
                (13501, 1, "CRIT_RATE", 5.0, "percent_points"),
            ],
        )
        conn.executemany(
            """INSERT INTO weapon_passive_tooltips (
                weapon_id, lang, passive_name, passive_text
            ) VALUES (?,?,?,?)""",
            [
                (11501, "en-us", "Passive", "ATK is increased by 12%."),
                (11501, "ru-ru", "Пассивный эффект", "Сила атаки повышается на 12%."),
                (13501, "en-us", "Unrelated", "Unrelated passive"),
            ],
        )
        conn.execute(
            """
            INSERT INTO artifact_sets (
                set_uid,hoyowiki_entry_id,hoyolab_set_id,artiscan_set_key,
                display_name,fallback_name,updated_at
            ) VALUES ('fixture-set','hoyowiki-fixture',3001,'set-key-fixture',
                     'Fixture Set','Fixture Set','2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO artifact_set_piece_icons(set_uid,pos,icon_url,local_path,updated_at)
            VALUES ('fixture-set',1,'signed-piece-url','','2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO artifact_set_names(set_uid,lang,name,normalized_name,updated_at)
            VALUES ('fixture-set','en-us','Fixture Set','fixture set','2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO artifact_set_bonus_descriptions(
                set_uid,lang,piece_count,description,source,updated_at
            ) VALUES ('fixture-set','en-us',2,'Fixture bonus','hoyowiki','2026-01-01')
            """
        )
        for artifact_id, relic_id, set_id, pos, stat_value in (
            (40, 701, 203, 1, "5.8%"),
            (90, 0, 0, 2, "21"),
        ):
            conn.execute(
                """
                INSERT INTO artifacts (
                    id,fingerprint,relic_id,name,set_id,set_uid,set_name,pos,pos_name,
                    rarity,level,main_property_type,main_property_name,main_property_value,
                    first_seen_at,last_seen_at
                ) VALUES (?,?,?,?,?,'fixture-set','Fixture Set',?,'Fixture',5,20,1,'ATK',?,
                         '2026-01-01','2026-01-01')
                """,
                (
                    artifact_id, f"artifact-fp-{artifact_id}", relic_id,
                    f"Artifact {artifact_id}", set_id, pos, stat_value,
                ),
            )
            conn.execute(
                """
                INSERT INTO artifact_substats(artifact_id,slot_index,property_type,property_name,value,times)
                VALUES (?,0,1,'ATK%',?,2)
                """,
                (artifact_id, stat_value),
            )
        conn.execute(
            """
            INSERT INTO artifact_builds(id,name,character_id,character_name,notes,created_at,updated_at)
            VALUES (40,'Build Direct',3000,'Fixture 3000','PRIVATE-NOTE','2026-01-01','2026-01-01')
            """
        )
        conn.execute(
            "INSERT INTO artifact_build_targets(build_id,target_type,character_id,character_name) VALUES (40,'character',3000,'Fixture 3000')"
        )
        conn.execute(
            "INSERT INTO artifact_build_slots(build_id,pos,artifact_id) VALUES (40,1,40)"
        )
        conn.execute(
            """
            INSERT INTO artifact_builds(id,name,created_at,updated_at)
            VALUES (90,'Build GCSIM','2026-01-01','2026-01-01')
            """
        )
        conn.execute(
            "INSERT INTO artifact_build_gcsim_targets(build_id,gcsim_character_key,character_name) VALUES (90,'sim-3001','Fixture 3001')"
        )
        conn.execute(
            """
            INSERT INTO artifact_builds(id,name,created_at,updated_at)
            VALUES (100,'Build Universal','2026-01-01','2026-01-01')
            """
        )
        conn.execute(
            "INSERT INTO artifact_build_targets(build_id,target_type,character_id) VALUES (100,'universal',NULL)"
        )
        conn.execute(
            """
            INSERT INTO artifact_builds(id,name,created_at,updated_at)
            VALUES (110,'Build Unrelated','2026-01-01','2026-01-01')
            """
        )
        conn.execute(
            "INSERT INTO artifact_build_targets(build_id,target_type,character_id) VALUES (110,'character',9999)"
        )
        conn.commit()


if __name__ == "__main__":
    unittest.main()
