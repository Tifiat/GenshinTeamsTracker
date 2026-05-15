from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from localization import tr
from ui.widgets.overlays.progress_bar import ElementProgressBar


class HoYoLABLoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(tr("common.hoyolab"))
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        if hasattr(Qt, "WindowTransparentForInput"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowModality(Qt.NonModal)

        self._progress_value = 0.0
        self._target_progress = 0.0

        self.bar = ElementProgressBar(self)

        self.status_label = QLabel(tr("loader.preparing"))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #f4ead8;
                font-size: 16px;
                font-weight: 600;
            }
            """
        )

        self.notice_label = QLabel(tr("loader.notice"))
        self.notice_label.setAlignment(Qt.AlignCenter)
        self.notice_label.setWordWrap(True)
        self.notice_label.setStyleSheet(
            """
            QLabel {
                color: rgba(244, 234, 216, 210);
                font-size: 13px;
                line-height: 1.35;
                padding: 6px 10px;
                background-color: rgba(255, 255, 255, 22);
                border: 1px solid rgba(226, 202, 148, 70);
                border-radius: 10px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(16)
        root.addWidget(self.bar, alignment=Qt.AlignCenter)
        root.addWidget(self.status_label)
        root.addWidget(self.notice_label)

        self.setStyleSheet(
            """
            QDialog {
                background-color: rgba(22, 20, 18, 228);
                border: 1px solid rgba(226, 202, 148, 185);
                border-radius: 18px;
            }
            """
        )

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self.resize(620, 240)

    def set_status(self, text: str, progress: float | None = None) -> None:
        self.status_label.setText(text)

        if progress is not None:
            # Не откатываем прогресс назад, только двигаем цель вперёд.
            self._target_progress = max(
                self._target_progress,
                max(0.0, min(1.0, progress)),
            )

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("common.hoyolab"))
        self.notice_label.setText(tr("loader.notice"))

    def _tick(self) -> None:
        # Пока импорт не завершён, прогресс сам медленно ползёт вперёд,
        # чтобы loader не стоял ступеньками между статусами.
        if self._target_progress < 1.0:
            self._target_progress = min(0.94, self._target_progress + 0.0002)

        if self._progress_value >= self._target_progress:
            return

        distance = self._target_progress - self._progress_value

        # Чем дальше цель, тем быстрее догоняем.
        # Но всегда есть минимальная скорость, чтобы движение было постоянным.
        step = max(0.0007, distance * 0.035)

        self._progress_value = min(
            self._target_progress,
            self._progress_value + step,
        )
        self.bar.set_progress(self._progress_value)

    def finish(self) -> None:
        self._target_progress = 1.0
        self._progress_value = 1.0
        self.bar.set_progress(1.0)
