from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.utils.toggle_switch import (  # noqa: E402
    FilterActionButton,
    FilterModeToggle,
    SortIconButton,
    ToggleSwitch,
)
from ui.utils.ui_palette import (  # noqa: E402
    UI_BG_APP,
    UI_BG_PANEL,
    UI_BORDER_DEFAULT,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
)


def _row(label: str, switch: QWidget, value_label: QLabel | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    text = QLabel(label)
    text.setFixedWidth(150)
    layout.addWidget(text)
    layout.addWidget(switch)
    if value_label is not None:
        layout.addWidget(value_label)
    layout.addStretch(1)
    return row


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(
        f"""
        QWidget {{
            background: {UI_BG_APP};
            color: {UI_TEXT_PRIMARY};
            font-family: Segoe UI;
            font-size: 13px;
        }}
        QFrame#Panel {{
            background: {UI_BG_PANEL};
            border: 1px solid {UI_BORDER_DEFAULT};
            border-radius: 6px;
        }}
        QLabel#Muted {{
            color: {UI_TEXT_MUTED};
        }}
        """
    )

    window = QWidget()
    window.setWindowTitle("ToggleSwitch Probe")
    root = QVBoxLayout(window)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)

    title = QLabel("ToggleSwitch probe")
    title.setStyleSheet("font-size: 18px; font-weight: 700;")
    root.addWidget(title)

    hint = QLabel("Click toggles, Space toggles, Left/Down = off, Right/Up = on.")
    hint.setObjectName("Muted")
    root.addWidget(hint)

    panel = QFrame()
    panel.setObjectName("Panel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(14, 14, 14, 14)
    panel_layout.setSpacing(12)

    value_label = QLabel("off")
    interactive = ToggleSwitch()
    interactive.toggled.connect(lambda checked: value_label.setText("on" if checked else "off"))
    panel_layout.addWidget(_row("Interactive", interactive, value_label))

    checked = ToggleSwitch()
    checked.setChecked(True)
    panel_layout.addWidget(_row("Initially on", checked))

    disabled_off = ToggleSwitch()
    disabled_off.setEnabled(False)
    panel_layout.addWidget(_row("Disabled off", disabled_off))

    disabled_on = ToggleSwitch()
    disabled_on.setChecked(True)
    disabled_on.setEnabled(False)
    panel_layout.addWidget(_row("Disabled on", disabled_on))

    compact_row = QWidget()
    compact_layout = QHBoxLayout(compact_row)
    compact_layout.setContentsMargins(0, 0, 0, 0)
    compact_layout.setSpacing(8)
    compact_layout.addWidget(QLabel("Dense row"))
    for index in range(4):
        toggle = ToggleSwitch()
        toggle.setChecked(index % 2 == 0)
        compact_layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignLeft)
    compact_layout.addStretch(1)
    panel_layout.addWidget(compact_row)

    panel_layout.addSpacing(6)
    section = QLabel("Filter / sort button concepts")
    section.setStyleSheet("font-weight: 700;")
    panel_layout.addWidget(section)

    filter_toggle = FilterModeToggle()
    panel_layout.addWidget(_row("Filter toggle", filter_toggle))

    sets_button = FilterActionButton("Filter sets active")
    sets_status = QLabel("Filter: normal")
    sets_status.setObjectName("Muted")
    sets_button.filterToggled.connect(
        lambda checked: sets_status.setText("Filter: exclude" if checked else "Filter: normal")
    )
    sets_button.actionClicked.connect(lambda: sets_status.setText("Sets button clicked"))
    panel_layout.addWidget(_row("Embedded in Sets", sets_button, sets_status))

    sort_button = SortIconButton()
    sort_state = QLabel("0")
    sort_state.setObjectName("Muted")

    def bump_sort_count() -> None:
        sort_button.setCount((sort_button.count() + 1) % 5)
        sort_state.setText(str(sort_button.count()))

    sort_button.clicked.connect(bump_sort_count)
    panel_layout.addWidget(_row("Sort button", sort_button, sort_state))

    matching_toggle = ToggleSwitch()
    matching_toggle.setChecked(True)
    panel_layout.addWidget(_row("Plain matching toggle", matching_toggle))

    root.addWidget(panel)
    window.resize(500, 460)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
