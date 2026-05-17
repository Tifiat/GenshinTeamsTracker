from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from hoyolab_export.paths import PROJECT_ROOT
from localization import tr

from .queries import (
    clear_json_imported_artifacts,
    count_json_imported_artifacts,
    delete_build_presets,
    import_artiscan_json_files,
)


ImportFilesFn = Callable[[list[str | Path]], list[dict[str, Any]]]
ReloadFn = Callable[[], None]
UpdateActionsFn = Callable[[], None]
ConfirmFn = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ArtiscanImportResult:
    file_count: int
    summaries: list[dict[str, Any]]
    errors: list[str]

    @property
    def has_imports(self) -> bool:
        return bool(self.summaries)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "files": self.file_count,
            "inserted": sum(int(item.get("inserted") or 0) for item in self.summaries),
            "duplicates": sum(
                int(item.get("skipped_duplicates") or 0)
                for item in self.summaries
            ),
            "invalid": sum(
                int(item.get("skipped_invalid") or 0)
                for item in self.summaries
            ),
        }

    def error_text(self, *, limit: int = 8) -> str:
        return "\n".join(self.errors[:limit])


def run_artiscan_imports(
    paths: list[str | Path],
    *,
    import_files: ImportFilesFn = import_artiscan_json_files,
) -> ArtiscanImportResult:
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in paths:
        try:
            summaries.extend(import_files([path]))
        except Exception as exc:
            errors.append(f"{Path(path).name}: {exc}")

    return ArtiscanImportResult(
        file_count=len(paths),
        summaries=summaries,
        errors=errors,
    )


def json_imports_available() -> bool:
    return count_json_imported_artifacts() > 0


def affected_preset_ids(clear_summary: dict[str, Any]) -> list[int]:
    return [
        int(item["id"])
        for item in list(clear_summary.get("affected_presets") or [])
    ]


def clear_summary_values(
    clear_summary: dict[str, Any],
    *,
    deleted_presets: int = 0,
) -> dict[str, int]:
    return {
        "deleted": int(clear_summary.get("deleted_artifacts") or 0),
        "slots": int(clear_summary.get("cleared_slots") or 0),
        "presets": int(deleted_presets),
    }


def choose_artiscan_json_files(parent: QWidget) -> list[str]:
    paths, _selected_filter = QFileDialog.getOpenFileNames(
        parent,
        tr("artifact.json.import_dialog_title"),
        str(PROJECT_ROOT),
        tr("artifact.json.file_filter"),
    )
    return list(paths)


def show_import_result(parent: QWidget, result: ArtiscanImportResult) -> None:
    title = tr("artifact.json.import_button")
    if result.has_imports:
        message = tr("artifact.json.import_summary", **result.totals)
        if result.errors:
            message = (
                message
                + "\n\n"
                + tr(
                    "artifact.json.import_error_summary",
                    errors=result.error_text(),
                )
            )
            QMessageBox.warning(parent, title, message)
        else:
            QMessageBox.information(parent, title, message)
        return

    QMessageBox.warning(
        parent,
        title,
        tr(
            "artifact.json.import_error_summary",
            errors=result.error_text(),
        ),
    )


def run_artiscan_import_action(
    parent: QWidget,
    *,
    confirm_ready: ConfirmFn,
    reload_database: ReloadFn,
    update_actions: UpdateActionsFn,
) -> None:
    if not confirm_ready():
        return

    paths = choose_artiscan_json_files(parent)
    if not paths:
        return

    result = run_artiscan_imports(paths)
    if result.has_imports:
        reload_database()
    else:
        update_actions()
    show_import_result(parent, result)


def run_clear_json_imports_action(
    parent: QWidget,
    *,
    confirm_ready: ConfirmFn,
    reload_database: ReloadFn,
    update_actions: UpdateActionsFn,
) -> None:
    if not confirm_ready():
        return

    count = count_json_imported_artifacts()
    title = tr("artifact.json.clear_button")
    if count <= 0:
        update_actions()
        QMessageBox.information(parent, title, tr("artifact.json.clear_none"))
        return

    answer = QMessageBox.question(
        parent,
        title,
        tr("artifact.json.clear_confirm", count=count),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    summary = clear_json_imported_artifacts()
    preset_ids = affected_preset_ids(summary)
    deleted_presets = 0

    if preset_ids:
        answer = QMessageBox.question(
            parent,
            title,
            tr("artifact.json.delete_affected_presets_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            deleted_presets = delete_build_presets(preset_ids)

    reload_database()
    QMessageBox.information(
        parent,
        title,
        tr(
            "artifact.json.clear_summary",
            **clear_summary_values(summary, deleted_presets=deleted_presets),
        ),
    )
