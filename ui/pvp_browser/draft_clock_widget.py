"""Small retained clock surface; ticks never rebuild the draft board."""
from math import ceil

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from localization import tr


def _time(value):
    seconds = max(0, ceil(value / 1000))
    return f"{seconds // 60}:{seconds % 60:02d}"


class DraftClockWidget(QFrame):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._display = None
        self.setObjectName("pvp_draft_action_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 8)
        self.turn_label = QLabel()
        self.reserve_label = QLabel()
        self.notice_label = QLabel()
        self.reserve_label.setMinimumHeight(32)
        self.notice_label.setMinimumHeight(32)
        for label in (self.turn_label, self.reserve_label, self.notice_label):
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            layout.addWidget(label)
        self.pause_button = QPushButton()
        self.pause_button.setObjectName("pvp_secondary_button")
        self.pause_button.clicked.connect(workspace.toggle_draft_clock_pause)
        layout.addWidget(self.pause_button)
        workspace.draft_clock_changed.connect(self.set_clock)
        self.set_clock(workspace.draft_clock_snapshot())

    def set_clock(self, snapshot):
        visible = bool(snapshot is not None and not snapshot.finished
                       and (snapshot.running or snapshot.paused or snapshot.expired))
        display = (visible, snapshot.active_seat, _time(snapshot.pick_remaining_ms),
                   tuple(_time(snapshot.reserve_remaining_ms[seat]) for seat in ("player_1", "player_2")),
                   snapshot.paused, snapshot.expired) if snapshot is not None else (False,)
        if display == self._display:
            return
        self._display = display
        self.setVisible(visible)
        if not visible:
            return
        seat = tr("app_shell.pvp.draft." + snapshot.active_seat) if snapshot.active_seat else ""
        self.turn_label.setText(tr("app_shell.pvp.clock.turn").format(seat=seat, time=_time(snapshot.pick_remaining_ms)))
        self.reserve_label.setText(tr("app_shell.pvp.clock.reserves").format(
            p1=_time(snapshot.reserve_remaining_ms["player_1"]),
            p2=_time(snapshot.reserve_remaining_ms["player_2"])))
        key = "paused" if snapshot.paused else "expired" if snapshot.expired else "running" if snapshot.running else "disabled"
        self.notice_label.setText(tr("app_shell.pvp.clock." + key))
        self.pause_button.setText(tr("app_shell.pvp.clock.resume" if snapshot.paused else "app_shell.pvp.clock.pause"))
        self.pause_button.setEnabled(not snapshot.finished and (snapshot.paused or snapshot.running or snapshot.expired))

    def retranslate_ui(self):
        self._display = None
        self.set_clock(self.workspace.draft_clock_snapshot())
