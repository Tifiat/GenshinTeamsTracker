"""In-memory PNG artwork for one finalized local PvP game.

The caller owns the localized copy and the chosen output path. This module
does not retain rendered images or inspect account/profile data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from run_workspace.pvp.match_result import (
    MATCH_STATUS_DRAW,
    MATCH_STATUS_FINISHED,
    MATCH_STATUS_TECHNICAL_LOSS,
    MatchResult,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2


@dataclass(frozen=True, slots=True)
class ResultExportLabels:
    title: str
    single_game: str
    chamber: str  # Format string with {number}.
    raw_total: str
    adjusted_total: str
    difference: str
    winner: str
    draw: str
    restarts: str
    paid_restarts: str
    penalty: str
    technical_loss: str


@dataclass(frozen=True, slots=True)
class _ResultView:
    names: tuple[str, str]
    chambers: tuple[tuple[str, str, str], ...]
    raw_totals: tuple[str, str]
    adjusted_totals: tuple[str, str] | None
    source_details: tuple[tuple[str, ...], tuple[str, ...]]
    verdict: str
    difference: str
    technical_loss: bool


def _time(seconds: int | float) -> str:
    value = Decimal(str(seconds))
    minutes, remainder = divmod(value, 60)
    whole = int(remainder)
    fraction = remainder - whole
    suffix = "" if not fraction else f"{fraction:.3f}".split(".", 1)[1].rstrip("0")
    return f"{int(minutes)}:{whole:02d}" + (f".{suffix}" if suffix else "")


def _view(result: MatchResult, names: tuple[str, str], labels: ResultExportLabels) -> _ResultView:
    timers = (result.player_1_timers, result.player_2_timers)
    if (timers[0].seat, timers[1].seat) != (SEAT_PLAYER_1, SEAT_PLAYER_2):
        raise ValueError("Result seats do not match player order")
    if len(timers[0].chambers) != 3 or len(timers[1].chambers) != 3:
        raise ValueError("A finalized local result must contain three chambers per player")
    if result.status not in (MATCH_STATUS_DRAW, MATCH_STATUS_FINISHED, MATCH_STATUS_TECHNICAL_LOSS):
        raise ValueError("Result is not finalized")

    chambers = tuple(
        (labels.chamber.format(number=index),
         _time(timers[0].chambers[index - 1].normalized_elapsed_seconds()),
         _time(timers[1].chambers[index - 1].normalized_elapsed_seconds()))
        for index in range(1, 4)
    )
    raw_totals = tuple(_time(t.total_elapsed_seconds) for t in timers)
    adjusted_totals = None
    details: list[tuple[str, ...]] = [(), ()]
    scoring = result.source_scoring
    if scoring is not None:
        per_seat = scoring.get("per_seat")
        if not isinstance(per_seat, Mapping):
            raise ValueError("Source scoring is missing per-seat totals")
        seat_scores = (per_seat.get(SEAT_PLAYER_1), per_seat.get(SEAT_PLAYER_2))
        if any(not isinstance(item, Mapping) for item in seat_scores):
            raise ValueError("Source scoring is missing a player")
        adjusted_totals = tuple(_time(item["adjusted_seconds"]) for item in seat_scores)
        for index, item in enumerate(seat_scores):
            details[index] = (
                f"{labels.restarts}: {item['restarts']}",
                f"{labels.paid_restarts}: {item['paid_restart_count']}",
                f"{labels.penalty}: +{_time(item['penalty_seconds'])}",
            )

    if result.winner_seat == SEAT_PLAYER_1:
        verdict = f"{labels.winner}: {names[0]}"
    elif result.winner_seat == SEAT_PLAYER_2:
        verdict = f"{labels.winner}: {names[1]}"
    else:
        verdict = labels.draw
    return _ResultView(
        names=names,
        chambers=chambers,
        raw_totals=raw_totals,
        adjusted_totals=adjusted_totals,
        source_details=(details[0], details[1]),
        verdict=verdict,
        difference=f"{labels.difference}: {_time(result.seconds_difference)}",
        technical_loss=result.status == MATCH_STATUS_TECHNICAL_LOSS,
    )


def _wrapped(text: str, font: QFont, width: int) -> list[str]:
    """Keep all nickname characters visible, including long words."""
    metrics = QFontMetrics(font)
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = f"{line} {word}" if line else word
            if metrics.horizontalAdvance(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and metrics.horizontalAdvance(line + char) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines or [""]


def _font(size: int, *, bold: bool = False) -> QFont:
    font = QFont("Segoe UI", size)
    font.setBold(bold)
    return font


def render_result_image(
    result: MatchResult,
    player_1_name: str,
    player_2_name: str,
    labels: ResultExportLabels,
    *,
    width: int = 1400,
) -> QImage:
    """Render a self-contained, deterministic image of one completed game."""
    if width < 800:
        raise ValueError("Result image width must be at least 800 pixels")
    view = _view(result, (player_1_name, player_2_name), labels)
    scale = width / 1400
    name_font = _font(31, bold=True)
    card_width = 620
    names = tuple(_wrapped(name, name_font, card_width - 44) for name in view.names)
    name_line_height = QFontMetrics(name_font).lineSpacing() + 5
    name_height = max(len(lines) for lines in names) * name_line_height
    verdict_lines = _wrapped(view.verdict, _font(31, bold=True), 1200)
    detail_height = 114 if view.adjusted_totals else 0
    base_height = 760 + name_height + detail_height + len(verdict_lines) * 41
    image = QImage(width, round(base_height * scale), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#081724"))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(scale, scale)

        def text(x: int, y: int, value: str, size: int, color: str, *, bold: bool = False) -> None:
            font = _font(size, bold=bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            painter.drawText(x, y, value)

        painter.fillRect(QRectF(0, 0, 1400, 9), QColor("#35d5ed"))
        text(76, 80, labels.title, 35, "#f0fbff", bold=True)
        text(78, 121, labels.single_game, 19, "#89aabd")

        card_y = 155
        card_h = 93 + name_height
        for index, x in enumerate((70, 710)):
            painter.setPen(QPen(QColor("#274959"), 2))
            painter.setBrush(QColor("#102c3b"))
            painter.drawRoundedRect(QRectF(x, card_y, card_width, card_h), 18, 18)
            painter.fillRect(QRectF(x + 2, card_y + 2, 7, card_h - 4), QColor("#35d5ed"))
            for line_index, line in enumerate(names[index]):
                text(x + 29, card_y + 51 + line_index * name_line_height,
                     line, 31, "#f0fbff", bold=True)

        y = card_y + card_h + 67
        for chamber, first, second in view.chambers:
            painter.fillRect(QRectF(70, y - 39, 1260, 66), QColor("#102531"))
            text(100, y + 2, chamber, 24, "#a8c9d7")
            text(552, y + 4, first, 29, "#f0fbff", bold=True)
            text(1193, y + 4, second, 29, "#f0fbff", bold=True)
            y += 78

        y += 23
        text(100, y, labels.raw_total, 24, "#a8c9d7")
        text(542, y + 3, view.raw_totals[0], 33, "#f0fbff", bold=True)
        text(1183, y + 3, view.raw_totals[1], 33, "#f0fbff", bold=True)
        if view.adjusted_totals:
            y += 58
            text(100, y, labels.adjusted_total, 24, "#a8c9d7")
            text(542, y + 3, view.adjusted_totals[0], 33, "#35d5ed", bold=True)
            text(1183, y + 3, view.adjusted_totals[1], 33, "#35d5ed", bold=True)
            y += 47
            for index, x in enumerate((100, 739)):
                text(x, y, "  |  ".join(view.source_details[index]), 17, "#9ec5d3")

        y += 74
        painter.setPen(QPen(QColor("#315564"), 2))
        painter.drawLine(70, y - 37, 1330, y - 37)
        for index, line in enumerate(verdict_lines):
            text(78, y + index * 41, line, 31, "#35d5ed", bold=True)
        y += len(verdict_lines) * 41 + 17
        text(78, y, view.difference, 23, "#c0dce6")
        if view.technical_loss:
            y += 38
            text(78, y, labels.technical_loss, 19, "#e5ac8e")
    finally:
        painter.end()
    return image


def save_result_png(image: QImage, destination: str | Path) -> None:
    """Write a caller-selected PNG; no path is chosen or retained here."""
    if not image.save(str(destination), "PNG"):
        raise OSError(f"Could not write PNG: {destination}")
