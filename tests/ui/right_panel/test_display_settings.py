from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from hoyolab_export.auth import AuthStatus
from localization import get_language, set_language, tr
from run_workspace.display_settings import USE_SYSTEM_SCALING_SETTING, use_system_scaling
from ui.right_panel.settings.display import DisplaySettingsBlock

_APP = QApplication.instance() or QApplication([])


class DisplaySettingsUiTests(unittest.TestCase):
    def _block(self, path: Path) -> DisplaySettingsBlock:
        block = DisplaySettingsBlock(settings_file=path)
        self.addCleanup(block.close)
        return block

    def test_toggle_persists_without_changing_running_process_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            original_env = dict(os.environ)
            block = self._block(path)
            self.assertFalse(block.system_scaling_switch.isChecked())
            self.assertFalse(path.exists())
            block.system_scaling_switch.click()
            self.assertTrue(use_system_scaling(settings_file=path))
            self.assertEqual(block.restart_label.text(), tr("settings.display.system_scaling.restart"))
            reopened = self._block(path)
            self.assertTrue(reopened.system_scaling_switch.isChecked())
            reopened.system_scaling_switch.click()
            self.assertFalse(use_system_scaling(settings_file=path))
            self.assertEqual(dict(os.environ), original_env)

    def test_readonly_settings_revert_choice_and_show_save_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            block = self._block(Path(tmp) / "settings.json")
            with patch("ui.right_panel.settings.display.set_use_system_scaling", side_effect=PermissionError):
                block.system_scaling_switch.click()
            self.assertFalse(block.system_scaling_switch.isChecked())
            self.assertEqual(block.restart_label.text(), tr("settings.display.system_scaling.save_failed"))
            block.system_scaling_switch.click()
            self.assertTrue(block.system_scaling_switch.isChecked())
            self.assertEqual(block.restart_label.text(), tr("settings.display.system_scaling.restart"))

    def test_language_refresh_updates_text_and_keeps_saved_choice(self) -> None:
        old_language = get_language()
        self.addCleanup(lambda: set_language(old_language))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({USE_SYSTEM_SCALING_SETTING: True}), encoding="utf-8")
            block = self._block(path)
            for language in ("ru", "en", "pt-br"):
                with self.subTest(language=language):
                    set_language(language)
                    block.retranslate_ui()
                    self.assertEqual(block.system_scaling_label.text(), tr("settings.display.system_scaling"))
                    self.assertEqual(block.system_scaling_switch.accessibleName(), block.system_scaling_label.text())
                    self.assertNotEqual(block.title_label.text(), "settings.display.title")
                    self.assertNotEqual(block.description_label.text(), "settings.display.system_scaling.description")
                    self.assertEqual(block.restart_label.text(), tr("settings.display.system_scaling.restart"))
                    self.assertEqual(block.system_scaling_switch.toolTip(), "")
                    self.assertTrue(block.system_scaling_switch.isChecked())

    def test_account_settings_contains_display_block_and_retranslates_it(self) -> None:
        from ui.right_panel.settings.account_data import AccountDataPage

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("ui.right_panel.settings.account_data.ensure_hoyolab_dirs"),
                patch("ui.right_panel.settings.account_data.get_auth_status", return_value=AuthStatus.NOT_LOGGED_IN),
                patch("ui.right_panel.settings.account_data.has_local_hoyolab_profile", return_value=False),
            ):
                page = AccountDataPage(settings_file=Path(tmp) / "settings.json")
            self.addCleanup(page.close)
            self.assertIsInstance(page.display_settings, DisplaySettingsBlock)
            self.assertIs(page.display_settings.parent(), page.settings_content)
            self.assertFalse(page.display_settings.system_scaling_switch.isChecked())
            with patch.object(page.display_settings, "retranslate_ui") as retranslate:
                page.retranslate_ui()
            retranslate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
