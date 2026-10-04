"""Qt process lifecycle fixtures; no network, login profile or account writes."""
import json
import tempfile
import unittest
import uuid
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
            ("get_import_result", {"return_value": None}),
            ("list_pending_import_attempts", {"return_value": []}),
            ("latest_committed_import", {"return_value": None}),
        ):
            self.stack.enter_context(patch.object(account_data, name, **kwargs))
        self.stack.enter_context(patch.object(account_data.QMessageBox, "warning"))
        self.stack.enter_context(patch.object(account_data.QMessageBox, "information"))
        self.page = account_data.AccountDataPage(settings_file=Path(folder) / "settings.json")
        self.addCleanup(self.page.close)
        self.addCleanup(self.page._close_hoyolab_loader)

    def test_failed_start_restores_button_and_closes_loader(self):
        process = MagicMock()
        process.waitForStarted.return_value = False
        with patch.object(account_data.QTimer, "singleShot") as timer, \
                patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_hoyolab_export.click()
            timer.assert_not_called()
        self.assertIsNone(self.page._hoyolab_export_process)
        self.assertIsNone(self.page._hoyolab_loader)
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())
        self.assertTrue(self.page.btn_images_refresh.isEnabled())
        process.deleteLater.assert_called_once()

    def test_equipment_toggle_defaults_on_and_is_passed_per_run(self):
        self.assertTrue(self.page.change_equipment_switch.isChecked())
        self.assertTrue(account_data.change_equipment_on_import(settings_file=self.page._settings_file))
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_hoyolab_export.click()
        arguments = process.setArguments.call_args.args[0]
        self.assertEqual(arguments[:2], ["-m", "hoyolab_export.run_import"])
        self.assertEqual(arguments[2], "--attempt-id")
        self.assertTrue(uuid.UUID(arguments[3]))
        self.assertEqual(arguments[4], "--change-equipment")
        self.assertFalse(self.page.change_equipment_switch.isEnabled())

    def test_saved_equipment_off_is_restored_and_not_passed_to_import(self):
        self.page.change_equipment_switch.click()
        replacement = account_data.AccountDataPage(settings_file=self.page._settings_file)
        self.addCleanup(replacement.close)
        self.addCleanup(replacement._close_hoyolab_loader)
        self.assertFalse(replacement.change_equipment_switch.isChecked())
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "QProcess", return_value=process):
            replacement.btn_hoyolab_export.click()
        self.assertNotIn("--change-equipment", process.setArguments.call_args.args[0])

    def test_image_refresh_button_runs_only_image_mode(self):
        self.page.change_equipment_switch.click()
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "QProcess", return_value=process):
            self.page.btn_images_refresh.click()
        process.setArguments.assert_called_once_with(
            ["-m", "hoyolab_export.run_import", "--images-only"]
        )
        self.assertFalse(self.page.btn_images_refresh.isEnabled())

    def test_images_only_does_not_require_authentication(self):
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "get_auth_status", side_effect=AssertionError("auth read")), \
                patch.object(account_data, "QProcess", return_value=process):
            self.page.run_hoyolab_export(images_only=True)
        process.start.assert_called_once()

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
                    self.assertTrue(self.page.btn_hoyolab_export.isEnabled())
                    self.assertIsNone(self.page._hoyolab_export_process)
                    changed.assert_not_called()
                    timer.assert_not_called()
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
        self.page._hoyolab_attempt_id = "fixture-attempt"
        changed = MagicMock()
        self.page.account_data_changed.connect(changed)
        with patch.object(account_data, "get_import_result", return_value={"status": "committed"}):
            self.page.on_hoyolab_import_finished(0, QProcess.ExitStatus.NormalExit)
        changed.assert_called_once_with(False)
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())

    def test_unmapped_set_is_not_shown_as_a_skipped_set_warning(self):
        warning = {"code": "artifact_sets_unmapped", "count": 1,
                   "sets": [{"hoyolab_set_id": 2150451, "name": "Celestial Gift"}]}
        line = ("[IMPORT_WARNING] " + json.dumps(warning)).encode()
        process = MagicMock()
        process.readAllStandardOutput.side_effect = [line[:12], line[12:], b""]
        self.page._hoyolab_export_process = process
        self.page._hoyolab_attempt_id = "fixture-attempt"
        changed = MagicMock()
        self.page.account_data_changed.connect(changed)
        self.page.read_hoyolab_import_output()
        self.page.read_hoyolab_import_output()
        self.assertEqual(self.page._hoyolab_import_warnings, [])
        with patch.object(account_data, "get_import_result", return_value={"status": "committed"}):
            self.page.on_hoyolab_import_finished(0, QProcess.ExitStatus.NormalExit)
        changed.assert_called_once_with(False)
        account_data.QMessageBox.warning.assert_not_called()
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())

    def test_split_utf8_output_decodes_without_replacement_characters(self):
        payload = "Сохранено\n".encode("utf-8")
        split = payload.index("Сохранено".encode("utf-8")) + 1
        process = MagicMock()
        process.readAllStandardOutput.side_effect = [payload[:split], payload[split:]]
        self.page._hoyolab_export_process = process
        self.page._hoyolab_import_decoder = account_data.codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.page.read_hoyolab_import_output()
        self.page.read_hoyolab_import_output()
        self.assertEqual(self.page._hoyolab_import_lines, ["Сохранено"])

    def test_committed_receipt_survives_process_crash_and_refreshes_early_and_final(self):
        attempt_id = "durable-attempt"
        process = MagicMock()
        process.readAllStandardOutput.side_effect = [
            f'[IMPORT_COMMITTED] {{"attempt_id":"{attempt_id}"}}\n'.encode(), b""
        ]
        self.page._hoyolab_export_process = process
        self.page._hoyolab_attempt_id = attempt_id
        self.page._hoyolab_import_decoder = account_data.codecs.getincrementaldecoder("utf-8")(errors="replace")
        changed = MagicMock()
        self.page.account_data_changed.connect(changed)
        with patch.object(account_data, "get_import_result", return_value={"status": "committed"}):
            self.page.read_hoyolab_import_output()
            changed.assert_called_once_with(False)
            self.page.on_hoyolab_import_finished(-1, QProcess.ExitStatus.CrashExit)
        self.assertEqual(changed.call_count, 2)
        account_data.QMessageBox.warning.assert_not_called()
        account_data.QMessageBox.information.assert_called_once()
        self.assertTrue(self.page.btn_hoyolab_export.isEnabled())

    def test_failed_core_with_no_receipt_is_not_reported_as_success(self):
        process = MagicMock()
        process.readAllStandardOutput.return_value = b"[HoYoLAB Import] Failed: fixture\n"
        self.page._hoyolab_export_process = process
        self.page._hoyolab_attempt_id = "failed-attempt"
        changed = MagicMock()
        self.page.account_data_changed.connect(changed)
        with patch.object(account_data, "get_import_result", return_value=None):
            self.page.on_hoyolab_import_finished(0, QProcess.ExitStatus.NormalExit)
        changed.assert_not_called()
        account_data.QMessageBox.warning.assert_called_once()

    def test_pending_attempt_is_offered_before_auth_and_resumes_saved_source(self):
        attempt = {"attempt_id": "saved-attempt", "account_uid": "123456789",
                   "server": "os_usa", "status": "pending"}
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "list_pending_import_attempts", return_value=[attempt]), \
                patch.object(self.page, "_ask_hoyolab_recovery", return_value="resume"), \
                patch.object(account_data, "get_auth_status", side_effect=AssertionError("auth read")), \
                patch.object(account_data, "QProcess", return_value=process):
            self.page.run_hoyolab_export()
        process.setArguments.assert_called_once_with([
            "-m", "hoyolab_export.run_import", "--resume-attempt", "saved-attempt"
        ])

    def test_committed_unfinished_jobs_are_offered_and_replay_uses_receipt(self):
        attempt = {
            "attempt_id": "committed-attempt", "account_uid": "123456789",
            "server": "os_usa", "status": "committed",
            "enrichment": {"assets": {"status": "pending"}},
        }
        process = MagicMock()
        process.waitForStarted.return_value = True
        with patch.object(account_data, "latest_committed_import", return_value=attempt), \
                patch.object(self.page, "_ask_hoyolab_recovery", return_value="resume"), \
                patch.object(account_data, "get_auth_status", side_effect=AssertionError("auth read")), \
                patch.object(account_data, "QProcess", return_value=process):
            self.page.run_hoyolab_export()
        process.setArguments.assert_called_once_with([
            "-m", "hoyolab_export.run_import", "--resume-attempt", "committed-attempt"
        ])

    def test_committed_pending_enrichment_has_a_quiet_status_label(self):
        attempt = {
            "attempt_id": "committed-attempt", "status": "committed",
            "enrichment": {"assets": {"status": "pending"}},
        }
        with patch.object(account_data, "latest_committed_import", return_value=attempt):
            self.page.refresh_hoyolab_auth_status()
        self.assertFalse(self.page.hoyolab_recovery_status.isHidden())
        self.assertEqual(
            self.page.hoyolab_recovery_status.text(),
            account_data.tr("hoyolab.recovery.status_committed"),
        )
        account_data.QMessageBox.warning.assert_not_called()

    def test_committed_pending_enrichment_has_a_quiet_status_label(self):
        attempt = {
            "attempt_id": "committed-attempt", "status": "committed",
            "enrichment": {"assets": {"status": "pending"}},
        }
        with patch.object(account_data, "latest_committed_import", return_value=attempt):
            self.page.refresh_hoyolab_auth_status()
        self.assertFalse(self.page.hoyolab_recovery_status.isHidden())
        self.assertEqual(
            self.page.hoyolab_recovery_status.text(),
            account_data.tr("hoyolab.recovery.status_committed"),
        )
        account_data.QMessageBox.warning.assert_not_called()

    def test_legacy_binding_confirmation_replays_the_same_staged_attempt(self):
        attempt_id = "legacy-attempt"
        marker = {"attempt_id": attempt_id, "account_uid": "123456789", "server": "os_usa"}
        process = MagicMock()
        process.readAllStandardOutput.return_value = (
            "[IMPORT_BINDING_REQUIRED] " + json.dumps(marker) + "\n"
        ).encode()
        self.page._hoyolab_export_process = process
        self.page._hoyolab_attempt_id = attempt_id
        self.page._hoyolab_import_decoder = account_data.codecs.getincrementaldecoder("utf-8")(errors="replace")
        replacement = MagicMock()
        replacement.waitForStarted.return_value = True
        with patch.object(account_data.QMessageBox, "question", return_value=account_data.QMessageBox.StandardButton.Yes) as confirm, \
                patch.object(account_data, "QProcess", return_value=replacement):
            self.page.on_hoyolab_import_finished(3, QProcess.ExitStatus.NormalExit)
        prompt = confirm.call_args.args[2]
        self.assertIn("123456789", prompt)
        self.assertIn("os_usa", prompt)
        replacement.setArguments.assert_called_once_with([
            "-m", "hoyolab_export.run_import", "--resume-attempt", attempt_id,
            "--adopt-legacy",
        ])
        self.assertEqual(self.page._hoyolab_attempt_id, attempt_id)

    def test_progress_never_moves_backward_across_concurrent_stages(self):
        loader = MagicMock()
        self.page._hoyolab_loader = loader
        self.page._set_hoyolab_loader_status("enriching_account")
        first = loader.set_status.call_args.args[1]
        self.page._set_hoyolab_loader_status("saving_account")
        second = loader.set_status.call_args.args[1]
        self.assertGreaterEqual(second, first)

    def test_structured_progress_tracks_parallel_jobs_and_rejects_other_attempts(self):
        from hoyolab_export.import_progress import ImportProgress
        loader = MagicMock()
        self.page._hoyolab_loader = loader
        self.page._hoyolab_attempt_id = "current"
        reporter = ImportProgress("current", emit=lambda payload: self.page._consume_hoyolab_import_line(
            "[IMPORT_PROGRESS] " + json.dumps(payload)))
        reporter.update("assets", "download", 4, 10)
        reporter.update("abyss", "hp", 2, 8)
        reporter.update("abyss", "icons", 3, 9)
        text = loader.set_details.call_args.args[0]
        for counter in ("4/10", "2/8", "3/9"):
            self.assertIn(counter, text)
        self.assertLess(loader.set_status.call_args.args[1], .5)
        calls = loader.set_details.call_count
        for value in ("broken", "[]", '{"attempt_id":"other","progress":0.9,"jobs":{}}',
                      '{"attempt_id":"current","progress":NaN,"jobs":{}}'):
            self.page._consume_hoyolab_import_line("[IMPORT_PROGRESS] " + value)
        self.assertEqual(loader.set_details.call_count, calls)

    def test_loader_wait_does_not_advance_unreported_work(self):
        self.page._show_hoyolab_loader()
        loader = self.page._hoyolab_loader
        loader.set_status("waiting", .2)
        for _ in range(1000):
            loader._tick()
        self.assertAlmostEqual(loader._target_progress, .2)
        self.assertAlmostEqual(loader.bar.progress, .2)
        self.assertTrue(loader.elapsed_label.text())

    def test_import_stages_and_job_details_are_localized_in_every_supported_language(self):
        from hoyolab_export.import_progress import JOB_PHASES
        from localization.i18n import LOCALES_DIR
        keys = {key for key, _ in account_data.HOYOLAB_IMPORT_STATUSES.values()}
        keys.add("loader.elapsed")
        keys.update("loader.job." + kind for kind in JOB_PHASES)
        keys.update("loader.work." + phase for phases in JOB_PHASES.values() for phase in phases)
        keys.update("loader.work." + state for state in ("waiting", "complete", "pending"))
        for language in ("ru", "en", "pt-br"):
            catalog = json.loads((LOCALES_DIR / (language + ".json")).read_text(encoding="utf-8"))
            with self.subTest(language=language):
                self.assertEqual(keys - catalog.keys(), set())
                self.assertTrue(all(catalog[key].strip() for key in keys))

    def test_malformed_warning_output_cannot_break_completion(self):
        for payload in ("broken json", "[]", '{"code": []}', '{"code": {}}', '{"code": "unknown"}'):
            self.page._record_hoyolab_import_warning("[IMPORT_WARNING] " + payload)
        self.assertEqual(self.page._hoyolab_import_warnings, [])
        warning = {"code": "equipment_not_applied", "count": "invalid", "sets": None}
        line = "[IMPORT_WARNING] " + json.dumps(warning)
        self.page._record_hoyolab_import_warning(line)
        self.page._record_hoyolab_import_warning(line)
        self.assertEqual(self.page._hoyolab_import_warnings, [warning])
        self.assertTrue(self.page._hoyolab_import_warning_details())

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
