from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ui.app_shell import CharacterWeaponWorkspace
from ui.utils.pixel_icon_grid import build_pixel_icon_grid_layout
from ui.utils.ui_palette import UI_ACCENT_TEAM_1


_APP = QApplication.instance() or QApplication([])


def _weapon(icon: Path, index: int, *, owner: dict | None = None) -> dict:
    metadata = {
        "weapon": {
            "id": str(1000 + index),
            "source_key": f"fp-{index}",
            "name": f"Weapon {index:02d}",
            "rarity": 4,
            "level": 80,
        }
    }
    if owner is not None:
        metadata["owner_badges"] = [owner]
    return {
        "path": str(icon),
        "filename": f"Weapon-{index}.png",
        "tooltip": f"Weapon {index} details",
        "metadata": metadata,
    }


class WeaponGridStyleTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        self.icon = folder / "weapon.png"
        self.owner_icon = folder / "owner.png"
        weapon_pixmap = QPixmap(48, 48)
        weapon_pixmap.fill(QColor("#5f5870"))
        self.assertTrue(weapon_pixmap.save(str(self.icon)))
        owner_pixmap = QPixmap(44, 44)
        owner_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(owner_pixmap)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d99e80"))
        painter.drawEllipse(QRect(4, 2, 36, 40))
        painter.end()
        self.assertTrue(owner_pixmap.save(str(self.owner_icon)))
        self.owner = {
            "character_id": "10000050",
            "name": "Thoma",
            "side_icon_path": str(self.owner_icon),
        }
        self.workspace = CharacterWeaponWorkspace(db_path=folder / "unused.db")
        self.addCleanup(self.workspace.close)
        self.workspace.setFont(QFont("Segoe UI", 9))
        self.workspace._all_character_items = []
        self.workspace._all_weapon_items = [
            _weapon(self.icon, index, owner=self.owner if index == 0 else None)
            for index in range(24)
        ]
        self.workspace.resize(220, 500)
        self.workspace.show()
        _APP.processEvents()
        self.workspace.reload_weapons()
        _APP.processEvents()

    def test_equipped_card_matches_pvp_grid_spacing_and_compact_owner_geometry(self) -> None:
        grid = self.workspace.weapon_grid
        self.assertEqual(grid.item_count(), 24)
        self.assertEqual(grid._metrics.item_width, 48)
        self.assertEqual(grid.horizontalSpacing(), 6)
        self.assertEqual(grid.verticalSpacing(), 6)
        self.assertEqual(grid.contentsMargins().top(), 12)
        self.assertEqual(grid.contentsMargins().bottom(), 6)

        rects = [grid.item_physical_rect(key) for key in grid.item_ids()]
        first_row = [rect for rect in rects if rect.y() == rects[0].y()]
        self.assertGreater(len(first_row), 1)
        self.assertLess(len(first_row), len(rects))
        self.assertEqual(
            first_row[1].left() - first_row[0].right() - 1,
            grid._layout.gap_x,
        )
        next_row = next(rect for rect in rects if rect.x() == rects[0].x() and rect.y() > rects[0].y())
        self.assertEqual(next_row.top() - rects[0].bottom() - 1, grid._layout.gap_y)

        item = grid.item(grid.item_ids()[0])
        self.assertIsNotNone(item)
        self.assertIsNotNone(item.outline)
        self.assertEqual(item.outline.color, UI_ACCENT_TEAM_1)
        self.assertEqual((item.outline.width, item.outline.radius, item.outline.overhang), (2, 4, 0))
        self.assertEqual((item.outline.alpha, item.outline.fill_alpha), (255, 0))
        self.assertEqual(len(item.overlay_icons), 1)
        self.assertEqual(item.tooltip, "Weapon 0 details")
        self.assertEqual(item.badges, ())

        overlay = item.overlay_icons[0]
        self.assertEqual(overlay.icon_path, str(self.owner_icon))
        self.assertTrue(overlay.background_enabled)
        self.assertLess(overlay.size_ratio, 0.5)
        for dpr in (1.0, 1.25, 2.0):
            layout = build_pixel_icon_grid_layout(24, 220, grid._metrics, dpr=dpr)
            card = layout.rects[0]
            side = round(card.width() * overlay.size_ratio)
            right_shift = round(side * overlay.right_overhang_ratio)
            top_shift = round(side * overlay.top_overhang_ratio)
            portrait = QRect(
                card.right() - side + 1 + right_shift,
                card.top() - top_shift,
                side,
                side,
            )
            self.assertTrue(card.contains(portrait), f"owner portrait overhangs at DPR {dpr}")
            self.assertLess(portrait.width(), card.width() // 2 + 1)
            self.assertGreaterEqual(card.right() - portrait.right(), 2)
            self.assertGreaterEqual(portrait.top() - card.top(), 2)

    def test_equip_and_unequip_refresh_owner_state_for_full_and_incremental_grids(self) -> None:
        grid = self.workspace.weapon_grid
        key = grid.item_ids()[0]
        clicks: list[dict] = []
        self.workspace.weapon_clicked.connect(clicks.append)

        self.workspace._all_weapon_items[0] = _weapon(self.icon, 0)
        self.workspace.refresh_weapons_incremental()
        self.assertIsNone(grid.item(key).outline)
        self.assertEqual(grid.item(key).overlay_icons, ())

        with patch(
            "ui.app_shell.load_weapon_owner_badges_for_fingerprints",
            return_value={"fp-0": [self.owner]},
        ):
            self.assertTrue(self.workspace.refresh_weapon_owner_badges(["fp-0"]))
        equipped = grid.item(key)
        self.assertIsNotNone(equipped.outline)
        self.assertEqual(len(equipped.overlay_icons), 1)
        self.assertTrue(grid.item_property(key, "has_owner_badges"))
        self.assertEqual(equipped.tooltip, "Weapon 0 details")
        self.assertTrue(grid.click_item_for_test(key))
        self.assertEqual(clicks[-1]["metadata"]["owner_badges"], [self.owner])

        self.workspace.refresh_weapons_incremental()
        incremental = grid.item(key)
        self.assertEqual(incremental.outline, equipped.outline)
        self.assertEqual(incremental.overlay_icons, equipped.overlay_icons)

        with patch(
            "ui.app_shell.load_weapon_owner_badges_for_fingerprints",
            return_value={"fp-0": []},
        ):
            self.assertTrue(self.workspace.refresh_weapon_owner_badges(["fp-0"]))
        unequipped = grid.item(key)
        self.assertIsNone(unequipped.outline)
        self.assertEqual(unequipped.overlay_icons, ())
        self.assertFalse(grid.item_property(key, "has_owner_badges"))
        self.assertTrue(grid.click_item_for_test(key))
        self.assertNotIn("owner_badges", clicks[-1]["metadata"])


if __name__ == "__main__":
    unittest.main()
