from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QLabel

from run_workspace.right_panel_prototype_view_model import (
    RightPanelBonusSourceDisplayItem,
    RightPanelBuildMiniSetViewModel,
    build_right_panel_prototype_view_model,
)
from run_workspace.team_builder import create_empty_team_builder_state
from ui.right_panel_prototype import (
    BONUS_MEMBER_ICON_SIZE,
    _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE,
    _BONUS_SOURCE_ICON_PIXMAP_CACHE,
    BonusSourceChipWidget,
    BonusSourceStripWidget,
    RightPanelPrototypeWidget,
    _bonus_member_side_icon_pixmap,
    _bonus_source_tooltip_html,
    _bonus_source_icon_pixmap,
    _build_mini_set_stack_pixmap,
)


class RightPanelBonusIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_bonus_source_icon_trims_transparent_padding_and_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon_path = Path(tmp) / "small_visible_icon.png"
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.fillRect(QRect(14, 14, 4, 4), QColor(255, 220, 80, 255))
            painter.end()
            self.assertTrue(image.save(str(icon_path), "PNG"))

            _BONUS_SOURCE_ICON_PIXMAP_CACHE.clear()
            pixmap = _bonus_source_icon_pixmap(str(icon_path), QSize(20, 20))
            cache_size = len(_BONUS_SOURCE_ICON_PIXMAP_CACHE)
            cached = _bonus_source_icon_pixmap(str(icon_path), QSize(20, 20))

            self.assertIsNotNone(pixmap)
            self.assertIsNotNone(cached)
            self.assertEqual(cache_size, 1)
            self.assertEqual(len(_BONUS_SOURCE_ICON_PIXMAP_CACHE), cache_size)
            self.assertEqual(pixmap.size(), QSize(20, 20))
            self.assertGreater(pixmap.toImage().pixelColor(2, 2).alpha(), 0)

    def test_bonus_tooltip_has_single_effects_section_without_duplicate_body_lines(self) -> None:
        item = RightPanelBonusSourceDisplayItem(
            source_kind="elemental_resonance",
            source_id="pyro_resonance",
            label="Res",
            short_effects=("ATK +25%",),
            tooltip_title="Pyro Resonance",
            tooltip_body="ATK +25%\nDirect display-stat elemental resonance bonus.",
            applied=True,
        )

        with patch("ui.right_panel_prototype.tr", return_value="Effects"):
            html = _bonus_source_tooltip_html(item)

        self.assertEqual(html.count("ATK +25%"), 1)
        self.assertIn("<b>Effects:</b>", html)
        self.assertIn("Direct display-stat elemental resonance bonus.", html)

    def test_bonus_tooltip_uses_full_effect_label_and_cleans_description_html(self) -> None:
        item = RightPanelBonusSourceDisplayItem(
            source_kind="artifact_set_static",
            source_id="DeepwoodMemories:2",
            label="2p",
            short_effects=("Dendro +15%",),
            tooltip_effects=("Бонус Дендро урона +15%",),
            tooltip_title="Deepwood Memories 2p",
            tooltip_body="<p>Эффекты:</p><p>Бонус Дендро урона +15%.</p>",
            applied=True,
        )

        with patch("ui.right_panel_prototype.tr", return_value="Эффекты"):
            tooltip = _bonus_source_tooltip_html(item)

        self.assertIn("<b>Эффекты:</b>", tooltip)
        self.assertEqual(tooltip.count("Эффекты:"), 1)
        self.assertIn("Бонус Дендро урона +15%", tooltip)
        self.assertEqual(tooltip.count("Бонус Дендро урона +15%"), 1)
        self.assertNotIn("Dendro +15%", tooltip)
        self.assertNotIn("&lt;p&gt;", tooltip)
        self.assertNotIn("&lt;/p&gt;", tooltip)

    def test_moonsign_tooltip_keeps_effect_and_breakdown_non_duplicated(self) -> None:
        item = RightPanelBonusSourceDisplayItem(
            source_kind="moonsign",
            source_id="moonsign_lunar_reaction_bonus",
            label="Lunar",
            short_effects=("Lunar +36%",),
            tooltip_title="Moonsign",
            tooltip_body=(
                "До лимита: 42%; лимит: 36%.\n"
                "Вклад:\n"
                "Lauma: Dendro EM 400 -> +9%"
            ),
            applied=True,
        )

        html = _bonus_source_tooltip_html(item)

        self.assertEqual(html.count("Lunar +36%"), 1)
        self.assertEqual(html.count("Вклад:"), 1)
        self.assertIn("Lauma: Dendro EM 400", html)

    def test_bonus_chip_uses_separate_effect_badges(self) -> None:
        item = RightPanelBonusSourceDisplayItem(
            source_kind="elemental_resonance",
            source_id="pyro_resonance",
            label="Res",
            short_effects=("ATK +25%", "CR +15%"),
            applied=True,
        )

        with patch("ui.right_panel_prototype.install_custom_tooltip"):
            chip = BonusSourceChipWidget(item)
        labels = chip.findChildren(QLabel)
        icon_labels = [label for label in labels if label.objectName() == "BonusSourceIcon"]
        effect_badges = [
            label for label in labels if label.objectName() == "BonusSourceEffectBadge"
        ]

        self.assertEqual(len(icon_labels), 1)
        self.assertEqual([badge.text() for badge in effect_badges], ["ATK +25%", "CR +15%"])

    def test_bonus_strip_drag_scroll_keeps_transparency_styles_scoped(self) -> None:
        strip = BonusSourceStripWidget()

        self.assertTrue(strip._scroll.property("dragScrollArea"))
        self.assertTrue(strip._scroll.viewport().property("dragScrollViewport"))
        self.assertTrue(strip._content.property("dragScrollContent"))
        self.assertEqual(strip._content.styleSheet(), "")
        self.assertIn(
            'QWidget[dragScrollContent="true"]',
            strip._scroll.styleSheet(),
        )

    def test_member_side_icon_bottom_align_renderer_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon_path = Path(tmp) / "side_icon.png"
            image = QImage(16, 32, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.fillRect(QRect(4, 20, 8, 12), QColor(120, 220, 255, 255))
            painter.end()
            self.assertTrue(image.save(str(icon_path), "PNG"))

            _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE.clear()
            pixmap = _bonus_member_side_icon_pixmap(str(icon_path), QSize(22, 22))
            cache_size = len(_BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE)
            cached = _bonus_member_side_icon_pixmap(str(icon_path), QSize(22, 22))

            self.assertIsNotNone(pixmap)
            self.assertIsNotNone(cached)
            self.assertEqual(cache_size, 1)
            self.assertEqual(len(_BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE), cache_size)
            self.assertEqual(pixmap.size(), QSize(22, 22))
            image = pixmap.toImage()
            self.assertGreater(image.pixelColor(11, 21).alpha(), 0)

    def test_hexerei_chip_uses_member_icons_without_numeric_effect_badge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon_path = Path(tmp) / "member_icon.png"
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.fillRect(QRect(14, 12, 4, 8), QColor(120, 220, 255, 255))
            painter.end()
            self.assertTrue(image.save(str(icon_path), "PNG"))

            item = RightPanelBonusSourceDisplayItem(
                source_kind="hexerei",
                source_id="hexerei_membership",
                label="Hexerei",
                short_effects=(),
                character_icons=(str(icon_path),),
                character_tooltips=("Mona\nHexerei text",),
                applied=True,
            )

            _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE.clear()
            with patch("ui.right_panel_prototype.install_custom_tooltip"):
                chip = BonusSourceChipWidget(item)
        effect_badges = [
            label for label in chip.findChildren(QLabel)
            if label.objectName() == "BonusSourceEffectBadge"
        ]
        member_icons = [
            label for label in chip.findChildren(QLabel)
            if label.objectName() == "BonusSourceMemberIcon"
        ]

        self.assertEqual(effect_badges, [])
        self.assertEqual(len(member_icons), 1)
        self.assertEqual(
            member_icons[0].size(),
            QSize(BONUS_MEMBER_ICON_SIZE, BONUS_MEMBER_ICON_SIZE),
        )
        self.assertEqual(len(_BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE), 1)
        self.assertIsNotNone(member_icons[0].pixmap())

    def test_member_side_icon_composite_keeps_badge_background_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon_path = Path(tmp) / "member_icon.png"
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.fillRect(QRect(14, 12, 4, 8), QColor(120, 220, 255, 255))
            painter.end()
            self.assertTrue(image.save(str(icon_path), "PNG"))

            _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE.clear()
            pixmap = _bonus_member_side_icon_pixmap(
                str(icon_path),
                QSize(BONUS_MEMBER_ICON_SIZE, BONUS_MEMBER_ICON_SIZE),
            )

        self.assertIsNotNone(pixmap)
        self.assertGreater(pixmap.toImage().pixelColor(4, 16).alpha(), 0)


if __name__ == "__main__":
    unittest.main()
