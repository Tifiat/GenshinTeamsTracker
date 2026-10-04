"""Set tooltips against owned SQLite fixtures; no live account data or GUI launch."""

from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from run_workspace.right_panel_prototype_view_model import RightPanelBuildMiniSetViewModel
from ui.artifact_browser import queries
from ui.right_panel.common import slot_parts


class MiniSetTooltipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.db = self.folder / "catalog #1.db"
        self.stack.enter_context(patch.object(slot_parts, "ARTIFACT_DB_PATH", self.db))
        self.stack.enter_context(patch.object(slot_parts, "HOYOLAB_DATA_DIR", self.folder))
        self.stack.enter_context(patch.object(queries, "HOYOLAB_DATA_DIR", self.folder))
        slot_parts._cached_set_bonus_descriptions.cache_clear()
        self.addCleanup(slot_parts._cached_set_bonus_descriptions.cache_clear)
        self.widget = slot_parts.RightPanelArtifactMiniZoneWidget()
        self.addCleanup(self.widget.close)
        self.state = slot_parts.RightPanelArtifactMiniZoneState(
            mini_sets=(RightPanelBuildMiniSetViewModel("TestSet", "Test Set", 4, 4),)
        )

    def _create_catalog(self, *, wal=False):
        conn = self.stack.enter_context(closing(sqlite3.connect(self.db)))
        if wal:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE artifact_set_bonus_descriptions ("
            "set_uid TEXT, lang TEXT, piece_count INTEGER, description TEXT, "
            "source TEXT, updated_at TEXT, PRIMARY KEY(set_uid, lang, piece_count))"
        )
        conn.executemany(
            "INSERT INTO artifact_set_bonus_descriptions VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("TestSet", "en-us", 2, "<p>Two-piece &amp; bonus</p>", "fixture", "1"),
                ("TestSet", "en-us", 4, "<p>Four-piece bonus</p>", "fixture", "1"),
                ("TestSet", "ru-ru", 2, "Localized two-piece bonus", "fixture", "1"),
                ("TestSet", "ru-ru", 4, "Localized four-piece bonus", "fixture", "1"),
            ],
        )
        conn.commit()
        if wal:
            return conn
        conn.close()
        return None

    def _tooltip(self):
        return self.widget._tooltip_controller.text()

    def test_catalog_created_after_startup_restores_both_bonuses_without_repainting_icon(self):
        with patch.object(self.widget, "_render_visual", wraps=self.widget._render_visual) as render, \
                patch.object(slot_parts, "list_set_bonus_description_map", wraps=queries.list_set_bonus_description_map) as read:
            self.widget.set_state(self.state)
            self.assertEqual(self._tooltip(), "4p Test Set")
            self._create_catalog()
            self.widget.set_state(self.state)
            self.assertIn("Two-piece &amp; bonus", self._tooltip())
            self.assertIn("Four-piece bonus", self._tooltip())
            self.assertEqual(self.widget.toolTip(), "")
            self.widget.set_state(self.state)
            other = slot_parts.RightPanelArtifactMiniZoneWidget()
            self.addCleanup(other.close)
            other.set_state(self.state)
            self.assertEqual(read.call_count, 2)
            render.assert_called_once_with(self.state)

    def test_wal_catalog_update_refreshes_unchanged_set(self):
        conn = self._create_catalog(wal=True)
        self.widget.set_state(self.state)
        main_stamp = self.db.stat().st_mtime_ns
        conn.execute(
            "UPDATE artifact_set_bonus_descriptions SET description = ? "
            "WHERE lang = 'en-us' AND piece_count = 4",
            ("Updated four-piece bonus",),
        )
        conn.commit()
        self.assertEqual(self.db.stat().st_mtime_ns, main_stamp)
        self.widget.set_state(self.state)
        self.assertIn("Updated four-piece bonus", self._tooltip())
        self.assertNotIn("Four-piece bonus", self._tooltip())

    def test_content_language_refreshes_tooltip_without_changing_equipment(self):
        self._create_catalog()
        self.widget.set_state(self.state)
        (self.folder / "account_language.json").write_text(
            json.dumps({"contentLanguage": "ru-ru"}), encoding="utf-8"
        )
        self.widget.set_state(self.state)
        self.assertIn("Localized two-piece bonus", self._tooltip())
        self.assertIn("Localized four-piece bonus", self._tooltip())

    def test_transient_read_error_is_not_cached_and_same_state_recovers(self):
        self._create_catalog()
        descriptions = {("TestSet", 2): "Recovered two-piece", ("TestSet", 4): "Recovered four-piece"}
        with patch.object(slot_parts, "list_set_bonus_description_map", side_effect=[sqlite3.OperationalError("fixture busy"), descriptions]) as read:
            self.widget.set_state(self.state)
            self.assertEqual(self._tooltip(), "4p Test Set")
            self.widget.set_state(self.state)
            self.assertIn("Recovered four-piece", self._tooltip())
            self.widget.set_state(self.state)
            self.assertEqual(read.call_count, 2)

    def test_two_plus_two_shows_only_each_sets_two_piece_bonus(self):
        self._create_catalog()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO artifact_set_bonus_descriptions VALUES (?, ?, ?, ?, ?, ?)",
                ("OtherSet", "en-us", 2, "Other two-piece bonus", "fixture", "1"),
            )
            conn.commit()
        state = slot_parts.RightPanelArtifactMiniZoneState(mini_sets=(
            RightPanelBuildMiniSetViewModel("TestSet", "Test Set", 2, 2),
            RightPanelBuildMiniSetViewModel("OtherSet", "Other Set", 2, 2),
        ))
        self.widget.set_state(state)
        self.assertIn("Two-piece &amp; bonus", self._tooltip())
        self.assertIn("Other two-piece bonus", self._tooltip())
        self.assertNotIn("Four-piece bonus", self._tooltip())

    def test_description_lookup_reads_catalog_without_initialization_or_database_writes(self):
        self._create_catalog()
        before = self.db.read_bytes()
        with patch.object(queries, "connect_db") as connect, patch.object(queries, "init_db") as init:
            descriptions = queries.list_set_bonus_description_map(db_path=self.db)
        self.assertEqual(descriptions[("TestSet", 4)], "<p>Four-piece bonus</p>")
        connect.assert_not_called()
        init.assert_not_called()
        self.assertEqual(before, self.db.read_bytes())


if __name__ == "__main__":
    unittest.main()
