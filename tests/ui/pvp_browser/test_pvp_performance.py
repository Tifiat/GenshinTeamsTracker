"""Synthetic, offscreen Decks hot-path regressions; never opens an account DB."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import statistics
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck_preset import deck_preset_to_draft_deck, set_deck_preset_rules
from tests.run_workspace.pvp.test_abyss_rules import _screenshot_scale_source
from tests.ui.pvp_browser.test_pvp_browser import (
    _character_asset, _weapon_asset, _create_test_asset_images,
)
from ui.app_shell import CharacterWeaponWorkspace, RosterSelectionMarker
from ui.pvp_browser import deck_rules
from ui.pvp_browser.window import PvpDecksWorkspace, PvpDeckGridItemHandle
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel


class PvpDecksPerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pvp-selection-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        portrait, weapon = _create_test_asset_images(self.temp.name)
        source, roster = _screenshot_scale_source()
        self.characters = [_character_asset(c.character_id, c.display_name, image_path=portrait) for c in roster]
        for asset in self.characters:
            asset["metadata"]["character"]["constellation"] = 0
        self.weapons = [_weapon_asset(str(99000 + i), f"W{i}", image_path=weapon) for i in range(70)]
        self.workspace = PvpDecksWorkspace(
            db_path=self.root / "unused.db", deck_dir=self.root / "decks",
            character_assets_provider=lambda: self.characters,
            weapon_assets_provider=lambda: self.weapons,
        )
        self.workspace.create_deck("Performance")
        self.workspace._editing_preset = set_deck_preset_rules(
            self.workspace.active_preset(), AbyssRuleset.from_source(*source),
        )
        self.workspace.refresh_view()
        self.panel = PvpDecksRightPanel(self.workspace)
        self.addCleanup(self.close_widgets)
        self.settle_allocation()

    def settle(self):
        for _ in range(3):
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def settle_allocation(self):
        deadline = time.monotonic() + 5
        while self.workspace.rules_controller.requirements_loading:
            self.assertLess(time.monotonic(), deadline, "Allocation did not settle")
            QThreadPool.globalInstance().waitForDone(100)
            self.settle()
        self.settle()

    def close_widgets(self):
        self.settle_allocation()
        self.panel.close()
        self.workspace.close()
        self.panel.deleteLater()
        self.workspace.deleteLater()
        self.settle()
        self.assertFalse((self.root / "unused.db").exists())

    def test_select_and_deselect_keep_grids_images_handles_and_panel(self):
        ws = self.workspace
        for kind, asset, grid, registry, callback in (
            ("character", self.characters[0], ws.character_grid, ws.character_cards_by_id, ws._on_character_card_clicked),
            ("weapon", self.weapons[0], ws.weapon_grid, ws.weapon_cards_by_key, ws._on_weapon_card_clicked),
        ):
            with self.subTest(kind=kind), ExitStack() as stack:
                counts = ws.selected_counts()
                item_id = (asset["metadata"]["character"]["id"] if kind == "character"
                           else ws._weapon_key_for_asset(asset))
                original = grid.item(item_id)
                untouched = {key: grid.item(key) for key in grid.item_ids() if key != item_id}
                handles = dict(registry)
                pixmaps = grid._prepared_pixmaps
                requirements = self.panel._requirement_section
                counts_label = self.panel.selected_info_labels["counts"]
                spies = [stack.enter_context(patch.object(target, method, wraps=getattr(target, method)))
                         for target, method in (
                             (ws, "refresh_view"), (ws, "_load_character_assets"), (ws, "_load_weapon_assets"),
                             (ws.character_grid, "set_items"), (ws.weapon_grid, "set_items"),
                             (ws.character_grid, "_refresh_prepared_pixmaps"),
                             (ws.weapon_grid, "_refresh_prepared_pixmaps"), (self.panel, "_rebuild_deck_list"),
                         )]
                converter = stack.enter_context(patch("ui.pvp_browser.window.deck_preset_to_draft_deck", wraps=deck_preset_to_draft_deck))
                callback(asset)
                self.assertTrue(grid.item_property(item_id, "deckInactive"))
                changed_counts = list(counts)
                changed_counts[0 if kind == "character" else 1] -= 1
                self.assertEqual(ws.selected_counts(), tuple(changed_counts))
                self.assertIn(str(changed_counts[0]), counts_label.text())
                self.settle_allocation()
                callback(asset)
                self.assertFalse(grid.item_property(item_id, "deckInactive"))
                self.assertEqual(ws.selected_counts(), counts)
                self.settle_allocation()
                self.assertEqual(grid.item(item_id).badges, original.badges)
                self.assertEqual(registry, handles)
                self.assertIs(grid._prepared_pixmaps, pixmaps)
                self.assertIs(self.panel._requirement_section, requirements)
                self.assertIs(self.panel.selected_info_labels["counts"], counts_label)
                for key, item in untouched.items():
                    self.assertIs(grid.item(key), item)
                converter.assert_not_called()
                for spy in spies:
                    spy.assert_not_called()

    def test_allocation_completion_and_weapon_click_reuse_character_allocation(self):
        ws = self.workspace
        controller = ws.rules_controller
        initial = controller._allocation_generation
        with patch.object(deck_rules, "evaluate_deck", wraps=deck_rules.evaluate_deck) as evaluate:
            ws._on_character_card_clicked(self.characters[0])
            self.settle_allocation()
            self.assertEqual(evaluate.call_count, 1, "Allocation result must reuse the priced report")
            self.assertGreater(controller._allocation_generation, initial)
            generation = controller._allocation_generation
            result = controller._allocation_result
            ws._on_weapon_card_clicked(self.weapons[0])
            self.settle_allocation()
            self.assertEqual(controller._allocation_generation, generation)
            self.assertIs(controller._allocation_result, result)
            self.assertEqual(evaluate.call_count, 2)

    def test_rapid_toggles_settle_to_latest_membership(self):
        ws = self.workspace
        for asset in self.characters[:12]:
            ws._on_character_card_clicked(asset)
        for asset in self.characters[:6]:
            ws._on_character_card_clicked(asset)
        self.settle_allocation()
        controller = ws.rules_controller
        self.assertEqual(controller._allocation_characters, ws._draft_for_preset(ws.active_preset()).characters)
        self.assertEqual(controller._report["character_count"], 72)
        self.assertEqual(controller._report["tier_counts"]["0"], 13)
        self.assertTrue(controller._allocation_result["complete"])

    def test_account_refresh_invalidates_projection_and_matches_uncached_conversion(self):
        ws = self.workspace
        old = ws._inventory_draft
        self.characters[0]["metadata"]["character"]["constellation"] = 2
        self.characters.pop()
        self.weapons.pop()
        ws.refresh_account_data()
        self.settle_allocation()
        self.assertIsNot(ws._inventory_draft, old)
        preset = ws.active_preset()
        projected = ws._draft_for_preset(preset)
        uncached = deck_preset_to_draft_deck(preset, ws.character_assets, ws.weapon_assets)
        self.assertEqual(projected.characters, uncached.characters)
        self.assertEqual(projected.weapons, uncached.weapons)
        self.assertEqual(projected.characters[0].constellation, 2)
        self.assertIsNone(projected.characters[-1].level)
        self.assertFalse(ws.validation_report().ready)

    def test_structural_refresh_releases_old_card_handles(self):
        ws = self.workspace
        for _ in range(3):
            ws.refresh_view()
            self.settle()
        self.assertEqual(len(ws.character_grid.findChildren(PvpDeckGridItemHandle)), len(ws.character_cards_by_id))
        self.assertEqual(len(ws.weapon_grid.findChildren(PvpDeckGridItemHandle)), len(ws.weapon_cards_by_key))

    def test_saved_weapon_count_fallback_survives_inventory_cache(self):
        ws = self.workspace
        asset = self.weapons[0]
        asset["metadata"].pop("known_count")
        asset["metadata"]["weapon"].pop("known_count")
        ws.refresh_account_data()
        preset = ws.active_preset()
        preset = replace(preset, weapon_refs=(replace(preset.weapon_refs[0], count=3),))
        self.assertEqual(ws._draft_for_preset(preset).weapons,
                         deck_preset_to_draft_deck(preset, ws.character_assets, ws.weapon_assets).weapons)
        self.assertEqual(ws._draft_for_preset(preset).weapons[0].count, 3)

    def test_selection_with_rules_stays_within_browser_frame_budget(self):
        """Compare warmed paths on one host; operation-count tests enforce the mechanism.

        Browser markers alone do not include a rules panel. Both must fit the same
        60 Hz response frame; this is not a claim of equal whole-AppShell timings.
        """
        browser = CharacterWeaponWorkspace(db_path=self.root / "unused.db")
        self.addCleanup(browser.deleteLater)
        self.addCleanup(browser.close)
        browser._all_character_items = self.characters
        browser._all_weapon_items = self.weapons
        browser._initial_grid_built = True
        browser.reload_characters()
        browser.reload_weapons()
        cid = self.characters[0]["metadata"]["character"]["id"]

        def measure(callback):
            samples = []
            for _ in range(20):
                start = time.perf_counter()
                callback()
                samples.append((time.perf_counter() - start) * 1000)
                self.settle_allocation()
            return statistics.median(samples)

        browser_ms = measure(lambda: browser.set_character_selection_markers(
            {} if browser._character_selection_markers else {cid: RosterSelectionMarker(0, 0, 1, "#f8cd63")},
            affected_character_ids={cid},
        ))
        # Scale for an unusually slow host, retaining one-frame tolerance for rules.
        budget_ms = max(1000 / 60, browser_ms * 20)
        for callback, asset in ((self.workspace._on_character_card_clicked, self.characters[0]),
                                (self.workspace._on_weapon_card_clicked, self.weapons[0])):
            elapsed = measure(lambda: callback(asset))
            self.assertLess(elapsed, budget_ms, f"Selection {elapsed:.2f} ms; browser {browser_ms:.2f} ms")

    def test_full_weapon_pricing_inventory_keeps_selection_within_frame_budget(self):
        source, _roster = _screenshot_scale_source()
        system, _agents, engines = source
        for index, asset in enumerate(self.weapons):
            source_id = f"{25000 + index:024x}"
            engines.append({"_id": source_id, "enkaId": asset["metadata"]["weapon"]["id"]})
            system["costs"]["engines"].append({"engine": source_id, "costs": [3, 4, 5, 6, 7, 2]})
        ws = self.workspace
        ws._editing_preset = set_deck_preset_rules(ws.active_preset(), AbyssRuleset.from_source(*source))
        ws.refresh_view()
        self.panel.refresh()
        self.settle_allocation()
        self.assertEqual(len(ws.rules_ui_state()["weapon_rule_lines"]), 140)
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            ws._on_weapon_card_clicked(self.weapons[0])
            samples.append((time.perf_counter() - start) * 1000)
            self.settle_allocation()
        self.assertLess(statistics.median(samples), 1000 / 60)


if __name__ == "__main__":
    unittest.main()
