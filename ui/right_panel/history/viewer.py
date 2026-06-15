from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from localization import tr
from run_workspace.history_snapshot import HISTORY_RUN_TYPE_ABYSS, HISTORY_RUN_TYPE_DPS_DUMMY
from run_workspace.history_snapshot_listing import HistorySnapshotDetailsPayload
from run_workspace.history_snapshot_preview import sanitize_history_snapshot_display_text


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _run_type_label(run_type: str) -> str:
    if run_type == HISTORY_RUN_TYPE_ABYSS:
        return tr("app_shell.history.run_type.abyss")
    if run_type == HISTORY_RUN_TYPE_DPS_DUMMY:
        return tr("app_shell.history.run_type.dps_dummy")
    return run_type


class HistoryRightPanelPlaceholder(QWidget):
    """Read-only History snapshot viewer for immutable saved bundles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanelPrototypeContent")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        frame = QFrame()
        frame.setObjectName("InfoBlock")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        frame_layout.addWidget(self.title_label)

        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        frame_layout.addWidget(self.empty_label)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        frame_layout.addWidget(self.note_label)

        self.details_area = QScrollArea()
        self.details_area.setWidgetResizable(True)
        self.details_area.setFrameShape(QFrame.Shape.NoFrame)
        self.details_content = QWidget()
        self.details_layout = QVBoxLayout(self.details_content)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(8)
        self.details_area.setWidget(self.details_content)
        frame_layout.addWidget(self.details_area, 1)

        root.addWidget(frame)
        root.addStretch(1)
        self._payload: HistorySnapshotDetailsPayload | None = None
        self.retranslate_ui()

    def set_snapshot_details(
        self,
        payload: HistorySnapshotDetailsPayload | None,
    ) -> None:
        self._payload = payload
        self._render_payload()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.history.viewer.title"))
        self.empty_label.setText(tr("app_shell.history.viewer.empty"))
        self.note_label.setText(tr("app_shell.history.viewer.note"))
        self._render_payload()

    def _render_payload(self) -> None:
        if not hasattr(self, "details_layout"):
            return
        _clear_layout(self.details_layout)
        payload = self._payload
        has_payload = payload is not None
        self.empty_label.setVisible(not has_payload)
        self.note_label.setVisible(not has_payload)
        self.details_area.setVisible(has_payload)
        if payload is None:
            return

        self.details_layout.addWidget(
            _details_label(
                f"{_run_type_label(payload.run_type)} | {payload.created_at}",
                object_name="SectionTitle",
            )
        )
        self.details_layout.addWidget(
            _details_label(
                tr("app_shell.history.viewer.bundle").format(
                    bundle_id=payload.bundle_id
                ),
                object_name="MutedLabel",
            )
        )
        if payload.run_type == HISTORY_RUN_TYPE_ABYSS:
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.viewer.abyss_meta").format(
                        period=_period_text(payload),
                        floor="-" if payload.floor is None else int(payload.floor),
                        season=_viewer_text(payload.season_label, fallback="-"),
                    ),
                    object_name="MutedLabel",
                )
            )

        self.details_layout.addWidget(
            _details_label(tr("app_shell.history.viewer.teams"), object_name="SectionTitle")
        )
        for team in payload.teams:
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.viewer.team_title").format(
                        number=int(team.team_index) + 1
                    ),
                    object_name="MutedLabel",
                )
            )
            for slot in team.slots:
                self.details_layout.addWidget(_details_label(_slot_line(slot)))

        if payload.chamber_details:
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.viewer.chambers"),
                    object_name="SectionTitle",
                )
            )
            for chamber in payload.chamber_details:
                lines = [
                    _viewer_text(chamber.label),
                    _viewer_text(chamber.timing_summary, max_chars=120),
                    *(_viewer_text(item, max_chars=120) for item in chamber.factual_dps_summaries),
                    *(_viewer_text(item, max_chars=120) for item in chamber.sim_dps_summaries),
                    *(_viewer_text(item, max_chars=160) for item in chamber.enemy_hp_summaries),
                ]
                self.details_layout.addWidget(
                    _details_label(" | ".join(item for item in lines if item))
                )

        result_lines = [
            item
            for item in (
                *(
                    _viewer_text(item, max_chars=140)
                    for item in payload.factual_dps_summaries
                ),
                *(
                    _viewer_text(item, max_chars=140)
                    for item in payload.sim_dps_summaries
                ),
            )
            if item
        ]
        if result_lines:
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.viewer.results"),
                    object_name="SectionTitle",
                )
            )
            for line in result_lines:
                self.details_layout.addWidget(_details_label(line))

        if payload.warnings:
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.viewer.warnings"),
                    object_name="SectionTitle",
                )
            )
            self.details_layout.addWidget(
                _details_label(
                    tr("app_shell.history.row.warnings").format(
                        count=len(payload.warnings)
                    ),
                    object_name="WarningLabel",
                )
            )
        self.details_layout.addStretch(1)


def _details_label(text: str, *, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if object_name:
        label.setObjectName(object_name)
    return label


def _period_text(payload: HistorySnapshotDetailsPayload) -> str:
    if payload.period_start and payload.period_end:
        return f"{payload.period_start}..{payload.period_end}"
    return payload.period_start or payload.period_end or "-"


def _slot_line(slot) -> str:
    character = _viewer_text(
        slot.character_name,
        fallback=tr("app_shell.history.viewer.empty_slot"),
    )
    parts = [f"{int(slot.slot_index) + 1}. {character}"]
    weapon = _viewer_text(slot.weapon_name or slot.weapon_icon_ref)
    if weapon:
        parts.append(weapon)
    set_labels = [
        f"{set_name} {int(item.piece_count)}p" if item.piece_count else set_name
        for item in slot.artifact_sets
        for set_name in (_viewer_text(item.set_name or item.icon_ref),)
        if set_name
    ]
    build_label = _viewer_text(slot.artifact_build_label)
    if build_label:
        parts.append(build_label)
    if set_labels:
        parts.append(", ".join(set_labels))
    return " | ".join(parts)


def _viewer_text(text: object, *, max_chars: int = 120, fallback: str = "") -> str:
    return sanitize_history_snapshot_display_text(
        text,
        max_chars=max_chars,
        fallback=fallback,
    )


__all__ = ["HistoryRightPanelPlaceholder"]
