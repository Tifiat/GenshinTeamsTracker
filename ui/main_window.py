import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.auth import AuthStatus, get_auth_status, open_login_browser, reset_profile
from hoyolab_export.paths import (
    PROJECT_ROOT,
    HOYOLAB_EXPORT_DIR,
    HOYOLAB_PROFILE_DIR,
    HOYOLAB_CHARACTER_ASSETS_DIR,
    HOYOLAB_WEAPON_ASSETS_DIR,
    ensure_hoyolab_dirs,
)
from hoyolab_export.offline_profile import (
    clear_current_offline_profile,
    export_offline_profile,
    has_local_hoyolab_profile,
    import_offline_profile,
    is_current_profile_exported,
)
from localization import get_language, language_options, set_language, tr
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    WEAPON_RARITY_FILTERS,
    WEAPON_TYPE_FILTERS,
    asset_path_from_manifest_crop,
    character_matches_filters,
    character_sort_key,
    folder_asset_items,
    manifest_asset_items,
    metadata_int,
)
from ui.run_history_window import RunHistoryWindow
from ui.widgets.drag import DraggableIcon
from ui.widgets.team import TeamSlot
from ui.widgets.timers import AbyssFloorRow
from ui.widgets.loader import HoYoLABLoadingDialog
from ui.widgets.overlays.login_hint import HoYoLABLoginHintOverlay

ASSETS_CHAR = str(HOYOLAB_CHARACTER_ASSETS_DIR)
ASSETS_WEAP = str(HOYOLAB_WEAPON_ASSETS_DIR)
STATE_FILE = "state.json"
RUNS_FILE = "runs_history.json"
HOYOLAB_MANIFEST_FILE = PROJECT_ROOT / "data" / "hoyolab" / "crop_manifest.json"
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
    "updating_artifact_catalog": ("loader.updating_artifact_catalog", 0.76),
    "mapping_artifact_sets": ("loader.mapping_artifact_sets", 0.80),
    "closing_browser": ("loader.closing_browser", 0.84),
    "importing_artifacts": ("loader.importing_artifacts", 0.87),
    "updating_hoyolab_data": ("loader.updating_hoyolab_data", 0.91),
    "cropping_assets": ("loader.cropping_assets", 0.95),
    "writing_import_log": ("loader.writing_import_log", 0.98),
    "done": ("loader.done", 1.0),
}
HOYOLAB_IMPORT_COOLDOWN_MS = 5000
HOYOLAB_AUTH_WARNING_STYLE = """
QWidget#hoyolab_auth_box {
    border: 1px solid #b98722;
    background: #fff5d6;
}
QWidget#hoyolab_auth_box QLabel {
    color: #3a2a0a;
}
QWidget#hoyolab_auth_box QPushButton {
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid #8d6b1f;
    border-radius: 4px;
    background: #ffffff;
    color: #1f1f1f;
    font-weight: 600;
}
QWidget#hoyolab_auth_box QPushButton:hover {
    background: #fffdf5;
}
QWidget#hoyolab_auth_box QPushButton:disabled {
    background: #e8e1cf;
    color: #777777;
}
"""
HOYOLAB_AUTH_READY_STYLE = """
QWidget#hoyolab_auth_box {
    border: 1px solid #8aa36f;
    background: #f1f7eb;
}
QWidget#hoyolab_auth_box QPushButton {
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid #6f8758;
    border-radius: 4px;
    background: #ffffff;
    color: #1f1f1f;
    font-weight: 600;
}
QWidget#hoyolab_auth_box QPushButton:hover {
    background: #fbfff7;
}
"""
FILTER_BUTTON_STYLE = """
QPushButton#asset_filter_button {
    border: 2px solid transparent;
    border-radius: 15px;
    background-color: #202228;
    padding: 1px;
}
QPushButton#asset_filter_button:hover {
    background-color: #292c34;
}
QPushButton#asset_filter_button:checked {
    border-color: #4e91ff;
    background-color: #252936;
}
"""
class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("app.title"))
        self.resize(1400, 800)
        ensure_hoyolab_dirs()
        self.main = QHBoxLayout(self)
        self.floors = []
        self.teams = []
        self.team_title_labels = []

        self.ctrl_pressed = False
        self.pending_grid_updates = False
        self._resize_timer = None
        self._ui_ready = False
        self._initial_grid_built = False
        self._run_history_window = None
        self._hoyolab_login_process = None
        self._hoyolab_login_hint = None
        self._hoyolab_login_screen = None
        self._hoyolab_export_process = None
        self._hoyolab_loader = None
        self._hoyolab_import_output_buffer = ""
        self._hoyolab_import_lines = []
        self._hoyolab_import_cooldown_active = False
        self._character_element_filters: set[str] = set()
        self._character_weapon_filters: set[str] = set()
        self._character_rarity_filters: set[int] = set()
        self._weapon_type_filters: set[str] = set()
        self._weapon_rarity_filters: set[int] = set()
        self._updating_language_combo = False
        self._hoyolab_auth_timer = QTimer(self)
        self._hoyolab_auth_timer.setInterval(1000)
        self._hoyolab_auth_timer.timeout.connect(self.poll_hoyolab_login_browser)

        self.build_left_panel()
        self.build_right_panel()
        self.load_state()
        self.refresh_hoyolab_auth_status()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_grid_built:
            self._initial_grid_built = True
            QTimer.singleShot(0, self._finish_initial_ui)

    def _finish_initial_ui(self):
        self.update_grids()
        self._ui_ready = True

    def _finish_hoyolab_import_cooldown(self):
        self._hoyolab_import_cooldown_active = False
        self.refresh_hoyolab_auth_status()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
            if self.pending_grid_updates:
                self.update_grids()
                self.pending_grid_updates = False
        super().keyReleaseEvent(event)

    def safe_update_grids(self):
        if self.ctrl_pressed:
            self.pending_grid_updates = True
        else:
            self.update_grids()

    def open_run_history(self):
        if self._run_history_window is None:
            self._run_history_window = RunHistoryWindow()
        else:
            self._run_history_window._first_show = True
            self._run_history_window._min_width = None
            self._run_history_window.reload()

        self._run_history_window.show()
        self._run_history_window.raise_()
        self._run_history_window.activateWindow()

    def refresh_hoyolab_auth_status(self):
        status = get_auth_status(HOYOLAB_PROFILE_DIR)
        local_profile_exists = has_local_hoyolab_profile()
        import_running = self._hoyolab_export_process is not None
        login_running = self._hoyolab_login_process is not None
        import_cooldown = self._hoyolab_import_cooldown_active

        self.hoyolab_auth_box.setVisible(False)
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
        box = QMessageBox(self)
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

    def open_hoyolab_login(self):
        if self._hoyolab_login_process is not None:
            return

        try:
            self._hoyolab_login_screen = QApplication.primaryScreen() or self.screen()
            login_geometry = self._hoyolab_login_screen.availableGeometry() if self._hoyolab_login_screen else None
            window_x = login_geometry.left() + 40 if login_geometry is not None else None
            window_y = login_geometry.top() + 40 if login_geometry is not None else None
            self._hoyolab_login_process = open_login_browser(
                HOYOLAB_PROFILE_DIR,
                x=window_x,
                y=window_y,
            )
        except Exception as exc:
            self._hoyolab_login_screen = None
            QMessageBox.warning(self, tr("common.hoyolab"), tr("hoyolab.open_browser_failed", error=exc))
            return

        self.btn_hoyolab_export.setText(tr("hoyolab.login_waiting_button"))
        self.btn_hoyolab_export.setEnabled(False)
        self._show_hoyolab_login_hint()
        self._hoyolab_auth_timer.start()

    def _show_hoyolab_login_hint(self):
        if self._hoyolab_login_hint is not None:
            self._hoyolab_login_hint.raise_()
            self._hoyolab_login_hint.set_target_screen(self._hoyolab_login_screen)
            self._hoyolab_login_hint.position_on_screen()
            return

        self._hoyolab_login_hint = HoYoLABLoginHintOverlay(self, target_screen=self._hoyolab_login_screen)
        self._hoyolab_login_hint.show()
        self._hoyolab_login_hint.raise_()

    def _close_hoyolab_login_hint(self):
        if self._hoyolab_login_hint is None:
            return

        hint = self._hoyolab_login_hint
        self._hoyolab_login_hint = None
        hint.close()
        hint.deleteLater()

    def poll_hoyolab_login_browser(self):
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

    def change_hoyolab_account(self):
        if self._hoyolab_export_process is not None:
            QMessageBox.information(
                self,
                tr("common.hoyolab"),
                tr("profile.close_import_before_switch"),
            )
            return

        if self._hoyolab_login_process is not None:
            QMessageBox.information(
                self,
                tr("common.hoyolab"),
                tr("hoyolab.close_browser_before_switch"),
            )
            return

        if has_local_hoyolab_profile() and not is_current_profile_exported():
            choice = QMessageBox(self)
            choice.setIcon(QMessageBox.Icon.Warning)
            choice.setWindowTitle(tr("profile.switch_title"))
            choice.setText(tr("profile.switch_export_warning"))
            export_button = choice.addButton(
                tr("profile.export_before_switch"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            choice.addButton(tr("profile.skip_export"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_button = choice.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
            cancel_button.hide()
            choice.setEscapeButton(cancel_button)
            choice.exec()

            clicked_button = choice.clickedButton()
            if clicked_button is None or clicked_button == cancel_button:
                return
            if clicked_button == export_button:
                if not self.export_profile(show_success=False):
                    return

        history_choice = QMessageBox(self)
        history_choice.setIcon(QMessageBox.Icon.Question)
        history_choice.setWindowTitle(tr("profile.switch_title"))
        history_choice.setText(tr("profile.keep_history_question"))
        keep_history_button = history_choice.addButton(
            tr("common.yes"),
            QMessageBox.ButtonRole.YesRole,
        )
        history_choice.addButton(tr("common.no"), QMessageBox.ButtonRole.NoRole)
        cancel_button = history_choice.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        cancel_button.hide()
        history_choice.setEscapeButton(cancel_button)
        history_choice.exec()
        clicked_button = history_choice.clickedButton()
        if clicked_button is None or clicked_button == cancel_button:
            return

        keep_history = clicked_button == keep_history_button

        try:
            reset_profile(HOYOLAB_PROFILE_DIR, HOYOLAB_EXPORT_DIR)
            clear_current_offline_profile(clear_history=not keep_history)
        except Exception as exc:
            QMessageBox.warning(self, tr("common.hoyolab"), tr("hoyolab.reset_failed", error=exc))
            return

        self.reset_run()
        if self._run_history_window is not None:
            self._run_history_window.reload()
        self.safe_update_grids()
        self.refresh_hoyolab_auth_status()

    def run_hoyolab_export(self):
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
        process.setProcessChannelMode(QProcess.MergedChannels)

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
            QMessageBox.warning(self, tr("common.hoyolab"), tr("hoyolab.start_import_failed"))

    def _show_hoyolab_loader(self):
        if self._hoyolab_loader is not None:
            self._hoyolab_loader.raise_()
            self._hoyolab_loader.activateWindow()
            return

        self._hoyolab_loader = HoYoLABLoadingDialog(self)
        self._hoyolab_loader.set_status(tr("loader.preparing"), 0.03)
        self._hoyolab_loader.show()
        self._hoyolab_loader.raise_()
        self._hoyolab_loader.activateWindow()

    def _close_hoyolab_loader(self):
        if self._hoyolab_loader is None:
            return

        loader = self._hoyolab_loader
        self._hoyolab_loader = None
        loader.close()
        loader.deleteLater()

    def _set_hoyolab_loader_status(self, status: str):
        if self._hoyolab_loader is None:
            return

        text_key, progress = HOYOLAB_IMPORT_STATUSES.get(
            status,
            ("loader.unknown_status", None),
        )
        self._hoyolab_loader.set_status(tr(text_key, status=status), progress)

    def read_hoyolab_import_output(self):
        process = self._hoyolab_export_process
        if process is None:
            return

        chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not chunk:
            return

        self._hoyolab_import_output_buffer += chunk

        while "\n" in self._hoyolab_import_output_buffer:
            line, self._hoyolab_import_output_buffer = self._hoyolab_import_output_buffer.split("\n", 1)
            line = line.rstrip("\r")

            if line:
                print(line)
                self._hoyolab_import_lines.append(line)

            if line.startswith("[STATUS] "):
                self._set_hoyolab_loader_status(line.replace("[STATUS] ", "", 1).strip())

    def _hoyolab_import_error_details(self) -> str:
        lines = [
            line
            for line in self._hoyolab_import_lines
            if line and not line.startswith("[STATUS] ")
        ]
        return "\n".join(lines[-8:])

    def on_hoyolab_import_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
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
        QTimer.singleShot(HOYOLAB_IMPORT_COOLDOWN_MS, self._finish_hoyolab_import_cooldown)

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            if self._hoyolab_loader is not None:
                self._hoyolab_loader.finish()

            self.safe_update_grids()
            self._close_hoyolab_loader()
            self.refresh_hoyolab_auth_status()
            return

        self._close_hoyolab_loader()
        QMessageBox.warning(
            self,
            tr("common.hoyolab"),
            tr(
                "hoyolab.import_failed_with_details",
                details=self._hoyolab_import_error_details() or tr("hoyolab.import_failed"),
            ),
        )

    def export_profile(self, *, show_success: bool = True) -> bool:
        export_dir = PROJECT_ROOT / "exports"
        default_path = export_dir / "hoyolab_offline_profile.zip"
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("profile.export_dialog_title"),
            str(default_path),
            tr("profile.zip_filter"),
        )
        if not path:
            return False

        try:
            result = export_offline_profile(path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("common.hoyolab"),
                tr("profile.export_failed", error=exc),
            )
            return False

        if show_success:
            QMessageBox.information(
                self,
                tr("common.done"),
                tr(
                    "profile.export_done",
                    count=len(result.get("includedFiles") or []),
                ),
            )

        self.refresh_hoyolab_auth_status()
        return True

    def import_profile(self) -> bool:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
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
                self,
                tr("common.hoyolab"),
                tr("profile.import_failed", error=exc),
            )
            return False

        self.safe_update_grids()
        self.refresh_hoyolab_auth_status()
        QMessageBox.information(
            self,
            tr("common.done"),
            tr(
                "profile.import_done",
                count=len(result.get("restoredFiles") or []),
            ),
        )
        return True

    def _make_filter_button(self, value, icon_name: str, active_set: set):
        button = QPushButton("")
        button.setObjectName("asset_filter_button")
        button.setCheckable(True)
        button.setFixedSize(30, 30)
        button.setIconSize(QSize(24, 24))
        button.setStyleSheet(FILTER_BUTTON_STYLE)

        icon_path = FILTER_ASSETS_DIR / icon_name
        if icon_path.exists():
            button.setIcon(QIcon(str(icon_path)))
        else:
            button.setText(str(value))

        def toggle_filter(checked, *, filter_value=value, filters=active_set):
            if checked:
                filters.add(filter_value)
            else:
                filters.discard(filter_value)
            self.safe_update_grids()

        button.clicked.connect(toggle_filter)
        return button

    def _build_filter_row(self, filter_groups):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)

        for filters, active_set in filter_groups:
            for value, icon_name, _tooltip_key in filters:
                row.addWidget(self._make_filter_button(value, icon_name, active_set))

        row.addStretch()
        return row

    def build_left_panel(self):
        left = QVBoxLayout()

        self.hoyolab_auth_box = QWidget()
        self.hoyolab_auth_box.setObjectName("hoyolab_auth_box")
        auth_layout = QVBoxLayout(self.hoyolab_auth_box)
        auth_layout.setContentsMargins(8, 8, 8, 8)
        auth_layout.setSpacing(8)
        self.hoyolab_auth_label = QLabel("")
        self.hoyolab_auth_label.setWordWrap(True)
        auth_layout.addWidget(self.hoyolab_auth_label)
        self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_WARNING_STYLE)

        self.btn_hoyolab_export = QPushButton(tr("hoyolab.import_button"))
        self.btn_hoyolab_export.setMinimumHeight(30)
        self.btn_hoyolab_export.clicked.connect(self.run_hoyolab_export)

        self.btn_profile_menu = QPushButton(tr("profile.menu_button"))
        self.btn_profile_menu.setMinimumHeight(30)
        self.profile_menu = QMenu(self.btn_profile_menu)
        self.action_export_profile = self.profile_menu.addAction(tr("profile.export"))
        self.action_import_profile = self.profile_menu.addAction(tr("profile.import"))
        self.profile_menu.addSeparator()
        self.action_switch_profile = self.profile_menu.addAction(tr("profile.switch"))
        self.action_export_profile.triggered.connect(lambda _checked=False: self.export_profile())
        self.action_import_profile.triggered.connect(lambda _checked=False: self.import_profile())
        self.action_switch_profile.triggered.connect(lambda _checked=False: self.change_hoyolab_account())
        self.btn_profile_menu.setMenu(self.profile_menu)

        self.weapon_title_label = QLabel(tr("asset_panel.weapons"))
        left.addWidget(self.weapon_title_label)
        left.addLayout(
            self._build_filter_row(
                (
                    (WEAPON_TYPE_FILTERS, self._weapon_type_filters),
                    (WEAPON_RARITY_FILTERS, self._weapon_rarity_filters),
                )
            )
        )
        self.weapon_area = QScrollArea()
        self.weapon_area.setWidgetResizable(True)
        self.weapon_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.weapon_widget = QWidget()
        self.weapon_grid = QGridLayout(self.weapon_widget)
        self.weapon_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.weapon_area.setWidget(self.weapon_widget)
        left.addWidget(self.weapon_area, 1)

        self.char_title_label = QLabel(tr("asset_panel.characters"))
        left.addWidget(self.char_title_label)
        left.addLayout(
            self._build_filter_row(
                (
                    (ELEMENT_FILTERS, self._character_element_filters),
                    (WEAPON_TYPE_FILTERS, self._character_weapon_filters),
                    (CHARACTER_RARITY_FILTERS, self._character_rarity_filters),
                )
            )
        )
        self.char_area = QScrollArea()
        self.char_area.setWidgetResizable(True)
        self.char_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.char_widget = QWidget()
        self.char_grid = QGridLayout(self.char_widget)
        self.char_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.char_area.setWidget(self.char_widget)
        left.addWidget(self.char_area, 3)

        hoyolab_actions = QHBoxLayout()
        hoyolab_actions.setContentsMargins(0, 0, 0, 0)
        hoyolab_actions.setSpacing(8)
        hoyolab_actions.addWidget(self.btn_hoyolab_export, 1)
        hoyolab_actions.addWidget(self.btn_profile_menu)
        left.addLayout(hoyolab_actions)
        self.main.addLayout(left, 2)

    def build_right_panel(self):
        right = QVBoxLayout()

        for i in range(2):
            team = []
            team_label = QLabel(tr("main.team_label", number=i + 1))
            self.team_title_labels.append(team_label)
            right.addWidget(team_label)
            row = QHBoxLayout()
            for _ in range(4):
                slot = TeamSlot()
                team.append(slot)
                row.addWidget(slot)
            self.teams.append(team)
            right.addLayout(row)

        right.addSpacing(20)
        self.abyss_timers_label = QLabel(tr("main.abyss_timers"))
        right.addWidget(self.abyss_timers_label)

        for i in range(1, 4):
            floor = AbyssFloorRow(i, self.calculate_abyss)
            self.floors.append(floor)
            right.addWidget(floor)

        self.total_label = QLabel(tr("main.total_zero"))
        right.addWidget(self.total_label)

        self.btn_reset_run = QPushButton(tr("main.reset_run"))
        self.btn_reset_run.clicked.connect(self.reset_run)
        right.addWidget(self.btn_reset_run)

        self.btn_save_run = QPushButton(tr("main.save_run"))
        self.btn_save_run.clicked.connect(self.save_run)
        right.addWidget(self.btn_save_run)

        self.btn_history = QPushButton(tr("main.open_history"))
        self.btn_history.clicked.connect(self.open_run_history)
        right.addWidget(self.btn_history)

        right.addStretch()
        self.build_language_switcher(right)
        self.main.addLayout(right, 1)

    def build_language_switcher(self, parent_layout):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.language_label = QLabel(tr("language.selector"))
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(150)

        for code, label in language_options():
            self.language_combo.addItem(label, code)

        self._sync_language_combo()
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)

        row.addStretch()
        row.addWidget(self.language_label)
        row.addWidget(self.language_combo)
        parent_layout.addLayout(row)

    def _sync_language_combo(self):
        if not hasattr(self, "language_combo"):
            return

        self._updating_language_combo = True
        current = get_language()
        index = self.language_combo.findData(current)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self._updating_language_combo = False

    def on_language_changed(self, index: int):
        if self._updating_language_combo or index < 0:
            return

        language = self.language_combo.itemData(index)
        if not language:
            return

        set_language(str(language), persist=True)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(tr("app.title"))
        self.btn_profile_menu.setText(tr("profile.menu_button"))
        self.action_export_profile.setText(tr("profile.export"))
        self.action_import_profile.setText(tr("profile.import"))
        self.action_switch_profile.setText(tr("profile.switch"))
        self.weapon_title_label.setText(tr("asset_panel.weapons"))
        self.char_title_label.setText(tr("asset_panel.characters"))

        for index, label in enumerate(self.team_title_labels, start=1):
            label.setText(tr("main.team_label", number=index))

        self.abyss_timers_label.setText(tr("main.abyss_timers"))
        self.btn_reset_run.setText(tr("main.reset_run"))
        self.btn_save_run.setText(tr("main.save_run"))
        self.btn_history.setText(tr("main.open_history"))
        self.language_label.setText(tr("language.selector"))

        for floor in self.floors:
            floor.retranslate_ui()

        try:
            total = sum(int(floor.total.text()) for floor in self.floors)
        except ValueError:
            total = 0
        self.total_label.setText(
            tr("main.total_seconds", seconds=total) if total else tr("main.total_zero")
        )

        if self._run_history_window is not None and hasattr(self._run_history_window, "retranslate_ui"):
            self._run_history_window.retranslate_ui()

        if self._hoyolab_loader is not None and hasattr(self._hoyolab_loader, "retranslate_ui"):
            self._hoyolab_loader.retranslate_ui()

        if self._hoyolab_login_hint is not None and hasattr(self._hoyolab_login_hint, "retranslate_ui"):
            self._hoyolab_login_hint.retranslate_ui()

        self.refresh_hoyolab_auth_status()

    def _clear_grid(self, grid):
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def load_hoyolab_manifest(self) -> dict:
        if not HOYOLAB_MANIFEST_FILE.exists():
            return {}

        try:
            with open(HOYOLAB_MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"Failed to load HoYoLAB manifest: {exc}")
            return {}

    def _asset_path_from_manifest_crop(self, crop: str | None) -> Path | None:
        return asset_path_from_manifest_crop(crop)

    def _folder_asset_items(self, directory: str | Path) -> list[dict]:
        return folder_asset_items(directory)

    def _manifest_asset_items(self, manifest: dict, manifest_key: str, directory: str | Path) -> list[dict]:
        return manifest_asset_items(manifest, manifest_key, directory)

    def _character_matches_filters(self, asset: dict) -> bool:
        return character_matches_filters(
            asset,
            self._character_element_filters,
            self._character_weapon_filters,
            self._character_rarity_filters,
        )

    def _weapon_matches_filters(self, asset: dict) -> bool:
        metadata = asset.get("metadata")
        if not metadata:
            return True

        weapon = metadata.get("weapon") or {}
        weapon_type = str(weapon.get("type_name") or "").lower()
        try:
            rarity = int(weapon.get("rarity") or 0)
        except (TypeError, ValueError):
            rarity = 0

        if self._weapon_type_filters and weapon_type not in self._weapon_type_filters:
            return False
        if self._weapon_rarity_filters and rarity not in self._weapon_rarity_filters:
            return False

        return True

    @staticmethod
    def _metadata_int(value, default: int = 0) -> int:
        return metadata_int(value, default)

    def _character_sort_key(self, asset: dict):
        return character_sort_key(asset)

    def _weapon_sort_key(self, asset: dict):
        metadata = asset.get("metadata") or {}
        weapon = metadata.get("weapon") or {}
        variants = metadata.get("variants") or []
        rarity = self._metadata_int(weapon.get("rarity"))
        max_level = self._metadata_int(weapon.get("level"))

        for variant in variants:
            max_level = max(max_level, self._metadata_int(variant.get("level")))

        name = str(weapon.get("name") or metadata.get("name") or asset.get("filename") or "").casefold()
        return (-rarity, -max_level, name, str(asset.get("filename") or ""))

    def _reset_grid_columns(self, grid):
        for column in range(grid.columnCount()):
            grid.setColumnMinimumWidth(column, 0)
            grid.setColumnStretch(column, 0)

    def _reload_icon_grid(self, assets, grid, container, area, icon_size, spacing):
        self._clear_grid(grid)
        self._reset_grid_columns(grid)
        if not assets:
            grid.setContentsMargins(0, 0, 0, 0)
            container.adjustSize()
            area.horizontalScrollBar().setValue(0)
            return

        available_width = area.viewport().width() or area.width() or 300
        cell_width = icon_size + spacing
        cols = max(1, (available_width + spacing) // cell_width)
        total_grid_width = cols * icon_size + max(0, cols - 1) * spacing
        left_margin = max(0, (available_width - total_grid_width) // 2)
        right_margin = max(0, available_width - total_grid_width - left_margin)

        grid.setContentsMargins(left_margin, 0, right_margin, 0)
        grid.setHorizontalSpacing(spacing)
        grid.setVerticalSpacing(spacing)

        for c in range(cols):
            grid.setColumnMinimumWidth(c, icon_size)
            grid.setColumnStretch(c, 0)

        for i, asset in enumerate(assets):
            path = asset["path"]
            filename = asset["filename"]
            try:
                icon = DraggableIcon(str(path), icon_size)

                tooltip = asset.get("tooltip")
                if tooltip:
                    icon.setToolTip(tooltip)

                grid.addWidget(icon, i // cols, i % cols)
            except Exception as exc:
                print(f"Failed to load {filename}: {exc}")

        container.adjustSize()
        container.updateGeometry()
        area.horizontalScrollBar().setValue(0)
        area.viewport().update()

    def reload_characters(self):
        manifest = self.load_hoyolab_manifest()
        assets = self._manifest_asset_items(manifest, "characterAssets", ASSETS_CHAR)
        assets = [asset for asset in assets if self._character_matches_filters(asset)]
        assets.sort(key=self._character_sort_key)
        self._reload_icon_grid(
            assets,
            self.char_grid,
            self.char_widget,
            self.char_area,
            72,
            3,
        )

    def reload_weapons(self):
        manifest = self.load_hoyolab_manifest()
        assets = self._manifest_asset_items(manifest, "weaponAssets", ASSETS_WEAP)
        assets = [asset for asset in assets if self._weapon_matches_filters(asset)]
        assets.sort(key=self._weapon_sort_key)
        self._reload_icon_grid(
            assets,
            self.weapon_grid,
            self.weapon_widget,
            self.weapon_area,
            48,
            6,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ui_ready:
            self.update_grids_delayed()

    def update_grids_delayed(self):
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.update_grids)
        self._resize_timer.start(75)

    def update_grids(self):
        self.reload_characters()
        self.reload_weapons()

    def calculate_abyss(self):
        total = sum(f.calculate() for f in self.floors)
        self.total_label.setText(tr("main.total_seconds", seconds=total))
        self.save_state()

    def save_state(self):
        data = {
            "floors": [{"t1": f.t1.seconds_left, "t2": f.t2.seconds_left} for f in self.floors],
            "teams": [[slot.to_dict() for slot in team] for team in self.teams],
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"Failed to load state: {exc}")
            return

        for team_slots, saved_team in zip(self.teams, data.get("teams", [])):
            for slot, saved in zip(team_slots, saved_team):
                slot.from_dict(saved)

        for floor, saved in zip(self.floors, data.get("floors", [])):
            floor.t1.seconds_left = saved.get("t1", 600)
            floor.t2.seconds_left = saved.get("t2", 600)
            floor.t1.min_spin.setValue(floor.t1.seconds_left // 60)
            floor.t1.sec_spin.setValue(floor.t1.seconds_left % 60)
            floor.t2.min_spin.setValue(floor.t2.seconds_left // 60)
            floor.t2.sec_spin.setValue(floor.t2.seconds_left % 60)

    def reset_run(self):
        for floor in self.floors:
            floor.t1.min_spin.setValue(10)
            floor.t1.sec_spin.setValue(0)
            floor.t1.seconds_left = 600
            floor.t1.result.setText("0")
            floor.t2.min_spin.setValue(10)
            floor.t2.sec_spin.setValue(0)
            floor.t2.seconds_left = 600
            floor.t2.result.setText("0")
            floor.total.setText("0")

        for team in self.teams:
            for slot in team:
                slot.char.clear()
                slot.weapon.clear()
                slot.artifact.clear()

        self.total_label.setText(tr("main.total_zero"))
        self.save_state()

    def save_run(self):
        team1_floors = []
        team2_floors = []

        for floor in self.floors:
            t1_left = floor.t1.seconds_left
            t2_left = floor.t2.seconds_left
            team1_floors.append(600 - t1_left)
            team2_floors.append(t1_left - t2_left)

        run = {
            "teams": {
                "team1": [slot.to_dict() for slot in self.teams[0]],
                "team2": [slot.to_dict() for slot in self.teams[1]],
            },
            "floors": {
                "team1": team1_floors,
                "team2": team2_floors,
            },
        }

        runs = []
        if os.path.exists(RUNS_FILE):
            try:
                with open(RUNS_FILE, "r", encoding="utf-8") as f:
                    runs = json.load(f)
            except Exception as exc:
                print(f"Failed to load run history: {exc}")

        runs.append(run)
        with open(RUNS_FILE, "w", encoding="utf-8") as f:
            json.dump(runs, f, indent=2, ensure_ascii=False)

        if self._run_history_window is not None:
            self._run_history_window.reload()
