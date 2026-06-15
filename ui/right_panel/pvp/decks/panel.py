from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from localization import tr
from run_workspace.pvp.deck_preset import PvpDeckPreset
from ui.utils.icon_utils import auto_contrast_svg_icon
from ui.utils.marquee_label import MarqueeButton
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
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
        self.edit_name_edit: QLineEdit | None = None
        self.ruleset_button: QPushButton | None = None
        self._edit_shortcuts: list[QShortcut] = []
        self._preserved_edit_deck_id = ""
        self._preserved_edit_name = ""
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

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

        self.deck_list_scroll = OverlayVerticalScrollArea()
        self.deck_list_scroll.setWidgetResizable(True)
        self.deck_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        list_content = QWidget()
        self.deck_list_layout = QVBoxLayout(list_content)
        self.deck_list_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_list_layout.setSpacing(5)
        self.deck_list_scroll.setWidget(list_content)
        root.addWidget(self.deck_list_scroll, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self._init_edit_shortcuts()
        self.create_name_edit.returnPressed.connect(self._on_create_clicked)
        self.workspace.state_changed.connect(self.refresh)
        self.workspace.save_edit_requested.connect(self._save_active_edit)
        self.workspace.cancel_edit_requested.connect(self._cancel_active_edit)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        self._capture_existing_edit_name()
        self._clear_stale_pending_delete()
        self._refresh_create_controls()
        self._rebuild_deck_list()
        status = self.workspace._last_status
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        self._sync_edit_shortcuts()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.decks.title"))
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
        _clear_layout(self.deck_list_layout)
        self.deck_row_frames.clear()
        self.selected_info_labels.clear()
        self.edit_name_edit = None
        self.ruleset_button = None

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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.ruleset_button = QPushButton(tr("app_shell.pvp.decks.ruleset_free"))
        self.ruleset_button.setObjectName("pvp_ruleset_chip")
        self.ruleset_button.setEnabled(False)
        layout.addWidget(self.ruleset_button)

        counts_label = self._info_label(
            tr("app_shell.pvp.decks.counts").format(
                characters=len(preset.character_ids),
                weapons=len(preset.weapon_refs),
            )
        )
        layout.addWidget(counts_label)
        self.selected_info_labels["counts"] = counts_label

        validation_label = self._info_label(self._validation_text())
        validation_label.setWordWrap(True)
        layout.addWidget(validation_label)
        self.selected_info_labels["validation"] = validation_label

        outer.addWidget(info)

    def _info_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pvp_deck_info_line")
        return label

    def _validation_text(self) -> str:
        preset = self.workspace.active_preset()
        if preset is None:
            return tr("app_shell.pvp.decks.validation_none")
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
