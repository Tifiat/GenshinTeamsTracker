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
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
)


HISTORY_PREVIEW_FILENAME = "history_card.png"
HISTORY_PREVIEW_SUBDIR = "preview"

_DEFAULT_TEXT_LIMIT = 96
_BODY_TEXT_LIMIT = 180
_INTERNAL_TEXT_PREFIXES = (
    "artifact_build_incomplete",
    "dps_dummy_factual_inputs_not_implemented",
    "history_builder_",
    "preview_",
    "right_panel_",
    "set_bonus_formulas_not_included",
)
_INTERNAL_TEXT_MARKERS = (
    "AppShellController",
    "RightPanelPrototype",
    "hoyolab_export.",
    "object at 0x",
    "run_workspace.",
    "ui.",
)

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


def sanitize_history_snapshot_display_text(
    value: object,
    *,
    max_chars: int = _DEFAULT_TEXT_LIMIT,
    fallback: str = "",
) -> str:
    """Return a compact user-facing label for preview/viewer presentation."""

    text = _text(value)
    if not text:
        return fallback
    if _is_internal_display_text(text):
        return fallback
    if _looks_like_path_ref(text):
        text = _path_basename_label(text)
    if not text or _is_internal_display_text(text):
        return fallback
    return _truncate(text, max_chars=max_chars)


def history_snapshot_preview_text_lines(bundle: HistorySnapshotBundle) -> tuple[str, ...]:
    """Return the sanitized visible text lines used by the v0 preview card."""

    return tuple(text for kind, text in _card_lines(bundle) if kind != "gap" and text)


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
        sim_dps_by_side = _sim_dps_by_chamber_side(bundle)
        for chamber in abyss.chambers:
            lines.extend(
                _abyss_chamber_lines(
                    chamber,
                    floor=abyss.floor,
                    sim_dps_by_side=sim_dps_by_side,
                )
            )
    elif bundle.run_type == HISTORY_RUN_TYPE_DPS_DUMMY and dps_dummy is not None:
        lines.append(("gap", ""))
        lines.append(("section", "Target"))
        target_parts = [
            sanitize_history_snapshot_display_text(
                dps_dummy.target_label,
                fallback="Target",
            )
        ]
        if dps_dummy.target_hp is not None:
            target_parts.append(f"HP {_compact_number(float(dps_dummy.target_hp))}")
        if dps_dummy.duration_seconds is not None:
            target_parts.append(f"{_format_seconds(dps_dummy.duration_seconds)}")
        if dps_dummy.factual_dps is not None:
            target_parts.append(f"Fact DPS {_compact_number(float(dps_dummy.factual_dps))}")
        lines.append(("body", _join_display_parts(target_parts)))
    result_lines = _result_lines(bundle)
    if result_lines:
        lines.append(("gap", ""))
        lines.append(("section", "Results"))
        lines.extend(("body", line) for line in result_lines)
    warning_lines = _warning_lines(bundle)
    if warning_lines:
        lines.append(("gap", ""))
        lines.append(("warning", f"Warnings: {len(warning_lines)}"))
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
                meta_parts.append(
                    sanitize_history_snapshot_display_text(abyss.season_label)
                )
        return title, _join_display_parts(meta_parts)
    return "DPS Dummy", bundle.created_at


def _team_lines(teams: tuple[HistoryTeamSnapshot, ...]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("section", "Teams")]
    for team in teams:
        team_label = sanitize_history_snapshot_display_text(
            team.label,
            fallback=f"Team {int(team.team_index) + 1}",
        )
        lines.append(("subsection", team_label))
        has_slot = False
        for slot in team.slots:
            slot_line = _slot_line(slot)
            if not slot_line:
                continue
            has_slot = True
            lines.append(("body", f"{int(slot.slot_index) + 1}. {slot_line}"))
        if not has_slot:
            lines.append(("muted", "-"))
    return lines


def _slot_line(slot: HistoryTeamSlotSnapshot) -> str:
    character = (
        ""
        if slot.character is None
        else _display_label(
            slot.character.name,
            slot.character.portrait_ref,
            slot.character.side_icon_ref,
        )
    )
    if not character:
        return ""
    parts = [character]
    if slot.weapon is not None:
        weapon = _display_label(slot.weapon.name, slot.weapon.icon_ref)
        if weapon:
            parts.append(weapon)
    if slot.artifact_build is not None:
        build_label = sanitize_history_snapshot_display_text(
            slot.artifact_build.build_name
        )
        if build_label:
            parts.append(build_label)
        set_names = [
            item
            for item in (
                _set_bonus_label(bonus.set_name, bonus.icon_ref, bonus.piece_count)
                for bonus in slot.artifact_build.active_set_bonuses
            )
            if item
        ]
        if set_names:
            parts.append(", ".join(set_names))
    return _join_display_parts(parts)


def _display_label(primary: object, *fallback_refs: object) -> str:
    label = sanitize_history_snapshot_display_text(primary)
    if label:
        return label
    for fallback_ref in fallback_refs:
        label = sanitize_history_snapshot_display_text(fallback_ref)
        if label:
            return label
    return ""


def _set_bonus_label(set_name: object, icon_ref: object, piece_count: int) -> str:
    label = _display_label(set_name, icon_ref)
    if not label:
        return ""
    if piece_count:
        return f"{label} {int(piece_count)}p"
    return label


def _abyss_chamber_lines(
    chamber: HistoryAbyssChamberSnapshot,
    *,
    floor: int | None,
    sim_dps_by_side: dict[tuple[int, int], float],
) -> list[tuple[str, str]]:
    label = sanitize_history_snapshot_display_text(
        chamber.chamber_label,
        fallback=(
            f"{int(floor)}-{int(chamber.chamber_index)}"
            if floor is not None
            else f"C{int(chamber.chamber_index)}"
        ),
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
        side = int(result.side)
        result_parts = [f"S{side}"]
        if result.factual_dps is not None:
            result_parts.append(f"Fact {_compact_number(float(result.factual_dps))}")
        if result.elapsed_seconds is not None:
            result_parts.append(_format_seconds(result.elapsed_seconds))
        sim_dps = sim_dps_by_side.get((int(chamber.chamber_index), side))
        if sim_dps is not None:
            result_parts.append(f"Sim {_compact_number(float(sim_dps))}")
        if len(result_parts) > 1:
            parts.append(" ".join(result_parts))
    return [("body", _join_display_parts(parts))]


def _result_lines(bundle: HistorySnapshotBundle) -> list[str]:
    lines: list[str] = []
    for result in bundle.result_summaries:
        parts = [
            sanitize_history_snapshot_display_text(
                result.label,
                fallback=_result_type_label(result.result_type),
            )
        ]
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
        lines.append(_join_display_parts(parts, max_chars=160))
    return lines


def _result_type_label(result_type: str) -> str:
    if result_type == "factual_dps":
        return "Factual DPS"
    if result_type == "sim_dps":
        return "Sim DPS"
    return "Result"


def _sim_dps_by_chamber_side(bundle: HistorySnapshotBundle) -> dict[tuple[int, int], float]:
    values: dict[tuple[int, int], float] = {}
    for summary in bundle.result_summaries:
        if summary.result_type != "sim_dps" or summary.dps is None:
            continue
        if summary.chamber_index is None or summary.side is None:
            continue
        values[(int(summary.chamber_index), int(summary.side))] = float(summary.dps)
    return values


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
        elif kind == "subsection":
            height += 26
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
        "subsection": QFont("Segoe UI", 12, QFont.Weight.DemiBold),
        "body": QFont("Segoe UI", 11),
        "muted": QFont("Segoe UI", 10),
        "warning": QFont("Segoe UI", 10, QFont.Weight.DemiBold),
    }
    colors = {
        "title": QColor("#f8fafc"),
        "section": QColor("#f0c36a"),
        "subsection": QColor("#e7edf7"),
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
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _join_display_parts(
    parts: list[str] | tuple[str, ...],
    *,
    max_chars: int = _BODY_TEXT_LIMIT,
) -> str:
    return _truncate(" | ".join(item for item in parts if item), max_chars=max_chars)


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _truncate(text: str, *, max_chars: int) -> str:
    limit = max(1, int(max_chars))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * limit
    return f"{text[: limit - 3].rstrip()}..."


def _looks_like_path_ref(text: str) -> bool:
    normalized = text.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        return True
    if normalized.startswith(("/", "~/")):
        return True
    if "/" not in normalized:
        return False
    name = normalized.rstrip("/").rsplit("/", 1)[-1]
    return "." in name


def _path_basename_label(text: str) -> str:
    normalized = text.replace("\\", "/").strip().rstrip("/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if not name:
        return ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.replace("_", " ").replace("-", " ").strip()


def _is_internal_display_text(text: str) -> bool:
    if any(text.startswith(prefix) for prefix in _INTERNAL_TEXT_PREFIXES):
        return True
    return any(marker in text for marker in _INTERNAL_TEXT_MARKERS)


__all__ = [
    "HISTORY_PREVIEW_FILENAME",
    "HISTORY_PREVIEW_SUBDIR",
    "HistorySnapshotPreviewOptions",
    "HistorySnapshotPreviewResult",
    "default_history_snapshot_preview_path",
    "history_snapshot_preview_text_lines",
    "render_history_snapshot_preview",
    "sanitize_history_snapshot_display_text",
]
