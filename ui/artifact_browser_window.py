from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.artifact_queries import (
    ARTIFACT_POSITIONS,
    add_artifact_tag,
    db_exists,
    list_artifact_tags,
    list_artifacts,
    remove_artifact_tag,
)
from localization import tr


CARD_STYLE = """
QFrame#artifact_card {
    border: 1px solid #333845;
    border-radius: 8px;
    background: #202228;
}
QFrame#artifact_card[selected="true"] {
    border: 2px solid #4e91ff;
    background: #252936;
}
QFrame#artifact_card QLabel {
    color: #eeeeee;
}
"""

DETAIL_STYLE = """
QFrame#artifact_detail_panel {
    border: 1px solid #333845;
    border-radius: 8px;
    background: #202228;
}
QFrame#artifact_detail_panel QLabel {
    color: #eeeeee;
}
"""

FILTER_COMBO_WIDTH = 145


class ArtifactCard(QFrame):
    clicked = Signal(int)

    def __init__(self, artifact: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.artifact = artifact
        self.artifact_id = int(artifact["id"])
        self.setObjectName("artifact_card")
        self.setProperty("selected", False)
        self.setStyleSheet(CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(58, 58)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_icon(artifact.get("icon_path"))
        layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = QLabel(self._title_text(artifact))
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        text_layout.addWidget(title)

        main = QLabel(self._main_text(artifact))
        main.setWordWrap(True)
        text_layout.addWidget(main)

        footer = QLabel(self._footer_text(artifact))
        footer.setWordWrap(True)
        footer.setStyleSheet("color: #b7bdc9;")
        text_layout.addWidget(footer)

        layout.addLayout(text_layout, 1)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.artifact_id)
        super().mousePressEvent(event)

    def _set_icon(self, icon_path: str | None) -> None:
        if icon_path and Path(icon_path).exists():
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(
                        QSize(58, 58),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return

        self.icon_label.setText("★")
        self.icon_label.setStyleSheet(
            "border: 1px solid #3d4351; border-radius: 6px; color: #d7c06a;"
        )

    @staticmethod
    def _title_text(artifact: dict[str, Any]) -> str:
        set_name = artifact.get("set_name") or artifact.get("name") or ""
        pos_name = artifact.get("pos_name") or ""
        rarity = int(artifact.get("rarity") or 0)
        return f"{'★' * rarity} {set_name}\n{pos_name}".strip()

    @staticmethod
    def _main_text(artifact: dict[str, Any]) -> str:
        main_name = artifact.get("main_property_name") or "—"
        main_value = artifact.get("main_property_value") or ""
        level = int(artifact.get("level") or 0)
        return f"+{level} · {main_name} {main_value}".strip()

    @staticmethod
    def _footer_text(artifact: dict[str, Any]) -> str:
        character_name = artifact.get("character_name") or tr("artifacts.unequipped")
        tags = artifact.get("tags") or []
        tag_text = ", ".join(tags) if tags else tr("artifacts.no_tags")
        return f"{character_name}\n{tag_text}"


class ArtifactBrowserWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("artifacts.window_title"))
        self.resize(1100, 720)

        self._artifacts: list[dict[str, Any]] = []
        self._cards: dict[int, ArtifactCard] = {}
        self._selected_artifact_id: int | None = None
        self._updating_filters = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_filters(root)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.grid = QGridLayout(self.scroll_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.scroll_area.setWidget(self.scroll_widget)
        body.addWidget(self.scroll_area, 3)

        self._build_detail_panel(body)
        root.addLayout(body, 1)

        self.reload()

    def _build_filters(self, parent_layout: QVBoxLayout) -> None:
        filters = QHBoxLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("artifacts.search_placeholder"))
        self.search_input.textChanged.connect(self.reload)
        filters.addWidget(self.search_input, 1)

        self.pos_combo = QComboBox()
        self.pos_combo.setMinimumWidth(FILTER_COMBO_WIDTH)
        self.pos_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.pos_combo)

        self.rarity_combo = QComboBox()
        self.rarity_combo.setMinimumWidth(FILTER_COMBO_WIDTH)
        self.rarity_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.rarity_combo)

        self.equipped_combo = QComboBox()
        self.equipped_combo.setMinimumWidth(FILTER_COMBO_WIDTH)
        self.equipped_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.equipped_combo)

        self.tag_filter_combo = QComboBox()
        self.tag_filter_combo.setMinimumWidth(FILTER_COMBO_WIDTH)
        self.tag_filter_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.tag_filter_combo)

        self.refresh_button = QPushButton(tr("artifacts.refresh"))
        self.refresh_button.clicked.connect(self.reload)
        filters.addWidget(self.refresh_button)

        self.close_button = QPushButton(tr("common.close"))
        self.close_button.clicked.connect(self.close)
        filters.addWidget(self.close_button)

        parent_layout.addLayout(filters)
        self._populate_static_filters()
        self._reload_tag_filter()

    def _build_detail_panel(self, parent_layout: QHBoxLayout) -> None:
        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("artifact_detail_panel")
        self.detail_panel.setStyleSheet(DETAIL_STYLE)
        self.detail_panel.setMinimumWidth(330)
        self.detail_panel.setMaximumWidth(410)

        layout = QVBoxLayout(self.detail_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.summary_label = QLabel(tr("artifacts.select_hint"))
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.summary_label, 1)

        self.tags_title = QLabel(tr("artifacts.tags"))
        self.tags_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.tags_title)

        self.tag_list = QListWidget()
        self.tag_list.setMaximumHeight(110)
        layout.addWidget(self.tag_list)

        tag_row = QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.setSpacing(6)
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText(tr("artifacts.tag_placeholder"))
        self.tag_input.returnPressed.connect(self.add_selected_tag)
        tag_row.addWidget(self.tag_input, 1)

        self.add_tag_button = QPushButton(tr("artifacts.add_tag"))
        self.add_tag_button.clicked.connect(self.add_selected_tag)
        tag_row.addWidget(self.add_tag_button)
        layout.addLayout(tag_row)

        self.remove_tag_button = QPushButton(tr("artifacts.remove_tag"))
        self.remove_tag_button.clicked.connect(self.remove_selected_tag)
        layout.addWidget(self.remove_tag_button)

        parent_layout.addWidget(self.detail_panel, 1)

    def _populate_static_filters(self) -> None:
        self._updating_filters = True
        try:
            self.pos_combo.clear()
            self.pos_combo.addItem(tr("artifacts.all_slots"), None)
            for pos, label in ARTIFACT_POSITIONS.items():
                self.pos_combo.addItem(label, pos)

            self.rarity_combo.clear()
            self.rarity_combo.addItem(tr("artifacts.all_rarities"), None)
            for rarity in (5, 4, 3, 2, 1):
                self.rarity_combo.addItem(tr("artifacts.rarity_value", rarity=rarity), rarity)

            self.equipped_combo.clear()
            self.equipped_combo.addItem(tr("artifacts.all_equipment"), None)
            self.equipped_combo.addItem(tr("artifacts.equipped_only"), True)
            self.equipped_combo.addItem(tr("artifacts.unequipped_only"), False)
        finally:
            self._updating_filters = False

    def _reload_tag_filter(self) -> None:
        current = self.tag_filter_combo.currentData()
        self._updating_filters = True
        try:
            self.tag_filter_combo.clear()
            self.tag_filter_combo.addItem(tr("artifacts.all_tags"), "")
            for tag_name in list_artifact_tags():
                self.tag_filter_combo.addItem(tag_name, tag_name)

            if current:
                index = self.tag_filter_combo.findData(current)
                if index >= 0:
                    self.tag_filter_combo.setCurrentIndex(index)
        finally:
            self._updating_filters = False

    def reload(self) -> None:
        if self._updating_filters:
            return

        previous_selected_id = self._selected_artifact_id
        self._reload_tag_filter()

        if not db_exists():
            self._artifacts = []
            self._clear_grid()
            self.count_label_text(tr("artifacts.no_database"))
            self._show_no_selection(tr("artifacts.no_database"))
            return

        self._artifacts = list_artifacts(
            search=self.search_input.text(),
            pos=self.pos_combo.currentData(),
            rarity=self.rarity_combo.currentData(),
            equipped=self.equipped_combo.currentData(),
            tag=self.tag_filter_combo.currentData(),
        )
        self._render_cards()

        if self._artifacts:
            next_selected_id = previous_selected_id
            if next_selected_id not in {int(item["id"]) for item in self._artifacts}:
                next_selected_id = int(self._artifacts[0]["id"])
            self.select_artifact(next_selected_id)
        else:
            self._selected_artifact_id = None
            self._show_no_selection(tr("artifacts.empty"))

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

    def _render_cards(self) -> None:
        self._clear_grid()
        self.count_label_text(tr("artifacts.count", count=len(self._artifacts)))

        if not self._artifacts:
            return

        available_width = self.scroll_area.viewport().width() or self.scroll_area.width() or 680
        card_width = 255
        cols = max(1, available_width // card_width)

        for index, artifact in enumerate(self._artifacts):
            card = ArtifactCard(artifact)
            card.clicked.connect(self.select_artifact)
            self._cards[int(artifact["id"])] = card
            self.grid.addWidget(card, index // cols, index % cols)

        self.scroll_widget.adjustSize()

    def count_label_text(self, text: str) -> None:
        if not hasattr(self, "count_label"):
            self.count_label = QLabel()
            self.count_label.setStyleSheet("color: #b7bdc9;")
            self.layout().insertWidget(1, self.count_label)
        self.count_label.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._artifacts:
            selected = self._selected_artifact_id
            self._render_cards()
            if selected is not None:
                self.select_artifact(selected)

    def select_artifact(self, artifact_id: int) -> None:
        self._selected_artifact_id = artifact_id
        selected = self._artifact_by_id(artifact_id)
        for card_id, card in self._cards.items():
            card.set_selected(card_id == artifact_id)

        if not selected:
            self._show_no_selection(tr("artifacts.select_hint"))
            return

        self._fill_details(selected)

    def _artifact_by_id(self, artifact_id: int | None) -> dict[str, Any] | None:
        if artifact_id is None:
            return None
        for artifact in self._artifacts:
            if int(artifact["id"]) == artifact_id:
                return artifact
        return None

    def _show_no_selection(self, text: str) -> None:
        self.summary_label.setText(escape(text))
        self.tag_list.clear()
        self.tag_input.clear()

    def _fill_details(self, artifact: dict[str, Any]) -> None:
        substats = artifact.get("substats") or []
        substat_html = "".join(
            f"<li>{escape(item.get('property_name') or '—')}: "
            f"{escape(str(item.get('value') or ''))}"
            f"{self._roll_text(item.get('times'))}</li>"
            for item in substats
        )
        if not substat_html:
            substat_html = f"<li>{escape(tr('artifacts.no_substats'))}</li>"

        tags = artifact.get("tags") or []
        tag_text = ", ".join(tags) if tags else tr("artifacts.no_tags")
        character_name = artifact.get("character_name") or tr("artifacts.unequipped")

        html = f"""
        <h2>{escape(artifact.get('set_name') or artifact.get('name') or '—')}</h2>
        <p><b>{escape(artifact.get('pos_name') or '—')}</b> · {'★' * int(artifact.get('rarity') or 0)} · +{int(artifact.get('level') or 0)}</p>
        <p><b>{escape(tr('artifacts.main_stat'))}:</b><br>{escape(artifact.get('main_property_name') or '—')} {escape(artifact.get('main_property_value') or '')}</p>
        <p><b>{escape(tr('artifacts.substats'))}:</b></p>
        <ul>{substat_html}</ul>
        <p><b>{escape(tr('artifacts.equipped_on'))}:</b><br>{escape(character_name)}</p>
        <p><b>{escape(tr('artifacts.tags'))}:</b><br>{escape(tag_text)}</p>
        """
        self.summary_label.setText(html)

        self.tag_list.clear()
        for tag_name in tags:
            self.tag_list.addItem(tag_name)
        self.tag_input.clear()

    @staticmethod
    def _roll_text(times: Any) -> str:
        try:
            value = int(times)
        except (TypeError, ValueError):
            return ""
        return f" ×{value}" if value > 0 else ""

    def add_selected_tag(self) -> None:
        artifact_id = self._selected_artifact_id
        if artifact_id is None:
            return

        tag_name = self.tag_input.text().strip()
        if not tag_name:
            return

        try:
            add_artifact_tag(artifact_id, tag_name)
        except Exception as exc:
            QMessageBox.warning(self, tr("common.error"), tr("artifacts.tag_update_failed", error=exc))
            return

        self.reload()
        self.select_artifact(artifact_id)

    def remove_selected_tag(self) -> None:
        artifact_id = self._selected_artifact_id
        if artifact_id is None:
            return

        selected_items = self.tag_list.selectedItems()
        if not selected_items:
            return

        try:
            for item in selected_items:
                remove_artifact_tag(artifact_id, item.text())
        except Exception as exc:
            QMessageBox.warning(self, tr("common.error"), tr("artifacts.tag_update_failed", error=exc))
            return

        self.reload()
        self.select_artifact(artifact_id)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("artifacts.window_title"))
        self.search_input.setPlaceholderText(tr("artifacts.search_placeholder"))
        self.refresh_button.setText(tr("artifacts.refresh"))
        self.close_button.setText(tr("common.close"))
        self.tags_title.setText(tr("artifacts.tags"))
        self.tag_input.setPlaceholderText(tr("artifacts.tag_placeholder"))
        self.add_tag_button.setText(tr("artifacts.add_tag"))
        self.remove_tag_button.setText(tr("artifacts.remove_tag"))
        self._populate_static_filters()
        self.reload()
