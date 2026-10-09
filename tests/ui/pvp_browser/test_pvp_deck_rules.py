from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from run_workspace.pvp.abyss_client import AbyssRulesChoice
from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck_preset import load_deck_presets
from tests.run_workspace.pvp.test_abyss_rules import _source
from tests.ui.pvp_browser.test_pvp_browser import _character_asset
from ui.pvp_browser.window import PvpDecksWorkspace
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel


class PvpDeckRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.characters = [_character_asset("1001", "A"), _character_asset("1002", "B")]
        for asset in self.characters:
            asset["metadata"]["character"]["constellation"] = 0
        self.source = _source()
        self.rules = AbyssRuleset.from_source(*self.source)
        self.workspace = PvpDecksWorkspace(
            deck_dir=self.temp.name, character_assets_provider=lambda: self.characters,
            weapon_assets_provider=lambda: [],
        )
        self.addCleanup(self.workspace.close)
        self.workspace.create_deck("Rules")

    def choice(self, rules):
        return AbyssRulesChoice(rules.system_id, rules.root_id, rules.title, rules.updated_at)

    def drain(self):
        deadline = time.monotonic() + 3
        while self.workspace.rules_controller.loading and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertFalse(self.workspace.rules_controller.loading)

    def load_rules(self):
        with patch("ui.pvp_browser.deck_rules.abyss_client.list_latest_rulesets", return_value=(self.choice(self.rules),)), \
             patch("ui.pvp_browser.deck_rules.abyss_client.fetch_ruleset_source", return_value=self.source):
            self.workspace.refresh_rules_catalog()
            self.drain()
            self.assertTrue(self.workspace.select_ruleset("abyss:" + self.rules.system_id))
            self.drain()

    def test_async_load_cost_badges_save_reopen_and_cancel(self):
        self.load_rules()
        state = self.workspace.rules_ui_state()
        self.assertEqual(state["freshness"], "current")
        self.assertTrue(state["requirement_lines"])
        self.assertFalse(any("app_shell.pvp.rules." in line for line in state["summary_lines"] + state["requirement_lines"] + state["issue_lines"]))
        badges = self.workspace.character_grid.item("1001").badges
        self.assertTrue(any(badge.text == "T1" for badge in badges))
        self.assertTrue(any(badge.text == "10" for badge in badges))
        self.assertTrue(self.workspace.save_edit())
        saved = load_deck_presets(self.temp.name)[0]
        self.assertEqual(saved.ruleset_id, "abyss:" + self.rules.system_id)
        self.assertEqual(saved.rules_snapshot["source"]["system_id"], self.rules.system_id)
        self.workspace.begin_edit()
        self.workspace.select_ruleset("free_draft_v0")
        self.workspace.cancel_edit()
        self.assertEqual(self.workspace.active_rules().system_id, self.rules.system_id)
        self.workspace.delete_selected()
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_new_version_only_and_explicit_update_preserves_selection(self):
        self.load_rules()
        self.workspace.save_edit()
        newer, agents, engines = _source()
        newer["_id"] = "f" * 24
        newer["updatedAt"] = "2026-10-10T00:00:00Z"
        new_rules = AbyssRuleset.from_source(newer, agents, engines)
        self.workspace.rules_controller._finished("catalog", None, (self.choice(new_rules),), "")
        state = self.workspace.rules_ui_state()
        self.assertEqual(state["freshness"], "update")
        self.assertNotIn("abyss:" + self.rules.system_id, [item["id"] for item in state["options"]])
        self.workspace.begin_edit()
        self.assertFalse(self.workspace.save_edit())
        self.assertFalse(self.workspace.select_ruleset("abyss:" + self.rules.system_id))
        with patch("ui.pvp_browser.deck_rules.abyss_client.fetch_ruleset_source", return_value=(newer, agents, engines)):
            self.assertTrue(self.workspace.update_ruleset())
            self.drain()
        self.assertEqual(self.workspace.active_preset().character_ids, ("1001", "1002"))
        self.assertEqual(self.workspace.active_rules().system_id, new_rules.system_id)
        self.assertTrue(self.workspace.save_edit())

    def test_cancelled_response_cannot_change_a_new_edit(self):
        old_context = (self.workspace._rules_edit_generation, self.workspace.active_preset().deck_id)
        self.workspace.cancel_edit()
        self.workspace.create_deck("Another")
        self.workspace._rules_received(old_context, self.rules)
        self.assertFalse(self.workspace.active_preset().rules_snapshot)

    def test_failed_refresh_retains_saved_snapshot_and_marks_unknown(self):
        self.load_rules()
        before = self.workspace.active_preset().rules_snapshot
        self.workspace.rules_controller._finished("catalog", None, None, "abyss_transport_error")
        self.assertEqual(self.workspace.active_preset().rules_snapshot, before)
        self.assertEqual(self.workspace.rules_ui_state()["freshness"], "unknown")
        self.assertEqual(len(self.workspace.rules_ui_state()["options"]), 1)
        self.assertFalse(self.workspace.save_edit())

    def test_integrated_panel_can_show_and_save_an_abyss_edit(self):
        self.load_rules()
        panel = PvpDecksRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.assertEqual(panel.ruleset_button.currentData(), "abyss:" + self.rules.system_id)
        self.assertTrue(panel.ruleset_button.isEnabled())
        self.workspace.save_edit()
        self.assertFalse(panel.ruleset_button.isEnabled())
