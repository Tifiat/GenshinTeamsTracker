"""Provisional Qt composition study, authorized in the History discussion.

Shows only the first frozen Abyss team; it is not imported by AppShell. The
existing card supplies assets, font rendering, frozen data and custom hover.
After visual approval, replace the production painter rather than keeping a
second product renderer. No new product/data contract is pinned by this study.
See ../README.md for acceptance status and bounded visual evidence.
"""
from __future__ import annotations

import argparse
import json
from math import ceil
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from localization import tr
from run_workspace.history_snapshot import HistorySnapshotBundle
from run_workspace.history_browser_catalog import _run_visual
from ui.right_panel.common.history_card import (
    CardPainter, HistoryCardWidget, chamber_values, number, room_enemies,
    seconds, stat_columns, team_seconds, team_slots, tint,
)
from ui.utils.app_scaling import configure_startup_ui_scale
from ui.utils.ui_palette import (
    UI_BG_APP, UI_BG_PANEL, UI_BG_BUTTON_HOVER, UI_BORDER_PANEL,
    UI_TEXT_PRIMARY, UI_TEXT_MUTED, UI_HISTORY_TEAM_1,
)


def stat_value(row):
    return number(int(row.value)) if row.value.isdigit() else row.value


class StudyPainter(CardPainter):
    """Native local coordinates; no width-dependent scaling of type or images."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.u = 1
        self.clipped = []

    def text(self, x, y, width, text, size=14, color=UI_TEXT_PRIMARY, bold=False,
             align=Qt.AlignmentFlag.AlignLeft, **kwargs):
        font = QFont("Segoe UI")
        font.setPixelSize(round(size))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        if QFontMetricsF(font).horizontalAdvance(str(text)) > width + .5:
            self.clipped.append(str(text))
        super().text(x, y, width, text, size, color, bold, align, **kwargs)

    @staticmethod
    def stats_height(team):
        return max(len(c) for slot in team_slots(team) for c in stat_columns(slot)) * 26 + 12

    @staticmethod
    def enemies_height(run, team):
        return 42 if any(room_enemies(run, team, c) for c in (1, 2, 3)) else 0

    @classmethod
    def height(cls, run, expanded):
        team = run.teams[0]
        return 190 + (cls.stats_height(team) + cls.enemies_height(run, team) if expanded else 0)

    def member(self, slot, x, width, expanded, stats_height):
        rect = QRectF(x-5, 40, width+10, 73+stats_height)
        if self.hovered is slot:
            self.rounded(rect, QColor(UI_BG_BUTTON_HOVER), radius=6)
        self.portrait(slot, x, 44, 42)
        # C is attached to the name, never to the far edge of the column.
        name = slot.character_name or tr("app_shell.history.slot.empty")
        font = QFont("Segoe UI")
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        name_width = min(QFontMetricsF(font).horizontalAdvance(name), width-80)
        self.text(x+50, 39, name_width+1, name, 15, bold=True)
        if slot.constellation is not None:
            self.text(x+50+name_width+6, 41, 25, f"C{slot.constellation}", 12, UI_TEXT_MUTED)
        self.icon(slot.weapon_icon_path, x+48, 65, 27)
        self.text(x+77, 69, 20, f"R{slot.weapon_refinement}" if slot.weapon_refinement is not None else "—", 13)
        for index, path in enumerate(slot.set_icon_paths[:2]):
            sx = x+101+index*33
            self.icon(path, sx, 65, 27)
            count = slot.set_counts[index] if index < len(slot.set_counts) else ""
            self.rounded(QRectF(sx+18, 82, 14, 15), QColor(UI_BG_PANEL), radius=3)
            self.text(sx+18, 78, 14, str(count), 12, UI_TEXT_PRIMARY, True, Qt.AlignmentFlag.AlignCenter)
        self.text(x, 92, 47, tr("history.card.level").format(value=slot.character_level or "—"), 11, UI_TEXT_MUTED)
        self.text(x+50, 91, width-50, slot.stat_badge or "—", 13)
        if expanded:
            halves = stat_columns(slot)
            half_width = (width-10)/2
            for col, rows in enumerate(halves):
                for i, row in enumerate(rows):
                    if row is None:
                        continue
                    sy = 122+i*26
                    sx = x+col*(half_width+10)
                    key = row.icon_label or row.key or row.label
                    font.setPixelSize(11)
                    font.setWeight(QFont.Weight.Normal)
                    label_width = QFontMetricsF(font).horizontalAdvance(key)+1
                    self.text(sx, sy+2, label_width, key, 11, UI_TEXT_MUTED)
                    self.text(sx+label_width+4, sy, half_width-label_width-4,
                              stat_value(row), 14, UI_TEXT_PRIMARY, False, Qt.AlignmentFlag.AlignRight)
        self.hits.append((rect, slot))

    def result(self, run, team, chamber, rect, expanded):
        x, y, width = rect.x(), rect.y(), rect.width()
        duration, factual, simulated = chamber_values(run, team, chamber)
        self.text(x, y+1, 34, f"{run.floor or '—'}-{chamber}", 12, UI_TEXT_MUTED)
        self.text(x+44, y-3, width-44, seconds(duration), 19, bold=True)
        values_y = y+26
        for sx, label, value in (
            (x, tr("history.card.fact_short"), factual),
            (x+width*.57, tr("history.card.sim_short"), simulated),
        ):
            self.text(sx, values_y+1, 34, label, 12, UI_TEXT_MUTED)
            value_width = width*.57-38 if sx == x else width*.43-38
            self.text(sx+38, values_y, value_width, number(value), 14)
        if expanded:
            for index, enemy in enumerate(room_enemies(run, team, chamber)):
                ex, ey = x+index*38, y+52
                self.icon(enemy.icon_path, ex, ey, 34, enemy.name[:2])
                if enemy.count > 1:
                    self.rounded(QRectF(ex+17, ey+22, 24, 15), QColor(UI_BG_PANEL), radius=3)
                    self.text(ex+17, ey+19, 24, f"×{enemy.count}", 11, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                tooltip = tr("app_shell.history.enemy.tooltip").format(
                    name=enemy.name or "—", level=enemy.level or "—", count=enemy.count,
                    wave=enemy.wave, hp=number(enemy.hp))
                self.hits.append((QRectF(ex, ey, 38, 38), tooltip))

    def team(self, run, expanded):
        team = run.teams[0]
        w = self.layout.width
        self.rounded(QRectF(0, 0, w, self.height(run, expanded)), QColor(UI_BG_PANEL), radius=9)
        self.rounded(QRectF(16, 15, 5, 15), QColor(UI_HISTORY_TEAM_1), radius=2)
        self.text(29, 11, 95, tr("history.card.team").format(value=team.team_index+1), 14, bold=True)
        self.text(131, 7, 80, seconds(team_seconds(run, team)), 20, bold=True)
        for i, bonus in enumerate(team.bonuses):
            x = 220+i*30
            self.p.setOpacity(1 if bonus.applied else .45)
            self.icon(bonus.icon_path, x, 10, 24, bonus.label[:2])
            self.p.setOpacity(1)
            self.hits.append((QRectF(x, 10, 27, 27), bonus.tooltip))
        column = (w-32-3*16)/4
        stats = self.stats_height(team) if expanded else 0
        for i, slot in enumerate(team_slots(team)):
            self.member(slot, 16+i*(column+16), column, expanded, stats)
        room_y = 123+stats
        self.line(16, room_y, w-16, room_y, UI_BORDER_PANEL, 255)
        cell = (w-32-2*24)/3
        for chamber in (1, 2, 3):
            self.result(run, team, chamber, QRectF(16+(chamber-1)*(cell+24), room_y+9, cell, 60), expanded)


class StudyWidget(HistoryCardWidget):
    @property
    def content_scale(self):
        # The current 1366px display starts Qt at 0.711458. Preserve the study's
        # minimum rendered text size without changing AppShell's global scale.
        return max(1., 1./self.devicePixelRatioF())

    def set_study_width(self, width):
        self.setFixedWidth(round(width*self.content_scale))

    def design_height(self):
        return ceil(StudyPainter.height(self.run, self.expanded)*self.content_scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        scale = self.content_scale
        painter.scale(scale, scale)
        draw = StudyPainter(painter, self._images, self.character_view,
                            width=self.width()/scale, hovered=self._hover)
        draw.team(self.run, self.expanded)
        self._hits = [(QRectF(r.x()*scale, r.y()*scale, r.width()*scale, r.height()*scale), value)
                      for r, value in draw.hits]
        self.clipped = draw.clipped
        painter.end()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    configure_startup_ui_scale()
    app = QApplication([])
    run = _run_visual(HistorySnapshotBundle.from_dict(json.loads(args.snapshot.read_text(encoding="utf-8"))), args.snapshot)
    window = QWidget()
    window.setWindowTitle("GTT History · Qt study v3")
    window.setStyleSheet(f"QWidget {{ background: {UI_BG_APP}; color: {UI_TEXT_PRIMARY}; }} QComboBox {{ padding: 7px; }}")
    layout = QVBoxLayout(window)
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(14)
    toolbar = QHBoxLayout()
    width_choice, view_choice = QComboBox(), QComboBox()
    for width in (720, 864, 1220):
        width_choice.addItem(f"{width} px", width)
    width_choice.setCurrentIndex(1)
    for view in ("profile", "portrait"):
        view_choice.addItem(tr(f"settings.history.{view}"), view)
    toolbar.addWidget(width_choice)
    toolbar.addWidget(view_choice)
    toolbar.addStretch()
    layout.addLayout(toolbar)
    card = StudyWidget(run)
    card.set_study_width(864)
    layout.addWidget(card)
    card.clicked.connect(lambda: (card.set_expanded(not card.expanded), window.adjustSize()))
    width_choice.currentIndexChanged.connect(lambda: (card.set_study_width(width_choice.currentData()), window.adjustSize()))
    view_choice.currentIndexChanged.connect(lambda: card.set_character_view(view_choice.currentData()))
    window.show()
    app.processEvents()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        for width in (720, 864, 1220):
            card.set_study_width(width)
            for view in ("profile", "portrait"):
                card.set_character_view(view)
                for expanded in (False, True):
                    card.set_expanded(expanded)
                    app.processEvents()
                    pixmap = card.grab()
                    # Keep the actual rendered pixels. Never enlarge a downscaled
                    # screenshot and mistake its interpolated text for UI output.
                    image = pixmap.toImage()
                    image.setDevicePixelRatio(1)
                    image.save(str(args.output / f"team-{width}-{view}-{'expanded' if expanded else 'compact'}.png"))
                    print(json.dumps(dict(width=width, view=view, expanded=expanded,
                        rendered_size=[image.width(), image.height()], dpr=card.devicePixelRatioF(),
                        character_regions=sum(hasattr(v, 'character_name') for _, v in card._hits),
                        clipped=card.clipped), ensure_ascii=False))
        card.set_study_width(864)
        card.set_character_view("profile")
        card.set_expanded(False)
        window.adjustSize()
    return app.exec() if args.show else 0


if __name__ == "__main__":
    raise SystemExit(main())
