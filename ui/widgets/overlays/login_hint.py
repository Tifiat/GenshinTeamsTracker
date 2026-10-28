from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from localization import tr


class HoYoLABLoginHintOverlay(QDialog):
    def __init__(self, parent=None, target_screen=None):
        super().__init__(parent)
        self._target_screen = target_screen

        self.setWindowTitle(tr("common.hoyolab"))
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        if hasattr(Qt, "WindowTransparentForInput"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowDoesNotAcceptFocus)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowModality(Qt.NonModal)

        self.title_label = QLabel(tr("hoyolab.login_hint_title"))
        self.title_label.setAlignment(Qt.AlignLeft)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            """
            QLabel {
                color: #ffe2a8;
                font-size: 17px;
                font-weight: 700;
            }
            """
        )

        self.body_label = QLabel(tr("hoyolab.login_hint_body"))
        self.body_label.setAlignment(Qt.AlignLeft)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet(
            """
            QLabel {
                color: rgba(255, 248, 232, 230);
                font-size: 13px;
                line-height: 1.35;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)
        root.addWidget(self.title_label)
        root.addWidget(self.body_label)

        self.setStyleSheet(
            """
            QDialog {
                background-color: rgba(22, 20, 18, 236);
                border: 2px solid rgba(226, 202, 148, 210);
                border-radius: 12px;
            }
            """
        )

        self.resize(420, 128)

    def showEvent(self, event):
        super().showEvent(event)
        self.position_on_screen()

    def set_target_screen(self, screen) -> None:
        self._target_screen = screen
        self.position_on_screen()

    def position_on_screen(self) -> None:
        screen = self._target_screen or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        margin = 26
        self.move(
            geometry.right() - self.width() - margin,
            geometry.top() + margin,
        )

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("common.hoyolab"))
        self.title_label.setText(tr("hoyolab.login_hint_title"))
        self.body_label.setText(tr("hoyolab.login_hint_body"))
        self.position_on_screen()
