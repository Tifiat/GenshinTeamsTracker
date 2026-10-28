from __future__ import annotations

import unittest

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from run_workspace.gcsim.virtual_roster import (
    GcsimCatalogCharacter,
    GcsimVirtualArtifactSetChoice,
    GcsimVirtualRosterCatalog,
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
)
from ui.gcsim_browser.virtual_slot_editor import VirtualGcsimCardEditor


_APP = QApplication.instance() or QApplication([])


class VirtualSlotEditorRefreshTest(unittest.TestCase):
    def test_unchanged_slot_refresh_preserves_popup_rows(self) -> None:
        editor = VirtualGcsimCardEditor()
        catalog = GcsimVirtualRosterCatalog(
            engine_id="test",
            characters=(GcsimCatalogCharacter("hero", "Hero", "polearm"),),
            weapons=(),
        )
        choices = (GcsimVirtualArtifactSetChoice("alpha", "Alpha", "alpha"),)
        editor.set_catalogs(catalog, choices)
        editor.set_context(override=None)
        row = editor.build_popup._rows["alpha"]

        editor.set_catalogs(catalog, choices)
        editor.set_context(override=None)

        self.assertIs(editor.build_popup._rows["alpha"], row)
        self.assertEqual(editor.character_combo.count(), 2)

    def test_changed_override_reuses_rows_and_changed_catalog_replaces_them(self) -> None:
        editor = VirtualGcsimCardEditor()
        catalog = GcsimVirtualRosterCatalog.empty()
        choices = (GcsimVirtualArtifactSetChoice("alpha", "Alpha", "alpha"),)
        editor.set_catalogs(catalog, choices)
        editor.set_context(override=None)
        row = editor.build_popup._rows["alpha"]

        editor.set_context(
            override=GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=0,
                character_key="hero",
                character_name="Hero",
                character_weapon_type="polearm",
                artifact_set_bonuses=(GcsimVirtualSetBonus("alpha", "Alpha", "alpha", 4),),
            )
        )
        self.assertIs(editor.build_popup._rows["alpha"], row)
        self.assertIn("4p", row.text())

        changed_choices = (GcsimVirtualArtifactSetChoice("beta", "Beta", "beta"),)
        editor.set_catalogs(catalog, changed_choices)
        editor.set_context(override=None)
        self.assertEqual(set(editor.build_popup._rows), {"beta"})


if __name__ == "__main__":
    unittest.main()
