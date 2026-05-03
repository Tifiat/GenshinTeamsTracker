import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.auth import AuthStatus, get_auth_status, open_login_browser, reset_profile
from ui.run_history_window import RunHistoryWindow
from ui.widgets.drag import DraggableIcon
from ui.widgets.team import TeamSlot
from ui.widgets.timers import AbyssFloorRow


ASSETS_CHAR = "assets/hd/characters"
ASSETS_WEAP = "assets/hd/weapons"
STATE_FILE = "state.json"
RUNS_FILE = "runs_history.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOYOLAB_PROFILE_DIR = PROJECT_ROOT / "hoyolab_export" / "profile"
HOYOLAB_EXPORT_DIR = PROJECT_ROOT / "hoyolab_export"
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
        self.setWindowTitle("Genshin Teams Tracker")
        self.resize(1400, 800)

        self.main = QHBoxLayout(self)
        self.floors = []
        self.teams = []

        self.ctrl_pressed = False
        self.pending_grid_updates = False
        self._resize_timer = None
        self._ui_ready = False
        self._initial_grid_built = False
        self._run_history_window = None
        self._hoyolab_login_process = None
        self._hoyolab_export_process = None
        self._hoyolab_auth_timer = QTimer(self)
        self._hoyolab_auth_timer.setInterval(1000)
        self._hoyolab_auth_timer.timeout.connect(self.poll_hoyolab_login_browser)
        self._hoyolab_export_timer = QTimer(self)
        self._hoyolab_export_timer.setInterval(1000)
        self._hoyolab_export_timer.timeout.connect(self.poll_hoyolab_export)

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
            self.btn_hoyolab_switch.setText("Сменить аккаунт")
            self.btn_hoyolab_export.setEnabled(self._hoyolab_export_process is None)
            self.btn_hoyolab_export.setToolTip("")
            self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_READY_STYLE)
            return

        self.hoyolab_auth_label.setVisible(True)
        self.btn_hoyolab_login.setVisible(True)
        self.btn_hoyolab_login.setText("Авторизоваться")
        self.hoyolab_auth_box.setVisible(True)
        self.btn_hoyolab_switch.setVisible(False)
        self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_WARNING_STYLE)
        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip("Authorize HoYoLAB first")

        if status == AuthStatus.PROFILE_LOCKED:
            self.hoyolab_auth_label.setText(
                "Профиль HoYoLAB сейчас занят. Если окно авторизации открыто, закройте его. "
                "После закрытия приложение проверит вход еще раз."
            )
            self.btn_hoyolab_login.setEnabled(self._hoyolab_login_process is None)
            QTimer.singleShot(2000, self.refresh_hoyolab_auth_status)
            return

        self.hoyolab_auth_label.setText(
            "Вход в HoYoLAB не обнаружен. Авторизуйтесь и закройте окно браузера."
        )
        self.btn_hoyolab_login.setEnabled(self._hoyolab_login_process is None)

    def open_hoyolab_login(self):
        if self._hoyolab_login_process is not None:
            return

        try:
            self._hoyolab_login_process = open_login_browser(HOYOLAB_PROFILE_DIR)
        except Exception as exc:
            QMessageBox.warning(self, "HoYoLAB", f"Could not open browser: {exc}")
            return

        self.hoyolab_auth_label.setText(
            "Окно HoYoLAB открыто. Войдите в аккаунт, убедитесь что вход выполнен, "
            "затем закройте браузер."
        )
        self.btn_hoyolab_login.setText("Ожидаю закрытия браузера")
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
                "HoYoLAB",
                "Close the current HoYoLAB browser window before changing account.",
            )
            return

        try:
            reset_profile(HOYOLAB_PROFILE_DIR, HOYOLAB_EXPORT_DIR)
        except Exception as exc:
            QMessageBox.warning(self, "HoYoLAB", f"Could not reset profile: {exc}")
            return

        self.refresh_hoyolab_auth_status()
        self.open_hoyolab_login()

    def run_hoyolab_export(self):
        if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
            QMessageBox.information(
                self,
                "HoYoLAB",
                "HoYoLAB authorization was not found. Please authorize first and check "
                "that the HoYoLAB page shows your account before closing the browser.",
            )
            self.refresh_hoyolab_auth_status()
            return

        if self._hoyolab_export_process is not None:
            return

        try:
            self._hoyolab_export_process = subprocess.Popen(
                [sys.executable, "-m", "hoyolab_export.run_manual_export"],
                cwd=str(PROJECT_ROOT),
            )
        except Exception as exc:
            QMessageBox.warning(self, "HoYoLAB", f"Could not start export: {exc}")
            self._hoyolab_export_process = None
            self.refresh_hoyolab_auth_status()
            return

        self.btn_hoyolab_export.setEnabled(False)
        self.btn_hoyolab_export.setToolTip("HoYoLAB export is running")
        self._hoyolab_export_timer.start()

    def poll_hoyolab_export(self):
        if self._hoyolab_export_process is None:
            self._hoyolab_export_timer.stop()
            self.refresh_hoyolab_auth_status()
            return

        if self._hoyolab_export_process.poll() is None:
            return

        exit_code = self._hoyolab_export_process.returncode
        self._hoyolab_export_process = None
        self._hoyolab_export_timer.stop()
        self.refresh_hoyolab_auth_status()

        if exit_code == 0:
            QMessageBox.information(self, "HoYoLAB", "Export finished.")
        else:
            QMessageBox.warning(
                self,
                "HoYoLAB",
                "Export failed. Check that you are logged in to HoYoLAB, then try again. "
                "The console log may contain additional details.",
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
        self.btn_hoyolab_login = QPushButton("Авторизоваться")
        self.btn_hoyolab_login.setMinimumHeight(30)
        self.btn_hoyolab_login.clicked.connect(self.open_hoyolab_login)
        self.btn_hoyolab_switch = QPushButton("Сменить аккаунт")
        self.btn_hoyolab_switch.setMinimumHeight(30)
        self.btn_hoyolab_switch.clicked.connect(self.change_hoyolab_account)
        auth_buttons.addWidget(self.btn_hoyolab_login)
        auth_buttons.addWidget(self.btn_hoyolab_switch)
        auth_layout.addWidget(self.hoyolab_auth_label)
        auth_layout.addLayout(auth_buttons)
        self.hoyolab_auth_box.setStyleSheet(HOYOLAB_AUTH_WARNING_STYLE)

        self.btn_hoyolab_export = QPushButton("HoYoLAB export")
        self.btn_hoyolab_export.clicked.connect(self.run_hoyolab_export)

        btn_clear = QPushButton("Clear characters and weapons")
        btn_clear.clicked.connect(self.clear_assets)

        left.addWidget(self.hoyolab_auth_box)
        left.addWidget(QLabel("Weapons"))
        self.weapon_area = QScrollArea()
        self.weapon_area.setWidgetResizable(True)
        self.weapon_widget = QWidget()
        self.weapon_grid = QGridLayout(self.weapon_widget)
        self.weapon_area.setWidget(self.weapon_widget)
        left.addWidget(self.weapon_area, 1)

        left.addWidget(QLabel("Characters"))
        self.char_area = QScrollArea()
        self.char_area.setWidgetResizable(True)
        self.char_widget = QWidget()
        self.char_grid = QGridLayout(self.char_widget)
        self.char_area.setWidget(self.char_widget)
        left.addWidget(self.char_area, 3)

        left.addWidget(self.btn_hoyolab_export)
        left.addWidget(btn_clear)
        self.main.addLayout(left, 2)

    def build_right_panel(self):
        right = QVBoxLayout()

        for i in range(2):
            team = []
            right.addWidget(QLabel(f"Команда {i + 1}"))
            row = QHBoxLayout()
            for _ in range(4):
                slot = TeamSlot()
                team.append(slot)
                row.addWidget(slot)
            self.teams.append(team)
            right.addLayout(row)

        right.addSpacing(20)
        right.addWidget(QLabel("Таймеры бездны"))

        for i in range(1, 4):
            floor = AbyssFloorRow(i, self.calculate_abyss)
            self.floors.append(floor)
            right.addWidget(floor)

        self.total_label = QLabel("Итого: 0 сек")
        right.addWidget(self.total_label)

        btn_reset = QPushButton("Сбросить забег")
        btn_reset.clicked.connect(self.reset_run)
        right.addWidget(btn_reset)

        btn_save = QPushButton("Сохранить забег")
        btn_save.clicked.connect(self.save_run)
        right.addWidget(btn_save)

        btn_history = QPushButton("Открыть историю забегов")
        btn_history.clicked.connect(self.open_run_history)
        right.addWidget(btn_history)

        right.addStretch()
        self.main.addLayout(right, 1)

    def _clear_grid(self, grid):
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _reload_icon_grid(self, directory, grid, container, area, icon_size, spacing):
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

        for c in range(cols):
            grid.setColumnMinimumWidth(c, icon_size)
            grid.setColumnStretch(c, 0)

        for i, filename in enumerate(files):
            try:
                icon = DraggableIcon(os.path.join(directory, filename), icon_size)
                grid.addWidget(icon, i // cols, i % cols)
            except Exception as exc:
                print(f"Failed to load {filename}: {exc}")

        container.adjustSize()
        container.updateGeometry()
        area.viewport().update()

    def reload_characters(self):
        self._reload_icon_grid(ASSETS_CHAR, self.char_grid, self.char_widget, self.char_area, 72, 3)

    def reload_weapons(self):
        self._reload_icon_grid(ASSETS_WEAP, self.weapon_grid, self.weapon_widget, self.weapon_area, 48, 6)

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
        self.total_label.setText(f"Итого: {total} сек")
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
        for folder in ["assets/characters", "assets/weapons", "assets/hd/characters", "assets/hd/weapons", "debug"]:
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder, exist_ok=True)

        self.safe_update_grids()
        QMessageBox.information(self, "Готово", "Кропы, HD-иконки и debug очищены")

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

        self.total_label.setText("Итого: 0 сек")
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

