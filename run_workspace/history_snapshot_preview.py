"""Render derived PNG preview cards from immutable History Snapshot Bundles.

This v0 renderer is intentionally text-first and dependency-light. It consumes
only `HistorySnapshotBundle` data and writes a derived PNG artifact; it does not
read live account/cache/DB state and does not mutate `snapshot.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_SNAPSHOT_FILENAME,
    HistoryAbyssChamberSnapshot,
    HistorySnapshotBundle,
    HistoryTeamSnapshot,
)


HISTORY_PREVIEW_FILENAME = "history_card.png"
HISTORY_PREVIEW_SUBDIR = "preview"

_QT_APP: QGuiApplication | None = None


@dataclass(frozen=True, slots=True)
class HistorySnapshotPreviewOptions:
    width: int = 960
    scale: float = 1.0


@dataclass(frozen=True, slots=True)
class HistorySnapshotPreviewResult:
    success: bool
    output_path: Path | None = None
    width: int = 0
    height: int = 0
    error_text: str = ""


def default_history_snapshot_preview_path(bundle_path: str | Path) -> Path:
    """Return `<bundle_dir>/preview/history_card.png` for a bundle path/dir."""

    path = Path(bundle_path)
    bundle_dir = path.parent if path.name == HISTORY_SNAPSHOT_FILENAME else path
    return bundle_dir / HISTORY_PREVIEW_SUBDIR / HISTORY_PREVIEW_FILENAME


def render_history_snapshot_preview(
    bundle: HistorySnapshotBundle,
    output_path: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
    options: HistorySnapshotPreviewOptions | None = None,
) -> HistorySnapshotPreviewResult:
    """Render `bundle` into a PNG preview card and return a small result object."""

    render_options = options or HistorySnapshotPreviewOptions()
    try:
        path = _resolve_output_path(output_path, output_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        width = max(360, int(render_options.width * max(render_options.scale, 0.1)))
        lines = _card_lines(bundle)
        height = _height_for(lines)
        _ensure_qt_app()
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#10151f"))
        painter = QPainter(image)
        try:
            _paint_card(painter, image.rect(), bundle=bundle, lines=lines)
        finally:
            painter.end()
        if not image.save(str(path), "PNG"):
            return HistorySnapshotPreviewResult(
                success=False,
                output_path=path,
                error_text=f"Failed to write PNG preview: {path}",
            )
        return HistorySnapshotPreviewResult(
            success=True,
            output_path=path,
            width=width,
            height=height,
        )
    except Exception as exc:  # pragma: no cover - exercised through public API
        return HistorySnapshotPreviewResult(
            success=False,
            output_path=None if output_path is None else Path(output_path),
            error_text=str(exc) or exc.__class__.__name__,
        )


def _resolve_output_path(
    output_path: str | Path | None,
    output_dir: str | Path | None,
) -> Path:
    if output_path is not None:
        return Path(output_path)
    if output_dir is not None:
        return Path(output_dir) / HISTORY_PREVIEW_FILENAME
    raise ValueError("output_path or output_dir is required.")


def _ensure_qt_app() -> None:
    global _QT_APP
    if QGuiApplication.instance() is not None:
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _QT_APP = QGuiApplication([])


def _card_lines(bundle: HistorySnapshotBundle) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    title, meta = _title_and_meta(bundle)
    lines.append(("title", title))
    if meta:
        lines.append(("muted", meta))
    lines.append(("gap", ""))
    lines.extend(_team_lines(bundle.teams))
    scenario = bundle.scenario
    abyss = None if scenario is None else scenario.abyss
    dps_dummy = None if scenario is None else scenario.dps_dummy
    if bundle.run_type == HISTORY_RUN_TYPE_ABYSS and abyss is not None:
        lines.append(("gap", ""))
        lines.append(("section", "Chambers"))
        for chamber in abyss.chambers:
            lines.extend(_abyss_chamber_lines(chamber, floor=abyss.floor))
    elif bundle.run_type == HISTORY_RUN_TYPE_DPS_DUMMY and dps_dummy is not None:
        lines.append(("gap", ""))
        lines.append(("section", "Target"))
        target_parts = [dps_dummy.target_label or "Target"]
        if dps_dummy.target_hp is not None:
            target_parts.append(f"HP {_compact_number(float(dps_dummy.target_hp))}")
        if dps_dummy.duration_seconds is not None:
            target_parts.append(f"{_format_seconds(dps_dummy.duration_seconds)}")
        if dps_dummy.factual_dps is not None:
            target_parts.append(f"Fact DPS {_compact_number(float(dps_dummy.factual_dps))}")
        lines.append(("body", " | ".join(target_parts)))
    result_lines = _result_lines(bundle)
    if result_lines:
        lines.append(("gap", ""))
        lines.append(("section", "Results"))
        lines.extend(("body", line) for line in result_lines)
    warning_lines = _warning_lines(bundle)
    if warning_lines:
        lines.append(("gap", ""))
        lines.append(("warning", f"Warnings: {len(warning_lines)}"))
        for warning in warning_lines[:3]:
            lines.append(("warning", warning))
    return lines


def _title_and_meta(bundle: HistorySnapshotBundle) -> tuple[str, str]:
    if bundle.run_type == HISTORY_RUN_TYPE_ABYSS:
        abyss = None if bundle.scenario is None else bundle.scenario.abyss
        title = "Abyss"
        meta_parts = [bundle.created_at]
        if abyss is not None:
            if abyss.period_start or abyss.period_end:
                meta_parts.append(f"{abyss.period_start or '?'}..{abyss.period_end or '?'}")
            if abyss.floor is not None:
                meta_parts.append(f"Floor {int(abyss.floor)}")
            if abyss.season_label:
                meta_parts.append(abyss.season_label)
        return title, " | ".join(item for item in meta_parts if item)
    return "DPS Dummy", bundle.created_at


def _team_lines(teams: tuple[HistoryTeamSnapshot, ...]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("section", "Teams")]
    for team in teams:
        team_label = team.label or f"Team {int(team.team_index) + 1}"
        slot_lines: list[str] = []
        for slot in team.slots:
            if slot.character is None:
                continue
            parts = [slot.character.name]
            if slot.weapon is not None and slot.weapon.name:
                parts.append(slot.weapon.name)
            if slot.weapon is not None and slot.weapon.icon_ref:
                parts.append(slot.weapon.icon_ref)
            if slot.artifact_build is not None:
                set_names = [
                    f"{bonus.set_name} {int(bonus.piece_count)}p"
                    if bonus.piece_count
                    else bonus.set_name
                    for bonus in slot.artifact_build.active_set_bonuses
                    if bonus.set_name
                ]
                if slot.artifact_build.build_name:
                    parts.append(slot.artifact_build.build_name)
                if set_names:
                    parts.append(", ".join(set_names))
            slot_lines.append(" - ".join(parts))
        lines.append(("body", f"{team_label}: {' / '.join(slot_lines) or '-'}"))
    return lines


def _abyss_chamber_lines(
    chamber: HistoryAbyssChamberSnapshot,
    *,
    floor: int | None,
) -> list[tuple[str, str]]:
    label = chamber.chamber_label or (
        f"{int(floor)}-{int(chamber.chamber_index)}"
        if floor is not None
        else f"C{int(chamber.chamber_index)}"
    )
    parts = [label]
    if chamber.timer is not None:
        timer_parts: list[str] = []
        if chamber.timer.team1_elapsed_seconds is not None:
            timer_parts.append(f"T1 {_format_seconds(chamber.timer.team1_elapsed_seconds)}")
        if chamber.timer.team2_elapsed_seconds is not None:
            timer_parts.append(f"T2 {_format_seconds(chamber.timer.team2_elapsed_seconds)}")
        if chamber.timer.total_elapsed_seconds is not None:
            timer_parts.append(f"Total {_format_seconds(chamber.timer.total_elapsed_seconds)}")
        if timer_parts:
            parts.append(", ".join(timer_parts))
    for result in chamber.side_results:
        result_parts = [f"S{int(result.side)}"]
        if result.factual_dps is not None:
            result_parts.append(f"Fact {_compact_number(float(result.factual_dps))}")
        if result.elapsed_seconds is not None:
            result_parts.append(_format_seconds(result.elapsed_seconds))
        if result.sim_result_ref:
            result_parts.append(f"Sim {result.sim_result_ref}")
        if len(result_parts) > 1:
            parts.append(" ".join(result_parts))
    return [("body", " | ".join(parts))]


def _result_lines(bundle: HistorySnapshotBundle) -> list[str]:
    lines: list[str] = []
    for result in bundle.result_summaries:
        parts = [result.label or result.result_type]
        if result.chamber_index is not None:
            parts.append(f"C{int(result.chamber_index)}")
        if result.side is not None:
            parts.append(f"S{int(result.side)}")
        if result.dps is not None:
            label = "Sim DPS" if result.result_type == "sim_dps" else "DPS"
            parts.append(f"{label} {_compact_number(float(result.dps))}")
        if result.damage is not None:
            parts.append(f"DMG {_compact_number(float(result.damage))}")
        if result.elapsed_seconds is not None:
            parts.append(_format_seconds(result.elapsed_seconds))
        lines.append(" | ".join(parts))
    return lines


def _warning_lines(bundle: HistorySnapshotBundle) -> list[str]:
    warnings: list[str] = [*bundle.warnings]
    if bundle.scenario is not None:
        warnings.extend(bundle.scenario.warnings)
        if bundle.scenario.abyss is not None:
            warnings.extend(bundle.scenario.abyss.warnings)
            for chamber in bundle.scenario.abyss.chambers:
                warnings.extend(chamber.warnings)
                for result in chamber.side_results:
                    warnings.extend(result.warnings)
        if bundle.scenario.dps_dummy is not None:
            warnings.extend(bundle.scenario.dps_dummy.warnings)
    for team in bundle.teams:
        warnings.extend(team.warnings)
        for slot in team.slots:
            warnings.extend(slot.warnings)
            if slot.artifact_build is not None:
                warnings.extend(slot.artifact_build.warnings)
    for result in bundle.result_summaries:
        warnings.extend(result.warnings)
    return _dedupe(warnings)


def _height_for(lines: list[tuple[str, str]]) -> int:
    height = 64
    for kind, _text in lines:
        if kind == "gap":
            height += 12
        elif kind == "title":
            height += 46
        elif kind == "section":
            height += 32
        else:
            height += 28
    return max(420, min(height + 48, 1600))


def _paint_card(
    painter: QPainter,
    rect: QRect,
    *,
    bundle: HistorySnapshotBundle,
    lines: list[tuple[str, str]],
) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    card_rect = rect.adjusted(18, 18, -18, -18)
    painter.fillRect(rect, QColor("#0b1018"))
    painter.setPen(QColor("#2f3a4f"))
    painter.setBrush(QColor("#141b27"))
    painter.drawRoundedRect(card_rect, 18, 18)

    accent = QColor("#f0c36a") if bundle.run_type == HISTORY_RUN_TYPE_ABYSS else QColor("#7ec8ff")
    painter.fillRect(card_rect.left(), card_rect.top(), 7, card_rect.height(), accent)

    x = card_rect.left() + 32
    y = card_rect.top() + 32
    content_width = card_rect.width() - 64
    fonts = {
        "title": QFont("Segoe UI", 24, QFont.Weight.DemiBold),
        "section": QFont("Segoe UI", 14, QFont.Weight.DemiBold),
        "body": QFont("Segoe UI", 11),
        "muted": QFont("Segoe UI", 10),
        "warning": QFont("Segoe UI", 10, QFont.Weight.DemiBold),
    }
    colors = {
        "title": QColor("#f8fafc"),
        "section": QColor("#f0c36a"),
        "body": QColor("#dce4f0"),
        "muted": QColor("#95a3b8"),
        "warning": QColor("#ffb86b"),
    }
    for kind, text in lines:
        if kind == "gap":
            y += 10
            continue
        painter.setFont(fonts.get(kind, fonts["body"]))
        painter.setPen(colors.get(kind, colors["body"]))
        metrics = QFontMetrics(painter.font())
        line_height = metrics.height() + (8 if kind in {"title", "section"} else 5)
        draw_rect = QRect(x, y, content_width, line_height * 2)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
        painter.drawText(draw_rect, flags, text)
        used = metrics.boundingRect(draw_rect, flags, text).height()
        y += max(line_height, used + 4)
        if y > card_rect.bottom() - 28:
            break


def _compact_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _format_seconds(value: float | int) -> str:
    return f"{float(value):.1f}s".replace(".0s", "s")


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


__all__ = [
    "HISTORY_PREVIEW_FILENAME",
    "HISTORY_PREVIEW_SUBDIR",
    "HistorySnapshotPreviewOptions",
    "HistorySnapshotPreviewResult",
    "default_history_snapshot_preview_path",
    "render_history_snapshot_preview",
]
