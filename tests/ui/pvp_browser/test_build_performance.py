from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from run_workspace.pvp.profile_package import LocalPvpProfileProvider
from ui.utils import pixel_icon_grid
from ui.pvp_browser.build_flow import PvpSeatBuildContext, _asset_weapon_keys
from ui.utils.pixel_icon_grid import (
    PixelIconGrid, PixelIconGridItem, PixelIconGridMetrics, PixelIconGridOverlayIcon,
)
from tests.ui.pvp_browser.test_pvp_browser import (
    _character_asset,
    _create_test_asset_images,
    _seed_pvp_build_db,
    _weapon_asset,
)


class PvpBuildPerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _context(self, directory: str) -> tuple[PvpSeatBuildContext, list[dict], list[dict]]:
        portrait, weapon_icon = _create_test_asset_images(directory)
        characters = [
            _character_asset(str(20000100 + index), f"Sword {index}",
                             weapon_type=1, weapon_type_name="Sword", image_path=portrait)
            for index in range(2)
        ]
        weapons = [
            _weapon_asset("11401", "First", weapon_type=1, weapon_type_name="Sword",
                          known_count=2, image_path=weapon_icon),
            _weapon_asset("11402", "Second", weapon_type=1, weapon_type_name="Sword",
                          known_count=2, image_path=weapon_icon),
        ]
        db_path = Path(directory) / "build.sqlite"
        _seed_pvp_build_db(db_path, characters=characters, weapons=weapons)
        context = PvpSeatBuildContext(
            seat="player_1",
            provider=LocalPvpProfileProvider(source_db_path=db_path),
            picked_character_ids=tuple(asset["metadata"]["character"]["id"] for asset in characters),
            allowed_weapon_keys=tuple(key for asset in weapons for key in _asset_weapon_keys(asset)),
            character_assets=tuple(characters),
            weapon_assets=tuple(weapons),
        )
        return context, characters, weapons

    def test_rapid_slot_and_weapon_changes_reuse_grid_images_and_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context, characters, weapons = self._context(directory)
            source = context.source_workspace
            self.assertEqual(source.weapon_grid.item_count(), 2)
            self.assertTrue(context.add_or_replace_character(characters[0]))
            context._weapon_filter_timer.stop()
            context._apply_deferred_weapon_filter()
            original_icons = dict(source.weapon_grid._prepared_pixmaps)
            with patch.object(source, "reload_weapons", wraps=source.reload_weapons) as reloads, \
                    patch("ui.utils.pixel_icon_grid.load_hidpi_pixmap",
                          wraps=pixel_icon_grid.load_hidpi_pixmap) as image_loads:
                self.assertTrue(context.assign_weapon_to_selected_slot(weapons[0]))
                context.toggle_slot_selection(0, 1)
                self.assertTrue(context.add_or_replace_character(characters[1]))
                self.assertTrue(context.assign_weapon_to_selected_slot(weapons[0]))
                shared = next(asset for asset in source._weapon_grid_assets_by_id.values()
                              if asset["metadata"]["weapon"]["id"] == "11401")
                self.assertEqual(len(shared["metadata"]["owner_badges"]), 2)
                self.assertEqual(shared["metadata"]["extra_owner_count"], 1)
                self.assertTrue(context.assign_weapon_to_selected_slot(weapons[1]))
                context.toggle_slot_selection(0, 0)
                self.assertTrue(context.assign_weapon_to_selected_slot(weapons[0]))
                self.assertEqual(reloads.call_count, 0)
                self.assertTrue(all(call.kwargs.get("surface", "").endswith("_overlay")
                                    for call in image_loads.call_args_list))
            self.assertEqual(source.weapon_grid.item_ids(), tuple(original_icons))
            for item_id, icon in original_icons.items():
                self.assertIs(source.weapon_grid._prepared_pixmaps[item_id], icon)
            first = next(asset for asset in source._weapon_grid_assets_by_id.values()
                         if asset["metadata"]["weapon"]["id"] == "11401")
            second = next(asset for asset in source._weapon_grid_assets_by_id.values()
                          if asset["metadata"]["weapon"]["id"] == "11402")
            self.assertEqual(first["metadata"].get("owner_badges"), None)
            self.assertEqual(second["metadata"]["owner_badges"][0]["character_id"],
                             characters[1]["metadata"]["character"]["id"])
            self.assertEqual(second["metadata"]["extra_owner_count"], 0)
            second_id = next(item_id for item_id, asset in source._weapon_grid_assets_by_id.items()
                             if asset["metadata"]["weapon"]["id"] == "11402")
            clicked = []
            source.weapon_clicked.connect(clicked.append)
            self.assertTrue(source.weapon_grid.click_item_for_test(second_id))
            self.assertEqual(clicked[-1]["metadata"]["owner_badges"],
                             second["metadata"]["owner_badges"])

    def test_filter_change_rebuilds_once_and_cancels_pending_filter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context, characters, weapons = self._context(directory)
            source = context.source_workspace
            self.assertTrue(context.add_or_replace_character(characters[0]))
            context.schedule_weapon_filter_sync()
            self.assertTrue(context._weapon_filter_timer.isActive())
            with patch.object(source, "reload_weapons", wraps=source.reload_weapons) as reloads:
                self.assertTrue(context.assign_weapon_to_selected_slot(weapons[0]))
                self.assertFalse(context._weapon_filter_timer.isActive())
                self.assertEqual(reloads.call_count, 1)

    def test_incremental_grid_retains_unaffected_pixmaps_and_invalidates_changed_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_path = str(Path(directory) / "first.png")
            second_path = str(Path(directory) / "second.png")
            for path, color in ((first_path, "red"), (second_path, "blue")):
                image = QPixmap(8, 8)
                image.fill(QColor(color))
                self.assertTrue(image.save(path))
            grid = PixelIconGrid()
            base = (PixelIconGridItem("a", first_path), PixelIconGridItem("b", second_path))
            grid.set_items(base)
            first_icon = grid._prepared_pixmaps["a"]
            second_icon = grid._prepared_pixmaps["b"]
            with patch("ui.utils.pixel_icon_grid._path_signature",
                       side_effect=AssertionError("Unchanged images were restatted")):
                grid.set_items_incremental((PixelIconGridItem("a", first_path, tooltip="fresh"),
                                            base[1]))
            overlay = PixelIconGridOverlayIcon(icon_path=second_path)
            grid.set_items_incremental((base[0], PixelIconGridItem("b", second_path,
                                                                    overlay_icons=(overlay,))))
            self.assertIs(grid._prepared_pixmaps["a"], first_icon)
            self.assertIs(grid._prepared_pixmaps["b"], second_icon)
            self.assertIn(("b", 0), grid._prepared_overlay_pixmaps)
            grid.set_items_incremental(base)
            self.assertNotIn(("b", 0), grid._prepared_overlay_pixmaps)
            grid.set_items_incremental((base[0], PixelIconGridItem("b", first_path)))
            self.assertNotEqual(grid._prepared_pixmaps["b"].toImage().pixelColor(0, 0),
                                second_icon.toImage().pixelColor(0, 0))
            retained_icon = grid._prepared_pixmaps["a"]
            with patch("ui.utils.pixel_icon_grid._path_signature",
                       side_effect=AssertionError("A reorder restatted unchanged images")):
                current = grid.item("b")
                grid.set_items_incremental((current, base[0]))
                grid.set_items_incremental((base[0],))
            self.assertIs(grid._prepared_pixmaps["a"], retained_icon)
            grid.set_items_incremental((base[1],))
            self.assertEqual(grid.item_ids(), ("b",))
            self.assertNotIn("a", grid._prepared_pixmaps)
            before_resize = grid._prepared_pixmaps["b"]
            grid.set_metrics(PixelIconGridMetrics(item_width=72))
            self.assertIsNot(grid._prepared_pixmaps["b"], before_resize)
            resized = grid._prepared_pixmaps["b"]
            grid.set_items_incremental((PixelIconGridItem("b", second_path,
                                                          tooltip="resized"),))
            self.assertIs(grid._prepared_pixmaps["b"], resized)

    def test_incremental_dpr_and_explicit_same_path_image_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "icon.png"
            image = QPixmap(8, 8)
            image.fill(QColor("red"))
            self.assertTrue(image.save(str(path)))
            grid = PixelIconGrid()
            items = (PixelIconGridItem("a", str(path)),)
            grid.set_items(items)
            old_icon = grid._prepared_pixmaps["a"]
            with patch.object(grid, "devicePixelRatioF", return_value=2.0):
                grid.set_items_incremental(items)
                self.assertEqual(grid._prepared_pixmaps["a"].devicePixelRatio(), 2.0)
                self.assertIsNot(grid._prepared_pixmaps["a"], old_icon)
            previous_stamp = path.stat().st_mtime_ns
            image.fill(QColor("blue"))
            self.assertTrue(image.save(str(path)))
            os.utime(path, ns=(previous_stamp + 1_000_000_000, previous_stamp + 1_000_000_000))
            grid.set_items(items)
            self.assertEqual(grid._prepared_pixmaps["a"].toImage().pixelColor(0, 0), QColor("blue"))


if __name__ == "__main__":
    unittest.main()
