from __future__ import annotations

import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hoyolab_export.artifact_db import connect_db
from run_workspace.gcsim.selected_team_config import build_selected_team_full_config_report
from run_workspace.gcsim.settings import GcsimRunSettings
from run_workspace.pvp.gcsim_preparation import PvpGcsimPreparation
from tests.run_workspace.gcsim.test_gcsim_account_prepared_config import (
    seeded_account_config_db,
)


class PvpGcsimPreparationTest(unittest.TestCase):
    def test_preparation_uses_disjoint_team_directories_and_cleans_idempotently(self) -> None:
        calls: list[dict[str, Any]] = []
        reports = [object(), object()]

        def fake_builder(**kwargs):
            calls.append(kwargs)
            return reports[len(calls) - 1]

        adapter = PvpGcsimPreparation(
            db_path=Path("seat-runtime.db"),
            report_builder=fake_builder,
        )
        self.assertIsNone(adapter.output_root)
        try:
            for team_index in (0, 1):
                report = adapter.prepare(
                    team_index=team_index,
                    selected_team=_selected_team(),
                    rotation_shell_text=f"active furina; # team {team_index}\n",
                    run_settings=GcsimRunSettings(boosted_energy_enabled=True),
                    artifact_set_registry_source=Path("engine") / "artifact.dm.go",
                )
                self.assertIs(report, reports[team_index])

            output_root = adapter.output_root
            self.assertIsNotNone(output_root)
            self.assertEqual(calls[0]["db_path"], Path("seat-runtime.db"))
            self.assertEqual(calls[0]["team_index"], 0)
            self.assertEqual(calls[1]["team_index"], 1)
            self.assertEqual(calls[0]["run_dir"], output_root / "team-0")
            self.assertEqual(calls[1]["run_dir"], output_root / "team-1")
            self.assertNotEqual(calls[0]["run_dir"], calls[1]["run_dir"])
            self.assertEqual(
                calls[0]["rotation_shell_path"],
                output_root / "team-0" / "rotation_shell.txt",
            )
            self.assertEqual(
                calls[1]["rotation_shell_path"].read_text(encoding="utf-8"),
                "active furina; # team 1\n",
            )
            self.assertTrue(calls[0]["write_config"])
            self.assertFalse(calls[0]["allow_account_equipment_fallback"])
            self.assertEqual(
                calls[0]["artifact_set_registry_source"],
                Path("engine") / "artifact.dm.go",
            )
            self.assertTrue(calls[0]["run_settings"].boosted_energy_enabled)
            self.assertTrue(
                all(
                    path.resolve().is_relative_to(output_root.resolve())
                    for path in output_root.rglob("*")
                )
            )
        finally:
            output_root = adapter.output_root
            adapter.close()
            adapter.close()

        self.assertIsNone(adapter.output_root)
        self.assertIsNotNone(output_root)
        self.assertFalse(output_root.exists())

    def test_invalid_team_indexes_and_empty_team_do_not_allocate_output(self) -> None:
        calls: list[dict[str, Any]] = []

        def fake_builder(**kwargs):
            calls.append(kwargs)
            return object()

        for team_index in (-1, 2, True, "0"):
            adapter = PvpGcsimPreparation(
                db_path="seat-runtime.db",
                report_builder=fake_builder,
            )
            with self.subTest(team_index=team_index):
                with self.assertRaises(ValueError):
                    adapter.prepare(
                        team_index=team_index,
                        selected_team=_selected_team(),
                        rotation_shell_text="active furina;\n",
                        run_settings=GcsimRunSettings(),
                        artifact_set_registry_source="artifact.dm.go",
                    )
                self.assertIsNone(adapter.output_root)
            adapter.close()

        adapter = PvpGcsimPreparation(
            db_path="seat-runtime.db",
            report_builder=fake_builder,
        )
        with self.assertRaisesRegex(ValueError, "no occupied slots"):
            adapter.prepare(
                team_index=0,
                selected_team={"slots": [{"slot_index": 0, "character": None}]},
                rotation_shell_text="active furina;\n",
                run_settings=GcsimRunSettings(),
                artifact_set_registry_source="artifact.dm.go",
            )
        self.assertIsNone(adapter.output_root)
        self.assertEqual(calls, [])
        adapter.close()

    def test_scoped_empty_equipment_does_not_borrow_source_account_equipment(self) -> None:
        with seeded_account_config_db() as db_path:
            with TemporaryDirectory() as normal_temp:
                normal_root = Path(normal_temp)
                shell_path = _write_shell(normal_root)
                normal_report = build_selected_team_full_config_report(
                    db_path=db_path,
                    selected_team=_selected_team(),
                    team_index=0,
                    rotation_shell_path=shell_path,
                    run_dir=normal_root / "normal",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                    run_settings=GcsimRunSettings(),
                )

            before_equipment = _account_equipment_rows(db_path)
            adapter = PvpGcsimPreparation(db_path=db_path)
            try:
                report = adapter.prepare(
                    team_index=0,
                    selected_team=_selected_team(),
                    rotation_shell_text=_shell_text(),
                    run_settings=GcsimRunSettings(),
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                )
                output_root = adapter.output_root
                self.assertIsNotNone(output_root)
                detail = report.team.characters[0]
                issue_statuses = {issue.status for issue in detail.issues}

                self.assertTrue(normal_report.ready, normal_report.issues)
                self.assertEqual(normal_report.team.characters[0].current_equipped_artifact_count, 5)
                self.assertTrue(normal_report.team.characters[0].weapon_found)

                self.assertFalse(report.ready)
                self.assertFalse(detail.weapon_found)
                self.assertEqual(detail.weapon_selection_method, "missing_current_weapon")
                self.assertEqual(detail.current_equipped_artifact_count, 0)
                self.assertEqual(detail.artifact_source, "missing_current_equipped_artifacts")
                self.assertIn("weapon_missing", issue_statuses)
                self.assertIn("current_artifacts_missing", issue_statuses)
                self.assertIn("current_artifact_stats_missing", issue_statuses)
                self.assertEqual(report.config_path, "")
                self.assertFalse(report.wrote_config)
                self.assertEqual(_account_equipment_rows(db_path), before_equipment)
                self.assertTrue(
                    all(
                        path.resolve().is_relative_to(output_root.resolve())
                        for path in output_root.rglob("*")
                    )
                )
            finally:
                output_root = adapter.output_root
                adapter.close()

        self.assertIsNotNone(output_root)
        self.assertFalse(output_root.exists())


def _selected_team() -> dict[str, Any]:
    return {
        "slots": [
            {
                "slot_index": 0,
                "character": {
                    "id": 10000089,
                    "name": "Furina",
                },
            }
        ]
    }


def _shell_text() -> str:
    return "\n".join(
        (
            "options swap_delay=12 iteration=1;",
            "energy every interval=480,720 amount=1;",
            "target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=999999999;",
            "active furina;",
            "wait(60);",
            "",
        )
    )


def _write_shell(directory: Path) -> Path:
    shell_path = directory / "rotation_shell.txt"
    shell_path.write_text(_shell_text(), encoding="utf-8")
    return shell_path


def _account_equipment_rows(db_path: str | Path) -> tuple[tuple[Any, ...], ...]:
    with closing(connect_db(db_path)) as conn:
        artifacts = tuple(
            tuple(row)
            for row in conn.execute(
                """
                SELECT character_id, slot_key, artifact_id
                FROM account_character_equipped_artifacts
                ORDER BY character_id, slot_key
                """
            ).fetchall()
        )
        weapons = tuple(
            tuple(row)
            for row in conn.execute(
                """
                SELECT character_id, weapon_fingerprint
                FROM account_character_equipped_weapons
                ORDER BY character_id
                """
            ).fetchall()
        )
    return (*artifacts, *weapons)


if __name__ == "__main__":
    unittest.main()
