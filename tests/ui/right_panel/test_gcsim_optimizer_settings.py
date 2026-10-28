from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from hoyolab_export.auth import AuthStatus
from localization import tr
from run_workspace.gcsim.settings import (
    GcsimOptimizerSettings,
    effective_gcsim_optimizer_settings,
    set_gcsim_optimizer_builds_per_group,
    set_gcsim_optimizer_expanded_limits_enabled,
    set_gcsim_optimizer_fast_mode_enabled,
    set_gcsim_optimizer_set_group_limit,
)
from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale(platform="linux")
_APP = QApplication.instance() or QApplication([])


class _SignalStub:
    def connect(self, _callback) -> None:
        return None


class _WorkerStub:
    def __init__(self, request) -> None:
        self.request = request
        self.progress = _SignalStub()
        self.finished = _SignalStub()

    def moveToThread(self, _thread) -> None:
        return None

    def run(self) -> None:
        return None

    def deleteLater(self) -> None:
        return None


class _ThreadStub:
    def __init__(self, *_args) -> None:
        self.started = _SignalStub()
        self.finished = _SignalStub()

    def start(self) -> None:
        return None

    def quit(self) -> None:
        return None

    def deleteLater(self) -> None:
        return None


class GcsimOptimizerSettingsUiTests(unittest.TestCase):
    def test_formula_result_text_does_not_show_measurement_or_gain_fields(self) -> None:
        from ui.app_shell import _format_formula_only_optimizer_text

        text = _format_formula_only_optimizer_text(
            "Selected Sets complete\n"
            "Final DPS: -\n"
            "Standard error: -\n"
            "Formula estimate: 12345\n"
            "Gain vs initial: -2%\n"
            "Formula residual: 0.2%"
        )

        self.assertIn(tr("gcsim.optimizer.formula_unverified"), text)
        self.assertIn("Formula estimate: 12345", text)
        self.assertNotIn("Final DPS:", text)
        self.assertNotIn("Standard error:", text)
        self.assertNotIn("Gain vs initial:", text)
        self.assertNotIn("Formula residual:", text)

    def _make_account_page(self, settings_file: Path):
        from ui.right_panel.settings.account_data import AccountDataPage

        with (
            patch("ui.right_panel.settings.account_data.ensure_hoyolab_dirs"),
            patch(
                "ui.right_panel.settings.account_data.get_auth_status",
                return_value=AuthStatus.NOT_LOGGED_IN,
            ),
            patch(
                "ui.right_panel.settings.account_data.has_local_hoyolab_profile",
                return_value=False,
            ),
        ):
            page = AccountDataPage(settings_file=settings_file)
        self.addCleanup(page.close)
        return page

    def test_spinboxes_persist_bounded_values_and_user_fast_mode_transitions_warn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            page = self._make_account_page(settings_file)

            self.assertEqual(
                (page.gcsim_optimizer_set_group_limit_spin.minimum(),
                 page.gcsim_optimizer_set_group_limit_spin.maximum()),
                (1, 5),
            )
            self.assertEqual(page.gcsim_optimizer_set_group_limit_spin.value(), 3)
            self.assertEqual(
                page.gcsim_optimizer_builds_per_group_spin.value(),
                2,
            )
            self.assertFalse(page.gcsim_optimizer_fast_mode_switch.isChecked())

            with patch.object(QMessageBox, "warning") as warning:
                page.gcsim_optimizer_set_group_limit_spin.setValue(4)
                page.gcsim_optimizer_builds_per_group_spin.setValue(2)
                page.gcsim_optimizer_fast_mode_switch.setChecked(True)
                page.gcsim_optimizer_fast_mode_switch.setChecked(False)
                page.gcsim_optimizer_fast_mode_switch.setChecked(True)

            self.assertEqual(warning.call_count, 2)
            self.assertEqual(
                warning.call_args.args[2],
                tr("settings.gcsim.optimizer.fast_mode.warning_body"),
            )
            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file).set_group_limit,
                4,
            )
            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file).builds_per_group,
                21,  # No explicit edit to the old default: use the fast default.
            )
            self.assertTrue(
                effective_gcsim_optimizer_settings(settings_file=settings_file).fast_mode
            )

    def test_restoring_enabled_fast_mode_does_not_show_the_transition_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            settings_file.write_text(
                json.dumps({"gcsim_optimizer_fast_mode": True}),
                encoding="utf-8",
            )
            with patch.object(QMessageBox, "warning") as warning:
                page = self._make_account_page(settings_file)
                self.assertTrue(page.gcsim_optimizer_fast_mode_switch.isChecked())
                page.set_gcsim_optimizer_fast_mode_enabled(True)

            warning.assert_not_called()

    def test_mode_limits_warn_bound_work_and_handle_zero_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            page = self._make_account_page(settings_file)

            with patch.object(QMessageBox, "warning") as warning:
                self.assertFalse(page.gcsim_optimizer_expanded_limits_checkbox.isChecked())
                page.gcsim_optimizer_set_group_limit_spin.setValue(5)
                self.assertEqual(warning.call_count, 1)
                page.gcsim_optimizer_builds_per_group_spin.setValue(3)
                self.assertEqual(warning.call_count, 1)
                page.gcsim_optimizer_fast_mode_switch.setChecked(True)
                self.assertEqual(warning.call_count, 2)
                self.assertEqual(page.gcsim_optimizer_set_group_limit_spin.maximum(), 10)
                self.assertEqual(page.gcsim_optimizer_builds_per_group_spin.maximum(), 40)
                page.gcsim_optimizer_set_group_limit_spin.setValue(10)
                page.gcsim_optimizer_builds_per_group_spin.setValue(20)
                page.gcsim_optimizer_fast_mode_switch.setChecked(False)
                self.assertEqual(warning.call_count, 3)
                self.assertEqual(
                    warning.call_args.args[2],
                    tr("settings.gcsim.optimizer.output_work.body"),
                )

            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file),
                GcsimOptimizerSettings(set_group_limit=5, builds_per_group=11),
            )
            self.assertEqual(
                page.gcsim_optimizer_set_group_limit_spin.maximum(),
                5,
            )
            self.assertEqual(
                page.gcsim_optimizer_builds_per_group_spin.maximum(),
                10,
            )
            page.gcsim_optimizer_builds_per_group_spin.setValue(0)
            self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file).builds_per_group, 1)

    def test_expanded_controls_and_warning_note_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            page = self._make_account_page(settings_file)
            with patch.object(QMessageBox, "warning"):
                checkbox = page.gcsim_optimizer_expanded_limits_checkbox
                self.assertTrue(page.gcsim_optimizer_expanded_limits_note.isHidden())
                checkbox.setChecked(True)
                self.assertFalse(page.gcsim_optimizer_expanded_limits_note.isHidden())
                page.gcsim_optimizer_set_group_limit_spin.setValue(1000)
                page.gcsim_optimizer_builds_per_group_spin.setValue(1000)
                self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file),
                    GcsimOptimizerSettings(50, 101, expanded_limits=True))
                page.gcsim_optimizer_fast_mode_switch.setChecked(True)
                self.assertEqual(page.gcsim_optimizer_builds_per_group_spin.value(), 100)
                checkbox.setChecked(False)
                self.assertEqual(page.gcsim_optimizer_set_group_limit_spin.maximum(), 10)
                self.assertEqual(page.gcsim_optimizer_builds_per_group_spin.maximum(), 40)
                self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file),
                    GcsimOptimizerSettings(10, 41, fast_mode=True))
                self.assertTrue(page.gcsim_optimizer_expanded_limits_note.isHidden())

    def test_account_settings_keep_page_title_visible_and_scroll_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            page = self._make_account_page(Path(temporary_directory) / "settings.json")
            self.assertIsInstance(page.settings_scroll, QScrollArea)
            self.assertIs(page.settings_scroll.widget(), page.settings_content)
            self.assertTrue(page.settings_scroll.widgetResizable())
            self.assertEqual(
                page.settings_scroll.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
            self.assertIs(page.title_label.parentWidget(), page)

            page.resize(360, 420)
            page.show()
            QApplication.processEvents()
            self.assertGreater(
                page.settings_scroll.verticalScrollBar().maximum(), 0
            )

    def test_selected_and_all_requests_read_fresh_settings_but_theory_does_not(self) -> None:
        from run_workspace.gcsim.settings import GcsimOptimizerSettings
        from ui.app_shell import AppShell

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            set_gcsim_optimizer_set_group_limit(6, settings_file=settings_file)
            set_gcsim_optimizer_builds_per_group(4, settings_file=settings_file)
            set_gcsim_optimizer_expanded_limits_enabled(
                True,
                settings_file=settings_file,
            )
            set_gcsim_optimizer_fast_mode_enabled(True, settings_file=settings_file)

            worker_instances: list[_WorkerStub] = []

            def make_worker(request):
                worker = _WorkerStub(request)
                worker_instances.append(worker)
                return worker

            settings_loader = lambda: effective_gcsim_optimizer_settings(
                settings_file=settings_file
            )
            shell = type("ShellStub", (), {})()
            shell._gcsim_browser_run_thread = None
            shell._clear_gcsim_run_worker_refs = lambda: None
            shell._on_gcsim_optimizer_selected_finished = lambda _payload: None
            shell.controller = type(
                "ControllerStub",
                (),
                {
                    "equipment_db_path": "unused-account.db",
                    "gcsim_boosted_energy_enabled": True,
                    "gcsim_browser_selected_team": lambda _self, _index: {
                        "slots": [{"character": {"name": "Furina"}}]
                    },
                },
            )()
            workspace = type("WorkspaceStub", (), {})()
            workspace.set_optimizer_busy = lambda _busy: None
            workspace.update_optimizer_progress = lambda _progress: None
            shell.left_host = type(
                "HostStub", (), {"gcsim_browser_workspace": workspace}
            )()

            with (
                patch("ui.app_shell.QThread", _ThreadStub),
                patch(
                    "ui.app_shell.GcsimBrowserSelectedOptimizerWorker",
                    side_effect=make_worker,
                ),
                patch(
                    "ui.app_shell.effective_gcsim_optimizer_settings",
                    side_effect=settings_loader,
                ) as load_settings,
                patch("ui.app_shell._selected_gcsim_engine_id", return_value="engine-v1"),
            ):
                AppShell._on_gcsim_optimizer_requested(
                    shell, 0, "active furina;", mode="selected"
                )
                selected_request = worker_instances[-1].request
                self.assertEqual(selected_request.set_group_limit, 1)
                self.assertEqual(selected_request.builds_per_group, 4)
                self.assertTrue(selected_request.fast_mode)
                self.assertTrue(selected_request.expanded_limits)
                shell._gcsim_browser_run_thread = None

                set_gcsim_optimizer_set_group_limit(2, settings_file=settings_file)
                set_gcsim_optimizer_builds_per_group(3, settings_file=settings_file)
                set_gcsim_optimizer_expanded_limits_enabled(
                    False,
                    settings_file=settings_file,
                )
                set_gcsim_optimizer_fast_mode_enabled(False, settings_file=settings_file)
                AppShell._on_gcsim_optimizer_requested(
                    shell, 0, "active furina;", mode="all_sets"
                )
                all_sets_request = worker_instances[-1].request
                self.assertEqual(all_sets_request.set_group_limit, 2)
                self.assertEqual(all_sets_request.builds_per_group, 3)
                self.assertFalse(all_sets_request.fast_mode)
                self.assertFalse(all_sets_request.expanded_limits)
                shell._gcsim_browser_run_thread = None

                AppShell._on_gcsim_optimizer_requested(
                    shell, 0, "active furina;", mode="theory"
                )

            self.assertEqual(load_settings.call_count, 2)
            theory_request = worker_instances[-1].request
            self.assertEqual(theory_request.set_group_limit, GcsimOptimizerSettings().set_group_limit)
            self.assertEqual(theory_request.builds_per_group, 2)  # Theory's separate legacy contract is unchanged.
            self.assertFalse(theory_request.fast_mode)


if __name__ == "__main__":
    unittest.main()
