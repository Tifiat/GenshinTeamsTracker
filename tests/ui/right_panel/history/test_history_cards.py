from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from run_workspace.history_artwork import HistoryArtworkStore
from run_workspace.history_snapshot import HistoryArtifactSlotSnapshot, HistoryStatRowSnapshot, HistorySnapshotBundleStore
from run_workspace.history_browser_catalog import _run_visual, HistoryEnemyVisual, HistorySideVisual
from run_workspace.history_snapshot_right_panel import build_history_snapshot_right_panel_view_model
from tests.run_workspace.history.test_history_snapshot_right_panel import _bundle
from ui.history_browser.window import HistoryBrowserWorkspace
from ui.right_panel.common.history_card import ArtworkAction, CardLayout, HistoryCardWidget, render_history_card_png, stat_columns, team_seconds


class HistoryCardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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
        # User rejected the 510px compact report: a whole run should occupy
        # roughly four 40px Akasha rows; a wide panel fits results alongside.
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        card = HistoryCardWidget(visual)
        scale = card.content_scale
        card.resize(round(864*scale), 1)
        card.set_expanded(False)
        self.assertLessEqual(card.height()/scale, 180)
        card.grab()
        regions = [r for r, slot in card._hits if hasattr(slot, "character_name")]
        self.assertEqual(len(regions), 8)
        self.assertTrue(all(r.height()/scale >= 42 for r in regions))
        card.resize(round(1220*scale), 1)
        card.set_expanded(False)  # Hidden widgets defer resize events until shown.
        self.assertLessEqual(card.height()/scale, 140)
        card.grab()
        self.assertEqual(sum(hasattr(s, "character_name") for _, s in card._hits), 8)
        card.set_expanded(True)
        self.assertGreater(card.height()/scale, 180)
        card.close()
        card.deleteLater()
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
