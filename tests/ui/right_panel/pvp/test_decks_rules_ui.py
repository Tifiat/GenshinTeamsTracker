"""Isolated Decks rules controls; no account or network data is loaded."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from localization import tr
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel


class _Workspace(QObject):
    state_changed = Signal()
    save_edit_requested = Signal()
    cancel_edit_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.preset = SimpleNamespace(
            deck_id="deck-1", name="Example", character_ids=("a",), weapon_refs=("w",),
            rules_snapshot={},
        )
        self.presets = [self.preset]
        self.selected_deck_id = self.preset.deck_id
        self.is_editing = False
        self.is_new_deck_edit = False
        self._last_status = ""
        self.selected_id = "old-rules"
        self.catalog_loaded = True
        self.refreshes = 0
        self.updated = 0
        self.selections: list[str] = []

    def active_preset(self):
        return self.preset

    def validation_report(self):
        return SimpleNamespace(ready=True, issue_codes=lambda: ())

    def rules_ui_state(self):
        return {
            "options": (
                {"id": "free_draft_v0", "label": "Free Draft"},
                {"id": "latest-rules", "label": "Abyss latest"},
            ),
            "selected_id": self.selected_id,
            "loading": False,
            "catalog_loaded": self.catalog_loaded,
            "editable": self.is_editing,
            "source_title": "Abyss 2026",
            "version_text": "v2",
            "freshness": "update" if self.selected_id == "old-rules" else "current",
            "update_id": "latest-rules" if self.selected_id == "old-rules" else "",
            "summary_lines": ("Total cost: 16",),
            "requirement_lines": ("At least 8 characters",),
            "issue_lines": ("One missing weapon",),
            "error_text": "",
        }

    def refresh_rules_catalog(self):
        self.refreshes += 1

    def update_ruleset(self):
        self.updated += 1
        return True

    def select_ruleset(self, ruleset_id):
        self.selections.append(ruleset_id)
        self.selected_id = ruleset_id
        self.state_changed.emit()
        return True

    def begin_edit(self):
        self.is_editing = True
        self.state_changed.emit()
        return True

    def save_edit(self, *, name):
        self.preset.name = name
        self.is_editing = False
        self.state_changed.emit()
        return True

    def cancel_edit(self):
        self.is_editing = False
        self.state_changed.emit()

    def select_deck(self, deck_id):
        self.selected_deck_id = deck_id

    def delete_deck(self, deck_id):
        return False

    def export_profile(self, path):
        return False


class DecksRulesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_view_shows_saved_unlisted_rules_and_refresh_and_update(self):
        workspace = _Workspace()
        panel = PvpDecksRightPanel(workspace)

        self.assertFalse(panel.ruleset_button.isEnabled())
        self.assertIsNone(panel.ruleset_button.currentData())
        self.assertIn("Abyss 2026", panel.ruleset_button.currentText())
        self.assertEqual(panel.ruleset_button.count(), 3)
        self.assertEqual(panel.rules_refresh_button.text(), tr("app_shell.pvp.decks.rules_refresh"))
        panel.rules_refresh_button.click()
        panel.rules_update_button.click()
        self.assertEqual((workspace.refreshes, workspace.updated), (1, 1))
        self.assertEqual(
            panel.selected_info_labels["counts"].text(),
            tr("app_shell.pvp.decks.counts").format(characters=1, weapons=1),
        )
        details = [label.text() for label in panel.findChildren(type(panel.status_label))]
        self.assertIn("Total cost: 16", details)
        self.assertIn("At least 8 characters", details)
        self.assertIn("One missing weapon", details)
        panel.deleteLater()

    def test_edit_selection_preserves_unsaved_name_across_state_refresh(self):
        workspace = _Workspace()
        workspace.selected_id = "free_draft_v0"
        workspace.catalog_loaded = False
        panel = PvpDecksRightPanel(workspace)
        self.assertEqual(panel.rules_refresh_button.text(), tr("app_shell.pvp.decks.rules_load"))
        workspace.begin_edit()
        panel.edit_name_edit.setText("Unsaved name")
        self.assertTrue(panel.ruleset_button.isEnabled())

        index = panel.ruleset_button.findData("latest-rules")
        panel.ruleset_button.activated.emit(index)

        self.assertEqual(workspace.selections, ["latest-rules"])
        self.assertEqual(panel.edit_name_edit.text(), "Unsaved name")
        self.assertEqual(panel.ruleset_button.currentData(), "latest-rules")
        panel.deleteLater()

    def test_new_deck_exposes_rules_before_any_preset_is_saved(self):
        workspace = _Workspace()
        workspace.presets = []
        workspace.selected_deck_id = workspace.preset.deck_id
        workspace.is_editing = True
        workspace.is_new_deck_edit = True
        workspace.selected_id = "free_draft_v0"
        panel = PvpDecksRightPanel(workspace)

        self.assertTrue(panel.new_deck_info.isVisibleTo(panel))
        self.assertTrue(panel.ruleset_button.isEnabled())
        self.assertEqual(panel.ruleset_button.currentData(), "free_draft_v0")
        self.assertIn("counts", panel.selected_info_labels)
        panel.deleteLater()

    def test_rules_snapshot_uses_editable_validation_message(self):
        workspace = _Workspace()
        workspace.preset.rules_snapshot = {"source": {"title": "Abyss"}}
        panel = PvpDecksRightPanel(workspace)

        self.assertEqual(
            panel.selected_info_labels["validation"].text(),
            tr("app_shell.pvp.rules.deck_editable"),
        )
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
