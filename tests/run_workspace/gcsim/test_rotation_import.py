import unittest

from run_workspace.gcsim.rotation_import import RotationImportError, prepare_rotation
from run_workspace.gcsim.rotation_editor import parse
from run_workspace.gcsim.rotation_editor.team import from_selected_team
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT


TEAM = ('furina', 'ororon', 'bennett', 'chasca')
SHELL = 'options iteration=1000; target lvl=100 hp=999999999; active furina; furina skill;'


class RotationImportTests(unittest.TestCase):
    def test_extracts_program_in_order_including_helpers_before_builds(self):
        helper = 'fn rotate() { furina skill; }'
        source = helper + '\nfurina char lvl=90/90 cons=6 talent=10,10,10;\n' + \
            'furina add weapon="favoniussword" refine=5 lvl=90/90;\n' + \
            'furina add set="goldentroupe" count=4 +params=[stacks=4];\n' + \
            'target lvl=1 hp=1; options iteration=1;\n# keep this comment\nactive furina; rotate();'
        result = prepare_rotation(source, SHELL, DIALECT, TEAM)
        self.assertIn(helper, result.program)
        self.assertIn('# keep this comment\nactive furina; rotate();', result.program)
        self.assertNotIn(' char ', result.source)
        self.assertNotIn(' add ', result.source)
        self.assertNotIn('target lvl=1 ', result.source)
        self.assertIn('target lvl=100 hp=999999999;', result.source)
        self.assertTrue(parse(result.source, DIALECT).syntax_complete)

    def test_infinite_program_preserved_with_visible_duration_notice(self):
        program = 'active furina; while 1 { furina skill; }'
        result = prepare_rotation(program, SHELL, DIALECT, TEAM)
        self.assertEqual(result.program, program)
        self.assertIn(program, result.source)
        self.assertIn('duration=90', result.source)
        self.assertNotIn('hp=999999999', result.source)
        self.assertIn('rotation.import.duration_mode', result.notices)

    def test_unsafe_or_foreign_inputs_never_become_a_partial_rotation(self):
        for source, error in (
            ('active furina; unknown statement;', 'rotation.import.syntax'),
            ('active raiden; raiden skill;', 'rotation.editor.team_outside'),
            ('furina char lvl=90/90 +params=[start_hp=1]; active furina; furina skill;', 'rotation.import.initial_state'),
            ('furina skill;', 'rotation.import.active_missing'),
        ):
            with self.subTest(source=source), self.assertRaisesRegex(RotationImportError, error):
                prepare_rotation(source, SHELL, DIALECT, TEAM)

    def test_combined_draft_must_fit_the_same_parser_limit(self):
        source = '#' + 'x' * 1100000 + '\nactive furina; furina skill;'
        shell = 'options frame_defaults="' + 'x' * 1100000 + '"; active furina;'
        with self.assertRaisesRegex(RotationImportError, 'rotation.import.syntax'):
            prepare_rotation(source, shell, DIALECT, TEAM)

    def test_search_identity_tracks_weapon_but_editor_membership_does_not(self):
        base = {'character': {'gcsim_key': 'furina', 'name': 'Furina', 'constellation': 1},
                'weapon': {'gcsim_key': 'favoniussword', 'refinement': 3}}
        original = from_selected_team({'slots': [{'gcsim_virtual_override': base}]}, scope='test')
        changed = from_selected_team({'slots': [{'gcsim_virtual_override': dict(base, weapon={'gcsim_key': 'other', 'refinement': 1})}]}, scope='test')
        self.assertEqual(original.members[0].weapon, 'favoniussword')
        self.assertEqual(original.members[0].refinement, 3)
        self.assertEqual(original.binding, changed.binding)
        self.assertNotEqual(original.search_binding, changed.search_binding)


if __name__ == '__main__':
    unittest.main()
