"""Frozen History cards laid out in widget pixels; PNG reuses the same composition."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from localization import tr
from run_workspace.history_browser_catalog import HistoryRunVisual, HistorySlotVisual
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.owner_icon_badge import DEFAULT_OWNER_BADGE_SIZE_RATIO
from ui.utils.tooltips import CUSTOM_TOOLTIP_DELAY_MS, CustomTooltipPopup, anchored_tooltip_rect
from ui.utils.ui_palette import (
    UI_BG_APP, UI_BG_PANEL_RAISED, UI_TEXT_PRIMARY, UI_TEXT_MUTED,
    UI_HISTORY_TEAM_1, UI_HISTORY_TEAM_2, UI_ELEMENT_ACCENTS,
    UI_HISTORY_BG_TOP, UI_HISTORY_BG_BOTTOM, UI_HISTORY_BORDER,
    UI_HISTORY_TEXT, UI_HISTORY_MUTED, UI_HISTORY_FACT, UI_HISTORY_SIM, UI_HISTORY_GRID,
    UI_HISTORY_ALT_TOP, UI_HISTORY_ALT_BOTTOM,
)

# Only the export chooses a reference width. On-screen geometry uses actual
# logical widget pixels; it never shrinks typography to fit a design canvas.
CARD_WIDTH = 1200


def number(value) -> str:
    return "—" if value is None else f"{float(value):,.0f}".replace(",", " ")


def seconds(value) -> str:
    return "—" if value is None else tr("history.card.seconds").format(value=f"{value:g}")


def team_slots(team):
    by_index = {slot.slot_index: slot for slot in team.slots}
    return tuple(by_index.get(i, HistorySlotVisual(slot_index=i)) for i in range(4))


def stat_rows(slot):
    order = {key: i for i, key in enumerate(("HP", "ATK", "DEF", "EM", "CR", "CD", "ER"))}
    return tuple(sorted(slot.stat_rows, key=lambda row: order.get(row.key or row.icon_label, 7)))


def stat_columns(slot):
    rows = stat_rows(slot)
    by_key = {row.key or row.icon_label: row for row in rows}
    return (tuple(by_key.get(key) for key in ("HP", "ATK", "DEF", "EM")),
            tuple(by_key.get(key) for key in ("CR", "CD", "ER")) + tuple(
                row for row in rows if (row.key or row.icon_label) not in
                {"HP", "ATK", "DEF", "EM", "CR", "CD", "ER"}))


def visible_teams(run):
    return run.teams[:2 if run.run_type == "abyss" else 1]


def chamber_values(run, team, chamber):
    item = next((row for row in run.chambers if row.chamber_index == chamber), None)
    side = team.team_index
    if item is None or side not in (0, 1):
        return None, None, None
    return item.side_times[side], item.factual_dps[side], item.sim_dps[side]


def team_seconds(run, team):
    if run.run_type != "abyss":
        return run.duration_seconds
    values = [chamber_values(run, team, c)[0] for c in (1, 2, 3)]
    return None if any(v is None for v in values) else sum(values)


def total_seconds(run):
    values = [team_seconds(run, team) for team in visible_teams(run)]
    return None if not values or any(v is None for v in values) else sum(values)


def display_period(run):
    """Month/year period, without mixing the save timestamp into Abyss dates."""
    source = run.period_start if run.run_type == "abyss" else run.created_at
    try:
        start = date.fromisoformat(source[:10])
    except ValueError:
        return "—"
    label = f"{start.month}.{start.year}"
    if run.run_type == "abyss":
        try:
            end = date.fromisoformat(run.period_end[:10])
            if (end-start).days >= 7 and (end.year, end.month) != (start.year, start.month):
                label += f"–{end.month}.{end.year}"
        except ValueError:
            pass
    return label


def room_enemies(run, team, chamber):
    return next((side.enemies for side in run.sides
                 if side.side == team.team_index + 1 and side.chamber == chamber), ())


@dataclass(frozen=True)
class CardLayout:
    width: float

    @property
    def unit(self):
        return 1.

    @property
    def header(self):
        return 48

    @property
    def team_header(self):
        return 6

    @property
    def identity_width(self):
        return 180 if self.width >= 1000 else 132

    @property
    def body_x(self):
        return self.identity_width+16

    @property
    def body_width(self):
        return self.width-self.body_x-12

    @property
    def expanded_columns(self):
        return 4 if self.width >= 800 else 2

    @property
    def columns(self):
        return 4 if self.width >= 680 else 2

    @property
    def column_width(self):
        return self.body_width/self.expanded_columns

    @property
    def portrait_size(self):
        return min(80., max(60., (self.column_width-16)*.42))

    def wraps_build(self, team):
        return self.column_width < 200 and any(len(s.set_icon_paths) > 1 for s in team.slots)

    def character_header(self, team):
        tiles = max((1+min(2, len(s.set_icon_paths)) for s in team.slots), default=1)
        rows = ceil(tiles/self.equipment_columns)
        return ceil(max(self.portrait_size, 24+rows*(self.equipment_size+4)-4)+24)

    @property
    def equipment_size(self):
        return min(self.portrait_size-24, max(34., (self.column_width-self.portrait_size-26)/2))

    @property
    def equipment_columns(self):
        return max(1, int((self.column_width-self.portrait_size-18)/(self.equipment_size+4)))

    def stats_height(self, team):
        count = max((len(col) for slot in team.slots for col in stat_columns(slot)), default=4)
        return max(4, count)*22+6

    def member_row_height(self, team, expanded):
        return self.character_header(team)+(self.stats_height(team) if expanded else 0)

    @property
    def room_width(self):
        return self.body_width/3

    @property
    def stacked_metrics(self):
        return self.room_width < 200

    def enemy_capacity(self):
        space = self.room_width-(108 if self.room_inline_enemies else 12)
        return max(1, int(space/self.enemy_step))

    @property
    def enemy_size(self):
        return min(68., max(52., (self.room_width-108)/3-4))

    @property
    def enemy_step(self):
        return self.enemy_size+4

    @property
    def room_inline_enemies(self):
        return self.room_width >= 290

    def room_height(self, run, team, expanded):
        if run.run_type != "abyss":
            return 84
        base = 86 if self.stacked_metrics else 64
        if not expanded:
            return base
        count = max((len(room_enemies(run, team, c)) for c in (1, 2, 3)), default=0)
        if self.room_inline_enemies:
            return max(88, ceil(count/self.enemy_capacity())*self.enemy_step+10)
        return base+ceil(count/self.enemy_capacity())*self.enemy_step

    def team_height(self, run, team, expanded):
        rows = ceil(4/self.expanded_columns)
        return (self.team_header + rows*self.member_row_height(team, expanded)
                +(rows-1)*8+self.room_height(run, team, expanded)+6)

    @property
    def compact_header(self):
        return 2

    def compact_wraps_build(self, team):
        return self.compact_column_width < 182 or (self.compact_column_width < 232 and any(len(s.set_icon_paths) > 1 for s in team.slots))

    @property
    def compact_total_width(self):
        return 104

    @property
    def compact_body_width(self):
        return self.width-self.compact_total_width

    @property
    def compact_column_width(self):
        return (self.compact_body_width-24)/self.columns

    def compact_member_height(self, team):
        return 64 if self.compact_wraps_build(team) else 44

    @property
    def compact_portrait_size(self):
        return min(42., max(34., (self.compact_column_width-90)/3))

    @property
    def compact_team_width(self):
        return min(248., max(224., self.compact_body_width*.33))

    @property
    def compact_room_width(self):
        return (self.compact_body_width-24-self.compact_team_width)/3

    def compact_results_height(self, run):
        return 42

    def compact_inline(self, run):
        # Keep the character groups readable before allocating a right-hand
        # result table. Two-set builds need one extra equipment tile per slot.
        has_two_sets = any(len(s.set_icon_paths) > 1 for t in visible_teams(run) for s in t.slots)
        return self.width >= (1320 if has_two_sets else 1160)

    @property
    def compact_inline_results_width(self):
        return 256

    def compact_team_height(self, run, team):
        if run.run_type == "abyss" and self.compact_inline(run):
            return 58
        return ceil(4/self.columns)*self.compact_member_height(team)+self.compact_results_height(run)+2

    def height(self, run, expanded):
        if not expanded:
            return ceil(self.compact_header+sum(self.compact_team_height(run, team)
                        for team in visible_teams(run))+2)
        return ceil(self.header+sum(self.team_height(run, team, expanded)+10
                                   for team in visible_teams(run))+2)


def detail_height(run, width=CARD_WIDTH):
    return CardLayout(width).height(run, True)


def summary_height(run, width=CARD_WIDTH):
    return CardLayout(width).height(run, False)


def prepare_images(run, dpr, artwork_paths=None):
    paths = set()
    portraits = set()
    bonus_paths = set()
    for team in visible_teams(run):
        bonus_paths.update(b.icon_path for b in team.bonuses if b.icon_path)
        for slot in team.slots:
            paths.update((slot.portrait_path, slot.side_icon_path, slot.weapon_icon_path, *slot.set_icon_paths))
            portraits.add(slot.portrait_path)
            paths.update(b.icon_path for b in slot.bonuses)
    paths.update(enemy.icon_path for side in run.sides for enemy in side.enemies)
    images = {path: load_hidpi_pixmap(path, 112, dpr=dpr, trim_alpha=path in portraits, surface="history_card").pixmap
              for path in paths if path}
    # Normalize bonus content in compact and expanded identity panels alike.
    images.update({("bonus", path): load_hidpi_pixmap(path, 112, dpr=dpr, trim_alpha=True,
                   trim_alpha_threshold=64, surface="history_bonus").pixmap for path in bonus_paths})
    for team in visible_teams(run):
        custom = (artwork_paths or {}).get(team.team_index)
        lead = next((slot for slot in team_slots(team) if slot.character_name), None)
        path = custom or ((lead.portrait_path or lead.side_icon_path) if lead else "")
        if path:
            images[("artwork", team.team_index)] = load_hidpi_pixmap(
                path, 420, dpr=dpr, trim_alpha=True, surface="history_artwork").pixmap
    return images


@dataclass(frozen=True)
class ArtworkAction:
    team_index: int
    reset: bool = False


def tint(color, alpha):
    value = QColor(color)
    value.setAlpha(alpha)
    return value


class CardPainter:
    """All screen and hit-test coordinates are local logical widget pixels."""
    def __init__(self, painter, images, character_view, *, width=CARD_WIDTH, hovered=None, alternate=False,
                 artwork_paths=None, interactive=False):
        self.p = painter
        self.images = images
        self.character_view = character_view
        self.layout = CardLayout(width)
        self.u = self.layout.unit
        self.hits = []
        self.hovered = hovered
        self.alternate = alternate
        self.artwork_paths = artwork_paths or {}
        self.interactive = interactive
        self.p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    def text(self, x, y, width, text, size=13, color=UI_HISTORY_TEXT, bold=False,
             align=Qt.AlignmentFlag.AlignLeft, *, italic=False):
        font = QFont("Segoe UI")
        font.setPixelSize(round(size))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        font.setItalic(italic)
        self.p.setFont(font)
        self.p.setPen(QColor(color))
        label = QFontMetricsF(font).elidedText(str(text), Qt.TextElideMode.ElideRight, max(1., width))
        self.p.drawText(QRectF(x, y, width, size + 7), align | Qt.AlignmentFlag.AlignVCenter, label)

    def icon(self, path, x, y, size, fallback=""):
        pixmap = self.images.get(path)
        if pixmap is None or pixmap.isNull():
            if fallback:
                self.text(x, y, size, fallback, 12, UI_HISTORY_MUTED, align=Qt.AlignmentFlag.AlignCenter)
            return
        ratio = min(size / pixmap.width(), size / pixmap.height())
        w, h = pixmap.width() * ratio, pixmap.height() * ratio
        self.p.drawPixmap(QRectF(x+(size-w)/2, y+(size-h)/2, w, h), pixmap, QRectF(pixmap.rect()))

    def line(self, x, y, x2, y2, color=UI_HISTORY_BORDER, alpha=130):
        self.p.setPen(QPen(tint(color, alpha), 1))
        self.p.drawLine(QPointF(x, y), QPointF(x2, y2))

    def rounded(self, rect, fill, border=None, radius=5):
        self.p.setBrush(fill if isinstance(fill, (QColor, QLinearGradient)) else QColor(fill))
        self.p.setPen(Qt.PenStyle.NoPen if border is None else QPen(border, 1))
        self.p.drawRoundedRect(rect, radius, radius)

    def surface(self, rect, accent, *, strong=False):
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, tint(accent, 57 if strong else 26))
        gradient.setColorAt(.55, tint(UI_HISTORY_BG_TOP, 235))
        gradient.setColorAt(1, tint(UI_HISTORY_BG_BOTTOM, 250))
        self.rounded(rect, gradient, tint(accent, 118 if strong else 62), 7*self.u)

    def portrait(self, slot, x, y, size, *, soft_crop=False):
        path = slot.side_icon_path if self.character_view == "profile" else slot.portrait_path
        if self.character_view == "profile" and slot.side_icon_path:
            # ArtifactCardDelegate uses the original calibrated side-icon canvas,
            # not per-character alpha bounds. Its shared badge ratio defines the
            # face scale; hats may extend above the text instead of shrinking it.
            canvas = size*.90/DEFAULT_OWNER_BADGE_SIZE_RATIO
            self.icon(path, x+(size-canvas)/2, y+size+1-canvas, canvas)
            return
        if soft_crop:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(x, y, size, size), 7, 7)
            self.p.save()
            self.p.setClipPath(clip)
        self.icon(path or slot.portrait_path or slot.side_icon_path,
                  x-2 if soft_crop else x, y-2 if soft_crop else y,
                  size+4 if soft_crop else size, slot.character_name[:1] or "—")
        if soft_crop:
            self.p.restore()

    def pill(self, x, y, width, text, color, *, size=11):
        self.rounded(QRectF(x, y, width, 18*self.u), tint(color, 38), tint(color, 90), 4*self.u)
        self.text(x, y-1, width, text, size*self.u, color, True, Qt.AlignmentFlag.AlignCenter)

    @staticmethod
    def measure(text, size=14, bold=False):
        font = QFont("Segoe UI")
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return QFontMetricsF(font).horizontalAdvance(str(text))

    def separator(self, x, y, length, *, vertical=False, alpha=90):
        """One continuous faded separator, shared by all table boundaries."""
        gradient = QLinearGradient(x, y, x if vertical else x+length, y+length if vertical else y)
        for stop, opacity in ((0., 0), (.14, alpha), (.86, alpha), (1., 0)):
            gradient.setColorAt(stop, tint(UI_HISTORY_GRID, opacity))
        self.p.fillRect(QRectF(x, y, 1 if vertical else length, length if vertical else 1), gradient)

    def header(self, run):
        w = self.layout.width
        title = (tr("history.card.abyss").format(floor=run.floor or "—")
                 if run.run_type == "abyss" else tr("history.card.dummy"))
        duration = seconds(total_seconds(run))
        time_width = self.measure(duration, 30, True)+8
        self.text(16, 3, time_width, duration, 30, UI_HISTORY_TEAM_2, True)
        # Symmetric gutters center the title on the whole card, not on whatever
        # blank space happens to remain beside a differently sized timer.
        gutter = max(160., time_width+32)
        self.text(gutter, 1, w-2*gutter, title, 20, bold=True, align=Qt.AlignmentFlag.AlignCenter)
        self.text(gutter, 25, w-2*gutter, display_period(run), 14, UI_HISTORY_MUTED,
                  align=Qt.AlignmentFlag.AlignCenter)

    def bonuses(self, team, x, y, right, *, size=25, prominent=False):
        step = size+5
        capacity = max(0, int((right-x)/step))
        shown = team.bonuses[:max(0, capacity-1)] if len(team.bonuses) > capacity else team.bonuses
        for bonus in shown:
            self.p.setOpacity(1. if bonus.applied else .4)
            if prominent:
                self.rounded(QRectF(x-1, y-1, size+2, size+2), tint(UI_HISTORY_TEXT, 13),
                             tint(UI_HISTORY_GRID, 75), 4)
            path = ("bonus", bonus.icon_path) if prominent else bonus.icon_path
            self.icon(path, x, y, size, bonus.label[:2])
            self.p.setOpacity(1.)
            self.hits.append((QRectF(x, y, step, size+3), bonus.tooltip))
            x += step
        rest = team.bonuses[len(shown):]
        if rest and capacity:
            self.text(x, y+(2 if size >= 25 else -3), step, f"+{len(rest)}", 12, UI_HISTORY_MUTED, True)
            self.hits.append((QRectF(x, y, step, size+3), "\n\n".join(b.tooltip for b in rest)))

    def compact_character(self, slot, rect, accent, team, *, inline=False):
        """Character, weapon and active sets share one full-height icon strip."""
        x, y, w = rect.x(), rect.y(), rect.width()
        element = UI_ELEMENT_ACCENTS.get(slot.element.casefold(), accent)
        glow = QLinearGradient(x, y, x+w, y)
        glow.setColorAt(0, tint(element, 18))
        glow.setColorAt(1, tint(element, 0))
        self.rounded(rect.adjusted(1, 1, -1, -1), glow, radius=3)
        if self.hovered is slot:
            self.rounded(rect.adjusted(1, 1, -1, -1), tint(element, 20), radius=3)
        wrap = not inline and self.layout.compact_wraps_build(team)
        paths = (slot.weapon_icon_path, *slot.set_icon_paths[:2])
        face = min(42., (w-8)/(1+len(paths))) if wrap else self.layout.compact_portrait_size
        equipment = face-(6 if inline else 4)
        iy = y+(44-face)/2
        self.portrait(slot, x+2, iy, face)
        labels = ("" if slot.weapon_refinement is None else f"R{slot.weapon_refinement}",
                  *(str(n) for n in slot.set_counts[:2]))
        for i, path in enumerate(paths):
            ix = x+3+face+i*(equipment+1)
            ey = iy+2
            self.icon(path, ix, ey, equipment)
            if i < len(labels) and labels[i]:
                lw = self.measure(labels[i], 11)+5
                self.rounded(QRectF(ix+equipment-lw, ey+equipment-14, lw, 14), tint(UI_HISTORY_BG_BOTTOM, 225), radius=3)
                self.text(ix+equipment-lw, ey+equipment-17, lw, labels[i], 11, align=Qt.AlignmentFlag.AlignCenter)
        constellation = "" if slot.constellation is None else f"C{slot.constellation}"
        tx = x+7+face+len(paths)*(equipment+1)
        available = x+w-4-tx
        level = tr("history.card.level").format(value=slot.character_level or "—")
        name = slot.character_name or tr("app_shell.history.slot.empty")
        if wrap:
            # At a narrow width keep all equipment full-sized and put the two
            # text fields below the icon strip, rather than shrink the icons.
            bx = x+w-5-self.measure(slot.stat_badge or "—", 11)
            self.character_name(x+3, y+43, max(1, bx-x-7), name, constellation, element, size=12)
            self.text(bx, y+43, x+w-4-bx, slot.stat_badge or "—", 11)
            self.text(x+w-46, y-2, 43, level, 10, UI_HISTORY_MUTED, align=Qt.AlignmentFlag.AlignRight)
        else:
            self.character_name(tx, y-4, available, name, constellation, element, size=13)
            self.text(tx, y+11, available, level, 10, UI_HISTORY_MUTED)
            self.text(tx, y+25, available, slot.stat_badge or "—", 11)
        self.hits.append((rect, slot))

    def character_name(self, x, y, width, name, constellation, element, *, size=14):
        """Keep C beside the displayed name, never over the character's face."""
        cw = self.measure(constellation, 11)+6 if constellation else 0
        name_width = min(self.measure(name, size, True)+2, max(1, width-cw))
        self.text(x, y, name_width, name, size, bold=True)
        if constellation:
            self.text(x+name_width+4, y+(size-11)/2, cw-4, constellation, 11, element)

    def compact_results(self, run, team, y, accent):
        height = self.layout.compact_results_height(run)
        team_width = self.layout.compact_team_width
        body_width = self.layout.compact_body_width
        gradient = QLinearGradient(8, y, body_width-8, y)
        gradient.setColorAt(0, tint(accent, 32))
        gradient.setColorAt(1, tint(accent, 5))
        self.rounded(QRectF(7, y, body_width-14, height), gradient, radius=3)
        self.line(10, y, body_width-10, y, accent, 85)
        self.compact_team_heading(run, team, QRectF(6, y+4, team_width, 34), accent)
        start = 12+team_width
        if run.run_type != "abyss":
            self.text(start+7, y, body_width-start-20,
                      run.target_label or tr("app_shell.history.dps.target_unavailable"), 12, bold=True)
            self.text(start+7, y+18, body_width-start-20,
                      run.target_setup or tr("app_shell.history.dps.setup_unavailable"), 11, UI_HISTORY_MUTED)
            return
        self.compact_chambers(run, team, QRectF(start, y+10, body_width-12-start, 24), accent)

    def compact_team_heading(self, run, team, rect, accent):
        """Reading order: team identity, large resonances/bonuses, team time."""
        x, y, w = rect.x(), rect.y(), rect.width()
        label = tr("history.card.team").format(value=team.team_index+1)
        label_width = self.measure(label, 12, True)+6
        self.text(x+7, y+6, label_width, label, 12, bold=True)
        duration = seconds(team_seconds(run, team))
        time_width = self.measure(duration, 21, True)+7
        time_x = x+w-time_width-6
        self.bonuses(team, x+7+label_width+4, y+1, time_x-6, size=30, prominent=True)
        self.text(time_x, y+1, time_width, duration, 21, accent, True,
                  Qt.AlignmentFlag.AlignRight)

    def compact_chambers(self, run, team, rect, accent):
        cw = rect.width()/3
        for i, chamber in enumerate((1, 2, 3)):
            x, y = rect.x()+i*cw, rect.y()
            duration, _, _ = chamber_values(run, team, chamber)
            if i:
                self.line(x, y+3, x, y+20, UI_HISTORY_GRID, 105)
            self.text(x+5, y+3, 29, f"{run.floor or '—'}-{chamber}", 11, UI_HISTORY_MUTED)
            self.text(x+35, y, cw-40, seconds(duration), 15, UI_HISTORY_TEXT, True)

    def compact_inline_results(self, run, team, rect, accent):
        x, y, w = rect.x(), rect.y(), rect.width()
        self.compact_team_heading(run, team, QRectF(x, y, w, 34), accent)
        self.line(x+7, y+33, x+w-5, y+33, accent, 105)
        self.compact_chambers(run, team, QRectF(x+2, y+32, w-4, 24), accent)

    def compact_total(self, run):
        x, w = self.layout.compact_body_width, self.layout.compact_total_width
        h = self.layout.height(run, False)
        accent = UI_HISTORY_TEAM_2
        gradient = QLinearGradient(x, 0, x+w, h)
        gradient.setColorAt(0, tint(accent, 35))
        gradient.setColorAt(1, tint(accent, 12))
        self.rounded(QRectF(x+2, 5, w-8, h-10), gradient, tint(accent, 135), 6)
        self.text(x+6, h/2-27, w-16, tr("history.card.total_label"), 13,
                  UI_HISTORY_TEXT, False, Qt.AlignmentFlag.AlignCenter)
        value = seconds(total_seconds(run))
        size = 30 if self.measure(value, 30, True) <= w-14 else 24
        self.text(x+5, h/2-9, w-14, value, size, accent, True, Qt.AlignmentFlag.AlignCenter)

    def compact_teams(self, run):
        y = self.layout.compact_header
        inline = run.run_type == "abyss" and self.layout.compact_inline(run)
        body_width = self.layout.compact_body_width
        cw = (body_width-24-self.layout.compact_inline_results_width)/4 if inline else self.layout.compact_column_width
        for index, team in enumerate(visible_teams(run)):
            accent = UI_HISTORY_TEAM_1 if index == 0 else UI_HISTORY_TEAM_2
            if index:
                self.line(10, y-1, body_width-7, y-1, UI_HISTORY_GRID, 95)
            if inline:
                band = QRectF(7, y, body_width-14, 57)
                gradient = QLinearGradient(band.topLeft(), band.bottomRight())
                gradient.setColorAt(0, tint(accent, 12))
                gradient.setColorAt(1, tint(accent, 3))
                self.rounded(band, gradient, radius=3)
            row_height = self.layout.compact_member_height(team)
            for i, slot in enumerate(team_slots(team)):
                col, row = i%self.layout.columns, i//self.layout.columns
                x = 12+col*cw
                cy = y+7 if inline else y+row*row_height
                self.compact_character(slot, QRectF(x, cy, cw, row_height), accent, team, inline=inline)
                if col:
                    self.line(x, cy+3, x, cy+row_height-3, UI_HISTORY_GRID, 105)
            if inline:
                rx = 12+4*cw
                self.line(rx, y+3, rx, y+55, accent, 170)
                self.compact_inline_results(run, team,
                    QRectF(rx, y, self.layout.compact_inline_results_width, 58), accent)
            else:
                self.compact_results(run, team, y+ceil(4/self.layout.columns)*row_height, accent)
            y += self.layout.compact_team_height(run, team)
        self.compact_total(run)

    def team_identity(self, run, team, y, room_y, accent):
        """Left identity/art stays above its timer, aligned with room results."""
        x, w = 12, self.layout.identity_width-4
        rect = QRectF(x, y+6, w, room_y-y-10)
        lead = next((slot for slot in team_slots(team) if slot.character_name), None)
        element = UI_ELEMENT_ACCENTS.get(lead.element.casefold(), accent) if lead else accent
        self.surface(rect, element, strong=True)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 6, 6)
        self.p.save()
        self.p.setClipPath(clip)
        image = self.images.get(("artwork", team.team_index))
        if image is not None and not image.isNull():
            # One centered cover crop, shared by local portraits and custom art.
            art = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
            ratio = max(art.width()/image.width(), art.height()/image.height())
            iw, ih = image.width()*ratio, image.height()*ratio
            self.p.drawPixmap(QRectF(art.center().x()-iw/2, art.center().y()-ih/2, iw, ih), image, QRectF(image.rect()))
        fade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fade.setColorAt(0, tint(UI_HISTORY_BG_BOTTOM, 32))
        fade.setColorAt(.42, tint(UI_HISTORY_BG_BOTTOM, 0))
        fade.setColorAt(.78, tint(UI_HISTORY_BG_BOTTOM, 190))
        fade.setColorAt(1, QColor(UI_HISTORY_BG_BOTTOM))
        self.p.fillRect(rect, fade)
        edge = QLinearGradient(rect.topLeft(), rect.topRight())
        edge.setColorAt(0, tint(element, 28))
        edge.setColorAt(.65, tint(UI_HISTORY_BG_BOTTOM, 0))
        edge.setColorAt(1, tint(UI_HISTORY_BG_BOTTOM, 155))
        self.p.fillRect(rect, edge)
        self.p.restore()
        self.pill(x+8, y+13, 28, f"{team.team_index+1:02d}", accent, size=12)
        self.bonuses(team, x+8, rect.bottom()-40, x+w-5, size=32, prominent=True)
        if self.interactive:
            action = ArtworkAction(team.team_index)
            art_hit = rect.adjusted(0, 0, 0, -44)
            active = isinstance(self.hovered, ArtworkAction) and self.hovered.team_index == team.team_index
            if active:
                self.rounded(art_hit.adjusted(4, 4, -4, -4), tint(UI_HISTORY_BG_BOTTOM, 155), radius=5)
                self.text(x+5, art_hit.center().y()-12, w-10, tr("history.card.artwork.change"),
                          12, bold=True, align=Qt.AlignmentFlag.AlignCenter)
                if team.team_index in self.artwork_paths:
                    reset = QRectF(x+8, art_hit.bottom()-27, w-16, 22)
                    self.text(reset.x(), reset.y(), reset.width(), tr("history.card.artwork.reset"),
                              11, UI_HISTORY_MUTED, align=Qt.AlignmentFlag.AlignCenter)
                    self.hits.append((reset, ArtworkAction(team.team_index, reset=True)))
            self.hits.append((art_hit, action))
        timer_h = self.layout.room_height(run, team, True)-6
        self.surface(QRectF(x, room_y+3, w, timer_h), accent, strong=True)
        self.text(x+10, room_y+10, w-20, tr("history.card.team").format(value=team.team_index+1),
                  12, UI_HISTORY_MUTED)
        self.text(x+10, room_y+29, w-20, seconds(team_seconds(run, team)), 28, accent, True)

    def character(self, slot, rect, expanded, accent, team):
        x, y, w = rect.x(), rect.y(), rect.width()
        face = self.layout.portrait_size
        element = UI_ELEMENT_ACCENTS.get(slot.element.casefold(), accent)
        self.rounded(rect.adjusted(2, 2, -2, -3), tint(UI_HISTORY_BG_BOTTOM, 135),
                     tint(UI_HISTORY_GRID, 125), 6)
        # Subtle element light behind the enlarged, alpha-trimmed portrait.
        glow = QLinearGradient(x, y, x+w, y+face+8)
        glow.setColorAt(0, tint(element, 34))
        glow.setColorAt(1, tint(element, 6))
        self.rounded(QRectF(x+3, y+3, w-6, self.layout.character_header(team)-4), glow, radius=5)
        if self.hovered is slot:
            self.rounded(rect.adjusted(3, 2, -3, -2), tint(element, 17), radius=5)
        self.portrait(slot, x+6, y+4, face, soft_crop=True)
        name = slot.character_name or tr("app_shell.history.slot.empty")
        level = tr("history.card.level").format(value=slot.character_level or "—")
        constellation = "" if slot.constellation is None else f"C{slot.constellation}"
        tx = x+face+14
        self.character_name(tx, y+1, x+w-6-tx, name, constellation, element)
        size = self.layout.equipment_size
        paths = (slot.weapon_icon_path, *slot.set_icon_paths[:2])
        labels = ("—" if slot.weapon_refinement is None else f"R{slot.weapon_refinement}",
                  *(str(n) for n in slot.set_counts[:2]))
        for i, path in enumerate(paths):
            sx = x+face+14+(i%self.layout.equipment_columns)*(size+4)
            sy = y+28+(i//self.layout.equipment_columns)*(size+4)
            self.icon(path, sx, sy, size)
            if i < len(labels):
                lw = self.measure(labels[i], 12)+7
                self.rounded(QRectF(sx+size-lw, sy+size-17, lw, 17), tint(UI_HISTORY_BG_BOTTOM, 230), radius=3)
                self.text(sx+size-lw, sy+size-20, lw, labels[i], 12, bold=True,
                          align=Qt.AlignmentFlag.AlignCenter)
        build_y = y+self.layout.character_header(team)-22
        level_width = self.measure(level, 11)+4
        self.text(x+8, build_y, w-level_width-24, slot.stat_badge or "—", 12)
        self.text(x+w-level_width-8, build_y+1, level_width, level, 11,
                  UI_HISTORY_MUTED, align=Qt.AlignmentFlag.AlignRight)
        if expanded:
            self.character_stats(slot, rect, team)
        self.hits.append((rect, slot))

    def character_stats(self, slot, rect, team):
        x, y, w = rect.x(), rect.y(), rect.width()
        sy = y+self.layout.character_header(team)
        height = self.layout.stats_height(team)-5
        self.rounded(QRectF(x+3, sy, w-6, height), tint(UI_HISTORY_BG_BOTTOM, 110), radius=4)
        self.line(x+4, sy, x+w-4, sy, UI_HISTORY_GRID, 115)
        row_count = max(4, ceil((height-3)/22))
        for row_index in range(row_count):
            ry = sy+row_index*22
            if row_index % 2 == 0:
                self.p.fillRect(QRectF(x+4, ry+1, w-8, 21), tint(UI_HISTORY_TEXT, 9))
            if row_index:
                self.p.fillRect(QRectF(x+4, ry, w-8, 1), tint(UI_HISTORY_GRID, 38))
        halves = stat_columns(slot)
        half = (w-20)/2
        self.line(x+w/2, sy+2, x+w/2, sy+height-4, UI_HISTORY_GRID, 65)
        for col, rows in enumerate(halves):
            for i, row in enumerate(rows):
                if row is None:
                    continue
                sx = x+8+col*(half+4)
                ry = sy+2+i*22
                key = row.icon_label or row.key or row.label
                label_width = self.measure(key, 11)+1
                value = number(int(row.value)) if row.value.isdigit() else row.value
                self.text(sx, ry+2, label_width, key, 11, UI_HISTORY_MUTED)
                self.text(sx+label_width+3, ry, half-label_width-5, value, 14,
                          UI_HISTORY_TEXT, False, Qt.AlignmentFlag.AlignRight)

    def metrics(self, x, y, width, factual, simulated, *, stacked=False):
        half = width/2
        for i, (label, value, color) in enumerate((
            (tr("history.card.fact_short"), factual, UI_HISTORY_FACT),
            (tr("history.card.sim_short"), simulated, UI_HISTORY_SIM),
        )):
            sx, sy = x+(0 if stacked else i*half), y+(i*21 if stacked else 0)
            available = width if stacked else half-6
            label_width = self.measure(label, 12)+6
            self.text(sx, sy+1, label_width, label, 12, UI_HISTORY_MUTED)
            self.text(sx+label_width, sy, available-label_width, number(value), 14, color)
        if not stacked:
            self.separator(x+half-5, y+3, 17, vertical=True, alpha=80)

    def dummy(self, run, rect):
        self.text(rect.x()+10, rect.y()+4, rect.width()-20,
                  run.target_label or tr("app_shell.history.dps.target_unavailable"), 14, bold=True)
        self.text(rect.x()+10, rect.y()+28, rect.width()-20,
                  run.target_setup or tr("app_shell.history.dps.setup_unavailable"), 12, UI_HISTORY_MUTED)
        self.metrics(rect.x()+10, rect.y()+53, rect.width()-20, run.factual_dps, run.sim_dps)

    def rooms(self, run, team, y, expanded, accent):
        height = self.layout.room_height(run, team, expanded)
        gradient = QLinearGradient(0, y, 0, y+height)
        gradient.setColorAt(0, tint(accent, 17))
        gradient.setColorAt(1, tint(accent, 3))
        self.rounded(QRectF(self.layout.body_x, y, self.layout.body_width, height), gradient, radius=6)
        if run.run_type != "abyss":
            self.dummy(run, QRectF(self.layout.body_x, y, self.layout.body_width, height))
            return
        cw = self.layout.room_width
        for c in (1, 2, 3):
            x = self.layout.body_x+(c-1)*cw
            self.rounded(QRectF(x, y+3, cw-6, height-6), tint(UI_HISTORY_BG_BOTTOM, 125),
                         tint(accent, 110), 5)
            duration, factual, simulated = chamber_values(run, team, c)
            beside = expanded and self.layout.room_inline_enemies
            self.text(x+7, y+7, 36, f"{run.floor or '—'}-{c}", 12, bold=True)
            self.rounded(QRectF(x+39, y+7, 63, 25), tint(accent, 26), radius=4)
            self.text(x+40, y+5, 61, seconds(duration), 18, accent, True,
                      align=Qt.AlignmentFlag.AlignCenter)
            self.metrics(x+7, y+33, 98 if beside else cw-18, factual, simulated,
                         stacked=beside or self.layout.stacked_metrics)
            if beside:
                self.line(x+105, y+12, x+105, y+height-12, UI_HISTORY_GRID, 65)
            if expanded:
                base_y = y+5 if beside else y+(86 if self.layout.stacked_metrics else 64)
                enemies = room_enemies(run, team, c)
                for i, enemy in enumerate(enemies):
                    size = self.layout.enemy_size
                    ex = x+(108 if beside else 7)+(i%self.layout.enemy_capacity())*self.layout.enemy_step
                    ey = base_y+(i//self.layout.enemy_capacity())*self.layout.enemy_step
                    self.icon(enemy.icon_path, ex, ey, size, enemy.name[:2])
                    if enemy.count > 1:
                        self.rounded(QRectF(ex+size-25, ey+size-14, 25, 15), tint(UI_HISTORY_BG_BOTTOM, 245), radius=3)
                        self.text(ex+size-25, ey+size-17, 25, f"×{enemy.count}", 12,
                                  UI_HISTORY_TEXT, True, Qt.AlignmentFlag.AlignCenter)
                    tooltip = tr("app_shell.history.enemy.tooltip").format(name=enemy.name or "—",
                        level=enemy.level or "—", count=enemy.count, wave=enemy.wave, hp=number(enemy.hp))
                    self.hits.append((QRectF(ex, ey, size+2, size+4), tooltip))
                if not enemies:
                    self.hits.append((QRectF(x, y, cw, height), tr("history.card.enemies_unavailable")))

    def card(self, run, expanded):
        w = self.layout.width
        height = self.layout.height(run, expanded)
        background = QLinearGradient(0, 0, w, height)
        alternate = self.alternate and not expanded
        background.setColorAt(0, QColor(UI_HISTORY_ALT_TOP if alternate else UI_HISTORY_BG_TOP))
        background.setColorAt(.55, QColor(UI_HISTORY_ALT_TOP if alternate else UI_BG_PANEL_RAISED))
        background.setColorAt(1, QColor(UI_HISTORY_ALT_BOTTOM if alternate else UI_HISTORY_BG_BOTTOM))
        border_alpha = 75 if expanded else (155 if alternate else 95)
        self.rounded(QRectF(1, 1, w-2, height-2), background, tint(UI_HISTORY_GRID, border_alpha), 9)
        if not expanded:
            self.compact_teams(run)
            return
        self.header(run)
        y = self.layout.header
        for index, team in enumerate(visible_teams(run)):
            accent = UI_HISTORY_TEAM_1 if index == 0 else UI_HISTORY_TEAM_2
            self.rounded(QRectF(7, y, w-14, self.layout.team_height(run, team, expanded)),
                         tint(UI_HISTORY_BG_BOTTOM, 60), tint(accent, 155), 7)
            member_y = y+self.layout.team_header
            row_height = self.layout.member_row_height(team, expanded)
            for i, slot in enumerate(team_slots(team)):
                col, row = i%self.layout.expanded_columns, i//self.layout.expanded_columns
                x = self.layout.body_x+col*self.layout.column_width
                cy = member_y+row*(row_height+8)
                self.character(slot, QRectF(x, cy, self.layout.column_width, row_height), expanded, accent, team)
            room_y = member_y+ceil(4/self.layout.expanded_columns)*row_height+(ceil(4/self.layout.expanded_columns)-1)*8
            self.team_identity(run, team, y, room_y, accent)
            self.rooms(run, team, room_y, expanded, accent)
            y += self.layout.team_height(run, team, expanded)+10

    def compact(self, run, y=0):
        self.card(run, False)

    def expanded(self, run, y=0):
        self.card(run, True)


class CharacterTooltip(QWidget):
    """Static, non-activating in-app popup anchored in global screen coordinates."""
    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.slot = None
        self.images = {}
        self.character_view = "profile"

    def show_slot(self, slot, images, character_view, owner, anchor):
        self.slot, self.images, self.character_view = slot, images, character_view
        height = 147 + len(stat_rows(slot))*27 + len(slot.set_labels)*29
        self._content_scale = max(1., 1./owner.devicePixelRatioF())
        self.setFixedSize(ceil(370*self._content_scale), ceil(height*self._content_scale))
        rect, screen = anchored_tooltip_rect(owner, anchor, self.size())
        self.setScreen(screen)
        self.setFixedSize(rect.size())
        self.move(rect.topLeft())
        self.show()
        self.update()

    def paintEvent(self, event):
        if self.slot is None:
            return
        painter = QPainter(self)
        accent = UI_ELEMENT_ACCENTS.get(self.slot.element.casefold(), UI_HISTORY_TEAM_1)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(UI_BG_PANEL_RAISED))
        dark = QColor(accent).darker(400)
        gradient.setColorAt(1, dark)
        painter.fillRect(self.rect(), gradient)
        painter.setPen(QColor(accent))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.scale(self._content_scale, self._content_scale)
        draw = CardPainter(painter, self.images, self.character_view)
        draw.portrait(self.slot, 13, 12, 48)
        draw.text(73, 13, 280, self.slot.character_name, 18, bold=True)
        draw.text(73, 39, 280, tr("history.card.level").format(value=self.slot.character_level or "—")+
                  (f" · C{self.slot.constellation}" if self.slot.constellation is not None else ""), 13, accent)
        draw.icon(self.slot.weapon_icon_path, 16, 70, 36)
        draw.text(66, 69, 289, self.slot.weapon_name or "—", 14, bold=True)
        draw.text(66, 91, 289, tr("history.card.level").format(value=self.slot.weapon_level or "—")+
                  (f" · R{self.slot.weapon_refinement}" if self.slot.weapon_refinement is not None else ""), 12, UI_TEXT_MUTED)
        draw.line(16, 119, 354, 119)
        y = 128
        for row in stat_rows(self.slot):
            draw.text(18, y, 233, row.label or row.icon_label, 14)
            draw.text(256, y, 96, row.value, 15, bold=True, align=Qt.AlignmentFlag.AlignRight)
            y += 27
        for i, label in enumerate(self.slot.set_labels):
            draw.icon(self.slot.set_icon_paths[i] if i < len(self.slot.set_icon_paths) else "", 17, y, 25)
            draw.text(49, y+2, 304, label, 13, accent)
            y += 29
        painter.end()


class HistoryCardWidget(QWidget):
    clicked = Signal()
    artwork_requested = Signal(int)
    artwork_reset_requested = Signal(int)

    def __init__(self, run: HistoryRunVisual, parent=None, *, character_view="profile", alternate=False,
                 artwork_paths=None):
        super().__init__(parent)
        self.run = run
        self.character_view = character_view
        self.alternate = bool(alternate)
        self.artwork_paths = dict(artwork_paths or {})
        self.expanded = False
        self._hits = []
        self._hover = None
        self._anchor = QPoint()
        self._images = {}
        self._image_dpr = 0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(tr("history.card.record").format(date=run.created_at[:16].replace("T", " ")))
        self._character_popup = CharacterTooltip(self)
        self._text_popup = CustomTooltipPopup(self)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_hover)
        self._sync_size()

    def sizeHint(self):
        return QSize(CARD_WIDTH, self.design_height())

    @property
    def content_scale(self):
        # Compensate startup downscale locally: 14px values must not become 10px.
        # AppShell's global scaling and the right-panel footprint are unchanged.
        return max(1., 1./self.devicePixelRatioF())

    def design_height(self):
        scale = self.content_scale
        return ceil(CardLayout(max(1, self.width()/scale)).height(self.run, self.expanded)*scale)

    def set_expanded(self, value):
        self.expanded = bool(value)
        self._hide_hover()
        self._sync_size()
        self.update()

    def set_character_view(self, value):
        self.character_view = value
        self._hide_hover()
        self.update()

    def set_artwork_paths(self, paths):
        self.artwork_paths = dict(paths)
        self._hide_hover()
        self._image_dpr = 0
        self._sync_size()
        self.update()

    def _sync_size(self):
        self.setFixedHeight(self.design_height())
        dpr = max(1., self.devicePixelRatioF())
        if abs(dpr-self._image_dpr) > .01:
            self._images = prepare_images(self.run, dpr, self.artwork_paths)
            self._image_dpr = dpr

    def resizeEvent(self, event):
        self._hide_hover()
        self._sync_size()
        super().resizeEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, "run"):
            self._sync_size()
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, "_hover_timer"):
            self._hide_hover()
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        scale = self.content_scale
        painter.scale(scale, scale)
        draw = CardPainter(painter, self._images, self.character_view,
                           width=self.width()/scale, hovered=self._hover, alternate=self.alternate,
                           artwork_paths=self.artwork_paths, interactive=True)
        draw.card(self.run, self.expanded)
        self._hits = [(QRectF(r.x()*scale, r.y()*scale, r.width()*scale, r.height()*scale), value)
                      for r, value in draw.hits]
        painter.end()

    def mouseMoveEvent(self, event):
        point = event.position()
        payload = next((value for rect, value in self._hits if rect.contains(point)), None)
        if payload != self._hover:
            self._hide_hover()
            self._hover = payload
            self._anchor = event.position().toPoint()
            if payload:
                self._hover_timer.start(CUSTOM_TOOLTIP_DELAY_MS)
            self.update()
        super().mouseMoveEvent(event)

    def _show_hover(self):
        if not self.isVisible():
            return
        if isinstance(self._hover, HistorySlotVisual) and self._hover.character_name:
            self._character_popup.show_slot(self._hover, self._images, self.character_view, self, self._anchor)
        elif isinstance(self._hover, str):
            self._text_popup.show_for(self, self._hover, anchor=self._anchor)

    def _hide_hover(self):
        self._hover_timer.stop()
        self._character_popup.hide()
        self._text_popup.hide()
        self._hover = None

    def dismiss_tooltip(self):
        self._hide_hover()

    def wheelEvent(self, event):
        self._hide_hover()
        super().wheelEvent(event)

    def leaveEvent(self, event):
        self._hide_hover()
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._hide_hover()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            action = next((value for rect, value in self._hits if rect.contains(event.position())), None)
            self._hide_hover()
            if isinstance(action, ArtworkAction):
                signal = self.artwork_reset_requested if action.reset else self.artwork_requested
                signal.emit(action.team_index)
            else:
                self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


def render_history_card_png(run, destination: str | Path, *, character_view="profile", width=1600,
                            artwork_paths=None):
    """Render only the expanded composition, independent of widget selection/size."""
    scale = width/CARD_WIDTH
    image = QImage(width, ceil(detail_height(run)*scale), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(UI_BG_APP))
    painter = QPainter(image)
    try:
        painter.scale(scale, scale)
        CardPainter(painter, prepare_images(run, scale, artwork_paths), character_view,
                    artwork_paths=artwork_paths).expanded(run)
    finally:
        painter.end()
    if not image.save(str(destination), "PNG"):
        raise OSError(f"Could not write PNG: {destination}")
    return image.size()
