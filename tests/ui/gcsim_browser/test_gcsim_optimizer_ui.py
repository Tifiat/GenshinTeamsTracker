from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from ui.artifact_browser.models import ArtifactItem, ArtifactSubstat
from ui.app_shell import AppShell
from ui.gcsim_browser.optimizer_result import (
    OptimizerResultBuildsWidget,
    build_optimizer_result_pages,
    build_optimizer_result_rows,
)
from ui.gcsim_browser.window import GcsimBrowserWorkspace, _format_optimizer_elapsed


_APP = QApplication.instance() or QApplication([])


class GcsimOptimizerUiTests(unittest.TestCase):
    def test_three_product_modes_are_visible_and_only_selected_is_enabled(self) -> None:
        workspace = GcsimBrowserWorkspace()

        self.assertEqual(workspace.optimizer_selected_button.text(), "Selected Sets")
        self.assertEqual(workspace.optimizer_all_sets_button.text(), "All Sets")
        self.assertEqual(workspace.optimizer_theory_button.text(), "Theory")
        self.assertTrue(workspace.optimizer_selected_button.isEnabled())
        self.assertFalse(workspace.optimizer_all_sets_button.isEnabled())
        self.assertFalse(workspace.optimizer_theory_button.isEnabled())

    def test_selected_button_sends_current_team_and_rotation(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.team_tabs.setCurrentIndex(1)
        workspace.rotation_editor.setPlainText("active furina;")
        requests: list[tuple[int, str]] = []
        workspace.optimizer_selected_requested.connect(
            lambda team, rotation: requests.append((team, rotation))
        )

        workspace.optimizer_selected_button.click()

        self.assertEqual(requests, [(1, "active furina;")])

    def test_progress_uses_mapping_contract_and_cancel_is_only_live_when_busy(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.set_optimizer_busy(True)
        workspace.update_optimizer_progress(
            {
                "stage": "simulating_finalists",
                "completed_work": 4,
                "total_work": 5,
            }
        )

        self.assertEqual(workspace.optimizer_progress_bar.maximum(), 5)
        self.assertEqual(workspace.optimizer_progress_bar.value(), 4)
        self.assertTrue(workspace.optimizer_cancel_button.isEnabled())

        workspace.set_optimizer_busy(False)
        self.assertFalse(workspace.optimizer_cancel_button.isEnabled())

    def test_timer_reports_elapsed_time_and_stops_on_completion(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.set_optimizer_busy(True)
        self.assertTrue(workspace._optimizer_elapsed_tick.isActive())
        self.assertIn("1", workspace.optimizer_elapsed_label.text())

        workspace.update_optimizer_progress(
            {"stage": "completed", "completed_work": 1, "total_work": 1}
        )

        self.assertFalse(workspace._optimizer_elapsed_tick.isActive())
        self.assertIn("0:00", workspace.optimizer_elapsed_label.text())
        self.assertEqual(_format_optimizer_elapsed(3_725_000), "1:02:05")

    def test_result_rows_follow_team_order_and_emit_existing_preset_payload(self) -> None:
        artifacts = [_artifact(artifact_id, position) for position, artifact_id in enumerate(range(11, 16), start=1)]
        payload = {
            "status": "success",
            "result": {
                "winner": [
                    {
                        "wearer_key": "furina",
                        "slot": slot,
                        "artifact_id": artifact_id,
                    }
                    for slot, artifact_id in zip(
                        ("flower", "plume", "sands", "goblet", "circlet"),
                        range(11, 16),
                        strict=True,
                    )
                ]
            },
        }
        selected_team = {
            "slots": [
                {
                    "character": {"id": "10000089", "name": "Furina"},
                    "character_details_data": {
                        "account_character": {
                            "id": 10000089,
                            "name": "Furina",
                            "gcsim_character_key": "furina",
                        }
                    },
                }
            ]
        }

        rows = build_optimizer_result_rows(payload, selected_team, artifacts)

        self.assertEqual([row.wearer_key for row in rows], ["furina"])
        self.assertEqual(dict(rows[0].slots), {1: 11, 2: 12, 3: 13, 4: 14, 5: 15})
        self.assertTrue(rows[0].can_save)

        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.close)
        widget.set_rows(rows)
        requests: list[dict] = []
        widget.save_requested.connect(requests.append)
        self.assertTrue(widget.request_save("furina", "Formula result"))
        self.assertEqual(requests[0]["slots"], {1: 11, 2: 12, 3: 13, 4: 14, 5: 15})
        self.assertEqual(
            requests[0]["targets"],
            [
                {
                    "target_type": "character",
                    "character_id": 10000089,
                    "character_name": "Furina",
                }
            ],
        )

    def test_save_request_uses_artifact_browser_preset_module(self) -> None:
        save_results: list[tuple[str, bool, str]] = []
        workspace = SimpleNamespace(
            set_optimizer_build_save_result=lambda wearer, success, message: save_results.append(
                (wearer, success, message)
            )
        )
        shell = SimpleNamespace(
            controller=SimpleNamespace(equipment_db_path="account.db"),
            left_host=SimpleNamespace(
                artifact_browser_workspace=None,
                gcsim_browser_workspace=workspace,
            ),
        )
        request = {
            "wearer_key": "furina",
            "name": "Selected Sets — Furina",
            "slots": {1: 11, 2: 12, 3: 13, 4: 14, 5: 15},
            "targets": [
                {
                    "target_type": "character",
                    "character_id": 10000089,
                    "character_name": "Furina",
                }
            ],
        }

        with patch("ui.app_shell.save_build_preset", return_value=7) as save:
            AppShell._on_gcsim_optimizer_build_save_requested(shell, request)

        save.assert_called_once_with(
            build_id=None,
            name="Selected Sets — Furina",
            slots={1: 11, 2: 12, 3: 13, 4: 14, 5: 15},
            targets=request["targets"],
            db_path="account.db",
        )
        self.assertEqual(save_results[0][:2], ("furina", True))

    def test_ranked_candidates_keep_fixed_navigation_and_switch_builds(self) -> None:
        artifacts = [
            _artifact(artifact_id, position)
            for position, artifact_id in enumerate(range(11, 16), start=1)
        ]
        assignments = [
            {
                "wearer_key": "furina",
                "slot": slot,
                "artifact_id": artifact_id,
            }
            for slot, artifact_id in zip(
                ("flower", "plume", "sands", "goblet", "circlet"),
                range(11, 16),
                strict=True,
            )
        ]
        payload = {
            "status": "success",
            "result": {
                "candidates": [
                    {"rank": 1, "artifacts": assignments, "measured": {"dps": "150000.5"}},
                    {"rank": 2, "artifacts": assignments, "measured": {"dps": "149900.25"}},
                ]
            },
        }
        selected_team = {
            "slots": [
                {
                    "character": {"id": "10000089", "name": "Furina"},
                    "character_details_data": {
                        "account_character": {
                            "id": 10000089,
                            "name": "Furina",
                            "gcsim_character_key": "furina",
                        }
                    },
                }
            ]
        }
        pages = build_optimizer_result_pages(payload, selected_team, artifacts)
        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.close)
        widget.set_pages(pages)

        self.assertEqual(len(pages), 2)
        self.assertEqual(widget.current_page_index, 0)
        self.assertFalse(widget.previous_button.isEnabled())
        self.assertTrue(widget.next_button.isEnabled())
        self.assertIn("150 000", widget.title_label.text())
        self.assertEqual(widget.previous_button.width(), widget.next_button.width())

        widget.next_button.click()

        self.assertEqual(widget.current_page_index, 1)
        self.assertTrue(widget.previous_button.isEnabled())
        self.assertFalse(widget.next_button.isEnabled())
        self.assertIn("149 900", widget.title_label.text())


def _artifact(artifact_id: int, position: int) -> ArtifactItem:
    return ArtifactItem(
        id=artifact_id,
        name=f"Artifact {artifact_id}",
        set_id=1,
        set_uid="test-set",
        set_name="Test Set",
        pos=position,
        pos_name=str(position),
        rarity=5,
        level=20,
        main_property_type=3,
        main_property_name="HP%",
        main_property_value="46.6%",
        substats=[
            ArtifactSubstat(1, 20, "CRIT Rate", "3.9%", 1),
            ArtifactSubstat(2, 22, "CRIT DMG", "7.8%", 1),
        ],
    )


if __name__ == "__main__":
    unittest.main()
