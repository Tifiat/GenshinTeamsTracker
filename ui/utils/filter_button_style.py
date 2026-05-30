from __future__ import annotations

from ui.utils.ui_palette import (
    UI_BG_FILTER_CHECKED,
    UI_BG_FILTER_HOVER,
    UI_BG_FILTER_IDLE,
    UI_BORDER_FILTER_SELECTED,
)


FILTER_BUTTON_SIZE = 30
FILTER_BUTTON_ICON_SIZE = 24
FILTER_BUTTON_BORDER_WIDTH = 2
FILTER_BUTTON_RADIUS = 15
FILTER_BUTTON_PADDING = 1
FILTER_BUTTON_CONTENT_SIZE = FILTER_BUTTON_SIZE - 2 * (
    FILTER_BUTTON_BORDER_WIDTH + FILTER_BUTTON_PADDING
)


def filter_button_style(
    object_name: str,
    *,
    content_size: int = FILTER_BUTTON_CONTENT_SIZE,
) -> str:
    return f"""
QPushButton#{object_name} {{
    min-width: {content_size}px;
    max-width: {content_size}px;
    min-height: {content_size}px;
    max-height: {content_size}px;
    border: {FILTER_BUTTON_BORDER_WIDTH}px solid transparent;
    border-radius: {FILTER_BUTTON_RADIUS}px;
    background-color: {UI_BG_FILTER_IDLE};
    padding: {FILTER_BUTTON_PADDING}px;
}}
QPushButton#{object_name}:hover {{
    background-color: {UI_BG_FILTER_HOVER};
}}
QPushButton#{object_name}:checked {{
    border-color: {UI_BORDER_FILTER_SELECTED};
    background-color: {UI_BG_FILTER_CHECKED};
}}
QPushButton#{object_name}[standardOnly="true"] {{
    border-color: {UI_BORDER_FILTER_SELECTED};
    background-color: {UI_BG_FILTER_CHECKED};
}}
"""
