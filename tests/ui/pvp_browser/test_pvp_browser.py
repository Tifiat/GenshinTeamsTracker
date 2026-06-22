from __future__ import annotations

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QSizePolicy

from hoyolab_export.account_equipment import (
    equip_weapon,
    list_equipped_weapon_owners,
)
from hoyolab_export.artifact_db import connect_db, init_db
from localization import tr
from ui.character_browser.filter_bar import CharacterFilterBar
from ui.pvp_browser.build_flow import (
    PvpRuntimeEquipmentState,
    PvpScopedCharacterWeaponWorkspace,
    _asset_weapon_keys,
)
from ui.pvp_browser.draft_order import PVP_DRAFT_ORDER_SLOT_SIZE
from ui.pvp_browser.window import PvpDecksWorkspace, PvpDraftWorkspace, PvpWorkspace
from ui.pvp_browser.timers import PvpTimersResultWidget
from ui.right_panel.pvp._shared import (
    PVP_DRAFT_BAN_ACCENT,
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_PAGE_DECKS,
    PVP_PAGE_DRAFT,
    PVP_PAGE_PLAY,
)
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.right_panel.common.seat_accent_frame import PvpSeatAccentFrame
from ui.right_panel.common.team_card import RightPanelTeamCardWidget
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.pvp.draft.panel import (
    PvpDraftRightPanel,
    PvpPostDraftRunPanel,
    PvpPostDraftSeatFrame,
)
from ui.right_panel.pvp.host import PvpRightPanelHost
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.utils.pixel_icon_grid import PixelIconGrid
from ui.utils.pvp_colors import pvp_player_color


class PvpBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_pvp_decks_workspace_create_view_edit_save_cancel(self) -> None:
        characters = [
            _character_asset("10000050", "Thoma"),
            _character_asset("10000089", "Furina", weapon_type=1),
        ]
        weapons = [
            _weapon_asset("13407", "Favonius Lance", weapon_type=13),
            _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )

            self.assertTrue(workspace.create_deck("Preset"))
            self.assertTrue(workspace.is_editing)
            self.assertTrue(workspace.is_new_deck_edit)
            self.assertEqual(workspace.selected_counts(), (2, 2))
            self.assertEqual(set(workspace.character_cards_by_id), {"10000050", "10000089"})
            workspace.cancel_edit()
            self.assertFalse(workspace.presets)

            self.assertTrue(workspace.create_deck("Preset"))
            self.assertTrue(workspace.save_edit(name="Preset"))

            self.assertTrue(workspace.begin_edit())
            workspace.character_cards_by_id["10000050"].clicked.emit(characters[0])
            self.assertTrue(
                workspace.character_cards_by_id["10000050"].property("deckInactive")
            )
            workspace.cancel_edit()
            self.assertEqual(workspace.selected_counts(), (2, 2))

            self.assertTrue(workspace.begin_edit())
            workspace.character_cards_by_id["10000050"].clicked.emit(characters[0])
            self.assertTrue(workspace.save_edit(name="Edited"))

            self.assertFalse(workspace.is_editing)
            self.assertEqual(workspace.selected_counts(), (1, 2))
            self.assertEqual(workspace.selected_preset().name, "Edited")
            self.assertNotIn("10000050", workspace.character_cards_by_id)
            self.assertIn("10000089", workspace.character_cards_by_id)

    def test_pvp_decks_workspace_empty_account_does_not_create_fake_deck(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: [],
                weapon_assets_provider=lambda: [],
            )

            self.assertFalse(workspace.create_deck("Empty"))
            self.assertEqual(workspace.presets, [])

    def test_pvp_decks_show_event_skips_unchanged_viewport_refresh(self) -> None:
        characters = [_character_asset("10000050", "Thoma")]
        weapons = [_weapon_asset("13407", "Favonius Lance", weapon_type=13)]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            workspace._last_refresh_viewport_widths = workspace._current_viewport_widths()

            with patch.object(workspace, "refresh_view", wraps=workspace.refresh_view) as refresh:
                QApplication.sendEvent(workspace, QEvent(QEvent.Type.Show))

            refresh.assert_not_called()

    def test_pvp_decks_width_change_refreshes_view(self) -> None:
        characters = [_character_asset("10000050", "Thoma")]
        weapons = [_weapon_asset("13407", "Favonius Lance", weapon_type=13)]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            workspace._last_refresh_viewport_widths = (-1, -1)

            with patch.object(workspace, "refresh_view", wraps=workspace.refresh_view) as refresh:
                workspace._refresh_view_if_viewport_widths_changed()

            refresh.assert_called_once()

    def test_pvp_decks_right_panel_has_no_start_draft_action(self) -> None:
        characters = [_character_asset("10000089", "Furina", weapon_type=1)]
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertTrue(workspace.create_deck("Preset"))
            self.assertTrue(workspace.save_edit(name="Preset"))
            panel = PvpDecksRightPanel(workspace)

            self.assertIn(workspace.selected_deck_id, panel.deck_row_frames)
            self.assertFalse(panel.ruleset_button.isEnabled())
            self.assertFalse(
                [
                    button
                    for button in panel.findChildren(QPushButton)
                    if button.text() == "Start local draft"
                ]
            )
            self.assertEqual(
                panel.selected_info_labels["counts"].text(),
                tr("app_shell.pvp.decks.counts").format(characters=1, weapons=1),
            )

    def test_pvp_decks_right_panel_shortcuts_save_and_cancel_edits(self) -> None:
        characters = [
            _character_asset("10000050", "Thoma"),
            _character_asset("10000089", "Furina", weapon_type=1),
        ]
        weapons = [
            _weapon_asset("13407", "Favonius Lance", weapon_type=13),
            _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            panel = PvpDecksRightPanel(workspace)

            panel.create_name_edit.setText("Draft")
            panel.create_button.click()
            self.assertTrue(workspace.is_new_deck_edit)
            self._send_key(panel.create_name_edit, Qt.Key.Key_Return)
            self.assertFalse(workspace.is_editing)
            self.assertEqual(workspace.selected_preset().name, "Draft")

            panel.create_name_edit.setText("Discard")
            panel.create_button.click()
            self.assertTrue(workspace.is_new_deck_edit)
            self._send_key(panel.create_name_edit, Qt.Key.Key_Escape)
            self.assertFalse(workspace.is_editing)
            self.assertEqual([preset.name for preset in workspace.presets], ["Draft"])

            self.assertTrue(workspace.begin_edit())
            panel.edit_name_edit.setText("Renamed")
            self._send_key(panel.edit_name_edit, Qt.Key.Key_Return)
            self.assertFalse(workspace.is_editing)
            self.assertEqual(workspace.selected_preset().name, "Renamed")

            self.assertTrue(workspace.begin_edit())
            panel.edit_name_edit.setText("Reverted")
            workspace.character_cards_by_id["10000050"].clicked.emit(characters[0])
            self.assertEqual(workspace.selected_counts(), (1, 2))
            self._send_key(panel.edit_name_edit, Qt.Key.Key_Escape)
            self.assertFalse(workspace.is_editing)
            self.assertEqual(workspace.selected_preset().name, "Renamed")
            self.assertEqual(workspace.selected_counts(), (2, 2))

    def test_pvp_decks_workspace_shortcut_signal_saves_after_card_toggle(self) -> None:
        characters = [
            _character_asset("10000050", "Thoma"),
            _character_asset("10000089", "Furina", weapon_type=1),
        ]
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            panel = PvpDecksRightPanel(workspace)
            self.assertTrue(workspace.create_deck("Preset"))
            self.assertTrue(workspace.save_edit(name="Preset"))

            self.assertTrue(workspace.begin_edit())
            panel.edit_name_edit.setText("Left Save")
            workspace.character_cards_by_id["10000050"].clicked.emit(characters[0])
            self.assertTrue(all(shortcut.isEnabled() for shortcut in workspace._edit_shortcuts))

            workspace._emit_save_edit_requested()

            self.assertFalse(workspace.is_editing)
            self.assertEqual(workspace.selected_preset().name, "Left Save")
            self.assertEqual(workspace.selected_counts(), (1, 1))

    def test_pvp_decks_right_panel_compact_info_validation_without_manual_validate(
        self,
    ) -> None:
        characters = [
            _character_asset(str(20000000 + index), f"Char {index}", weapon_type=1)
            for index in range(11)
        ]
        weapons = [
            _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword"),
            _weapon_asset("13407", "Lance", weapon_type=13),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertTrue(workspace.create_deck("Ready"))
            self.assertTrue(workspace.save_edit(name="Ready"))
            panel = PvpDecksRightPanel(workspace)

            self.assertNotIn("name", panel.selected_info_labels)
            self.assertNotIn(
                "Ready",
                [label.text() for label in panel.selected_info_labels.values()],
            )
            self.assertEqual(
                panel.selected_info_labels["validation"].text(),
                tr("app_shell.pvp.decks.validation_ready").format(issues=0),
            )
            self.assertFalse(
                any(
                    button.text() == "Validate"
                    for button in panel.findChildren(QPushButton)
                )
            )

    def test_pvp_decks_edit_mode_exposes_selected_card_markers(self) -> None:
        characters = [
            _character_asset("10000050", "Thoma"),
            _character_asset("10000089", "Furina", weapon_type=1),
        ]
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpDecksWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertFalse(workspace.property("pvpDeckEditMode"))
            self.assertFalse(workspace.weapon_area.property("deckEditMode"))
            self.assertFalse(workspace.weapon_widget.property("deckEditMode"))
            self.assertFalse(workspace.character_area.property("deckEditMode"))
            self.assertFalse(workspace.character_widget.property("deckEditMode"))

            self.assertTrue(workspace.create_deck("Preset"))
            self.assertTrue(workspace.property("pvpDeckEditMode"))
            self.assertTrue(workspace.weapon_area.property("deckEditMode"))
            self.assertTrue(workspace.weapon_widget.property("deckEditMode"))
            self.assertTrue(workspace.character_area.property("deckEditMode"))
            self.assertTrue(workspace.character_widget.property("deckEditMode"))
            self.assertTrue(
                workspace.character_cards_by_id["10000050"].property("deckEditSelected")
            )
            self.assertTrue(workspace.save_edit(name="Preset"))
            self.assertFalse(workspace.property("pvpDeckEditMode"))
            self.assertFalse(workspace.weapon_area.property("deckEditMode"))
            self.assertFalse(workspace.weapon_widget.property("deckEditMode"))
            self.assertFalse(workspace.character_area.property("deckEditMode"))
            self.assertFalse(workspace.character_widget.property("deckEditMode"))
            self.assertFalse(
                workspace.character_cards_by_id["10000050"].property("deckEditSelected")
            )

            panel = PvpDecksRightPanel(workspace)
            self.assertIn(workspace.selected_deck_id, panel.deck_row_frames)

            self.assertTrue(workspace.begin_edit())
            self.assertTrue(workspace.property("pvpDeckEditMode"))
            self.assertTrue(workspace.weapon_area.property("deckEditMode"))
            self.assertTrue(workspace.character_area.property("deckEditMode"))
            self.assertTrue(
                workspace.character_cards_by_id["10000050"].property("deckEditSelected")
            )
            workspace.character_cards_by_id["10000050"].clicked.emit(characters[0])
            self.assertFalse(
                workspace.character_cards_by_id["10000050"].property("deckEditSelected")
            )
            self.assertTrue(
                workspace.character_cards_by_id["10000050"].property("deckInactive")
            )
            self.assertTrue(
                workspace.character_cards_by_id["10000089"].property("deckEditSelected")
            )

            workspace.cancel_edit()
            self.assertFalse(workspace.property("pvpDeckEditMode"))
            self.assertFalse(workspace.weapon_area.property("deckEditMode"))
            self.assertFalse(workspace.character_area.property("deckEditMode"))

    def test_pvp_play_panel_lists_presets_and_uses_decks_selection_default(self) -> None:
        characters = _valid_character_assets()
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertTrue(workspace.decks_workspace.create_deck("Alpha"))
            self.assertTrue(workspace.decks_workspace.save_edit(name="Alpha"))
            self.assertTrue(workspace.decks_workspace.create_deck("Beta"))
            self.assertTrue(workspace.decks_workspace.save_edit(name="Beta"))
            beta_id = next(
                preset.deck_id for preset in workspace.presets if preset.name == "Beta"
            )
            workspace.decks_workspace.select_deck(beta_id)

            panel = PvpPlayRightPanel(workspace)

            self.assertEqual(panel.player_1_combo.count(), 2)
            self.assertEqual(
                [panel.player_1_combo.itemText(index) for index in range(2)],
                ["Alpha", "Beta"],
            )
            self.assertEqual(panel.player_1_deck_id, beta_id)
            self.assertTrue(panel.start_button.isEnabled())

    def test_pvp_play_start_disabled_without_valid_decks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: [],
                weapon_assets_provider=lambda: [],
            )
            panel = PvpPlayRightPanel(workspace)

            self.assertFalse(panel.start_button.isEnabled())
            self.assertFalse(workspace.start_local_draft("", ""))
            self.assertIsNone(workspace.active_draft_session)
            self.assertIn(
                tr("app_shell.pvp.play.start_blocked"),
                panel.status_label.text(),
            )

    def test_pvp_play_start_creates_in_memory_controller_summary(self) -> None:
        characters = _valid_character_assets()
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertTrue(workspace.decks_workspace.create_deck("Alpha"))
            self.assertTrue(workspace.decks_workspace.save_edit(name="Alpha"))
            self.assertTrue(workspace.decks_workspace.create_deck("Beta"))
            self.assertTrue(workspace.decks_workspace.save_edit(name="Beta"))
            panel = PvpPlayRightPanel(workspace)
            beta_index = panel.player_2_combo.findText("Beta")
            panel.player_2_combo.setCurrentIndex(beta_index)

            panel.start_button.click()

            self.assertIsNotNone(workspace.active_draft_session)
            session = workspace.active_draft_session
            board = session.board_dict()
            self.assertEqual(board["draft_system"]["system_id"], "free_draft_v0")
            self.assertIn("current_requirement", board)
            self.assertGreater(board["progress"]["legal_target_count"], 0)
            self.assertEqual(len(board["action_log"]), 0)
            summary_text = "\n".join(
                label.text() for label in panel.active_summary_labels if label.text()
            )
            self.assertIn("Legal targets:", summary_text)
            self.assertIn("Action log: 0", summary_text)
            self.assertIn(
                tr("app_shell.pvp.play.summary_open_draft"),
                summary_text,
            )
            self.assertEqual(workspace.active_page_id, PVP_PAGE_DRAFT)
            self.assertIs(workspace.stack.currentWidget(), workspace.draft_workspace)

    def test_pvp_play_same_deck_for_both_players_is_allowed(self) -> None:
        characters = _valid_character_assets()
        weapons = [_weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword")]
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: characters,
                weapon_assets_provider=lambda: weapons,
            )
            self.assertTrue(workspace.decks_workspace.create_deck("Mirror"))
            self.assertTrue(workspace.decks_workspace.save_edit(name="Mirror"))
            panel = PvpPlayRightPanel(workspace)

            panel.start_button.click()

            session = workspace.active_draft_session
            self.assertIsNotNone(session)
            self.assertEqual(session.player_1_deck_id, session.player_2_deck_id)
            self.assertIsNot(
                session.controller.state.player_1_deck,
                session.controller.state.player_2_deck,
            )
            self.assertTrue(session.controller.state.setup_ready)

    def test_pvp_draft_tab_without_active_session_shows_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: [],
                weapon_assets_provider=lambda: [],
            )
            host = PvpRightPanelHost(workspace)

            host.set_page(PVP_PAGE_DRAFT)

            self.assertEqual(workspace.active_page_id, PVP_PAGE_DRAFT)
            self.assertIs(workspace.stack.currentWidget(), workspace.draft_workspace)
            self.assertIs(host.stack.currentWidget(), host.draft_panel)
            self.assertFalse(workspace.draft_workspace.empty_frame.isHidden())
            self.assertIn(
                tr("app_shell.pvp.draft.no_active_title"),
                workspace.draft_workspace.empty_title_label.text(),
            )

    def test_pvp_draft_board_renders_current_action_and_legal_targets(self) -> None:
        workspace, _panel = self._started_draft_workspace(character_count=12)

        draft = workspace.draft_workspace
        board = workspace.active_draft_session.board_dict()
        pool_entries = [
            entry
            for entry in board["unified_pool"]["entries"]
            if entry["zone"] == "pool"
        ]

        self.assertIsInstance(draft, PvpDraftWorkspace)
        self.assertIn("ban", draft.order_strip.active_action_type())
        current_visual = draft.order_strip.current_action_visual()
        self.assertEqual(current_visual["seat"], "player_1")
        self.assertIn("ban", current_visual["action_type"])
        self.assertIn(tr("app_shell.pvp.draft.player_1"), current_visual["title"])
        self.assertEqual(current_visual["border_color"], pvp_player_color("player_1"))
        self.assertEqual(current_visual["action_color"], PVP_DRAFT_BAN_ACCENT)
        self.assertEqual(
            current_visual["detail"],
            tr("app_shell.pvp.draft.turn_ban").upper(),
        )
        self.assertIsInstance(draft.character_filter_bar, CharacterFilterBar)
        self.assertEqual(
            set(draft._pool_scope_buttons),
            {"all", "player_1", "player_2"},
        )
        self.assertFalse(
            [
                frame
                for frame in draft.findChildren(QFrame)
                if frame.objectName() == "pvp_draft_zone"
            ]
        )
        self.assertIsInstance(draft.pool_grid, PixelIconGrid)
        self.assertEqual(draft.pool_grid.item_count(), len(pool_entries))
        self.assertEqual(len(draft.pool_items_by_character_id), len(pool_entries))
        self.assertFalse(draft.findChildren(QFrame, "pvp_draft_card"))
        self.assertTrue(
            all(
                item.icon_path and item.properties["hasImage"]
                for item in draft.pool_items_by_character_id.values()
            )
        )

        draft.character_filter_bar.rarity_filters.add(4)
        draft.character_filter_bar.filters_changed.emit()
        QApplication.processEvents()
        self.assertFalse(draft.pool_items_by_character_id)

        draft.character_filter_bar.reset()
        QApplication.processEvents()
        self.assertEqual(draft.pool_grid.item_count(), len(pool_entries))
        self.assertEqual(
            len(set(draft.legal_character_ids)),
            board["progress"]["legal_target_count"],
        )
        self.assertGreater(len(draft.legal_character_ids), 0)
        self.assertIn("20000000", draft.pool_items_by_character_id)
        shared_item = draft.pool_items_by_character_id["20000000"]
        self.assertTrue(shared_item.properties["sharedOwner"])
        self.assertEqual({badge.text for badge in shared_item.badges}, {"C6"})
        self.assertEqual(
            {badge.position for badge in shared_item.badges},
            {"bottom_left", "bottom_right"},
        )
        self.assertEqual(draft.order_strip.position_count(), 22)
        self.assertEqual(draft.order_strip.active_position(), 1)
        active_visual = draft.order_strip.position_visual(1)
        self.assertEqual(active_visual["overlay_color"], PVP_DRAFT_BAN_ACCENT)
        self.assertGreater(active_visual["overlay_alpha"], 34)
        self.assertFalse(active_visual["draw_action_label"])
        pending_pick = next(
            row
            for row in draft.order_strip._positions
            if "pick" in row["action_type"]
        )
        pick_visual = draft.order_strip.position_visual(pending_pick["number"])
        self.assertEqual(
            pick_visual["overlay_color"],
            pvp_player_color(pending_pick["seat"]),
        )
        self.assertEqual(pick_visual["overlay_alpha"], 34)
        self.assertFalse(pick_visual["draw_action_label"])
        for width in (370, 520, 620, 860, 1030, 1365):
            layout_visual = draft.order_strip.layout_visual(width)
            self.assertFalse(layout_visual["has_overlap"], width)
            self.assertGreaterEqual(layout_visual["height"], PVP_DRAFT_ORDER_SLOT_SIZE)
            for rect in layout_visual["position_rects"]:
                self.assertEqual(rect.width(), PVP_DRAFT_ORDER_SLOT_SIZE)
                self.assertEqual(rect.height(), PVP_DRAFT_ORDER_SLOT_SIZE)
                self.assertFalse(
                    rect.intersects(layout_visual["turn_rect"]),
                    (width, rect, layout_visual["turn_rect"]),
                )
            if width >= 520:
                turn_rect = layout_visual["turn_rect"]
                side_slots = [
                    rect
                    for rect in layout_visual["position_rects"]
                    if rect.top() <= turn_rect.bottom() and rect.bottom() >= turn_rect.top()
                ]
                self.assertTrue(
                    any(rect.right() < turn_rect.left() for rect in side_slots),
                    (width, turn_rect, side_slots),
                )
                self.assertTrue(
                    any(rect.left() > turn_rect.right() for rect in side_slots),
                    (width, turn_rect, side_slots),
                )
            if width >= 1030:
                row_count = len({rect.y() for rect in layout_visual["position_rects"]})
                self.assertLessEqual(row_count, 3, width)

        draft_panel = PvpDraftRightPanel(workspace)
        QApplication.processEvents()
        self.assertTrue(draft_panel.title_label.isHidden())
        self.assertTrue(draft_panel.action_frame.isHidden())

    def test_pvp_draft_legal_click_applies_one_backend_action(self) -> None:
        workspace, _panel = self._started_draft_workspace(character_count=12)
        draft = workspace.draft_workspace
        first_legal = draft.legal_character_ids[0]
        pool_grid = draft.pool_grid

        self.assertTrue(draft.click_legal_character_for_test(first_legal))
        QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(len(board["action_log"]), 1)
        self.assertEqual(board["progress"]["actions_accepted"], 1)
        self.assertIs(draft.pool_grid, pool_grid)
        self.assertEqual(workspace.last_draft_status(), "")

    def test_pvp_draft_illegal_click_does_not_apply_action(self) -> None:
        workspace, _panel = self._started_draft_workspace(character_count=12)
        before = len(workspace.active_draft_session.board_dict()["action_log"])

        self.assertFalse(
            workspace.apply_draft_card_click(
                {
                    "type": "ban_character",
                    "target_type": "character",
                    "character_id": "not_a_legal_entry",
                }
            )
        )
        QApplication.processEvents()

        self.assertEqual(
            len(workspace.active_draft_session.board_dict()["action_log"]),
            before,
        )

    def test_pvp_draft_result_entries_leave_main_pool_and_right_panel_zones_update(self) -> None:
        workspace, _panel = self._started_draft_workspace(character_count=12)
        draft_panel = PvpDraftRightPanel(workspace)
        banned_id = workspace.draft_workspace.legal_character_ids[0]
        banned_grid = draft_panel.result_zone_widgets[("player_1", "banned")].grid

        self.assertTrue(workspace.draft_workspace.click_legal_character_for_test(banned_id))
        QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(len(board["action_log"]), 1)
        self.assertNotIn(banned_id, workspace.draft_workspace.pool_items_by_character_id)
        self.assertIn(
            banned_id,
            board["unified_pool"]["result_zones"]["player_1"]["banned"],
        )
        banned_zone = draft_panel.result_zone_widgets[("player_1", "banned")]
        picked_zone = draft_panel.result_zone_widgets[("player_1", "picked")]
        self.assertIn(banned_id, banned_zone.items_by_character_id)
        self.assertTrue(banned_zone.items_by_character_id[banned_id].icon_path)
        self.assertFalse(banned_zone.items_by_character_id[banned_id].badges)
        self.assertFalse(picked_zone.items_by_character_id)
        self.assertIsInstance(banned_zone.grid, PixelIconGrid)
        self.assertIs(banned_zone.grid, banned_grid)
        self.assertTrue(draft_panel.log_labels[0].isHidden())
        self.assertFalse(draft_panel.findChildren(QLabel, "pvp_draft_result_picks"))
        self.assertFalse(draft_panel.findChildren(QLabel, "pvp_draft_result_bans"))

    def test_pvp_draft_same_deck_self_vs_self_keeps_seat_state_independent(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )

        initial_entries = workspace.active_draft_session.board_dict()["unified_pool"]["entries"]
        self.assertEqual(len(workspace.draft_workspace.pool_items_by_character_id), 24)
        self.assertEqual(
            sum(1 for entry in initial_entries if entry["character_id"] == "20000000"),
            1,
        )
        self.assertTrue(
            workspace.draft_workspace.pool_items_by_character_id["20000000"].properties[
                "sharedOwner"
            ]
        )

        while len(workspace.active_draft_session.board_dict()["action_log"]) < 5:
            workspace.draft_workspace.click_legal_character_for_test()
            QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        pick = board["action_log"][-1]
        self.assertEqual(pick["action_type"], "pick_character")
        picked_id = pick["target_id"]
        p1_card = _board_card(board, "player_1", picked_id)
        p2_card = _board_card(board, "player_2", picked_id)

        self.assertEqual(p1_card["status"], "picked_by_self")
        self.assertEqual(p2_card["status"], "blocked_by_opponent_pick")
        self.assertEqual(_board_entry(board, picked_id)["zone"], "picked")

    def test_pvp_draft_can_complete_full_schedule_through_ui_clicks(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        draft_panel = PvpDraftRightPanel(workspace)
        guard = 0

        while not workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
            guard += 1
            self.assertLess(guard, 40)
            self.assertTrue(workspace.draft_workspace.legal_character_ids)
            workspace.draft_workspace.click_legal_character_for_test()
            QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(board["progress"]["actions_accepted"], 22)
        self.assertEqual(len(board["action_log"]), 22)
        self.assertTrue(board["status"]["draft_finished"])
        self.assertFalse(workspace.draft_workspace.legal_character_ids)
        self.assertTrue(
            all(
                not item.properties["legalTarget"]
                for item in workspace.draft_workspace.pool_items_by_character_id.values()
            )
        )
        self.assertTrue(
            draft_panel.result_zone_widgets[("player_1", "picked")].items_by_character_id
        )
        self.assertTrue(
            draft_panel.result_zone_widgets[("player_2", "picked")].items_by_character_id
        )
        self.assertEqual(workspace.draft_workspace.order_strip.position_count(), 22)
        self.assertEqual(workspace.draft_workspace.order_strip.active_position(), 0)
        self.assertFalse(draft_panel.status_frame.isVisible())

    def test_pvp_post_draft_full_local_flow_reaches_result_summary(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        draft_panel = PvpDraftRightPanel(workspace)
        self._complete_draft(workspace)

        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_DRAFT)
        self.assertFalse(draft_panel.stage_button.isHidden())
        self.assertTrue(draft_panel.stage_button.isEnabled())

        draft_panel.stage_button.click()
        QApplication.processEvents()

        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_ASSIGNMENT)
        board = workspace.active_draft_session.board_dict()
        self.assertEqual(
            set(workspace.draft_workspace.source_zone_frames_by_seat),
            {"player_1", "player_2"},
        )
        self.assertEqual(
            set(draft_panel.target_zone_frames_by_seat),
            {"player_1", "player_2"},
        )
        self.assertFalse(
            workspace.draft_workspace.findChildren(QPushButton, "pvp-picked-character-tile")
        )
        self.assertFalse(
            workspace.draft_workspace.findChildren(QPushButton, "pvp-weapon-tile")
        )
        self.assertFalse(
            draft_panel.findChildren(QPushButton, "pvp-team-slot")
        )
        self.assertTrue(draft_panel.stage_button.isHidden())
        self.assertTrue(draft_panel.clear_button.isHidden())
        self.assertTrue(draft_panel.play_button.isHidden())
        self.assertTrue(draft_panel.status_frame.isHidden())
        self.assertEqual(len(draft_panel.team_slot_buttons_by_key), 16)
        self.assertIsInstance(
            draft_panel.postdraft_run_panels_by_seat["player_1"],
            PvpPostDraftRunPanel,
        )
        self.assertFalse(draft_panel.postdraft_run_panels_by_seat["player_2"].isVisible())
        self.assertEqual(len(draft_panel.findChildren(RightPanelTeamCardWidget)), 4)
        self.assertEqual(len(draft_panel.findChildren(RightPanelSlotCardWidget)), 16)
        self.assertFalse(draft_panel.findChildren(QPushButton, "row_cancel_button"))
        self.assertFalse(draft_panel.findChildren(QFrame, "pvp-team-slot"))
        self.assertFalse(draft_panel.findChildren(QFrame, "pvp-team-half"))
        self.assertFalse(draft_panel.findChildren(QFrame, "pvp-timer-area"))
        self.assertFalse(hasattr(draft_panel, "timer_inputs_by_key"))
        for seat, zone in draft_panel.target_zone_frames_by_seat.items():
            self.assertIsInstance(zone, PvpPostDraftSeatFrame)
            self.assertEqual(len(zone.findChildren(RightPanelTeamCardWidget)), 2, seat)
        player_1_zone = draft_panel.target_zone_frames_by_seat["player_1"]
        player_2_zone = draft_panel.target_zone_frames_by_seat["player_2"]
        player_1_index = draft_panel.match_layout.indexOf(player_1_zone)
        player_2_index = draft_panel.match_layout.indexOf(player_2_zone)
        self.assertEqual(draft_panel.match_layout.stretch(player_1_index), 1)
        self.assertEqual(draft_panel.match_layout.stretch(player_2_index), 0)
        draft_panel.resize(660, 520)
        draft_panel.show()
        QApplication.processEvents()
        p1_panel = draft_panel.postdraft_run_panels_by_seat["player_1"]
        self.assertGreaterEqual(player_1_zone.minimumHeight(), 540)
        self.assertGreaterEqual(p1_panel.minimumHeight(), 470)
        self.assertGreaterEqual(p1_panel.height(), 300)
        self.assertTrue(
            all(row.isHidden() for row in draft_panel.result_zone_rows_by_seat.values())
        )
        self.assertGreaterEqual(draft_panel.match_scroll.viewport().height(), 430)
        slot_bottom = max(
            slot.mapTo(draft_panel.match_frame, QPoint(0, 0)).y() + slot.height()
            for slot in p1_panel.slot_widgets()
        )
        self.assertLessEqual(slot_bottom, draft_panel.match_scroll.viewport().height())
        self.assertLessEqual(
            draft_panel.match_frame.width(),
            draft_panel.match_scroll.viewport().width(),
        )
        self.assertEqual(player_1_zone.x(), 0)
        workspace.toggle_build_seat_collapsed("player_1")
        QApplication.processEvents()
        self.assertLessEqual(
            draft_panel.match_frame.width(),
            draft_panel.match_scroll.viewport().width(),
        )
        self.assertTrue(
            all(
                zone.maximumHeight() < 100
                for zone in draft_panel.target_zone_frames_by_seat.values()
            )
        )
        workspace.toggle_build_seat_collapsed("player_1")
        QApplication.processEvents()
        self.assertGreaterEqual(player_1_zone.minimumHeight(), 540)
        self.assertGreaterEqual(
            draft_panel.postdraft_run_panels_by_seat["player_1"].minimumHeight(),
            470,
        )
        draft_panel.hide()
        for seat in ("player_1", "player_2"):
            source_zone = workspace.draft_workspace.source_zone_frames_by_seat[seat]
            self.assertIsInstance(source_zone, PvpSeatAccentFrame)
            scoped_sources = source_zone.findChildren(PvpScopedCharacterWeaponWorkspace)
            self.assertEqual(len(scoped_sources), 1, seat)
            source = workspace.build_source_workspace(seat)
            self.assertIsInstance(source, PvpScopedCharacterWeaponWorkspace)
            character_grid = source.char_grid
            weapon_grid = source.weapon_grid
            picks = board["unified_pool"]["result_zones"][seat]["picked"]
            self.assertEqual(character_grid.item_count(), 8)
            self.assertEqual(set(character_grid.item_ids()), set(picks))
            self.assertGreater(weapon_grid.item_count(), 0)
        self.assertFalse(
            hasattr(workspace.draft_workspace, "source_character_grids_by_seat")
        )
        self.assertFalse(
            hasattr(workspace.draft_workspace, "source_weapon_grids_by_seat")
        )
        self.assertFalse(workspace.assignment_ready())

        first_p1 = board["unified_pool"]["result_zones"]["player_1"]["picked"][0]
        p1_source = workspace.build_source_workspace("player_1")
        self.assertTrue(p1_source.char_grid.click_item_for_test(first_p1))
        QApplication.processEvents()
        p1_context = workspace.build_flow_context.seat("player_1")
        self.assertEqual(
            p1_context.controller.state.team(0).slot(0).character.id,
            first_p1,
        )
        marker = p1_context.controller.roster_selection_markers()[first_p1]
        self.assertEqual((marker.team_index, marker.slot_number), (0, 1))
        selected_item = p1_source.char_grid.item(first_p1)
        self.assertIsNotNone(selected_item.outline)
        self.assertNotEqual(getattr(selected_item.outline, "badge_text", ""), "SEL")
        self.assertIsNone(selected_item.overlay_fill)
        assigned_slot = draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)]
        self.assertIsInstance(assigned_slot, RightPanelSlotCardWidget)
        self.assertTrue(assigned_slot.property("hasPortraitPixmap"))
        draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)].clicked.emit(0, 0)
        QApplication.processEvents()
        self.assertLess(p1_context.controller.selected_team_index, 0)

        self._assign_all_picks_to_teams(workspace)

        self.assertEqual(p1_context.filled_character_count(), 8)
        draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)].clicked.emit(0, 0)
        QApplication.processEvents()
        self.assertEqual(
            (p1_context.controller.selected_team_index, p1_context.controller.selected_slot_index),
            (0, 0),
        )
        weapon_asset = workspace.weapon_assets[0]
        self.assertTrue(workspace.handle_build_weapon_clicked("player_1", weapon_asset))
        QApplication.processEvents()
        weaponed_slot = draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)]
        self.assertTrue(weaponed_slot.property("hasWeaponPixmap"))
        self.assertFalse(
            draft_panel.findChildren(QLabel, "pvp-assigned-weapon-indicator")
        )

        self._assign_compatible_weapons(workspace)

        for seat in ("player_1", "player_2"):
            self.assertTrue(workspace.ready_build_seat(seat), seat)
            QApplication.processEvents()

        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_TIMERS_RESULTS)
        timer_widget = workspace.draft_workspace.findChild(PvpTimersResultWidget)
        self.assertIsNotNone(timer_widget)
        self.assertFalse(timer_widget.finalize_button.isEnabled())
        for index in range(3):
            self.assertTrue(
                timer_widget.set_timer_seconds_for_test("player_1", index, 540)
            )
        for index, seconds in enumerate((530, 540, 540)):
            self.assertTrue(
                timer_widget.set_timer_seconds_for_test("player_2", index, seconds)
            )
        self.assertTrue(workspace.timers_ready())
        self.assertTrue(timer_widget.finalize_button.isEnabled())
        self.assertIs(
            workspace.draft_workspace.findChild(PvpTimersResultWidget),
            timer_widget,
        )

        timer_widget.finalize_button.click()
        QApplication.processEvents()

        result = workspace.active_draft_session.controller.state.match_result
        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_COMPLETED_RESULT)
        self.assertIsNotNone(result)
        self.assertEqual(result.winner_seat, "player_1")
        self.assertEqual(result.seconds_difference, 10)
        self.assertTrue(timer_widget.finalize_button.isHidden())
        self.assertIn("10", timer_widget.difference_label.text())
        self.assertEqual(timer_widget.left_chevron.property("outcome"), "winner")
        self.assertEqual(timer_widget.right_chevron.property("outcome"), "loser")
        summary_text = "\n".join(
            label.text()
            for label in workspace.draft_workspace.findChildren(QLabel)
            if label.text()
        )
        panel_text = "\n".join(
            label.text()
            for label in draft_panel.findChildren(QLabel)
            if label.text()
        )
        self.assertIn(tr("app_shell.pvp.post.result_summary_title"), summary_text)
        self.assertIn(tr("app_shell.pvp.draft.player_1"), panel_text)
        self.assertNotIn("not run", panel_text.casefold())

    def test_pvp_scoped_quick_pick_repeated_character_does_not_duplicate(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        board = workspace.active_draft_session.board_dict()
        character_id = board["unified_pool"]["result_zones"]["player_1"]["picked"][0]
        asset = next(
            asset
            for asset in workspace.character_assets
            if _asset_character_id(asset) == character_id
        )
        seat_context = workspace.build_flow_context.seat("player_1")

        self.assertTrue(workspace.handle_build_character_clicked("player_1", asset))
        self.assertEqual(seat_context.filled_character_count(), 1)

        self.assertTrue(workspace.handle_build_character_clicked("player_1", asset))
        self.assertEqual(seat_context.filled_character_count(), 0)
        self.assertNotIn(
            character_id,
            seat_context.controller.roster_selection_markers(),
        )

    def test_pvp_runtime_weapon_state_is_isolated_and_incremental(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        portrait_path, weapon_path = _create_test_asset_images(temp_dir.name)
        characters = _valid_character_assets(24, image_path=portrait_path)
        weapons = [
            _weapon_asset(
                "11401",
                "Sword",
                weapon_type=1,
                weapon_type_name="Sword",
                known_count=24,
                image_path=weapon_path,
            )
        ]
        db_path = Path(temp_dir.name) / "pvp-runtime-state.sqlite"
        _seed_pvp_build_db(db_path, characters=characters, weapons=weapons)
        weapon_fingerprint = weapons[0]["metadata"]["weapon"]["weapon_fingerprint"]
        with closing(connect_db(db_path)) as conn:
            equip_weapon(conn, _asset_character_id(characters[0]), weapon_fingerprint)
            conn.commit()
            self.assertEqual(
                tuple(list_equipped_weapon_owners(conn, weapon_fingerprint)),
                (int(_asset_character_id(characters[0])),),
            )

        workspace = PvpWorkspace(db_path=db_path, deck_dir=temp_dir.name)
        self.assertTrue(
            any(
                weapon.get("metadata", {}).get("owner_badges")
                for weapon in workspace.weapon_assets
            )
        )
        self.assertTrue(workspace.decks_workspace.create_deck("Mirror"))
        self.assertTrue(workspace.decks_workspace.save_edit(name="Mirror"))
        play_panel = PvpPlayRightPanel(workspace)
        play_panel.start_button.click()
        QApplication.processEvents()
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        draft_panel = PvpDraftRightPanel(workspace)

        p1_source = workspace.build_source_workspace("player_1")
        p2_source = workspace.build_source_workspace("player_2")
        self.assertIsInstance(p1_source, PvpScopedCharacterWeaponWorkspace)
        self.assertIsInstance(p2_source, PvpScopedCharacterWeaponWorkspace)
        p1_weapon_item_id = p1_source.weapon_grid.item_ids()[0]
        p2_weapon_item_id = p2_source.weapon_grid.item_ids()[0]
        self.assertFalse(
            p1_source.weapon_grid.item_property(p1_weapon_item_id, "has_owner_badges")
        )
        self.assertFalse(
            p2_source.weapon_grid.item_property(p2_weapon_item_id, "has_owner_badges")
        )

        p1_run_panel = draft_panel.postdraft_run_panels_by_seat["player_1"]
        p1_zone = draft_panel.target_zone_frames_by_seat["player_1"]
        p1_source_zone = workspace.draft_workspace.source_zone_frames_by_seat["player_1"]
        scoped_source_frame = workspace.draft_workspace._scoped_build_source_frame
        p1_first_pick = workspace.active_draft_session.board_dict()["unified_pool"][
            "result_zones"
        ]["player_1"]["picked"][0]
        p1_asset = next(
            asset
            for asset in workspace.character_assets
            if _asset_character_id(asset) == p1_first_pick
        )
        with patch.object(
            p1_source,
            "reload_characters",
            wraps=p1_source.reload_characters,
        ) as reload_characters:
            self.assertTrue(p1_source.char_grid.click_item_for_test(p1_first_pick))
            QApplication.processEvents()
            self.assertEqual(reload_characters.call_count, 0)
        self.assertIs(workspace.build_source_workspace("player_1"), p1_source)
        self.assertIs(draft_panel.postdraft_run_panels_by_seat["player_1"], p1_run_panel)
        self.assertIs(draft_panel.target_zone_frames_by_seat["player_1"], p1_zone)
        self.assertIs(
            workspace.draft_workspace.source_zone_frames_by_seat["player_1"],
            p1_source_zone,
        )
        self.assertIs(workspace.draft_workspace._scoped_build_source_frame, scoped_source_frame)
        self.assertEqual(
            workspace.build_flow_context.seat("player_1")
            .controller.state.team(0)
            .slot(0)
            .character.id,
            p1_first_pick,
        )

        self.assertTrue(workspace.handle_build_weapon_clicked("player_1", weapons[0]))
        QApplication.processEvents()
        self.assertTrue(
            p1_source.weapon_grid.item_property(p1_weapon_item_id, "has_owner_badges")
        )
        self.assertFalse(
            p2_source.weapon_grid.item_property(p2_weapon_item_id, "has_owner_badges")
        )
        with closing(connect_db(db_path)) as conn:
            self.assertEqual(
                tuple(list_equipped_weapon_owners(conn, weapon_fingerprint)),
                (int(_asset_character_id(characters[0])),),
            )

        self.assertTrue(workspace.handle_build_character_clicked("player_1", p1_asset))
        QApplication.processEvents()
        self.assertIsNone(
            workspace.build_flow_context.seat("player_1")
            .controller.state.team(0)
            .slot(0)
            .character
        )
        self.assertTrue(
            p1_source.weapon_grid.item_property(p1_weapon_item_id, "has_owner_badges")
        )
        self.assertTrue(workspace.handle_build_character_clicked("player_1", p1_asset))
        QApplication.processEvents()
        restored_slot = (
            workspace.build_flow_context.seat("player_1")
            .controller.state.team(0)
            .slot(0)
        )
        self.assertIsNotNone(restored_slot.character)
        self.assertIsNotNone(restored_slot.weapon)
        self.assertTrue(
            draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)].property(
                "hasWeaponPixmap"
            )
        )

        p2_first_pick = workspace.active_draft_session.board_dict()["unified_pool"][
            "result_zones"
        ]["player_2"]["picked"][0]
        p2_asset = next(
            asset
            for asset in workspace.character_assets
            if _asset_character_id(asset) == p2_first_pick
        )
        self.assertTrue(workspace.handle_build_character_clicked("player_2", p2_asset))
        self.assertTrue(workspace.handle_build_weapon_clicked("player_2", weapons[0]))
        QApplication.processEvents()
        self.assertTrue(
            p1_source.weapon_grid.item_property(p1_weapon_item_id, "has_owner_badges")
        )
        self.assertTrue(
            p2_source.weapon_grid.item_property(p2_weapon_item_id, "has_owner_badges")
        )

    def test_pvp_postdraft_right_panel_slot_drop_swaps_slots(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        draft_panel = PvpDraftRightPanel(workspace)
        self._assign_all_picks_to_teams(workspace)
        seat_context = workspace.build_flow_context.seat("player_1")
        first_id = str(seat_context.controller.state.team(0).slot(0).character.id)
        second_id = str(seat_context.controller.state.team(0).slot(1).character.id)

        draft_panel.postdraft_run_panels_by_seat["player_1"].slot_dropped.emit(
            0,
            0,
            0,
            1,
        )
        QApplication.processEvents()

        self.assertEqual(
            str(seat_context.controller.state.team(0).slot(0).character.id),
            second_id,
        )
        self.assertEqual(
            str(seat_context.controller.state.team(0).slot(1).character.id),
            first_id,
        )
        markers = seat_context.controller.roster_selection_markers()
        self.assertEqual(markers[first_id].slot_number, 2)
        self.assertEqual(markers[second_id].slot_number, 1)

    def test_pvp_postdraft_source_click_refreshes_draft_panel_once(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        calls: list[str] = []
        original_refresh = PvpDraftRightPanel.refresh

        def counted_refresh(panel):
            calls.append("refresh")
            return original_refresh(panel)

        with patch.object(PvpDraftRightPanel, "refresh", counted_refresh):
            draft_panel = PvpDraftRightPanel(workspace)
            QApplication.processEvents()
            calls.clear()
            first_pick = workspace.active_draft_session.board_dict()["unified_pool"][
                "result_zones"
            ]["player_1"]["picked"][0]
            source = workspace.build_source_workspace("player_1")
            with patch.object(
                source,
                "reload_weapons",
                wraps=source.reload_weapons,
            ) as reload_weapons:
                self.assertTrue(source.char_grid.click_item_for_test(first_pick))
                self.assertEqual(reload_weapons.call_count, 0)
            QApplication.processEvents()

        self.assertEqual(calls, ["refresh"])
        self.assertIn(("player_1", 0, 0), draft_panel.team_slot_buttons_by_key)

    def test_pvp_collapsed_postdraft_seat_is_compact_full_width_toggle(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        draft_panel = PvpDraftRightPanel(workspace)
        self.assertTrue(
            draft_panel.match_layout.alignment() & Qt.AlignmentFlag.AlignTop
        )

        p1_zone = draft_panel.target_zone_frames_by_seat["player_1"]
        p2_zone = draft_panel.target_zone_frames_by_seat["player_2"]
        p2_toggle = draft_panel.postdraft_toggle_buttons_by_seat["player_2"]

        self.assertLessEqual(p2_zone.maximumHeight(), p2_toggle.sizeHint().height() + 14)
        self.assertGreater(p1_zone.maximumHeight(), p1_zone.minimumHeight())
        self.assertEqual(
            p2_toggle.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Expanding,
        )

        workspace.toggle_build_seat_collapsed("player_1")
        QApplication.processEvents()
        self.assertLessEqual(
            draft_panel.target_zone_frames_by_seat["player_1"].maximumHeight(),
            draft_panel.postdraft_toggle_buttons_by_seat["player_1"].sizeHint().height()
            + 14,
        )

    def test_pvp_runtime_weapon_state_matches_allowed_key_from_numeric_type(self) -> None:
        weapon = _weapon_asset(
            "11401",
            "Localized Sword",
            weapon_type=1,
            weapon_type_name="Локализованный меч",
            known_count=1,
        )
        allowed_key = "11401|sword|4|90|5"
        state = PvpRuntimeEquipmentState.from_assets(
            seat="player_1",
            allowed_character_ids=("20000000",),
            allowed_weapon_keys=(allowed_key,),
            weapon_assets=(weapon,),
        )

        _result, persisted_weapon = state.assign_weapon_to_character(
            "20000000",
            {"id": "20000000", "name": "Sword User", "weapon_type": 1},
            weapon["metadata"]["weapon"],
        )

        self.assertIsNotNone(persisted_weapon)
        self.assertEqual(persisted_weapon["pvp_weapon_stack_key"], allowed_key)

    def test_pvp_ready_uses_scoped_weapon_stack_key_not_display_type(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        session = workspace.active_draft_session
        stack_key = session.controller.session_state.deck_for("player_1").weapons[0].stack_key
        weapon_meta = workspace.weapon_assets[0]["metadata"]["weapon"]
        weapon_meta["source_key"] = stack_key
        weapon_meta["weapon_fingerprint"] = ""
        weapon_meta["weapon_type_name"] = "Sword Display"
        weapon_meta["type_name"] = "Sword Display"

        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        self._assign_all_picks_to_teams(workspace)
        for seat in ("player_1", "player_2"):
            for team_index in range(2):
                for slot_index in range(4):
                    workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                    self.assertTrue(
                        workspace.handle_build_weapon_clicked(
                            seat,
                            workspace.weapon_assets[0],
                        ),
                        (seat, team_index, slot_index),
                    )
            self.assertTrue(workspace.ready_build_seat(seat), workspace.last_draft_status())
            self.assertNotIn("weapon_type_mismatch", workspace.last_draft_status())

    def test_pvp_ready_accepts_localized_character_weapon_type(self) -> None:
        characters = [
            _character_asset(
                str(20000000 + index),
                f"Claymore Char {index}",
                weapon_type=11,
                weapon_type_name="Двуручный меч",
                rarity=5,
            )
            for index in range(24)
        ]
        weapons = [
            _weapon_asset(
                "12401",
                "Favonius Greatsword",
                weapon_type=11,
                weapon_type_name="Claymore",
                known_count=24,
            )
        ]
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
            characters=characters,
            weapons=weapons,
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        self._assign_all_picks_to_teams(workspace)

        for seat in ("player_1", "player_2"):
            for team_index in range(2):
                for slot_index in range(4):
                    workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                    self.assertTrue(
                        workspace.handle_build_weapon_clicked(
                            seat,
                            workspace.weapon_assets[0],
                        ),
                        (seat, team_index, slot_index),
                    )
            self.assertTrue(workspace.ready_build_seat(seat), workspace.last_draft_status())
            self.assertNotIn("weapon_type_mismatch", workspace.last_draft_status())

    def test_pvp_ready_accepts_russian_bow_display_weapon_type(self) -> None:
        characters = [
            _character_asset(
                str(20000000 + index),
                f"Bow Char {index}",
                weapon_type=12,
                weapon_type_name="Bow",
                rarity=5,
            )
            for index in range(24)
        ]
        weapons = [
            _weapon_asset(
                "15508",
                "Aqua Simulacra",
                weapon_type=12,
                weapon_type_name="\u0421\u0442\u0440\u0435\u043b\u043a\u043e\u0432\u043e\u0435",
                known_count=24,
            )
        ]
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
            characters=characters,
            weapons=weapons,
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        self._assign_all_picks_to_teams(workspace)

        for seat in ("player_1", "player_2"):
            for team_index in range(2):
                for slot_index in range(4):
                    workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                    self.assertTrue(
                        workspace.handle_build_weapon_clicked(
                            seat,
                            workspace.weapon_assets[0],
                        ),
                        (seat, team_index, slot_index),
                    )
            self.assertTrue(workspace.ready_build_seat(seat), workspace.last_draft_status())
            self.assertNotIn("weapon_type_mismatch", workspace.last_draft_status())

    def test_pvp_weapon_stage_rejects_incompatible_and_exhausted_stack(self) -> None:
        weapons = [
            _weapon_asset(
                "11401",
                "One Sword",
                weapon_type=1,
                weapon_type_name="Sword",
                known_count=1,
            ),
            _weapon_asset(
                "15401",
                "Wrong Bow",
                weapon_type=12,
                weapon_type_name="Bow",
                known_count=8,
            ),
        ]
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
            weapons=weapons,
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        self._assign_all_picks_to_teams(workspace)

        board = workspace.active_draft_session.board_dict()
        first, second = board["unified_pool"]["result_zones"]["player_1"]["picked"][:2]
        deck = workspace.active_draft_session.controller.session_state.deck_for("player_1")
        sword_stack = next(
            stack for stack in deck.weapons if _weapon_types_match(1, stack.weapon_type)
        )
        _bow_stack = next(
            stack for stack in deck.weapons if _weapon_types_match(12, stack.weapon_type)
        )
        sword_asset = next(
            asset
            for asset in workspace.weapon_assets
            if asset["metadata"]["weapon"]["weapon_type_name"] == "Sword"
        )
        bow_asset = next(
            asset
            for asset in workspace.weapon_assets
            if asset["metadata"]["weapon"]["weapon_type_name"] == "Bow"
        )
        seat_context = workspace.build_flow_context.seat("player_1")

        workspace.handle_build_slot_clicked("player_1", 0, 0)
        self.assertFalse(workspace.handle_build_weapon_clicked("player_1", bow_asset))
        self.assertIsNone(seat_context.controller.state.team(0).slot(0).weapon)

        self.assertTrue(workspace.handle_build_weapon_clicked("player_1", sword_asset))
        self.assertEqual(
            seat_context.weapon_assignment().assignments[0].weapon_stack_key,
            sword_stack.stack_key,
        )
        workspace.handle_build_slot_clicked("player_1", 0, 1)
        self.assertTrue(workspace.handle_build_weapon_clicked("player_1", sword_asset))
        self.assertIsNone(seat_context.controller.state.team(0).slot(0).weapon)
        self.assertIsNotNone(seat_context.controller.state.team(0).slot(1).weapon)
        self.assertEqual(len(seat_context.weapon_assignment().assignments), 1)
        self.assertFalse(workspace.weapons_ready())

    def test_pvp_clear_active_draft_resets_post_draft_state(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        board = workspace.active_draft_session.board_dict()
        character_id = board["unified_pool"]["result_zones"]["player_1"]["picked"][0]
        asset = next(
            asset
            for asset in workspace.character_assets
            if _asset_character_id(asset) == character_id
        )
        self.assertTrue(workspace.handle_build_character_clicked("player_1", asset))
        self.assertIsNotNone(workspace.build_flow_context)
        workspace.set_timer_text("player_1", 0, "09:00")

        workspace.clear_active_draft()

        self.assertIsNone(workspace.active_draft_session)
        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_DRAFT)
        self.assertIsNone(workspace.build_flow_context)
        self.assertFalse(hasattr(workspace, "assignment_slots_by_seat"))
        self.assertFalse(hasattr(workspace, "weapon_assignments_by_seat"))
        self.assertEqual(workspace.timer_texts_by_seat["player_1"], ["", "", ""])

    def test_imported_profile_drives_player_2_scoped_build_provider(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        portrait_path, weapon_path = _create_test_asset_images(temp_dir.name)
        characters = _valid_character_assets(24, image_path=portrait_path)
        weapons = [
            _weapon_asset(
                "11401",
                "Sword",
                weapon_type=1,
                weapon_type_name="Sword",
                known_count=24,
                image_path=weapon_path,
            )
        ]
        db_path = Path(temp_dir.name) / "local.sqlite"
        _seed_pvp_build_db(db_path, characters=characters, weapons=weapons)
        weapon_fingerprint = weapons[0]["metadata"]["weapon"]["weapon_fingerprint"]
        with closing(connect_db(db_path)) as conn:
            equip_weapon(conn, _asset_character_id(characters[0]), weapon_fingerprint)
            conn.commit()
        workspace = PvpWorkspace(
            db_path=db_path,
            deck_dir=temp_dir.name,
            character_assets_provider=lambda: characters,
            weapon_assets_provider=lambda: weapons,
        )
        self.assertTrue(workspace.decks_workspace.create_deck("Local"))
        self.assertTrue(workspace.decks_workspace.save_edit(name="Local"))
        package_path = Path(temp_dir.name) / "remote.gttpvp"
        self.assertTrue(workspace.decks_workspace.export_profile(package_path))

        self.assertTrue(
            workspace.import_profile_for_seat("player_2", package_path)
        )
        self.assertTrue(workspace.seat_profile_is_imported("player_2"))
        self.assertEqual(
            [preset.name for preset in workspace.play_deck_options("player_2")],
            ["Local"],
        )
        self.assertTrue(
            any(
                asset.get("metadata", {}).get("owner_badges")
                for asset in workspace._profile_assets("player_2")[1]
            )
        )
        play_panel = PvpPlayRightPanel(workspace)
        self.assertFalse(play_panel.player_2_local_button.isHidden())
        self.assertIn("remote", play_panel.player_2_label.text())

        deck_id = workspace.decks_workspace.presets[0].deck_id
        self.assertTrue(workspace.start_local_draft(deck_id, deck_id))
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        player_2_source = workspace.build_source_workspace("player_2")
        player_2_weapon_item_id = player_2_source.weapon_grid.item_ids()[0]
        self.assertFalse(
            player_2_source.weapon_grid.item_property(
                player_2_weapon_item_id,
                "has_owner_badges",
            )
        )
        imported_provider = workspace.seat_profile_provider("player_2")
        self.assertIs(
            workspace.build_flow_context.seat("player_2").provider,
            imported_provider,
        )
        self.assertNotEqual(
            workspace.build_flow_context.seat("player_2").db_path,
            db_path,
        )

        workspace.clear_active_draft()
        imported_db_path = Path(imported_provider.db_path)
        self.assertTrue(imported_db_path.exists())
        workspace.use_local_profile_for_seat("player_2")
        self.assertFalse(imported_db_path.exists())
        self.assertFalse(workspace.seat_profile_is_imported("player_2"))

    def test_pvp_right_panel_host_switches_decks_and_play_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PvpWorkspace(
                deck_dir=temp_dir,
                character_assets_provider=lambda: [],
                weapon_assets_provider=lambda: [],
            )
            host = PvpRightPanelHost(workspace)

            self.assertEqual(host.current_page(), PVP_PAGE_DECKS)
            self.assertIs(host.stack.currentWidget(), host.decks_panel)

            host.set_page(PVP_PAGE_PLAY)

            self.assertEqual(workspace.active_page_id, PVP_PAGE_PLAY)
            self.assertIs(workspace.stack.currentWidget(), workspace.play_workspace)
            self.assertIs(host.stack.currentWidget(), host.play_panel)

            host.set_page(PVP_PAGE_DRAFT)

            self.assertEqual(workspace.active_page_id, PVP_PAGE_DRAFT)
            self.assertIs(workspace.stack.currentWidget(), workspace.draft_workspace)
            self.assertIs(host.stack.currentWidget(), host.draft_panel)

            host.set_page(PVP_PAGE_DECKS)

            self.assertIs(workspace.stack.currentWidget(), workspace.decks_workspace)
            self.assertIs(host.stack.currentWidget(), host.decks_panel)


    def _started_draft_workspace(
        self,
        *,
        character_count: int,
        deck_names: tuple[str, ...] = ("Alpha", "Beta"),
        characters: list[dict] | None = None,
        weapons: list[dict] | None = None,
    ) -> tuple[PvpWorkspace, PvpPlayRightPanel]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        portrait_path, weapon_path = _create_test_asset_images(temp_dir.name)
        characters = characters or _valid_character_assets(
            character_count,
            image_path=portrait_path,
        )
        weapons = _with_weapon_image_paths(
            weapons or [
                _weapon_asset(
                    "11401",
                    "Sword",
                    weapon_type=1,
                    weapon_type_name="Sword",
                    known_count=24,
                    image_path=weapon_path,
                )
            ],
            weapon_path,
        )
        db_path = Path(temp_dir.name) / "pvp-build.sqlite"
        _seed_pvp_build_db(db_path, characters=characters, weapons=weapons)
        workspace = PvpWorkspace(
            db_path=db_path,
            deck_dir=temp_dir.name,
            character_assets_provider=lambda: characters,
            weapon_assets_provider=lambda: weapons,
        )
        for name in deck_names:
            self.assertTrue(workspace.decks_workspace.create_deck(name))
            self.assertTrue(workspace.decks_workspace.save_edit(name=name))
        panel = PvpPlayRightPanel(workspace)
        if len(deck_names) > 1:
            index = panel.player_2_combo.findText(deck_names[1])
            panel.player_2_combo.setCurrentIndex(index)
        panel.start_button.click()
        QApplication.processEvents()
        self.assertIsNotNone(workspace.active_draft_session)
        self.assertEqual(workspace.active_page_id, PVP_PAGE_DRAFT)
        self.assertIs(workspace.stack.currentWidget(), workspace.draft_workspace)
        return workspace, panel

    def _complete_draft(self, workspace: PvpWorkspace) -> None:
        guard = 0
        while not workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
            guard += 1
            self.assertLess(guard, 40)
            self.assertTrue(workspace.draft_workspace.legal_character_ids)
            workspace.draft_workspace.click_legal_character_for_test()
            QApplication.processEvents()

    def _assign_all_picks_to_teams(self, workspace: PvpWorkspace) -> None:
        board = workspace.active_draft_session.board_dict()
        assets_by_id = {
            _asset_character_id(asset): asset
            for asset in workspace.character_assets
        }
        for seat in ("player_1", "player_2"):
            seat_context = workspace.build_flow_context.seat(seat)
            picks = board["unified_pool"]["result_zones"][seat]["picked"]
            self.assertEqual(len(picks), 8)
            for character_id in picks:
                if character_id in seat_context.controller.roster_selection_markers():
                    continue
                self.assertTrue(
                    workspace.handle_build_character_clicked(
                        seat,
                        assets_by_id[character_id],
                    ),
                    (seat, character_id),
                )
        QApplication.processEvents()

    def _assign_compatible_weapons(self, workspace: PvpWorkspace) -> None:
        session = workspace.active_draft_session
        self.assertIsNotNone(session)
        assets_by_stack_key = {}
        for asset in workspace.weapon_assets:
            for stack_key in _asset_weapon_keys(asset):
                assets_by_stack_key[stack_key] = asset
        for seat in ("player_1", "player_2"):
            seat_context = workspace.build_flow_context.seat(seat)
            deck = session.controller.session_state.deck_for(seat)
            character_by_id = deck.character_by_id
            for team_index, team in enumerate(seat_context.controller.state.teams[:2]):
                for slot_index, slot in enumerate(team.slots[:4]):
                    if slot.character is None or slot.weapon is not None:
                        continue
                    character_id = str(slot.character.id)
                    weapon_type = character_by_id[character_id].weapon_type
                    stack = next(
                        stack
                        for stack in deck.weapons
                        if _weapon_types_match(stack.weapon_type, weapon_type)
                    )
                    workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                    self.assertTrue(
                        workspace.handle_build_weapon_clicked(
                            seat,
                            assets_by_stack_key[stack.stack_key],
                        ),
                        (seat, character_id, stack.stack_key),
                    )
        QApplication.processEvents()

    @staticmethod
    def _send_key(widget, key: Qt.Key) -> None:
        QApplication.sendEvent(
            widget,
            QKeyEvent(
                QEvent.Type.KeyPress,
                key,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        QApplication.processEvents()


_WEAPON_TYPE_BY_ID = {
    "1": "sword",
    "10": "catalyst",
    "11": "claymore",
    "12": "bow",
    "13": "polearm",
}
_WEAPON_TYPE_ALIASES = {
    "sword": "sword",
    "one_handed_sword": "sword",
    "одноручный_меч": "sword",
    "одноручное": "sword",
    "claymore": "claymore",
    "двуручный_меч": "claymore",
    "двуручное": "claymore",
    "bow": "bow",
    "лук": "bow",
    "стрелковое": "bow",
    "catalyst": "catalyst",
    "катализатор": "catalyst",
    "polearm": "polearm",
    "древковое": "polearm",
    "копье": "polearm",
    "копьё": "polearm",
}


def _weapon_types_match(left: object, right: object) -> bool:
    left_key = _canonical_weapon_type(left)
    right_key = _canonical_weapon_type(right)
    if left_key and right_key:
        return left_key == right_key
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _canonical_weapon_type(value: object) -> str:
    raw = str(value or "").strip()
    if raw in _WEAPON_TYPE_BY_ID:
        return _WEAPON_TYPE_BY_ID[raw]
    token = raw.casefold().replace("-", "_").replace(" ", "_")
    while "__" in token:
        token = token.replace("__", "_")
    return _WEAPON_TYPE_ALIASES.get(token, "")


def _character_asset(
    character_id: str,
    name: str,
    *,
    weapon_type: int = 13,
    weapon_type_name: str = "Polearm",
    rarity: int = 4,
    image_path: str = "portrait.png",
) -> dict:
    return {
        "path": image_path,
        "filename": "portrait.png",
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "level": 90,
                "rarity": rarity,
                "constellation": 6,
                "element": "Pyro",
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "portrait_path": image_path,
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
    known_count: int = 1,
    weapon_fingerprint: str | None = None,
    image_path: str = "weapon.png",
) -> dict:
    fingerprint = weapon_fingerprint or f"fingerprint-{weapon_id}"
    return {
        "path": image_path,
        "filename": "weapon.png",
        "metadata": {
            "known_count": known_count,
            "weapon": {
                "id": weapon_id,
                "name": name,
                "level": 90,
                "rarity": rarity,
                "refinement": 5,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "type_name": weapon_type_name,
                "icon_path": image_path,
                "source_key": fingerprint,
                "weapon_fingerprint": fingerprint,
                "known_count": known_count,
            }
        },
    }


def _valid_character_assets(count: int = 11, *, image_path: str = "portrait.png") -> list[dict]:
    return [
        _character_asset(
            str(20000000 + index),
            f"Char {index}",
            weapon_type=1,
            weapon_type_name="Sword",
            rarity=5,
            image_path=image_path,
        )
        for index in range(count)
    ]


def _create_test_asset_images(directory: str) -> tuple[str, str]:
    portrait_path = f"{directory}\\portrait.png"
    weapon_path = f"{directory}\\weapon.png"
    portrait = QPixmap(16, 16)
    portrait.fill(QColor("#c96b4f"))
    if not portrait.save(portrait_path):
        raise AssertionError("Failed to create portrait fixture image")
    weapon = QPixmap(16, 16)
    weapon.fill(QColor("#6b9bd2"))
    if not weapon.save(weapon_path):
        raise AssertionError("Failed to create weapon fixture image")
    return portrait_path, weapon_path


def _with_weapon_image_paths(weapons: list[dict], image_path: str) -> list[dict]:
    updated: list[dict] = []
    for weapon in weapons:
        item = dict(weapon)
        metadata = dict(item.get("metadata") or {})
        weapon_meta = dict(metadata.get("weapon") or {})
        item["path"] = image_path
        weapon_meta["icon_path"] = image_path
        metadata["weapon"] = weapon_meta
        item["metadata"] = metadata
        updated.append(item)
    return updated


def _seed_pvp_build_db(
    db_path: Path,
    *,
    characters: list[dict],
    weapons: list[dict],
) -> None:
    with closing(connect_db(db_path)) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO account_characters (
                character_id,
                name,
                element,
                rarity,
                level,
                constellation,
                weapon_type,
                weapon_type_name,
                portrait_path,
                side_icon_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(_asset_character_id(character)),
                    character["metadata"]["character"]["name"],
                    character["metadata"]["character"].get("element") or "",
                    int(character["metadata"]["character"].get("rarity") or 0),
                    int(character["metadata"]["character"].get("level") or 0),
                    int(character["metadata"]["character"].get("constellation") or 0),
                    int(character["metadata"]["character"].get("weapon_type") or 0),
                    character["metadata"]["character"].get("weapon_type_name") or "",
                    str(character.get("path") or ""),
                    str(character.get("path") or ""),
                )
                for character in characters
            ],
        )
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
                (
                    weapon["metadata"]["weapon"].get("weapon_fingerprint")
                    or weapon["metadata"]["weapon"].get("source_key"),
                    int(weapon["metadata"]["weapon"].get("id") or 0),
                    weapon["metadata"]["weapon"].get("name") or "",
                    int(weapon["metadata"]["weapon"].get("weapon_type") or 0),
                    weapon["metadata"]["weapon"].get("weapon_type_name") or "",
                    int(weapon["metadata"]["weapon"].get("rarity") or 0),
                    int(weapon["metadata"]["weapon"].get("level") or 0),
                    int(weapon["metadata"]["weapon"].get("refinement") or 0),
                    weapon["metadata"]["weapon"].get("icon_path") or "",
                    int(weapon["metadata"].get("known_count") or 1),
                )
                for weapon in weapons
            ],
        )
        conn.commit()


def _asset_character_id(asset: dict) -> str:
    return str(asset.get("metadata", {}).get("character", {}).get("id") or "").strip()


def _board_card(board: dict, seat: str, character_id: str) -> dict:
    for card in board["seats"][seat]["cards"]:
        if card["character_id"] == character_id:
            return card
    raise AssertionError(f"Missing card {seat}/{character_id}")


def _board_entry(board: dict, character_id: str) -> dict:
    for entry in board["unified_pool"]["entries"]:
        if entry["character_id"] == character_id:
            return entry
    raise AssertionError(f"Missing unified entry {character_id}")
