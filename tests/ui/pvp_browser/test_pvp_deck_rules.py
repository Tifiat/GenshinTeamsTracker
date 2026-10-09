from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton

from localization import get_language, set_language, tr
from run_workspace.pvp.abyss_client import AbyssRulesChoice
from run_workspace.pvp.abyss_rules import AbyssRuleset, evaluate_deck
from run_workspace.pvp.deck_preset import load_deck_presets
from tests.run_workspace.pvp.test_abyss_rules import _character, _deck, _source, _weapon
from tests.ui.pvp_browser.test_pvp_browser import _character_asset
from ui.pvp_browser.deck_rules import DeckRulesController, format_report
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
        while (self.workspace.rules_controller.loading or self.workspace.rules_controller.requirements_loading) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertFalse(self.workspace.rules_controller.loading)
        self.assertFalse(self.workspace.rules_controller.requirements_loading)

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

    def test_requirement_counts_follow_selection_and_free_draft(self):
        self.load_rules()
        before = self.workspace.rules_ui_state()["requirement_rows"]
        tier = next(row for row in before if row["label"].startswith("T1 ·"))
        self.assertEqual((tier["current"], tier["status"]), ("2", "info"))
        self.workspace.character_cards_by_id["1001"].clicked.emit(self.characters[0])
        after = self.workspace.rules_ui_state()["requirement_rows"]
        tier = next(row for row in after if row["label"].startswith("T1 ·"))
        self.assertEqual((tier["current"], tier["status"]), ("1", "info"))
        self.workspace.select_ruleset("free_draft_v0")
        free = self.workspace.rules_ui_state()["requirement_rows"]
        self.assertEqual((free[0]["current"], free[0]["status"]), ("1 / 11", "fail"))
        self.assertFalse(any(row["label"].startswith("T1 ·") for row in free))

    def test_role_condition_buttons_filter_without_changing_the_deck(self):
        self.source[0]["preset"]["rules"][0]["from"].append({"agent": 1, "specification": 1})
        for row in self.source[0]["costs"]["agents"]:
            row["specification"] = 0  # Public price-editor default, not character roles.
        self.rules = AbyssRuleset.from_source(*self.source)
        self.load_rules()
        panel = PvpDecksRightPanel(self.workspace)
        self.addCleanup(panel.close)
        before = self.workspace.active_preset().to_dict()

        def button(role):
            self.app.processEvents()
            return next(item for item in panel.findChildren(QPushButton, "pvp_requirement_show")
                        if item.isVisibleTo(panel) and item.property("criterionRole") == role)

        button(0).click()
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001"})
        self.assertTrue(button(0).isChecked())
        self.assertEqual(button(0).text(), tr("app_shell.pvp.rules.filter_reset"))
        self.assertEqual(self.workspace.rules_ui_state()["active_character_filter"], (1, 0))
        self.assertTrue(self.workspace.requirement_filter_frame.isVisibleTo(self.workspace))
        button(1).click()
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1002"})
        self.assertFalse(button(0).isChecked())
        self.assertTrue(button(1).isChecked())
        button(1).click()
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001", "1002"})
        self.assertFalse(self.workspace.requirement_filter_frame.isVisibleTo(self.workspace))
        self.assertEqual(self.workspace.active_preset().to_dict(), before)

    def test_active_role_filter_banner_retranslates_immediately(self):
        self.load_rules()
        self.workspace.toggle_requirement_filter(1, 0)
        self.addCleanup(set_language, get_language(), persist=False)
        for language in ("ru", "en", "pt-br"):
            set_language(language, persist=False)
            self.workspace.retranslate_ui()
            expected = tr("app_shell.pvp.rules.filter_active").format(
                tier=1, role=tr("app_shell.pvp.rules.role_dd"), count=1,
            )
            self.assertEqual(self.workspace.requirement_filter_label.text(), expected)
            self.assertEqual(self.workspace.requirement_filter_reset.text(), tr("app_shell.pvp.rules.filter_reset"))

    def test_role_filter_intersects_other_filters_and_clears_for_new_rules(self):
        self.characters[1]["metadata"]["character"]["element"] = "Hydro"
        self.workspace.refresh_account_data(reload_presets=False)
        self.load_rules()
        self.workspace.toggle_requirement_filter(1, 0)
        self.workspace._character_element_filters.add("Hydro")
        self.workspace.refresh_view()
        self.assertFalse(self.workspace.character_cards_by_id)
        self.workspace.requirement_filter_reset.click()
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1002"})
        self.workspace._character_element_filters.clear()
        self.workspace.toggle_requirement_filter(1, 0)
        self.workspace.select_ruleset("free_draft_v0")
        self.assertIsNone(self.workspace.rules_ui_state()["active_character_filter"])
        self.workspace.toggle_requirement_filter(1, 0)
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001", "1002"})
        self.assertFalse(any("character_filter" in row for row in self.workspace.rules_ui_state()["requirement_rows"]))

    def test_role_filter_uses_tier_and_resets_on_rules_version_change(self):
        self.load_rules()
        self.workspace.toggle_requirement_filter(1, 0)
        newer, agents, engines = _source()
        newer["_id"] = "f" * 24
        newer["preset"]["ddAgents"] = ["1002"]
        newer["costs"]["agents"][1]["costs"] = [25] * 7 + [0, 0]
        rules = AbyssRuleset.from_source(newer, agents, engines)
        context = (self.workspace._rules_edit_generation, self.workspace.active_preset().deck_id)
        self.workspace._rules_received(context, rules)
        self.workspace._rules_changed()
        self.assertIsNone(self.workspace.rules_ui_state()["active_character_filter"])
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001", "1002"})
        self.workspace.toggle_requirement_filter(1, 0)
        self.assertFalse(self.workspace.character_cards_by_id)  # The only DD is T4.
        self.workspace.clear_requirement_filter()
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001", "1002"})

    def test_role_filter_preserves_hidden_selection_on_save_and_does_not_persist(self):
        self.load_rules()
        self.workspace.toggle_requirement_filter(1, 0)
        self.assertTrue(self.workspace.save_edit())
        saved = load_deck_presets(self.temp.name)[0]
        self.assertEqual(saved.character_ids, ("1001", "1002"))
        self.workspace.create_deck("Another")
        self.assertIsNone(self.workspace.rules_ui_state()["active_character_filter"])
        self.assertEqual(set(self.workspace.character_cards_by_id), {"1001", "1002"})

    def test_same_roster_reuses_allocation_but_selection_invalidates_it(self):
        self.load_rules()
        from ui.pvp_browser.deck_rules import allocate_requirements
        self.workspace.rules_controller._allocation_rules = None
        with patch("ui.pvp_browser.deck_rules.allocate_requirements", wraps=allocate_requirements) as allocate:
            self.workspace.rules_ui_state()
            self.workspace.rules_ui_state()
            self.drain()
            self.assertEqual(allocate.call_count, 1)
            self.workspace.character_cards_by_id["1001"].clicked.emit(self.characters[0])
            self.workspace.rules_ui_state()
            self.drain()
            self.assertEqual(allocate.call_count, 2)


class DeckRulesPresentationTest(unittest.TestCase):
    def test_statuses_distinguish_price_bands_limits_and_unknown_costs(self):
        rules = AbyssRuleset.from_source(*_source())
        deck = _deck(_character("1001", "PYRO"))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(rules.to_dict(), report, deck)
        rows = state["requirement_rows"]
        # One T1 is information, not a violation of the 10–19 cost band.
        tier = next(row for row in rows if row["label"].startswith("T1 ·"))
        self.assertEqual((tier["current"], tier["status"]), ("1", "info"))
        budget = rows[0]
        self.assertEqual((budget["current"], budget["status"]), ("10", "fail"))
        maximum = next(row for row in rows if row["label"] == tr("app_shell.pvp.rules.max_count").format(value=3))
        self.assertEqual((maximum["current"], maximum["status"]), ("1 / 3", "pass"))
        report["character_total"] = None
        uncertain = format_report(rules.to_dict(), report, deck)["requirement_rows"][0]
        self.assertEqual((uncertain["current"], uncertain["status"]), ("?", "unknown"))

    def test_shared_allocation_counts_and_optional_equivalent_rows(self):
        rules = AbyssRuleset.from_source(*_source())
        snapshot = rules.to_dict()
        snapshot["preset_rules"] = [
            {"type": "requires", "to": 4, "from": [{"tier": 1, "specification": 0}, {"tier": 1, "specification": 1}]},
            {"type": "requires", "to": 3, "from": [{"tier": 1}]},
            {"type": "equals", "to": 1, "from": [{"tier": 0}] * 3, "from_cost": 19},
        ]
        deck = _deck()
        report = evaluate_deck(deck, rules).to_dict()
        report.update(character_rows=[
            {"index": i, "character_id": str(i), "source_id": str(i), "cost": cost,
             "tier": tier, "specification": role}
            for i, (tier, role, cost) in enumerate(((4, None, 70), (4, None, 70), (3, None, 50), (1, 1, 20)))
        ], tier_counts={"4": 2, "3": 1, "1": 1})
        state = format_report(snapshot, report, deck)
        parents = [row for row in state["requirement_rows"] if row.get("detail") == tr("app_shell.pvp.rules.coverage_legend")]
        # One T1 can cover the T3, but cannot also count as T4 support.
        self.assertEqual([(row["current"], row["status"]) for row in parents], [("0 / 2", "fail"), ("1 / 1", "pass")])
        roles = [row for row in state["requirement_rows"] if row.get("depth") == 1]
        self.assertEqual(sum(int(row["current"].split(" / ")[0]) for row in roles), 1)
        equivalent = next(row for row in state["requirement_rows"] if row["label"].startswith("T0 + T0 + T0"))
        self.assertEqual(equivalent["status"], "info")
        pending = format_report(snapshot, report, deck, allocation={"status": "unknown", "complete": False, "reason": "budget"})
        combination_rows = [row for row in pending["requirement_rows"] if row.get("detail") == tr("app_shell.pvp.rules.coverage_legend") or row.get("depth") == 1]
        self.assertTrue(all(row["status"] == "unknown" for row in combination_rows))

    def test_weapon_issues_use_names_and_unknown_conditions_have_readable_fallback(self):
        language = get_language()
        self.addCleanup(set_language, language, persist=False)
        rules = AbyssRuleset.from_source(*_source())
        deck = _deck(_character("1001", "PYRO"), weapons=(
            replace(_weapon("2001"), display_name="Test sword"),
        ))
        report = evaluate_deck(deck, rules).to_dict()
        report["issues"].append({"code": "future_condition", "details": {}})
        for language in ("ru", "en", "pt-br"):
            set_language(language, persist=False)
            lines = format_report(rules.to_dict(), report, deck)["issue_lines"]
            weapon_line = next(line for line in lines if "Test sword" in line)
            self.assertNotIn("2001", weapon_line)
            self.assertIn(tr("app_shell.pvp.rules.unsupported_rule"), lines)
            self.assertFalse(any("app_shell.pvp.rules." in line for line in lines))


class DeckRulesAsyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.002)
        self.assertTrue(predicate())

    def test_rapid_changes_coalesce_and_stale_result_is_not_published(self):
        controller = DeckRulesController()
        rules = AbyssRuleset.from_source(*_source())
        preset = SimpleNamespace(ruleset_id="abyss:" + rules.system_id)
        entered, release = threading.Event(), threading.Event()
        calls, published = [], []
        controller.requirements_changed.connect(lambda: published.append(controller._allocation_result["witness"]))

        def controlled(rows, _rules):
            witness = tuple(row["character_id"] for row in rows)
            calls.append(witness)
            if len(calls) == 1:
                entered.set()
                release.wait(3)
            return {"status": "pass", "complete": True, "witness": witness}

        with patch("ui.pvp_browser.deck_rules.allocate_requirements", side_effect=controlled):
            controller.ui_state(preset, editable=True, rules=rules, deck=_deck(_character("1001", "PYRO")))
            self.wait_for(entered.is_set)
            controller.ui_state(preset, editable=True, rules=rules, deck=_deck(_character("1002", "HYDRO")))
            current = controller.ui_state(preset, editable=True, rules=rules, deck=_deck())
            self.assertEqual(len(calls), 1)
            self.assertIn(tr("app_shell.pvp.rules.allocation_pending"), current["issue_lines"])
            release.set()
            self.wait_for(lambda: not controller.requirements_loading)
        self.assertEqual(calls, [("1001",), ()])
        self.assertEqual(published, [()])

    def test_free_draft_discards_a_pending_abyss_result(self):
        controller = DeckRulesController()
        rules = AbyssRuleset.from_source(*_source())
        entered, release = threading.Event(), threading.Event()
        notifications = []
        controller.requirements_changed.connect(lambda: notifications.append(True))

        def controlled(_rows, _rules):
            entered.set()
            release.wait(3)
            return {"status": "pass", "complete": True}

        with patch("ui.pvp_browser.deck_rules.allocate_requirements", side_effect=controlled):
            controller.ui_state(SimpleNamespace(ruleset_id="abyss:" + rules.system_id), editable=True,
                                rules=rules, deck=_deck(_character("1001", "PYRO")))
            self.wait_for(entered.is_set)
            state = controller.ui_state(SimpleNamespace(ruleset_id="free_draft_v0", character_ids=()), editable=True)
            release.set()
            self.wait_for(lambda: not controller.requirements_loading)
        self.assertEqual(notifications, [])
        self.assertIsNone(controller._allocation_result)
        self.assertEqual(state["requirement_rows"][0]["current"], "0 / 11")
