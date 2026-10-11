"""Optional display nicknames for an exported result, scoped to the current match."""
from __future__ import annotations

import re

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from localization import tr
from ui.pvp_browser.result_export import ResultExportLabels


def is_default_player_name(name: str) -> bool:
    return re.fullmatch(r"(?:player|игрок|jogador)[12]", re.sub(r"\s+", "", name).casefold()) is not None


def request_export_names(parent, names: tuple[str, str]) -> tuple[str, str] | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("app_shell.pvp.export.names_title"))
    dialog.setMinimumWidth(360)
    layout = QVBoxLayout(dialog)
    notice = QLabel(tr("app_shell.pvp.export.names_notice"))
    notice.setWordWrap(True)
    layout.addWidget(notice)
    form = QFormLayout()
    edits = []
    for index, name in enumerate(names, 1):
        edit = QLineEdit(name)
        edit.setMaxLength(64)
        form.addRow(tr(f"app_shell.pvp.draft.player_{index}"), edit)
        edits.append(edit)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    try:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return tuple(edit.text().strip() or names[index] for index, edit in enumerate(edits))
    finally:
        dialog.deleteLater()


def localized_result_labels() -> ResultExportLabels:
    return ResultExportLabels(**{
        field: tr("app_shell.pvp.export." + field)
        for field in ResultExportLabels.__dataclass_fields__
    })
