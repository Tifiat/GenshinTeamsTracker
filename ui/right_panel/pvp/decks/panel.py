from __future__ import annotations

from collections import defaultdict, deque

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.pvp.deck_preset import PvpDeckPreset
from ui.utils.icon_utils import auto_contrast_svg_icon, tinted_svg_pixmap
from ui.utils.marquee_label import MarqueeButton
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_STATE_DANGER, UI_STATE_SUCCESS
from ui.right_panel.pvp._shared import (
    PVP_DECKS_RIGHT_PANEL_STYLE,
    PVP_DECK_UI_ICON_BACKGROUND,
    PVP_DECK_UI_ICON_SIZE,
    _clear_layout,
)


class PvpDecksRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpDecksWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.pending_delete_deck_id = ""
        self.deck_row_frames: dict[str, QFrame] = {}
        self.selected_info_labels: dict[str, QLabel] = {}
        self._rules_meta_labels: dict[str, QLabel] = {}
        self._rules_line_sections: dict[str, tuple[QFrame, QVBoxLayout, list[QLabel]]] = {}
        self._requirement_rows: list[dict] = []
        self._settled_requirement_rows: tuple[dict, ...] = ()
        self._pending_row_heights: list[tuple[QLabel, int]] = []
        self._requirement_table: QGridLayout | None = None
        self._requirement_section: QFrame | None = None
        self._expanded_layout: QVBoxLayout | None = None
        self._expanded_info: QFrame | None = None
        self._details_geometry_width = 0
        self._reserved_geometry: dict[QWidget, tuple[int, bool]] = {}
        self._row_count_labels: dict[str, QLabel] = {}
        self._status_pixmaps = {
            "pass": tinted_svg_pixmap("check", 14, UI_STATE_SUCCESS),
            "fail": tinted_svg_pixmap("x", 14, UI_STATE_DANGER),
        }
        self.edit_name_edit: QLineEdit | None = None
        self.ruleset_button: QComboBox | None = None
        self.rules_refresh_button: QPushButton | None = None
        self.rules_update_button: QPushButton | None = None
        self._edit_shortcuts: list[QShortcut] = []
        self._preserved_edit_deck_id = ""
        self._preserved_edit_name = ""
        self._scroll_deck_id = ""
        self._restore_scroll_value = 0
        self._scroll_restore_timer = QTimer(self)
        self._scroll_restore_timer.setSingleShot(True)
        self._scroll_restore_timer.timeout.connect(self._restore_scroll_position)
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.export_profile_button = QPushButton()
        self.export_profile_button.setObjectName("pvp_secondary_button")
        self.export_profile_button.clicked.connect(self._on_export_profile)
        root.addWidget(self.export_profile_button)

        self.create_row_widget = QWidget()
        create_layout = QHBoxLayout(self.create_row_widget)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.setSpacing(6)
        self.create_name_edit = QLineEdit()
        self.create_name_edit.installEventFilter(self)
        create_layout.addWidget(self.create_name_edit, 1)

        self.create_button = QPushButton()
        self.create_button.setObjectName("icon_button")
        self.create_button.setIcon(self._ui_icon("plus"))
        self.create_button.clicked.connect(self._on_create_clicked)
        create_layout.addWidget(self.create_button)

        self.cancel_new_deck_button = QPushButton()
        self.cancel_new_deck_button.setObjectName("row_cancel_button")
        self.cancel_new_deck_button.setIcon(self._ui_icon("x"))
        self.cancel_new_deck_button.clicked.connect(self._on_cancel_new_clicked)
        create_layout.addWidget(self.cancel_new_deck_button)
        root.addWidget(self.create_row_widget)

        self.new_deck_info = QWidget()
        self.new_deck_info_layout = QVBoxLayout(self.new_deck_info)
        self.new_deck_info_layout.setContentsMargins(0, 0, 0, 0)

        self.deck_list_scroll = OverlayVerticalScrollArea()
        self.deck_list_scroll.setWidgetResizable(True)
        self.deck_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        list_content = QWidget()
        content_layout = QVBoxLayout(list_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        # New and saved deck details must share the same height-for-width scroll
        # boundary. Keeping new-deck rules in the fixed header crushes labels.
        content_layout.addWidget(self.new_deck_info)
        self.deck_list_content = QWidget()
        self.deck_list_layout = QVBoxLayout(self.deck_list_content)
        self.deck_list_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_list_layout.setSpacing(5)
        content_layout.addWidget(self.deck_list_content)
        content_layout.addStretch(1)
        self.deck_list_scroll.setWidget(list_content)
        root.addWidget(self.deck_list_scroll, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self._init_edit_shortcuts()
        self.create_name_edit.returnPressed.connect(self._on_create_clicked)
        self.workspace.state_changed.connect(self.refresh)
        details_changed = getattr(self.workspace, "details_changed", None)
        if details_changed is not None:
            details_changed.connect(self.refresh_details)
        self.workspace.save_edit_requested.connect(self._save_active_edit)
        self.workspace.cancel_edit_requested.connect(self._cancel_active_edit)
        self.retranslate_ui()

    def refresh(self) -> None:
        active = self.workspace.active_preset()
        deck_id = active.deck_id if active is not None else ""
        if deck_id != self._scroll_deck_id:
            self._restore_scroll_value = 0
        elif not self._scroll_restore_timer.isActive():
            self._restore_scroll_value = self.deck_list_scroll.verticalScrollBar().value()
        self._scroll_deck_id = deck_id
        self._capture_existing_edit_name()
        self._clear_stale_pending_delete()
        self._refresh_create_controls()
        self._rebuild_deck_list()
        status = self.workspace._last_status
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        self._sync_edit_shortcuts()
        self._scroll_restore_timer.start(0)

    def refresh_details(self) -> None:
        """Update the selected draft after a membership/allocation change."""
        preset = self.workspace.active_preset()
        if preset is None or self._expanded_layout is None:
            return
        scroll_value = self.deck_list_scroll.verticalScrollBar().value()
        self._scroll_restore_timer.stop()
        updates_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            self._reserve_details_geometry()
            state = self.workspace.rules_ui_state()
            self._update_rules_details(state)
            self.selected_info_labels["counts"].setText(
                tr("app_shell.pvp.decks.counts").format(
                    characters=len(preset.character_ids), weapons=len(preset.weapon_refs)
                )
            )
            self.selected_info_labels["validation"].setText(self._validation_text())
            count = self._row_count_labels.get(preset.deck_id)
            if count is not None:
                count.setText(f"({len(preset.character_ids) + len(preset.weapon_refs)})")
            status = self.workspace._last_status
            self.status_label.setText(status)
            self.status_label.setVisible(bool(status))
            self._activate_details_layout()
            self.deck_list_scroll.verticalScrollBar().setValue(scroll_value)
        finally:
            self.setUpdatesEnabled(updates_enabled)

    def _reserve_details_geometry(self) -> None:
        if not self.isVisible():
            return
        width = self.deck_list_scroll.viewport().width()
        if width != self._details_geometry_width:
            self._release_details_geometry()
            self._details_geometry_width = width
        widgets = [self._expanded_info, self._requirement_section,
                   *self.selected_info_labels.values()]
        for section, _layout, labels in self._rules_line_sections.values():
            widgets.extend((section, *labels))
        for widget in widgets:
            if widget is None or not widget.isVisibleTo(self):
                continue
            policy = widget.sizePolicy()
            if widget not in self._reserved_geometry:
                self._reserved_geometry[widget] = (widget.minimumHeight(), policy.retainSizeWhenHidden())
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
            widget.setMinimumHeight(max(widget.minimumHeight(), widget.height()))

    def _release_details_geometry(self) -> None:
        for widget, (height, retain) in self._reserved_geometry.items():
            widget.setMinimumHeight(height)
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(retain)
            widget.setSizePolicy(policy)
        self._reserved_geometry.clear()
        self._details_geometry_width = 0

    def _activate_details_layout(self) -> None:
        # The content layout activates dirty child layouts recursively. Avoid
        # forcing each descendant layout on every selection click.
        content = self.deck_list_scroll.widget()
        QCoreApplication.sendPostedEvents(content, QEvent.Type.LayoutRequest)
        content.layout().activate()
        QCoreApplication.sendPostedEvents(content, QEvent.Type.LayoutRequest)
        self.layout().activate()

    def resizeEvent(self, event) -> None:
        if event.size().width() != event.oldSize().width():
            self._release_details_geometry()
        super().resizeEvent(event)

    def _restore_scroll_position(self) -> None:
        self.deck_list_scroll.verticalScrollBar().setValue(self._restore_scroll_value)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.decks.title"))
        self.export_profile_button.setText(tr("app_shell.pvp.profile.export"))
        self.create_name_edit.setPlaceholderText(
            tr("app_shell.pvp.decks.create_placeholder")
        )
        self._install_button_tooltip(self.create_button, tr("artifact.build.new"))
        self._install_button_tooltip(
            self.cancel_new_deck_button,
            tr("artifact.build.cancel"),
        )
        self.refresh()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.create_name_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.workspace.is_editing:
                    self._save_active_edit()
                else:
                    self._on_create_clicked()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape:
                if self.workspace.is_new_deck_edit:
                    self._on_cancel_new_clicked()
                else:
                    self.create_name_edit.clear()
                event.accept()
                return True
        if (
            watched is self.edit_name_edit
            and event.type() == QEvent.Type.KeyPress
        ):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._save_existing_from(watched)
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_active_edit()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self.workspace.is_editing and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self._save_active_edit()
            event.accept()
            return
        if self.workspace.is_editing and event.key() == Qt.Key.Key_Escape:
            self._cancel_active_edit()
            event.accept()
            return
        if self.pending_delete_deck_id:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._confirm_delete_deck(self.pending_delete_deck_id)
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_delete_deck()
                event.accept()
                return
        super().keyPressEvent(event)

    def _init_edit_shortcuts(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._save_active_edit)
            shortcut.setEnabled(False)
            self._edit_shortcuts.append(shortcut)

        cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        cancel_shortcut.activated.connect(self._cancel_active_edit)
        cancel_shortcut.setEnabled(False)
        self._edit_shortcuts.append(cancel_shortcut)

    def _sync_edit_shortcuts(self) -> None:
        editing = self.workspace.is_editing
        for shortcut in self._edit_shortcuts:
            shortcut.setEnabled(editing)

    def _capture_existing_edit_name(self) -> None:
        self._preserved_edit_deck_id = ""
        self._preserved_edit_name = ""
        if not self.workspace.is_editing or self.workspace.is_new_deck_edit:
            return
        active_preset = self.workspace.active_preset()
        if active_preset is None or self.edit_name_edit is None:
            return
        self._preserved_edit_deck_id = active_preset.deck_id
        self._preserved_edit_name = self.edit_name_edit.text()

    def _refresh_create_controls(self) -> None:
        new_edit = self.workspace.is_new_deck_edit
        existing_edit = self.workspace.is_editing and not new_edit
        if new_edit:
            preset = self.workspace.active_preset()
            if preset is not None and not self.create_name_edit.text().strip():
                self.create_name_edit.setText(preset.name)
        elif not self.workspace.is_editing:
            if self.create_button.objectName() == "row_save_button":
                self.create_name_edit.clear()

        self.create_name_edit.setEnabled(not existing_edit)
        self.create_button.setEnabled(not existing_edit)
        self.create_button.setObjectName("row_save_button" if new_edit else "icon_button")
        self.create_button.setIcon(self._ui_icon("save" if new_edit else "plus"))
        self._install_button_tooltip(
            self.create_button,
            tr("artifact.build.save") if new_edit else tr("artifact.build.new"),
        )
        self.cancel_new_deck_button.setVisible(new_edit)
        for button in (self.create_button, self.cancel_new_deck_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.ensurePolished()
            button.sizeHint()

    def _rebuild_deck_list(self) -> None:
        self._release_details_geometry()
        self._release_pending_row_heights()
        _clear_layout(self.deck_list_layout)
        _clear_layout(self.new_deck_info_layout)
        self.deck_row_frames.clear()
        self.selected_info_labels.clear()
        self._rules_meta_labels.clear()
        self._rules_line_sections.clear()
        self._requirement_rows.clear()
        self._settled_requirement_rows = ()
        self._requirement_table = None
        self._requirement_section = None
        self._requirement_content = None
        self._requirement_row_shape = None
        self._expanded_layout = None
        self._expanded_info = None
        self._row_count_labels.clear()
        self.edit_name_edit = None
        self.ruleset_button = None
        self.rules_refresh_button = None
        self.rules_update_button = None

        self.new_deck_info.setVisible(self.workspace.is_new_deck_edit)
        if self.workspace.is_new_deck_edit:
            self._add_expanded_deck_info(
                self.new_deck_info_layout, self.workspace.active_preset()
            )

        if not self.workspace.presets:
            if not self.workspace.is_new_deck_edit:
                label = QLabel(tr("app_shell.pvp.decks.list_empty"))
                label.setObjectName("small_muted")
                label.setWordWrap(True)
                self.deck_list_layout.addWidget(label)
            self.deck_list_layout.addStretch(1)
            return

        for preset in self.workspace.presets:
            row = self._make_deck_row(preset)
            self.deck_list_layout.addWidget(row)
            self.deck_row_frames[preset.deck_id] = row
        self.deck_list_layout.addStretch(1)

    def _make_deck_row(self, preset: PvpDeckPreset) -> QFrame:
        selected = preset.deck_id == self.workspace.selected_deck_id
        pending = self.pending_delete_deck_id == preset.deck_id
        editing_this_row = (
            self.workspace.is_editing
            and not self.workspace.is_new_deck_edit
            and self.workspace.active_preset() is not None
            and self.workspace.active_preset().deck_id == preset.deck_id
        )

        row = QFrame()
        row.setObjectName("build_slot_row")
        row.setProperty("selectedDeck", selected or editing_this_row)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)
        outer.addLayout(top)

        if editing_this_row:
            name_input = QLineEdit()
            active_preset = self.workspace.active_preset()
            name_text = active_preset.name if active_preset is not None else ""
            if (
                active_preset is not None
                and self._preserved_edit_deck_id == active_preset.deck_id
            ):
                name_text = self._preserved_edit_name
            name_input.setText(name_text)
            name_input.setPlaceholderText(tr("app_shell.pvp.decks.create_placeholder"))
            name_input.installEventFilter(self)
            name_input.returnPressed.connect(lambda: self._save_existing_from(name_input))
            top.addWidget(name_input, 1)
            self.edit_name_edit = name_input
        else:
            select_button = MarqueeButton(preset.name)
            select_button.setCheckable(True)
            select_button.setChecked(selected)
            select_button.setEnabled(not self.workspace.is_editing)
            select_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self.workspace.select_deck(deck_id)
            )
            top.addWidget(select_button, 1)

        if pending:
            confirm_label = QLabel(tr("artifact.build.delete_confirm_short"))
            confirm_label.setObjectName("small_muted")
            top.addWidget(confirm_label)

            confirm_button = self._row_icon_button("check", tr("artifact.build.delete"))
            confirm_button.setObjectName("row_save_button")
            confirm_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self._confirm_delete_deck(deck_id)
            )
            self._prepare_row_action_button(confirm_button)
            top.addWidget(confirm_button)

            cancel_button = self._row_icon_button("x", tr("common.cancel"))
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.clicked.connect(self._cancel_delete_deck)
            self._prepare_row_action_button(cancel_button)
            top.addWidget(cancel_button)
            return row

        if editing_this_row:
            save_button = self._row_icon_button("save", tr("artifact.build.save"))
            save_button.setObjectName("row_save_button")
            save_button.clicked.connect(lambda _checked=False: self._save_existing_from(name_input))
            self._prepare_row_action_button(save_button)
            top.addWidget(save_button)

            cancel_button = self._row_icon_button("x", tr("artifact.build.cancel"))
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.clicked.connect(self._cancel_active_edit)
            self._prepare_row_action_button(cancel_button)
            top.addWidget(cancel_button)
        else:
            count_label = QLabel(f"({len(preset.character_ids) + len(preset.weapon_refs)})")
            count_label.setObjectName("small_muted")
            top.addWidget(count_label)
            self._row_count_labels[preset.deck_id] = count_label

            edit_button = self._row_icon_button("edit", tr("artifact.build.edit"))
            edit_button.clicked.connect(self.workspace.begin_edit)
            top.addWidget(edit_button)

            delete_button = self._row_icon_button("delete", tr("artifact.build.delete"))
            delete_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self._request_delete_deck(deck_id)
            )
            top.addWidget(delete_button)

        if selected or editing_this_row:
            self._add_expanded_deck_info(outer, preset if not editing_this_row else self.workspace.active_preset())

        return row

    def _add_expanded_deck_info(
        self,
        outer: QVBoxLayout,
        preset: PvpDeckPreset | None,
    ) -> None:
        if preset is None:
            return
        info = QFrame()
        info.setObjectName("pvp_deck_expanded_info")
        layout = QVBoxLayout(info)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._expanded_layout = layout
        self._expanded_info = info

        rules_state = self.workspace.rules_ui_state()
        rules_header = QHBoxLayout()
        rules_header.setContentsMargins(0, 0, 0, 0)
        rules_label = self._info_label(tr("app_shell.pvp.decks.rules_label"))
        rules_label.setObjectName("pvp_rules_heading")
        rules_header.addWidget(rules_label)
        rules_header.addStretch(1)
        layout.addLayout(rules_header)

        self.ruleset_button = QComboBox()
        self.ruleset_button.setObjectName("pvp_ruleset_chip")
        self.ruleset_button.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.ruleset_button.setMinimumContentsLength(12)
        options = rules_state.get("options", ())
        selected_id = str(rules_state.get("selected_id", ""))
        for option in options:
            self.ruleset_button.addItem(str(option["label"]), str(option["id"]))
        selected_index = self.ruleset_button.findData(selected_id)
        if selected_index < 0:
            saved_text = str(rules_state.get("source_title", "")).strip() or selected_id
            self.ruleset_button.insertItem(
                0,
                tr("app_shell.pvp.decks.rules_unlisted").format(source=saved_text),
                None,
            )
            self.ruleset_button.model().item(0).setEnabled(False)
            selected_index = 0
        self.ruleset_button.setCurrentIndex(selected_index)
        self.ruleset_button.setEnabled(
            bool(rules_state.get("editable")) and not bool(rules_state.get("loading"))
        )
        self.ruleset_button.activated.connect(self._on_ruleset_activated)
        layout.addWidget(self.ruleset_button)

        self.rules_refresh_button = QPushButton(
            tr(
                "app_shell.pvp.decks.rules_refresh"
                if rules_state.get("catalog_loaded")
                else "app_shell.pvp.decks.rules_load"
            )
        )
        self.rules_refresh_button.setObjectName("pvp_secondary_button")
        self.rules_refresh_button.setEnabled(not bool(rules_state.get("loading")))
        self.rules_refresh_button.clicked.connect(self.workspace.refresh_rules_catalog)
        layout.addWidget(self.rules_refresh_button)

        for name in ("loading", "source", "version", "freshness"):
            label = self._rules_detail_label("")
            layout.addWidget(label)
            self._rules_meta_labels[name] = label
        self.rules_update_button = QPushButton(tr("app_shell.pvp.decks.rules_update_button"))
        self.rules_update_button.setObjectName("pvp_secondary_button")
        self.rules_update_button.clicked.connect(self.workspace.update_ruleset)
        layout.addWidget(self.rules_update_button)

        self._add_rules_lines(layout, "rules_costs_heading", ())
        self._add_rules_lines(layout, "rules_requirements_heading", ())
        self._add_requirement_rows(layout, (), None)
        self._add_rules_lines(layout, "rules_issues_heading", ())
        self._add_rules_lines(layout, "rules_error_heading", ())
        self._update_rules_details(rules_state)

        counts_label = self._info_label(
            tr("app_shell.pvp.decks.counts").format(
                characters=len(preset.character_ids),
                weapons=len(preset.weapon_refs),
            )
        )
        counts_label.setWordWrap(True)
        layout.addWidget(counts_label)
        self.selected_info_labels["counts"] = counts_label

        validation_label = self._info_label(self._validation_text())
        validation_label.setWordWrap(True)
        layout.addWidget(validation_label)
        self.selected_info_labels["validation"] = validation_label

        outer.addWidget(info)

    def _on_ruleset_activated(self, index: int) -> None:
        if self.ruleset_button is None:
            return
        ruleset_id = self.ruleset_button.itemData(index)
        if ruleset_id:
            self.workspace.select_ruleset(str(ruleset_id))

    def _rules_detail_label(self, text: str) -> QLabel:
        label = self._info_label(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _add_rules_lines(self, layout: QVBoxLayout, heading_key: str, lines) -> None:
        section = QFrame()
        section.setObjectName("pvp_rules_section")
        section.setProperty("rulesSection", heading_key)
        content = QVBoxLayout(section)
        content.setContentsMargins(9, 8, 9, 8)
        content.setSpacing(6)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = self._rules_detail_label(tr("app_shell.pvp.decks." + heading_key))
        heading.setObjectName("pvp_rules_heading")
        content.addWidget(heading)
        layout.addWidget(section)
        self._rules_line_sections[heading_key] = (section, content, [])
        self._update_rules_lines(heading_key, lines)

    def _update_rules_lines(self, heading_key: str, lines) -> None:
        section, content, labels = self._rules_line_sections[heading_key]
        lines = tuple(str(line) for line in lines)
        while len(labels) < len(lines):
            label = self._rules_detail_label("")
            content.addWidget(label)
            labels.append(label)
        for index, label in enumerate(labels):
            if index < len(lines):
                label.setText(lines[index])
                label.show()
            else:
                label.hide()
        section.setVisible(bool(lines))

    def _update_rules_details(self, state: dict) -> None:
        loading = bool(state.get("loading"))
        source = str(state.get("source_title", "")).strip()
        version = str(state.get("version_text", "")).strip()
        freshness = str(state.get("freshness", "unknown"))
        freshness_keys = {
            "current": "rules_current", "update": "rules_update_available",
            "unknown": "rules_unknown",
        }
        texts = {
            "loading": tr("app_shell.pvp.decks.rules_loading") if loading else "",
            "source": tr("app_shell.pvp.decks.rules_source").format(source=source) if source else "",
            "version": tr("app_shell.pvp.decks.rules_version").format(version=version) if version else "",
            "freshness": tr("app_shell.pvp.decks." + freshness_keys[freshness])
                         if freshness in freshness_keys else "",
        }
        for name, value in texts.items():
            label = self._rules_meta_labels[name]
            label.setText(value)
            label.setVisible(bool(value))
        self.rules_update_button.setVisible(freshness == "update" and bool(state.get("update_id")))
        self.rules_update_button.setEnabled(not loading)
        self._update_rules_lines("rules_costs_heading", state.get("summary_lines", ()))
        rows = tuple(state.get("requirement_rows", ()))
        self._update_rules_lines(
            "rules_requirements_heading", state.get("requirement_lines", ()) if not rows else ()
        )
        self._update_requirement_rows(rows, state.get("active_character_filter"),
                                      pending=bool(state.get("requirements_pending")))
        self._update_rules_lines("rules_issues_heading", state.get("issue_lines", ()))
        error = str(state.get("error_text", "")).strip()
        self._update_rules_lines("rules_error_heading", (error,) if error else ())

    def _add_requirement_rows(self, layout: QVBoxLayout, rows, active_filter=None) -> None:
        section = QFrame()
        section.setObjectName("pvp_rules_section")
        section.setProperty("rulesSection", "rules_requirements_heading")
        content = QVBoxLayout(section)
        content.setContentsMargins(9, 8, 9, 8)
        content.setSpacing(6)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = self._rules_detail_label(
            tr("app_shell.pvp.decks.rules_requirements_heading")
        )
        heading.setObjectName("pvp_rules_heading")
        content.addWidget(heading)
        self._requirement_section = section
        self._requirement_content = content
        layout.addWidget(section)
        self._update_requirement_rows(tuple(rows), active_filter)

    @staticmethod
    def _requirement_shape(rows) -> tuple:
        return tuple(
            (bool(str(entry.get("detail", "")).strip()),
             tuple(entry["character_filter"]) if entry.get("character_filter") is not None else None,
             entry.get("depth") == 1)
            for entry in rows
        )

    def _update_requirement_rows(self, rows, active_filter=None, *, pending=False) -> None:
        if pending and self._settled_requirement_rows:
            available = defaultdict(deque)
            for entry in rows:
                available[self._requirement_identity(entry)].append(entry)
            retained = []
            for entry in self._settled_requirement_rows:
                matches = available[self._requirement_identity(entry)]
                if matches:
                    retained.append(matches.popleft())
                elif entry.get("allocation_group"):
                    if not self._pending_row_heights and self._requirement_rows:
                        # Retain wrapped group row heights while their new members
                        # are unknown; show blank labels rather than stale names.
                        for row in self._requirement_rows:
                            label = row["label"]
                            self._pending_row_heights.append((label, label.minimumHeight()))
                            label.setMinimumHeight(max(label.minimumHeight(), label.height()))
                    retained.append(dict(entry, label="", current="—", status="unknown"))
            for remaining in available.values():
                retained.extend(remaining)
            rows = tuple(retained)
        elif not pending:
            self._release_pending_row_heights()
            self._settled_requirement_rows = tuple(rows)
        self._requirement_section.setVisible(bool(rows))
        if not rows:
            return
        shape = self._requirement_shape(rows)
        if shape != getattr(self, "_requirement_row_shape", None):
            self._release_pending_row_heights()
            if self._requirement_table is not None:
                self._requirement_content.removeItem(self._requirement_table)
                _clear_layout(self._requirement_table)
                self._requirement_table.deleteLater()
            self._requirement_rows = []
            self._requirement_row_shape = shape
            self._populate_requirement_rows(rows, active_filter)
            return
        for entry, widgets in zip(rows, self._requirement_rows):
            label = widgets["label"]
            label.setText(str(entry.get("label", "")))
            widgets["current"].setText(str(entry.get("current", "")))
            if widgets["detail"] is not None:
                widgets["detail"].setText(str(entry.get("detail", "")).strip())
            button = widgets["button"]
            if button is not None:
                active = tuple(entry["character_filter"]) == active_filter
                button.setChecked(active)
                button.setText(tr("app_shell.pvp.rules.filter_reset" if active else "app_shell.pvp.rules.filter_show"))
                button.setAccessibleName(button.text() + ": " + label.text())
            self._set_requirement_status(widgets["marker"], str(entry.get("status", "info")),
                                         str(entry.get("status_detail", "")))

    @staticmethod
    def _requirement_identity(entry) -> tuple:
        return (entry.get("label", ""), tuple(entry.get("character_filter") or ()), entry.get("depth", 0))

    def _release_pending_row_heights(self) -> None:
        for label, height in self._pending_row_heights:
            label.setMinimumHeight(height)
        self._pending_row_heights.clear()

    def _set_requirement_status(self, marker: QLabel, status: str, detail: str = "") -> None:
        marker.setAccessibleDescription(detail)
        if status not in ("pass", "fail", "unknown", "info"):
            status = "info"
        if marker.property("requirementStatus") == status:
            return
        marker.setProperty("requirementStatus", status)
        marker.setAccessibleName(tr("app_shell.pvp.rules.status_" + status))
        if status in self._status_pixmaps:
            marker.setText("")
            marker.setPixmap(self._status_pixmaps[status])
        else:
            marker.clear()
            marker.setText("?" if status == "unknown" else "—")

    def _populate_requirement_rows(self, rows, active_filter=None) -> None:

        table = QGridLayout()
        self._requirement_table = table
        table.setObjectName("pvp_requirement_table")
        table.setContentsMargins(0, 0, 0, 0)
        table.setHorizontalSpacing(6)
        table.setVerticalSpacing(5)
        table.setColumnStretch(0, 1)
        table.setColumnMinimumWidth(1, 62)
        table.setColumnMinimumWidth(2, 54)
        for column, key in enumerate(("table_requirement", "table_current", "table_status")):
            header = self._rules_detail_label(tr("app_shell.pvp.rules." + key))
            header.setObjectName("pvp_requirement_header")
            if column == 0:
                policy = header.sizePolicy()
                policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
                header.setSizePolicy(policy)
            if column == 1:
                header.setFixedWidth(62)
            if column == 2:
                header.setFixedWidth(54)
                header.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            table.addWidget(header, 0, column)

        next_row = 1
        for entry in rows:
            label = self._rules_detail_label(str(entry.get("label", "")))
            label.setObjectName("pvp_requirement_description")
            if entry.get("depth") == 1:
                # QLabel.indent also indents the top edge with AlignTop.
                label.setContentsMargins(12, 0, 0, 0)
            criterion = entry.get("character_filter")
            button = None
            if criterion is not None:
                description = QWidget()
                line = QHBoxLayout(description)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(6)
                line.addWidget(label, 1, Qt.AlignmentFlag.AlignTop)
                active = tuple(criterion) == active_filter
                button = QPushButton(tr("app_shell.pvp.rules.filter_reset" if active else "app_shell.pvp.rules.filter_show"))
                button.setObjectName("pvp_requirement_show")
                button.setProperty("criterionTier", criterion[0])
                button.setProperty("criterionRole", criterion[1])
                button.setCheckable(True)
                button.setChecked(active)
                button.setAccessibleName(button.text() + ": " + label.text())
                button.clicked.connect(lambda _checked=False, value=tuple(criterion):
                                       self.workspace.toggle_requirement_filter(*value))
                line.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
                table.addWidget(description, next_row, 0)
            else:
                table.addWidget(label, next_row, 0)

            current = self._rules_detail_label(str(entry.get("current", "")))
            current.setObjectName("pvp_requirement_current")
            current.setFixedWidth(62)
            table.addWidget(current, next_row, 1)

            marker = QLabel()
            marker.setObjectName("pvp_requirement_status")
            marker.setFixedWidth(54)
            marker.setFixedHeight(max(14, marker.fontMetrics().lineSpacing()))
            marker.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self._set_requirement_status(marker, str(entry.get("status", "info")),
                                         str(entry.get("status_detail", "")))
            table.addWidget(marker, next_row, 2)
            next_row += 1

            detail = str(entry.get("detail", "")).strip()
            detail_label = None
            if detail:
                detail_label = self._rules_detail_label(detail)
                detail_label.setObjectName("pvp_requirement_detail")
                if entry.get("depth") == 1:
                    detail_label.setContentsMargins(12, 0, 0, 0)
                table.addWidget(detail_label, next_row, 0, 1, 2)
                next_row += 1
            self._requirement_rows.append({
                "label": label, "current": current, "marker": marker,
                "detail": detail_label, "button": button,
            })

        self._requirement_content.addLayout(table)

    def _info_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pvp_deck_info_line")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _validation_text(self) -> str:
        preset = self.workspace.active_preset()
        if preset is None:
            return tr("app_shell.pvp.decks.validation_none")
        if getattr(preset, "rules_snapshot", None):
            return tr("app_shell.pvp.rules.deck_editable")
        try:
            report = self.workspace.validation_report()
        except Exception as exc:
            return tr("app_shell.pvp.decks.validation_error").format(error=str(exc))
        if report is None:
            return tr("app_shell.pvp.decks.validation_none")
        codes = list(report.issue_codes())
        code_text = ", ".join(codes[:4])
        if len(codes) > 4:
            code_text += ", ..."
        if report.ready:
            return tr("app_shell.pvp.decks.validation_ready").format(
                issues=len(codes),
            )
        return tr("app_shell.pvp.decks.validation_invalid").format(
            issues=len(codes),
            codes=f": {code_text}" if code_text else "",
        )

    def _on_create_clicked(self) -> None:
        if self.workspace.is_new_deck_edit:
            if self.workspace.save_edit(name=self.create_name_edit.text()):
                self.create_name_edit.clear()
            return
        if self.workspace.is_editing:
            return
        if self.workspace.create_deck(self.create_name_edit.text()):
            preset = self.workspace.active_preset()
            if preset is not None:
                self.create_name_edit.setText(preset.name)

    def _on_cancel_new_clicked(self) -> None:
        if self.workspace.is_new_deck_edit:
            self.workspace.cancel_edit()
        self.create_name_edit.clear()

    def _on_export_profile(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("app_shell.pvp.profile.export"),
            "profile.gttpvp",
            tr("app_shell.pvp.profile.file_filter"),
        )
        if path:
            self.workspace.export_profile(path)

    def _save_existing_from(self, name_input: QLineEdit) -> None:
        self.workspace.save_edit(name=name_input.text())

    def _save_active_edit(self) -> None:
        if self.workspace.is_new_deck_edit:
            if self.workspace.save_edit(name=self.create_name_edit.text()):
                self.create_name_edit.clear()
        elif self.edit_name_edit is not None:
            self.workspace.save_edit(name=self.edit_name_edit.text())

    def _cancel_active_edit(self) -> None:
        if self.workspace.is_new_deck_edit:
            self._on_cancel_new_clicked()
        else:
            self.workspace.cancel_edit()

    def _request_delete_deck(self, deck_id: str) -> None:
        if self.workspace.is_editing:
            return
        self.pending_delete_deck_id = deck_id
        self.refresh()

    def _cancel_delete_deck(self) -> None:
        self.pending_delete_deck_id = ""
        self.refresh()

    def _confirm_delete_deck(self, deck_id: str) -> None:
        if self.pending_delete_deck_id != deck_id:
            return
        self.pending_delete_deck_id = ""
        self.workspace.delete_deck(deck_id)

    def _clear_stale_pending_delete(self) -> None:
        if not self.pending_delete_deck_id:
            return
        if any(preset.deck_id == self.pending_delete_deck_id for preset in self.workspace.presets):
            return
        self.pending_delete_deck_id = ""

    def _row_icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("icon_button")
        button.setIcon(self._ui_icon(icon_name))
        self._install_button_tooltip(button, tooltip)
        self._prepare_row_action_button(button)
        return button

    def _ui_icon(self, name: str) -> QIcon:
        return auto_contrast_svg_icon(
            name,
            PVP_DECK_UI_ICON_SIZE,
            PVP_DECK_UI_ICON_BACKGROUND,
        )

    def _install_button_tooltip(self, button: QPushButton, text: str) -> None:
        controller = button.property("_custom_tooltip_controller")
        if controller is None:
            controller = install_custom_tooltip(button)
            button.setProperty("_custom_tooltip_controller", controller)
        controller.set_text(text)
        button.setToolTip("")

    def _prepare_row_action_button(self, button: QPushButton) -> None:
        button.ensurePolished()
        button.sizeHint()
        button.minimumSizeHint()


__all__ = ["PvpDecksRightPanel"]
