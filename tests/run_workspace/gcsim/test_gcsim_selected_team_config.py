from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.readiness_summary import (
    GROUP_ARTIFACT_SETS,
    GROUP_MISSING_WEAPONS,
    build_gcsim_readiness_summary,
)
from run_workspace.gcsim.selected_team_config import (
    build_selected_team_full_config_report,
    build_selected_team_payload,
)
from run_workspace.gcsim.settings import GcsimRunSettings
from tests.run_workspace.gcsim.test_gcsim_account_prepared_config import (
    seeded_account_config_db,
)


class GcsimSelectedTeamConfigTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
