"""Qt process lifecycle fixtures; no network, login profile or account writes."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication
from ui.right_panel.settings import account_data


class HoYoLABImportLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        for name, kwargs in (
            ("get_auth_status", {"return_value": account_data.AuthStatus.LOGGED_IN}),
            ("has_local_hoyolab_profile", {"return_value": True}),
            ("ensure_hoyolab_dirs", {}),
        ):
            self.stack.enter_context(patch.object(account_data, name, **kwargs))
        self.stack.enter_context(patch.object(account_data.QMessageBox, "warning"))
        self.page = account_data.AccountDataPage(settings_file=Path(folder) / "settings.json")
        self.addCleanup(self.page.close)
        self.addCleanup(self.page._close_hoyolab_loader)

    def test_failed_start_restores_button_and_closes_loader(self):
        process = MagicMock()
        process.waitForStarted.return_value = False
        with patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_hoyolab_export.click()
        self.assertIsNone(self.page._hoyolab_export_process)
        self.assertIsNone(self.page._hoyolab_loader)
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())
        process.deleteLater.assert_called_once()

    def test_equipment_toggle_defaults_off_persists_and_is_passed_per_run(self):
        self.assertFalse(self.page.change_equipment_switch.isChecked())
        self.page.change_equipment_switch.click()
        self.assertTrue(account_data.change_equipment_on_import(settings_file=self.page._settings_file))
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_hoyolab_export.click()
        process.setArguments.assert_called_once_with(["-m", "hoyolab_export.run_import", "--change-equipment"])
        self.assertFalse(self.page.change_equipment_switch.isEnabled())

    def test_failure_and_crash_restore_button_after_cleanup_and_allow_restart(self):
        for exit_code, status in ((1, QProcess.ExitStatus.NormalExit), (-1, QProcess.ExitStatus.CrashExit)):
            with self.subTest(status=status):
                process = MagicMock()
                process.readAllStandardOutput.return_value = b"[HoYoLAB Import] Failed: fixture\n"
                self.page._hoyolab_export_process = process
                changed = MagicMock()
                self.page.account_data_changed.connect(changed)
                with patch.object(account_data.QTimer, "singleShot") as timer:
                    self.page.on_hoyolab_import_finished(exit_code, status)
                    self.assertFalse(self.page.btn_hoyolab_export.isEnabled())
                    self.assertIsNone(self.page._hoyolab_export_process)
                    changed.assert_not_called()
                    timer.call_args.args[1]()
                self.assertTrue(self.page.btn_hoyolab_export.isEnabled())
                self.assertIsNone(self.page._hoyolab_loader)
                replacement = MagicMock()
                replacement.waitForStarted.return_value = False
                with patch.object(account_data, "QProcess", return_value=replacement):
                    self.page.btn_hoyolab_export.click()
                replacement.start.assert_called_once()
                self.page.account_data_changed.disconnect(changed)

    def test_success_refreshes_account_and_restores_button(self):
        process = MagicMock()
        process.readAllStandardOutput.return_value = b"[STATUS] done\n"
        self.page._hoyolab_export_process = process
        changed = MagicMock()
        self.page.account_data_changed.connect(changed)
        with patch.object(account_data.QTimer, "singleShot") as timer:
            self.page.on_hoyolab_import_finished(0, QProcess.ExitStatus.NormalExit)
            changed.assert_called_once_with(False)
            timer.call_args.args[1]()
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())

    def test_running_import_blocks_profile_operations_before_auth_checks(self):
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_hoyolab_export.click()
        self.assertFalse(self.page.btn_profile_menu.isEnabled())
        with patch.object(account_data, "get_auth_status") as auth, \
                patch.object(account_data.QFileDialog, "getOpenFileName") as open_file, \
                patch.object(account_data.QFileDialog, "getSaveFileName") as save_file:
            self.page.run_hoyolab_export()
            self.assertFalse(self.page.import_profile())
            self.assertFalse(self.page.export_profile())
            auth.assert_not_called()
            open_file.assert_not_called()
            save_file.assert_not_called()
        process.start.assert_called_once()

    def test_stale_or_duplicate_finished_signal_cannot_finish_another_run(self):
        current = MagicMock()
        self.page._hoyolab_export_process = current
        with patch.object(self.page, "on_hoyolab_import_finished") as finished:
            self.page._on_hoyolab_process_finished(MagicMock(), 0, QProcess.ExitStatus.NormalExit)
            finished.assert_not_called()
        self.assertIs(self.page._hoyolab_export_process, current)
        self.page._hoyolab_export_process = None
        with patch.object(account_data.QTimer, "singleShot") as timer:
            self.page.on_hoyolab_import_finished(0, QProcess.ExitStatus.NormalExit)
            timer.assert_not_called()
