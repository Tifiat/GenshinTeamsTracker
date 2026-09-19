from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication, QAbstractSpinBox

from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest,
)
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest,
)
from run_workspace.gcsim.optimizer_go_theory import (
    GcsimOptimizerGoTheoryRequest,
)
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
)
from ui.artifact_browser.models import ArtifactItem, ArtifactSubstat
from ui.app_shell import AppShell
from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
from ui.gcsim_browser.optimizer_result import (
    OptimizerResultBuildsWidget,
    build_optimizer_result_pages,
    build_optimizer_result_rows,
)
from ui.gcsim_browser.window import GcsimBrowserWorkspace, _format_optimizer_elapsed


_APP = QApplication.instance() or QApplication([])


class GcsimOptimizerUiTests(unittest.TestCase):
    def test_compact_virtual_levels_do_not_hide_values_behind_arrow_buttons(self) -> None:
        workspace = GcsimBrowserWorkspace()
        editor = workspace._team_cards[0][0].virtual_editor

        self.assertEqual(
            editor.character_level_spin.buttonSymbols(),
            QAbstractSpinBox.ButtonSymbols.NoButtons,
        )
        self.assertEqual(
            editor.weapon_level_spin.buttonSymbols(),
            QAbstractSpinBox.ButtonSymbols.NoButtons,
        )
        editor.character_level_spin.setValue(90)
        editor.weapon_level_spin.setValue(90)
        self.assertEqual(editor.character_level_spin.text(), "Lv 90")
        self.assertEqual(editor.weapon_level_spin.text(), "Lv 90")

    def test_three_product_modes_are_visible_and_only_selected_is_enabled(self) -> None:
        workspace = GcsimBrowserWorkspace()

        self.assertEqual(workspace.optimizer_selected_button.text(), "Selected Sets")
        self.assertEqual(workspace.optimizer_all_sets_button.text(), "All Sets")
        self.assertEqual(workspace.optimizer_theory_button.text(), "Theory")
        self.assertTrue(workspace.optimizer_selected_button.isEnabled())
        self.assertFalse(workspace.optimizer_all_sets_button.isEnabled())
        self.assertFalse(workspace.optimizer_theory_button.isEnabled())
        self.assertIn("2+2", workspace.optimizer_description.text())

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

    def test_all_sets_gate_signal_and_busy_share_existing_result_surface(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.set_optimizer_all_sets_available(True)
        workspace.rotation_editor.setPlainText("active furina;")
        requests = []
        workspace.optimizer_all_sets_requested.connect(lambda team, text: requests.append((team, text)))
        workspace.optimizer_all_sets_button.click()
        self.assertEqual(requests, [(0, "active furina;")])
        self.assertEqual(workspace._optimizer_mode, "all_sets")
        self.assertIn("10", workspace.optimizer_elapsed_label.text())
        workspace.set_optimizer_busy(True)
        self.assertFalse(workspace.optimizer_all_sets_button.isEnabled())
        self.assertFalse(workspace.optimizer_selected_button.isEnabled())
        workspace.set_optimizer_busy(False)
        self.assertTrue(workspace.optimizer_all_sets_button.isEnabled())
        workspace.set_optimizer_all_sets_available(False)
        self.assertFalse(workspace.optimizer_all_sets_button.isEnabled())

    def test_theory_gate_signal_and_busy_share_text_result_surface(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.set_optimizer_theory_available(True)
        workspace.rotation_editor.setPlainText("active flins;")
        requests = []
        workspace.optimizer_theory_requested.connect(lambda team, text: requests.append((team, text)))

        workspace.optimizer_theory_button.click()

        self.assertEqual(requests, [(0, "active flins;")])
        self.assertEqual(workspace._optimizer_mode, "theory")
        self.assertIn("0:00", workspace.optimizer_elapsed_label.text())
        workspace.set_optimizer_busy(True)
        self.assertFalse(workspace.optimizer_theory_button.isEnabled())
        self.assertFalse(workspace.optimizer_selected_button.isEnabled())
        workspace.set_optimizer_busy(False)
        self.assertTrue(workspace.optimizer_theory_button.isEnabled())
        workspace.set_optimizer_theory_available(False)
        self.assertFalse(workspace.optimizer_theory_button.isEnabled())

    def test_optimizer_immediately_reports_and_preserves_infinite_rotation(self) -> None:
        workspace = GcsimBrowserWorkspace()
        workspace.set_optimizer_theory_available(True)
        rotation = (
            "options iteration=1000;\n"
            "target lvl=100 hp=999999999;\n"
            "active chiori;\n"
            "while 1 { chiori skill; }\n"
        )
        workspace.rotation_editor.setPlainText(rotation)
        requests: list[tuple[int, str]] = []
        workspace.optimizer_theory_requested.connect(
            lambda team, text: requests.append((team, text))
        )

        workspace.optimizer_theory_button.click()

        self.assertEqual(requests, [(0, rotation)])
        self.assertEqual(workspace.rotation_editor.toPlainText(), rotation)
        self.assertIn("90", workspace.optimizer_progress_label.text())
        self.assertIn("90", workspace.optimizer_result.toPlainText())

    def test_theory_button_routes_complete_virtual_profile_to_production_request(self) -> None:
        workspace = GcsimBrowserWorkspace()
        virtual = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=3,
            character_key="chiori",
            character_name="Chiori",
            character_weapon_type="sword",
            weapon_key="urakumisutogiri",
            weapon_name="Uraku Misugiri",
            weapon_type="sword",
            constellation=2,
            refinement=1,
            character_level=80,
            talent_normal=10,
            talent_skill=10,
            talent_burst=10,
            weapon_level=90,
            weapon_promote_level=6,
            artifact_set_bonuses=(
                GcsimVirtualSetBonus(
                    "GoldenTroupe", "Golden Troupe", "goldentroupe", 4
                ),
            ),
        )
        selected_team = {
            "slots": [
                {"slot_index": 0, "character": {"id": 10000104, "name": "Chasca"}},
                {"slot_index": 1, "character": {"id": 10000105, "name": "Ororon"}},
                {"slot_index": 2, "character": {"id": 10000089, "name": "Furina"}},
                {"slot_index": 3, "gcsim_virtual_override": virtual.to_dict()},
            ]
        }
        shell = SimpleNamespace(
            _gcsim_browser_run_thread=None,
            controller=SimpleNamespace(
                equipment_db_path="account.db",
                gcsim_boosted_energy_enabled=True,
                gcsim_browser_selected_team=lambda _team: selected_team,
            ),
            left_host=SimpleNamespace(gcsim_browser_workspace=workspace),
            _on_gcsim_optimizer_selected_finished=lambda _payload: None,
            _clear_gcsim_run_worker_refs=lambda: None,
            _gcsim_browser_run_worker=None,
            _gcsim_browser_run_rotation_text="",
            _gcsim_optimizer_selected_team=None,
        )
        workspace.optimizer_theory_requested.connect(
            lambda team, text: AppShell._on_gcsim_optimizer_requested(
                shell, team, text, mode="theory"
            )
        )
        workspace.set_optimizer_theory_available(True)
        workspace.rotation_editor.setPlainText("active chiori;")
        worker = MagicMock()
        thread = MagicMock()

        with (
            patch("ui.app_shell.GcsimBrowserSelectedOptimizerWorker", return_value=worker) as worker_type,
            patch("ui.app_shell.QThread", return_value=thread),
        ):
            workspace.optimizer_theory_button.click()

        request = worker_type.call_args.args[0]
        self.assertIsInstance(request, GcsimOptimizerGoTheoryRequest)
        virtual_payload = request.selected_team["slots"][3]["gcsim_virtual_override"]
        self.assertEqual(virtual_payload["character"]["level"], 80)
        self.assertEqual(virtual_payload["character"]["promote_level"], 6)
        self.assertIsNone(virtual_payload["artifact_build_id"])
        self.assertEqual(virtual_payload["artifact_set_bonuses"][0]["count"], 4)
        thread.start.assert_called_once_with()

    def test_three_request_types_route_to_the_same_product_sessions_as_the_buttons(self) -> None:
        request_args = ("account.db", {"slots": []}, 0, "active flins;")
        selected_request = GcsimOptimizerGoSelectedRequest(*request_args)
        all_sets_request = GcsimOptimizerGoAllSetsRequest(*request_args)
        theory_request = GcsimOptimizerGoTheoryRequest(*request_args)

        with (
            patch(
                "ui.gcsim_browser.run_worker.GcsimOptimizerGoSelectedSession"
            ) as selected_session,
            patch(
                "run_workspace.gcsim.optimizer_go_all.GcsimOptimizerGoAllSetsSession"
            ) as all_sets_session,
            patch(
                "run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession"
            ) as theory_session,
        ):
            selected_worker = GcsimBrowserSelectedOptimizerWorker(selected_request)
            all_sets_worker = GcsimBrowserSelectedOptimizerWorker(all_sets_request)
            theory_worker = GcsimBrowserSelectedOptimizerWorker(theory_request)

        self.assertIs(selected_worker._session, selected_session.return_value)
        self.assertIs(all_sets_worker._session, all_sets_session.return_value)
        self.assertIs(theory_worker._session, theory_session.return_value)
        selected_session.assert_called_once_with(
            selected_request,
            progress_callback=selected_worker.progress.emit,
        )
        all_sets_session.assert_called_once_with(
            all_sets_request,
            progress_callback=all_sets_worker.progress.emit,
        )
        theory_session.assert_called_once_with(
            theory_request,
            progress_callback=theory_worker.progress.emit,
        )

    def test_all_sets_button_forwards_virtual_slot_without_saved_build(self) -> None:
        workspace = GcsimBrowserWorkspace()
        virtual = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=0,
            character_key="chiori",
            character_name="Chiori",
            character_weapon_type="sword",
            weapon_key="urakumisutogiri",
            weapon_name="Uraku Misugiri",
            weapon_type="sword",
            character_level=90,
            weapon_level=90,
            weapon_promote_level=6,
        )
        team = {"slots": [{"slot_index": 0, "gcsim_virtual_override": virtual.to_dict()}]}
        shell = SimpleNamespace(
            _gcsim_browser_run_thread=None,
            controller=SimpleNamespace(
                equipment_db_path="account.db",
                gcsim_boosted_energy_enabled=True,
                gcsim_browser_selected_team=lambda _team: team,
            ),
            left_host=SimpleNamespace(gcsim_browser_workspace=workspace),
            _on_gcsim_optimizer_selected_finished=lambda _payload: None,
            _clear_gcsim_run_worker_refs=lambda: None,
            _gcsim_browser_run_worker=None,
            _gcsim_browser_run_rotation_text="",
            _gcsim_optimizer_selected_team=None,
        )
        workspace.optimizer_all_sets_requested.connect(
            lambda index, rotation: AppShell._on_gcsim_optimizer_requested(
                shell, index, rotation, mode="all_sets"
            )
        )
        workspace.set_optimizer_all_sets_available(True)
        workspace.rotation_editor.setPlainText("active chiori;")
        with (
            patch("ui.app_shell.GcsimBrowserSelectedOptimizerWorker") as worker_type,
            patch("ui.app_shell.QThread") as thread_type,
        ):
            workspace.optimizer_all_sets_button.click()

        request = worker_type.call_args.args[0]
        self.assertIsInstance(request, GcsimOptimizerGoAllSetsRequest)
        self.assertIsNone(
            request.selected_team["slots"][0]["gcsim_virtual_override"]["artifact_build_id"]
        )
        self.assertEqual(request.rotation_shell_text, "active chiori;")
        thread_type.return_value.start.assert_called_once_with()

    def test_optimizer_energy_switch_is_one_controllable_view(self) -> None:
        workspace = GcsimBrowserWorkspace()
        changes: list[bool] = []
        workspace.optimizer_infinite_energy_changed.connect(changes.append)

        workspace.set_optimizer_infinite_energy_enabled(True)
        self.assertTrue(workspace.optimizer_infinite_energy_switch.isChecked())
        infinite_note = workspace.optimizer_energy_note.text()
        self.assertTrue(infinite_note)
        self.assertEqual(changes, [])

        workspace.optimizer_infinite_energy_switch.setChecked(False)
        self.assertEqual(changes, [False])
        self.assertTrue(workspace.optimizer_energy_note.text())
        self.assertNotEqual(workspace.optimizer_energy_note.text(), infinite_note)

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
