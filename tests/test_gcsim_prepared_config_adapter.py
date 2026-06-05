from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from hoyolab_export.artifact_stats import CRIT_RATE, HP_FLAT
from run_workspace.gcsim.config_blocks import CONFIG_BLOCK_READY
from run_workspace.gcsim.config_readiness import (
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_TALENT_DATA,
    READINESS_MISSING_WEAPON,
    READINESS_UNSUPPORTED_TRAVELER,
)
from run_workspace.gcsim.prepared_config_adapter import (
    PREPARED_CONFIG_READY,
    WARNING_FINAL_STATS_IGNORED,
    adapt_prepared_character_config_input,
    adapt_prepared_team_config_inputs,
    load_prepared_team_config_inputs_json,
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


if __name__ == "__main__":
    unittest.main()
