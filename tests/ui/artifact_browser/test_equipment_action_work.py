from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton

from hoyolab_export.account_equipment import equip_artifact, get_applied_build_preset
from hoyolab_export.artifact_db import create_build_preset
from tests.hoyolab_export.account.test_account_equipment import seeded_equipment_db
from ui.artifact_browser import window as window_module
from ui.artifact_browser.window import ArtifactBrowserWindow


class EquipmentActionWorkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_browser(self, conn):
        conn.execute("UPDATE artifacts SET main_property_type=2000, main_property_name='HP', "
                     "main_property_value='4780', rarity=5, level=20")
        target = [{"target_type": "character", "character_id": 1001, "character_name": "Hero A"}]
        first = create_build_preset(conn, name="Applied", slots={1: 1, 2: 4}, targets=target)
        other = create_build_preset(conn, name="Other", slots={1: 2}, targets=target)
        conn.commit()
        browser = ArtifactBrowserWindow(
            db_path=Path(conn.execute("PRAGMA database_list").fetchone()[2]),
            character_asset_items=[], operation_target={"character_id": 1001, "name": "Hero A"},
        )
        self.addCleanup(browser.close)
        return browser, first, other

    def test_apply_keeps_rows_and_preserves_marker_and_manual_toggle(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            browser, preset, other = self.make_browser(conn)
            rows = dict(browser.build_preset_rows)
            with patch("ui.artifact_browser.queries.init_db", side_effect=AssertionError("Unexpected schema setup")), patch(
                "hoyolab_export.account_equipment.init_account_equipment_storage",
                side_effect=AssertionError("Unexpected equipment setup"),
            ):
                browser.build_preset_row_buttons[preset].click()
                browser.equipment_zone_action_button.click()
                self.assertIsNone(browser.selected_build_id)
                self.assertEqual(browser.current_equipment_preview_slots, {1: 1, 2: 4})
                self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1, 4})
                self.assertIn("Applied", browser.equipment_zone_label.text())
                self.assertTrue(browser.build_preset_rows[preset].property("presetSelected"))
                self.assertFalse(browser.build_preset_row_buttons[preset].isChecked())
                self.assertFalse(browser.build_preset_rows[other].property("presetSelected"))
                self.assertTrue(all(browser.build_preset_rows[key] is row for key, row in rows.items()))
                browser.equip_clicked_artifact(1)
                self.assertEqual(browser.current_equipment_preview_slots, {2: 4})
                self.assertNotIn("Applied", browser.equipment_zone_label.text())
                self.assertFalse(browser.build_preset_rows[preset].property("presetSelected"))
                browser.equip_clicked_artifact(1)
                self.assertEqual(browser.current_equipment_preview_slots, {1: 1, 2: 4})
                self.assertNotIn("Applied", browser.equipment_zone_label.text())
            self.assertIsNone(get_applied_build_preset(conn, 1001))

    def test_apply_cancels_pending_delete_and_restores_normal_row_controls(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            browser, preset, other = self.make_browser(conn)
            browser.select_build_preset(preset)
            browser.request_delete_build_preset(other)
            pending_row = browser.build_preset_rows[other]
            self.assertIsNotNone(pending_row.findChild(QPushButton, "row_cancel_button"))
            browser.apply_selected_build_preset_to_current_equipment()
            self.assertIsNone(browser.pending_delete_build_id)
            self.assertIsNot(browser.build_preset_rows[other], pending_row)
            self.assertIn(other, browser.build_preset_row_buttons)
            self.assertIsNone(browser.build_preset_rows[other].findChild(QPushButton, "row_cancel_button"))
            self.assertTrue(browser.build_preset_rows[preset].property("presetSelected"))

    def test_conflict_preflight_is_one_fresh_batch_with_unique_other_owners(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            browser, _, _ = self.make_browser(conn)
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1002, 2)
            equip_artifact(conn, 1002, 4)
            equip_artifact(conn, 1003, 3)
            conn.commit()
            statements = []
            connect = window_module.connect_db

            def traced(path):
                opened = connect(path)
                opened.set_trace_callback(statements.append)
                return opened

            with patch.object(window_module, "connect_db", new=traced):
                self.assertEqual(browser._preset_conflict_character_ids(1001, [1, 2, 3, 4, 2]), (1002, 1003))
            self.assertEqual(len(statements), 1)
            self.assertTrue(statements[0].lstrip().upper().startswith("SELECT"))

    def test_deselect_and_bonus_cells_use_one_current_slot_read(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            browser, preset, _ = self.make_browser(conn)
            browser.select_build_preset(preset)
            browser.apply_selected_build_preset_to_current_equipment()
            browser.select_build_preset(preset)
            with patch(
                "ui.artifact_browser.window.list_equipped_artifacts_for_character",
                wraps=window_module.list_equipped_artifacts_for_character,
            ) as read_slots:
                browser.select_build_preset(preset)
                self.assertEqual(read_slots.call_count, 1)
                self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1, 4})
            with patch.object(
                ArtifactBrowserWindow, "current_build_artifact_ids",
                new=lambda *args: self.fail("Bonus cells reread equipment"),
            ):
                browser.fill_build_bonus_summary([
                    {"set_uid": "fixture-first", "set_name": "First", "count": 2},
                    {"set_uid": "fixture-second", "set_name": "Second", "count": 2},
                ], artifact_ids={1, 4})

    def test_preset_row_descendants_are_visible_after_open_and_refresh(self):
        with seeded_equipment_db() as conn:
            browser, _, _ = self.make_browser(conn)
            browser.resize(1250, 800)
            browser.show()
            self.app.processEvents()
            for refresh in (False, True):
                if refresh:
                    browser.refresh_build_preset_list()
                    self.app.processEvents()
                for row in browser.build_preset_rows.values():
                    self.assertTrue(row.isVisible())
                    children = row.findChildren(window_module.QWidget)
                    self.assertGreater(len(children), 3)
                    self.assertTrue(all(child.isVisible() for child in children))


if __name__ == "__main__":
    unittest.main()
