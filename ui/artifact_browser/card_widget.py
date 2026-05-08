from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from .stat_types import is_crit_type, stat_badge
from .models import ArtifactItem, ArtifactSubstat


CARD_STYLE = """
QFrame#artifact_card {
    border: 1px solid #3a3f4b;
    border-radius: 10px;
    background: #20232a;
}
QFrame#artifact_card:hover {
    border-color: #6f86b8;
    background: #252a33;
}
QLabel {
    color: #eeeeee;
    background: transparent;
}
QLabel#muted {
    color: #aab0bd;
}
QLabel#main_stat {
    color: #f0d58a;
    font-weight: 700;
    font-size: 13px;
}
QLabel#level_label {
    color: #f0d58a;
    font-weight: 700;
    font-size: 14px;
}
QLabel#badge_label {
    color: #d9e2ff;
    background: #2d3340;
    border: 1px solid #475066;
    border-radius: 6px;
    padding: 1px 6px;
    font-weight: 600;
}
QLabel#roll_label {
    color: #9aa4b5;
}
"""

CV_COLORS = [
    (0.0, 14.9, "#9b9b9b"),      # серый
    (15.0, 24.9, "#3f8cff"),     # синий
    (25.0, 34.9, "#b27cff"),     # фиолетовый
    (35.0, 44.9, "#ff9c47"),     # оранжевый
    (45.0, 49.9, "#ffe066"),     # желтый
    (50.0, 9999.0, "#62d0ff"),   # лазурный
]

_ICON_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def cached_scaled_pixmap(icon_path: Path, size: QSize) -> QPixmap | None:
    key = (str(icon_path.resolve()), size.width(), size.height())

    cached = _ICON_PIXMAP_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached

    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        return None

    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _ICON_PIXMAP_CACHE[key] = scaled
    return scaled

def cv_color(cv: float, *, artifact: ArtifactItem) -> str:
    effective_cv = cv

    if artifact.pos == 5 and is_crit_type(artifact.main_property_type):
        effective_cv = cv * 2

    for lower, upper, color in CV_COLORS:
        if lower <= effective_cv <= upper:
            return color

    return "#9b9b9b"


class ArtifactCard(QFrame):
    def __init__(self, artifact: ArtifactItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.artifact = artifact

        self.setObjectName("artifact_card")
        self.setStyleSheet(CARD_STYLE)
        self.setFixedSize(248, 138)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(5)

        main_stat = QLabel(self._main_stat_text())
        main_stat.setObjectName("main_stat")
        main_stat.setWordWrap(False)
        root.addWidget(main_stat)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        left = QVBoxLayout()
        left.setContentsMargins(0, 3, 0, 0)
        left.setSpacing(4)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(56, 56)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_icon(artifact.icon_path)
        left.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        cv_label = QLabel(self._cv_text())
        cv_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv_label.setStyleSheet(
            f"color: {cv_color(self.artifact.cv, artifact=self.artifact)};"
            "font-weight: 700;"
            "font-size: 14px;"
        )
        left.addWidget(cv_label)

        level_label = QLabel(f"+{artifact.level}")
        level_label.setObjectName("level_label")
        level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(level_label)

        left.addStretch()
        body.addLayout(left)

        stats = QVBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(4)

        for substat in artifact.substats[:4]:
            stats.addWidget(
                self._make_stat_row(
                    substat.property_type,
                    substat.value,
                    substat.times,
                )
            )

        while stats.count() < 4:
            stats.addWidget(QLabel(""))

        stats.addStretch()
        body.addLayout(stats, 1)

        root.addLayout(body, 1)

    def _set_icon(self, icon_path: Path | None) -> None:
        if icon_path and icon_path.exists():
            pixmap = cached_scaled_pixmap(icon_path, QSize(56, 56))
            if pixmap is not None:
                self.icon_label.setPixmap(pixmap)
                return

        self.icon_label.setText("★")
        self.icon_label.setStyleSheet(
            "border: 1px solid #4a5060; border-radius: 7px; color: #d8c36a;"
        )

    def _main_stat_text(self) -> str:
        return f"{self.artifact.main_property_name}: {self.artifact.main_property_value}"

    def _cv_text(self) -> str:
        if self.artifact.cv <= 0:
            return "CV —"
        return f"CV {self.artifact.cv:.1f}"

    def _make_stat_row(
            self,
            property_type: int,
            value: str,
            times: int | None,
    ) -> QWidget:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        badge = QLabel(stat_badge(property_type))
        badge.setObjectName("badge_label")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedWidth(48)
        row.addWidget(badge)

        value_label = QLabel(str(value or ""))
        value_label.setObjectName("muted")
        row.addWidget(value_label, 1)

        roll_text = self._roll_text(times)
        if roll_text:
            roll_label = QLabel(roll_text)
            roll_label.setObjectName("roll_label")
            row.addWidget(roll_label, alignment=Qt.AlignmentFlag.AlignRight)

        return row_widget

    @staticmethod
    def _roll_text(times: int | None) -> str:
        try:
            value = int(times or 0)
        except (TypeError, ValueError):
            return ""

        return f"×{value}" if value > 0 else ""