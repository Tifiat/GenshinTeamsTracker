"""Scoped browser preparation; no engine execution or physical UI acceptance."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtTest import QSignalSpy

from ui.gcsim_browser.window import GcsimBrowserWorkspace
from run_workspace.gcsim.rotation_editor.team import from_selected_team
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from tests.ui.pvp_browser.test_pvp_artifacts import PvpBuildFixture
from tests.ui.pvp_browser.test_pvp_browser import _asset_character_id


class PvpGcsimPreparationUiTest(PvpBuildFixture):
    def test_rotation_import_uses_selected_pvp_team_and_explicit_engine_keys(self) -> None:
        context = self.context.seat("player_1")
        chosen = tuple(context.picked_character_ids[:5])
        keys = ("furina", "ororon", "bennett", "chasca", "mona")
        for index, character_id in enumerate(chosen[:4]):
            context.controller.selected_team_index = 0
            context.controller.selected_slot_index = index
            asset = next(item for item in context.character_assets if _asset_character_id(item) == character_id)
            if index:
                self.assertTrue(context.add_or_replace_character(asset))
        context.controller.selected_team_index = 1
        context.controller.selected_slot_index = 0
        fifth = next(item for item in context.character_assets if _asset_character_id(item) == chosen[4])
        self.assertTrue(context.add_or_replace_character(fifth))
        identity = dict(zip(chosen, keys))

        def load_explicit_team(payload, *, scope, database):
            self.assertEqual(database, context.db_path)
            return from_selected_team(payload, scope=scope, lookup=lambda character_id: {
                "gcsim_character_key_status": "ready", "gcsim_character_key": identity[character_id],
            } if character_id in identity else {})

        with patch("run_workspace.gcsim.rotation_editor.team.load_selected_team", side_effect=load_explicit_team):
            browser = context.ensure_gcsim_browser(self.workspace.draft_workspace.build_browser_stack)
            self.assertIs(browser.rotation_team_provider.__self__, context.controller)
            browser.team_tabs.setCurrentIndex(0)
            selected = browser._current_rotation_team()
            self.assertEqual(selected.keys, keys[:4])
            self.assertFalse(selected.unresolved)
            browser.team_tabs.setCurrentIndex(1)
            self.assertEqual(browser._current_rotation_team().keys, keys[4:])
        self.assert_sources_unchanged()

    def test_browser_is_reused_per_seat_and_executable_actions_are_unavailable(self) -> None:
        panel = PvpDraftRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.postdraft_gcsim_buttons_by_seat["player_1"].click()
        first = self.context.seat("player_1").gcsim_browser
        self.assertIsInstance(first, GcsimBrowserWorkspace)
        self.assertIs(first.rotation_team_provider.__self__, self.context.seat("player_1").controller)
        self.assertFalse(first.isWindow())
        self.assertEqual(self.context.browser_kind, "gcsim")
        self.assertFalse(first.workspace_tabs.isTabVisible(1))
        self.assertTrue(first._team_cards[0][0].activate_virtual_button.isHidden())
        spies = [QSignalSpy(first.run_selected_requested), QSignalSpy(first.run_all_requested),
                 QSignalSpy(first.optimizer_selected_requested)]
        first.set_actions_busy(False)
        first.set_optimizer_busy(False)
        first._request_run_selected_chamber()
        first._request_run_all_chambers()
        first._request_optimizer_selected()
        self.assertEqual([spy.count() for spy in spies], [0, 0, 0])
        self.assertFalse(first.run_selected_button.isEnabled())
        first.rotation_editor.setPlainText("first rotation")
        changed = QSignalSpy(self.workspace.state_changed)
        self.workspace.handle_build_slot_clicked("player_2", 0, 0)
        self.assertEqual(changed.count(), 1)
        self.assertEqual(self.context.browser_seat, "player_2")
        second = self.context.seat("player_2").gcsim_browser
        self.assertIsNot(first, second)
        self.assertIs(second.rotation_team_provider.__self__, self.context.seat("player_2").controller)
        second.rotation_editor.setPlainText("second rotation")
        second.set_prepare_result_text("second report")
        self.workspace.close_build_browser()
        self.workspace.open_build_gcsim("player_1")
        self.assertIs(first, self.context.seat("player_1").gcsim_browser)
        self.assertEqual(first.rotation_editor.toPlainText(), "first rotation")
        self.assertNotEqual(first._last_result_text, "second report")
        self.assert_sources_unchanged()

    def test_prepare_routes_fresh_gear_db_and_outputs_then_clear_cleans_only_outputs(self) -> None:
        calls = []

        def builder(**kwargs):
            calls.append(kwargs)
            config = kwargs["run_dir"] / "fixture.txt"
            config.write_text("fixture config", encoding="utf-8")
            return SimpleNamespace(to_dict=lambda: {"status": "fixture", "ready": True,
                "config_path": str(config), "team": {"characters": []}})

        roots = []
        with patch("ui.pvp_browser.build_flow._selected_gcsim_engine_id", return_value="fixture-engine"), \
             patch("ui.gcsim_browser.run_worker._active_run_binding", return_value=SimpleNamespace(artifact_registry="fixture-registry")), \
             patch("run_workspace.pvp.gcsim_preparation.build_selected_team_full_config_report", side_effect=builder):
            for seat in ("player_1", "player_2"):
                self.workspace.open_build_artifacts(seat)
                context = self.context.seat(seat)
                context.artifact_browser.select_build_preset(context.artifact_browser.build_presets[0]["id"])
                context.artifact_browser.apply_selected_build_preset_to_current_equipment()
                self.workspace.open_build_gcsim(seat)
                context.gcsim_browser.prepare_requested.emit(0, f"{seat} rotation")
                self.assertIsNotNone(context.gcsim_preparation.output_root)
                roots.append(context.gcsim_preparation.output_root)
                self.assertTrue(roots[-1].is_dir())
                self.assertEqual(calls[-1]["db_path"], context.db_path)
                self.assertEqual(calls[-1]["artifact_set_registry_source"], "fixture-registry")
                self.assertFalse(calls[-1]["allow_account_equipment_fallback"])
                self.assertTrue(calls[-1]["selected_team"])
                self.assertEqual(calls[-1]["rotation_shell_path"].read_text(encoding="utf-8"), f"{seat} rotation")
            self.assertNotEqual(*roots)
            self.assertNotEqual(calls[0]["selected_team"], calls[1]["selected_team"])
            second = self.context.seat("player_2").gcsim_browser
            second_text = second._last_result_text
            first = self.context.seat("player_1")
            first.artifact_browser.equip_clicked_artifact(8)
            self.assertNotIn("fixture", first.gcsim_browser._last_result_text)
            self.assertEqual(second._last_result_text, second_text)
        self.workspace.clear_active_draft()
        self.assertTrue(all(not path.exists() for path in roots))
        self.assertEqual(self.workspace.draft_workspace.build_browser_stack.count(), 0)
        self.assert_sources_unchanged()

    def test_normal_browser_retains_run_and_virtual_controls(self) -> None:
        browser = GcsimBrowserWorkspace()
        self.addCleanup(browser.close)
        self.assertTrue(browser.workspace_tabs.isTabVisible(1))
        self.assertFalse(browser.run_selected_button.isHidden())
        self.assertFalse(browser._team_cards[0][0].activate_virtual_button.isHidden())
        run = QSignalSpy(browser.run_selected_requested)
        browser._request_run_selected_chamber()
        self.assertEqual(run.count(), 1)
