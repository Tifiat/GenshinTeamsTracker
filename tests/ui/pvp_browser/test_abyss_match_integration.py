"""Synthetic local Play → source draft → build → timer path; no live account."""
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PySide6.QtWidgets import QApplication

from localization import tr
from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck_preset import save_deck_preset
from tests.run_workspace.pvp.test_abyss_rules import _source
from tests.ui.pvp_browser.test_pvp_period import _workspace_fixture
from tests.ui.pvp_browser.test_pvp_browser import _asset_character_id
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.right_panel.pvp._shared import _draft_action_label


def fixture_rules(workspace):
    """Real 6 Oct Cup action sequence, synthetic source identities/prices."""
    system, _, _ = _source()
    system["main"]["mode"] = "shiyu"
    inventory = workspace.decks_workspace._inventory_draft
    agents = [{"_id": f"{100 + index:024x}", "enkaId": item.character_id,
               "attribute": 17, "specialty": 5, "name": {"en": item.display_name}}
              for index, item in enumerate(inventory.characters)]
    engines = [{"_id": f"{900 + index:024x}", "enkaId": item.weapon_id, "specialty": 5}
               for index, item in enumerate(inventory.weapons)]
    system["costs"].update(agents=[{"agent": row["_id"], "costs": [1] * 7 + [0, 0]}
                                    for row in agents],
                           engines=[{"engine": row["_id"], "costs": [2] * 5 + [0]}
                                    for row in engines], agentsBundles=[],
                           tiers=[{"tier": 0, "minCost": 0, "maxCost": 14}])
    system["draft"] = {"minMaxCosts": {"agents": [0, 0], "engines": [0, 0]},
                       "minMaxCount": {"agents": [0, 0], "engines": [0, 0]}}
    system["preset"] = {"rules": [], "ddAgents": []}
    actions = [("IMMUNE_BAN", 0), ("IMMUNE_BAN", 1), ("IMMUNE_PICK", 0), ("IMMUNE_PICK", 1),
               ("BAN", 0), ("BAN", 1), ("BAN", 0), ("BAN", 1),
               ("PICK", 0), ("PICK", 1), ("PICK", 1), ("PICK", 0), ("PICK", 0), ("PICK", 1),
               ("IMMUNE", 0), ("IMMUNE", 1), ("BAN", 1), ("BAN", 0),
               ("PICK", 1), ("PICK", 0), ("PICK", 0), ("PICK", 1), ("PICK", 1), ("PICK", 0),
               ("IMMUNE", 0), ("IMMUNE", 1)]
    system["phasePicks"] = {"flow": [{"type": kind, "player": f"player{seat}"} for kind, seat in actions],
                            "absoluteImmune": [], "prebanCostStep": 60, "pickTime": 60000,
                            "reserveTime": 300000}
    system["phaseTeams"] = {"maxEnginesCost": 500, "maxEnginesCostStep": 500}
    system["phaseStage"] = {"isEnabled": False}
    system["phaseMatch"] = {"freeRestarts": 3, "paidRestarts": [5, 5, 10]}
    return AbyssRuleset.from_source(system, agents, engines)


class AbyssMatchIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace, _ = _workspace_fixture(Path(self.temp.name))
        self.addCleanup(self.workspace.close)
        self.rules = fixture_rules(self.workspace)
        self.save_rules()

    def save_rules(self, *, deck_id="local", rules=None):
        original = self.workspace.decks_workspace.presets[0]
        rules = rules or self.rules
        save_deck_preset(replace(original, deck_id=deck_id, ruleset_id="abyss:" + rules.system_id,
                                rules_snapshot=rules.to_dict()), self.workspace.decks_workspace.deck_dir)
        self.workspace.refresh_account_data(reload_presets=True)

    def test_source_actions_are_clickable_and_reach_existing_build(self):
        self.assertTrue(self.workspace.can_start_local_draft("local", "local"))
        self.assertTrue(self.workspace.start_local_draft("local", "local"))
        types = []
        for _ in range(26):
            board = self.workspace.draft_board_dict()
            entry = next(row for row in board["unified_pool"]["entries"] if row["is_current_legal_target"])
            types.append(entry["action"]["type"])
            self.assertTrue(self.workspace.apply_draft_card_click(entry["action"]))
        self.assertIn("immune_ban_character", types)
        self.assertIn("immune_pick_character", types)
        self.assertEqual(types.count("immune_character"), 4)
        for action in set(types):
            self.assertNotEqual(_draft_action_label(action), action)
        state = self.workspace.active_draft_session.controller.session_state
        self.assertEqual(len(state.picked_character_ids_for("player_1")), 8)
        self.assertEqual(len(state.picked_character_ids_for("player_2")), 8)
        self.assertTrue(self.workspace.continue_to_assignment())
        self.assertIsNotNone(self.workspace.build_flow_context)

    def test_different_rules_block_button_and_launch(self):
        newer = self.rules.to_dict()
        newer["source"]["system_id"] = "f" * 24
        self.save_rules(deck_id="other", rules=AbyssRuleset.from_dict(newer))
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.player_1_deck_id = "local"
        panel.player_2_deck_id = "other"
        panel.refresh()
        self.assertFalse(panel.start_button.isEnabled())
        self.assertEqual(panel.status_label.text(), tr("app_shell.pvp.rules.match_rules_mismatch"))
        self.assertFalse(self.workspace.start_local_draft("local", "other"))
        self.assertIsNone(self.workspace.active_draft_session)

    def test_old_snapshot_shows_update_instruction(self):
        data = self.rules.to_dict()
        data.pop("phase_picks")
        self.save_rules(rules=AbyssRuleset.from_dict(data))
        status = self.workspace.deck_start_status("local", player_label="Player 1")
        self.assertFalse(status.ready)
        self.assertEqual(status.text, tr("app_shell.pvp.rules.match_phase_missing"))

    def test_fetch_time_does_not_make_same_rules_incompatible(self):
        data = self.rules.to_dict()
        data["source"]["fetched_at"] = "2026-10-09T12:00:00Z"
        self.save_rules(deck_id="other", rules=AbyssRuleset.from_dict(data))
        self.assertEqual(self.workspace.match_rules_status("local", "other"), "")
        self.assertTrue(self.workspace.can_start_local_draft("local", "other"))

    def test_build_weapon_budget_restart_inputs_and_adjusted_result(self):
        self.assertTrue(self.workspace.start_local_draft("local", "local"))
        for _ in range(26):
            board = self.workspace.draft_board_dict()
            entry = next(row for row in board["unified_pool"]["entries"] if row["is_current_legal_target"])
            self.assertTrue(self.workspace.apply_draft_card_click(entry["action"]))
        self.assertTrue(self.workspace.continue_to_assignment())
        for seat in ("player_1", "player_2"):
            picked = self.workspace.active_draft_session.controller.session_state.picked_character_ids_for(seat)
            assets = {_asset_character_id(item): item for item in self.workspace._build_character_assets_for_seat(seat)}
            for index, character_id in enumerate(picked):
                self.workspace.handle_build_slot_clicked(seat, index // 4, index % 4)
                self.assertTrue(self.workspace.handle_build_character_clicked(seat, assets[character_id]))
                self.assertTrue(self.workspace.handle_build_weapon_clicked(seat, self.workspace.weapon_assets[0]))
        budget = self.workspace.abyss_weapon_budget()
        self.assertEqual([row["total"] for row in budget["per_seat"].values()], [16, 16])
        self.assertTrue(self.workspace.ready_build_seat("player_1"))
        self.assertTrue(self.workspace.ready_build_seat("player_2"))
        widget = self.workspace.draft_workspace._timers_result_widget
        self.assertIsNotNone(widget)
        widget.restart_inputs["player_1"].setValue(4)
        self.assertEqual(self.workspace.restart_counts_by_seat["player_1"], 4)
        for seat, times in (("player_1", (30, 30, 39)), ("player_2", (30, 30, 40))):
            for index, elapsed in enumerate(times):
                self.assertTrue(widget.set_timer_seconds_for_test(seat, index, 600 - elapsed))
        self.assertIn("104", widget.total_labels["player_1"].text())
        self.assertTrue(self.workspace.finalize_match_result())
        result = self.workspace.active_draft_session.controller.state.match_result.to_dict()
        self.assertEqual(result["winner_seat"], "player_2")
        self.assertEqual(result["seconds_difference"], 4)
        self.assertEqual(result["totals"]["player_1"], 99)
        self.assertEqual(result["source_scoring"]["per_seat"]["player_1"]["penalty_seconds"], 5)
        self.assertFalse(self.workspace.active_draft_session.controller.to_board_dict()["status"]["bundle_ready"])
        self.assertIn("104", widget.total_labels["player_1"].text())

    def test_mandatory_traveler_is_named_in_play(self):
        data = self.rules.to_dict()
        traveler = dict(data["characters"][0], game_id="10000007", source_id="a" * 24,
                        names={"en": "Traveler", "ru": "Путешественница"}, attribute=17)
        data["characters"].append(traveler)
        data["preset_rules"].append({"type": "required_agents", "characters": [
            {key: traveler[key] for key in ("source_id", "game_id", "attribute")}]})
        self.save_rules(rules=AbyssRuleset.from_dict(data))
        status = self.workspace.deck_start_status("local", player_label="Player 1")
        self.assertFalse(status.ready)
        self.assertIn("abyss_required_character_missing", status.issue_codes)
        self.assertNotEqual(status.text, tr("app_shell.pvp.play.start_blocked"))
        self.assertTrue("Traveler" in status.text or "Путешественница" in status.text)

    def test_pair_without_shared_immunity_candidates_is_blocked(self):
        original = self.workspace.decks_workspace.presets[0]
        for deck_id, characters in (("local", original.character_ids[:12]), ("other", original.character_ids[12:])):
            save_deck_preset(replace(original, deck_id=deck_id, character_ids=characters),
                             self.workspace.decks_workspace.deck_dir)
        self.workspace.refresh_account_data(reload_presets=True)
        self.assertTrue(self.workspace.deck_start_status("local", player_label="Player 1").ready)
        self.assertFalse(self.workspace.can_start_local_draft("local", "other"))
        self.assertEqual(self.workspace.match_rules_status("local", "other"),
                         tr("app_shell.pvp.rules.match_shared_roster").format(minimum=4, actual=0))
        self.assertFalse(self.workspace.start_local_draft("local", "other"))

    def test_repeated_play_readiness_reuses_report_and_refresh_invalidates_it(self):
        from ui.pvp_browser.window import validate_abyss_match_deck
        self.workspace._deck_start_cache = {}
        with patch("ui.pvp_browser.window.validate_abyss_match_deck", wraps=validate_abyss_match_deck) as evaluate:
            first = self.workspace.deck_start_status("local", player_label="Player 1")
            self.assertIs(self.workspace.deck_start_status("local", player_label="Player 1"), first)
            self.assertEqual(evaluate.call_count, 1)
            self.workspace.refresh_account_data(reload_presets=True)
            self.workspace.deck_start_status("local", player_label="Player 1")
            self.assertEqual(evaluate.call_count, 2)

    def test_source_phases_survive_export_import_and_launch(self):
        package = Path(self.temp.name) / "abyss.gttpvp"
        self.assertTrue(self.workspace.decks_workspace.export_profile(package))
        self.assertTrue(self.workspace.import_profile_for_seat("player_2", package))
        remote = self.workspace.play_deck_options("player_2")[0]
        self.assertEqual(remote.rules_snapshot, self.rules.to_dict())
        self.assertTrue(self.workspace.can_start_local_draft("local", remote.deck_id))
        self.assertTrue(self.workspace.start_local_draft("local", remote.deck_id))


if __name__ == "__main__":
    unittest.main()
