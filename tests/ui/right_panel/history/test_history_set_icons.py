"""Frozen History set artwork, checked as pixels rather than helper calls."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from run_workspace.history_browser_catalog import _run_visual
from run_workspace.history_snapshot import HistorySetBonusSnapshot, HistorySnapshotBundleStore
from run_workspace.history_snapshot_builder import build_history_snapshot_bundle
from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS, RightPanelBuildMiniSetViewModel, RightPanelDetailRowViewModel,
    RightPanelSelectedDetailsViewModel,
)
from run_workspace.session import RunSessionController
from tests.run_workspace.history.test_history_snapshot_builder import _context, _right_panel_model, _slot_vm, _teams_vm
from tests.run_workspace.history.test_history_snapshot_right_panel import _bundle
from ui.right_panel.common.history_card import CardLayout, CardPainter, HistoryCardWidget, render_history_card_png


def _color_bounds(image, color, region=None):
    region = region or image.rect()
    points = [(x, y) for y in range(region.top(), region.bottom()+1)
              for x in range(region.left(), region.right()+1)
              if image.pixelColor(x, y).name() == color]
    if not points:
        return None
    xs, ys = zip(*points)
    return QRect(min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1)


def _saved_supplied_set_run(root, counts, paths, *, supplied_via="summary"):
    """Exercise public build -> frozen asset copy -> store read -> visual adapter."""
    names = ("Emblem of Severed Fate", "Deepwood Memories")
    raw_sets = tuple({"set_uid": uid, "set_name": name, "piece_count": count,
                      "owned_count": count, "icon_path": path}
                     for uid, name, count, path in zip(("emblem", "deepwood"), names, counts, paths))
    details = {
        "account_character": {"id": "10000041", "name": "Mona", "level": 90, "element": "Hydro"},
        "account_weapon": {"id": "14402", "name": "The Widsith", "level": 90, "refinement": 5},
        "selected_build": {"build_name": "Saved pair"},
        "stat_snapshot": {"artifact": {"summary": {
            "active_set_bonuses": raw_sets if supplied_via == "summary" else (),
        }}},
    }
    session = RunSessionController.empty()
    session.team_state = session.team_state.set_character(0, 0, {"id": "10000041", "name": "Mona"}).attach_character_details_data(0, 0, details)
    slot_vm = replace(_slot_vm(0, 0, character_title="Mona"), build_label="Saved pair",
                      build_mini_sets=tuple(RightPanelBuildMiniSetViewModel(**item) for item in raw_sets)
                      if supplied_via == "mini_sets" else ())
    model = _right_panel_model(mode=MODE_ABYSS, teams=_teams_vm(overrides={(0, 0): slot_vm}),
                              selected_details=RightPanelSelectedDetailsViewModel(
                                  has_selection=True, team_index=0, slot_index=0,
                                  character_name="Mona", weapon_name="The Widsith",
                                  stat_rows=(RightPanelDetailRowViewModel("CR", "70%", icon_label="CR"),)))
    context = _context(bundle_id=f"physical-{counts[0]}-{counts[1]}-{supplied_via}", account={})
    bundle = build_history_snapshot_bundle(session.state, model, context)
    store = HistorySnapshotBundleStore(root / context.bundle_id)
    path = store.write_bundle_grouped(bundle, copy_assets=True, asset_source_roots=(root,))
    return _run_visual(store.read_bundle(bundle.bundle_id), path), store, path


class HistorySetIconsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gtt-history-set-icons-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources = []
        for name, color in (("first.png", Qt.GlobalColor.red), ("second.png", Qt.GlobalColor.blue)):
            path = self.root / name
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(color)
            self.assertTrue(image.save(str(path)))
            self.sources.append(path)
        self.source_bytes = tuple(path.read_bytes() for path in self.sources)
        self.bundle = _bundle()
        team = self.bundle.teams[0]
        slot = team.slots[1]
        bonuses = (
            HistorySetBonusSnapshot("emblem", "Emblem of Severed Fate", 2, icon_ref="first.png"),
            HistorySetBonusSnapshot("deepwood", "Deepwood Memories", 2, icon_ref="second.png"),
        )
        slot = replace(slot, artifact_build=replace(slot.artifact_build, active_set_bonuses=bonuses))
        self.bundle = replace(self.bundle, teams=(replace(team, slots=(slot,)),))
        self.before = self.bundle.to_dict()
        self.visual = _run_visual(self.bundle, self.root / "snapshot.json")
        self.scale_patch = patch.object(HistoryCardWidget, "content_scale", new_callable=PropertyMock, return_value=1.)
        self.scale_patch.start()
        self.addCleanup(self.scale_patch.stop)

    def _card_image(self, visual, expanded, width):
        card = HistoryCardWidget(visual)
        self.addCleanup(card.deleteLater)
        self.addCleanup(card.close)
        card.resize(width, 1)
        card.set_expanded(expanded)
        self.painted_text = []
        self.count_positions = []
        original = CardPainter.text
        def text(draw, x, y, w, value, *args, **kwargs):
            self.painted_text.append(str(value))
            if str(value) == "2":
                self.count_positions.append((x, y))
            return original(draw, x, y, w, value, *args, **kwargs)
        with patch.object(CardPainter, "text", text):
            image = card.grab().toImage()
        slot = visual.teams[0].slots[0]
        region = next(rect for rect, value in card._hits if value is slot).toAlignedRect()
        return image, region, card

    def _assert_diagonal_tile(self, image, region, maximum_size):
        first = _color_bounds(image, "#ff0000", region)
        second = _color_bounds(image, "#0000ff", region)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        tile = first.united(second)
        # Separate adjacent icons cannot satisfy the overlapping x/y bounds.
        self.assertGreater(first.intersected(second).width(), tile.width()*.5)
        self.assertGreater(first.intersected(second).height(), tile.height()*.5)
        self.assertLessEqual(tile.width(), maximum_size+2)
        self.assertLessEqual(tile.height(), maximum_size+2)
        sample = lambda fx, fy: image.pixelColor(
            tile.left()+round((tile.width()-1)*fx), tile.top()+round((tile.height()-1)*fy)).name()
        self.assertEqual(sample(.15, .15), "#ff0000")
        # The count badge covers the lower-right corner at compact sizes.
        self.assertIn("#0000ff", [sample(fx, fy) for fx, fy in
                                 ((.95, .15), (.95, .25), (.8, .4), (.6, .6))])

    def _assert_frozen_sources(self):
        self.assertEqual(self.bundle.to_dict(), self.before)
        self.assertEqual(tuple(path.read_bytes() for path in self.sources), self.source_bytes)
        slot = self.visual.teams[0].slots[0]
        self.assertEqual(slot.set_counts, (2, 2))
        self.assertEqual(slot.set_labels, ("Emblem of Severed Fate 2pc", "Deepwood Memories 2pc"))
        self.assertEqual(slot.set_icon_paths, tuple(str(path) for path in self.sources))

    def test_collapsed_two_plus_two_paints_one_diagonal_icon(self):
        for width in (520, 864, 960, 1600):
            with self.subTest(width=width):
                image, region, card = self._card_image(self.visual, False, width)
                self._assert_diagonal_tile(image, region, 26)
                self.assertEqual(self.painted_text.count("2"), 1)
                self.assertEqual(card.height(), CardLayout(width).height(self.visual, False))
        self._assert_frozen_sources()

    def test_expanded_two_plus_two_paints_one_diagonal_icon(self):
        for width in (520, 864, 960, 1600):
            with self.subTest(width=width):
                image, region, _ = self._card_image(self.visual, True, width)
                self._assert_diagonal_tile(image, region, CardLayout(width).equipment_size)
                self.assertEqual(self.painted_text.count("2"), 1)
        self._assert_frozen_sources()

    def test_supplied_physical_three_plus_two_survives_save_as_one_card_icon(self):
        self._assert_saved_physical_pair((3, 2))

    def test_supplied_physical_two_plus_three_survives_save_as_one_card_icon(self):
        self._assert_saved_physical_pair((2, 3))

    def test_saved_physical_pairs_with_missing_icon_keep_original_counts(self):
        for counts in ((3, 2), (2, 3)):
            with self.subTest(counts=counts):
                visual, _, snapshot = _saved_supplied_set_run(
                    self.root, counts, tuple(str(path) for path in self.sources))
                before = snapshot.read_bytes()
                Path(visual.teams[0].slots[0].set_icon_paths[1]).unlink()
                for expanded in (False, True):
                    image, region, _ = self._card_image(visual, expanded, 960)
                    self.assertIsNotNone(_color_bounds(image, "#ff0000", region))
                    self.assertIsNone(_color_bounds(image, "#0000ff", region))
                    self.assertEqual(self.painted_text.count("2"), 1)
                    self.assertEqual(self.painted_text.count("3"), 1)
                self.assertEqual(visual.teams[0].slots[0].set_counts, counts)
                self.assertEqual(snapshot.read_bytes(), before)

    def _assert_saved_physical_pair(self, counts):
        for route in ("summary", "mini_sets"):
            with self.subTest(supplied_via=route):
                visual, store, snapshot = _saved_supplied_set_run(
                    self.root, counts, tuple(str(path) for path in self.sources), supplied_via=route)
                before = snapshot.read_bytes()
                slot = visual.teams[0].slots[0]
                self.assertEqual(slot.set_counts, counts)
                expected_labels = tuple(f"{name} {count}pc" for name, count in zip(
                    ("Emblem of Severed Fate", "Deepwood Memories"), counts))
                self.assertEqual(slot.set_labels, expected_labels)
                for expanded in (False, True):
                    image, region, _ = self._card_image(visual, expanded, 960)
                    self._assert_diagonal_tile(image, region, 26 if not expanded else CardLayout(960).equipment_size)
                    self.assertEqual(self.painted_text.count("2"), 1)
                    self.assertEqual(self.painted_text.count("3"), 0)
                # At the same logical width, PNG shares the card's slot allocation.
                _, region, _ = self._card_image(visual, True, 1200)
                destination = self.root / f"export-{counts[0]}-{counts[1]}-{route}.png"
                render_history_card_png(visual, destination, width=1200)
                self._assert_diagonal_tile(QImage(str(destination)), region, CardLayout(1200).equipment_size)
                self.assertEqual(snapshot.read_bytes(), before)
                self.assertEqual(tuple(b.piece_count for b in store.read_bundle(visual.bundle_id).teams[0].slots[0].artifact_build.active_set_bonuses), counts)
                self.assertEqual(slot.set_labels, expected_labels)
        self._assert_frozen_sources()

    def test_png_export_keeps_diagonal_halves_at_native_and_scaled_widths(self):
        for width in (1200, 1600):
            with self.subTest(width=width):
                destination = self.root / f"export-{width}.png"
                painted = []
                original = CardPainter.text
                def text(draw, x, y, w, value, *args, **kwargs):
                    painted.append(str(value))
                    return original(draw, x, y, w, value, *args, **kwargs)
                with patch.object(CardPainter, "text", text):
                    size = render_history_card_png(self.visual, destination, width=width)
                image = QImage(str(destination))
                self.assertEqual(image.size(), size)
                self._assert_diagonal_tile(image, image.rect(), CardLayout(1200).equipment_size*width/1200)
                self.assertEqual(painted.count("2"), 1)
        self._assert_frozen_sources()

    def test_four_piece_and_single_two_piece_still_use_the_original_icon_and_count(self):
        slot = self.visual.teams[0].slots[0]
        for count in (2, 4):
            updated = replace(slot, set_counts=(count,), set_icon_paths=(str(self.sources[0]),),
                              set_labels=(f"Emblem of Severed Fate {count}pc",))
            visual = replace(self.visual, teams=(replace(self.visual.teams[0], slots=(updated,)),))
            for expanded in (False, True):
                with self.subTest(count=count, expanded=expanded):
                    image, region, _ = self._card_image(visual, expanded, 960)
                    red = _color_bounds(image, "#ff0000", region)
                    self.assertIsNotNone(red)
                    self.assertIsNone(_color_bounds(image, "#0000ff", region))
                    self.assertEqual(image.pixelColor(red.left()+2, red.top()+2).name(), "#ff0000")
                    self.assertEqual(self.painted_text.count(str(count)), 1)

    def test_missing_halves_keep_surviving_icon_and_no_sets_still_render(self):
        slot = self.visual.teams[0].slots[0]
        missing = str(self.root / "missing.png")
        cases = (
            ((str(self.sources[0]), missing), "#ff0000"),
            ((missing, str(self.sources[1])), "#0000ff"),
            ((str(self.sources[0]), ""), "#ff0000"),
            ((missing, ""), None),
            ((), None),
        )
        for paths, expected in cases:
            updated = replace(slot, set_icon_paths=paths, set_counts=(2, 2) if paths else (),
                              set_labels=slot.set_labels if paths else ())
            visual = replace(self.visual, teams=(replace(self.visual.teams[0], slots=(updated,)),))
            for expanded in (False, True):
                with self.subTest(paths=paths, expanded=expanded):
                    image, region, _ = self._card_image(visual, expanded, 960)
                    self.assertEqual(self.painted_text.count("2"), 2 if paths else 0)
                    self.assertEqual(len(set(self.count_positions)), 2 if paths else 0)
                    for color in ("#ff0000", "#0000ff"):
                        bounds = _color_bounds(image, color, region)
                        if color == expected:
                            self.assertIsNotNone(bounds)
                            self.assertEqual(image.pixelColor(bounds.left()+2, bounds.top()+2).name(), color)
                        else:
                            self.assertIsNone(bounds)
        self._assert_frozen_sources()


if __name__ == "__main__":
    unittest.main()
