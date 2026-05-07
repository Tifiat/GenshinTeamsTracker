import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
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
    clear_hoyolab_current_data,
    ensure_hoyolab_dirs,
)
from localization import get_language, language_options, set_language, tr
from ui.run_history_window import RunHistoryWindow
from ui.widgets.drag import DraggableIcon
from ui.widgets.team import TeamSlot
from ui.widgets.timers import AbyssFloorRow
from ui.widgets.loader import HoYoLABLoadingDialog

ASSETS_CHAR = str(HOYOLAB_CHARACTER_ASSETS_DIR)
ASSETS_WEAP = str(HOYOLAB_WEAPON_ASSETS_DIR)
STATE_FILE = "state.json"
RUNS_FILE = "runs_history.json"
HOYOLAB_MANIFEST_FILE = PROJECT_ROOT / "data" / "hoyolab" / "crop_manifest.json"
HOYOLAB_IMPORT_STATUSES = {
    "preparing": ("loader.preparing", 0.05),
    "opening_hoyolab": ("loader.opening_hoyolab", 0.15),
    "collecting_inventory": ("loader.collecting_inventory", 0.30),
    "exporting_image": ("loader.exporting_image", 0.45),
    "building_layout": ("loader.building_layout", 0.65),
    "writing_inventory": ("loader.writing_inventory", 0.75),
    "cropping_assets": ("loader.cropping_assets", 0.88),
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
        self._hoyolab_export_process = None
        self._hoyolab_loader = None
        self._hoyolab_import_output_buffer = ""
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

        if status == AuthStatus.LOGGED_IN:
            self.hoyolab_auth_box.setVisible(True)
            self.hoyolab_auth_label.setVisible(False)
            self.btn_hoyolab_login.setVisible(False)
            self.btn_hoyolab_switch.setVisible(True)
            self.btn_hoyolab_switch.setText(tr("hoyolab.switch_account"))
            self.btn_hoyolab_export.setEnabled(self._hoyolab_export_process is None)
            if self._hoyolab_export_process is None:
                self.btn_hoyolab_export.setToolTip("")
            else:
                self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_running_tooltip"))
            self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_READY_STYLE)
            return

        self.hoyolab_auth_label.setVisible(True)
        self.btn_hoyolab_login.setVisible(True)
        self.btn_hoyolab_login.setText(tr("hoyolab.login_button"))
        self.hoyolab_auth_box.setVisible(True)
        self.btn_hoyolab_switch.setVisible(False)
        self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_WARNING_STYLE)
        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip(tr("hoyolab.auth_required_tooltip"))

        if status == AuthStatus.PROFILE_LOCKED:
            self.hoyolab_auth_label.setText(tr("hoyolab.profile_busy"))
            self.btn_hoyolab_login.setEnabled(self._hoyolab_login_process is None)
            QTimer.singleShot(2000, self.refresh_hoyolab_auth_status)
            return

        self.hoyolab_auth_label.setText(tr("hoyolab.not_logged_in"))
        self.btn_hoyolab_login.setEnabled(self._hoyolab_login_process is None)

    def open_hoyolab_login(self):
        if self._hoyolab_login_process is not None:
            return

        try:
            self._hoyolab_login_process = open_login_browser(HOYOLAB_PROFILE_DIR)
        except Exception as exc:
            QMessageBox.warning(self, tr("common.hoyolab"), tr("hoyolab.open_browser_failed", error=exc))
            return

        self.hoyolab_auth_label.setText(tr("hoyolab.login_browser_open"))
        self.btn_hoyolab_login.setText(tr("hoyolab.login_waiting_button"))
        self.btn_hoyolab_login.setEnabled(False)
        self._hoyolab_auth_timer.start()

    def poll_hoyolab_login_browser(self):
        if self._hoyolab_login_process is None:
            self._hoyolab_auth_timer.stop()
            self.refresh_hoyolab_auth_status()
            return

        if self._hoyolab_login_process.poll() is None:
            return

        self._hoyolab_login_process = None
        self._hoyolab_auth_timer.stop()
        self.refresh_hoyolab_auth_status()

    def change_hoyolab_account(self):
        if self._hoyolab_login_process is not None:
            QMessageBox.information(
                self,
                tr("common.hoyolab"),
                tr("hoyolab.close_browser_before_switch"),
            )
            return

        try:
            reset_profile(HOYOLAB_PROFILE_DIR, HOYOLAB_EXPORT_DIR)
            clear_hoyolab_current_data()
        except Exception as exc:
            QMessageBox.warning(self, tr("common.hoyolab"), tr("hoyolab.reset_failed", error=exc))
            return

        self.safe_update_grids()
        self.refresh_hoyolab_auth_status()
        self.open_hoyolab_login()

    def run_hoyolab_export(self):
        if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
            QMessageBox.information(
                self,
                tr("common.hoyolab"),
                tr("hoyolab.auth_not_found"),
            )
            self.refresh_hoyolab_auth_status()
            return

        if self._hoyolab_export_process is not None:
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

            if line.startswith("[STATUS] "):
                self._set_hoyolab_loader_status(line.replace("[STATUS] ", "", 1).strip())

    def on_hoyolab_import_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        process = self._hoyolab_export_process

        if process is not None:
            self.read_hoyolab_import_output()

            if self._hoyolab_import_output_buffer.strip():
                print(self._hoyolab_import_output_buffer.strip())
                self._hoyolab_import_output_buffer = ""

            process.deleteLater()

        self._hoyolab_export_process = None

        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip(tr("hoyolab.import_cleanup_tooltip"))
        QTimer.singleShot(HOYOLAB_IMPORT_COOLDOWN_MS, self._finish_hoyolab_import_cooldown)

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            if self._hoyolab_loader is not None:
                self._hoyolab_loader.finish()

            self.safe_update_grids()
            self._close_hoyolab_loader()
            return

        self._close_hoyolab_loader()
        QMessageBox.warning(
            self,
            tr("common.hoyolab"),
            tr("hoyolab.import_failed"),
        )

    def build_left_panel(self):
        left = QVBoxLayout()

        self.hoyolab_auth_box = QWidget()
        self.hoyolab_auth_box.setObjectName("hoyolab_auth_box")
        auth_layout = QVBoxLayout(self.hoyolab_auth_box)
        auth_layout.setContentsMargins(8, 8, 8, 8)
        auth_layout.setSpacing(8)
        self.hoyolab_auth_label = QLabel("")
        self.hoyolab_auth_label.setWordWrap(True)
        auth_buttons = QHBoxLayout()
        auth_buttons.setContentsMargins(0, 0, 0, 0)
        auth_buttons.setSpacing(8)
        self.btn_hoyolab_login = QPushButton(tr("hoyolab.login_button"))
        self.btn_hoyolab_login.setMinimumHeight(30)
        self.btn_hoyolab_login.clicked.connect(self.open_hoyolab_login)
        self.btn_hoyolab_switch = QPushButton(tr("hoyolab.switch_account"))
        self.btn_hoyolab_switch.setMinimumHeight(30)
        self.btn_hoyolab_switch.clicked.connect(self.change_hoyolab_account)
        auth_buttons.addWidget(self.btn_hoyolab_login)
        auth_buttons.addWidget(self.btn_hoyolab_switch)
        auth_layout.addWidget(self.hoyolab_auth_label)
        auth_layout.addLayout(auth_buttons)
        self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_WARNING_STYLE)

        self.btn_hoyolab_export = QPushButton(tr("hoyolab.import_button"))
        self.btn_hoyolab_export.clicked.connect(self.run_hoyolab_export)

        self.btn_clear_assets = QPushButton(tr("asset_panel.clear"))
        self.btn_clear_assets.clicked.connect(self.clear_assets)

        left.addWidget(self.hoyolab_auth_box)
        self.weapon_title_label = QLabel(tr("asset_panel.weapons"))
        left.addWidget(self.weapon_title_label)
        self.weapon_area = QScrollArea()
        self.weapon_area.setWidgetResizable(True)
        self.weapon_widget = QWidget()
        self.weapon_grid = QGridLayout(self.weapon_widget)
        self.weapon_area.setWidget(self.weapon_widget)
        left.addWidget(self.weapon_area, 1)

        self.char_title_label = QLabel(tr("asset_panel.characters"))
        left.addWidget(self.char_title_label)
        self.char_area = QScrollArea()
        self.char_area.setWidgetResizable(True)
        self.char_widget = QWidget()
        self.char_grid = QGridLayout(self.char_widget)
        self.char_area.setWidget(self.char_widget)
        left.addWidget(self.char_area, 3)

        left.addWidget(self.btn_hoyolab_export)
        left.addWidget(self.btn_clear_assets)
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
        self.btn_hoyolab_login.setText(tr("hoyolab.login_button"))
        self.btn_hoyolab_switch.setText(tr("hoyolab.switch_account"))
        self.btn_hoyolab_export.setText(tr("hoyolab.import_button"))
        self.btn_clear_assets.setText(tr("asset_panel.clear"))
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

        self.refresh_hoyolab_auth_status()

    def _clear_grid(self, grid):
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def load_hoyolab_tooltips(self) -> tuple[dict[str, str], dict[str, str]]:
        char_tooltips: dict[str, str] = {}
        weapon_tooltips: dict[str, str] = {}

        if not HOYOLAB_MANIFEST_FILE.exists():
            return char_tooltips, weapon_tooltips

        try:
            with open(HOYOLAB_MANIFEST_FILE, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as exc:
            print(f"Failed to load HoYoLAB manifest tooltips: {exc}")
            return char_tooltips, weapon_tooltips

        for item in manifest.get("characterAssets", []):
            crop = item.get("crop")
            tooltip = item.get("tooltip")
            if crop and tooltip:
                char_tooltips[os.path.basename(crop)] = tooltip

        for item in manifest.get("weaponAssets", []):
            crop = item.get("crop")
            tooltip = item.get("tooltip")
            if crop and tooltip:
                weapon_tooltips[os.path.basename(crop)] = tooltip

        return char_tooltips, weapon_tooltips

    def _reload_icon_grid(self, directory, grid, container, area, icon_size, spacing, tooltips=None):
        self._clear_grid(grid)
        if not os.path.exists(directory):
            container.adjustSize()
            return

        files = [f for f in sorted(os.listdir(directory)) if f.lower().endswith(".png")]
        if not files:
            container.adjustSize()
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
        tooltips = tooltips or {}

        for c in range(cols):
            grid.setColumnMinimumWidth(c, icon_size)
            grid.setColumnStretch(c, 0)

        for i, filename in enumerate(files):
            try:
                icon = DraggableIcon(os.path.join(directory, filename), icon_size)

                tooltip = tooltips.get(filename)
                if tooltip:
                    icon.setToolTip(tooltip)

                grid.addWidget(icon, i // cols, i % cols)
            except Exception as exc:
                print(f"Failed to load {filename}: {exc}")

        container.adjustSize()
        container.updateGeometry()
        area.viewport().update()

    def reload_characters(self):
        char_tooltips, _ = self.load_hoyolab_tooltips()
        self._reload_icon_grid(
            ASSETS_CHAR,
            self.char_grid,
            self.char_widget,
            self.char_area,
            72,
            3,
            char_tooltips,
        )

    def reload_weapons(self):
        _, weapon_tooltips = self.load_hoyolab_tooltips()
        self._reload_icon_grid(
            ASSETS_WEAP,
            self.weapon_grid,
            self.weapon_widget,
            self.weapon_area,
            48,
            6,
            weapon_tooltips,
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

    def clear_assets(self):
        clear_hoyolab_current_data()

        self.safe_update_grids()
        QMessageBox.information(
            self,
            tr("common.done"),
            tr("main.clear_finished"),
        )

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
