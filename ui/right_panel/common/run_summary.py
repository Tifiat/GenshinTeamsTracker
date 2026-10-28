"""Compact reusable presentation for saved and exportable run summaries."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from localization import tr
from run_workspace.history_browser_catalog import (
    HistoryChamberVisual,
    HistoryRunVisual,
    HistorySlotVisual,
    HistoryTeamVisual,
)
from ui.right_panel.common.metrics import _fit_pixmap


SLOT_WIDTH = 53
SLOT_HEIGHT = 56
PORTRAIT_SIZE = 42
WEAPON_SIZE = 18
SET_SIZE = 16


class CompactSlotSummaryWidget(QFrame):
    def __init__(self, slot: HistorySlotVisual, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompactRunSlot")
        self.setFixedSize(SLOT_WIDTH, SLOT_HEIGHT)
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 2)
        root.setSpacing(1)

        portrait = QLabel()
        portrait.setObjectName("CompactRunPortrait")
        portrait.setFixedSize(PORTRAIT_SIZE, PORTRAIT_SIZE)
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = _fit_pixmap(slot.portrait_path, QSize(PORTRAIT_SIZE, PORTRAIT_SIZE))
        if pixmap is not None:
            portrait.setPixmap(pixmap)
        elif slot.character_name:
            portrait.setText(slot.character_name[:1].upper())
        else:
            portrait.setText("-")

        weapon = QLabel(portrait)
        weapon.setObjectName("CompactRunWeapon")
        weapon.setFixedSize(WEAPON_SIZE, WEAPON_SIZE)
        weapon.move(PORTRAIT_SIZE - WEAPON_SIZE, PORTRAIT_SIZE - WEAPON_SIZE)
        weapon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weapon_pixmap = _fit_pixmap(
            slot.weapon_icon_path,
            QSize(WEAPON_SIZE - 2, WEAPON_SIZE - 2),
        )
        if weapon_pixmap is not None:
            weapon.setPixmap(weapon_pixmap)
        elif slot.weapon_name:
            weapon.setText("W")
        else:
            weapon.hide()

        set_badge = QLabel(portrait)
        set_badge.setObjectName("CompactRunSetBadge")
        set_badge.setFixedSize(SET_SIZE, SET_SIZE)
        set_badge.move(0, 0)
        set_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_pixmap = _fit_pixmap(
            slot.set_icon_paths[0] if slot.set_icon_paths else "",
            QSize(SET_SIZE - 2, SET_SIZE - 2),
        )
        if set_pixmap is not None:
            set_badge.setPixmap(set_pixmap)
        elif slot.set_labels:
            set_badge.setText(slot.set_labels[0].rsplit(" ", 1)[-1])
        elif slot.build_label:
            set_badge.setText("A")
        else:
            set_badge.hide()
        root.addWidget(portrait, 0, Qt.AlignmentFlag.AlignHCenter)

        sets = QLabel(" + ".join(slot.set_labels[:2]) or slot.build_label or " ")
        sets.setObjectName("CompactRunSetLabel")
        sets.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sets.setFixedHeight(8)
        root.addWidget(sets)
        self.setToolTip(_slot_tooltip(slot))


class CompactTeamStripWidget(QWidget):
    def __init__(self, team: HistoryTeamVisual, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)
        slots = list(team.slots[:4])
        while len(slots) < 4:
            slots.append(HistorySlotVisual(slot_index=len(slots)))
        for slot in slots:
            root.addWidget(CompactSlotSummaryWidget(slot))
        root.addStretch(1)


class CompactChamberSummaryWidget(QFrame):
    def __init__(
        self,
        chamber: HistoryChamberVisual,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CompactChamberSummary")
        self.setMinimumWidth(92)
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 4, 5, 4)
        root.setSpacing(2)

        title = QLabel(f"C{chamber.chamber_index}")
        title.setObjectName("CompactRunTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        for index in range(2):
            line = QLabel(_chamber_side_text(chamber, index))
            line.setObjectName("CompactRunMetric")
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(line)
        root.addStretch(1)


class CompactRunSummaryWidget(QWidget):
    """Content-only run card usable by History rows and future export."""

    def __init__(self, run: HistoryRunVisual, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.run = run
        root = QHBoxLayout(self)
        root.setContentsMargins(7, 6, 7, 6)
        root.setSpacing(7)

        teams_column = QVBoxLayout()
        teams_column.setContentsMargins(0, 0, 0, 0)
        teams_column.setSpacing(3)
        for team in run.teams[: (2 if run.run_type == "abyss" else 1)]:
            teams_column.addWidget(CompactTeamStripWidget(team))
        teams_column.addStretch(1)
        root.addLayout(teams_column, 3)

        if run.run_type == "abyss":
            chambers = QHBoxLayout()
            chambers.setContentsMargins(0, 0, 0, 0)
            chambers.setSpacing(4)
            by_index = {item.chamber_index: item for item in run.chambers}
            for chamber_index in (1, 2, 3):
                chambers.addWidget(
                    CompactChamberSummaryWidget(
                        by_index.get(
                            chamber_index,
                            HistoryChamberVisual(chamber_index=chamber_index),
                        )
                    )
                )
            root.addLayout(chambers, 4)
        else:
            metrics = QVBoxLayout()
            metrics.setContentsMargins(0, 0, 0, 0)
            metrics.setSpacing(3)
            for text in _dummy_metric_lines(run):
                label = QLabel(text)
                label.setObjectName("CompactRunMetric")
                label.setWordWrap(True)
                metrics.addWidget(label)
            metrics.addStretch(1)
            root.addLayout(metrics, 4)

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(2)
        date = QLabel(_compact_created_at(run.created_at))
        date.setObjectName("MutedLabel")
        date.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta.addWidget(date)
        if run.warnings_count:
            warnings = QLabel(
                tr("app_shell.history.row.warnings_short").format(
                    count=run.warnings_count
                )
            )
            warnings.setObjectName("WarningLabel")
            warnings.setAlignment(Qt.AlignmentFlag.AlignRight)
            meta.addWidget(warnings)
        meta.addStretch(1)
        root.addLayout(meta, 1)


def _slot_tooltip(slot: HistorySlotVisual) -> str:
    lines = [slot.character_name or tr("app_shell.history.slot.empty")]
    character_bits = []
    if slot.character_level is not None:
        character_bits.append(f"Lv. {slot.character_level}")
    if slot.constellation is not None:
        character_bits.append(f"C{slot.constellation}")
    if character_bits:
        lines.append(" | ".join(character_bits))
    if slot.weapon_name:
        refinement = (
            "" if slot.weapon_refinement is None else f" R{slot.weapon_refinement}"
        )
        lines.append(f"{slot.weapon_name}{refinement}")
    if slot.build_label:
        lines.append(slot.build_label)
    lines.extend(slot.set_labels)
    return "\n".join(lines)


def _chamber_side_text(chamber: HistoryChamberVisual, index: int) -> str:
    elapsed = chamber.side_times[index]
    fact = chamber.factual_dps[index]
    sim = chamber.sim_dps[index]
    time_text = "-" if elapsed is None else f"{elapsed}s"
    fact_text = "-" if fact is None else _compact_number(fact)
    sim_text = "-" if sim is None else _compact_number(sim)
    return f"S{index + 1}  {time_text}\nF {fact_text}  S {sim_text}"


def _dummy_metric_lines(run: HistoryRunVisual) -> tuple[str, ...]:
    target = run.target_label or tr("app_shell.history.dps.target_unavailable")
    setup = run.target_setup or tr("app_shell.history.dps.setup_unavailable")
    duration = "-" if run.duration_seconds is None else f"{run.duration_seconds:g}s"
    factual = "-" if run.factual_dps is None else _compact_number(run.factual_dps)
    simulated = "-" if run.sim_dps is None else _compact_number(run.sim_dps)
    return (
        tr("app_shell.history.dps.target").format(target=target),
        tr("app_shell.history.dps.setup").format(setup=setup),
        tr("app_shell.history.dps.results").format(
            duration=duration,
            factual=factual,
            simulated=simulated,
        ),
    )


def _compact_created_at(value: str) -> str:
    text = str(value or "")
    return text[:16].replace("T", " ")


def _compact_number(value: float | int) -> str:
    number = float(value)
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}m".replace(".0m", "m")
    if abs(number) >= 1_000:
        return f"{number / 1_000:.0f}k"
    return f"{number:.0f}"


__all__ = [
    "CompactChamberSummaryWidget",
    "CompactRunSummaryWidget",
    "CompactSlotSummaryWidget",
    "CompactTeamStripWidget",
]
