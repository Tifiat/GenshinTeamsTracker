"""Synthetic button-to-file regression; no native window or account data."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLineEdit

from localization import get_language, set_language
from tests.ui.pvp_browser.test_pvp_period import _workspace_fixture
from tests.ui.pvp_browser.test_abyss_match_integration import fixture_rules
from tests.ui.pvp_browser.test_pvp_browser import _asset_character_id
from run_workspace.pvp.deck_preset import save_deck_preset, set_deck_preset_rules
from ui.pvp_browser.result_export_dialog import is_default_player_name, localized_result_labels, request_export_names
from ui.pvp_browser.window import PVP_DRAFT_STAGE_COMPLETED_RESULT


class ResultExportFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace, _ = _workspace_fixture(Path(self.temp.name))
        self.addCleanup(self.workspace.close)
        preset = set_deck_preset_rules(self.workspace.decks_workspace.presets[0], fixture_rules(self.workspace))
        save_deck_preset(preset, self.workspace.decks_workspace.deck_dir)
        self.workspace.refresh_account_data(reload_presets=True)
        self.assertTrue(self.workspace.start_local_draft("local", "local"))
        for _ in range(26):
            entry = next(row for row in self.workspace.draft_board_dict()["unified_pool"]["entries"]
                         if row["is_current_legal_target"])
            self.assertTrue(self.workspace.apply_draft_card_click(entry["action"]))
        self.assertTrue(self.workspace.continue_to_assignment())
        for seat in ("player_1", "player_2"):
            picked = self.workspace.active_draft_session.controller.session_state.picked_character_ids_for(seat)
            assets = {_asset_character_id(item): item for item in self.workspace._build_character_assets_for_seat(seat)}
            for index, character_id in enumerate(picked):
                self.workspace.handle_build_slot_clicked(seat, index // 4, index % 4)
                self.assertTrue(self.workspace.handle_build_character_clicked(seat, assets[character_id]))
                self.assertTrue(self.workspace.handle_build_weapon_clicked(seat, self.workspace.weapon_assets[0]))
            self.assertTrue(self.workspace.ready_build_seat(seat))
        widget = self.workspace.draft_workspace._timers_result_widget
        for seat in ("player_1", "player_2"):
            for index in range(3):
                self.assertTrue(widget.set_timer_seconds_for_test(seat, index, 540))

    def test_finalize_button_offers_names_saves_png_and_repeat_export_reuses_names(self):
        destination = Path(self.temp.name) / "result.png"
        widget = self.workspace.draft_workspace._timers_result_widget
        with patch("ui.pvp_browser.result_export_dialog.request_export_names", return_value=("Лиса", "Wolf")) as names, \
             patch("ui.pvp_browser.window.QFileDialog.getSaveFileName", return_value=(str(destination), "PNG")):
            widget.finalize_button.click()
            self.assertEqual(names.call_count, 1)
            self.assertEqual(self.workspace.draft_stage, PVP_DRAFT_STAGE_COMPLETED_RESULT)
            self.assertFalse(QImage(str(destination)).isNull())
            self.assertFalse(widget.export_button.isHidden())
            widget.export_button.click()
            self.assertEqual(names.call_count, 1)
        self.workspace.clear_active_draft()
        self.assertIsNone(self.workspace._result_export_names)

    def test_cancel_names_keeps_result_and_skips_save_dialog(self):
        with patch("ui.pvp_browser.result_export_dialog.request_export_names", return_value=None), \
             patch("ui.pvp_browser.window.QFileDialog.getSaveFileName") as choose:
            self.workspace.draft_workspace._timers_result_widget.finalize_button.click()
            choose.assert_not_called()
        self.assertEqual(self.workspace.draft_stage, PVP_DRAFT_STAGE_COMPLETED_RESULT)
        self.assertIsNotNone(self.workspace.active_draft_session.controller.state.match_result)

    def test_confirmed_default_names_are_not_prompted_again_for_same_match(self):
        self.assertTrue(self.workspace.finalize_match_result())
        destination = Path(self.temp.name) / "defaults.png"
        with patch("ui.pvp_browser.result_export_dialog.request_export_names", return_value=("Player 1", "Player 2")) as names, \
             patch("ui.pvp_browser.window.QFileDialog.getSaveFileName", return_value=(str(destination), "PNG")):
            self.assertTrue(self.workspace.export_match_result())
            self.assertTrue(self.workspace.export_match_result())
            self.assertEqual(names.call_count, 1)

    def test_cancel_file_or_save_failure_preserves_finalized_result(self):
        self.assertTrue(self.workspace.finalize_match_result())
        result = self.workspace.active_draft_session.controller.state.match_result
        with patch("ui.pvp_browser.result_export_dialog.request_export_names", return_value=("A", "B")), \
             patch("ui.pvp_browser.window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.assertFalse(self.workspace.export_match_result())
        with patch("ui.pvp_browser.result_export_dialog.request_export_names", return_value=("A", "B")), \
             patch("ui.pvp_browser.window.QFileDialog.getSaveFileName", return_value=(str(Path(self.temp.name) / "fail.png"), "")), \
             patch("ui.pvp_browser.result_export.save_result_png", side_effect=OSError("test")):
            self.assertFalse(self.workspace.export_match_result())
        self.assertIs(self.workspace.active_draft_session.controller.state.match_result, result)


class ResultExportCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_name_dialog_accepts_optional_names_or_can_cancel(self):
        def accept():
            dialog = self.app.activeModalWidget()
            first, second = dialog.findChildren(QLineEdit)
            first.setText("  Лиса  ")
            second.setText("")
            dialog.accept()
        QTimer.singleShot(0, accept)
        self.assertEqual(request_export_names(None, ("Player 1", "Player 2")), ("Лиса", "Player 2"))
        QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
        self.assertIsNone(request_export_names(None, ("Player 1", "Player 2")))

    def test_default_names_and_labels_in_all_languages(self):
        for name in ("Player 1", "player2", "Игрок 1", "Игрок2", "Jogador 1", "Jogador2"):
            self.assertTrue(is_default_player_name(name))
        for name in ("Wolf", "Игрок 11", "Player 3"):
            self.assertFalse(is_default_player_name(name))
        previous = get_language()
        self.addCleanup(set_language, previous)
        for lang in ("ru", "en", "pt-br"):
            set_language(lang)
            labels = localized_result_labels()
            self.assertEqual(labels.chamber.format(number=1), "12-1")
            self.assertFalse(any("app_shell." in getattr(labels, field) for field in labels.__dataclass_fields__))
