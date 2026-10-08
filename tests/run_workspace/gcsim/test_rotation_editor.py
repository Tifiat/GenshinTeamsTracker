from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from run_workspace.gcsim.rotation_editor import CodeGenerationError, Dialect, parse, node, write
from run_workspace.gcsim.rotation_editor.model import action, conditional, loop, shape
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.session import EditorSession


ROOT = Path(__file__).resolve().parents[3]
DIALECT = Dialect({key: key for key in ("furina", "chasca", "ororon", "bennett", "xingqiu", "raiden", "xiangling", "nahida", "neuvillette")} | {"furinadefontaine": "furina"}, identity="gcsim-v2.45.0-gcsl")
NAMES = {"furina": "Фурина", "chasca": "Часка", "bennett": "Беннет"}


def translator(language: str = "ru"):
    # Public locale files only. No localization.i18n import/settings/account IO.
    values = json.loads((ROOT / "localization" / "locales" / f"{language}.json").read_text(encoding="utf-8"))
    return lambda key, **fields: values[key].format(**fields)


PUBLIC_CASES = (
    'options iteration=10 duration=90 hitlag=true frame_defaults=human; active furina; furina skill, dash, burst; chasca aim[bullets=4]:2;',
    'active bennett; bennett skill[hold=2];',
    'active furina; let x = 1 + 2 * 3; let y = (1 + 2) * 3; print(x, y);',
    'active furina; if .furina.energy >= 60 { furina burst; } else if .furina.onfield { furina skill; } else { chasca skill; }',
    'active furina; while !.furina.status.favonius-cd { furina attack; }',
    'active furina; for { wait(1); break; } for .furina.energy < 60 { furina skill; }',
    'active furina; for let i=0; i<4; i=i+1 { if is_even(i) { furina burst; continue; } chasca skill; }',
    'active furina; let i=0; for i=0; i<3; { i=i+1; }',
    'active furina; switch { case .furina.energy > 10: furina skill; fallthrough; case .stam > 20: chasca dash; default: wait(30); }',
    'active furina; switch f() { case 0: wait(30); default: wait(60); }',
    'active furina; fn rotate(a number, b map) number { let c = a + 1; furina skill; return c; } rotate(1, [flag=true]);',
    'active furina; let make = fn(a fn(number) number) fn() string { return fn() string { return "hi"; }; };',
    'active furina; let x = fn() { return 1; }() + 2;',
    'active furina; { let wait fn(number) number = fn(n) { return n; }; wait(2); } wait(3);',
    'active furina; let data map = [x=1, x=2, label_value="a\\n"]; print(data);',
    'furina char lvl=90/90 cons=0 talent=9,9,9; furina add weapon="favoniussword" refine=1 lvl=90/90; furina add set="goldentroupe" count=4; furina add stats hp=4780 atk=311.0 hydro%=0.466; active furina;',
    'active furina; energy every interval=480,720 amount=1; hurt once interval=300 amount=1,300 element=physical; target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=10000;',
    'active furina; target lvl=100 type=hilichurl[hp_mult=1,particles=2] hp=10000; furina char +params=[foo=1];',
    'active xiangling; xiangling add stats random rarity=5 sand=hp% goblet=pyro% circlet=cr;',
    'active furina; furina attack:0; chasca swap, skill; furina attack[randomparam=2]:4;',
    'active furina; let x = 10; print(x - 1, x-1, -2, .5, 3., 1<>2);',
    'active furina; energy; hurt; energy every interval=300,600 amount=1; hurt once amount=1,300 interval=400;',
    'furina char cons=0 talent=9,9,9 +params=[flag=true]; furina add weapon="favoniussword" lvl=90/90 refine=1 +params=[a=1+2]; furina add set="goldentroupe" count=4 +params=[b=2]; active furina;',
    'active furina; print(f(),rand(),randnorm(),sin(1),cos(1),asin(.5),acos(.5),type(1),is_even(2),is_target_dead(1)); set_target_pos(1,2,3); set_player_pos(0,1); set_default_target(1); set_swap_icd(30); set_particle_delay("furina",10); kill_target(1); pick_up_crystallize("any"); set_starting_verdant_dew(3); set_on_tick(fn(){return 0;}); execute_action(.keys.char.furina,.action.skill,[]);',
)


def flatten(items):
    for item in items:
        yield item
        yield from flatten(item.children)


class RotationSyntaxTests(unittest.TestCase):
    def test_setup_validation_blocks_commit_without_replacing_draft(self):
        session = EditorSession('options iteration=foo; active furina;', DIALECT)
        original = session.current
        self.assertTrue(original.syntax_complete)
        with self.assertRaisesRegex(CodeGenerationError, 'rotation.setup.value_type'):
            session.commit()
        self.assertIs(session.current, original)
        session.set_code('options iteration=10; active furina;')
        self.assertTrue(session.commit().syntax_complete)

    def test_options_validation_is_part_of_structured_commit(self):
        from run_workspace.gcsim.rotation_editor.options import ActionOption, CharacterOptions, EngineIdentity
        identity = EngineIdentity('public', 'source')
        options = CharacterOptions('chasca', identity, (ActionOption('aim', True),), (), (), 'local')
        session = EditorSession('active chasca; chasca aim;', DIALECT)
        with self.assertRaisesRegex(CodeGenerationError, 'rotation.action.invalid'):
            session.commit(character_options={'chasca': options}, expected_identity=identity)

    def test_public_forms_preserve_source_and_roundtrip(self):
        for source in PUBLIC_CASES:
            with self.subTest(source=source):
                doc = parse(source, DIALECT)
                self.assertTrue(doc.syntax_complete, doc.diagnostics)
                self.assertEqual(write(doc), source)
                normalized = parse(write(doc, preserve=False), DIALECT)
                self.assertTrue(normalized.syntax_complete, normalized.diagnostics)
                self.assertEqual(shape(doc.root), shape(normalized.root))

    def test_actual_project_public_fixture(self):
        source = (ROOT / "run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt").read_text(encoding="utf-8")
        doc = parse(source, DIALECT)
        self.assertTrue(doc.syntax_complete)
        self.assertEqual(write(doc), source)
        self.assertEqual(shape(doc.root), shape(parse(write(doc, preserve=False), DIALECT).root))

    def test_precedence_and_subtraction_spelling(self):
        doc = parse('active furina; let x = 1 + 2 * 3; let y = x-1; let z = x - 1;', DIALECT)
        x, y, z = doc.root.get("items")[1:]
        self.assertEqual(x.get("value").get("operator"), "+")
        self.assertEqual(x.get("value").get("right").get("operator"), "*")
        self.assertEqual(y.get("value").get("value"), "x-1")
        self.assertEqual(z.get("value").get("operator"), "-")

    def test_reserved_names_are_not_user_variables(self):
        for source in ('let skill=1;', 'let hp=1;', 'let pyro=1;', 'active furina; furina wait;', 'wait 10;', 'for ; ; { wait(1); }'):
            doc = parse(source, DIALECT)
            self.assertFalse(doc.syntax_complete, source)
            self.assertEqual(write(doc), source)

    def test_unknown_syntax_is_visible_and_does_not_erase_following_code(self):
        source = 'active furina; @bad; chasca skill;'
        doc = parse(source, DIALECT)
        self.assertFalse(doc.syntax_complete)
        self.assertEqual([n.kind for n in doc.root.get("items")], ["active", "unknown", "action_line"])
        text = render(doc, translator(), resolve_name=NAMES.get).text()
        self.assertIn("Неразобранный фрагмент: @bad;", text)
        self.assertIn("Часка", text)
        self.assertEqual(write(doc), source)

    def test_unfinished_code_remains_current(self):
        session = EditorSession('active furina; furina skill;', DIALECT)
        old = session.last_complete
        session.set_code('active furina; if .furina.energy > 10 {')
        self.assertFalse(session.current.syntax_complete)
        self.assertIs(session.last_complete, old)
        self.assertIn("Неразобранный", render(session.current, translator()).text())
        with self.assertRaises(CodeGenerationError):
            session.commit()

    def test_leaf_edit_changes_only_selected_source_range(self):
        source = '# title\r\nactive furina; // start\r\nchasca aim[bullets = 4]:2; # keep\r\n'
        doc = parse(source, DIALECT)
        selected = next(n for n in doc.root.walk() if n.kind == "entry" and n.get("key").get("value") == "bullets").get("value")
        edited = doc.replace(selected.node_id, node("number", value="6"))
        self.assertEqual(write(edited), source.replace("bullets = 4", "bullets = 6"))
        regenerated = parse(write(edited), DIALECT)
        self.assertEqual(shape(regenerated.root), shape(edited.root))

    def test_structural_edit_keeps_comments_and_other_statements(self):
        source = 'active furina; if 1 /*bad*/ { furina skill; }'
        # GCSIM has line comments, not block comments.
        self.assertFalse(parse(source, DIALECT).syntax_complete)
        source = 'active furina; if 1 # condition\n { furina skill; # action\n } chasca skill;'
        doc = parse(source, DIALECT)
        old = doc.root.get("items")[1]
        replacement = loop(old.get("condition"), old.get("then"))
        edited = doc.replace(old.node_id, replacement)
        text = write(edited)
        self.assertEqual(text.count("# condition"), 1)
        self.assertEqual(text.count("# action"), 1)
        self.assertTrue(text.endswith(" chasca skill;"))
        reparsed = parse(text, DIALECT)
        self.assertTrue(reparsed.syntax_complete, reparsed.diagnostics)
        self.assertEqual(shape(edited.root), shape(reparsed.root))

    def test_builder_slots_are_visible_and_block_generation(self):
        session = EditorSession('active furina; furina skill;', DIALECT)
        old = session.current.root.get("items")[1]
        session.replace(old.node_id, conditional())
        text = render(session.current, translator()).text()
        self.assertIn("Необходимо вставить условие", text)
        self.assertIn("Необходимо вставить действие", text)
        self.assertFalse(session.current.syntax_complete)
        with self.assertRaises(CodeGenerationError):
            session.commit()
        session.undo()
        self.assertEqual(write(session.current), 'active furina; furina skill;')
        with self.assertRaises(ValueError):
            action("", "skill")

    def test_structured_action_and_condition_generate_same_tree(self):
        session = EditorSession('active furina; furina skill;', DIALECT)
        previous = session.current.root.get("items")[1]
        new = conditional(node("field", path=("furina", "onfield")), node("block", items=(action("chasca", "skill"),)))
        session.replace(previous.node_id, new)
        expected = shape(session.current.root)
        committed = session.commit()
        self.assertEqual(shape(committed.root), expected)
        self.assertIn("chasca skill;", committed.source)

    def test_unicode_source_links_and_byte_offsets(self):
        doc = parse('active furina; print("Привет"); furina skill;', DIALECT)
        actor = doc.root.get("items")[-1].get("actor")
        self.assertEqual(doc.source[actor.span.start:actor.span.end], "furina")
        self.assertGreater(doc.byte_span(actor.span).start, actor.span.start)
        self.assertEqual(doc.position(actor.span)[0], 1)

    def test_list_insertion_keeps_comments_at_original_boundaries(self):
        source = 'let a = 1; // for-a\n# keep-near-b\nlet b = 2;\n'
        doc = parse(source, DIALECT)
        added = parse('let c = 3;', DIALECT).root.get("items")[0]
        items = doc.root.get("items")
        edited = doc.replace(doc.root.node_id, doc.root.changed(items=(items[0], added, items[1])))
        code = write(edited)
        self.assertEqual(code, 'let a = 1; // for-a\nlet c = 3;\n# keep-near-b\nlet b = 2;\n')
        self.assertEqual(shape(parse(code, DIALECT).root), shape(edited.root))

    def test_repaired_unknown_statement_can_be_committed(self):
        session = EditorSession('let x = ;', DIALECT)
        repaired = parse('let x = 1;', DIALECT).root.get("items")[0]
        session.replace(session.current.root.get("items")[0].node_id, repaired)
        self.assertEqual(session.commit().source, 'let x = 1;')

    def test_unicode_decimal_digits_match_go_letter_and_digit_categories(self):
        self.assertFalse(parse('let x²=1;', DIALECT).syntax_complete)
        self.assertTrue(parse('let x٢=1;', DIALECT).syntax_complete)
        self.assertFalse(parse('active furina; furina attack:' + '9' * 5000 + ';', DIALECT).syntax_complete)

    def test_case_body_has_no_duplicate_colon_after_structural_edit(self):
        doc = parse('active furina; switch 1 { case 1: furina skill; }', DIALECT)
        case = next(n for n in doc.root.walk() if n.kind == "case")
        changed = doc.replace(case.node_id, case.changed(condition=None))
        self.assertTrue(parse(write(changed), DIALECT).syntax_complete)

    def test_core_import_does_not_load_accounts_or_settings(self):
        result = subprocess.run([sys.executable, "-B", "-c", "import sys; import run_workspace.gcsim.rotation_editor; assert 'run_workspace.app_settings' not in sys.modules; assert 'localization.i18n' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


class RotationReadableTests(unittest.TestCase):
    def read(self, source, language="ru"):
        return render(parse(source, DIALECT), translator(language), resolve_name=NAMES.get)

    def test_switch_forms_share_window_and_source_stays_distinct(self):
        implicit = 'active furina; furina skill; chasca skill;'
        explicit = 'active furina; furina skill; chasca swap; chasca skill;'
        left, right = self.read(implicit), self.read(explicit)
        self.assertEqual(left.text(), right.text())
        self.assertEqual([n.actor_key for n in left.items], ["furina", "chasca"])
        self.assertEqual(write(parse(explicit, DIALECT)), explicit)
        self.assertNotIn("становится актив", left.text())

    def test_last_global_active_applies_before_first_action(self):
        value = self.read('active furina; wait(30); active chasca;')
        self.assertEqual(value.items[0].actor_key, "chasca")

    def test_alias_and_condition_owner_do_not_create_extra_windows(self):
        value = self.read('active furina; furina skill; furinadefontaine burst; if .chasca.bullet1 == .keys.element.pyro { furina attack; }')
        windows = [n for n in flatten(value.items) if n.kind == "window"]
        self.assertTrue(windows)
        self.assertEqual({n.actor_key for n in windows}, {"furina"})
        self.assertIn("Элемент следующей пули №1 (Часка)", value.text())

    def test_branch_actor_is_not_invented_for_following_wait(self):
        value = self.read('active furina; if rand() > .5 { furina skill; } else { chasca skill; } wait(10);')
        self.assertEqual(value.items[-1].kind, "expression_stmt")
        self.assertIsNone(value.items[-1].actor_key)
        self.assertIn("Ждать 10 кадров", value.items[-1].text)

    def test_repeat_zero_does_not_activate_target(self):
        value = self.read('active furina; chasca attack:0; wait(10);')
        self.assertEqual({n.actor_key for n in flatten(value.items) if n.kind == "window"}, {"furina"})
        self.assertIn("команда не выполняется", value.text())
        padded = self.read('active furina; chasca attack:' + '0' * 5000 + ';')
        self.assertIn('команда не выполняется', padded.text())

    def test_hold_means_level_for_bennett_and_unknown_remains_explicit(self):
        text = self.read('active bennett; bennett skill[hold=2]; nahida skill[hold=2];').text()
        self.assertIn("Удержание второго уровня", text)
        self.assertIn("hold: 2", text)

    def test_favonius_is_owning_character_cooldown_not_new_proc(self):
        text = self.read('active furina; while !.furina.status.favonius-cd { furina attack; }').text()
        self.assertIn("Перезарядка эффекта Фавония (Фурина), осталось кадров", text)
        self.assertIn("проверка перед каждой итерацией", text)
        self.assertNotIn("обязательно", text)

    def test_builtin_shadowing_and_override_are_not_translated_as_wait_or_combat(self):
        text = self.read('active furina; wait = fn(n) { return n; }; wait(30); execute_action = fn(a,b,c) { return 0; }; chasca skill;').text()
        self.assertIn("Вызвать wait(30)", text)
        self.assertNotIn("Ждать 30", text)
        self.assertIn("изменённый обработчик", text)
        self.assertFalse(any(n.kind == "window" and n.actor_key == "chasca" for n in flatten(self.read('active furina; execute_action = fn(a,b,c) { return 0; }; chasca skill;').items)))

    def test_function_parameter_shadows_builtin_only_in_its_scope(self):
        text = self.read('active furina; fn run(wait fn(number) number) { wait(10); } wait(20);').text()
        self.assertIn("Вызвать wait(10)", text)
        self.assertIn("Ждать 20", text)

    def test_anonymous_function_body_is_visible(self):
        text = self.read('active furina; let make = fn() { chasca skill; return 1; };').text()
        self.assertIn("Часка", text)
        self.assertIn("Элементальный навык", text)
        self.assertIn("Вернуть 1", text)

    def test_nested_anonymous_body_is_not_duplicated(self):
        text = self.read('active furina; let make = fn() { return fn() { chasca skill; return 1; }; };').text()
        self.assertEqual(text.count("Элементальный навык"), 1)

    def test_direct_control_marks_unreachable_tail_in_all_locales(self):
        source = 'active furina; while 1 { break; chasca skill; }'
        for language in ('ru', 'en', 'pt-br'):
            result = self.read(source, language)
            tail = [item for item in flatten(result.items) if item.kind == 'unreachable']
            self.assertEqual(len(tail), 1)
            self.assertEqual(tail[0].children[0].actor_key, 'chasca')

    def test_both_terminating_if_branches_mark_tail_without_assuming_one_branch(self):
        source = 'active furina; fn pick(x) { if x { return 1; } else { return 2; } chasca skill; }'
        result = self.read(source)
        self.assertEqual(len([item for item in flatten(result.items) if item.kind == 'unreachable']), 1)
        one_branch = self.read('active furina; fn pick(x) { if x { return 1; } chasca skill; }')
        self.assertFalse(any(item.kind == 'unreachable' for item in flatten(one_branch.items)))

    def test_duplicate_parameter_marks_overwritten_value(self):
        text = self.read('active bennett; bennett skill[hold=1,hold=2];').text()
        self.assertIn("первого уровня — заменено последующей записью", text)
        self.assertIn("второго уровня", text)

    def test_missing_active_has_diagnostic_without_default_selection(self):
        value = self.read('wait(10);')
        self.assertEqual(value.items[0].kind, "diagnostic")
        self.assertNotIn("window", [n.kind for n in value.items])

    def test_all_project_locales_support_readable_keys(self):
        source = 'active bennett; bennett skill[hold=2]; if .bennett.energy < 60 { wait(30); }'
        for language, expected in (("ru", "Элементальный навык"), ("en", "Elemental skill"), ("pt-br", "Habilidade elemental")):
            with self.subTest(language=language):
                text = self.read(source, language).text()
                self.assertIn(expected, text)
                self.assertNotIn("rotation.", text)


if __name__ == "__main__":
    unittest.main()
