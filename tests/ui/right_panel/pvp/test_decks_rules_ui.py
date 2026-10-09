"""Isolated Decks rules controls; no account or network data is loaded."""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QStackedWidget

from localization import get_language, set_language, tr
from ui.right_panel.live_run.panel import right_panel_stylesheet
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel


class _Workspace(QObject):
    state_changed = Signal()
    save_edit_requested = Signal()
    cancel_edit_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.preset = SimpleNamespace(
            deck_id="deck-1", name="Example", character_ids=("a",), weapon_refs=("w",),
            rules_snapshot={},
        )
        self.presets = [self.preset]
        self.selected_deck_id = self.preset.deck_id
        self.is_editing = False
        self.is_new_deck_edit = False
        self._last_status = ""
        self.selected_id = "old-rules"
        self.catalog_loaded = True
        self.refreshes = 0
        self.updated = 0
        self.selections: list[str] = []

    def active_preset(self):
        return self.preset

    def validation_report(self):
        return SimpleNamespace(ready=True, issue_codes=lambda: ())

    def rules_ui_state(self):
        return {
            "options": (
                {"id": "free_draft_v0", "label": "Free Draft"},
                {"id": "latest-rules", "label": "Abyss latest"},
            ),
            "selected_id": self.selected_id,
            "loading": False,
            "catalog_loaded": self.catalog_loaded,
            "editable": self.is_editing,
            "source_title": "Abyss 2026",
            "version_text": "v2",
            "freshness": "update" if self.selected_id == "old-rules" else "current",
            "update_id": "latest-rules" if self.selected_id == "old-rules" else "",
            "summary_lines": ("Total cost: 16",),
            "requirement_lines": ("At least 8 characters",),
            "issue_lines": ("One missing weapon",),
            "error_text": "",
        }

    def refresh_rules_catalog(self):
        self.refreshes += 1

    def update_ruleset(self):
        self.updated += 1
        return True

    def select_ruleset(self, ruleset_id):
        self.selections.append(ruleset_id)
        self.selected_id = ruleset_id
        self.state_changed.emit()
        return True

    def begin_edit(self):
        self.is_editing = True
        self.state_changed.emit()
        return True

    def save_edit(self, *, name):
        self.preset.name = name
        self.is_editing = False
        self.state_changed.emit()
        return True

    def cancel_edit(self):
        self.is_editing = False
        self.state_changed.emit()

    def select_deck(self, deck_id):
        self.selected_deck_id = deck_id

    def delete_deck(self, deck_id):
        return False

    def export_profile(self, path):
        return False


def _long_rules_state(workspace):
    """Synthetic, localized long content for layout tests and offscreen review."""
    state = workspace.rules_ui_state()
    t = lambda key, **values: tr("app_shell.pvp.rules." + key).format(**values)
    state.update(
        source_title="Abyss Cup · Layout fixture",
        version_text="09.10.2026 00:00 UTC",
        summary_lines=(
            t("character_cost", value="987"),
            t("weapon_base_cost", value="128"),
            t("weapon_cost", value="?"),
            t("card_legend"),
            t("tier_counts", values="T0: 12 · T1: 17 · T2: 4 · T3: 3 · T4: 2"),
        ),
        requirement_lines=tuple(
            t("limit", subject=t(group + "_" + metric), minimum="8", maximum="500")
            for group in ("agents", "engines") for metric in ("cost", "count")
        ) + tuple(f"T{tier}: {tier * 15}–{tier * 15 + 14}" for tier in range(5)) + (
            t("requires", tier=4, parts="T1 " + t("role_dd") + " + T1 " + t("role_support")),
            t("equals", tier=2, parts="T0 + T0 + T1") + t("threshold", value="30"),
            t("required", names="Amber, Lisa, Kaeya, Barbara, Xiangling, Noelle, Collei"),
        ),
        requirement_rows=(
            {"label": t("limit", subject=t("agents_cost"), minimum="8", maximum="500"),
             "current": "0 / 2", "status": "fail",
             "detail": t("required", names="Amber, Lisa, Kaeya, Barbara, Xiangling, Noelle, Collei")},
            {"label": t("limit", subject=t("engines_cost"), minimum="8", maximum="500"),
             "current": "17 / 20", "status": "pass"},
            {"label": t("requires", tier=4, parts="T1 " + t("role_dd") + " + T1 " + t("role_support")),
             "current": "1 / 2", "status": "unknown"},
            {"label": "T1 " + t("role_support"),
             "current": "0 / 1", "status": "info", "depth": 1,
             "character_filter": (1, 1),
             "detail": t("tier_combination_unverified")},
        ) * 3,
        issue_lines=(t("traveler_unavailable"), t("weapon_assignment_needed"),
                     t("tier_combination_unverified"), t("unsupported_rule")),
    )
    return state


class DecksRulesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_view_shows_saved_unlisted_rules_and_refresh_and_update(self):
        workspace = _Workspace()
        panel = PvpDecksRightPanel(workspace)

        self.assertFalse(panel.ruleset_button.isEnabled())
        self.assertIsNone(panel.ruleset_button.currentData())
        self.assertIn("Abyss 2026", panel.ruleset_button.currentText())
        self.assertEqual(panel.ruleset_button.count(), 3)
        self.assertEqual(panel.rules_refresh_button.text(), tr("app_shell.pvp.decks.rules_refresh"))
        panel.rules_refresh_button.click()
        panel.rules_update_button.click()
        self.assertEqual((workspace.refreshes, workspace.updated), (1, 1))
        self.assertEqual(
            panel.selected_info_labels["counts"].text(),
            tr("app_shell.pvp.decks.counts").format(characters=1, weapons=1),
        )
        details = [label.text() for label in panel.findChildren(type(panel.status_label))]
        self.assertIn("Total cost: 16", details)
        self.assertIn("At least 8 characters", details)
        self.assertIn("One missing weapon", details)
        panel.deleteLater()

    def test_edit_selection_preserves_unsaved_name_across_state_refresh(self):
        workspace = _Workspace()
        workspace.selected_id = "free_draft_v0"
        workspace.catalog_loaded = False
        panel = PvpDecksRightPanel(workspace)
        self.assertEqual(panel.rules_refresh_button.text(), tr("app_shell.pvp.decks.rules_load"))
        workspace.begin_edit()
        panel.edit_name_edit.setText("Unsaved name")
        self.assertTrue(panel.ruleset_button.isEnabled())

        index = panel.ruleset_button.findData("latest-rules")
        panel.ruleset_button.activated.emit(index)

        self.assertEqual(workspace.selections, ["latest-rules"])
        self.assertEqual(panel.edit_name_edit.text(), "Unsaved name")
        self.assertEqual(panel.ruleset_button.currentData(), "latest-rules")
        panel.deleteLater()

    def test_new_deck_exposes_rules_before_any_preset_is_saved(self):
        workspace = _Workspace()
        workspace.presets = []
        workspace.selected_deck_id = workspace.preset.deck_id
        workspace.is_editing = True
        workspace.is_new_deck_edit = True
        workspace.selected_id = "free_draft_v0"
        panel = PvpDecksRightPanel(workspace)

        self.assertTrue(panel.new_deck_info.isVisibleTo(panel))
        self.assertTrue(panel.ruleset_button.isEnabled())
        self.assertEqual(panel.ruleset_button.currentData(), "free_draft_v0")
        self.assertIn("counts", panel.selected_info_labels)
        panel.deleteLater()

    def test_rules_snapshot_uses_editable_validation_message(self):
        workspace = _Workspace()
        workspace.preset.rules_snapshot = {"source": {"title": "Abyss"}}
        panel = PvpDecksRightPanel(workspace)

        self.assertEqual(
            panel.selected_info_labels["validation"].text(),
            tr("app_shell.pvp.rules.deck_editable"),
        )
        panel.deleteLater()

    def test_requirement_table_has_three_columns_and_accessible_statuses(self):
        workspace = _Workspace()
        workspace.presets = []
        workspace.is_editing = True
        workspace.is_new_deck_edit = True
        state = workspace.rules_ui_state()
        state["requirement_rows"] = (
            {"label": "Minimum characters", "current": "0 / 2", "status": "fail", "detail": "Choose two"},
            {"label": "Weapon budget", "current": "10 / 12", "status": "pass"},
            {"label": "Tier combination", "current": "1 / 2", "status": "unknown"},
            {"label": "Damage role", "current": "—", "status": "info", "depth": 1},
        )
        workspace.rules_ui_state = lambda: state
        panel = PvpDecksRightPanel(workspace)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        table = panel.findChild(QGridLayout, "pvp_requirement_table")
        self.assertIsNotNone(table)
        self.assertEqual(table.columnCount(), 3)
        headers = [table.itemAtPosition(0, i).widget().text() for i in range(3)]
        self.assertEqual(headers, [tr("app_shell.pvp.rules." + key) for key in
                                   ("table_requirement", "table_current", "table_status")])
        markers = panel.findChildren(QLabel, "pvp_requirement_status")
        self.assertTrue(all(marker.pixmap() is not None and not marker.pixmap().isNull()
                            for marker in markers[:2]))
        self.assertNotEqual(markers[0].pixmap().cacheKey(), markers[1].pixmap().cacheKey())
        self.assertEqual([marker.text() for marker in markers[2:]], ["?", "—"])
        self.assertEqual([marker.property("requirementStatus") for marker in markers],
                         ["fail", "pass", "unknown", "info"])
        self.assertEqual([marker.accessibleName() for marker in markers],
                         [tr("app_shell.pvp.rules.status_" + status)
                          for status in ("fail", "pass", "unknown", "info")])
        self.assertEqual([marker.width() for marker in markers], [54] * 4)
        self.assertEqual([label.text() for label in panel.findChildren(QLabel,
                          "pvp_requirement_detail")], ["Choose two"])
        self.assertIs(table.itemAtPosition(2, 0), table.itemAtPosition(2, 1))
        self.assertIsNone(table.itemAtPosition(2, 2))
        margins = table.itemAtPosition(5, 0).widget().contentsMargins()
        self.assertEqual((margins.left(), margins.top()), (12, 0))
        self.assertFalse(any(label.text() == "At least 8 characters"
                             for label in panel.findChildren(QLabel)))
        panel.deleteLater()


class DecksRulesLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.previous_font = cls.app.font()
        cls.fixture_fonts = []
        # Windows' offscreen plugin has no system fonts; load only the fixture
        # fonts so wrapping/render checks exercise text rather than tofu boxes.
        if not QFontDatabase.families() and os.name == "nt":
            fonts = Path(os.environ["WINDIR"]) / "Fonts"
            for name in ("segoeui.ttf", "segoeuib.ttf"):
                font_id = QFontDatabase.addApplicationFont(str(fonts / name))
                if font_id >= 0:
                    cls.fixture_fonts.append(font_id)
        if "Segoe UI" in QFontDatabase.families():
            cls.app.setFont(QFont("Segoe UI", 9))

    @classmethod
    def tearDownClass(cls):
        cls.app.setFont(cls.previous_font)
        for font_id in cls.fixture_fonts:
            QFontDatabase.removeApplicationFont(font_id)

    def setUp(self):
        language = get_language()
        self.addCleanup(set_language, language, persist=False)

    def settle(self):
        for _ in range(8):
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def make_panel(self, *, new=True, saved=False, language="ru"):
        set_language(language, persist=False)
        workspace = _Workspace()
        workspace.is_editing = True
        workspace.is_new_deck_edit = new
        workspace.preset.rules_snapshot = {"source": {"title": "Abyss"}}
        if new:
            workspace.presets = [SimpleNamespace(
                deck_id="another", name="Saved deck", character_ids=("b",), weapon_refs=(),
            )] if saved else []
        state = _long_rules_state(workspace)
        workspace.rules_ui_state = lambda: state
        panel = PvpDecksRightPanel(workspace)
        host = QStackedWidget()
        host.setStyleSheet(right_panel_stylesheet())
        host.addWidget(panel)
        self.addCleanup(host.deleteLater)
        self.addCleanup(host.close)
        return workspace, state, panel, host

    def assert_readable(self, panel):
        labels = [label for label in panel.findChildren(QLabel)
                  if label.objectName() in ("pvp_deck_info_line", "pvp_rules_heading",
                                            "pvp_requirement_header", "pvp_requirement_description",
                                            "pvp_requirement_current", "pvp_requirement_detail")
                  and label.isVisibleTo(panel)]
        self.assertGreater(len(labels), 20)
        for label in labels:
            required = label.heightForWidth(label.width()) if label.wordWrap() else label.sizeHint().height()
            self.assertGreaterEqual(label.height(), required, label.text())
            siblings = [other for other in labels if other.parentWidget() is label.parentWidget()
                        and other is not label]
            for other in siblings:
                self.assertFalse(label.geometry().intersects(other.geometry()), label.text())
        scroll = panel.deck_list_scroll
        content = scroll.widget()
        self.assertLessEqual(content.width(), scroll.viewport().width())
        self.assertLessEqual(content.height(), max(scroll.viewport().height(), content.heightForWidth(content.width())) + 2)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        table = panel.findChild(QGridLayout, "pvp_requirement_table")
        self.assertIsNotNone(table)
        first = table.itemAtPosition(1, 0).widget()
        current = table.itemAtPosition(1, 1).widget()
        status = table.itemAtPosition(1, 2).widget()
        self.assertLess(first.geometry().right(), current.geometry().left())
        self.assertLess(current.geometry().right(), status.geometry().left())
        self.assertGreaterEqual(first.height(), first.heightForWidth(first.width()))
        self.assertGreaterEqual(current.height(), current.heightForWidth(current.width()))

    def test_long_new_and_saved_rules_wrap_in_constrained_hosts(self):
        for language in ("ru", "en", "pt-br"):
            for new, saved in ((True, False), (True, True), (False, True)):
                with self.subTest(language=language, new=new, saved=saved):
                    _, _, panel, host = self.make_panel(new=new, saved=saved, language=language)
                    for width, height in ((354, 480), (650, 590)):
                        host.setFixedSize(width, height)
                        host.show()
                        self.settle()
                        self.assert_readable(panel)
                        self.assertLessEqual(panel.minimumSizeHint().height(), height)
                    host.close()

    def test_refresh_preserves_scroll_and_deck_change_resets_it(self):
        workspace, _, panel, host = self.make_panel()
        host.setFixedSize(354, 480)
        host.show()
        self.settle()
        scroll = panel.deck_list_scroll.verticalScrollBar()
        scroll.setValue(scroll.maximum() // 2)
        previous = scroll.value()
        workspace.state_changed.emit()
        workspace.state_changed.emit()
        self.settle()
        self.assertEqual(scroll.value(), previous)
        self.assert_readable(panel)
        workspace.preset.deck_id = "another-deck"
        workspace.state_changed.emit()
        self.settle()
        self.assertEqual(scroll.value(), 0)

    def test_role_actions_fit_next_to_the_requirement_in_all_languages(self):
        for language in ("ru", "en", "pt-br"):
            workspace, state, panel, host = self.make_panel(language=language)
            calls = []
            workspace.toggle_requirement_filter = lambda *criterion: calls.append(criterion)
            host.setFixedSize(354, 480)
            host.show()
            self.settle()
            buttons = panel.findChildren(QPushButton, "pvp_requirement_show")
            self.assertEqual(len(buttons), 3)
            for button in buttons:
                label = button.parentWidget().findChild(QLabel, "pvp_requirement_description")
                self.assertGreaterEqual(button.width(), button.sizeHint().width())
                self.assertLess(label.geometry().right(), button.geometry().left())
                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
                self.assertLessEqual(button.geometry().right(), button.parentWidget().width())
            buttons[0].click()
            self.assertEqual(calls, [(1, 1)])
            state["active_character_filter"] = (1, 1)
            workspace.state_changed.emit()
            self.settle()
            self.assertTrue(all(button.isChecked() for button in panel.findChildren(QPushButton, "pvp_requirement_show")))
            self.assert_readable(panel)
            host.close()

    def test_bottom_is_reachable_and_short_rules_shrink_content(self):
        workspace, state, panel, host = self.make_panel()
        host.setFixedSize(354, 480)
        host.show()
        self.settle()
        scroll = panel.deck_list_scroll
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.settle()
        final = panel.selected_info_labels["validation"]
        bottom = final.mapTo(scroll.viewport(), QPoint(0, final.height())).y()
        self.assertLessEqual(bottom, scroll.viewport().height())
        self.assertGreaterEqual(bottom, scroll.viewport().height() - 32)
        previous_height = scroll.widget().height()
        state.update(selected_id="free_draft_v0", source_title="", version_text="",
                     freshness="free", update_id="", summary_lines=(), requirement_lines=(),
                     requirement_rows=(), issue_lines=())
        workspace.state_changed.emit()
        self.settle()
        self.assertLess(scroll.widget().height(), previous_height)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.verticalScrollBar().value(), 0)
        self.assertTrue(panel.ruleset_button.isVisibleTo(panel))


if __name__ == "__main__":
    unittest.main()
