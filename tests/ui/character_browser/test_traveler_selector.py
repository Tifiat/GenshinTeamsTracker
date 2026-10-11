from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_variant_id
from ui.app_shell import AppShellController, CharacterWeaponWorkspace, RosterSelectionMarker
from ui.character_browser.icon_grid_adapter import build_asset_grid_items
from ui.character_browser.traveler_selector import collapse_traveler_assets

_APP = QApplication.instance() or QApplication([])
SOURCE = 10000007


def _roster(portrait: Path) -> list[dict]:
    assets = []
    for index, element in enumerate(TRAVELER_ELEMENTS):
        character_id = SOURCE if element == "Cryo" else traveler_variant_id(SOURCE, element)
        assets.append({
            "path": portrait, "filename": portrait.name, "tooltip": f"Traveler {element}",
            "metadata": {"portrait_is_neutral": True, "is_standard_5_star": True,
                         "character": {"id": str(character_id), "name": "Traveler", "element": element,
                                       "rarity": 5, "weapon_type": 1, "constellation": index}},
        })
    assets.append({"path": portrait, "filename": portrait.name, "tooltip": "Ordinary hero",
                   "metadata": {"portrait_is_neutral": True, "character": {
                       "id": "10000050", "name": "Thoma", "element": "Pyro", "rarity": 4, "constellation": 2}}})
    return assets


class TravelerSelectorTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.portrait = Path(temporary.name) / "portrait.png"
        Image.new("RGBA", (64, 64), "#7a6770").save(self.portrait)
        self.workspace = CharacterWeaponWorkspace(db_path=Path(temporary.name) / "unused.db")
        self.addCleanup(self.workspace.close)
        self.workspace._all_character_items = _roster(self.portrait)
        self.workspace._all_weapon_items = []
        self.workspace.resize(600, 600)
        self.workspace.show()
        _APP.processEvents()
        self.workspace.reload_characters()
        self.clicked: list[dict] = []
        self.workspace.character_clicked.connect(self.clicked.append)

    def test_one_card_switches_element_without_changing_team_until_card_click(self) -> None:
        grid = self.workspace.char_grid
        self.assertEqual(grid.item_count(), 2)
        self.assertIn(str(SOURCE), grid.item_ids())
        button = grid._variant_buttons[str(SOURCE)]
        rect = grid.item_logical_rect(str(SOURCE))
        self.assertLess(button.geometry().center().x(), rect.center().x())
        self.assertGreater(button.geometry().center().y(), rect.center().y())
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        _APP.processEvents()
        popup = grid._variant_popup
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.grid.item_count(), 6)
        self.assertEqual(popup.grid._layout.rows, 1)
        self.assertNotIn(str(SOURCE), popup.grid.item_ids())
        chosen = str(traveler_variant_id(SOURCE, "Pyro"))
        QTest.mouseClick(popup.grid, Qt.MouseButton.LeftButton, pos=popup.grid.item_logical_rect(chosen).center().toPoint())
        _APP.processEvents()
        self.assertFalse(popup.isVisible())
        self.assertEqual(self.clicked, [])
        self.assertIn(chosen, grid.item_ids())
        self.assertNotIn(str(SOURCE), grid.item_ids())
        self.assertEqual([badge.text for badge in grid.item(chosen).badges], ["C5"])
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=grid.item_logical_rect(chosen).center().toPoint())
        self.assertEqual(len(self.clicked), 1)
        self.assertEqual(self.clicked[0]["metadata"]["character"]["id"], chosen)
        self.assertEqual(self.clicked[0]["metadata"]["character"]["element"], "Pyro")
        controller = AppShellController.empty(equipment_db_path=self.workspace.db_path)
        placed = controller.add_or_replace_character_fast(self.clicked[0])
        self.assertTrue(placed.added)
        self.assertEqual(placed.character_id, chosen)
        self.assertIn(chosen, controller.roster_selection_markers())
        removed = controller.add_or_replace_character_fast(self.clicked[0])
        self.assertTrue(removed.removed)
        self.assertNotIn(chosen, controller.roster_selection_markers())

    def test_filter_restricts_popup_and_restores_session_choice(self) -> None:
        chosen = str(traveler_variant_id(SOURCE, "Pyro"))
        self.workspace._select_traveler_variant(chosen)
        self.workspace._character_element_filters = {"Hydro", "Geo"}
        self.workspace.reload_characters()
        shown = str(traveler_variant_id(SOURCE, "Geo"))
        grid = self.workspace.char_grid
        self.assertEqual(grid.item_ids(), (shown,))
        self.assertTrue(grid.open_variants(shown))
        self.assertEqual(grid._variant_popup.grid.item_ids(), (str(traveler_variant_id(SOURCE, "Hydro")),))
        self.workspace._character_element_filters = {"Hydro"}
        self.workspace.reload_characters()
        self.assertEqual(grid.item_count(), 1)
        self.assertEqual(grid._variant_buttons, {})
        self.assertFalse(grid._variant_popup.isVisible())
        self.workspace._character_element_filters.clear()
        self.workspace.reload_characters()
        self.assertIn(chosen, grid.item_ids())
        self.workspace._character_standard_filter = "exclude"
        self.workspace.reload_characters()
        self.assertEqual(grid.item_ids(), ("10000050",))
        self.assertEqual(grid._variant_buttons, {})

    def test_marker_updates_include_hidden_variants_without_roster_reload(self) -> None:
        chosen = str(traveler_variant_id(SOURCE, "Pyro"))
        marker = RosterSelectionMarker(team_index=0, slot_index=1, color="#3ed47b", slot_number=2)
        with patch.object(self.workspace, "reload_characters") as reload:
            self.workspace.set_character_selection_markers({chosen: marker}, affected_character_ids={chosen})
        reload.assert_not_called()
        grid = self.workspace.char_grid
        grid.open_variants(str(SOURCE))
        self.assertEqual(grid._variant_popup.grid.item(chosen).outline.badge_text, "2")
        self.workspace.set_character_selection_markers({}, affected_character_ids={chosen})
        self.assertIsNone(grid._variant_popup.grid.item(chosen).outline)

    def test_escape_and_scroll_dismiss_without_selection(self) -> None:
        grid = self.workspace.char_grid
        grid.open_variants(str(SOURCE))
        popup = grid._variant_popup
        QTest.keyClick(popup, Qt.Key.Key_Escape)
        _APP.processEvents()
        self.assertFalse(popup.isVisible())
        self.assertIn(str(SOURCE), grid.item_ids())
        self.assertEqual(self.clicked, [])
        grid.open_variants(str(SOURCE))
        self.workspace.char_area.verticalScrollBar().valueChanged.emit(1)
        self.assertFalse(popup.isVisible())

    def test_selected_traveler_slot_badge_stays_visible_beside_the_chevron(self) -> None:
        grid = self.workspace.char_grid
        self.workspace.set_character_selection_markers({str(SOURCE): RosterSelectionMarker(
            team_index=0, slot_index=1, slot_number=2, color="#3ed47b",
        )})
        outline = grid.item(str(SOURCE)).outline
        self.assertEqual(outline.badge_position, "bottom_right")
        image = grid.grab().toImage()
        rect = grid.item_logical_rect(str(SOURCE)).toAlignedRect()
        dpr = image.devicePixelRatio()
        # The inner lower-right region must contain the green slot badge,
        # while the selector continues occupying the lower-left corner.
        green = 0
        for y in range(rect.bottom() - 18, rect.bottom() - 6):
            for x in range(rect.right() - 22, rect.right() - 6):
                color = image.pixelColor(round(x * dpr), round(y * dpr))
                green += color.green() > 140 and color.red() < 90 and color.blue() < 160
        self.assertGreater(green, 40)
        self.assertLess(grid._variant_buttons[str(SOURCE)].geometry().right(), rect.center().x())

    def test_horizontal_popup_and_button_hit_zone_at_fractional_dpr(self) -> None:
        grid = self.workspace.char_grid
        for dpr in (0.71, 1.25, 1.5):
            with self.subTest(dpr=dpr), patch.object(grid, "devicePixelRatioF", return_value=dpr), patch.object(
                grid._variant_popup.grid, "devicePixelRatioF", return_value=dpr,
            ):
                grid._refresh_layout()
                button = grid._variant_buttons[str(SOURCE)]
                self.assertTrue(grid.item_logical_rect(str(SOURCE)).contains(button.geometry().center()))
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                _APP.processEvents()
                popup = grid._variant_popup
                self.assertEqual(popup.grid._layout.rows, 1)
                self.assertEqual(popup.grid.item_count(), 6)
                self.assertTrue(popup.screen().availableGeometry().contains(popup.geometry()))
                popup.hide()

    def test_shared_builder_keeps_all_variants_for_pvp(self) -> None:
        result = build_asset_grid_items(_roster(self.portrait)[:-1], key_for_asset=lambda asset: asset["metadata"]["character"]["id"])
        self.assertEqual(len(result.items), 7)
        self.assertEqual(len({item.item_id for item in result.items}), 7)

    def test_unknown_element_remains_visible_and_genders_keep_separate_groups(self) -> None:
        assets = _roster(self.portrait)
        invalid = {"metadata": {"character": {"id": "10000005", "element": "Unknown"}}}
        assets.append(invalid)
        assets.append({"metadata": {"character": {"id": str(traveler_variant_id(10000005, "Geo")), "element": "Geo"}}})
        result = collapse_traveler_assets(assets, {})
        self.assertEqual(len(result.assets), 4)
        self.assertIn(invalid, result.assets)
        self.assertEqual(len(result.groups), 2)


if __name__ == "__main__":
    unittest.main()
