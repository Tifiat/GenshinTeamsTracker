from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from tests.run_workspace.history.test_history_snapshot_builder import _slot_vm
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.utils.character_card_pixmap import character_card_pixmap


class CharacterPortraitLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Windows offscreen Qt has no system font database; only test rendering
        # needs this explicit load. The native application uses system fonts.
        font_path = Path("C:/Windows/Fonts/segoeui.ttf")
        if font_path.is_file() and not QFontDatabase.families():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                cls.app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 9))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.raw, self.background, self.element = (root / name for name in ("raw.png", "rarity.png", "element.png"))
        raw = Image.new("RGBA", (96, 96))
        raw.paste((25, 45, 220, 255), (24, 24, 72, 96))
        raw.save(self.raw)
        Image.new("RGBA", (96, 96), "#a45f25").save(self.background)
        Image.new("RGBA", (32, 32), "#cf3028").save(self.element)
        self.model = replace(_slot_vm(0, 0, character_title="Fixture Hero"),
                             portrait_path=str(self.raw), portrait_rarity=5, portrait_element="Pyro",
                             portrait_constellation=2, portrait_background_path=str(self.background),
                             portrait_element_icon_path=str(self.element))

    def test_shared_live_and_pvp_slot_renderer_prepares_all_layers(self):
        for team in (0, 1):
            with self.subTest(team=team):
                card = RightPanelSlotCardWidget(replace(self.model, team_index=team))
                self.addCleanup(card.close)
                image = card._portrait.pixmap().toImage()
                dpr = image.devicePixelRatio()
                sample = lambda x, y: image.pixelColor(round(x*dpr), round(y*dpr)).name()
                self.assertEqual(sample(3, 40), "#a45f25")
                self.assertEqual(sample(7, 7), "#cf3028")
                self.assertEqual(sample(45, 45), "#192ddc")
                self.assertNotEqual(sample(90, 7), "#a45f25")
                self.assertTrue(card._portrait.property("hasPixmap"))

    def test_constellation_and_element_changes_invalidate_slot_visual_without_selection_reload(self):
        card = RightPanelSlotCardWidget(self.model)
        self.addCleanup(card.close)
        first = card._portrait.pixmap().toImage()
        with patch("ui.right_panel.common.slot_parts.character_card_pixmap", wraps=character_card_pixmap) as render:
            card.set_model(replace(self.model, is_selected=True))
            render.assert_not_called()
            card.set_model(replace(self.model, portrait_constellation=6, is_selected=True))
            self.assertEqual(render.call_count, 1)
            self.assertNotEqual(first, card._portrait.pixmap().toImage())
            card.set_model(replace(self.model, portrait_element="Hydro", portrait_constellation=6))
            self.assertEqual(render.call_count, 2)

    def test_explicit_frozen_resources_do_not_use_live_bundle_and_preserve_dpr(self):
        with (
            patch("ui.utils.character_card_layers.character_background_path", side_effect=AssertionError("no live bundle")),
            patch("ui.utils.character_card_layers.filter_icon_path", side_effect=AssertionError("no live element")),
        ):
            for dpr in (.71, 1.25, 2.):
                pixmap = character_card_pixmap(str(self.raw), QSize(96, 96), dpr=dpr,
                    rarity=5, element="Pyro", constellation=2,
                    background_path=str(self.background), element_icon_path=str(self.element))
                self.assertEqual(pixmap.devicePixelRatio(), max(1., dpr))
                self.assertEqual(pixmap.width(), round(96*max(1., dpr)))

    def test_legacy_empty_and_missing_portraits_do_not_retain_decorations(self):
        card = RightPanelSlotCardWidget(self.model)
        self.addCleanup(card.close)
        legacy = replace(self.model, portrait_background_path="", portrait_element_icon_path="")
        card.set_model(legacy)
        self.assertEqual(card._portrait.pixmap().toImage().pixelColor(3, 40).alpha(), 0)
        card.set_model(replace(legacy, is_empty=True, portrait_path="", portrait_label="+"))
        self.assertFalse(card._portrait.property("hasPixmap"))
        self.assertEqual(card._portrait.text(), "+")


if __name__ == "__main__":
    unittest.main()
