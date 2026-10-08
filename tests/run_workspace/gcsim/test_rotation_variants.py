import unittest

from run_workspace.gcsim.rotation_editor import Dialect, parse, write
from run_workspace.gcsim.rotation_editor.context import context_for
from run_workspace.gcsim.rotation_editor.model import shape
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.session import EditorSession
from run_workspace.gcsim.rotation_editor.variants import VARIANTS, VariantChoice, apply_variant, choices_for, plan_variant
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, NAMES, translator


VARIANT_CASES = (
    VariantChoice('bennett.skill_hold', 0), VariantChoice('bennett.skill_hold', 1), VariantChoice('bennett.skill_hold', 2),
    VariantChoice('chasca.nightsoul_aim', 6), VariantChoice('chasca.nightsoul_aim', 4),
    VariantChoice('chasca.nightsoul_aim', 6, 'guard'), VariantChoice('chasca.nightsoul_aim', 1, 'guard'),
    VariantChoice('furina.ousia_skill'), VariantChoice('furina.pneuma_skill'),
    VariantChoice('furina.pneuma_skill', preparation='guard'),
)


def plan_document(choice):
    doc = parse('active furina;', DIALECT)
    plan = plan_variant(doc, choice)
    return doc.replace(doc.root.node_id, doc.root.changed(items=(*doc.root.get('items'), plan.block))), plan


class VariantTests(unittest.TestCase):
    def test_all_plans_are_ordinary_nodes_and_roundtrip(self):
        for choice in VARIANT_CASES:
            with self.subTest(choice=choice):
                doc, _ = plan_document(choice)
                code = write(doc)
                reparsed = parse(code, DIALECT)
                self.assertTrue(reparsed.syntax_complete, reparsed.diagnostics)
                self.assertEqual(shape(doc.root), shape(reparsed.root))

    def test_chasca_preparation_is_guarded_and_attack_rechecks_state(self):
        doc, _ = plan_document(VariantChoice('chasca.nightsoul_aim', 6))
        code = write(doc)
        self.assertEqual(code.count('chasca skill;'), 1)
        self.assertIn('if !(.chasca.nightsoul.state)', code)
        self.assertIn('if .chasca.nightsoul.state', code)
        self.assertIn('aim[bullets=6]', code)
        text = render(doc, translator(), resolve_name=NAMES.get).text()
        self.assertIn('Благословение Ночного духа не действует', text)
        self.assertIn('действует Благословение Ночного духа', text)

    def test_partial_chasca_shots_have_visible_constellation_boundary(self):
        doc, plan = plan_document(VariantChoice('chasca.nightsoul_aim', 4))
        code = write(doc)
        self.assertIn('.chasca.cons < 6', code)
        self.assertIn('aim[bullets=4]', code)
        self.assertNotIn('c6-instant', code)
        self.assertIn('rotation.variant.chasca_partial_c0_c5', plan.note_keys)
        self.assertIn('число созвездий (Часка) меньше 6', render(doc, translator(), resolve_name=NAMES.get).text())

    def test_guard_policy_does_not_prepare_or_wait(self):
        for key in ('chasca.nightsoul_aim', 'furina.pneuma_skill'):
            doc, plan = plan_document(VariantChoice(key, preparation='guard'))
            code = write(doc)
            self.assertNotIn('chasca skill;', code)
            self.assertNotIn('furina charge;', code)
            self.assertNotIn('wait', code)
            self.assertNotIn('rotation.variant.furina_switch_wait', plan.note_keys)

    def test_furina_switch_wait_and_recheck_are_visible_and_ordered(self):
        for key in ('furina.ousia_skill', 'furina.pneuma_skill'):
            doc, plan = plan_document(VariantChoice(key))
            code = write(doc)
            self.assertEqual(code.count('furina charge;'), 1)
            self.assertLess(code.index('furina charge;'), code.index('(wait)(2);'))
            self.assertLess(code.index('(wait)(2);'), code.index('furina skill;'))
            self.assertEqual(code.count('.furina.ousia'), 2)
            self.assertIn('rotation.variant.furina_switch_wait', plan.note_keys)

    def test_import_and_context_inspection_never_insert_preparation(self):
        source = 'active chasca; chasca skill, aim[bullets=4], skill;'
        doc = parse(source, DIALECT)
        for item in doc.root.walk():
            if item.kind == 'action':
                context_for(doc, item.node_id)
        render(doc, translator())
        self.assertEqual(write(doc), source)

    def test_only_explicit_edit_splits_line_and_preserves_neighbour_order(self):
        source = 'active chasca; chasca dash, aim[bullets=6], jump; # tail\n'
        session = EditorSession(source, DIALECT)
        selected = next(item for item in session.current.root.walk() if item.kind == 'action' and item.get('name').get('value') == 'aim')
        session.edit_option(selected.node_id, 'variant', VariantChoice('chasca.nightsoul_aim', 6))
        code = session.code_text()
        self.assertLess(code.index('chasca dash;'), code.index('chasca skill;'))
        self.assertLess(code.index('aim[bullets=6]'), code.index('chasca jump;'))
        self.assertEqual(code.count('# tail'), 1)
        self.assertTrue(session.commit().syntax_complete)
        session.undo()
        session.undo()
        self.assertEqual(session.code_text(), source)

    def test_parameter_conflicts_and_repeated_actions_require_explicit_edit(self):
        for source, choice in (
            ('bennett skill[hold=1,hold_c4=1];', VariantChoice('bennett.skill_hold', 2)),
            ('chasca aim[hold=1,bullets=4];', VariantChoice('chasca.nightsoul_aim', 4)),
            ('chasca aim:4;', VariantChoice('chasca.nightsoul_aim', 6)),
        ):
            doc = parse('active furina; ' + source, DIALECT)
            selected = next(item for item in doc.root.walk() if item.kind == 'action')
            with self.assertRaises(ValueError):
                apply_variant(doc, selected.node_id, choice)
            self.assertEqual(write(doc), doc.source)

    def test_ranges_actor_and_custom_handlers_are_validated(self):
        doc = parse('active furina;', DIALECT)
        for choice in (VariantChoice('chasca.nightsoul_aim', 0), VariantChoice('chasca.nightsoul_aim', 7),
                       VariantChoice('bennett.skill_hold', True), VariantChoice('bennett.skill_hold', 3),
                       VariantChoice('furina.ousia_skill', 1), VariantChoice('missing'),
                       VariantChoice('furina.ousia_skill', preparation='hidden')):
            with self.assertRaises(ValueError):
                plan_variant(doc, choice)
        with self.assertRaises(ValueError):
            plan_variant(doc, VariantChoice('chasca.nightsoul_aim'), actor='furina')
        for source in ('let wait=fn(n){return n;};', 'execute_action=fn(a,b,c){return 0;};'):
            with self.assertRaises(ValueError):
                plan_variant(parse(source, DIALECT), VariantChoice('furina.ousia_skill'))

    def test_version_and_character_scoping(self):
        doc = parse('', Dialect(DIALECT.character_aliases))
        self.assertFalse(choices_for(doc, 'bennett', 'skill'))
        with self.assertRaises(ValueError):
            plan_variant(doc, VariantChoice('bennett.skill_hold', 1))
        doc = parse('', DIALECT)
        self.assertFalse(choices_for(doc, 'ororon', 'skill'))
        self.assertFalse(choices_for(doc, 'chasca', 'charge'))
        self.assertEqual(len(choices_for(doc, 'furinadefontaine', 'skill')), 2)

    def test_all_variants_have_localized_labels_and_requirements(self):
        for language in ('ru', 'en', 'pt-br'):
            tr = translator(language)
            for variant in VARIANTS:
                self.assertNotIn('rotation.', tr(variant.label_key))
                for key in variant.requirement_keys:
                    self.assertNotIn('rotation.', tr(key))
            for choice in VARIANT_CASES:
                doc, plan = plan_document(choice)
                self.assertNotIn('rotation.', render(doc, tr).text())
                for key in plan.note_keys:
                    self.assertNotIn('rotation.', tr(key))


if __name__ == '__main__':
    unittest.main()
