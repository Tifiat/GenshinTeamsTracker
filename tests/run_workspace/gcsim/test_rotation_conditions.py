import unittest

from run_workspace.gcsim.rotation_editor import Dialect, node, parse, write
from run_workspace.gcsim.rotation_editor.conditions import Condition, compile_condition, describe, make_if, make_while, recognize
from run_workspace.gcsim.rotation_editor.context import context_for
from run_workspace.gcsim.rotation_editor.model import action, shape
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.session import EditorSession
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, NAMES, translator


CONDITION_CASES = (
    ('.furina.energy >= .furina.energymax', Condition('energy_full', 'furina')),
    ('.furina.energymax <= .furina.energy', Condition('energy_full', 'furina')),
    ('.furina.energy >= 60', Condition('energy', 'furina', operator='>=', value='60')),
    ('60 <= .furina.energy', Condition('energy', 'furina', operator='>=', value='60')),
    ('.furina.hpratio < .5', Condition('hp_percent', 'furina', operator='<', value='50')),
    ('.furina.onfield != 0', Condition('on_field', 'furina')),
    ('.furina.burst.ready == 1', Condition('action_ready', 'furina', 'burst')),
    ('.furina.skill.ready >= 1', Condition('action_ready', 'furina', 'skill')),
    ('.furina.status.favonius-cd > 0', Condition('effect', 'furina', 'favonius-cd')),
    ('.status.test-effect != 0', Condition('effect', subject='test-effect')),
    ('.chasca.nightsoul.state', Condition('mode', 'chasca', 'nightsoul')),
    ('.furina.ousia', Condition('mode', 'furina', 'ousia')),
    ('.chasca.cons < 6', Condition('constellations', 'chasca', operator='<', value='6')),
)


def with_condition(source):
    return parse('active furina; if ' + source + ' { furina skill; } else { furina burst; }', DIALECT)


class ConditionTests(unittest.TestCase):
    def test_import_recognition_is_source_preserving(self):
        for source, expected in CONDITION_CASES:
            with self.subTest(source=source):
                doc = with_condition(source)
                self.assertTrue(doc.syntax_complete, doc.diagnostics)
                self.assertEqual(recognize(doc, doc.root.get('items')[1].get('condition')), expected)
                self.assertEqual(write(doc), doc.source)

    def test_generated_choices_reparse_and_use_same_recognizer(self):
        base = parse('active furina;', DIALECT)
        for _, choice in CONDITION_CASES:
            condition = compile_condition(base, choice)
            block = make_if(base, choice, node('block', items=(action('furina', 'skill'),)))
            doc = base.replace(base.root.node_id, base.root.changed(items=(base.root.get('items')[0], block)))
            reparsed = parse(write(doc), DIALECT)
            self.assertTrue(reparsed.syntax_complete, reparsed.diagnostics)
            self.assertEqual(shape(doc.root), shape(reparsed.root))
            self.assertEqual(recognize(base, condition), choice)

    def test_negation_respects_timer_and_boolean_domains(self):
        for source in ('.furina.onfield == 0', '!.furina.onfield', '.furina.onfield < 1'):
            doc = with_condition(source)
            self.assertEqual(recognize(doc, doc.root.get('items')[1].get('condition')), Condition('not', children=(Condition('on_field', 'furina'),)))
        doc = with_condition('.furina.status.test-effect == 1')
        self.assertIsNone(recognize(doc, doc.root.get('items')[1].get('condition')))

    def test_compound_grouping_stays_visible_and_editable(self):
        doc = with_condition('(.furina.onfield || .chasca.nightsoul.state) && .furina.energy >= 60')
        block = doc.root.get('items')[1]
        choice = context_for(doc, block.node_id).properties[0].value
        self.assertEqual((choice.kind, choice.children[0].kind), ('all', 'any'))
        text = describe(choice, translator(), NAMES.get)
        self.assertIn('(Фурина на поле или действует Благословение Ночного духа (Часка)) и', text)
        regenerated = doc.replace(block.get('condition').node_id, compile_condition(doc, choice))
        self.assertEqual(shape(regenerated.root), shape(parse(write(regenerated), DIALECT).root))

    def test_unknown_terms_do_not_disappear_from_composites(self):
        for source in ('custom() && .furina.onfield', '.furina.energy >= needed', '.furina.hp < .furina.hpmax * .5', '.furina.energy >= .chasca.energymax', '.chasca.nightsoul.unknown', '.furina.hpratio < 2'):
            doc = with_condition(source)
            block = doc.root.get('items')[1]
            prop = context_for(doc, block.node_id).properties[0]
            self.assertFalse(prop.editable, source)
            self.assertEqual(write(doc), doc.source)

    def test_timer_is_not_mislabeled_as_general_active_state(self):
        doc = with_condition('!.chasca.status.nightsoul-blessing')
        text = render(doc, translator(), resolve_name=NAMES.get).text()
        self.assertIn('таймер «nightsoul-blessing» равен нулю', text)
        self.assertNotIn('Благословение Ночного духа не действует', text)
        text = render(with_condition('!.furina.status.favonius-cd'), translator(), resolve_name=NAMES.get).text()
        self.assertIn('таймер перезарядки Фавония равен нулю', text)
        self.assertNotIn('не на перезарядке', text)
        self.assertNotIn('не сработал', text)

    def test_conditions_do_not_create_character_windows(self):
        doc = parse('active furina; if .chasca.nightsoul.state { furina burst; }', DIALECT)
        from tests.run_workspace.gcsim.test_rotation_editor import flatten
        self.assertEqual([item.actor_key for item in flatten(render(doc, translator()).items) if item.kind == 'window'], ['furina'])

    def test_condition_edit_preserves_body_else_comments_and_undo(self):
        source = 'active furina; if .furina.energy>=60 /*test*/ {furina burst;} else {furina skill;}'
        # GCSL comments use # or //, so keep this fixture in that actual form.
        source = source.replace('/*test*/', '# test\n')
        session = EditorSession(source, DIALECT)
        block = session.current.root.get('items')[1]
        session.edit_option(block.node_id, 'condition', Condition('energy_full', 'furina'))
        code = session.code_text()
        self.assertIn('# test', code)
        self.assertIn('{furina burst;} else {furina skill;}', code)
        self.assertTrue(session.commit().syntax_complete)
        session.undo()
        self.assertIn('.furina.energymax', session.code_text())
        session.undo()
        self.assertEqual(session.code_text(), source)

    def test_new_if_and_while_keep_required_slots(self):
        for factory in (make_if, make_while):
            session = EditorSession('active furina;', DIALECT)
            block = factory(session.current)
            session.replace(session.current.root.node_id, session.current.root.changed(items=(*session.current.root.get('items'), block)))
            self.assertIsNone(session.code_text())
            session.edit_option(block.node_id, 'condition', Condition('on_field', 'furina'))
            self.assertIsNone(session.code_text())
            body = block.get('then') if block.kind == 'if' else block.get('body')
            session.replace(body.node_id, node('block', items=(action('furina', 'attack'),)))
            self.assertTrue(session.commit().syntax_complete)

    def test_while_and_condition_only_for_share_condition_property(self):
        for source in ('while .furina.energy<60 { furina attack; }', 'for .furina.energy<60 { furina attack; }'):
            session = EditorSession('active furina; ' + source, DIALECT)
            block = session.current.root.get('items')[1]
            self.assertTrue(context_for(session.current, block.node_id).properties[0].editable)
            session.edit_option(block.node_id, 'condition', Condition('not', children=(Condition('energy_full', 'furina'),)))
            self.assertTrue(session.commit().syntax_complete)
            self.assertIn('Повторять, пока энергия ещё не заполнена', render(session.current, translator()).text())

    def test_unknown_dialect_does_not_enable_mechanic_builders(self):
        doc = parse('active furina; if .furina.onfield { furina skill; }', Dialect(DIALECT.character_aliases))
        self.assertIsNone(recognize(doc, doc.root.get('items')[1].get('condition')))
        with self.assertRaises(ValueError):
            compile_condition(doc, Condition('on_field', 'furina'))

    def test_threshold_character_effect_and_depth_validation(self):
        doc = parse('', DIALECT)
        invalid = (Condition('energy', 'missing', value='60'), Condition('hp_percent', 'furina', value='101'),
                   Condition('energy', 'furina', value='NaN'), Condition('effect', 'furina', 'x; print(1)'),
                   Condition('all', children=()), Condition('mode', 'bennett', 'nightsoul'),
                   Condition('constellations', 'chasca', value='1.5'), Condition('hp_percent', 'furina', value='0.000000000001'))
        for choice in invalid:
            with self.assertRaises(ValueError):
                compile_condition(doc, choice)
        choice = Condition('on_field', 'furina')
        for _ in range(34):
            choice = Condition('not', children=(choice,))
        with self.assertRaises(ValueError):
            compile_condition(doc, choice)

    def test_aliases_and_all_locales(self):
        doc = with_condition('.furinadefontaine.energy >= .furina.energymax')
        self.assertEqual(recognize(doc, doc.root.get('items')[1].get('condition')), Condition('energy_full', 'furina'))
        for language in ('ru', 'en', 'pt-br'):
            for _, choice in CONDITION_CASES:
                self.assertNotIn('rotation.', describe(choice, translator(language), NAMES.get))


if __name__ == '__main__':
    unittest.main()
