"""Synthetic setup→preban→clock path; no live profile/window."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from localization import tr, get_language, set_language
from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck_preset import save_deck_preset, set_deck_preset_rules
from run_workspace.pvp.draft_options import DraftMatchOptions
from tests.ui.pvp_browser.test_abyss_match_integration import fixture_rules
from tests.ui.pvp_browser.test_pvp_browser import _asset_character_id
from tests.ui.pvp_browser.test_pvp_period import _workspace_fixture
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel


class PrebanClockFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace, _ = _workspace_fixture(Path(self.temp.name))
        self.addCleanup(self.workspace.close)
        self.now = [0.0]
        self.workspace._draft_time_provider = lambda: self.now[0]
        self.rules = fixture_rules(self.workspace)
        self.assertEqual(DraftMatchOptions().resolve(self.rules),
                         DraftMatchOptions(60, 60000, 300000, free_restarts=3, paid_restarts=(5, 5, 10)))
        self.preset = self.workspace.decks_workspace.presets[0]
        self.save_rules()

    def save_rules(self, unequal=False):
        data = self.rules.to_dict()
        if unequal:
            for row in data["characters"][-2:]:
                row["constellation_costs"] = [84] * 7
        self.rules = AbyssRuleset.from_dict(data)
        first = set_deck_preset_rules(self.preset, self.rules)
        second = replace(first, deck_id="second", name="Opponent")
        if unequal:
            first = replace(first, character_ids=first.character_ids[:22])
        for preset in (first, second):
            save_deck_preset(preset, self.workspace.decks_workspace.deck_dir)
        self.workspace.refresh_account_data(reload_presets=True)

    def action(self):
        return next(row["action"] for row in self.workspace.draft_board_dict()["unified_pool"]["entries"]
                    if row["is_current_legal_target"])

    def test_cost_difference_settings_and_prebans_reach_main_flow(self):
        self.save_rules(unequal=True)
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.player_1_deck_id, panel.player_2_deck_id = "local", "second"
        panel.refresh()
        before = tuple(self.workspace.decks_workspace.presets)
        report = self.workspace.play_preban_report("local", "second")
        self.assertEqual((report.difference, report.count, report.seat), (168, 2, "player_1"))
        self.assertIn("2", panel.preban_preview_label.text())
        self.assertEqual((panel.preban_step_spin.value(), panel.pick_time_spin.value(), panel.reserve_time_spin.value()),
                         (60, 60, 300))
        panel.source_settings_check.setChecked(False)
        panel.preban_step_spin.setValue(84)
        panel.free_restarts_spin.setValue(1)
        panel.paid_restarts_edit.setText("20 / 30")
        self.assertEqual(self.workspace.play_preban_report("local", "second", match_options=panel.match_options()).count, 2)
        panel.start_button.click()
        self.assertIsNotNone(self.workspace.active_draft_session)
        self.assertFalse(panel.source_settings_check.isEnabled())
        controller = self.workspace.active_draft_session.controller
        self.assertEqual(controller.state.match_options.preban_cost_step, 84)
        for _ in range(2):
            action = self.action()
            self.assertEqual(action["type"], "preban_character")
            self.assertTrue(self.workspace.apply_draft_card_click(action))
            self.assertFalse(self.workspace.apply_draft_card_click(action))
        self.assertEqual(self.workspace.draft_board_dict()["current_requirement"]["expected_action_type"],
                         "immune_ban_character")
        for _ in range(26):
            self.assertTrue(self.workspace.apply_draft_card_click(self.action()))
        self.assertTrue(controller.session_state.is_complete)
        self.assertEqual(len(controller.session_state.picked_character_ids_for("player_1")), 8)
        self.assertEqual(len(controller.session_state.picked_character_ids_for("player_2")), 8)
        self.assertEqual(controller.to_board_dict()["progress"]["per_seat"]["player_1"]["expected_bans"], 5)
        self.assertEqual(tuple(self.workspace.decks_workspace.presets), before)
        self.assertTrue(self.workspace.draft_clock_snapshot().finished)
        self.assertTrue(self.workspace.continue_to_assignment())
        for seat in ("player_1", "player_2"):
            picked = controller.session_state.picked_character_ids_for(seat)
            assets = {_asset_character_id(item): item for item in self.workspace._build_character_assets_for_seat(seat)}
            for index, character_id in enumerate(picked):
                self.workspace.handle_build_slot_clicked(seat, index // 4, index % 4)
                self.assertTrue(self.workspace.handle_build_character_clicked(seat, assets[character_id]))
                self.assertTrue(self.workspace.handle_build_weapon_clicked(seat, self.workspace.weapon_assets[0]))
            self.assertTrue(self.workspace.ready_build_seat(seat))
        widget = self.workspace.draft_workspace._timers_result_widget
        self.assertEqual(widget._restart_rules, {"free_restarts": 1, "paid_restarts": (20, 30)})
        widget.restart_inputs["player_1"].setValue(2)
        for seat in ("player_1", "player_2"):
            for index, elapsed in enumerate((30, 30, 40)):
                self.assertTrue(widget.set_timer_seconds_for_test(seat, index, 600 - elapsed))
        self.assertTrue(self.workspace.finalize_match_result())
        result = controller.state.match_result
        self.assertEqual(result.seconds_difference, 20)
        self.assertEqual(result.source_scoring["per_seat"]["player_1"]["penalty_seconds"], 20)

    def test_pause_expiry_reserve_and_rejected_action_do_not_reset_clock(self):
        panel = PvpDraftRightPanel(self.workspace)
        self.addCleanup(panel.close)
        options = DraftMatchOptions(pick_time_ms=1000, reserve_time_ms=1000, auto_on_expire=False)
        self.assertTrue(self.workspace.start_local_draft("local", "local", match_options=options))
        controller = self.workspace.active_draft_session.controller
        with patch.object(controller, "to_board_dict", wraps=controller.to_board_dict) as project:
            self.workspace.draft_board_dict()
            project.reset_mock()
            self.now[0] = 1.4
            self.workspace._tick_draft_clock()
            snapshot = self.workspace.draft_clock_snapshot()
            self.assertEqual(snapshot.pick_remaining_ms, 0)
            self.assertEqual(snapshot.reserve_remaining_ms["player_1"], 600)
            self.assertEqual(project.call_count, 0)
        action = self.action()
        panel.clock_widget.pause_button.click()
        self.assertFalse(self.workspace._draft_tick_timer.isActive())
        self.assertFalse(self.workspace.apply_draft_card_click(action))
        previous_language = get_language()
        self.addCleanup(set_language, previous_language)
        set_language("ru")
        panel.retranslate_ui()
        self.assertEqual(panel.clock_widget.notice_label.text(), tr("app_shell.pvp.clock.paused"))
        set_language("en")
        panel.retranslate_ui()
        self.assertEqual(panel.clock_widget.notice_label.text(), tr("app_shell.pvp.clock.paused"))
        self.now[0] = 10
        self.workspace._tick_draft_clock()
        self.assertEqual(self.workspace.draft_clock_snapshot().reserve_remaining_ms["player_1"], 600)
        panel.clock_widget.pause_button.click()
        self.assertTrue(self.workspace._draft_tick_timer.isActive())
        self.now[0] = 10.7
        self.workspace._tick_draft_clock()
        self.assertTrue(self.workspace.draft_clock_snapshot().expired)
        self.assertIn(tr("app_shell.pvp.clock.expired"), panel.clock_widget.notice_label.text())
        self.assertEqual(len(controller.accepted_actions), 0)
        self.assertTrue(self.workspace.apply_draft_card_click(action))
        snapshot = self.workspace.draft_clock_snapshot()
        self.assertEqual(snapshot.active_seat, "player_2")
        self.assertEqual(snapshot.pick_remaining_ms, 1000)
        self.assertEqual(snapshot.reserve_remaining_ms["player_1"], 0)
        self.assertFalse(self.workspace.apply_draft_card_click(action))
        self.assertEqual(self.workspace.draft_clock_snapshot().action_key, 1)
        self.workspace.clear_active_draft()
        self.assertIsNone(self.workspace.draft_clock_snapshot())
        self.assertFalse(self.workspace._draft_tick_timer.isActive())
        self.assertTrue(self.workspace.start_local_draft("local", "local", match_options=options))
        self.assertTrue(self.workspace._draft_tick_timer.isActive())
        self.workspace._on_application_quit()
        self.assertFalse(self.workspace._draft_tick_timer.isActive())

    def test_disabling_prebans_does_not_change_saved_rules(self):
        self.save_rules(unequal=True)
        self.assertTrue(self.workspace.start_local_draft("local", "second",
                        match_options=DraftMatchOptions(preban_cost_step=0, pick_time_ms=0)))
        state = self.workspace.active_draft_session.controller.state
        self.assertEqual(state.preban_report.count, 0)
        self.assertEqual(state.session_state.current_requirement.action_type, "immune_ban_character")
        self.assertEqual(state.abyss_rules.to_dict()["phase_picks"]["preban_cost_step"], 60)
        self.now[0] = 1000
        self.assertFalse(self.workspace.draft_clock_snapshot().expired)

    def test_missing_prices_and_excessive_prebans_block_launch(self):
        self.save_rules(unequal=True)
        options = DraftMatchOptions(preban_cost_step=1)
        self.assertFalse(self.workspace.can_start_local_draft("local", "second", match_options=options))
        self.assertFalse(self.workspace.start_local_draft("local", "second", match_options=options))
        self.assertIsNone(self.workspace.active_draft_session)

    def test_timer_can_be_disabled_and_bad_penalties_block_start(self):
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.assertTrue(panel.timer_enabled_check.isChecked())
        panel.timer_enabled_check.setChecked(False)
        self.assertEqual(panel.match_options().pick_time_ms, 0)
        self.assertFalse(panel.pick_time_spin.isEnabled())
        panel.paid_restarts_edit.setText("bad")
        self.assertFalse(panel.start_button.isEnabled())
        self.assertEqual(panel.status_label.text(), tr("app_shell.pvp.setup.penalties_invalid"))
        panel.paid_restarts_edit.setText("5 / 5 / 10")
        panel.start_button.click()
        self.assertIsNotNone(self.workspace.active_draft_session)
        self.assertFalse(self.workspace._draft_tick_timer.isActive())
        self.now[0] = 1000
        self.workspace._tick_draft_clock()
        self.assertFalse(self.workspace.draft_clock_snapshot().expired)
        self.assertEqual(len(self.workspace.active_draft_session.controller.accepted_actions), 0)

    def test_auto_toggle_preserves_exact_source_millisecond_clocks(self):
        data = self.rules.to_dict()
        data["phase_picks"]["pick_time"] = 500
        data["phase_picks"]["reserve_time"] = 60500
        self.rules = AbyssRuleset.from_dict(data)
        self.save_rules()
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.auto_on_expire_check.setChecked(False)
        options = panel.match_options().resolve(self.rules)
        self.assertEqual((options.pick_time_ms, options.reserve_time_ms), (500, 60500))
        self.assertFalse(options.auto_on_expire)

    def test_expiry_auto_skips_bans_and_selects_one_legal_character(self):
        self.save_rules(unequal=True)
        options = DraftMatchOptions(pick_time_ms=1000, reserve_time_ms=0)
        self.assertTrue(self.workspace.start_local_draft("local", "second", match_options=options))
        controller = self.workspace.active_draft_session.controller
        for instant in (1.1, 2.2):
            self.now[0] = instant
            self.workspace._tick_draft_clock()
            self.assertTrue(controller.accepted_actions[-1].skip)
            self.assertEqual(controller.accepted_actions[-1].character_id, "")
        self.assertEqual(controller.session_state.banned_character_ids, ())
        from ui.pvp_browser.draft_order import PvpDraftOrderStrip
        strip = PvpDraftOrderStrip()
        self.addCleanup(strip.close)
        strip.set_board(controller.to_board_dict(), portrait_paths={})
        self.assertEqual(strip.position_visual(1)["label_key"], "app_shell.pvp.clock.skipped")
        self.assertEqual(controller.to_board_dict()["progress"]["per_seat"]["player_1"]["actual_bans"], 2)
        before = len(controller.accepted_actions)
        self.now[0] = 3.3
        self.workspace._tick_draft_clock()
        self.assertEqual(len(controller.accepted_actions), before + 1)
        self.assertFalse(controller.accepted_actions[-1].skip)
        self.assertTrue(controller.accepted_actions[-1].character_id)
        self.workspace._tick_draft_clock()
        self.assertEqual(len(controller.accepted_actions), before + 1)


class DraftOptionsTest(unittest.TestCase):
    def test_invalid_override_fields_are_rejected(self):
        for payload in ({"preban_cost_step": -1}, {"pick_time_ms": True},
                        {"reserve_time_ms": 86400001}, {"pick_time_ms": 1.5}):
            with self.assertRaises(ValueError):
                DraftMatchOptions(**payload)
