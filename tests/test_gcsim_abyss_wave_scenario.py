from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.gcsim.abyss_wave_scenario import (
    FIXTURE_FIELDS_WARNING,
    MISSING_FIXTURE_POLICY_WARNING,
    ProvisionalTargetFixturePolicy,
    build_abyss_wave_scenario_payload,
    write_abyss_wave_scenario_payload,
)
from tests.abyss.test_source_data import composition_report, fandom_row, nanoka_report, nanoka_row


def _fixture_policy() -> ProvisionalTargetFixturePolicy:
    return ProvisionalTargetFixturePolicy(
        radius=1.2,
        resist=0.1,
        positions=((0.0, 0.0), (3.0, 0.0), (-3.0, 0.0)),
        policy_name="test_fixture_policy",
    )


def _source_data(*, missing_level: bool = False, missing_hp: bool = False):
    fandom_rows = [
        fandom_row(
            "First Enemy",
            chamber=1,
            side=1,
            wave=1,
            count=2,
            level=None if missing_level else 95,
        ),
        fandom_row(
            "Second Enemy",
            chamber=1,
            side=1,
            wave=2,
            count=1,
            level=90,
        ),
    ]
    tower_report = None
    if not missing_hp:
        tower_report = nanoka_report(
            "119",
            [
                nanoka_row(
                    "First Enemy",
                    chamber=1,
                    side=1,
                    hp=100_000,
                    monster_id="first",
                    level=95,
                ),
                nanoka_row(
                    "Second Enemy",
                    chamber=1,
                    side=1,
                    hp=200_000,
                    monster_id="second",
                    level=90,
                ),
            ],
        )
    return load_abyss_floor12_source_data(
        "2026-05-16",
        "119",
        composition_report=composition_report("2026-05-16", fandom_rows),
        nanoka_report=tower_report,
    )


class GcsimAbyssWaveScenarioTest(unittest.TestCase):
    def test_rows_grouped_by_wave_and_enemy_count_expands_targets(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            fixture_policy=_fixture_policy(),
        )

        self.assertTrue(result.ready)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertEqual(result.audit.wave_count, 2)
        self.assertEqual(result.audit.source_enemy_row_count, 2)
        self.assertEqual(result.audit.generated_target_count, 3)
        self.assertEqual([len(wave["targets"]) for wave in result.payload["waves"]], [2, 1])
        self.assertEqual(result.payload["waves"][0]["targets"][0]["hp"], 100_000.0)
        self.assertEqual(result.payload["waves"][0]["targets"][1]["hp"], 100_000.0)
        self.assertEqual(result.payload["waves"][1]["targets"][0]["level"], 90)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["pos"], [0.0, 0.0])
        self.assertEqual(result.payload["waves"][0]["targets"][1]["pos"], [3.0, 0.0])

    def test_missing_hp_reports_not_ready_without_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(missing_hp=True),
            chamber=1,
            side=1,
            fixture_policy=_fixture_policy(),
        )

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertGreater(len(result.audit.missing_hp_rows), 0)
        self.assertIn("First Enemy", result.audit.missing_hp_rows[0])

    def test_missing_level_reports_not_ready_without_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(missing_level=True),
            chamber=1,
            side=1,
            fixture_policy=_fixture_policy(),
        )

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertGreater(len(result.audit.missing_level_rows), 0)
        self.assertIn("First Enemy", result.audit.missing_level_rows[0])

    def test_missing_fixture_policy_prevents_payload_generation(self) -> None:
        result = build_abyss_wave_scenario_payload(_source_data(), chamber=1, side=1)

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertFalse(result.audit.fixture_fields_used)
        self.assertIn(MISSING_FIXTURE_POLICY_WARNING, result.audit.warnings)

    def test_fixture_policy_produces_schema_v1_payload_and_audit_warning(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            fixture_policy=_fixture_policy(),
        )

        self.assertTrue(result.ready)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertEqual(result.payload["schema_version"], 1)
        self.assertEqual(result.payload["spawn_policy"], "group_clear")
        self.assertEqual(result.audit.fixture_policy_name, "test_fixture_policy")
        self.assertTrue(result.audit.fixture_fields_used)
        self.assertIn(FIXTURE_FIELDS_WARNING, result.audit.warnings)

    def test_write_payload_helper_writes_json_only_when_caller_has_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            fixture_policy=_fixture_policy(),
        )
        assert result.payload is not None

        with tempfile.TemporaryDirectory() as tmp:
            path = write_abyss_wave_scenario_payload(
                result.payload,
                Path(tmp) / "scenario.json",
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn('"spawn_policy": "group_clear"', text)


if __name__ == "__main__":
    unittest.main()
