from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_db import (
    calculate_raw_build_summary,
    connect_db,
    create_build_preset,
    init_db,
)

from run_workspace.gcsim.readiness_summary import (
    GROUP_ARTIFACT_SETS,
    GROUP_MISSING_WEAPONS,
    build_gcsim_readiness_summary,
)
from run_workspace.gcsim.selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
    build_selected_team_full_config_report,
    build_selected_team_payload,
    run_selected_team_dps_dummy_artifact,
)
from run_workspace.gcsim.settings import GcsimRunSettings
from tests.run_workspace.gcsim.test_gcsim_account_prepared_config import (
    seeded_account_config_db,
)


class GcsimSelectedTeamConfigTest(unittest.TestCase):
    def test_virtual_slot_reaches_config_boundary_and_fails_closed_without_profile(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_selected_team_payload(
                db_path=db_path,
                selected_team={
                    "slots": [
                        {
                            "slot_index": 0,
                            "gcsim_virtual_override": {
                                "schema_version": 1,
                                "source": "virtual_gcsim_slot_override",
                                "character": {
                                    "gcsim_key": "testhero",
                                    "name": "TestHero",
                                    "weapon_type": "polearm",
                                    "constellation": 3,
                                },
                                "weapon": {
                                    "gcsim_key": "testspear",
                                    "name": "TestSpear",
                                    "weapon_type": "polearm",
                                    "refinement": 4,
                                },
                            },
                        }
                    ]
                },
            )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.characters), 1)
        detail = result.characters[0]
        self.assertFalse(detail.character_found)
        self.assertTrue(detail.character_key_ready)
        self.assertEqual(detail.weapon_selection_method, "virtual_gcsim_catalog")
        self.assertEqual(
            result.payload["characters"][0]["mapping"]["gcsim_key"],
            "testhero",
        )
        self.assertEqual(result.payload["characters"][0]["constellation"], 3)
        self.assertEqual(result.payload["characters"][0]["weapon"]["refinement"], 4)
        self.assertIn(
            "virtual_gcsim_profile_incomplete",
            [issue.status for issue in result.issues],
        )

    def test_complete_virtual_profile_generates_character_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "artifacts.db"
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = _seed_virtual_artifact_build(conn)
                conn.commit()
            shell_path = _write_shell(root, active="testhero")
            report = build_selected_team_full_config_report(
                db_path=db_path,
                selected_team={
                    "slots": [
                        {
                            "slot_index": 0,
                            "gcsim_virtual_override": {
                                "schema_version": 1,
                                "source": "virtual_gcsim_slot_override",
                                "character": {
                                    "gcsim_key": "testhero",
                                    "name": "TestHero",
                                    "weapon_type": "polearm",
                                    "constellation": 3,
                                    "level": 90,
                                    "promote_level": 6,
                                    "talents": {
                                        "normal": 8,
                                        "skill": 10,
                                        "burst": 9,
                                        "source_order_confirmed": True,
                                        "source": "virtual_gcsim_profile_editor",
                                    },
                                },
                                "weapon": {
                                    "gcsim_key": "testspear",
                                    "name": "TestSpear",
                                    "weapon_type": "polearm",
                                    "refinement": 4,
                                    "level": 90,
                                    "promote_level": 6,
                                },
                                "artifact_build_id": build_id,
                                # Derived presentation metadata must not be
                                # allowed to override the explicit profile.
                                "missing_profile_fields": [
                                    "character_level",
                                    "character_talents",
                                    "weapon_level",
                                ],
                            },
                        }
                    ]
                },
                team_index=0,
                rotation_shell_path=shell_path,
                run_dir=root / "run",
            )
            config_text = Path(report.config_path).read_text(encoding="utf-8")

        self.assertTrue(report.ready)
        self.assertIn("testhero char lvl=90/90 cons=3 talent=8,10,9;", config_text)
        self.assertIn(
            'testhero add weapon="testspear" refine=4 lvl=90/90;',
            config_text,
        )
        self.assertIn("testhero add stats ", config_text)

    def test_theory_virtual_profile_uses_non_owned_baseline_without_saved_build_or_set(self) -> None:
        with seeded_account_config_db() as db_path, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shell_path = _write_shell(root, active="testhero")
            report = build_selected_team_full_config_report(
                db_path=db_path,
                selected_team={
                    "slots": [
                        {
                            "slot_index": 0,
                            "gcsim_virtual_override": {
                                "schema_version": 1,
                                "source": "virtual_gcsim_slot_override",
                                "character": {
                                    "gcsim_key": "testhero",
                                    "name": "TestHero",
                                    "weapon_type": "polearm",
                                    "constellation": 0,
                                    "level": 80,
                                    "promote_level": 6,
                                    "talents": {
                                        "normal": 10,
                                        "skill": 10,
                                        "burst": 10,
                                        "source_order_confirmed": True,
                                    },
                                },
                                "weapon": {
                                    "gcsim_key": "testspear",
                                    "name": "TestSpear",
                                    "weapon_type": "polearm",
                                    "refinement": 1,
                                    "level": 90,
                                    "promote_level": 6,
                                },
                                "artifact_build_id": None,
                            },
                        }
                    ]
                },
                team_index=0,
                rotation_shell_path=shell_path,
                run_dir=root / "run",
                write_config=False,
                virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
            )

        self.assertTrue(report.ready, report.issues)
        self.assertIn("testhero char lvl=80/90", report.assembly.config_text)
        self.assertNotIn(" add set=", report.assembly.config_text)
        self.assertIn(
            "testhero add stats hp=4780 atk=311 atk%=0.932 cr=0.311;",
            report.assembly.config_text,
        )
        build = report.team.payload["characters"][0]["artifact_build"]
        self.assertEqual(build["source_kind"], "theory_neutral_baseline")
        self.assertEqual(build["artifact_ids_by_pos"], {})
        self.assertFalse(build["owned_artifact_ids_claimed"])

    def test_all_sets_virtual_profile_uses_service_only_inventory_baseline_without_saved_build(self) -> None:
        with seeded_account_config_db() as db_path, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with closing(connect_db(db_path)) as conn:
                baseline = calculate_raw_build_summary(
                    conn,
                    slots={1: 300, 2: 301, 3: 302, 4: 303, 5: 304},
                )
            report = build_selected_team_full_config_report(
                db_path=db_path,
                selected_team={
                    "slots": [
                        {
                            "slot_index": 0,
                            "gcsim_virtual_override": {
                                "schema_version": 1,
                                "source": "virtual_gcsim_slot_override",
                                "character": {
                                    "gcsim_key": "testhero",
                                    "name": "TestHero",
                                    "weapon_type": "polearm",
                                    "constellation": 0,
                                    "level": 90,
                                    "promote_level": 6,
                                    "talents": {
                                        "normal": 10,
                                        "skill": 10,
                                        "burst": 10,
                                        "source_order_confirmed": True,
                                    },
                                },
                                "weapon": {
                                    "gcsim_key": "testspear",
                                    "name": "TestSpear",
                                    "weapon_type": "polearm",
                                    "refinement": 1,
                                    "level": 90,
                                    "promote_level": 6,
                                },
                                "artifact_build_id": None,
                            },
                        }
                    ]
                },
                team_index=0,
                rotation_shell_path=_write_shell(root, active="testhero"),
                run_dir=root / "run",
                write_config=False,
                virtual_artifact_policy=(
                    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE
                ),
                virtual_artifact_baselines={0: baseline},
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        self.assertTrue(report.ready, report.issues)
        build = report.team.payload["characters"][0]["artifact_build"]
        self.assertEqual(build["source_kind"], "optimizer_virtual_inventory_baseline")
        self.assertTrue(build["service_only"])
        self.assertFalse(build["owned_artifact_ids_claimed"])
        self.assertEqual(
            build["artifact_ids_by_pos"],
            {"1": 300, "2": 301, "3": 302, "4": 303, "5": 304},
        )

    def test_theory_mixed_team_uses_neutral_baseline_without_saved_build_or_set(self) -> None:
        with seeded_account_config_db() as db_path, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with closing(connect_db(db_path)) as conn:
                conn.executemany(
                    """
                    INSERT INTO account_character_equipped_weapons (
                        character_id, weapon_fingerprint, source, updated_at
                    ) VALUES (?, ?, 'test', '2026-09-18T00:00:00+00:00')
                    """,
                    ((10000104, "bow-a"), (10000105, "bow-b")),
                )
                conn.commit()
            shell_path = _write_shell(root, active="testhero")
            report = build_selected_team_full_config_report(
                db_path=db_path,
                selected_team={
                    "slots": [
                        _selected_team(10000104, "Chasca")["slots"][0],
                        _selected_team(10000105, "Ororon")["slots"][0],
                        _selected_team(10000089, "Furina")["slots"][0],
                        {
                            "slot_index": 3,
                            "gcsim_virtual_override": {
                                "schema_version": 1,
                                "source": "virtual_gcsim_slot_override",
                                "character": {
                                    "gcsim_key": "testhero",
                                    "name": "Test Hero",
                                    "weapon_type": "polearm",
                                    "constellation": 2,
                                    "level": 80,
                                    "promote_level": 6,
                                    "talents": {
                                        "normal": 10,
                                        "skill": 10,
                                        "burst": 10,
                                        "source_order_confirmed": True,
                                    },
                                },
                                "weapon": {
                                    "gcsim_key": "testspear",
                                    "name": "Test Spear",
                                    "weapon_type": "polearm",
                                    "refinement": 3,
                                    "level": 90,
                                    "promote_level": 6,
                                },
                                "artifact_set_bonuses": [
                                    {
                                        "set_uid": "GoldenTroupe",
                                        "display_name": "Golden Troupe",
                                        "count": 4,
                                        "mapping": {
                                            "gcsim_key": "goldentroupe",
                                            "source": "virtual_gcsim_set_selector",
                                            "ambiguous": False,
                                        },
                                    }
                                ],
                            },
                        },
                    ]
                },
                team_index=0,
                rotation_shell_path=shell_path,
                run_dir=root / "run",
                write_config=False,
                virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        self.assertTrue(report.ready, report.issues)
        self.assertEqual(len(report.team.payload["characters"]), 4)
        self.assertNotIn(" add set=", report.assembly.config_text)
        for actor in ("chasca", "ororon", "furina", "testhero"):
            self.assertIn(
                f"{actor} add stats hp=4780 atk=311 atk%=0.932 cr=0.311;",
                report.assembly.config_text,
            )
        self.assertTrue(
            all(
                row["artifact_build"]["source_kind"] == "theory_neutral_baseline"
                for row in report.team.payload["characters"]
            )
        )
        virtual = report.team.payload["characters"][3]
        self.assertEqual(virtual["promote_level"], 6)
        self.assertEqual(virtual["artifact_build"]["artifact_ids_by_pos"], {})
        self.assertEqual(virtual["artifact_build"]["set_counts"][0]["count"], 1)
        self.assertEqual(
            virtual["artifact_build"]["set_counts"][0]["mapping"]["gcsim_key"], ""
        )

    def test_selected_team_uses_stable_character_id_not_selected_display_name(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                shell_path = _write_shell(Path(temp_dir), active="furina")
                report = build_selected_team_full_config_report(
                    db_path=db_path,
                    selected_team=_selected_team(10000089, "Not Furina"),
                    team_index=0,
                    rotation_shell_path=shell_path,
                    run_dir=Path(temp_dir) / "run",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                )
                config_text = Path(report.config_path).read_text(encoding="utf-8")

        self.assertTrue(report.ready)
        self.assertEqual(report.source_notes["adapter"], "selected_runtime_team_adapter")
        self.assertFalse(report.source_notes["localized_names_used_as_gcsim_identity"])
        self.assertFalse(report.source_notes["dev_weapon_candidate_not_account_truth"])
        self.assertIn("furina char lvl=90/90", config_text)
        self.assertIn('furina add weapon="favoniussword"', config_text)
        self.assertNotIn("Not Furina", config_text)
        self.assertNotIn("prepared_fixture_adapter_boundary", report.warnings)
        self.assertNotIn("no_ui_or_storage_access", report.warnings)

    def test_stale_selected_character_mapping_cannot_override_account_identity(self) -> None:
        with seeded_account_config_db() as db_path:
            for stale_key, stale_status in (("", "missing"), ("notfurina", "ready")):
                with self.subTest(key=stale_key, status=stale_status):
                    selected = _selected_team(10000089, "Furina")
                    selected["slots"][0]["character"].update(
                        gcsim_character_key=stale_key, gcsim_character_key_status=stale_status)
                    result = build_selected_team_payload(
                        db_path=db_path, selected_team=selected,
                        artifact_set_registry_source=db_path.artifact_set_registry_source)
                    self.assertTrue(result.ready)
                    self.assertEqual(result.characters[0].account_character["gcsim_character_key"], "furina")
                    self.assertEqual(result.characters[0].account_character["gcsim_character_key_status"], "ready")

    def test_selected_team_does_not_choose_dev_weapon_candidate(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_selected_team_payload(
                db_path=db_path,
                selected_team=_selected_team(10000104, "Chasca"),
                team_index=0,
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        self.assertFalse(result.ready)
        detail = result.characters[0]
        self.assertFalse(detail.weapon_found)
        self.assertEqual(detail.weapon_selection_method, "missing_current_weapon")
        self.assertIn("weapon_missing", [issue.status for issue in result.issues])
        self.assertNotIn(
            "dev_weapon_candidate_not_account_truth",
            detail.warnings,
        )

    def test_missing_artifact_set_mapping_blocks_selected_team(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                empty_registry = Path(temp_dir) / "artifact_sets.go"
                empty_registry.write_text("package shortcut\n", encoding="utf-8")
                result = build_selected_team_payload(
                    db_path=db_path,
                    selected_team=_selected_team(10000089, "Furina"),
                    team_index=0,
                    artifact_set_registry_source=empty_registry,
                )

        self.assertFalse(result.ready)
        self.assertIn(
            "artifact_set_gcsim_key_not_ready",
            [issue.status for issue in result.issues],
        )
        summary = build_gcsim_readiness_summary(result.to_dict())
        self.assertIn(GROUP_ARTIFACT_SETS, summary.groups)

    def test_boosted_energy_setting_is_explicit(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                shell_path = _write_shell(Path(temp_dir), active="furina")
                normal_report = build_selected_team_full_config_report(
                    db_path=db_path,
                    selected_team=_selected_team(10000089, "Furina"),
                    team_index=0,
                    rotation_shell_path=shell_path,
                    run_dir=Path(temp_dir) / "normal",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                    run_settings=GcsimRunSettings(boosted_energy_enabled=False),
                )
                boosted_report = build_selected_team_full_config_report(
                    db_path=db_path,
                    selected_team=_selected_team(10000089, "Furina"),
                    team_index=0,
                    rotation_shell_path=shell_path,
                    run_dir=Path(temp_dir) / "boosted",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                    run_settings=GcsimRunSettings(boosted_energy_enabled=True),
                )
                normal_text = Path(normal_report.config_path).read_text(encoding="utf-8")
                boosted_text = Path(boosted_report.config_path).read_text(encoding="utf-8")

        self.assertIn("energy every interval=480,720 amount=1;", normal_text)
        self.assertNotIn("energy every interval=480,720 amount=100;", normal_text)
        self.assertIn("energy every interval=480,720 amount=100;", boosted_text)
        self.assertNotIn("energy every interval=480,720 amount=1;", boosted_text)
        self.assertFalse(normal_report.source_notes["energy"]["enabled"])
        self.assertTrue(boosted_report.source_notes["energy"]["enabled"])

    def test_dps_dummy_run_reports_energy_and_dummy_target_metadata(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                shell_path = _write_shell(Path(temp_dir), active="furina")
                report = build_selected_team_full_config_report(
                    db_path=db_path,
                    selected_team=_selected_team(10000089, "Furina"),
                    team_index=0,
                    rotation_shell_path=shell_path,
                    run_dir=Path(temp_dir) / "run",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                    run_settings=GcsimRunSettings(boosted_energy_enabled=True),
                )
                payload = run_selected_team_dps_dummy_artifact(
                    report,
                    run_dir=Path(temp_dir) / "dummy",
                    artifact_run_func=_fake_artifact_run,
                )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["energy"]["mode"], "boosted")
        self.assertEqual(payload["dummy_target"]["hp"], "999999999")
        self.assertEqual(payload["dummy_target"]["resist"], "0.1")
        self.assertEqual(payload["scenario_summary"]["dummy_target_hp"], "999999999")

    def test_readiness_summary_groups_missing_weapon(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_selected_team_payload(
                db_path=db_path,
                selected_team=_selected_team(10000104, "Chasca"),
                team_index=0,
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        summary = build_gcsim_readiness_summary(result.to_dict())

        self.assertTrue(summary.blocked)
        self.assertIn(GROUP_MISSING_WEAPONS, summary.groups)
        self.assertTrue(any("Chasca" in item for item in summary.groups[GROUP_MISSING_WEAPONS]))


def _selected_team(character_id: int, name: str) -> dict:
    return {
        "slots": [
            {
                "slot_index": 0,
                "character": {
                    "id": character_id,
                    "name": name,
                },
            }
        ]
    }


def _write_shell(directory: Path, *, active: str) -> Path:
    shell_path = directory / "rotation_shell.txt"
    shell_path.write_text(
        "\n".join(
            [
                "options swap_delay=12 iteration=1;",
                "energy every interval=480,720 amount=1;",
                "target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=999999999;",
                f"active {active};",
                "wait(60);",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return shell_path


def _seed_virtual_artifact_build(conn) -> int:
    now = "2026-09-17T00:00:00+00:00"
    main_stats = (
        (1, 2, "HP", "4780"),
        (2, 5, "ATK", "311"),
        (3, 23, "Energy Recharge", "51.8"),
        (4, 20, "CRIT Rate", "31.1"),
        (5, 22, "CRIT DMG", "62.2"),
    )
    slots: dict[int, int] = {}
    for pos, property_type, property_name, value in main_stats:
        artifact_id = 100 + pos
        slots[pos] = artifact_id
        conn.execute(
            """
            INSERT INTO artifacts (
                id, fingerprint, name, set_uid, set_name, pos, pos_name,
                rarity, level, main_property_type, main_property_name,
                main_property_value, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 5, 20, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                f"virtual-{artifact_id}",
                f"Virtual Piece {pos}",
                f"virtual_set_{pos}",
                f"Virtual Set {pos}",
                pos,
                f"Position {pos}",
                property_type,
                property_name,
                value,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO artifact_substats (
                artifact_id, slot_index, property_type, property_name, value, times
            )
            VALUES (?, 0, 20, 'CRIT Rate', '3.1', 1)
            """,
            (artifact_id,),
        )
    return create_build_preset(
        conn,
        name="Virtual complete build",
        slots=slots,
        targets=[
            {
                "target_type": "gcsim_character",
                "gcsim_character_key": "testhero",
                "character_name": "TestHero",
            }
        ],
    )


class _FakeArtifactRunResult:
    success = True
    status = "run_passed"

    def to_dict(self) -> dict:
        return {
            "success": True,
            "status": "run_passed",
            "summary": {},
        }


def _fake_artifact_run(*args, **kwargs) -> _FakeArtifactRunResult:
    return _FakeArtifactRunResult()


if __name__ == "__main__":
    unittest.main()
