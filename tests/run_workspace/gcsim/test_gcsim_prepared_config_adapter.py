from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from io import StringIO

from hoyolab_export.artifact_stats import CRIT_RATE, HP_FLAT
from run_workspace.gcsim.config_assembly import (
    ASSEMBLY_READY,
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
)
from run_workspace.gcsim.config_blocks import CONFIG_BLOCK_READY
from run_workspace.gcsim.config_readiness import (
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_TALENT_DATA,
    READINESS_MISSING_WEAPON,
    READINESS_UNSUPPORTED_TRAVELER,
)
from run_workspace.gcsim.prepared_config_adapter import (
    DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
    PREPARED_CONFIG_CONFIG_WRITTEN,
    PREPARED_CONFIG_MISSING_CHARACTER,
    PREPARED_CONFIG_READY,
    PREPARED_CONFIG_WRITE_SKIPPED_NOT_READY,
    WARNING_FINAL_STATS_IGNORED,
    WARNING_SYNTHETIC_DEV_FIXTURE,
    adapt_prepared_character_config_input,
    adapt_prepared_team_config_inputs,
    build_prepared_team_full_config_report,
    build_prepared_team_full_config_report_from_json,
    load_prepared_team_config_inputs_json,
    main,
)


def ready_mapping(key: str) -> dict:
    return {
        "gcsim_key": key,
        "source": "curated_test_fixture",
    }


def prepared_character(**overrides) -> dict:
    payload = {
        "project_character_id": "10000021",
        "display_name": "Mona",
        "level": 80,
        "promote_level": 6,
        "constellation": 2,
        "mapping": ready_mapping("mona"),
        "talents": {
            "normal": 6,
            "skill": 9,
            "burst": 10,
            "source_order_confirmed": True,
        },
        "weapon": {
            "project_weapon_id": "14405",
            "display_name": "Favonius Codex",
            "level": 90,
            "promote_level": 6,
            "refinement": 5,
            "mapping": ready_mapping("favoniuscodex"),
        },
        "artifact_build": {
            "set_counts": [
                {
                    "set_uid": "NoblesseOblige",
                    "display_name": "Noblesse Oblige",
                    "count": 4,
                    "mapping": ready_mapping("noblesseoblige"),
                }
            ],
            "stat_totals": [
                {"property_type": HP_FLAT, "raw_value": 4780},
                {"property_type": CRIT_RATE, "raw_value": 31.1},
            ],
        },
    }
    payload.update(overrides)
    return payload


class GcsimPreparedConfigAdapterTest(unittest.TestCase):
    def test_prepared_fixture_converts_to_ready_character_input(self) -> None:
        result = adapt_prepared_character_config_input(prepared_character())

        self.assertTrue(result.ready)
        self.assertEqual(result.status, PREPARED_CONFIG_READY)
        self.assertEqual(result.block.status, CONFIG_BLOCK_READY)
        self.assertEqual(result.character_input.mapping.gcsim_key, "mona")
        self.assertEqual(result.character_input.weapon.mapping.gcsim_key, "favoniuscodex")
        self.assertIn("mona char lvl=80/90", result.block.text)
        self.assertFalse(result.source_notes["ui_access"])
        self.assertFalse(result.source_notes["storage_query"])
        self.assertFalse(result.source_notes["network_fetch"])

    def test_prepared_team_json_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "team.json"
            path.write_text(
                json.dumps({"characters": [prepared_character()]}),
                encoding="utf-8",
            )

            result = load_prepared_team_config_inputs_json(path)

        self.assertTrue(result.ready)
        self.assertEqual(len(result.ready_blocks), 1)

    def test_default_chasca_team_fixture_converts_four_ready_blocks(self) -> None:
        result = load_prepared_team_config_inputs_json(
            DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.status, PREPARED_CONFIG_READY)
        self.assertEqual(len(result.characters), 4)
        self.assertEqual(
            [item.character_input.mapping.gcsim_key for item in result.characters],
            ["chasca", "ororon", "furina", "bennett"],
        )
        self.assertEqual(
            [item.block.status for item in result.characters],
            [CONFIG_BLOCK_READY] * 4,
        )
        self.assertIn(WARNING_SYNTHETIC_DEV_FIXTURE, result.warnings)
        self.assertFalse(result.source_notes["account_truth"])
        self.assertFalse(result.source_notes["ui_state"])
        self.assertFalse(result.source_notes["production_mapping"])

    def test_full_config_assembly_from_default_fixture_writes_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_prepared_team_full_config_report_from_json(
                DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
                run_dir=Path(temp_dir) / "run",
            )

            config_path = Path(report.config_path)
            config_text = config_path.read_text(encoding="utf-8")

        self.assertTrue(report.ready)
        self.assertEqual(report.status, PREPARED_CONFIG_CONFIG_WRITTEN)
        self.assertTrue(report.wrote_config)
        self.assertEqual(report.assembly.status, ASSEMBLY_READY)
        self.assertTrue(config_text.startswith("chasca char lvl=90/90"))
        self.assertIn("ororon char lvl=90/90", config_text)
        self.assertIn("furina char lvl=90/90", config_text)
        self.assertIn("bennett char lvl=90/90", config_text)
        self.assertLess(
            config_text.index("bennett add stats"),
            config_text.index("options swap_delay=12"),
        )
        self.assertIn("active furina;", config_text)

    def test_final_stats_are_ignored_not_used_as_add_stats(self) -> None:
        payload = prepared_character(
            artifact_build={
                "set_counts": [
                    {
                        "set_uid": "NoblesseOblige",
                        "count": 4,
                        "mapping": ready_mapping("noblesseoblige"),
                    }
                ],
                "stat_totals": [
                    {"property_type": CRIT_RATE, "raw_value": 31.1},
                ],
            },
            right_panel_stats={
                "hp": 999999,
            },
        )
        result = adapt_prepared_character_config_input(payload)

        self.assertTrue(result.ready)
        self.assertIn(WARNING_FINAL_STATS_IGNORED, result.warnings)
        self.assertNotIn("999999", result.block.text)

    def test_missing_talents_weapon_build_traveler_and_mapping_are_controlled(self) -> None:
        cases = (
            (
                "missing_talents",
                prepared_character(talents=None),
                READINESS_MISSING_TALENT_DATA,
            ),
            (
                "missing_weapon",
                prepared_character(weapon=None),
                READINESS_MISSING_WEAPON,
            ),
            (
                "missing_build",
                prepared_character(artifact_build=None),
                READINESS_MISSING_ARTIFACT_DATA,
            ),
            (
                "traveler",
                prepared_character(
                    project_character_id="10000007",
                    display_name="Traveler",
                    mapping=ready_mapping("pyrotraveler"),
                ),
                READINESS_UNSUPPORTED_TRAVELER,
            ),
            (
                "missing_mapping",
                prepared_character(mapping={}),
                READINESS_MISSING_MAPPING,
            ),
        )

        for label, payload, expected_status in cases:
            with self.subTest(label=label):
                result = adapt_prepared_character_config_input(payload)
                self.assertFalse(result.ready)
                self.assertEqual(result.block.status, expected_status)
                self.assertEqual(result.block.lines, ())

    def test_missing_artifact_stats_is_controlled_not_ready(self) -> None:
        result = adapt_prepared_character_config_input(
            prepared_character(
                artifact_build={
                    "set_counts": [
                        {
                            "set_uid": "NoblesseOblige",
                            "count": 4,
                            "mapping": ready_mapping("noblesseoblige"),
                        }
                    ],
                    "stat_totals": [],
                }
            )
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.block.status, "missing_artifact_stats")
        self.assertEqual(result.block.lines, ())

    def test_required_missing_character_is_controlled_not_ready(self) -> None:
        team = adapt_prepared_team_config_inputs(
            {
                "required_characters": ["Mona", "Furina"],
                "characters": [prepared_character(display_name="Mona")],
            }
        )

        self.assertFalse(team.ready)
        self.assertEqual(team.status, "not_ready")
        self.assertEqual(
            team.characters[-1].issues[0].status,
            PREPARED_CONFIG_MISSING_CHARACTER,
        )
        self.assertIn(
            PREPARED_CONFIG_MISSING_CHARACTER,
            [issue.status for issue in team.issues],
        )

    def test_full_config_report_refuses_partial_output_when_character_not_ready(self) -> None:
        payload = json.loads(
            DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH.read_text(encoding="utf-8")
        )
        payload["characters"][1]["mapping"] = {}
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_prepared_team_full_config_report(
                payload,
                run_dir=Path(temp_dir) / "run",
            )

            self.assertFalse((Path(temp_dir) / "run" / "config.txt").exists())

        self.assertFalse(report.ready)
        self.assertEqual(report.status, PREPARED_CONFIG_WRITE_SKIPPED_NOT_READY)
        self.assertEqual(report.config_path, "")
        self.assertFalse(report.wrote_config)
        self.assertEqual(report.assembly.config_text, "")

    def test_full_config_report_refuses_partial_output_for_missing_required_character(self) -> None:
        payload = json.loads(
            DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH.read_text(encoding="utf-8")
        )
        payload["characters"] = payload["characters"][:3]
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_prepared_team_full_config_report(
                payload,
                run_dir=Path(temp_dir) / "run",
            )

            self.assertFalse((Path(temp_dir) / "run" / "config.txt").exists())

        self.assertFalse(report.ready)
        self.assertEqual(report.status, PREPARED_CONFIG_WRITE_SKIPPED_NOT_READY)
        self.assertIn(
            PREPARED_CONFIG_MISSING_CHARACTER,
            [issue["status"] for issue in report.issues],
        )

    def test_team_adapter_preserves_character_order(self) -> None:
        team = adapt_prepared_team_config_inputs(
            {
                "characters": [
                    prepared_character(mapping=ready_mapping("chasca"), display_name="Chasca"),
                    prepared_character(mapping=ready_mapping("furina"), display_name="Furina"),
                ]
            }
        )

        self.assertTrue(team.ready)
        self.assertEqual(
            [item.character_input.mapping.gcsim_key for item in team.characters],
            ["chasca", "furina"],
        )

    def test_rotation_shell_fixture_still_has_no_manual_blocks(self) -> None:
        shell_text = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(" char lvl=", shell_text)
        self.assertNotIn(" add weapon=", shell_text)
        self.assertNotIn(" add set=", shell_text)
        self.assertNotIn(" add stats ", shell_text)

    def test_cli_json_and_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            json_stdout = StringIO()
            json_code = main(
                [
                    "--fixture",
                    str(DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH),
                    "--run-dir",
                    str(Path(temp_dir) / "json-run"),
                    "--format",
                    "json",
                ],
                stdout=json_stdout,
            )
            text_stdout = StringIO()
            text_code = main(
                [
                    "--fixture",
                    str(DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH),
                    "--run-dir",
                    str(Path(temp_dir) / "text-run"),
                    "--format",
                    "text",
                ],
                stdout=text_stdout,
            )
            payload = json.loads(json_stdout.getvalue())
            config_exists = Path(payload["config_path"]).is_file()

        self.assertEqual(json_code, 0)
        self.assertEqual(text_code, 0)
        self.assertTrue(payload["ready"])
        self.assertTrue(config_exists)
        self.assertIn("Prepared GCSIM config bridge", text_stdout.getvalue())
        self.assertIn("config=", text_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
