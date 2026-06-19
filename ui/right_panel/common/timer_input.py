from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QKeyEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QWidget

from run_workspace.models import (
    adjust_abyss_timer_seconds_with_second_wheel,
    clamp_abyss_timer_edit_seconds,
)
from ui.right_panel.common.metrics import (
    ABYSS_TIMER_FRAME_WIDTH,
    ABYSS_TIMER_SEPARATOR_WIDTH,
    ABYSS_TIMER_SEGMENT_WIDTH,
)


class TimerSegmentEdit(QLineEdit):
    def __init__(
        self,
        timer: "CompactTimerInputWidget",
        segment: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timer = timer
        self.segment = segment
        self.setMaxLength(2)
        self.setValidator(QIntValidator(0, 99, self))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._timer.commit_segment(self)
            self.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self._timer.commit_segment(self)
            self._timer.focus_segment("minutes")
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self._timer.commit_segment(self)
            self._timer.focus_segment("seconds")
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._timer.adjust_segment(
                self.segment,
                1 if event.key() == Qt.Key.Key_Up else -1,
            )
            self.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.selectAll()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._timer.commit_segment(self)
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self.selectAll()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta_steps = event.angleDelta().y() // 120
        if delta_steps:
            self._timer.adjust_segment(self.segment, delta_steps)
            self.selectAll()
            event.accept()
            return
        super().wheelEvent(event)


class CompactTimerInputWidget(QFrame):
    seconds_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        minimum_seconds: int = 0,
        maximum_seconds: int = 600,
        initial_seconds: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TimerEditorFrame")
        self._minimum_seconds = max(0, int(minimum_seconds))
        self._maximum_limit = max(self._minimum_seconds, int(maximum_seconds))
        self._max_seconds = self._maximum_limit
        self._seconds_left = self._minimum_seconds
        self._updating = False
        self._segment_dirty = {"minutes": False, "seconds": False}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        self.min_edit = TimerSegmentEdit(self, "minutes")
        self.min_edit.setObjectName("TimerSegmentEdit")
        self.min_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.min_edit.setFixedWidth(ABYSS_TIMER_SEGMENT_WIDTH)

        colon = QLabel(":")
        colon.setObjectName("TimerSeparator")
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        colon.setFixedWidth(ABYSS_TIMER_SEPARATOR_WIDTH)

        self.sec_edit = TimerSegmentEdit(self, "seconds")
        self.sec_edit.setObjectName("TimerSegmentEdit")
        self.sec_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sec_edit.setFixedWidth(ABYSS_TIMER_SEGMENT_WIDTH)

        layout.addWidget(self.min_edit)
        layout.addWidget(colon)
        layout.addWidget(self.sec_edit)
        self.setFixedWidth(ABYSS_TIMER_FRAME_WIDTH)

        self.min_edit.textEdited.connect(
            lambda _text: self._mark_segment_dirty("minutes")
        )
        self.sec_edit.textEdited.connect(
            lambda _text: self._mark_segment_dirty("seconds")
        )
        self.set_seconds(initial_seconds)

    @property
    def seconds_left(self) -> int:
        return self._seconds_left

    def set_seconds(self, seconds: int, *, emit: bool = False) -> None:
        self._set_seconds(
            seconds,
            emit=emit,
            force_sync=True,
            force_emit=emit,
        )

    def set_max_seconds(self, maximum_seconds: int) -> None:
        self._max_seconds = max(
            self._minimum_seconds,
            min(self._maximum_limit, int(maximum_seconds)),
        )
        self._set_seconds(self._seconds_left, emit=False, force_sync=True)

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802
        self.min_edit.setReadOnly(read_only)
        self.sec_edit.setReadOnly(read_only)

    def adjust_seconds(self, delta_steps: int) -> None:
        self._set_seconds(
            adjust_abyss_timer_seconds_with_second_wheel(
                self._seconds_left,
                delta_steps,
                start_seconds=self._max_seconds,
                min_seconds=self._minimum_seconds,
            ),
            emit=True,
            force_sync=True,
        )

    def adjust_segment(self, segment: str, delta_steps: int) -> None:
        edit = self._edit_for_segment(segment)
        self.commit_segment(edit)
        multiplier = 60 if segment == "minutes" else 1
        self.adjust_seconds(int(delta_steps) * multiplier)

    def commit_segment(self, edit: TimerSegmentEdit) -> None:
        if self._updating:
            return
        segment = edit.segment
        if not self._segment_dirty[segment]:
            return
        value_text = edit.text().strip()
        if not value_text.isdigit():
            self._segment_dirty[segment] = False
            self._sync_segment_texts()
            return
        value = int(value_text)
        minutes, seconds = divmod(self._seconds_left, 60)
        if segment == "minutes":
            minutes = value
        else:
            seconds = min(value, 59)
        self._segment_dirty[segment] = False
        self._set_seconds(
            minutes * 60 + seconds,
            emit=True,
            force_sync=True,
            force_emit=True,
        )

    def focus_segment(self, segment: str) -> None:
        destination = self._edit_for_segment(segment)
        focused = self.focusWidget()
        if isinstance(focused, TimerSegmentEdit):
            self.commit_segment(focused)
        destination.setFocus(Qt.FocusReason.TabFocusReason)
        destination.selectAll()

    def _edit_for_segment(self, segment: str) -> TimerSegmentEdit:
        return self.min_edit if segment == "minutes" else self.sec_edit

    def _mark_segment_dirty(self, segment: str) -> None:
        if not self._updating:
            self._segment_dirty[segment] = True

    def _set_seconds(
        self,
        seconds: int,
        *,
        emit: bool,
        force_sync: bool = False,
        force_emit: bool = False,
    ) -> None:
        value = clamp_abyss_timer_edit_seconds(
            seconds,
            start_seconds=self._max_seconds,
            min_seconds=self._minimum_seconds,
        )
        changed = value != self._seconds_left
        self._seconds_left = value
        if force_sync or changed or not any(self._segment_dirty.values()):
            self._sync_segment_texts()
        if emit and (changed or force_emit):
            self.seconds_changed.emit(value)

    def _sync_segment_texts(self) -> None:
        minutes, remainder = divmod(self._seconds_left, 60)
        self._updating = True
        try:
            self.min_edit.setText(f"{minutes:02d}")
            self.sec_edit.setText(f"{remainder:02d}")
            self._segment_dirty["minutes"] = False
            self._segment_dirty["seconds"] = False
        finally:
            self._updating = False


__all__ = ["CompactTimerInputWidget", "TimerSegmentEdit"]
