from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.auth import AuthStatus, get_auth_status, open_login_browser, reset_profile
from hoyolab_export.offline_profile import (
    clear_current_offline_profile,
    export_offline_profile,
    has_local_hoyolab_profile,
    import_offline_profile,
    is_current_profile_exported,
)
from hoyolab_export.paths import (
    HOYOLAB_EXPORT_DIR,
    HOYOLAB_PROFILE_DIR,
    PROJECT_ROOT,
    ensure_hoyolab_dirs,
)
from localization import get_language, language_options, set_language, tr
from run_workspace.abyss.fact_dps_settings import (
    is_abyss_fact_dps_multi_target_enabled,
    set_abyss_fact_dps_multi_target_enabled,
)
from run_workspace.gcsim.settings import (
    is_gcsim_boosted_energy_enabled,
    set_gcsim_boosted_energy_enabled,
)
from ui.utils.toggle_switch import ToggleSwitch
from ui.widgets.loader import HoYoLABLoadingDialog
from ui.widgets.overlays.login_hint import HoYoLABLoginHintOverlay


HOYOLAB_IMPORT_COOLDOWN_MS = 5000
HOYOLAB_IMPORT_STATUSES = {
    "preparing": ("loader.preparing", 0.03),
    "opening_hoyolab": ("loader.opening_hoyolab", 0.10),
    "exporting_image": ("loader.exporting_image", 0.15),
    "opening_character_list": ("loader.opening_character_list", 0.18),
    "collecting_inventory": ("loader.collecting_inventory", 0.24),
    "waiting_export_images": ("loader.waiting_export_images", 0.30),
    "opening_share_menu": ("loader.opening_share_menu", 0.34),
    "starting_image_download": ("loader.starting_image_download", 0.38),
    "waiting_image_download": ("loader.waiting_image_download", 0.42),
    "retrying_image_download_2": ("loader.retrying_image_download_2", 0.43),
    "retrying_image_download_3": ("loader.retrying_image_download_3", 0.44),
    "waiting_image_generation": ("loader.waiting_image_generation", 0.45),
    "using_image_fallback": ("loader.using_image_fallback", 0.46),
    "downloading_image": ("loader.downloading_image", 0.48),
    "image_downloaded": ("loader.image_downloaded", 0.52),
    "building_layout": ("loader.building_layout", 0.58),
    "writing_inventory": ("loader.writing_inventory", 0.63),
    "fetching_character_details": ("loader.fetching_character_details", 0.70),
    "fetching_abyss_period": ("loader.fetching_abyss_period", 0.735),
    "updating_artifact_catalog": ("loader.updating_artifact_catalog", 0.76),
    "mapping_artifact_sets": ("loader.mapping_artifact_sets", 0.80),
    "closing_browser": ("loader.closing_browser", 0.84),
    "importing_artifacts": ("loader.importing_artifacts", 0.87),
    "updating_hoyolab_data": ("loader.updating_hoyolab_data", 0.91),
    "cropping_assets": ("loader.cropping_assets", 0.95),
    "syncing_account_storage": ("loader.syncing_account_storage", 0.965),
    "account_storage_sync_warning": ("loader.account_storage_sync_warning", 0.97),
    "updating_abyss_source_data": ("loader.updating_abyss_source_data", 0.972),
    "caching_abyss_monster_icons": ("loader.caching_abyss_monster_icons", 0.976),
    "skipping_abyss_source_data_refresh": ("loader.skipping_abyss_source_data_refresh", 0.976),
    "writing_import_log": ("loader.writing_import_log", 0.98),
    "done": ("loader.done", 1.0),
}


class AccountDataPage(QWidget):
    """Compact AppShell account page reusing the current HoYoLAB/profile flow."""

    account_data_changed = Signal(bool)
    language_changed = Signal()
    fact_dps_multi_target_changed = Signal(bool)
    gcsim_boosted_energy_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_file: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        ensure_hoyolab_dirs()
        self.setObjectName("RightPanelPrototypeContent")
        self._settings_file = settings_file

        self._hoyolab_login_process = None
        self._hoyolab_login_hint: HoYoLABLoginHintOverlay | None = None
        self._hoyolab_login_screen = None
        self._hoyolab_export_process: QProcess | None = None
        self._hoyolab_loader: HoYoLABLoadingDialog | None = None
        self._hoyolab_import_output_buffer = ""
        self._hoyolab_import_lines: list[str] = []
        self._hoyolab_import_cooldown_active = False
        self._updating_language_combo = False

        self._hoyolab_auth_timer = QTimer(self)
        self._hoyolab_auth_timer.setInterval(1000)
        self._hoyolab_auth_timer.timeout.connect(self.poll_hoyolab_login_browser)

        self._build_ui()
        self.refresh_hoyolab_auth_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel(tr("app_shell.account.title"))
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        account_frame = QFrame()
        account_frame.setObjectName("InfoBlock")
        account_layout = QVBoxLayout(account_frame)
        account_layout.setContentsMargins(8, 8, 8, 8)
        account_layout.setSpacing(8)

        self.hoyolab_label = QLabel(tr("common.hoyolab"))
        self.hoyolab_label.setObjectName("SectionTitle")
        account_layout.addWidget(self.hoyolab_label)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.btn_hoyolab_export = QPushButton(tr("hoyolab.import_button"))
        self.btn_hoyolab_export.setObjectName("ActionButton")
        self.btn_hoyolab_export.clicked.connect(self.run_hoyolab_export)
        action_row.addWidget(self.btn_hoyolab_export, 1)

        self.btn_profile_menu = QPushButton(tr("profile.menu_button"))
        self.btn_profile_menu.setObjectName("GhostButton")
        self.profile_menu = QMenu(self.btn_profile_menu)
        self.action_export_profile = self.profile_menu.addAction(tr("profile.export"))
        self.action_import_profile = self.profile_menu.addAction(tr("profile.import"))
        self.profile_menu.addSeparator()
        self.action_switch_profile = self.profile_menu.addAction(tr("profile.switch"))
        self.action_export_profile.triggered.connect(
            lambda _checked=False: self.export_profile()
        )
        self.action_import_profile.triggered.connect(
            lambda _checked=False: self.import_profile()
        )
        self.action_switch_profile.triggered.connect(
            lambda _checked=False: self.change_hoyolab_account()
        )
        self.btn_profile_menu.setMenu(self.profile_menu)
        action_row.addWidget(self.btn_profile_menu)
        account_layout.addLayout(action_row)
        root.addWidget(account_frame)

        language_frame = QFrame()
        language_frame.setObjectName("InfoBlock")
        language_layout = QHBoxLayout(language_frame)
        language_layout.setContentsMargins(8, 8, 8, 8)
        language_layout.setSpacing(8)

        self.language_label = QLabel(tr("language.selector"))
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(150)
        for code, label in language_options():
            self.language_combo.addItem(label, code)
        self._sync_language_combo()
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_combo, 1)
        root.addWidget(language_frame)

        dps_frame = QFrame()
        dps_frame.setObjectName("InfoBlock")
        dps_layout = QVBoxLayout(dps_frame)
        dps_layout.setContentsMargins(8, 8, 8, 8)
        dps_layout.setSpacing(8)

        self.dps_label = QLabel(tr("settings.dps.title"))
        self.dps_label.setObjectName("SectionTitle")
        dps_layout.addWidget(self.dps_label)

        dps_toggle_row = QHBoxLayout()
        dps_toggle_row.setContentsMargins(0, 0, 0, 0)
        dps_toggle_row.setSpacing(8)
        self.fact_dps_multi_target_label = QLabel(
            tr("settings.dps.multi_target_hp")
        )
        self.fact_dps_multi_target_switch = ToggleSwitch()
        self.fact_dps_multi_target_switch.setChecked(
            is_abyss_fact_dps_multi_target_enabled(
                settings_file=self._settings_file
            )
        )
        self.fact_dps_multi_target_switch.toggled.connect(
            self.on_fact_dps_multi_target_changed
        )
        dps_toggle_row.addWidget(self.fact_dps_multi_target_label, 1)
        dps_toggle_row.addWidget(self.fact_dps_multi_target_switch)
        dps_layout.addLayout(dps_toggle_row)
        root.addWidget(dps_frame)

        gcsim_frame = QFrame()
        gcsim_frame.setObjectName("InfoBlock")
        gcsim_layout = QVBoxLayout(gcsim_frame)
        gcsim_layout.setContentsMargins(8, 8, 8, 8)
        gcsim_layout.setSpacing(8)

        self.gcsim_label = QLabel(tr("settings.gcsim.title"))
        self.gcsim_label.setObjectName("SectionTitle")
        gcsim_layout.addWidget(self.gcsim_label)

        gcsim_toggle_row = QHBoxLayout()
        gcsim_toggle_row.setContentsMargins(0, 0, 0, 0)
        gcsim_toggle_row.setSpacing(8)
        gcsim_text_col = QVBoxLayout()
        gcsim_text_col.setContentsMargins(0, 0, 0, 0)
        gcsim_text_col.setSpacing(2)
        self.gcsim_boosted_energy_label = QLabel(
            tr("settings.gcsim.boosted_energy")
        )
        self.gcsim_boosted_energy_description = QLabel(
            tr("settings.gcsim.boosted_energy.description")
        )
        self.gcsim_boosted_energy_description.setWordWrap(True)
        gcsim_text_col.addWidget(self.gcsim_boosted_energy_label)
        gcsim_text_col.addWidget(self.gcsim_boosted_energy_description)
        self.gcsim_boosted_energy_switch = ToggleSwitch()
        self.gcsim_boosted_energy_switch.setChecked(
            is_gcsim_boosted_energy_enabled(settings_file=self._settings_file)
        )
        self.gcsim_boosted_energy_switch.toggled.connect(
            self.on_gcsim_boosted_energy_changed
        )
        gcsim_toggle_row.addLayout(gcsim_text_col, 1)
        gcsim_toggle_row.addWidget(self.gcsim_boosted_energy_switch)
        gcsim_layout.addLayout(gcsim_toggle_row)
        tooltip = tr("settings.gcsim.boosted_energy.description")
        self.gcsim_boosted_energy_label.setToolTip(tooltip)
        self.gcsim_boosted_energy_switch.setToolTip(tooltip)
        root.addWidget(gcsim_frame)
        root.addStretch(1)

    def _dialog_parent(self) -> QWidget:
        return self.window() or self

    def _finish_hoyolab_import_cooldown(self) -> None:
        self._hoyolab_import_cooldown_active = False
        self.refresh_hoyolab_auth_status()

    def refresh_hoyolab_auth_status(self) -> None:
        status = get_auth_status(HOYOLAB_PROFILE_DIR)
        local_profile_exists = has_local_hoyolab_profile()
        import_running = self._hoyolab_export_process is not None
        login_running = self._hoyolab_login_process is not None
        import_cooldown = self._hoyolab_import_cooldown_active

        self.btn_profile_menu.setEnabled(not import_running and not import_cooldown)

        if import_running:
            self.btn_hoyolab_export.setEnabled(False)
            self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_running_tooltip"))
            return
        if import_cooldown:
            self.btn_hoyolab_export.setEnabled(False)
            self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_cleanup_tooltip"))
            return
        if login_running:
            self.btn_hoyolab_export.setText(tr("hoyolab.login_waiting_button"))
            self.btn_hoyolab_export.setEnabled(False)
            self.btn_hoyolab_export.setToolTip("")
            return
        if status == AuthStatus.LOGGED_IN:
            self.btn_hoyolab_export.setText(
                tr("hoyolab.update_button")
                if local_profile_exists
                else tr("hoyolab.import_button")
            )
            self.btn_hoyolab_export.setEnabled(True)
            self.btn_hoyolab_export.setToolTip("")
            return

        self.btn_hoyolab_export.setText(tr("hoyolab.authorize_or_select_profile"))
        self.btn_hoyolab_export.setToolTip("")
        if status == AuthStatus.PROFILE_LOCKED:
            self.btn_hoyolab_export.setEnabled(False)
            QTimer.singleShot(2000, self.refresh_hoyolab_auth_status)
            return
        self.btn_hoyolab_export.setEnabled(True)

    def ask_open_hoyolab_login(self) -> bool:
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr("common.hoyolab"))
        box.setText(tr("hoyolab.authorize_instruction"))
        open_button = box.addButton(
            tr("hoyolab.open_login_browser"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() == open_button

    def open_hoyolab_login(self) -> None:
        if self._hoyolab_login_process is not None:
            return
        try:
            self._hoyolab_login_screen = QApplication.primaryScreen() or self.screen()
            geometry = (
                self._hoyolab_login_screen.availableGeometry()
                if self._hoyolab_login_screen is not None
                else None
            )
            self._hoyolab_login_process = open_login_browser(
                HOYOLAB_PROFILE_DIR,
                x=geometry.left() + 40 if geometry is not None else None,
                y=geometry.top() + 40 if geometry is not None else None,
            )
        except Exception as exc:
            self._hoyolab_login_screen = None
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.open_browser_failed", error=exc),
            )
            return

        self.btn_hoyolab_export.setText(tr("hoyolab.login_waiting_button"))
        self.btn_hoyolab_export.setEnabled(False)
        self._show_hoyolab_login_hint()
        self._hoyolab_auth_timer.start()

    def _show_hoyolab_login_hint(self) -> None:
        if self._hoyolab_login_hint is not None:
            self._hoyolab_login_hint.raise_()
            self._hoyolab_login_hint.set_target_screen(self._hoyolab_login_screen)
            self._hoyolab_login_hint.position_on_screen()
            return
        self._hoyolab_login_hint = HoYoLABLoginHintOverlay(
            self._dialog_parent(),
            target_screen=self._hoyolab_login_screen,
        )
        self._hoyolab_login_hint.show()
        self._hoyolab_login_hint.raise_()

    def _close_hoyolab_login_hint(self) -> None:
        if self._hoyolab_login_hint is None:
            return
        hint = self._hoyolab_login_hint
        self._hoyolab_login_hint = None
        hint.close()
        hint.deleteLater()

    def poll_hoyolab_login_browser(self) -> None:
        if self._hoyolab_login_process is None:
            self._hoyolab_auth_timer.stop()
            self._hoyolab_login_screen = None
            self._close_hoyolab_login_hint()
            self.refresh_hoyolab_auth_status()
            return
        if self._hoyolab_login_process.poll() is None:
            if self._hoyolab_login_hint is not None:
                self._hoyolab_login_hint.position_on_screen()
            return
        self._hoyolab_login_process = None
        self._hoyolab_login_screen = None
        self._hoyolab_auth_timer.stop()
        self._close_hoyolab_login_hint()
        self.refresh_hoyolab_auth_status()

    def change_hoyolab_account(self) -> None:
        if self._hoyolab_export_process is not None:
            QMessageBox.information(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("profile.close_import_before_switch"),
            )
            return
        if self._hoyolab_login_process is not None:
            QMessageBox.information(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.close_browser_before_switch"),
            )
            return

        if has_local_hoyolab_profile() and not is_current_profile_exported():
            choice = QMessageBox(self._dialog_parent())
            choice.setIcon(QMessageBox.Icon.Warning)
            choice.setWindowTitle(tr("profile.switch_title"))
            choice.setText(tr("profile.switch_export_warning"))
            export_button = choice.addButton(
                tr("profile.export_before_switch"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            choice.addButton(
                tr("profile.skip_export"),
                QMessageBox.ButtonRole.DestructiveRole,
            )
            cancel_button = choice.addButton(
                tr("common.cancel"),
                QMessageBox.ButtonRole.RejectRole,
            )
            cancel_button.hide()
            choice.setEscapeButton(cancel_button)
            choice.exec()
            clicked_button = choice.clickedButton()
            if clicked_button is None or clicked_button == cancel_button:
                return
            if clicked_button == export_button and not self.export_profile(
                show_success=False
            ):
                return

        history_choice = QMessageBox(self._dialog_parent())
        history_choice.setIcon(QMessageBox.Icon.Question)
        history_choice.setWindowTitle(tr("profile.switch_title"))
        history_choice.setText(tr("profile.keep_history_question"))
        keep_history_button = history_choice.addButton(
            tr("common.yes"),
            QMessageBox.ButtonRole.YesRole,
        )
        history_choice.addButton(tr("common.no"), QMessageBox.ButtonRole.NoRole)
        cancel_button = history_choice.addButton(
            tr("common.cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        cancel_button.hide()
        history_choice.setEscapeButton(cancel_button)
        history_choice.exec()
        clicked_button = history_choice.clickedButton()
        if clicked_button is None or clicked_button == cancel_button:
            return

        try:
            reset_profile(HOYOLAB_PROFILE_DIR, HOYOLAB_EXPORT_DIR)
            clear_current_offline_profile(
                clear_history=clicked_button != keep_history_button
            )
        except Exception as exc:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.reset_failed", error=exc),
            )
            return

        self.account_data_changed.emit(True)
        self.refresh_hoyolab_auth_status()

    def run_hoyolab_export(self) -> None:
        if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
            if self.ask_open_hoyolab_login():
                self.open_hoyolab_login()
            self.refresh_hoyolab_auth_status()
            return
        if self._hoyolab_export_process is not None or self._hoyolab_import_cooldown_active:
            return

        self._show_hoyolab_loader()
        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(["-m", "hoyolab_export.run_import"])
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.read_hoyolab_import_output)
        process.finished.connect(self.on_hoyolab_import_finished)
        self._hoyolab_export_process = process
        self._hoyolab_import_output_buffer = ""
        self._hoyolab_import_lines = []
        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_running_tooltip"))
        process.start()
        if not process.waitForStarted(3000):
            self._hoyolab_export_process = None
            process.deleteLater()
            self._close_hoyolab_loader()
            self.refresh_hoyolab_auth_status()
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.start_import_failed"),
            )

    def _show_hoyolab_loader(self) -> None:
        if self._hoyolab_loader is not None:
            self._hoyolab_loader.raise_()
            self._hoyolab_loader.activateWindow()
            return
        self._hoyolab_loader = HoYoLABLoadingDialog(self._dialog_parent())
        self._hoyolab_loader.set_status(tr("loader.preparing"), 0.03)
        self._hoyolab_loader.show()
        self._hoyolab_loader.raise_()
        self._hoyolab_loader.activateWindow()

    def _close_hoyolab_loader(self) -> None:
        if self._hoyolab_loader is None:
            return
        loader = self._hoyolab_loader
        self._hoyolab_loader = None
        loader.close()
        loader.deleteLater()

    def _set_hoyolab_loader_status(self, status: str) -> None:
        if self._hoyolab_loader is None:
            return
        text_key, progress = HOYOLAB_IMPORT_STATUSES.get(
            status,
            ("loader.unknown_status", None),
        )
        self._hoyolab_loader.set_status(tr(text_key, status=status), progress)

    def read_hoyolab_import_output(self) -> None:
        process = self._hoyolab_export_process
        if process is None:
            return
        chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not chunk:
            return
        self._hoyolab_import_output_buffer += chunk
        while "\n" in self._hoyolab_import_output_buffer:
            line, self._hoyolab_import_output_buffer = (
                self._hoyolab_import_output_buffer.split("\n", 1)
            )
            line = line.rstrip("\r")
            if line:
                print(line)
                self._hoyolab_import_lines.append(line)
            if line.startswith("[STATUS] "):
                self._set_hoyolab_loader_status(
                    line.replace("[STATUS] ", "", 1).strip()
                )

    def _hoyolab_import_error_details(self) -> str:
        lines = [
            line
            for line in self._hoyolab_import_lines
            if line and not line.startswith("[STATUS] ")
        ]
        return "\n".join(lines[-8:])

    def on_hoyolab_import_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        process = self._hoyolab_export_process
        if process is not None:
            self.read_hoyolab_import_output()
            if self._hoyolab_import_output_buffer.strip():
                line = self._hoyolab_import_output_buffer.strip()
                print(line)
                self._hoyolab_import_lines.append(line)
                self._hoyolab_import_output_buffer = ""
            process.deleteLater()
        self._hoyolab_export_process = None
        self._hoyolab_import_cooldown_active = True
        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_cleanup_tooltip"))
        QTimer.singleShot(
            HOYOLAB_IMPORT_COOLDOWN_MS,
            self._finish_hoyolab_import_cooldown,
        )

        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            if self._hoyolab_loader is not None:
                self._hoyolab_loader.finish()
            self.account_data_changed.emit(False)
            self._close_hoyolab_loader()
            self.refresh_hoyolab_auth_status()
            return

        self._close_hoyolab_loader()
        QMessageBox.warning(
            self._dialog_parent(),
            tr("common.hoyolab"),
            tr(
                "hoyolab.import_failed_with_details",
                details=self._hoyolab_import_error_details() or tr("hoyolab.import_failed"),
            ),
        )

    def export_profile(self, *, show_success: bool = True) -> bool:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog_parent(),
            tr("profile.export_dialog_title"),
            str(PROJECT_ROOT / "exports" / "hoyolab_offline_profile.zip"),
            tr("profile.zip_filter"),
        )
        if not path:
            return False
        try:
            result = export_offline_profile(path)
        except Exception as exc:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("profile.export_failed", error=exc),
            )
            return False
        if show_success:
            QMessageBox.information(
                self._dialog_parent(),
                tr("common.done"),
                tr("profile.export_done", count=len(result.get("includedFiles") or [])),
            )
        self.refresh_hoyolab_auth_status()
        return True

    def import_profile(self) -> bool:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self._dialog_parent(),
            tr("profile.import_dialog_title"),
            str(PROJECT_ROOT / "exports"),
            tr("profile.zip_filter"),
        )
        if not path:
            return False
        try:
            result = import_offline_profile(path)
        except Exception as exc:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("profile.import_failed", error=exc),
            )
            return False
        self.account_data_changed.emit(True)
        self.refresh_hoyolab_auth_status()
        QMessageBox.information(
            self._dialog_parent(),
            tr("common.done"),
            tr("profile.import_done", count=len(result.get("restoredFiles") or [])),
        )
        return True

    def _sync_language_combo(self) -> None:
        self._updating_language_combo = True
        index = self.language_combo.findData(get_language())
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self._updating_language_combo = False

    def on_language_changed(self, index: int) -> None:
        if self._updating_language_combo or index < 0:
            return
        language = self.language_combo.itemData(index)
        if not language:
            return
        set_language(str(language), persist=True)
        self.retranslate_ui()
        self.language_changed.emit()

    def on_fact_dps_multi_target_changed(self, enabled: bool) -> None:
        set_abyss_fact_dps_multi_target_enabled(
            bool(enabled),
            settings_file=self._settings_file,
        )
        self.fact_dps_multi_target_changed.emit(bool(enabled))

    def on_gcsim_boosted_energy_changed(self, enabled: bool) -> None:
        set_gcsim_boosted_energy_enabled(
            bool(enabled),
            settings_file=self._settings_file,
        )
        self.gcsim_boosted_energy_changed.emit(bool(enabled))

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.account.title"))
        self.hoyolab_label.setText(tr("common.hoyolab"))
        self.btn_profile_menu.setText(tr("profile.menu_button"))
        self.action_export_profile.setText(tr("profile.export"))
        self.action_import_profile.setText(tr("profile.import"))
        self.action_switch_profile.setText(tr("profile.switch"))
        self.language_label.setText(tr("language.selector"))
        self.dps_label.setText(tr("settings.dps.title"))
        self.fact_dps_multi_target_label.setText(
            tr("settings.dps.multi_target_hp")
        )
        self.gcsim_label.setText(tr("settings.gcsim.title"))
        self.gcsim_boosted_energy_label.setText(
            tr("settings.gcsim.boosted_energy")
        )
        self.gcsim_boosted_energy_description.setText(
            tr("settings.gcsim.boosted_energy.description")
        )
        tooltip = tr("settings.gcsim.boosted_energy.description")
        self.gcsim_boosted_energy_label.setToolTip(tooltip)
        self.gcsim_boosted_energy_switch.setToolTip(tooltip)
        self._sync_language_combo()
        if self._hoyolab_loader is not None:
            self._hoyolab_loader.retranslate_ui()
        if self._hoyolab_login_hint is not None:
            self._hoyolab_login_hint.retranslate_ui()
        self.refresh_hoyolab_auth_status()
