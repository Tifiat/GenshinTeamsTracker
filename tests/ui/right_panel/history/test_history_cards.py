from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from run_workspace.history_artwork import HistoryArtworkStore
from run_workspace.history_snapshot import HistoryArtifactSlotSnapshot, HistoryStatRowSnapshot, HistorySnapshotBundleStore
from run_workspace.history_browser_catalog import (
    _run_visual,
    HistoryBonusVisual,
    HistoryEnemyVisual,
    HistoryPeriodVisual,
    HistoryRunVisual,
    HistorySlotVisual,
    HistorySideVisual,
)
from run_workspace.history_snapshot_right_panel import build_history_snapshot_right_panel_view_model
from tests.run_workspace.history.test_history_snapshot_right_panel import _bundle
from ui.history_browser.window import AbyssPeriodSectionWidget, HistoryBrowserWorkspace
from ui.right_panel.common.history_card import (
    ArtworkAction,
    CardLayout,
    HistoryCardWidget,
    compact_seconds,
    render_history_card_png,
    stat_columns,
    prepare_images,
    team_seconds,
)


class HistoryCardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_team_art_uses_frozen_unbadged_layer_and_custom_art_still_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy, raw, custom = (root / name for name in ("badged.png", "raw.png", "custom.png"))
            for path, color in ((legacy, Qt.GlobalColor.red), (raw, Qt.GlobalColor.blue), (custom, Qt.GlobalColor.green)):
                picture = QImage(24, 24, QImage.Format.Format_ARGB32)
                picture.fill(color)
                picture.save(str(path))
            visual = _run_visual(_bundle(), root / "snapshot.json")
            team = visual.teams[0]
            slot = replace(team.slots[1], portrait_path=str(legacy), expanded_portrait_path=str(raw))
            visual = replace(visual, teams=(replace(team, slots=(slot,)),))
            self.assertEqual(prepare_images(visual, 1)[("artwork", team.team_index)].toImage().pixelColor(0, 0).name(), "#0000ff")
            self.assertEqual(prepare_images(visual, 1, {team.team_index: custom})[("artwork", team.team_index)].toImage().pixelColor(0, 0).name(), "#00ff00")

    def test_larger_expanded_weapon_and_two_sets_fit_each_character_header(self):
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        team = replace(visual.teams[0], slots=(HistorySlotVisual(slot_index=0, character_name="Hero",
                      weapon_icon_path="weapon", set_icon_paths=("set-a", "set-b")),))
        for width in (520, 704, 960, 1600):
            layout = CardLayout(width)
            tiles = layout.equipment_tiles(2)
            self.assertGreater(tiles[0][2], tiles[1][2])
            for dx, dy, size in tiles:
                self.assertGreaterEqual(dx, 0)
                self.assertLessEqual(layout.portrait_size+14+dx+size, layout.column_width-8)
                self.assertLessEqual(28+dy+size, layout.character_header(team)-24)
            for left, right in zip(tiles, tiles[1:]):
                self.assertTrue(right[1] >= left[1]+left[2] or right[0] >= left[0]+left[2])

    def test_visible_portrait_and_weapon_bottoms_align_in_both_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            portrait, weapon = root / "wide-portrait.png", root / "tall-weapon.png"
            for path, width, height, color in ((portrait, 30, 15, Qt.GlobalColor.red),
                                              (weapon, 12, 30, Qt.GlobalColor.green)):
                picture = QImage(width, height, QImage.Format.Format_ARGB32)
                picture.fill(color)
                picture.save(str(path))
            visual = _run_visual(_bundle(), root / "snapshot.json")
            slot = HistorySlotVisual(slot_index=0, character_name="Hero", portrait_path=str(portrait),
                                     expanded_portrait_path=str(portrait), weapon_icon_path=str(weapon))
            visual = replace(visual, teams=(replace(visual.teams[0], slots=(slot,)),))
            for expanded in (False, True):
                card = HistoryCardWidget(visual)
                card.resize(960, 1)
                card.set_expanded(expanded)
                picture = card.grab().toImage()
                region = next(rect for rect, value in card._hits if value is slot).toAlignedRect()
                if expanded:
                    region.setHeight(CardLayout(960).character_header(visual.teams[0]))
                pixels = {color: [] for color in ("#ff0000", "#00ff00")}
                for y in range(region.top(), region.bottom()+1):
                    for x in range(region.left(), region.right()+1):
                        color = picture.pixelColor(x, y).name()
                        if color in pixels:
                            pixels[color].append(y)
                self.assertTrue(all(pixels.values()))
                self.assertLessEqual(abs(max(pixels["#ff0000"])-max(pixels["#00ff00"])), 1)
                if not expanded:
                    self.assertGreaterEqual(max(pixels["#00ff00"])-min(pixels["#00ff00"]), 30)
                card.close()
                card.deleteLater()
            self.app.processEvents()

    def test_saved_badges_use_live_property_ids_and_only_obsolete_warnings_are_hidden(self):
        bundle = _bundle()
        slot = bundle.teams[0].slots[1]
        build = replace(slot.artifact_build, artifact_slots=(
            HistoryArtifactSlotSnapshot(position=3, main_stat=HistoryStatRowSnapshot("Сила атаки", "46.6%", key="6")),
            HistoryArtifactSlotSnapshot(position=4, main_stat=HistoryStatRowSnapshot("Бонус Пиро урона", "46.6%", key="40")),
        ), warnings=("set_bonus_formulas_not_included", "conditional_set_bonuses_not_included", "asset_missing"))
        slot = replace(slot, artifact_build=build, warnings=build.warnings)
        bundle = replace(bundle, teams=(replace(bundle.teams[0], slots=(bundle.teams[0].slots[0], slot)), bundle.teams[1]))
        before = bundle.to_dict()
        model = build_history_snapshot_right_panel_view_model(bundle, bundle_dir=Path("unused"))
        visual = _run_visual(bundle, Path("unused/snapshot.json"))
        self.assertEqual(model.teams[0].slots[1].stat_badge, "ATK%/PYRO")
        self.assertEqual(visual.teams[0].slots[1].stat_badge, "ATK%/PYRO")
        self.assertEqual(model.teams[0].slots[1].warning_count, 1)
        self.assertEqual(model.teams[0].slots[1].warning_tooltip, "asset_missing")
        self.assertEqual(bundle.to_dict(), before)

    def test_click_expands_and_selects_same_snapshot_repeat_collapses_only_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = replace(_bundle(), bundle_id="card-first")
            second = replace(_bundle(), bundle_id="card-second")
            store = HistorySnapshotBundleStore(root)
            store.write_bundle_grouped(first)
            store.write_bundle_grouped(second)
            workspace = HistoryBrowserWorkspace(snapshot_root=root, abyss_cache_dir=root/"none")
            workspace.resize(1120, 800)
            workspace.show()
            self.app.processEvents()
            seen = []
            workspace.snapshot_selected.connect(seen.append)
            row = workspace.row_widget(first.bundle_id)
            QTest.mouseClick(row.card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
            self.app.processEvents()
            self.assertTrue(row.card.expanded)
            self.assertEqual(workspace.selected_bundle_id(), first.bundle_id)
            self.assertIsNotNone(seen[-1])
            QTest.mouseClick(row.card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
            self.assertFalse(row.card.expanded)
            self.assertEqual(workspace.selected_bundle_id(), first.bundle_id)
            self.assertIsNotNone(seen[-1])
            row.click()
            workspace.row_widget(second.bundle_id).click()
            self.assertFalse(row.card.expanded)
            self.assertTrue(workspace.row_widget(second.bundle_id).card.expanded)
            identity = id(workspace.row_widget(second.bundle_id))
            workspace.reload_data()
            self.assertEqual(id(workspace.row_widget(second.bundle_id)), identity)
            self.assertEqual(workspace.row_widget(second.bundle_id).card.character_view, "profile")
            workspace._clear_selection()
            workspace.close()
            workspace.deleteLater()
            self.app.processEvents()

    def test_scrolled_enemy_tooltip_follows_visible_hover_and_stays_on_screen(self):
        card = HistoryCardWidget(_run_visual(_bundle(), Path("unavailable/snapshot.json")))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(card)
        area.resize(850, 300)
        card.set_expanded(True)
        area.show()
        self.app.processEvents()
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        self.app.processEvents()
        point = area.viewport().mapToGlobal(QPoint(70, area.viewport().height()-20))
        card._anchor = card.mapFromGlobal(point)
        card._hover = "Enemy\nLevel 100\nHP 2000000"
        card._show_hover()
        self.app.processEvents()
        popup = card._text_popup
        self.assertTrue(popup.isVisible())
        bounds = popup.screen().availableGeometry()
        self.assertTrue(bounds.contains(popup.frameGeometry()))
        self.assertLessEqual(abs(popup.frameGeometry().top()-point.y()), popup.height()+20)
        # Character popups use the same global-coordinate placement boundary.
        card._hover = next(s for t in card.run.teams for s in t.slots if s.character_name)
        card._show_hover()
        self.app.processEvents()
        self.assertTrue(bounds.contains(card._character_popup.frameGeometry()))
        area.close()
        area.deleteLater()
        self.app.processEvents()

    def test_scrolling_dismisses_character_popup_and_pending_hover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _bundle()
            HistorySnapshotBundleStore(root).write_bundle_grouped(bundle)
            workspace = HistoryBrowserWorkspace(snapshot_root=root, abyss_cache_dir=root/"none")
            workspace.resize(1120, 400)
            workspace.show()
            workspace.row_widget(bundle.bundle_id).click()
            self.app.processEvents()
            card = workspace.row_widget(bundle.bundle_id).card
            card._hover = next(slot for team in card.run.teams for slot in team.slots if slot.character_name)
            card._show_hover()
            self.assertTrue(card._character_popup.isVisible())
            card._hover_timer.start(1000)
            bar = workspace.scroll_area.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())
            self.assertFalse(card._character_popup.isVisible())
            self.assertFalse(card._hover_timer.isActive())
            self.assertIsNone(card._hover)
            workspace.close()
            workspace.deleteLater()
            self.app.processEvents()

    def test_png_uses_frozen_data_and_unavailable_time_is_not_zero(self):
        bundle = _bundle()
        visual = _run_visual(bundle, Path("unavailable/snapshot.json"))
        before = bundle.to_dict()
        self.assertIsNone(team_seconds(visual, visual.teams[0]))  # only one saved chamber
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"run.png"
            size = render_history_card_png(visual, path, character_view="portrait")
            image = QImage(str(path))
            self.assertFalse(image.isNull())
            self.assertEqual(image.size(), size)
            self.assertEqual(size.width(), 1600)
        self.assertEqual(bundle.to_dict(), before)

    def test_missing_stat_does_not_shift_crit_into_hp_attack_column(self):
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        slot = visual.teams[0].slots[1]
        left, right = stat_columns(slot)
        self.assertTrue(all(row is None for row in left))
        self.assertEqual(right[0].value, "70%")

    def test_compact_run_fits_about_four_reference_rows_without_duplicate_characters(self):
        # A 1366/RDP-sized viewport removes chamber timing detail instead of
        # adding a full-width results row beneath each team.
        scale_patch = patch.object(HistoryCardWidget, "content_scale", new_callable=PropertyMock, return_value=1.)
        scale_patch.start()
        self.addCleanup(scale_patch.stop)
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        card = HistoryCardWidget(visual)
        card.resize(864, 1)
        card.set_expanded(False)
        scale = card.content_scale
        self.assertEqual(scale, 1.)
        self.assertEqual(card.height(), 84)
        card.grab()
        regions = [r for r, slot in card._hits if hasattr(slot, "character_name")]
        self.assertEqual(len(regions), 8)
        self.assertTrue(all(r.height() == 36 for r in regions))
        self.assertEqual({round(r.y()) for r in regions}, {3, 44})
        self.assertLessEqual(min(r.x() for r in regions), 2)
        card.resize(1220, 1)
        card.set_expanded(False)  # Hidden widgets defer resize events until shown.
        self.assertEqual(card.content_scale, 1.)
        self.assertEqual(card.height(), 84)
        card.grab()
        self.assertEqual(sum(hasattr(s, "character_name") for _, s in card._hits), 8)
        # A 2K desktop at 150% commonly leaves about 1000 logical pixels for
        # this pane. It must retain inline team/chamber timing without growing
        # beyond the narrow card's height budget.
        card.resize(1000, 1)
        card.set_expanded(False)
        self.assertTrue(CardLayout(1000).compact_inline(visual))
        self.assertEqual(card.height(), 84)
        card.grab()
        self.assertEqual(sum(hasattr(s, "character_name") for _, s in card._hits), 8)
        card.set_expanded(True)
        self.assertGreater(card.height(), 180)
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_compact_two_set_run_reserves_only_build_height_without_results_rows(self):
        scale_patch = patch.object(HistoryCardWidget, "content_scale", new_callable=PropertyMock, return_value=1.)
        scale_patch.start()
        self.addCleanup(scale_patch.stop)
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        first = visual.teams[0]
        slot = replace(first.slots[0], set_icon_paths=("first", "second"), set_counts=(2, 2))
        visual = replace(visual, teams=(replace(first, slots=(slot, *first.slots[1:])), visual.teams[1]))
        self.assertTrue(CardLayout(1000).compact_inline(visual))
        self.assertEqual(CardLayout(1000).height(visual, False), 84)
        card = HistoryCardWidget(visual)
        card.resize(1000, 1)
        card.set_expanded(False)
        card.grab()
        self.assertEqual(card.height(), 84)
        self.assertTrue(all(card.rect().contains(rect.toAlignedRect()) for rect, _ in card._hits))
        card.resize(864, 1)
        card.set_expanded(False)
        self.assertEqual(card.content_scale, 1.)
        self.assertEqual(card.height(), 84)
        card.grab()
        self.assertEqual(sum(hasattr(value, "character_name") for _, value in card._hits), 8)
        self.assertTrue(all(card.rect().contains(rect.toAlignedRect()) for rect, _ in card._hits))
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_narrow_compact_separates_resonances_and_hides_roman_marker_first(self):
        scale_patch = patch.object(HistoryCardWidget, "content_scale", new_callable=PropertyMock, return_value=1.)
        scale_patch.start()
        self.addCleanup(scale_patch.stop)
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        first = visual.teams[0]
        bonuses = tuple(
            HistoryBonusVisual(
                identity=f"bonus-{index}",
                label=str(index),
                tooltip=f"unique bonus {index}",
            )
            for index in range(5)
        )
        visual = replace(
            visual,
            teams=(replace(first, bonuses=bonuses), visual.teams[1]),
        )
        layout = CardLayout(864)
        self.assertEqual(layout.compact_total_width, 86)
        self.assertEqual(layout.compact_team_index_width, 0)
        self.assertEqual(layout.compact_resonance_width(visual), 28)
        self.assertTrue(CardLayout(960).compact_inline(visual))
        self.assertEqual(CardLayout(960).compact_team_index_width, 0)
        self.assertEqual(CardLayout(1000).compact_team_index_width, 14)
        self.assertEqual(CardLayout(1000).compact_resonance_width(visual), 0)
        self.assertEqual(CardLayout(540).compact_team_index_width, 0)
        self.assertEqual(CardLayout(540).compact_resonance_width(visual), 0)
        self.assertEqual(CardLayout(320).compact_team_index_width, 0)
        self.assertNotIn(" ", compact_seconds(444))

        card = HistoryCardWidget(visual)
        card.resize(864, 1)
        card.set_expanded(False)
        card.grab()
        visible_bonus_hits = [
            (rect, value)
            for rect, value in card._hits
            if isinstance(value, str) and value.startswith("unique bonus")
        ]
        self.assertEqual(
            {value for _, value in visible_bonus_hits},
            {"unique bonus 0", "unique bonus 1"},
        )
        visible_bonus_hits.sort(key=lambda item: item[1])
        first_rect, _ = visible_bonus_hits[0]
        second_rect, _ = visible_bonus_hits[1]
        self.assertAlmostEqual(first_rect.x(), second_rect.x())
        self.assertGreater(second_rect.y(), first_rect.y())
        self.assertTrue(
            all(rect.right() < layout.compact_body_width for rect, _ in visible_bonus_hits)
        )
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_compact_responsive_geometry_keeps_team_rows_stable_and_in_bounds(self):
        scale_patch = patch.object(HistoryCardWidget, "content_scale", new_callable=PropertyMock, return_value=1.)
        scale_patch.start()
        self.addCleanup(scale_patch.stop)
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        for width, expected_height, expected_rows in (
            (520, 156, 4),
            (560, 84, 2),
            (704, 84, 2),
            (960, 84, 2),
            (980, 84, 2),
        ):
            with self.subTest(width=width):
                card = HistoryCardWidget(visual)
                card.resize(width, 1)
                card.set_expanded(False)
                card.grab()
                regions = [
                    rect
                    for rect, value in card._hits
                    if hasattr(value, "character_name")
                ]
                layout = CardLayout(width)
                self.assertEqual(card.height(), expected_height)
                self.assertEqual(len(regions), 8)
                self.assertEqual(len({round(rect.y()) for rect in regions}), expected_rows)
                self.assertTrue(all(card.rect().contains(rect.toAlignedRect()) for rect in regions))
                expected_left = layout.compact_inner_margin + layout.compact_team_index_width
                self.assertAlmostEqual(min(rect.x() for rect in regions), expected_left)
                self.assertLessEqual(
                    max(rect.right() for rect in regions),
                    layout.compact_body_width-layout.compact_inner_margin,
                )
                for row_y in {round(rect.y()) for rect in regions}:
                    row = sorted((rect for rect in regions if round(rect.y()) == row_y), key=lambda rect: rect.x())
                    self.assertTrue(all(right.left() >= left.right() for left, right in zip(row, row[1:])))
                card.close()
                card.deleteLater()
        self.app.processEvents()

    def test_expanded_bonus_grid_stays_inside_identity_panel(self):
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        first = visual.teams[0]
        bonuses = tuple(
            HistoryBonusVisual(
                identity=f"expanded-bonus-{index}",
                label=str(index),
                tooltip=f"expanded bonus {index}",
            )
            for index in range(11)
        )
        visual = replace(visual, teams=(replace(first, bonuses=bonuses), visual.teams[1]))
        card = HistoryCardWidget(visual)
        card.resize(1220, 1)
        card.set_expanded(True)
        card.grab()
        bonus_hits = [
            (rect, value)
            for rect, value in card._hits
            if isinstance(value, str) and value.startswith("expanded bonus")
        ]
        self.assertEqual(len(bonus_hits), 10)  # Nine icons plus one in-bounds overflow cell.
        self.assertEqual(len({round(rect.y()) for rect, _ in bonus_hits}), 2)
        self.assertTrue(all(rect.left() >= 20 and rect.right() <= 183 for rect, _ in bonus_hits))
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_period_heading_is_one_row_and_bosses_take_no_height_until_requested(self):
        run = HistoryRunVisual(
            bundle_id="period-run",
            run_type="abyss",
            created_at="2026-09-17T00:00:00Z",
            bundle_path=Path("period-run/snapshot.json"),
        )
        period = HistoryPeriodVisual(
            period_start="2026-09-16",
            period_end="2026-10-01",
            floor=12,
            runs=(run,),
            sides=(
                HistorySideVisual(
                    chamber=1,
                    side=1,
                    total_hp=10_500_000,
                    enemies=(HistoryEnemyVisual(name="Boss"),),
                ),
            ),
        )
        empty_period = HistoryPeriodVisual(
            period_start="2026-09-01",
            period_end="2026-09-15",
            floor=12,
        )
        section = AbyssPeriodSectionWidget(period, (period, empty_period))
        section.resize(864, 1)
        section.show()
        self.app.processEvents()
        self.assertIn("12", section.selector.text())
        self.assertIn("9.2026", section.selector.text())
        self.assertIn("10.2026", section.selector.text())
        self.assertEqual(len(section.selector.menu().actions()), 1)
        self.assertGreaterEqual(section.selector.menu().minimumWidth(), 360)
        self.assertTrue(section.preview.isHidden())
        collapsed_height = section.height()
        section.boss_button.setChecked(True)
        self.app.processEvents()
        self.assertFalse(section.preview.isHidden())
        self.assertGreater(section.height(), collapsed_height)
        chamber_labels = section.findChildren(QLabel, "HistoryChamberIndex")
        enemy_icons = section.findChildren(QLabel, "HistoryEnemyIcon")
        hp_labels = section.findChildren(QLabel, "HistorySideHp")
        self.assertEqual([label.text() for label in chamber_labels], ["12-1", "12-2", "12-3"])
        self.assertEqual(len(enemy_icons), 1)
        self.assertEqual(enemy_icons[0].width(), 50)
        self.assertEqual(len(hp_labels), 6)
        self.assertEqual(hp_labels[0].text(), "10.5m")
        section.boss_button.setChecked(False)
        self.app.processEvents()
        self.assertTrue(section.preview.isHidden())
        section.close()
        section.deleteLater()
        self.app.processEvents()

    def test_expansion_replaces_compact_characters_and_hover_uses_viewport_coordinates(self):
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        card = HistoryCardWidget(visual)
        for dpr, width in ((1., 720), (1., 1220), (.711458, 1220), (.711458, 720)):
            with patch.object(card, "devicePixelRatioF", return_value=dpr):
                card.resize(width, 1)
                for expanded in (False, True):
                    card.set_expanded(expanded)
                    card.show()
                    self.app.processEvents()
                    card.grab()  # Populate actual painted hit regions at this width.
                    slots = [(rect, slot) for rect, slot in card._hits if hasattr(slot, "character_name")]
                    self.assertEqual(len(slots), 8)  # A second stacked report would duplicate them.
                    self.assertTrue(all(card.rect().contains(rect.toAlignedRect()) for rect, _ in slots))
                    rect, slot = next((r, s) for r, s in slots if s.character_name)
                    local = rect.center()
                    event = QMouseEvent(
                        QEvent.Type.MouseMove,
                        local,
                        QPointF(card.mapToGlobal(local.toPoint())),
                        Qt.MouseButton.NoButton,
                        Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier,
                    )
                    QApplication.sendEvent(card, event)
                    self.app.processEvents()
                    self.assertEqual(card._hover, slot)
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_two_sets_and_wrapped_enemies_reserve_space_without_leaving_card(self):
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        first = visual.teams[0]
        slot = replace(first.slots[0], set_icon_paths=("missing-first", "missing-second"),
                       set_counts=(2, 2), stat_badge="ATK%/ELECTRO")
        visual = replace(visual, teams=(replace(first, slots=(slot, *first.slots[1:])), visual.teams[1]),
                         sides=(HistorySideVisual(chamber=1, side=1, enemies=tuple(
                             HistoryEnemyVisual(name=f"Enemy {i}") for i in range(14))),))
        layout = CardLayout(720)
        self.assertTrue(CardLayout(864).wraps_build(visual.teams[0]))
        self.assertGreater(layout.room_height(visual, visual.teams[0], True), 64+40)
        card = HistoryCardWidget(visual)
        card.resize(720, 1)
        card.set_expanded(True)
        card.grab()
        self.assertTrue(all(card.rect().contains(rect.toAlignedRect()) for rect, _ in card._hits))
        self.assertEqual(sum(isinstance(v, str) and "Enemy " in v for _, v in card._hits), 14)
        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_custom_artwork_is_per_record_and_survives_source_removal_without_mutating_snapshot(self):
        from ui.history_browser.window import HistoryRunRowWidget
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _bundle()
            path = HistorySnapshotBundleStore(root/"snapshots").write_bundle_grouped(bundle)
            before = path.read_bytes()
            visual = _run_visual(bundle, path)
            store = HistoryArtworkStore(root/"presentation")
            source = root/"source.png"
            img = QImage(100, 160, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.red)
            img.save(str(source))
            with patch("ui.history_browser.window.HistoryArtworkStore", return_value=store):
                row = HistoryRunRowWidget(visual)
                row.card.resize(1220, 1)
                row.set_expanded(True)
                row.card.grab()
                action_rect = next(r for r, value in row.card._hits if value == ArtworkAction(0))
                clicks = []
                row.card.clicked.connect(lambda: clicks.append(True))
                with patch("ui.history_browser.window.QFileDialog.getOpenFileName", return_value=(str(source), "")):
                    QTest.mouseClick(row.card, Qt.MouseButton.LeftButton, pos=action_rect.center().toPoint())
                self.assertFalse(clicks)
                self.assertTrue(row.card.expanded)
                self.assertIn(0, row.card.artwork_paths)
                source.unlink()
                reopened = HistoryRunRowWidget(visual)
                self.assertEqual(reopened.card.artwork_paths, row.card.artwork_paths)
                other = replace(visual, bundle_id="other-record")
                self.assertEqual(store.paths(other), {})
                self.assertNotIn(1, store.paths(visual))
                export = root/"custom.png"
                render_history_card_png(visual, export, artwork_paths=reopened.card.artwork_paths)
                self.assertFalse(QImage(str(export)).isNull())
                # Cancelling a replacement must retain the user's previous image.
                saved = store.path(visual, 0).read_bytes()
                with patch("ui.history_browser.window.QFileDialog.getOpenFileName", return_value=("", "")):
                    reopened._choose_artwork(0)
                self.assertEqual(store.path(visual, 0).read_bytes(), saved)
                reopened._reset_artwork(0)
                self.assertEqual(store.paths(visual), {})
                self.assertEqual(path.read_bytes(), before)
                row.close()
                reopened.close()
                row.deleteLater()
                reopened.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
