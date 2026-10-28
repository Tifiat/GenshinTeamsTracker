from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from localization import tr


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOADER_ASSETS_DIR = PROJECT_ROOT / "assets" / "loader"

GREY_LOADER_PATH = LOADER_ASSETS_DIR / "grey_ldr.png"
COLOR_LOADER_PATH = LOADER_ASSETS_DIR / "color_ldr.png"


class ElementProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.grey = QPixmap(str(GREY_LOADER_PATH))
        self.color = QPixmap(str(COLOR_LOADER_PATH))
        self.progress = 0.0

        self.setFixedSize(540, 82)

    def set_progress(self, value: float) -> None:
        self.progress = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self.grey.isNull() or self.color.isNull():
            painter.drawText(self.rect(), Qt.AlignCenter, tr("loader.fallback"))
            return

        source_size = self.grey.size()
        target = self.rect()

        scaled = source_size.scaled(
            target.size(),
            Qt.KeepAspectRatio,
        )

        x = target.x() + (target.width() - scaled.width()) // 2
        y = target.y() + (target.height() - scaled.height()) // 2
        target = target.adjusted(0, 0, 0, 0)
        target.setRect(x, y, scaled.width(), scaled.height())

        painter.drawPixmap(target, self.grey)

        clip_width = int(target.width() * self.progress)
        if clip_width <= 0:
            return

        painter.save()
        painter.setClipRect(target.left(), target.top(), clip_width, target.height())
        painter.drawPixmap(target, self.color)
        painter.restore()
