from __future__ import annotations

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionButton, QWidget

from hoyolab_export.account_equipment import (
    equip_artifact,
    equip_weapon,
    get_equipped_weapon_for_character,
)
from hoyolab_export.artifact_db import connect_db, init_db
from ui.app_shell import (
    AppShell,
    AppShellController,
    AssetIconLabel,
    CharacterWeaponWorkspace,
    RIGHT_OPERATIONS_DOCK_WIDTH,
    RosterSelectionMarker,
    _SCALED_ICON_PIXMAP_CACHE,
)
from ui.artifact_browser.card_delegate import GRID_SIZE
from ui.artifact_browser.window import (
    ArtifactBrowserWindow,
    BUILD_PANEL_WIDTH,
    TARGET_PANEL_WIDTH,
)
from run_workspace.perf import perf_enabled
from localization import tr
from ui.utils.marquee_label import MarqueeButton
from ui.utils.overlay_scroll import OverlayVerticalScrollArea, OverlayVerticalScrollbar
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS, MODE_DPS_DUMMY


class AppShellTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_app_shell_constructs_with_character_weapon_workspace(self) -> None:
        shell = AppShell()

        self.assertIsInstance(
            shell.left_host.character_weapon_workspace,
            CharacterWeaponWorkspace,
        )
        self.assertEqual(shell.left_host.stack.currentIndex(), 0)
        self.assertEqual(shell.left_host.stack.count(), 2)
        self.assertIsNone(shell.left_host.artifact_browser_workspace)

    def test_perf_logging_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {"GTT_PERF_LOG": ""}):
            self.assertFalse(perf_enabled())

    def test_right_dock_uses_fixed_width(self) -> None:
        shell = AppShell()

        self.assertEqual(shell.right_dock.minimumWidth(), shell.right_dock.maximumWidth())
        self.assertEqual(shell.right_dock.minimumWidth(), RIGHT_OPERATIONS_DOCK_WIDTH)
        self.assertEqual(shell.right_dock.sizePolicy().horizontalPolicy().name, "Fixed")

    def test_artifact_workspace_can_be_created_and_switched_to(self) -> None:
        shell = AppShell()

        shell.left_host.show_artifact_browser_workspace()

        self.assertIsInstance(
            shell.left_host.artifact_browser_workspace,
            ArtifactBrowserWindow,
        )
        self.assertEqual(
            shell.left_host.stack.currentWidget(),
            shell.left_host.artifact_browser_workspace,
        )
        self.assertEqual(shell.right_dock.minimumWidth(), RIGHT_OPERATIONS_DOCK_WIDTH)

    def test_artifact_workspace_minimum_width_lands_on_one_grid_cell(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(1535, 900)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None

        shell.resize(shell.minimumSizeHint().width(), shell.height())
        self._app.processEvents()
        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        viewport_width = browser.list_view.viewport().width()
        self.assertGreaterEqual(viewport_width, GRID_SIZE.width())
        self.assertLessEqual(viewport_width, GRID_SIZE.width() + 8)
        self.assertGreaterEqual(
            browser.build_target_panel.width(),
            browser.build_target_panel.minimumSizeHint().width(),
        )
        self.assertEqual(browser.build_target_panel.width(), TARGET_PANEL_WIDTH)
        self.assertLess(browser.build_target_panel.width(), 180)
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)

        content_right = (
            browser.content_layout.geometry().x()
            + browser.content_layout.geometry().width()
        )
        for index in range(browser.content_layout.count()):
            widget = browser.content_layout.itemAt(index).widget()
            assert widget is not None
            self.assertLessEqual(widget.geometry().x() + widget.width(), content_right)

        shell.close()
        self._app.processEvents()

    def test_switching_artifact_workspace_preserves_team_state(self) -> None:
        shell = AppShell()
        shell.left_host.character_weapon_workspace.character_clicked.emit(
            _character_asset("10000050", "Thoma")
        )

        shell.left_host.show_artifact_browser_workspace()
        shell.left_host.stack.setCurrentIndex(0)

        self.assertEqual(shell.controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(shell.controller.selected_slot_index, 0)

    def test_embedded_artifact_browser_is_not_standalone_window(self) -> None:
        parent = QWidget()
        browser = ArtifactBrowserWindow(parent=parent, embedded=True)

        self.assertFalse(bool(browser.windowFlags() & Qt.Window))
        self.assertFalse(browser.close_button.isVisible())
        self.assertTrue(browser.embedded)
        browser.update_adaptive_target_panel_width()
        self.assertFalse(browser._adaptive_target_resize_timer.isActive())

    def test_embedded_artifact_browser_uses_non_shifting_scrollbars(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.build_target_scroll, OverlayVerticalScrollArea)
        self.assertIsInstance(browser.build_preset_list_scroll, OverlayVerticalScrollArea)
        self.assertIsInstance(
            browser.artifact_grid_overlay_scrollbar,
            OverlayVerticalScrollbar,
        )
        self.assertEqual(
            browser.list_view.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertIs(
            browser.artifact_grid_overlay_scrollbar._overlay.parent(),
            browser.list_view,
        )

    def test_artifact_browser_target_title_has_room_for_localized_text(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.build_target_title_label, MarqueeButton)
        self.assertGreaterEqual(browser.build_target_title_label.minimumWidth(), 50)
        self.assertLessEqual(browser.build_target_title_label.minimumWidth(), 70)
        self.assertEqual(browser.build_target_title_label.sizeHint().width(), 0)
        self.assertEqual(
            browser.build_target_title_label.minimumSizeHint().width(),
            0,
        )
        self.assertEqual(
            browser.build_target_title_label.sizePolicy().horizontalPolicy().name,
            "Expanding",
        )

    def test_artifact_browser_json_buttons_use_compact_marquee_text(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.import_json_button, MarqueeButton)
        self.assertIsInstance(browser.clear_json_button, MarqueeButton)
        assert browser.import_json_button is not None
        assert browser.clear_json_button is not None
        self.assertEqual(browser.import_json_button.sizeHint().width(), 0)
        self.assertEqual(browser.clear_json_button.sizeHint().width(), 0)
        self.assertLessEqual(
            browser.import_json_button.minimumWidth(),
            GRID_SIZE.width() // 2,
        )
        self.assertLessEqual(
            browser.clear_json_button.minimumWidth(),
            GRID_SIZE.width() // 2,
        )

    def test_artifact_browser_target_buttons_use_marquee_without_forcing_width(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        long_key = "character:99999999"
        icon_path = next(
            (
                item.get("path")
                for item in browser.build_target_items_by_key.values()
                if item.get("path")
            ),
            None,
        )
        browser.build_target_items_by_key[long_key] = {
            "key": long_key,
            "target_type": "character",
            "character_id": 99999999,
            "character_name": "Очень Длинное Имя Персонажа Для Проверки Прокрутки",
            "asset": {},
            "path": icon_path,
        }

        browser.refresh_build_target_list()
        button = browser.build_target_buttons_by_key[long_key]

        self.assertIsInstance(button, MarqueeButton)
        self.assertEqual(button.sizeHint().width(), 0)
        self.assertEqual(button.minimumSizeHint().width(), 0)
        self.assertLessEqual(button.minimumWidth(), 100)
        self.assertEqual(browser.build_target_panel.width(), TARGET_PANEL_WIDTH)

        option = QStyleOptionButton()
        button.initStyleOption(option)
        text_rect = button._text_rect(option)
        icon_rect = button._icon_rect(text_rect, option.iconSize)
        text_start = icon_rect.right() + 7

        self.assertFalse(option.icon.isNull())
        self.assertGreater(text_start, icon_rect.right())
        self.assertGreater(button._available_text_width(), 0)
        self.assertGreaterEqual(text_start, text_rect.left() + option.iconSize.width())
        self.assertLess(text_start, text_rect.right())

    def test_right_panel_target_updates_artifact_browser_equip_state(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            browser = shell.left_host.ensure_artifact_browser_workspace()
            browser.build_target_items_by_key["character:10000050"] = {
                "key": "character:10000050",
                "target_type": "character",
                "character_id": 10000050,
                "character_name": "Thoma",
            }
            browser.refresh_build_target_list()

            shell.left_host.character_weapon_workspace.character_clicked.emit(
                _character_asset("10000050", "Thoma")
            )

            self.assertEqual(browser.operation_target_character_id, 10000050)
            self.assertEqual(browser.operation_target_source, "right_panel")
            self.assertTrue(browser.equip_mode_enabled)
            self.assertEqual(browser.equipment_target_label.text(), "")
            self.assertNotIn("right panel", browser.equipment_target_label.text().casefold())
            self.assertNotIn("правой панели", browser.equipment_target_label.text().casefold())
            self.assertEqual(browser.selected_build_target_keys, {"character:10000050"})
            self.assertFalse(browser.build_preset_list_scroll.isHidden())
            self.assertTrue(
                browser.build_target_buttons_by_key["character:10000050"].isChecked()
            )

            browser.toggle_build_target("character:10000050")

            self.assertEqual(browser.selected_build_target_keys, set())
            self.assertEqual(browser.operation_target_character_id, 10000050)
            self.assertEqual(browser.operation_target_source, "right_panel")
            self.assertTrue(browser.equip_mode_enabled)
            self.assertTrue(browser.build_preset_list_scroll.isHidden())
            button = browser.build_target_buttons_by_key["character:10000050"]
            self.assertFalse(button.isChecked())
            self.assertTrue(button.property("operationTarget"))

            shell._on_slot_selected(0, 0)

            self.assertFalse(browser.equip_mode_enabled)
            self.assertFalse(
                browser.build_target_buttons_by_key["character:10000050"].isChecked()
            )
            self.assertFalse(
                browser.build_target_buttons_by_key["character:10000050"].property(
                    "operationTarget"
                )
            )

    def test_artifact_browser_can_browse_other_target_while_right_target_stays_active(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.build_target_items_by_key["character:10000050"] = {
            "key": "character:10000050",
            "target_type": "character",
            "character_id": 10000050,
            "character_name": "Thoma",
        }
        browser.build_target_items_by_key["character:10000089"] = {
            "key": "character:10000089",
            "target_type": "character",
            "character_id": 10000089,
            "character_name": "Furina",
        }
        browser.refresh_build_target_list()

        browser.set_right_panel_operation_target(
            {"character_id": 10000050, "character_name": "Thoma"}
        )
        browser.toggle_build_target("character:10000050")
        browser.toggle_build_target("character:10000089")

        self.assertEqual(browser.selected_build_target_keys, {"character:10000089"})
        self.assertEqual(browser.operation_target_character_id, 10000050)
        self.assertEqual(browser.operation_target_source, "right_panel")
        self.assertTrue(browser.equip_mode_enabled)
        self.assertTrue(browser.build_target_buttons_by_key["character:10000089"].isChecked())
        self.assertFalse(browser.build_target_buttons_by_key["character:10000050"].isChecked())
        self.assertTrue(
            browser.build_target_buttons_by_key["character:10000050"].property(
                "operationTarget"
            )
        )

    def test_artifact_browser_target_falls_back_to_one_browser_character(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.build_target_items_by_key["character:10000050"] = {
            "key": "character:10000050",
            "target_type": "character",
            "character_id": 10000050,
            "character_name": "Thoma",
        }
        browser.build_target_items_by_key["character:10000089"] = {
            "key": "character:10000089",
            "target_type": "character",
            "character_id": 10000089,
            "character_name": "Furina",
        }

        browser.selected_build_target_keys = {"character:10000050"}
        browser.refresh_equipment_target_state()

        self.assertEqual(browser.operation_target_character_id, 10000050)
        self.assertEqual(browser.operation_target_source, "artifact_browser")
        self.assertTrue(browser.equip_mode_enabled)

        browser.selected_build_target_keys = {"character:10000050", "character:10000089"}
        browser.refresh_equipment_target_state()

        self.assertFalse(browser.equip_mode_enabled)

    def test_artifact_browser_current_equipment_zone_scaffold(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertEqual(
            browser.equipment_zone_label.text(),
            tr("artifact.build.current_equipment"),
        )
        browser.set_right_panel_operation_target(
            {"character_id": 10000050, "character_name": "Thoma"}
        )
        self.assertEqual(
            browser.equipment_zone_label.text(),
            tr("artifact.build.current_equipment"),
        )

        browser.selected_build_id = 123
        browser.update_build_panel()

        self.assertEqual(
            browser.equipment_zone_label.text(),
            tr("artifact.equipment.apply_preset"),
        )
        self.assertFalse(browser.equipment_zone_action_button.isEnabled())

    def test_character_weapon_workspace_uses_overlay_scroll_areas(self) -> None:
        workspace = CharacterWeaponWorkspace()

        self.assertIsInstance(workspace.weapon_area, OverlayVerticalScrollArea)
        self.assertIsInstance(workspace.char_area, OverlayVerticalScrollArea)
        self.assertEqual(
            workspace.weapon_area.verticalScrollBarPolicy().name,
            "ScrollBarAlwaysOff",
        )
        self.assertEqual(
            workspace.char_area.verticalScrollBarPolicy().name,
            "ScrollBarAlwaysOff",
        )

    def test_initial_right_panel_has_no_selected_target(self) -> None:
        shell = AppShell()

        model = shell.controller.right_panel_model()
        self.assertFalse(model.selected_details.has_selection)
        self.assertEqual(shell.controller.selected_team_index, -1)
        self.assertEqual(shell.controller.selected_slot_index, -1)

    def test_controller_character_without_selection_fills_first_empty_slot(self) -> None:
        controller = AppShellController.empty()

        changed = controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        self.assertTrue(changed)
        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000050")
        self.assertEqual(controller.selected_team_index, 0)
        self.assertEqual(controller.selected_slot_index, 0)
        self.assertEqual(slot.character_details_data["account_character"]["portrait_path"], "thoma.png")

    def test_controller_character_with_selection_still_fills_first_empty_slot(self) -> None:
        controller = AppShellController.empty()
        controller.toggle_slot_selection(0, 2)

        changed = controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        self.assertTrue(changed)
        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000089")
        self.assertIsNone(controller.state.team(0).slot(2).character)
        self.assertEqual(controller.selected_slot_index, 0)

    def test_controller_existing_character_click_removes_without_compacting(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma"))
        controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        changed = controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        self.assertTrue(changed)
        self.assertIsNone(controller.state.team(0).slot(0).character)
        self.assertEqual(controller.state.team(0).slot(1).character.id, "10000089")
        selected_ids = [
            slot.character.id
            for slot in controller.state.team(0).slots
            if slot.character is not None
        ]
        self.assertEqual(selected_ids, ["10000089"])

    def test_repeated_slot_click_clears_selected_target(self) -> None:
        controller = AppShellController.empty()

        controller.toggle_slot_selection(0, 1)
        controller.toggle_slot_selection(0, 1)

        self.assertEqual(controller.selected_team_index, -1)
        self.assertEqual(controller.selected_slot_index, -1)

    def test_weapon_without_selected_character_does_not_assign(self) -> None:
        controller = AppShellController.empty()

        changed = controller.assign_weapon_to_selected_slot(_weapon_asset("13407", "Favonius Lance"))

        self.assertFalse(changed)

    def test_weapon_with_selected_character_assigns_compatible_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                persisted = get_equipped_weapon_for_character(conn, 10000050)

        self.assertTrue(changed)
        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.weapon.id, "13407")
        self.assertEqual(slot.character_details_data["account_weapon"]["icon_path"], "fav.png")
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.weapon_fingerprint, "fingerprint-13407")

    def test_incompatible_weapon_fails_soft(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))

        changed = controller.assign_weapon_to_selected_slot(
            _weapon_asset("11401", "Sword", weapon_type=1)
        )

        self.assertFalse(changed)
        self.assertIsNone(controller.state.team(0).slot(0).weapon)

    def test_weapon_type_filter_uses_stable_weapon_type_metadata(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._weapon_type_filters = {"polearm"}

        self.assertTrue(
            workspace._weapon_matches_filters(
                _weapon_asset(
                    "13407",
                    "Favonius Lance",
                    weapon_type=13,
                    weapon_type_name="localized polearm label",
                )
            )
        )
        self.assertFalse(
            workspace._weapon_matches_filters(
                _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="sword")
            )
        )

    def test_weapon_rarity_and_type_filters_can_combine(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._weapon_type_filters = {"polearm"}
        workspace._weapon_rarity_filters = {4}

        self.assertTrue(
            workspace._weapon_matches_filters(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13, rarity=4)
            )
        )
        self.assertFalse(
            workspace._weapon_matches_filters(
                _weapon_asset("13505", "Five Star Spear", weapon_type=13, rarity=5)
            )
        )

    def test_persistent_weapon_clears_for_new_character_and_restores_old_character(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            with closing(connect_db(db_path)) as conn:
                persisted_after_remove = get_equipped_weapon_for_character(conn, 10000050)
            controller.add_or_replace_character(_character_asset("10000089", "Furina", weapon_type=1))

            furina_slot = controller.state.team(0).slot(0)
            details = controller.right_panel_model().selected_details

            controller.add_or_replace_character(_character_asset("10000089", "Furina", weapon_type=1))
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            thoma_slot = controller.state.team(0).slot(0)

        self.assertIsNotNone(persisted_after_remove)
        self.assertEqual(furina_slot.character.id, "10000089")
        self.assertIsNone(furina_slot.weapon)
        self.assertEqual(details.weapon_name, "")
        self.assertEqual(details.weapon_icon_path, "")
        self.assertEqual(details.weapon_tooltip, "")
        self.assertEqual(thoma_slot.character.id, "10000050")
        self.assertEqual(thoma_slot.weapon.id, "13407")

    def test_adding_character_restores_persistent_weapon_from_sqlite(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000050, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.weapon.id, "13407")
        self.assertEqual(
            slot.character_details_data["account_weapon"]["source_key"],
            "fingerprint-13407",
        )

    def test_replacing_character_restores_incoming_own_persistent_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000050, "fingerprint-13407")
                equip_weapon(conn, 10000089, "fingerprint-11401")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000089", "Furina", weapon_type=1)
            )

        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000089")
        self.assertEqual(slot.weapon.id, "11401")
        self.assertEqual(slot.character_details_data["account_weapon"]["name"], "Sword")

    def test_app_shell_assignment_respects_known_count_without_stale_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000051, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

        self.assertFalse(changed)
        self.assertIsNone(controller.state.team(0).slot(0).weapon)
        self.assertIn("No available copy", controller.last_equipment_error)

    def test_app_shell_has_no_session_weapon_memory_source_of_truth(self) -> None:
        controller = AppShellController.empty()

        self.assertFalse(hasattr(controller, "session_equipment_by_character_id"))

    def test_persistent_equipment_is_per_character_across_modes(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

            controller.set_mode(MODE_DPS_DUMMY)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        self.assertEqual(len(controller.state.teams), 1)
        self.assertEqual(controller.state.team(0).slot(0).weapon.id, "13407")

    def test_adding_character_reads_current_equipped_artifact_ids_readonly(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        details = controller.state.team(0).slot(0).character_details_data
        self.assertEqual(
            details["current_equipped_artifact_ids_by_slot"],
            {"flower": 1},
        )
        self.assertEqual(details["selected_build"]["build_id"], None)
        self.assertEqual(
            details["selected_build"]["identity_source"],
            "current_equipment",
        )
        self.assertEqual(
            details["stat_snapshot"]["artifact"]["summary"]["artifact_ids_by_pos"],
            {"1": 1},
        )
        stat_totals = {
            item["property_type"]: item["raw_value"]
            for item in details["stat_snapshot"]["artifact"]["summary"]["stat_totals"]
        }
        self.assertEqual(stat_totals[2], 4780.0)
        self.assertTrue(details["source_notes"]["current_equipped_artifacts_readonly"])
        self.assertTrue(details["source_notes"]["current_equipment_artifact_snapshot"])

    def test_current_equipped_artifact_set_bonus_appears_in_right_panel(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000050, 2)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            model = controller.right_panel_model()

        artifact_sources = [
            item
            for item in model.selected_details.bonus_sources
            if item.source_kind == "artifact_set_static"
        ]
        self.assertEqual(model.selected_details.active_sets, ("2p Current Set",))
        self.assertEqual(len(artifact_sources), 1)
        self.assertEqual(artifact_sources[0].short_effects, ("ATK +18%",))

    def test_replacing_character_clears_current_artifact_snapshot_from_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000089", "Furina", weapon_type=1)
            )

        details = controller.state.team(0).slot(0).character_details_data
        self.assertEqual(details["account_character"]["id"], "10000089")
        self.assertNotIn("current_equipped_artifact_ids_by_slot", details)
        self.assertNotIn("stat_snapshot", details)
        self.assertEqual(controller.right_panel_model().selected_details.active_sets, ())

    def test_current_equipped_artifact_restore_does_not_create_build_rows(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                before = _artifact_build_count(conn)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                after = _artifact_build_count(conn)

        self.assertEqual(after, before)

    def test_sequential_quick_pick_fills_team_one_then_team_two(self) -> None:
        controller = AppShellController.empty()

        for index in range(5):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        self.assertEqual(
            [slot.character.id for slot in controller.state.team(0).slots],
            ["10000050", "10000051", "10000052", "10000053"],
        )
        self.assertEqual(controller.state.team(1).slot(0).character.id, "10000054")

    def test_sequential_quick_pick_preserves_gaps_and_blocks_when_full(self) -> None:
        controller = AppShellController.empty()
        for index in range(8):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        self.assertFalse(
            controller.add_or_replace_character(_character_asset("10000099", "Overflow"))
        )

        controller.add_or_replace_character(_character_asset("10000051", "Character 1"))
        self.assertIsNone(controller.state.team(0).slot(1).character)
        controller.add_or_replace_character(_character_asset("10000099", "Overflow"))

        self.assertEqual(controller.state.team(0).slot(1).character.id, "10000099")
        self.assertEqual(controller.state.team(0).slot(2).character.id, "10000052")

    def test_mode_states_keep_independent_quick_picks(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        controller.set_mode(MODE_DPS_DUMMY)
        controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000089")
        self.assertEqual(len(controller.state.teams), 1)

        controller.set_mode(MODE_ABYSS)
        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(len(controller.state.teams), 2)

    def test_roster_selection_markers_expose_team_color_and_slot_number(self) -> None:
        controller = AppShellController.empty()
        for index in range(5):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        markers = controller.roster_selection_markers()

        self.assertEqual(markers["10000050"].slot_number, 1)
        self.assertEqual(markers["10000050"].team_index, 0)
        self.assertEqual(markers["10000054"].slot_number, 1)
        self.assertEqual(markers["10000054"].team_index, 1)
        self.assertNotEqual(markers["10000050"].color, markers["10000054"].color)

        controller.add_or_replace_character(_character_asset("10000054", "Character 4"))
        self.assertNotIn("10000054", controller.roster_selection_markers())

    def test_marker_update_does_not_reload_character_grid(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            workspace.set_character_selection_markers(
                {
                    "10000050": RosterSelectionMarker(
                        team_index=0,
                        slot_index=0,
                        slot_number=1,
                        color="#3ed47b",
                    )
                },
                affected_character_ids={"10000050"},
            )

        self.assertIsNotNone(card.selection_marker)
        self.assertEqual(card.selection_marker.slot_number, 1)

    def test_marker_update_clears_removed_card_without_pixmap_reload(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        marker = RosterSelectionMarker(
            team_index=0,
            slot_index=0,
            slot_number=1,
            color="#3ed47b",
        )
        card.set_selection_marker(marker)
        workspace._character_selection_markers = {"10000050": marker}
        workspace._character_cards_by_id = {"10000050": card}

        with (
            patch.object(workspace, "reload_characters", side_effect=AssertionError),
            patch.object(card, "_update_pixmap", side_effect=AssertionError),
        ):
            workspace.set_character_selection_markers(
                {},
                affected_character_ids={"10000050"},
            )

        self.assertIsNone(card.selection_marker)

    def test_app_shell_character_click_uses_incremental_marker_update(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))

        self.assertIsNotNone(card.selection_marker)
        self.assertEqual(card.selection_marker.slot_number, 1)
        shell.flush_pending_right_panel_refresh()

    def test_roster_click_defers_right_panel_refresh(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))

            self.assertIsNotNone(card.selection_marker)
            self.assertEqual(set_model.call_count, 0)
            self.assertTrue(shell._right_panel_refresh_pending)

            shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_rapid_roster_clicks_coalesce_right_panel_refresh(self) -> None:
        shell = AppShell()

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            for index in range(4):
                shell._on_character_clicked(
                    _character_asset(f"1000005{index}", f"Character {index}")
                )

            self.assertEqual(set_model.call_count, 0)
            self.assertTrue(shell._right_panel_refresh_pending)

            shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_weapon_click_schedules_right_panel_refresh(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
                shell._on_weapon_clicked(_weapon_asset("13407", "Favonius Lance", weapon_type=13))

                self.assertEqual(set_model.call_count, 0)
                self.assertTrue(shell._right_panel_refresh_pending)

                shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_right_panel_uses_visible_asset_path_for_character_portrait(self) -> None:
        shell = AppShell()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "portrait.png"
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#00ff00"))
            self.assertTrue(pixmap.save(str(path)))
            asset = _character_asset("10000050", "Thoma")
            asset["path"] = str(path)
            asset["metadata"]["character"]["portrait_path"] = "missing-relative.png"

            shell._on_character_clicked(asset)
            shell.flush_pending_right_panel_refresh()

            model = shell.controller.right_panel_model()

        self.assertEqual(model.teams[0].slots[0].portrait_path, str(path))

    def test_right_panel_uses_visible_asset_path_for_weapon_icon(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "weapon.png"
                pixmap = QPixmap(8, 8)
                pixmap.fill(QColor("#00ff00"))
                self.assertTrue(pixmap.save(str(path)))
                asset = _weapon_asset("13407", "Favonius Lance", weapon_type=13)
                asset["path"] = str(path)
                asset["metadata"]["weapon"]["icon_path"] = "missing-relative-weapon.png"

                shell._on_weapon_clicked(asset)
                shell.flush_pending_right_panel_refresh()

                model = shell.controller.right_panel_model()

        self.assertEqual(model.teams[0].slots[0].weapon_image_path, str(path))
        self.assertEqual(model.selected_details.weapon_icon_path, str(path))

    def test_app_shell_weapon_assignment_loads_passive_tooltip_and_bonus_source(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            with (
                patch(
                "ui.app_shell.get_weapon_passive_tooltip",
                return_value={
                    "passive_name": "Windfall",
                    "passive_text": "CRIT Hits generate Elemental Particles.",
                    "language": "en-us",
                },
                ) as passive_lookup,
                patch(
                    "ui.app_shell.list_weapon_display_stat_effects",
                    return_value=[
                        {
                            "weapon_id": 13407,
                            "refinement": 5,
                            "stat_key": "ENERGY_RECHARGE",
                            "value": 12,
                            "value_type": "percent_points",
                        }
                    ],
                ) as effects_lookup,
            ):
                weapon_asset = _weapon_asset("13407", "Favonius Lance", weapon_type=13, rarity=4)
                weapon_asset["metadata"]["weapon"]["desc"] = "A polearm made from old lore."
                shell._on_weapon_clicked(
                    weapon_asset
                )
                shell.flush_pending_right_panel_refresh()

            model = shell.controller.right_panel_model()
        weapon_sources = [
            item
            for item in model.selected_details.bonus_sources
            if item.source_kind == "weapon_passive_static"
        ]

        self.assertEqual(passive_lookup.call_count, 1)
        self.assertEqual(effects_lookup.call_count, 1)
        self.assertIn("Favonius Lance R5", model.selected_details.weapon_tooltip)
        self.assertIn("Windfall", model.selected_details.weapon_tooltip)
        self.assertIn("Elemental Particles", model.selected_details.weapon_tooltip)
        self.assertNotIn("old lore", model.selected_details.weapon_tooltip)
        self.assertEqual(len(weapon_sources), 1)
        self.assertEqual(weapon_sources[0].short_effects, ("ER +12%",))
        self.assertIn("Windfall", weapon_sources[0].tooltip_body)

    def test_switching_weapon_clears_stale_static_passive_and_tooltip(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _seed_weapon_static_effect(
                    conn,
                    weapon_id=13407,
                    stat_key="ATK_PERCENT",
                    value=15.0,
                    value_type="percent_points",
                    passive_name="Old ATK Passive",
                    passive_text="Increases ATK by 15%.",
                )
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            shell._on_weapon_clicked(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            with_bonus = shell.controller.right_panel_model()
            shell._on_weapon_clicked(
                _weapon_asset("13408", "Kitain Cross Spear", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            no_bonus = shell.controller.right_panel_model()

        self.assertTrue(
            any(
                item.source_kind == "weapon_passive_static"
                and item.short_effects == ("ATK +15%",)
                for item in with_bonus.selected_details.bonus_sources
            )
        )
        slot_details = shell.controller.state.team(0).slot(0).character_details_data
        self.assertEqual(slot_details["weapon_display_stat_effects"], [])
        self.assertEqual(slot_details["weapon_passive_reference"], {})
        self.assertFalse(
            any(
                item.source_kind == "weapon_passive_static"
                for item in no_bonus.selected_details.bonus_sources
            )
        )
        self.assertNotIn("Old ATK Passive", no_bonus.selected_details.weapon_tooltip)
        self.assertNotIn("Increases ATK", no_bonus.selected_details.weapon_tooltip)

    def test_switching_weapon_clears_stale_em_static_passive_display_stats(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _seed_weapon_static_effect(
                    conn,
                    weapon_id=13407,
                    stat_key="ELEMENTAL_MASTERY",
                    value=100.0,
                    value_type="flat",
                    passive_name="Old EM Passive",
                    passive_text="Increases Elemental Mastery by 100.",
                )
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            shell._on_weapon_clicked(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            with_bonus = shell.controller.right_panel_model()
            shell._on_weapon_clicked(
                _weapon_asset("13408", "Kitain Cross Spear", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            no_bonus = shell.controller.right_panel_model()

        self.assertTrue(
            any(row.label == "EM" and row.value == "100" for row in with_bonus.selected_details.stat_rows)
        )
        self.assertFalse(
            any(row.label == "EM" for row in no_bonus.selected_details.stat_rows)
        )
        self.assertFalse(
            any(
                item.source_kind == "weapon_passive_static"
                for item in no_bonus.selected_details.bonus_sources
            )
        )

    def test_team_bonus_member_icons_use_visible_asset_paths(self) -> None:
        shell = AppShell()
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.png"
            second_path = Path(temp_dir) / "second.png"
            first_pixmap = QPixmap(8, 8)
            first_pixmap.fill(QColor("#00ff00"))
            second_pixmap = QPixmap(8, 8)
            second_pixmap.fill(QColor("#0000ff"))
            self.assertTrue(first_pixmap.save(str(first_path)))
            self.assertTrue(second_pixmap.save(str(second_path)))
            first = _character_asset("10000050", "Thoma")
            second = _character_asset("10000089", "Furina", weapon_type=1)
            for asset, path in ((first, first_path), (second, second_path)):
                asset["path"] = str(path)
                character = asset["metadata"]["character"]
                character["portrait_path"] = "missing-relative-portrait.png"
                character["side_icon_path"] = "missing-relative-side.png"
                character["traits"] = ["hexerei", "moonsign"]

            shell._on_character_clicked(first)
            shell._on_character_clicked(second)
            model = shell.controller.right_panel_model()

        sources = {item.source_kind: item for item in model.selected_details.bonus_sources}
        self.assertIn("hexerei", sources)
        self.assertIn("moonsign", sources)
        self.assertEqual(sources["hexerei"].character_icons[:2], (str(first_path), str(second_path)))
        self.assertEqual(sources["moonsign"].character_icons[:2], (str(first_path), str(second_path)))

    def test_selected_character_auto_filters_weapons_by_type_and_clears_on_cancel(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        with patch(
            "ui.app_shell.load_account_weapon_stack_asset_items",
            return_value=[
                _weapon_asset("13407", "Favonius Lance", weapon_type=13),
                _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword"),
            ],
        ):
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, {"polearm"})
            self.assertTrue(workspace._weapon_type_buttons["polearm"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["sword"].isChecked())
            self.assertEqual(workspace.weapon_grid.count(), 1)

            shell._on_slot_selected(0, 0)
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, set())
            self.assertFalse(workspace._weapon_type_buttons["polearm"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["sword"].isChecked())

            shell._on_character_clicked(_character_asset("10000089", "Furina", weapon_type=1))
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, {"sword"})
            self.assertTrue(workspace._weapon_type_buttons["sword"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["polearm"].isChecked())

        shell.flush_pending_right_panel_refresh()

    def test_mode_switch_syncs_markers_without_grid_rebuild(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))
            self.assertIsNotNone(card.selection_marker)
            shell._on_mode_requested(MODE_DPS_DUMMY)

        self.assertIsNone(card.selection_marker)
        self.assertTrue(shell._right_panel_refresh_pending)
        shell.flush_pending_right_panel_refresh()

    def test_mode_switch_schedules_refresh_without_immediate_set_model(self) -> None:
        shell = AppShell()
        shell._on_character_clicked(_character_asset("10000050", "Thoma"))
        shell.flush_pending_right_panel_refresh()

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            shell._on_mode_requested(MODE_DPS_DUMMY)

            self.assertEqual(set_model.call_count, 0)
            self.assertTrue(shell._right_panel_refresh_pending)

            shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_character_filters_use_session_cached_items(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True

        with patch(
            "ui.app_shell.load_account_character_asset_items",
            return_value=[
                _character_asset("10000050", "Thoma"),
                _character_asset("10000089", "Furina", weapon_type=1),
            ],
        ) as load_items:
            workspace.reload_characters()
            workspace._character_weapon_filters = {"sword"}
            workspace.reload_characters()

        self.assertEqual(load_items.call_count, 1)
        self.assertEqual(list(workspace._character_cards_by_id), ["10000089"])

    def test_weapon_filters_use_session_cached_items(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True

        with patch(
            "ui.app_shell.load_account_weapon_stack_asset_items",
            return_value=[
                _weapon_asset("13407", "Favonius Lance", weapon_type=13),
                _weapon_asset("11401", "Sword", weapon_type=1),
            ],
        ) as load_items:
            workspace.reload_weapons()
            workspace._weapon_type_filters = {"sword"}
            workspace.reload_weapons()

        self.assertEqual(load_items.call_count, 1)
        self.assertEqual(workspace.weapon_grid.count(), 1)

    def test_marker_registry_survives_filter_rebuilds(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        marker = RosterSelectionMarker(
            team_index=0,
            slot_index=0,
            slot_number=1,
            color="#3ed47b",
        )
        workspace.set_character_selection_markers({"10000050": marker})

        with patch(
            "ui.app_shell.load_account_character_asset_items",
            return_value=[
                _character_asset("10000050", "Thoma"),
                _character_asset("10000089", "Furina", weapon_type=1),
            ],
        ):
            workspace.reload_characters()
            workspace._character_weapon_filters = {"sword"}
            workspace.reload_characters()
            workspace._character_weapon_filters = set()
            workspace.reload_characters()

        self.assertIn("10000050", workspace._character_cards_by_id)
        self.assertIsNotNone(workspace._character_cards_by_id["10000050"].selection_marker)

    def test_scaled_icon_pixmap_cache_reuses_scaled_pixmaps(self) -> None:
        _SCALED_ICON_PIXMAP_CACHE.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "icon.png"
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#ff0000"))
            self.assertTrue(pixmap.save(str(path)))

            first = AssetIconLabel(str(path), 24)
            first_hit = first._last_pixmap_cache_hit
            second = AssetIconLabel(str(path), 24)
            second_hit = second._last_pixmap_cache_hit

        self.assertFalse(first_hit)
        self.assertTrue(second_hit)

    def test_workspace_character_signal_updates_app_shell_state(self) -> None:
        shell = AppShell()

        shell.left_host.character_weapon_workspace.character_clicked.emit(
            _character_asset("10000050", "Thoma")
        )
        shell.flush_pending_right_panel_refresh()

        self.assertEqual(shell.controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(shell.controller.selected_slot_index, 0)

    def test_workspace_weapon_signal_updates_selected_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell.left_host.character_weapon_workspace.character_clicked.emit(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()

            shell.left_host.character_weapon_workspace.weapon_clicked.emit(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()

        self.assertEqual(shell.controller.state.team(0).slot(0).weapon.id, "13407")


def _character_asset(
    character_id: str,
    name: str,
    *,
    weapon_type: int = 13,
) -> dict:
    weapon_names = {
        1: "sword",
        10: "catalyst",
        11: "claymore",
        12: "bow",
        13: "polearm",
    }
    return {
        "path": "portrait.png",
        "filename": "portrait.png",
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "level": 90,
                "element": "Pyro",
                "rarity": 4,
                "constellation": 6,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_names.get(weapon_type, "polearm"),
                "portrait_path": f"{name.casefold()}.png",
            }
        },
    }


def _weapon_asset(
    weapon_id: str,
    name: str,
    *,
    weapon_type: int = 13,
    weapon_type_name: str = "Polearm",
    rarity: int = 4,
    weapon_fingerprint: str | None = None,
) -> dict:
    fingerprint = weapon_fingerprint or f"fingerprint-{weapon_id}"
    return {
        "path": "weapon.png",
        "filename": "weapon.png",
        "metadata": {
            "weapon": {
                "id": weapon_id,
                "name": name,
                "level": 90,
                "rarity": rarity,
                "refinement": 5,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "type_name": weapon_type_name,
                "icon_path": "fav.png",
                "source_key": fingerprint,
                "weapon_fingerprint": fingerprint,
            }
        },
    }


class temp_app_shell_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "artifacts.db"
        with closing(connect_db(self.path)) as conn:
            init_db(conn)
            _seed_app_shell_characters(conn)
            _seed_app_shell_weapons(conn)
            _seed_app_shell_artifacts(conn)
            conn.commit()
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def _seed_app_shell_characters(conn) -> None:
    conn.executemany(
        """
        INSERT INTO account_characters (
            character_id,
            name,
            weapon_type,
            weapon_type_name
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (10000050, "Thoma", 13, "polearm"),
            (10000051, "Polearm Friend", 13, "polearm"),
            (10000089, "Furina", 1, "sword"),
        ],
    )


def _seed_app_shell_weapons(conn) -> None:
    conn.executemany(
        """
        INSERT INTO account_weapon_observed_stacks (
            weapon_fingerprint,
            weapon_id,
            name,
            weapon_type,
            weapon_type_name,
            rarity,
            level,
            refinement,
            icon_path,
            known_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("fingerprint-13407", 13407, "Favonius Lance", 13, "Polearm", 4, 90, 5, "fav.png", 1),
            ("fingerprint-13408", 13408, "Kitain Cross Spear", 13, "Polearm", 4, 90, 1, "kitain.png", 1),
            ("fingerprint-11401", 11401, "Sword", 1, "Sword", 4, 90, 1, "sword.png", 1),
        ],
    )


def _seed_app_shell_artifacts(conn) -> None:
    conn.execute(
        """
        INSERT INTO artifact_sets (
            set_uid,
            hoyowiki_entry_id,
            fallback_name,
            updated_at
        )
        VALUES ('current_set', 'current-set-entry', 'Current Set', '2026-05-26T00:00:00+00:00')
        """
    )
    conn.executemany(
        """
        INSERT INTO artifacts (
            id,
            fingerprint,
            name,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-05-26T00:00:00+00:00', '2026-05-26T00:00:00+00:00')
        """,
        [
            (1, "artifact-flower-a", "Flower A", "current_set", "Current Set", 1, "Flower", 5, 20, 2, "HP", "4780"),
            (2, "artifact-plume-a", "Plume A", "current_set", "Current Set", 2, "Plume", 5, 20, 5, "ATK", "311"),
        ],
    )
    conn.execute(
        """
        INSERT INTO artifact_set_display_stat_effects (
            set_uid,
            pieces_required,
            stat_key,
            value,
            value_type,
            updated_at
        )
        VALUES ('current_set', 2, 'ATK_PERCENT', 18.0, 'percent_points', '2026-05-26T00:00:00+00:00')
        """
    )


def _seed_weapon_static_effect(
    conn,
    *,
    weapon_id: int,
    stat_key: str,
    value: float,
    value_type: str,
    passive_name: str,
    passive_text: str,
) -> None:
    conn.execute(
        """
        INSERT INTO weapon_display_stat_effects (
            weapon_id,
            refinement,
            stat_key,
            value,
            value_type,
            updated_at
        )
        VALUES (?, 5, ?, ?, ?, '2026-05-26T00:00:00+00:00')
        """,
        (weapon_id, stat_key, value, value_type),
    )
    conn.execute(
        """
        INSERT INTO weapon_passive_tooltips (
            weapon_id,
            lang,
            passive_name,
            passive_text,
            updated_at
        )
        VALUES (?, 'en-us', ?, ?, '2026-05-26T00:00:00+00:00')
        """,
        (weapon_id, passive_name, passive_text),
    )


def _artifact_build_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM artifact_builds").fetchone()
    return int(row["count"])
