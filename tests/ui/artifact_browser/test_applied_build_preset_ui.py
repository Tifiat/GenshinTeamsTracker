from __future__ import annotations

import unittest
from contextlib import closing
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from hoyolab_export.account_equipment import get_applied_build_preset, unequip_artifact_slot
from hoyolab_export.artifact_db import connect_db, create_build_preset
from tests.hoyolab_export.account.test_account_equipment import seeded_equipment_db
from ui.artifact_browser.window import ArtifactBrowserWindow


class AppliedBuildPresetUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_browser(self, path):
        browser = ArtifactBrowserWindow(db_path=path, character_asset_items=[])
        browser.set_right_panel_operation_target({"character_id": 1001, "name": "Hero A"})
        self.addCleanup(browser.close)
        return browser

    @staticmethod
    def complete_artifact_fixture(conn):
        conn.execute(
            "UPDATE artifacts SET main_property_type = 2000, "
            "main_property_name = 'HP', main_property_value = '4780', rarity = 5, level = 20"
        )

    def test_apply_switch_reopen_and_highlight_preview_then_applied(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None
        ):
            self.complete_artifact_fixture(conn)
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            target = [{"target_type": "character", "character_id": 1001, "character_name": "Hero A"}]
            first = create_build_preset(conn, name="Top build", slots={1: 1, 2: 4}, targets=target)
            second = create_build_preset(conn, name="Other", slots={1: 2}, targets=target)
            conn.commit()
            browser = self.make_browser(path)
            browser.build_preset_row_buttons[first].click()
            self.assertTrue(browser.build_preset_rows[first].property("presetSelected"))
            self.assertFalse(browser.build_preset_rows[second].property("presetSelected"))
            browser.equipment_zone_action_button.click()
            self.assertIn("Top build", browser.equipment_zone_label.text())
            self.assertTrue(browser.build_preset_rows[first].property("presetSelected"))
            browser.set_right_panel_operation_target({"character_id": 1002, "name": "Hero B"})
            self.assertNotIn("Top build", browser.equipment_zone_label.text())
            browser.set_right_panel_operation_target({"character_id": 1001, "name": "Hero A"})
            self.assertIn("Top build", browser.equipment_zone_label.text())
            browser.close()
            reopened = self.make_browser(path)
            self.assertIn("Top build", reopened.equipment_zone_label.text())
            reopened.build_preset_row_buttons[second].click()
            self.assertTrue(reopened.build_preset_rows[second].property("presetSelected"))
            self.assertFalse(reopened.build_preset_rows[first].property("presetSelected"))
            reopened.build_preset_row_buttons[second].click()
            self.assertTrue(reopened.build_preset_rows[first].property("presetSelected"))
            with closing(connect_db(path)) as writer:
                unequip_artifact_slot(writer, 1001, 1)
                writer.commit()
            reopened.update_build_panel()
            self.assertNotIn("Top build", reopened.equipment_zone_label.text())
            self.assertFalse(reopened.build_preset_rows[first].property("presetSelected"))

    def test_apply_failure_rolls_back_partial_equipment_and_marker(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None
        ):
            self.complete_artifact_fixture(conn)
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            preset = create_build_preset(conn, name="Build", slots={1: 1, 2: 4}, targets=[
                {"target_type": "character", "character_id": 1001, "character_name": "Hero A"}
            ])
            conn.commit()
            browser = self.make_browser(path)
            browser.build_preset_row_buttons[preset].click()
            with patch("ui.artifact_browser.window.remember_applied_build_preset", side_effect=RuntimeError("fixture failure")):
                browser.equipment_zone_action_button.click()
            self.assertIsNone(get_applied_build_preset(conn, 1001))
            self.assertEqual(conn.execute("SELECT count(*) FROM account_character_equipped_artifacts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
