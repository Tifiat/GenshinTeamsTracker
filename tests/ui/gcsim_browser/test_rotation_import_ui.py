"""Controlled network responses; no AppShell, account or startup mutations."""
import os
os.environ.setdefault('GTT_LANGUAGE', 'ru')

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from run_workspace.gcsim.rotation_database import DatabaseMember, RotationRecord, SearchResult
from run_workspace.gcsim.rotation_editor import Dialect
from run_workspace.gcsim.rotation_editor.team import TeamContext, TeamMember
from ui.gcsim_browser.rotation_import import RotationImportDialog
from ui.gcsim_browser.window import GcsimBrowserWorkspace

APP = QApplication.instance() or QApplication([])
KEYS = ('furina', 'ororon', 'bennett', 'chasca')
TEAM = TeamContext('public', tuple(TeamMember(key, key, key, 0, 'weapon', 1) for key in KEYS))
ENV = SimpleNamespace(identity='public', dialect=Dialect({key: key for key in KEYS}), character_options={})
SHELL = 'options iteration=10; target lvl=100; active furina; furina skill;'


def record(identifier, *, cons=0, description='Only the author text.', source='active furina; furina burst;'):
    return RotationRecord(identifier, source, description, 'author', '',
        tuple(DatabaseMember(key, cons, 'weapon', 1, {'gt': 4}) for key in KEYS))


class RotationImportUiTests(unittest.TestCase):
    def dialog(self, records):
        dialog = RotationImportDialog(TEAM, ENV, SHELL,
            search=lambda *args, **kwargs: SearchResult(tuple(records), True))
        dialog.show()
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.worker.wait(3000))
        APP.processEvents()
        return dialog

    def browser(self):
        browser = GcsimBrowserWorkspace()
        browser.rotation_team_provider = lambda index: TEAM
        browser._load_rotation_environment = lambda: ENV
        browser.rotation_editor.setPlainText(SHELL)
        browser.show()
        self.addCleanup(browser.close)
        return browser

    def test_first_preview_is_ranked_and_description_is_unpolluted(self):
        dialog = self.dialog([record('changed', cons=6), record('exact')])
        self.assertEqual(dialog.records[0].id, 'exact')
        self.assertEqual(dialog.description.toPlainText(), 'Only the author text.')
        self.assertIn('Взрыв стихии', dialog.readable.toPlainText())
        self.assertTrue(dialog.load_button.isEnabled())
        selected = []
        dialog.chosen.connect(selected.append)
        QTest.mouseClick(dialog.load_button, Qt.MouseButton.LeftButton)
        self.assertEqual(selected, [dialog.prepared.source])

    def test_unsupported_candidate_keeps_original_without_enabling_load(self):
        dialog = self.dialog([record('unsupported', source='active furina; ???;')])
        self.assertFalse(dialog.load_button.isEnabled())
        self.assertIn('???', dialog.original.toPlainText())
        self.assertFalse(dialog.code.toPlainText())

    def test_loading_preserves_main_code_and_existing_draft_undo(self):
        browser = self.browser()
        browser._create_rotation_window(ENV, SHELL, reset_base=True)
        window = browser._rotation_window
        self.addCleanup(window.close)
        dialog = self.dialog([record('new')])
        snapshot = browser._import_state(ENV, TEAM)
        browser._accept_rotation_import(dialog.prepared.source, snapshot, dialog)
        self.assertEqual(browser.rotation_editor.toPlainText(), SHELL)
        self.assertIn('furina burst;', window.session.code_text())
        window.session.undo()
        self.assertEqual(window.session.code_text(), SHELL)

    def test_stale_main_revision_and_team_roundtrip_reject_import(self):
        browser = self.browser()
        dialog = self.dialog([record('new')])
        snapshot = browser._import_state(ENV, TEAM)
        browser.rotation_editor.setPlainText(SHELL + '\nwait(1);')
        browser.rotation_editor.setPlainText(SHELL)
        browser._accept_rotation_import(dialog.prepared.source, snapshot, dialog)
        self.assertFalse(dialog.load_button.isEnabled())
        self.assertIsNone(browser._rotation_window)
        browser.refresh_rotation_team_context()
        snapshot = browser._import_state(ENV, TEAM)
        browser.rotation_team_provider = lambda index: replace(TEAM, scope='other')
        browser.refresh_rotation_team_context()
        browser.rotation_team_provider = lambda index: TEAM
        browser.refresh_rotation_team_context()
        self.assertNotEqual(snapshot, browser._import_state(ENV, TEAM))

    def test_failed_window_creation_keeps_picker_and_main_code(self):
        browser = self.browser()
        dialog = self.dialog([record('new')])
        snapshot = browser._import_state(ENV, TEAM)
        with patch.object(browser, '_create_rotation_window', return_value=False):
            browser._accept_rotation_import(dialog.prepared.source, snapshot, dialog)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(browser.rotation_editor.toPlainText(), SHELL)

    def test_open_button_establishes_context_before_unchanged_refresh(self):
        browser = self.browser()
        def make_picker(*args, **kwargs):
            return RotationImportDialog(*args, **kwargs,
                search=lambda *args, **kwargs: SearchResult((record('new'),), True))
        with patch('ui.gcsim_browser.rotation_import.RotationImportDialog', side_effect=make_picker):
            QTest.mouseClick(browser.import_rotation_button, Qt.MouseButton.LeftButton)
        dialog = browser._import_dialog
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.worker.wait(3000))
        APP.processEvents()
        browser.refresh_rotation_team_context()
        QTest.mouseClick(dialog.load_button, Qt.MouseButton.LeftButton)
        self.assertIsNotNone(browser._rotation_window)
        self.addCleanup(browser._rotation_window.close)
        self.assertIn('furina burst;', browser._rotation_window.session.code_text())
        self.assertEqual(browser.rotation_editor.toPlainText(), SHELL)


if __name__ == '__main__':
    unittest.main()
