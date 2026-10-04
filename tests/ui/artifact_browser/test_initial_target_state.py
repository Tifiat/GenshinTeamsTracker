from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from hoyolab_export.account_equipment import equip_artifact, remember_applied_build_preset
from hoyolab_export.artifact_db import create_build_preset, init_db
from tests.hoyolab_export.account.test_account_equipment import seeded_equipment_db
from ui.app_shell import LeftWorkspaceHost
from ui.artifact_browser.window import ArtifactBrowserWindow
from ui.artifact_browser.queries import calculate_build_summary, get_build_preset, list_build_presets
from ui.artifact_browser.store import ArtifactBrowserStore


class InitialArtifactTargetStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_first_host_open_has_equipment_highlight_priority_and_all_targets(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            conn.execute("UPDATE artifacts SET main_property_type=2000, main_property_name='HP', "
                         "main_property_value='4780', rarity=5, level=20")
            conn.execute("UPDATE artifacts SET rarity=4 WHERE id=1")
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            preset = create_build_preset(conn, name="Applied", slots={1: 1, 2: 4}, targets=[{
                "target_type": "character", "character_id": 1001, "character_name": "Hero A",
            }])
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1001, 4)
            remember_applied_build_preset(conn, 1001, preset)
            conn.commit()
            host = LeftWorkspaceHost(artifact_db_path=path)
            self.addCleanup(host.close)
            host.set_artifact_right_panel_operation_target({"character_id": 1001, "character_name": "Hero A"})
            host.set_virtual_gcsim_artifact_targets([{
                "gcsim_character_key": "futurehero", "character_name": "Future Hero",
            }])
            browser = host.ensure_artifact_browser_workspace()
            self.assertEqual(browser.selected_build_target_keys, {"character:1001"})
            self.assertTrue(browser.build_target_buttons_by_key["character:1001"].isChecked())
            self.assertIn("gcsim_character:futurehero", browser.build_target_items_by_key)
            self.assertEqual(browser.operation_target_character_id, 1001)
            self.assertEqual(browser.operation_target_source, "right_panel")
            self.assertEqual(browser.current_equipment_preview_slots, {1: 1, 2: 4})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1, 4})
            self.assertEqual(browser.model.artifact_ids[0], 1)
            self.assertIn("Applied", browser.equipment_zone_label.text())
            self.assertTrue(browser.build_preset_rows[preset].property("presetSelected"))
            self.assertIs(host.ensure_artifact_browser_workspace(), browser)

    def test_json_action_uses_loaded_database_flags_and_refreshes_after_reload(self):
        with seeded_equipment_db() as conn, patch.object(
            ArtifactBrowserWindow, "_add_build_preset_row_metadata", new=lambda *args: None,
        ):
            conn.execute("UPDATE artifacts SET main_property_type=2000, main_property_name='HP', "
                         "main_property_value='4780', rarity=5, level=20")
            conn.execute("UPDATE artifacts SET json_imported=1, import_source='artiscan' WHERE id=1")
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            conn.commit()
            with patch("ui.artifact_browser.queries.init_db", wraps=init_db) as initialize:
                browser = ArtifactBrowserWindow(db_path=path, character_asset_items=[])
                self.addCleanup(browser.close)
                self.assertTrue(browser.clear_json_button.isEnabled())
                browser.update_json_import_actions()
                browser.update_edit_selection_mode()
                self.assertEqual(initialize.call_count, 1)
                conn.execute("UPDATE artifacts SET import_source='hoyolab' WHERE id=1")
                conn.commit()
                browser.reload_from_database()
                self.assertFalse(browser.clear_json_button.isEnabled())
                self.assertEqual(initialize.call_count, 2)

    def test_initialized_read_wrappers_keep_results_without_repeating_schema_setup(self):
        with seeded_equipment_db() as conn:
            path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
            preset = create_build_preset(conn, name="Build", slots={1: 1})
            conn.commit()
            expected = list_build_presets(db_path=path)
            expected_summary = calculate_build_summary(build_id=preset, db_path=path)
            expected_preset = get_build_preset(preset, db_path=path)
            with patch("ui.artifact_browser.queries.init_db", side_effect=AssertionError("Unexpected DDL")):
                self.assertEqual(list_build_presets(db_path=path, initialize=False), expected)
                self.assertEqual(calculate_build_summary(build_id=preset, db_path=path, initialize=False),
                                 expected_summary)
                self.assertEqual(get_build_preset(preset, db_path=path, initialize=False), expected_preset)

    def test_store_initializes_missing_equipment_tables_before_reads(self):
        with seeded_equipment_db() as conn:
            conn.execute("UPDATE artifacts SET main_property_type=2000, main_property_name='HP', "
                         "main_property_value='4780', rarity=5, level=20")
            for table in ("account_character_applied_build_presets",
                          "account_character_equipped_artifacts",
                          "account_character_equipped_weapons"):
                conn.execute(f"DROP TABLE {table}")
            conn.commit()
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            store = ArtifactBrowserStore.load_from_db(path)
            self.assertTrue(store.database_exists)
            self.assertTrue(store.artifacts_by_id)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"account_character_applied_build_presets",
                             "account_character_equipped_artifacts",
                             "account_character_equipped_weapons"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
