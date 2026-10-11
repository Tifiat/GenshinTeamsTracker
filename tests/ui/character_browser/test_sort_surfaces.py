from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from hoyolab_export.traveler import traveler_variant_id
from ui.app_shell import CharacterWeaponWorkspace
from ui.artifact_browser.window import ArtifactBrowserWindow, BUILD_TARGET_UNIVERSAL_KEY
from ui.character_assets import character_matches_filters
from ui.character_browser.filter_bar import CharacterFilterBar
from ui.character_browser.sorting import DEFAULT_CHARACTER_SORT
from ui.main_window import App
from ui.pvp_browser.build_flow import PvpScopedCharacterWeaponWorkspace
from ui.pvp_browser.window import PvpDecksWorkspace, PvpDraftWorkspace
from ui.utils.icon_utils import UI_ICON_DIR


_APP = QApplication.instance() or QApplication([])
_MODES = (
    ("constellation", 1, ("102", "103", "101", "104", "105", "106")),
    ("constellation", 2, ("103", "101", "102", "104", "105", "106")),
    ("constellation", 0, ("102", "103", "104", "101", "105", "106")),
    ("level", 1, ("102", "103", "104", "101", "105", "106")),
    ("level", 2, ("103", "101", "102", "104", "105", "106")),
    ("level", 3, ("105", "102", "103", "104", "101", "106")),
    ("level", 0, ("102", "103", "104", "101", "105", "106")),
)


def _asset(portrait: Path, character_id: int, name: str, *, rarity: int = 5,
           level: int = 90, constellation: int = 0, standard: bool = False,
           element: str = "Pyro") -> dict:
    return {
        "path": portrait, "filename": f"{character_id}.png", "tooltip": name,
        "metadata": {"portrait_is_neutral": True, "character": {
            "id": str(character_id), "name": name, "canonical_name": name,
            "rarity": rarity, "level": level, "constellation": constellation,
            "element": element, "weapon_type_name": "sword",
            "is_standard_5_star": standard,
        }},
    }


class _LegacyFilterHarness(App):
    """Exercise the production left-panel builder without App's account startup."""

    def __init__(self) -> None:
        QWidget.__init__(self)
        self.main = QHBoxLayout(self)
        self._character_standard_filter = "all"
        self._weapon_type_filters = set()
        self._weapon_rarity_filters = set()
        self.rendered_ids = ()
        self.build_left_panel()

    def _reload_icon_grid(self, assets, *_args, **_kwargs) -> None:
        self.rendered_ids = tuple(asset["metadata"]["character"]["id"] for asset in assets)

    def reload_weapons(self) -> None:
        pass


class CharacterSortSurfacesTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.portrait = self.root / "portrait.png"
        pixmap = QPixmap(48, 48)
        pixmap.fill(QColor("#736584"))
        self.assertTrue(pixmap.save(str(self.portrait)))
        self.roster = [
            _asset(self.portrait, 101, "LimitedLow", level=20, constellation=1),
            _asset(self.portrait, 102, "StandardHigh", level=90, constellation=6, standard=True),
            _asset(self.portrait, 103, "LimitedHigh", level=80, constellation=4),
            _asset(self.portrait, 104, "StandardLow", level=40, standard=True),
            _asset(self.portrait, 105, "FourHigh", rarity=4, level=95, constellation=6),
            _asset(self.portrait, 106, "FourLow", rarity=4, level=10, constellation=3),
        ]

    def test_normal_roster_displays_every_sort_mode_and_filters_still_intersect(self) -> None:
        workspace = CharacterWeaponWorkspace(db_path=self.root / "unused.db")
        self.addCleanup(workspace.close)
        workspace._all_character_items = self.roster
        workspace._all_weapon_items = []
        workspace.reload_characters()
        for criterion, mode, expected in _MODES:
            with self.subTest(criterion=criterion, mode=mode):
                workspace.character_filter_bar.sort_controls.buttons[criterion].click()
                self.assertEqual(workspace.char_grid.item_ids(), expected)
        filters = workspace.character_filter_bar
        filters.rarity_filters.add(4)
        filters.standard_button.click()
        self.assertEqual(workspace.char_grid.item_ids(), ())
        filters.sort_controls.level_button.click()
        self.assertEqual(workspace.char_grid.item_ids(), ())
        self.assertEqual(filters.rarity_filters, {4})
        filters.reset()
        self.assertEqual(workspace.char_grid.item_ids(), _MODES[-1][2])

    def test_pvp_deck_uses_the_same_controls_and_order_without_mutating_members(self) -> None:
        workspace = PvpDecksWorkspace(
            db_path=self.root / "unused.db", deck_dir=self.root / "decks",
            character_assets_provider=lambda: self.roster,
            weapon_assets_provider=lambda: [], abyss_period_provider=lambda: None,
        )
        self.addCleanup(workspace.close)
        self.assertTrue(workspace.create_deck("Sort fixture"))
        original_members = workspace.active_preset().character_ids
        for criterion, mode, expected in _MODES:
            with self.subTest(criterion=criterion, mode=mode):
                workspace.character_filter_bar.sort_controls.buttons[criterion].click()
                self.assertEqual(workspace.character_grid.item_ids(), expected)
                self.assertEqual(workspace.active_preset().character_ids, original_members)
        self.assertFalse((self.root / "unused.db").exists())

    def test_artifact_targets_reorder_cached_rows_and_reset_sort_only(self) -> None:
        browser = ArtifactBrowserWindow(
            embedded=True, db_path=self.root / "unused.db",
            character_asset_items=self.roster, read_only_source=True,
        )
        self.addCleanup(browser.close)
        kept_key = "character:101"
        browser.selected_build_target_keys = {kept_key}
        browser.refresh_build_target_list()
        buttons_before = dict(browser.build_target_buttons_by_key)
        parents_before = {key: button.parent() for key, button in buttons_before.items()}
        for criterion, mode, expected in _MODES:
            with self.subTest(criterion=criterion, mode=mode):
                browser.build_target_sort_controls.buttons[criterion].click()
                expected_keys = [BUILD_TARGET_UNIVERSAL_KEY] + [f"character:{cid}" for cid in expected]
                self.assertEqual(browser._build_target_button_order, expected_keys)
                self.assertEqual(
                    [browser.build_target_list_layout.itemAt(i).widget() for i in range(len(expected_keys))],
                    [buttons_before[key] for key in expected_keys],
                )
                self.assertEqual(browser.selected_build_target_keys, {kept_key})
                self.assertTrue(buttons_before[kept_key].isChecked())
                for key, button in buttons_before.items():
                    self.assertIs(browser.build_target_buttons_by_key[key], button)
                    self.assertIs(button.parent(), parents_before[key])
        browser.build_target_sort_controls.level_button.click()
        self.assertTrue(browser.build_target_filter_reset_button.isEnabled())
        browser.build_target_rarity_filters.add(4)
        browser.build_target_standard_filter = "only"
        browser.refresh_build_target_list()
        self.assertEqual(browser._visible_build_target_keys(), {BUILD_TARGET_UNIVERSAL_KEY, kept_key})
        browser.build_target_sort_controls.constellation_button.click()
        self.assertEqual(browser._visible_build_target_keys(), {BUILD_TARGET_UNIVERSAL_KEY, kept_key})
        browser.build_target_filter_reset_button.click()
        self.assertEqual(browser.build_target_sort_controls.state, DEFAULT_CHARACTER_SORT)
        self.assertEqual(browser.selected_build_target_keys, {kept_key})
        self.assertFalse(browser.build_target_filter_reset_button.isEnabled())
        removed_key = "character:104"
        browser.build_target_items_by_key.pop(removed_key)
        browser.refresh_build_target_list()
        self.assertIs(browser.build_target_buttons_by_key[removed_key], buttons_before[removed_key])
        self.assertTrue(buttons_before[removed_key].isHidden())
        self.assertNotIn(removed_key, browser._visible_build_target_keys())
        self.assertFalse((self.root / "unused.db").exists())

    def test_draft_pool_sort_preserves_legal_actions_ownership_and_board(self) -> None:
        workspace = PvpDraftWorkspace()
        self.addCleanup(workspace.close)
        workspace._character_assets_by_id = {asset["metadata"]["character"]["id"]: asset for asset in self.roster}
        board = {"unified_pool": {"entries": [
            {"character_id": str(cid), "name": f"Character {cid}", "zone": "pool",
             "owner_seats": ["player_2" if cid == 105 else "player_1"],
             "is_current_legal_target": cid != 104,
             "action": {"action_type": "pick_character", "character_id": str(cid)}}
            for cid in range(101, 107)
        ]}}
        before = deepcopy(board)
        workspace._build_unified_pool(board, draft_complete=False)
        for criterion, mode, expected in _MODES:
            with self.subTest(criterion=criterion, mode=mode):
                workspace.character_filter_bar.sort_controls.buttons[criterion].click()
                workspace._build_unified_pool(board, draft_complete=False)
                self.assertEqual(workspace.pool_grid.item_ids(), expected)
                self.assertEqual(set(workspace.legal_character_ids), {"101", "102", "103", "105", "106"})
                self.assertFalse(workspace.pool_grid.item("104").enabled)
                self.assertEqual(workspace.pool_grid.item("105").properties["ownerP2"], True)
                self.assertEqual(workspace._draft_actions_by_character_id["101"], before["unified_pool"]["entries"][0]["action"])
                self.assertEqual(board, before)
        workspace._pool_scope = "player_1"
        workspace.character_filter_bar.sort_controls.level_button.click()
        workspace._build_unified_pool(board, draft_complete=False)
        self.assertNotIn("105", workspace.pool_grid.item_ids())
        self.assertEqual(board, before)

    def test_traveler_order_uses_displayed_variant_constellation_and_level(self) -> None:
        source = 10000007
        pyro = traveler_variant_id(source, "Pyro")
        workspace = CharacterWeaponWorkspace(db_path=self.root / "unused.db")
        self.addCleanup(workspace.close)
        workspace._all_character_items = [
            _asset(self.portrait, source, "Traveler", constellation=0, level=40, element="Cryo", standard=True),
            _asset(self.portrait, pyro, "Traveler", constellation=6, level=90, standard=True),
            _asset(self.portrait, 101, "Ordinary", constellation=3, level=60),
        ]
        workspace._all_weapon_items = []
        workspace.character_filter_bar.sort_controls.constellation_button.click()
        self.assertEqual(workspace.char_grid.item_ids(), ("101", str(source)))
        workspace._select_traveler_variant(str(pyro))
        self.assertEqual(workspace.char_grid.item_ids(), (str(pyro), "101"))
        self.assertEqual(workspace.char_grid.item_count(), 2)
        workspace.character_filter_bar.sort_controls.level_button.click()
        self.assertEqual(workspace.char_grid.item_ids(), (str(pyro), "101"))
        workspace._select_traveler_variant(str(source))
        self.assertEqual(workspace.char_grid.item_ids(), ("101", str(source)))

    def test_draft_shared_characters_use_selected_or_active_player_values(self) -> None:
        workspace = PvpDraftWorkspace()
        self.addCleanup(workspace.close)
        assets = [
            _asset(self.portrait, 101, "SharedA", level=90, constellation=6),
            _asset(self.portrait, 102, "SharedB", level=20, constellation=0),
            _asset(self.portrait, 103, "OpponentOnly", level=60, constellation=5),
        ]
        workspace._character_assets_by_id = {a["metadata"]["character"]["id"]: a for a in assets}
        board = {"current_requirement": {"active_seat": "player_1"}, "unified_pool": {"entries": [
            {"character_id": "101", "zone": "pool", "owner_seats": ["player_1", "player_2"],
             "base_seat": "player_1", "per_seat": {"player_1": {"level": 20, "constellation": 0},
                                                    "player_2": {"level": 90, "constellation": 6}}},
            {"character_id": "102", "zone": "pool", "owner_seats": ["player_1", "player_2"],
             "base_seat": "player_1", "per_seat": {"player_1": {"level": 80, "constellation": 4},
                                                    "player_2": {"level": 40, "constellation": 1}}},
            {"character_id": "103", "zone": "pool", "owner_seats": ["player_2"],
             "base_seat": "player_2", "per_seat": {"player_2": {"level": 60, "constellation": 5}}},
        ]}}
        original_assets = deepcopy(assets)
        workspace._build_unified_pool(board, draft_complete=False)
        workspace.character_filter_bar.sort_controls.constellation_button.click()
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("103", "102", "101"))
        for _ in range(3):
            workspace.character_filter_bar.sort_controls.level_button.click()
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("102", "103", "101"))
        workspace.character_filter_bar.sort_controls.constellation_button.click()
        board["current_requirement"]["active_seat"] = "player_2"
        before = deepcopy(board)
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("101", "103", "102"))
        workspace._pool_scope = "player_1"
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("102", "101"))
        workspace._pool_scope = "all"
        for _ in range(3):
            workspace.character_filter_bar.sort_controls.level_button.click()
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("101", "103", "102"))
        workspace._pool_scope = "player_1"
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("102", "101"))
        self.assertEqual(board, before)
        self.assertEqual(assets, original_assets)
        board["unified_pool"]["entries"][1]["per_seat"]["player_1"]["constellation"] = None
        workspace.character_filter_bar.sort_controls.constellation_button.click()
        self.assertEqual(tuple(e["character_id"] for e in workspace._filtered_draft_pool_entries(board)), ("101", "102"))

    def test_scoped_pvp_source_keeps_only_allowed_ids_with_shared_sorting(self) -> None:
        allowed = {"101", "102", "105"}
        workspace = PvpScopedCharacterWeaponWorkspace(
            seat="player_1", db_path=self.root / "unused.db",
            character_assets=self.roster, allowed_character_ids=allowed,
        )
        self.addCleanup(workspace.close)
        workspace.character_filter_bar.sort_controls.level_button.click()
        workspace.character_filter_bar.sort_controls.level_button.click()
        workspace.character_filter_bar.sort_controls.level_button.click()
        self.assertEqual(workspace.char_grid.item_ids(), ("105", "102", "101"))
        self.assertEqual(set(workspace.char_grid.item_ids()), allowed)
        self.assertFalse((self.root / "unused.db").exists())

    def test_legacy_left_panel_uses_shared_sorting_without_account_startup(self) -> None:
        workspace = _LegacyFilterHarness()
        self.addCleanup(workspace.deleteLater)
        self.assertIsInstance(workspace.character_filter_bar, CharacterFilterBar)
        with patch("ui.main_window.load_account_character_asset_items", return_value=self.roster):
            for criterion, mode, expected in _MODES:
                with self.subTest(criterion=criterion, mode=mode):
                    workspace.character_filter_bar.sort_controls.buttons[criterion].click()
                    _APP.processEvents()
                    self.assertEqual(workspace.rendered_ids, expected)

    def test_shipped_sort_icons_render_and_exclusive_reset_emits_once(self) -> None:
        bar = CharacterFilterBar()
        self.addCleanup(bar.close)
        changes = []
        bar.filters_changed.connect(lambda: changes.append(bar.sort_controls.state))
        for name in ("constellation", "level"):
            self.assertTrue((UI_ICON_DIR / f"character-{name}.svg").is_file())
            image = bar.sort_controls.buttons[name].icon().pixmap(24, 24).toImage()
            self.assertFalse(image.isNull())
            self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())))
        bar.sort_controls.constellation_button.click()
        bar.sort_controls.level_button.click()
        self.assertFalse(bar.sort_controls.constellation_button.isChecked())
        self.assertTrue(bar.sort_controls.level_button.isChecked())
        bar.reset()
        self.assertEqual(len(changes), 3)
        self.assertEqual(bar.sort_controls.state, DEFAULT_CHARACTER_SORT)
        self.assertTrue(all(button.property("sortMode") == 0 for button in bar.sort_controls.buttons.values()))

    def test_existing_filter_families_use_union_inside_and_intersection_between(self) -> None:
        roster = deepcopy(self.roster)
        for asset, element, weapon, traits, region in zip(
            roster,
            ("Pyro", "Hydro", "Dendro", "Cryo", "Pyro", "Hydro"),
            ("sword", "sword", "catalyst", "bow", "bow", "bow"),
            ([], ["hexerei"], ["moonsign"], [], ["moonsign"], ["hexerei"]),
            ("mond", "mond", "sumeru", "liyue", "liyue", "mond"),
        ):
            asset["metadata"]["character"].update(
                element=element, weapon_type_name=weapon, traits=traits, region_key=region,
            )
        elements, weapons, rarities, traits, regions = {"Pyro", "Hydro"}, set(), {4, 5}, set(), set()

        def visible(standard="all"):
            return tuple(asset["metadata"]["character"]["id"] for asset in roster
                         if character_matches_filters(asset, elements, weapons, rarities, regions, traits, standard))

        self.assertEqual(visible(), ("101", "102", "105", "106"))
        weapons.add("bow")
        self.assertEqual(visible(), ("105", "106"))
        weapons.add("sword")
        traits.update(("hexerei", "moonsign"))
        self.assertEqual(visible(), ("102", "105", "106"))
        regions.add("liyue")
        self.assertEqual(visible(), ("105",))
        regions.add("mond")
        self.assertEqual(visible(), ("102", "105", "106"))
        rarities.discard(5)
        self.assertEqual(visible("only"), ())
        self.assertEqual(visible("exclude"), ("105", "106"))
        self.assertEqual(rarities, {4})
        self.assertEqual(weapons, {"sword", "bow"})


if __name__ == "__main__":
    unittest.main()
