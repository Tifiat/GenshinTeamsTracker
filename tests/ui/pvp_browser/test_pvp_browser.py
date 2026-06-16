from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from localization import tr
from ui.pvp_browser.window import PvpDecksWorkspace, PvpDraftWorkspace, PvpWorkspace
from ui.right_panel.pvp._shared import (
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_PAGE_DECKS,
    PVP_PAGE_DRAFT,
    PVP_PAGE_PLAY,
)
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.right_panel.common.team_card import RightPanelTeamCardWidget
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from ui.right_panel.pvp.draft.pick_ban.result_zone import PvpDraftResultChipWidget
from ui.right_panel.pvp.host import PvpRightPanelHost
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.utils.pixel_icon_grid import PixelIconGrid


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
        self.assertIn(tr("app_shell.pvp.draft.ban"), draft.action_title_label.text())
        self.assertFalse(
            [
                frame
                for frame in draft.findChildren(QFrame)
                if frame.objectName() == "pvp_draft_zone"
            ]
        )
        self.assertEqual(len(draft.card_buttons_by_character_id), len(pool_entries))
        self.assertFalse(draft.findChildren(QPushButton, "pvp_draft_card"))
        self.assertGreaterEqual(
            len(draft.findChildren(QFrame, "pvp_draft_card")),
            len(pool_entries),
        )
        self.assertTrue(
            all(
                button.property("hasPortraitPixmap")
                for button in draft.card_buttons_by_character_id.values()
            )
        )
        self.assertEqual(
            len({button.character_id for button in draft.legal_card_buttons}),
            board["progress"]["legal_target_count"],
        )
        self.assertGreater(len(draft.legal_card_buttons), 0)
        self.assertIn("20000000", draft.card_buttons_by_character_id)
        shared_button = draft.card_buttons_by_character_id["20000000"]
        self.assertTrue(shared_button.property("sharedOwner"))
        self.assertIn("P1 C6", shared_button.text())
        self.assertIn("P2 C6", shared_button.text())

    def test_pvp_draft_legal_click_applies_one_backend_action(self) -> None:
        workspace, _panel = self._started_draft_workspace(character_count=12)
        draft = workspace.draft_workspace
        first_legal = draft.legal_card_buttons[0]

        first_legal.click()
        QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(len(board["action_log"]), 1)
        self.assertEqual(board["progress"]["actions_accepted"], 1)
        self.assertIn(
            tr("app_shell.pvp.draft.action_accepted").split("{", 1)[0],
            workspace.last_draft_status(),
        )

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
        first_legal = workspace.draft_workspace.legal_card_buttons[0]
        banned_id = first_legal.character_id

        first_legal.click()
        QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(len(board["action_log"]), 1)
        self.assertNotIn(banned_id, workspace.draft_workspace.card_buttons_by_character_id)
        self.assertIn(
            banned_id,
            board["unified_pool"]["result_zones"]["player_1"]["banned"],
        )
        banned_zone = draft_panel.result_zone_widgets[("player_1", "banned")]
        picked_zone = draft_panel.result_zone_widgets[("player_1", "picked")]
        self.assertIn(banned_id, banned_zone.chips_by_character_id)
        self.assertTrue(
            banned_zone.chips_by_character_id[banned_id].property("hasPortraitPixmap")
        )
        self.assertFalse(picked_zone.chips_by_character_id)
        self.assertFalse(draft_panel.findChildren(QLabel, "pvp_draft_result_picks"))
        self.assertFalse(draft_panel.findChildren(QLabel, "pvp_draft_result_bans"))

    def test_pvp_draft_same_deck_self_vs_self_keeps_seat_state_independent(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )

        initial_entries = workspace.active_draft_session.board_dict()["unified_pool"]["entries"]
        self.assertEqual(len(workspace.draft_workspace.card_buttons_by_character_id), 24)
        self.assertEqual(
            sum(1 for entry in initial_entries if entry["character_id"] == "20000000"),
            1,
        )
        self.assertTrue(
            workspace.draft_workspace.card_buttons_by_character_id["20000000"].property(
                "sharedOwner"
            )
        )

        while len(workspace.active_draft_session.board_dict()["action_log"]) < 5:
            workspace.draft_workspace.legal_card_buttons[0].click()
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
            self.assertTrue(workspace.draft_workspace.legal_card_buttons)
            workspace.draft_workspace.legal_card_buttons[0].click()
            QApplication.processEvents()

        board = workspace.active_draft_session.board_dict()
        self.assertEqual(board["progress"]["actions_accepted"], 22)
        self.assertEqual(len(board["action_log"]), 22)
        self.assertTrue(board["status"]["draft_finished"])
        self.assertFalse(workspace.draft_workspace.legal_card_buttons)
        self.assertTrue(
            all(
                not button.property("legalTarget")
                for button in workspace.draft_workspace.card_buttons_by_character_id.values()
            )
        )
        self.assertTrue(
            draft_panel.result_zone_widgets[("player_1", "picked")].chips_by_character_id
        )
        self.assertTrue(
            draft_panel.result_zone_widgets[("player_2", "picked")].chips_by_character_id
        )
        self.assertGreater(
            len(draft_panel.findChildren(PvpDraftResultChipWidget)),
            0,
        )
        completed_text = "\n".join(
            label.text()
            for label in workspace.draft_workspace.completed_labels
            if label.text()
        )
        self.assertIn(tr("app_shell.pvp.draft.player_1"), completed_text)
        self.assertIn(tr("app_shell.pvp.draft.player_2"), completed_text)
        self.assertIn("Action log: 22", completed_text)

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
        self.assertEqual(len(draft_panel.team_slot_buttons_by_key), 16)
        self.assertEqual(len(draft_panel.findChildren(RightPanelTeamCardWidget)), 4)
        self.assertEqual(len(draft_panel.findChildren(RightPanelSlotCardWidget)), 16)
        self.assertFalse(draft_panel.findChildren(QPushButton, "row_cancel_button"))
        self.assertFalse(draft_panel.findChildren(QFrame, "pvp-team-slot"))
        self.assertFalse(draft_panel.findChildren(QFrame, "pvp-team-half"))
        for seat, zone in draft_panel.target_zone_frames_by_seat.items():
            self.assertEqual(len(zone.findChildren(RightPanelTeamCardWidget)), 2, seat)
        for seat in ("player_1", "player_2"):
            source_zone = workspace.draft_workspace.source_zone_frames_by_seat[seat]
            grids = source_zone.findChildren(PixelIconGrid)
            self.assertEqual(len(grids), 2, seat)
            character_grid = workspace.draft_workspace.source_character_grids_by_seat[seat]
            weapon_grid = workspace.draft_workspace.source_weapon_grids_by_seat[seat]
            picks = board["unified_pool"]["result_zones"][seat]["picked"]
            self.assertEqual(character_grid.item_count(), 8)
            self.assertEqual(tuple(character_grid.item_ids()), tuple(picks))
            self.assertTrue(
                all(character_grid.item_property(item_id, "hasImage") for item_id in picks)
            )
            self.assertGreater(weapon_grid.item_count(), 0)
            self.assertTrue(
                all(
                    weapon_grid.item_property(item_id, "hasImage")
                    for item_id in weapon_grid.item_ids()
                )
            )
        self.assertFalse(workspace.assignment_ready())

        first_p1 = board["unified_pool"]["result_zones"]["player_1"]["picked"][0]
        self.assertTrue(
            workspace.draft_workspace.source_character_grids_by_seat[
                "player_1"
            ].click_item_for_test(first_p1)
        )
        QApplication.processEvents()
        draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)].clicked.emit(0, 0)
        QApplication.processEvents()
        self.assertEqual(workspace.assignment_slots_by_seat["player_1"][0][0], first_p1)
        assigned_slot = draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)]
        self.assertIsInstance(assigned_slot, RightPanelSlotCardWidget)
        self.assertTrue(assigned_slot.property("hasPortraitPixmap"))

        self._assign_all_picks_to_teams(workspace)

        self.assertTrue(workspace.assignment_ready())
        self.assertTrue(draft_panel.stage_button.isEnabled())
        draft_panel.stage_button.click()
        QApplication.processEvents()

        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_WEAPONS)
        draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)].clicked.emit(0, 0)
        QApplication.processEvents()
        self.assertEqual(workspace.selected_weapon_character, ("player_1", first_p1))
        weapon_grid = workspace.draft_workspace.source_weapon_grids_by_seat["player_1"]
        enabled_weapon_ids = [
            item_id
            for item_id in weapon_grid.item_ids()
            if weapon_grid.item(item_id) is not None and weapon_grid.item(item_id).enabled
        ]
        self.assertGreater(len(enabled_weapon_ids), 0)
        self.assertTrue(weapon_grid.click_item_for_test(enabled_weapon_ids[0]))
        QApplication.processEvents()
        self.assertIn(first_p1, workspace.weapon_assignments_by_seat["player_1"])
        weaponed_slot = draft_panel.team_slot_buttons_by_key[("player_1", 0, 0)]
        self.assertTrue(weaponed_slot.property("hasWeaponPixmap"))
        self.assertFalse(
            draft_panel.findChildren(QLabel, "pvp-assigned-weapon-indicator")
        )

        self._assign_compatible_weapons(workspace)

        self.assertTrue(workspace.weapons_ready())
        draft_panel.stage_button.click()
        QApplication.processEvents()

        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_TIMERS_RESULTS)
        self.assertEqual(len(draft_panel.timer_inputs_by_key), 6)
        for index, text in enumerate(("01:00", "01:00", "01:00")):
            workspace.set_timer_text("player_1", index, text)
        for index, text in enumerate(("01:10", "01:00", "01:00")):
            workspace.set_timer_text("player_2", index, text)
        self.assertTrue(workspace.timers_ready())

        draft_panel.stage_button.click()
        QApplication.processEvents()

        result = workspace.active_draft_session.controller.state.match_result
        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_COMPLETED_RESULT)
        self.assertIsNotNone(result)
        self.assertEqual(result.winner_seat, "player_1")
        self.assertEqual(result.seconds_difference, 10)
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
        self.assertIn("01:00", panel_text)
        self.assertIn(tr("app_shell.pvp.post.result_win"), panel_text)

    def test_pvp_assignment_moves_used_character_instead_of_duplicating(self) -> None:
        workspace, _panel = self._started_draft_workspace(
            character_count=24,
            deck_names=("Mirror",),
        )
        self._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())
        board = workspace.active_draft_session.board_dict()
        character_id = board["unified_pool"]["result_zones"]["player_1"]["picked"][0]

        workspace.select_assignment_character("player_1", character_id)
        workspace.assign_selected_character_to_slot("player_1", 0, 0)
        workspace.select_assignment_character("player_1", character_id)
        workspace.assign_selected_character_to_slot("player_1", 0, 1)

        slots = workspace.assignment_slots_by_seat["player_1"]
        assigned = [
            value
            for team in slots
            for value in team
            if value == character_id
        ]
        self.assertEqual(assigned, [character_id])
        self.assertIsNone(slots[0][0])
        self.assertEqual(slots[0][1], character_id)

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
        self.assertTrue(workspace.continue_to_weapons())

        board = workspace.active_draft_session.board_dict()
        first, second = board["unified_pool"]["result_zones"]["player_1"]["picked"][:2]
        deck = workspace.active_draft_session.controller.session_state.deck_for("player_1")
        sword_stack = next(stack for stack in deck.weapons if stack.weapon_type == "Sword")
        bow_stack = next(stack for stack in deck.weapons if stack.weapon_type == "Bow")

        workspace.assign_weapon_stack("player_1", first, bow_stack.stack_key)
        self.assertNotIn(first, workspace.weapon_assignments_by_seat["player_1"])

        workspace.assign_weapon_stack("player_1", first, sword_stack.stack_key)
        self.assertEqual(
            workspace.weapon_assignments_by_seat["player_1"][first],
            sword_stack.stack_key,
        )
        workspace.assign_weapon_stack("player_1", second, sword_stack.stack_key)
        self.assertNotEqual(
            workspace.weapon_assignments_by_seat["player_1"].get(second),
            sword_stack.stack_key,
        )
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
        workspace.select_assignment_character("player_1", character_id)
        workspace.assign_selected_character_to_slot("player_1", 0, 0)
        workspace.weapon_assignments_by_seat["player_1"][character_id] = "manual"
        workspace.set_timer_text("player_1", 0, "01:00")

        workspace.clear_active_draft()

        self.assertIsNone(workspace.active_draft_session)
        self.assertEqual(workspace.draft_stage, PVP_DRAFT_STAGE_DRAFT)
        self.assertEqual(workspace.assignment_slots_by_seat, {
            "player_1": [[None, None, None, None], [None, None, None, None]],
            "player_2": [[None, None, None, None], [None, None, None, None]],
        })
        self.assertEqual(workspace.weapon_assignments_by_seat, {
            "player_1": {},
            "player_2": {},
        })
        self.assertEqual(workspace.timer_texts_by_seat["player_1"], ["", "", ""])

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
        weapons: list[dict] | None = None,
    ) -> tuple[PvpWorkspace, PvpPlayRightPanel]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        portrait_path, weapon_path = _create_test_asset_images(temp_dir.name)
        characters = _valid_character_assets(character_count, image_path=portrait_path)
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
        workspace = PvpWorkspace(
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
            self.assertTrue(workspace.draft_workspace.legal_card_buttons)
            workspace.draft_workspace.legal_card_buttons[0].click()
            QApplication.processEvents()

    def _assign_all_picks_to_teams(self, workspace: PvpWorkspace) -> None:
        board = workspace.active_draft_session.board_dict()
        for seat in ("player_1", "player_2"):
            picks = board["unified_pool"]["result_zones"][seat]["picked"]
            self.assertEqual(len(picks), 8)
            for index, character_id in enumerate(picks):
                workspace.select_assignment_character(seat, character_id)
                workspace.assign_selected_character_to_slot(
                    seat,
                    index // 4,
                    index % 4,
                )
        QApplication.processEvents()

    def _assign_compatible_weapons(self, workspace: PvpWorkspace) -> None:
        session = workspace.active_draft_session
        self.assertIsNotNone(session)
        for seat in ("player_1", "player_2"):
            deck = session.controller.session_state.deck_for(seat)
            character_by_id = deck.character_by_id
            assigned = [
                character_id
                for team in workspace.assignment_slots_by_seat[seat]
                for character_id in team
                if character_id
            ]
            for character_id in assigned:
                weapon_type = character_by_id[character_id].weapon_type
                stack = next(
                    stack
                    for stack in deck.weapons
                    if stack.weapon_type == weapon_type
                )
                workspace.select_weapon_character(seat, character_id)
                workspace.assign_weapon_stack(seat, character_id, stack.stack_key)
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
