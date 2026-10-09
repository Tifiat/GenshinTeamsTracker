import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_workspace.gcsim.rotation_editor import CodeGenerationError
from run_workspace.gcsim.rotation_editor.conditions import Condition, make_if
from run_workspace.gcsim.rotation_editor.editing import insert
from run_workspace.gcsim.rotation_editor.model import action, node
from run_workspace.gcsim.rotation_editor.options import ActionOption, CharacterOptions, EngineIdentity
from run_workspace.gcsim.rotation_editor.session import EditorSession
from run_workspace.gcsim.rotation_editor.team import from_selected_team, load_selected_team
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, translator
from run_workspace.gcsim.rotation_editor.readable import render


class RotationTeamTests(unittest.TestCase):
    def test_membership_cannot_be_taken_from_imported_code(self):
        source = 'active furina; bennett skill;'
        session = EditorSession(source, DIALECT, allowed_actors=('furina',))
        self.assertEqual(session.code_text(), source)
        with self.assertRaisesRegex(CodeGenerationError, 'rotation.team.outside'):
            session.commit()
        previous = session.current
        with self.assertRaisesRegex(CodeGenerationError, 'rotation.team.outside'):
            session.edit_structure(insert, None, action('chasca', 'skill'))
        self.assertIs(session.current, previous)

    def test_alias_is_allowed_but_foreign_conditions_and_explicit_keys_are_not(self):
        session = EditorSession('active furinadefontaine; furina skill;', DIALECT, allowed_actors=('furina',))
        self.assertTrue(session.commit().syntax_complete)
        for source in ('active chasca;', 'active furina; if .bennett.energy > 0 { furina skill; }',
                       'active furina; execute_action(.keys.char.chasca, .action.skill, []);'):
            session.set_code(source)
            with self.assertRaisesRegex(CodeGenerationError, 'rotation.team.outside'):
                session.commit()

    def test_empty_roster_fails_closed_and_does_not_rewrite_draft(self):
        session = EditorSession('active furina; furina skill;', DIALECT, allowed_actors=())
        with self.assertRaisesRegex(CodeGenerationError, 'rotation.team.empty'):
            session.commit()
        self.assertEqual(session.code_text(), 'active furina; furina skill;')

    def test_documented_invalid_and_unknown_actions_rejected_before_insertion(self):
        descriptor = CharacterOptions('furina', EngineIdentity('fixture', 'public'),
            (ActionOption('skill', False), ActionOption('aim', True)), (), (), 'fixture')
        session = EditorSession('active furina; furina skill;', DIALECT, allowed_actors=('furina',), character_options={'furina': descriptor})
        for name in ('aim', 'charge'):
            previous = session.current
            with self.assertRaises(CodeGenerationError):
                session.edit_structure(insert, None, action('furina', name))
            self.assertIs(session.current, previous)

    def test_account_identity_comes_from_stored_key_not_display_name(self):
        payload = {'slots': [{'character': {'id': '21', 'name': 'Chasca', 'gcsim_character_key': 'furina', 'gcsim_character_key_status': 'ready'}},
            {'gcsim_virtual_override': {'character': {'gcsim_key': 'chasca', 'name': 'Virtual Chasca', 'constellation': 6}}}]}
        context = from_selected_team(payload, scope='team:0', lookup=lambda value: {'gcsim_character_key': 'bennett', 'gcsim_character_key_status': 'ready'})
        self.assertEqual(context.keys, ('bennett', 'chasca'))
        self.assertEqual(context.members[-1].constellation, 6)
        unresolved = from_selected_team(payload, scope='team:0', lookup=lambda value: {'gcsim_character_key': 'furina', 'gcsim_character_key_status': 'ambiguous'})
        self.assertEqual(unresolved.keys, ('chasca',))
        self.assertEqual(unresolved.unresolved, ('21',))

    def test_missing_database_is_not_created_and_old_snapshot_not_trusted(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'missing.db'
            payload = {'slots': [{'character': {'id': '21', 'gcsim_character_key': 'furina', 'gcsim_character_key_status': 'ready'}}]}
            context = load_selected_team(payload, scope='team:0', database=path)
            self.assertEqual(context.keys, ())
            self.assertFalse(path.exists())

    def test_selected_database_identity_read_does_not_modify_database(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.db'
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE account_characters(character_id INTEGER PRIMARY KEY, gcsim_character_key TEXT, gcsim_character_key_status TEXT)')
                conn.execute("INSERT INTO account_characters VALUES(21,'bennett','ready')")
                conn.commit()
            before = path.read_bytes()
            context = load_selected_team({'slots': [{'character': {'id': '21', 'name': 'Bennett'}}]}, scope='team:0', database=path)
            self.assertEqual(context.keys, ('bennett',))
            self.assertEqual(path.read_bytes(), before)

    def test_compact_readable_merges_actions_without_erasing_branches(self):
        session = EditorSession('active furina; for let i=0; i<4; i=i+1 { if is_even(i) { furina skill, dash, burst; } chasca skill, aim[bullets=4]; }', DIALECT)
        text = render(session.current, translator(), resolve_name={'furina': 'Фурина', 'chasca': 'Часка'}.get).compact_text()
        self.assertIn('Цикл из 4 ротаций', text)
        self.assertIn('В каждой нечётной ротации', text)
        self.assertIn('Фурина: Элементальный навык, Рывок, Взрыв стихии', text)
        self.assertNotIn('i <', text)
        self.assertIn('4', text)
        self.assertLess(len(text.splitlines()), 8)


if __name__ == '__main__':
    unittest.main()
