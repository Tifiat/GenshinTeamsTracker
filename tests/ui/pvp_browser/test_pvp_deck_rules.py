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
from run_workspace.pvp.deck import FREE_DRAFT_V0_RULESET_ID
from run_workspace.pvp.deck_preset import load_deck_presets
from tests.run_workspace.pvp.test_abyss_rules import _character, _deck, _source, _weapon, _screenshot_scale_source
from tests.ui.pvp_browser.test_pvp_browser import _character_asset, _weapon_asset
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

    def test_weapon_prices_stay_in_summary_without_an_inventory_catalog(self):
        inventory = [_weapon_asset("2001", "Test sword")]
        self.workspace._weapon_assets_provider = lambda: inventory
        self.workspace.refresh_account_data()
        self.load_rules()
        panel = PvpDecksRightPanel(self.workspace)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        state = self.workspace.rules_ui_state()
        self.assertNotIn("weapon_rule_lines", state)
        self.assertNotIn("rules_weapon_prices_heading", panel._rules_line_sections)
        self.assertFalse(hasattr(panel, "_weapon_rules_button"))
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_summary").format(value="0"),
                      state["summary_lines"])
        self.workspace._on_weapon_card_clicked(inventory[0])
        self.assertEqual(self.workspace.selected_counts()[1], 1)
        selected = self.workspace.rules_ui_state()
        self.assertNotIn("weapon_rule_lines", selected)
        weapon_summary = next(line for line in selected["summary_lines"]
                              if line.startswith(tr("app_shell.pvp.rules.weapon_roster_summary").split(":")[0]))
        self.assertNotIn("?", weapon_summary)

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

    def test_restart_can_edit_and_save_retained_rules_without_catalog(self):
        self.load_rules()
        self.assertTrue(self.workspace.save_edit())
        before = load_deck_presets(self.temp.name)[0]
        restarted = PvpDecksWorkspace(
            deck_dir=self.temp.name, character_assets_provider=lambda: self.characters,
            weapon_assets_provider=lambda: [],
        )
        self.addCleanup(restarted.close)
        self.assertFalse(restarted.rules_controller.catalog_loaded)
        self.assertTrue(restarted.begin_edit())
        restarted._on_character_card_clicked(self.characters[1])
        self.assertEqual(restarted.rules_ui_state()["freshness"], "unknown")
        self.assertTrue(restarted.save_edit(name="Edited offline"))
        saved = load_deck_presets(self.temp.name)[0]
        self.assertEqual(saved.name, "Edited offline")
        self.assertEqual(saved.character_ids, ("1001",))
        self.assertEqual(saved.rules_snapshot, before.rules_snapshot)

    def test_existing_deck_cannot_save_unchecked_replacement_rules(self):
        self.load_rules()
        self.assertTrue(self.workspace.save_edit())
        self.assertTrue(self.workspace.begin_edit())
        changed = self.rules.to_dict()
        changed["source"]["system_id"] = "f" * 24
        self.workspace._rules_received(
            (self.workspace._rules_edit_generation, self.workspace.active_preset().deck_id),
            AbyssRuleset.from_dict(changed),
        )
        self.workspace.rules_controller.catalog_current = False
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

    def test_screenshot_scale_counters_settle_and_t0_groups_cover_removed_t1(self):
        self.workspace.cancel_edit()
        self.source, characters = _screenshot_scale_source()
        self.characters = [_character_asset(item.character_id, item.display_name) for item in characters]
        for asset in self.characters:
            asset["metadata"]["character"]["constellation"] = 0
        self.rules = AbyssRuleset.from_source(*self.source)
        self.workspace.create_deck("Synthetic screenshot roster")
        self.load_rules()
        panel = PvpDecksRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.drain()

        def coverage():
            return [(row["current"], row["status"]) for row in self.workspace.rules_ui_state()["requirement_rows"]
                    if row.get("detail") == tr("app_shell.pvp.rules.coverage_legend")]

        self.assertEqual(coverage(), [("2 / 2", "pass"), ("3 / 3", "pass")])
        rows = self.workspace.rules_ui_state()["requirement_rows"]
        outside = next(row for row in rows if row["label"] == tr("app_shell.pvp.rules.outside_tiers"))
        self.assertEqual(outside["current"], "36")
        roles = [row for row in rows if row.get("character_filter")]
        self.assertEqual([(row["current"], row["status"]) for row in roles], [("2 / 2", "pass")] * 2)
        self.assertEqual(sum(row["current"] == tr("app_shell.pvp.rules.groups_not_needed") for row in rows), 2)
        self.workspace.toggle_requirement_filter(1, 0)
        self.assertEqual(len(self.workspace.character_cards_by_id), 9)
        self.assertEqual(coverage(), [("2 / 2", "pass"), ("3 / 3", "pass")])
        self.workspace.clear_requirement_filter()

        # Keep one physical T1 of each role; five real T0 triples must cover the rest.
        for asset in self.characters[21:36]:
            self.workspace.character_cards_by_id[asset["metadata"]["character"]["id"]].clicked.emit(asset)
        self.drain()
        self.assertEqual(coverage(), [("2 / 2", "pass"), ("3 / 3", "pass")])
        allocation = self.workspace.rules_controller._allocation_result
        self.assertEqual([row["used"] for row in allocation["equals"]], [5, 0])
        groups = allocation["equals"][0]["groups"]
        self.assertEqual(len({index for group in groups for index in group}), 15)
        self.assertEqual(self.workspace.selected_counts()[0], 63)

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
    def test_free_draft_requirement_counts_all_traveler_variants(self):
        from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_variant_id
        ids = ("10000007",) + tuple(str(traveler_variant_id(10000007, element))
                                    for element in TRAVELER_ELEMENTS if element != "Cryo")
        preset = SimpleNamespace(character_ids=ids, ruleset_id=FREE_DRAFT_V0_RULESET_ID)
        controller = DeckRulesController()
        state = controller.ui_state(preset, editable=True)
        self.assertTrue(state["requirement_rows"][0]["current"].startswith("7 / "))

    def test_selected_required_traveler_has_no_obsolete_unavailable_warning(self):
        rules = AbyssRuleset.from_source(*_source())
        snapshot = rules.to_dict()
        snapshot["preset_rules"] = [{"type": "required_agents", "characters": [
            {"source_id": "required-pyro", "game_id": "10000005", "attribute": 17},
        ]}]
        deck = _deck()
        report = evaluate_deck(deck, rules).to_dict()
        report["character_rows"] = [{"index": 0, "source_id": "required-pyro", "character_id": "-100000076",
                                     "cost": 0, "tier": None, "specification": None}]
        state = format_report(snapshot, report, deck)
        required = next(row for row in state["requirement_rows"] if row["label"] == tr("app_shell.pvp.rules.required_heading"))
        self.assertEqual((required["current"], required["status"]), ("1 / 1", "pass"))
        self.assertNotIn(tr("app_shell.pvp.rules.traveler_unavailable"), state["issue_lines"])

    def test_statuses_distinguish_price_bands_limits_and_unknown_costs(self):
        rules = AbyssRuleset.from_source(*_source())
        deck = _deck(_character("1001", "PYRO"))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(rules.to_dict(), report, deck)
        rows = state["requirement_rows"]
        # One T1 is information, not a violation of the 10–19 cost band.
        tier = next(row for row in rows if row["label"].startswith("T1 ·"))
        self.assertEqual((tier["current"], tier["status"]), ("1", "info"))
        budget_label = tr("app_shell.pvp.rules.limit").format(
            subject=tr("app_shell.pvp.rules.agents_cost"), minimum="20", maximum="40",
        )
        budget = next(row for row in rows if row["label"] == budget_label)
        self.assertEqual((budget["current"], budget["status"]), ("10", "fail"))
        maximum = next(row for row in rows if row["label"] == tr("app_shell.pvp.rules.max_count").format(value=3))
        self.assertEqual((maximum["current"], maximum["status"]), ("1 / 3", "pass"))
        report["character_total"] = None
        uncertain_rows = format_report(rules.to_dict(), report, deck)["requirement_rows"]
        uncertain = next(row for row in uncertain_rows if row["label"] == budget_label)
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
        self.assertTrue(all(row["current"].startswith("— /") for row in combination_rows))
        self.assertIn(tr("app_shell.pvp.rules.allocation_budget"), pending["issue_lines"])
        equivalent = next(row for row in pending["requirement_rows"] if row["label"].startswith("T0 + T0 + T0"))
        self.assertEqual((equivalent["current"], equivalent["status"]), ("—", "unknown"))
        calculating = format_report(snapshot, report, deck, allocation={
            "status": "unknown", "complete": False, "reason": "pending",
        })
        self.assertNotIn(tr("app_shell.pvp.rules.allocation_pending"), calculating["issue_lines"])
        pending_coverage = [row for row in calculating["requirement_rows"]
                            if row.get("detail") == tr("app_shell.pvp.rules.coverage_legend")
                            or row.get("depth") == 1]
        self.assertTrue(pending_coverage)
        self.assertTrue(all(row["status"] == "unknown" for row in pending_coverage))
        policy = next(row for row in calculating["requirement_rows"]
                      if row["label"] == tr("app_shell.pvp.rules.allocation_policy"))
        self.assertEqual(policy["status"], "unknown")
        self.assertEqual(policy["status_detail"], tr("app_shell.pvp.rules.allocation_pending"))
        report["character_rows"][0]["tier"] = None
        uncertain = format_report(snapshot, report, deck)
        parents = [row for row in uncertain["requirement_rows"]
                   if row.get("detail") == tr("app_shell.pvp.rules.coverage_legend")]
        self.assertTrue(all((row["current"], row["status"]) == ("— / ?", "unknown") for row in parents))

    def test_weapon_summary_uses_selected_entry_prices_and_explicit_unknown_count(self):
        language = get_language()
        self.addCleanup(set_language, language, persist=False)
        rules = AbyssRuleset.from_source(*_source())
        snapshot = rules.to_dict()
        deck = _deck(_character("1001", "PYRO"), weapons=(
            _weapon("2001", 1, 2),
            _weapon("2002", 1, 3),
            _weapon("9999", 1, 1),
        ))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(snapshot, report, deck)
        self.assertEqual(report["weapon_roster"]["known_total"], 5)
        self.assertEqual(report["weapon_roster"]["unknown_price_count"], 1)
        partial = tr("app_shell.pvp.rules.weapon_roster_partial").format(known="5", unknown=1)
        expected = tr("app_shell.pvp.rules.weapon_roster_summary").format(value=partial)
        self.assertIn(expected, state["summary_lines"])
        self.assertNotIn("?", expected)
        counter = next(row for row in state["requirement_rows"]
                       if row["label"] == tr("app_shell.pvp.rules.weapon_roster_cost"))
        self.assertEqual((counter["current"], counter["status"]), (partial, "info"))
        self.assertNotIn("weapon_rule_lines", state)

    def test_unknown_inventory_quantity_does_not_change_selected_weapon_cost(self):
        rules = AbyssRuleset.from_source(*_source())
        deck = _deck(_character("1001", "PYRO"), weapons=(_weapon("2002", 1, None),))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(rules.to_dict(), report, deck)
        self.assertIsNone(report["weapon_count"])
        self.assertEqual(report["weapon_roster"]["total"], 2)
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_summary").format(value="2"),
                      state["summary_lines"])
        counter = next(row for row in state["requirement_rows"]
                       if row["label"] == tr("app_shell.pvp.rules.weapon_roster_cost"))
        self.assertEqual((counter["current"], counter["status"]), ("2", "info"))

        snapshot = rules.to_dict()
        snapshot["bounds"]["engines"]["count"] = [0, 2]
        snapshot["bounds"]["engines"]["cost"] = [0, 10]
        legacy_report = dict(report)
        legacy_report.pop("weapon_roster")
        bounded = format_report(snapshot, legacy_report, deck)
        count_label = tr("app_shell.pvp.rules.limit").format(
            subject=tr("app_shell.pvp.rules.engines_count"), minimum="0", maximum="2",
        )
        bounded_rows = {row["label"]: row for row in bounded["requirement_rows"]}
        self.assertEqual(bounded_rows[count_label]["current"],
                         tr("app_shell.pvp.rules.weapon_count_incomplete"))
        self.assertEqual(bounded_rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["current"],
                         "2 / 10")
        self.assertNotIn(tr("app_shell.pvp.rules.limit").format(
            subject=tr("app_shell.pvp.rules.engines_cost"), minimum="0", maximum="10",
        ), bounded_rows)

    def test_roster_policy_rows_show_total_and_expensive_costs_with_source(self):
        system, agents, engines = _source()
        system["_id"] = "6ac54cc57032007b0dd5e4f9"
        system["root"] = "6953c08267a24684c387795c"
        system["updatedAt"] = "2026-10-06T19:34:41.433Z"
        system["costs"]["engines"][0]["costs"] = [14] * 6
        system["costs"]["engines"][1]["costs"] = [15] * 6
        rules = AbyssRuleset.from_source(system, agents, engines)
        deck = _deck(_character("1001", "PYRO"), weapons=(
            _weapon("2001"), _weapon("2002"),
        ))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(rules.to_dict(), report, deck)
        labels = {row["label"]: row for row in state["requirement_rows"]}
        total = labels[tr("app_shell.pvp.rules.weapon_roster_cost")]
        expensive_label = tr("app_shell.pvp.rules.weapon_roster_expensive").format(threshold="15")
        expensive = labels[expensive_label]
        self.assertEqual((total["current"], total["status"]), ("29 / 155", "pass"))
        self.assertEqual((expensive["current"], expensive["status"]), ("15 / 130", "pass"))
        self.assertIn("2026-10-10", total["detail"])
        self.assertIn("docs.google.com/document", total["detail"])
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_pools_detail").format(
            general="130", reserve="25", cheap_max="14"), expensive["detail"])
        self.assertNotIn("docs.google.com/document", expensive["detail"])
        rows = state["requirement_rows"]
        self.assertFalse(any("130 + 25" in row["label"] for row in rows))

        # The reserve is not a separate cap on cheap weapons: these total 28,
        # which exceeds the 25 reserve while remaining within the total pool.
        system["costs"]["engines"][1]["costs"] = [14] * 6
        cheap_rules = AbyssRuleset.from_source(system, agents, engines)
        cheap_deck = _deck(_character("1001", "PYRO"), weapons=(
            _weapon("2001"), _weapon("2002"),
        ))
        cheap_report = evaluate_deck(cheap_deck, cheap_rules).to_dict()
        cheap_rows = {row["label"]: row for row in format_report(
            cheap_rules.to_dict(), cheap_report, cheap_deck)["requirement_rows"]}
        expensive_label = tr("app_shell.pvp.rules.weapon_roster_expensive").format(threshold="15")
        self.assertEqual((cheap_rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["current"],
                          cheap_rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["status"]),
                         ("28 / 155", "pass"))
        self.assertEqual((cheap_rows[expensive_label]["current"],
                          cheap_rows[expensive_label]["status"]),
                         ("0 / 130", "pass"))

        system["costs"]["engines"][0]["costs"] = [160] * 6
        over_rules = AbyssRuleset.from_source(system, agents, engines)
        over_deck = _deck(_character("1001", "PYRO"), weapons=(_weapon("2001"),))
        over_report = evaluate_deck(over_deck, over_rules).to_dict()
        over_state = format_report(over_rules.to_dict(), over_report, over_deck)
        over_rows = {row["label"]: row for row in over_state["requirement_rows"]}
        self.assertEqual((over_rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["current"],
                          over_rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["status"]),
                         ("160 / 155", "fail"))
        self.assertEqual((over_rows[expensive_label]["current"],
                          over_rows[expensive_label]["status"]), ("160 / 130", "fail"))

    def test_unknown_prices_and_unclassified_costs_stay_unknown(self):
        system, agents, engines = _source()
        system["_id"] = "6ac54cc57032007b0dd5e4f9"
        system["root"] = "6953c08267a24684c387795c"
        system["updatedAt"] = "2026-10-06T19:34:41.433Z"
        rules = AbyssRuleset.from_source(system, agents, engines)
        deck = _deck(_character("1001", "PYRO"), weapons=(
            _weapon("2001"), _weapon("9999"),
        ))
        report = evaluate_deck(deck, rules).to_dict()
        state = format_report(rules.to_dict(), report, deck)
        rows = {row["label"]: row for row in state["requirement_rows"]}
        total = rows[tr("app_shell.pvp.rules.weapon_roster_cost")]
        expensive_label = tr("app_shell.pvp.rules.weapon_roster_expensive").format(threshold="15")
        expensive = rows[expensive_label]
        self.assertEqual(total["status"], "unknown")
        self.assertIn("3", total["current"])
        self.assertIn("1", total["current"])
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_unknown_prices").format(count=1),
                      total["detail"])
        self.assertEqual(expensive["status"], "unknown")
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_unknown_prices").format(count=1),
                      expensive["detail"])
        self.assertNotIn("?", total["current"] + expensive["current"])

        # 14.5 falls between the documented ≤14 and ≥15 pools.
        deck = _deck(_character("1001", "PYRO"), weapons=(_weapon("2001"),))
        report = evaluate_deck(deck, rules).to_dict()
        report["weapon_rows"][0]["base_unit_cost"] = 14.5
        report.pop("weapon_roster")
        report["issues"].append({"code": "weapon_roster_classification_unknown",
                                 "details": {"count": 1}})
        classified = format_report(rules.to_dict(), report, deck)
        rows = {row["label"]: row for row in classified["requirement_rows"]}
        self.assertEqual((rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["current"],
                          rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["status"]),
                         ("14.5 / 155", "pass"))
        expensive_label = tr("app_shell.pvp.rules.weapon_roster_expensive").format(threshold="15")
        expensive = rows[expensive_label]
        self.assertEqual(expensive["status"], "unknown")
        self.assertTrue(expensive["current"].startswith(
            tr("app_shell.pvp.rules.weapon_roster_expensive_partial").format(
                known="0", unknown_prices=0, unclassified=1, threshold="15")))
        classification_text = tr("app_shell.pvp.rules.weapon_roster_classification_unknown").format(count=1)
        self.assertIn(classification_text, expensive["detail"])
        self.assertNotIn(classification_text,
                         rows[tr("app_shell.pvp.rules.weapon_roster_cost")]["detail"])
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_classification_unknown").format(count=1),
                      classified["issue_lines"])

    def test_no_policy_still_shows_a_numeric_weapon_counter(self):
        rules = AbyssRuleset.from_source(*_source())
        empty_deck = _deck(_character("1001", "PYRO"))
        empty = format_report(rules.to_dict(), evaluate_deck(empty_deck, rules).to_dict(), empty_deck)
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_summary").format(value="0"),
                      empty["summary_lines"])
        empty_row = next(row for row in empty["requirement_rows"]
                         if row["label"] == tr("app_shell.pvp.rules.weapon_roster_cost"))
        self.assertEqual((empty_row["current"], empty_row["status"]), ("0", "info"))
        self.assertEqual(empty_row["detail"], tr("app_shell.pvp.rules.weapon_roster_policy_unspecified"))

        system, agents, engines = _source()
        system["costs"]["engines"][1]["costs"][0] = 0
        zero_rules = AbyssRuleset.from_source(system, agents, engines)
        zero_deck = _deck(_character("1001", "PYRO"), weapons=(_weapon("2002", 1, 2),))
        zero = format_report(zero_rules.to_dict(), evaluate_deck(zero_deck, zero_rules).to_dict(), zero_deck)
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_summary").format(value="0"),
                      zero["summary_lines"])

    def test_structured_api_budget_precedes_pinned_prose_for_legacy_reports(self):
        system, agents, engines = _source()
        system["_id"] = "6ac54cc57032007b0dd5e4f9"
        system["root"] = "6953c08267a24684c387795c"
        system["updatedAt"] = "2026-10-06T19:34:41.433Z"
        rules = AbyssRuleset.from_source(system, agents, engines)
        deck = _deck(_character("1001", "PYRO"), weapons=(_weapon("2001"),))
        report = evaluate_deck(deck, rules).to_dict()
        report.pop("weapon_roster")
        snapshot = rules.to_dict()
        snapshot["bounds"]["engines"]["cost"] = [0, 100]
        state = format_report(snapshot, report, deck)
        row = next(row for row in state["requirement_rows"]
                   if row["label"] == tr("app_shell.pvp.rules.weapon_roster_cost"))
        self.assertEqual((row["current"], row["status"]), ("3 / 100", "pass"))
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_api_source").format(
            title=system["main"]["title"]), row["detail"])
        self.assertNotIn("155", row["current"])

    def test_weapon_requirements_show_live_pinned_budget_not_manual_weapon_note(self):
        system, agents, engines = _source()
        system["_id"] = "6ac54cc57032007b0dd5e4f9"
        system["root"] = "6953c08267a24684c387795c"
        system["updatedAt"] = "2026-10-06T19:34:41.433Z"
        system["phaseTeams"] = {"maxEnginesCost": 155, "maxEnginesCostStep": 25}
        rules = AbyssRuleset.from_source(system, agents, engines)
        deck = _deck(_character("1001", "PYRO"))
        state = format_report(rules.to_dict(), evaluate_deck(deck, rules).to_dict(), deck)
        rows = state["requirement_rows"]
        labels = {row["label"]: row for row in rows}
        self.assertIn(tr("app_shell.pvp.rules.weapon_price_explanation"), labels)
        self.assertIn(tr("app_shell.pvp.rules.weapon_roster_cost"), labels)
        expensive_label = tr("app_shell.pvp.rules.weapon_roster_expensive").format(threshold="15")
        self.assertIn(expensive_label, labels)
        self.assertFalse(any("130 + 25" in row["label"] for row in rows))
        team_max = labels[tr("app_shell.pvp.rules.phase_teams_weapon_max")]
        self.assertEqual((team_max["current"], team_max["status"], team_max["detail"]),
                         ("155", "info", tr("app_shell.pvp.rules.phase_teams_not_deck_cap")))
        self.assertEqual(labels[tr("app_shell.pvp.rules.phase_teams_weapon_step")]["current"], "25")
        self.assertIn("2026-10-10", labels[tr("app_shell.pvp.rules.weapon_roster_cost")]["detail"])
        joker = labels[tr("app_shell.pvp.rules.manual_joker_regulation")]
        self.assertIn("docs.google.com/document", joker["detail"])

        system["updatedAt"] = "2026-10-06T19:34:41.434Z"
        other_version = AbyssRuleset.from_source(system, agents, engines)
        other = format_report(other_version.to_dict(), evaluate_deck(deck, other_version).to_dict(), deck)
        self.assertFalse(any(row["label"] in {
            tr("app_shell.pvp.rules.manual_joker_regulation"),
        } for row in other["requirement_rows"]))

    def test_weapon_and_match_strings_exist_in_all_locales(self):
        language = get_language()
        self.addCleanup(set_language, language, persist=False)
        for language in ("ru", "en", "pt-br"):
            set_language(language, persist=False)
            for key in (
                "app_shell.pvp.rules.weapon_roster_summary",
                "app_shell.pvp.rules.weapon_roster_partial",
                "app_shell.pvp.rules.weapon_roster_cost",
                "app_shell.pvp.rules.weapon_roster_expensive",
                "app_shell.pvp.rules.weapon_roster_expensive_partial",
                "app_shell.pvp.rules.weapon_roster_pools_detail",
                "app_shell.pvp.rules.weapon_roster_policy_unspecified",
                "app_shell.pvp.rules.weapon_roster_api_source",
                "app_shell.pvp.rules.weapon_roster_regulation_source",
                "app_shell.pvp.rules.weapon_roster_api_bounds",
                "app_shell.pvp.rules.weapon_roster_unknown_prices",
                "app_shell.pvp.rules.weapon_roster_classification_unknown",
                "app_shell.pvp.rules.weapon_roster_cost_exceeded",
                "app_shell.pvp.rules.weapon_roster_expensive_exceeded",
                "app_shell.pvp.rules.weapon_roster_budget_unknown",
                "app_shell.pvp.rules.match_rules_mismatch",
                "app_shell.pvp.rules.match_phase_missing",
                "app_shell.pvp.rules.match_flow_unsupported",
                "app_shell.pvp.rules.match_shared_roster",
                "app_shell.pvp.rules.match_mode_unsupported",
                "app_shell.pvp.rules.regulation_score_difference",
                "app_shell.pvp.draft.immune_ban",
                "app_shell.pvp.draft.immune_pick",
                "app_shell.pvp.draft.immune",
                "app_shell.pvp.post.local_source_game",
                "app_shell.pvp.post.weapon_budget",
                "app_shell.pvp.post.ready_issue.abyss_weapon_budget_invalid",
                "app_shell.pvp.post.ready_issue.abyss_assigned_weapon_price_unknown",
                "app_shell.pvp.post.ready_issue.abyss_assigned_weapon_specialty_unknown",
                "app_shell.pvp.post.restart_count",
                "app_shell.pvp.post.restart_rules",
                "app_shell.pvp.post.restart_adjustment",
                "app_shell.pvp.post.ready_issue.abyss_restart_count_invalid",
            ):
                self.assertNotEqual(tr(key), key)
            self.assertIn("{character}", tr("app_shell.pvp.rules.match_required_missing"))
            self.assertIn("{count}", tr("app_shell.pvp.rules.weapon_roster_classification_unknown"))
            self.assertIn("{threshold}", tr("app_shell.pvp.rules.weapon_roster_expensive"))

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
            self.assertNotIn(tr("app_shell.pvp.rules.allocation_pending"), current["issue_lines"])
            policy = next(row for row in current["requirement_rows"]
                          if row["label"] == tr("app_shell.pvp.rules.allocation_policy"))
            self.assertEqual(policy["status"], "unknown")
            self.assertEqual(policy["status_detail"], tr("app_shell.pvp.rules.allocation_pending"))
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
