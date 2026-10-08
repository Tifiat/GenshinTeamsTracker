from pathlib import Path
import unittest

from run_workspace.gcsim.rotation_editor import CodeGenerationError, node, parse, write
from run_workspace.gcsim.rotation_editor.context import apply_context_edit, context_for
from run_workspace.gcsim.rotation_editor.model import action, shape
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.semantics import ScheduleChoice, analyze, make_cycle, make_schedule, set_cycle_count, set_schedule
from run_workspace.gcsim.rotation_editor.session import EditorSession
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, NAMES, ROOT, flatten, translator


def document(body, start=0, end=4, counter='i', operator='<'):
    return parse(f'active furina; for let {counter}={start}; {counter}{operator}{end}; {counter}={counter}+1 {{ {body} }}', DIALECT)


class RotationMeaningTests(unittest.TestCase):
    def test_public_example_is_human_blocks_and_preserves_exact_source(self):
        source = (ROOT / 'run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt').read_text(encoding='utf-8')
        parsed = parse(source, DIALECT)
        result = render(parsed, translator(), resolve_name=NAMES.get)
        text = result.text()
        self.assertIn('Цикл из 4 ротаций', text)
        self.assertEqual(text.count('В каждой нечётной ротации'), 2)
        for technical in ('i <', 'is_even', 'Создать переменную', 'После каждой итерации', 'Настройки:'):
            self.assertNotIn(technical, text)
        self.assertEqual(write(parsed), source)
        self.assertEqual(len(result.details), 3)
        chasca = next(item for item in flatten(result.items) if item.kind == 'window' and item.actor_key == 'chasca')
        self.assertEqual(chasca.children[-1].kind, 'schedule')
        self.assertEqual(chasca.children[-1].children[0].text, 'Взрыв стихии')

    def test_equivalent_counts_and_variable_names(self):
        for args in ((0, 4, '<'), (1, 4, '<='), (3, 7, '<')):
            parsed = document('furina skill;', start=args[0], end=args[1], operator=args[2], counter='rotation_count')
            self.assertEqual(next(iter(analyze(parsed).cycles.values())).count, 4)

    def test_mutation_shadowing_callbacks_and_custom_calls_are_not_exact_cycles(self):
        bodies = ('i=i+1; furina skill;', 'let i=2; furina skill;', 'let change=fn(){i=3;}; change();',
                  'custom(); furina skill;', 'set_on_tick(fn(){i=3;}); wait(1);', 'return 1;')
        for body in bodies:
            parsed = document(body)
            self.assertFalse(analyze(parsed).cycles, body)
            self.assertIn('Повторение по особому правилу', render(parsed, translator()).text())
            self.assertIn('for let i', context_for(parsed, parsed.root.get('items')[1].node_id).source)
        assigned = parse('execute_action=fn(a,b,c){return 0;}; ' + document('furina skill;').source, DIALECT)
        self.assertFalse(analyze(assigned).cycles)

    def test_break_and_continue_are_distinct(self):
        direct = document('if .stam < 1 { break; } furina skill;')
        self.assertTrue(next(iter(analyze(direct).cycles.values())).may_break)
        self.assertIn('До 4 ротаций', render(direct, translator()).text())
        nested = document('while 1 { break; } continue;')
        self.assertFalse(next(iter(analyze(nested).cycles.values())).may_break)
        self.assertIn('Цикл из 4 ротаций', render(nested, translator()).text())

    def test_parity_uses_human_one_based_ordinals(self):
        for start, test, expected in ((0, 'is_even(i)', (1, 3)), (0, 'is_even(i+1)', (2, 4)),
                                      (0, '!is_even(i)', (2, 4)), (1, 'is_even(i)', (2, 4)),
                                      (1, '!is_even(i)', (1, 3))):
            with self.subTest(start=start, test=test):
                parsed = document(f'if {test} {{ furina skill; }}', start=start, end=start+4)
                choice = next(iter(analyze(parsed).schedules.values())).choice
                self.assertEqual(tuple(i for i in range(1, 5) if choice.includes(i)), expected)

    def test_shadowed_parity_function_is_not_a_schedule(self):
        parsed = parse('let is_even=fn(n){return true;}; ' + document('if is_even(i) { furina skill; }').source, DIALECT)
        self.assertFalse(analyze(parsed).schedules)

    def test_schedule_large_intermediate_values_keep_detailed_condition(self):
        parsed = document('if i+5==9007199254740990 { furina skill; }', start=9007199254740988, end=9007199254740989)
        self.assertTrue(analyze(parsed).cycles)
        self.assertFalse(analyze(parsed).schedules)
        cancelled = document('if is_even(i+9007199254740990-9007199254740990) { furina skill; }')
        self.assertFalse(analyze(cancelled).schedules)

    def test_switch_default_break_may_exit_enclosing_loop(self):
        default = document('switch i { case 0: furina skill; default: break; }')
        self.assertTrue(next(iter(analyze(default).cycles.values())).may_break)
        case = document('switch i { case 0: break; default: furina skill; }')
        self.assertFalse(next(iter(analyze(case).cycles.values())).may_break)

    def test_unbounded_return_keeps_detailed_loop(self):
        parsed = parse('fn run() number { for { return 1; } }', DIALECT)
        self.assertFalse(analyze(parsed).cycles)

    def test_selected_numbers_and_otherwise_keep_source(self):
        parsed = document('if i==0 || i==3 { furina skill; } else { chasca skill; }')
        meaning = analyze(parsed)
        schedule = next(iter(meaning.schedules.values()))
        self.assertEqual(schedule.choice.positions, (1, 4))
        edited = set_schedule(parsed, schedule.node_id, ScheduleChoice('selected', positions=(2, 3)))
        self.assertIn('В ротациях: 2, 3', render(edited, translator()).text())
        self.assertIn('В остальных ротациях', render(edited, translator()).text())
        self.assertIn('else { chasca skill; }', write(edited))

    def test_schedule_reference_stays_bound_to_outer_cycle(self):
        parsed = document('for let j=1; j<=2; j=j+1 { if is_even(i) { furina skill; } }')
        meaning = analyze(parsed)
        cycles = list(meaning.cycles.values())
        schedule = next(iter(meaning.schedules.values()))
        self.assertEqual(schedule.cycle_id, cycles[0].node_id)
        self.assertIn('внешнего цикла', render(parsed, translator()).text())
        self.assertEqual(context_for(parsed, schedule.node_id).cycle_id, cycles[0].node_id)

    def test_unknown_inner_call_does_not_invent_outer_binding(self):
        parsed = document('for let j=1; j<=2; j=j+1 { custom(); } if is_even(i) { furina skill; }')
        self.assertFalse(analyze(parsed).cycles)
        self.assertFalse(analyze(parsed).schedules)

    def test_count_edit_changes_only_bound_and_retains_comments(self):
        source = 'active furina; for let i=0; i < 4; i=i+1 { # body\n if is_even(i) { furina skill; } } # tail\n'
        session = EditorSession(source, DIALECT)
        cycle = next(iter(analyze(session.current).cycles.values()))
        session.edit_option(cycle.node_id, 'count', 6)
        self.assertEqual(session.code_text(), source.replace('i < 4', 'i < 6'))
        self.assertEqual(next(iter(analyze(session.commit()).cycles.values())).count, 6)
        self.assertEqual(session.undo().source, source)

    def test_count_edit_cannot_silently_drop_selected_rotation(self):
        parsed = document('if i==3 { furina skill; }')
        cycle = next(iter(analyze(parsed).cycles.values()))
        with self.assertRaisesRegex(ValueError, 'outside'):
            set_cycle_count(parsed, cycle.node_id, 3)
        self.assertEqual(next(iter(analyze(parsed).cycles.values())).count, 4)

    def test_generated_cycle_and_schedules_roundtrip_through_same_recognizer(self):
        empty = parse('active furina;', DIALECT)
        cycle_node = make_cycle(empty, 4, node('block', items=(action('furina', 'skill'),)))
        built = empty.replace(empty.root.node_id, empty.root.changed(items=empty.root.get('items') + (cycle_node,)))
        cycle = next(iter(analyze(built).cycles.values()))
        for choice in (ScheduleChoice(), ScheduleChoice(every=2, first=2), ScheduleChoice(every=3, first=1), ScheduleChoice('selected', positions=(1, 4))):
            with self.subTest(choice=choice):
                scheduled = make_schedule(built, cycle.node_id, choice, node('block', items=(action('furina', 'burst'),)))
                changed = built.replace(cycle.body_id, node('block', items=(scheduled,)))
                code = write(changed)
                reparsed = parse(code, DIALECT)
                self.assertTrue(reparsed.syntax_complete, reparsed.diagnostics)
                self.assertEqual(shape(changed.root), shape(reparsed.root))
                self.assertEqual(next(iter(analyze(reparsed).schedules.values())).choice, choice)
                self.assertNotIn('%', code)

    def test_generated_counter_avoids_capture_in_document_and_body(self):
        parsed = parse('let _rotation=7;', DIALECT)
        body = node('block', items=(parse('let _rotation1=5;', DIALECT).root.get('items')[0],))
        self.assertEqual(make_cycle(parsed, 4, body).get('initial').get('name').get('value'), '_rotation2')

    def test_draft_has_required_action_slot(self):
        parsed = parse('active furina;', DIALECT)
        cycle = make_cycle(parsed, 4)
        draft = parsed.replace(parsed.root.node_id, parsed.root.changed(items=(cycle,)))
        with self.assertRaises(CodeGenerationError):
            write(draft)
        self.assertIn('Необходимо вставить действие', render(draft, translator()).text())

    def test_infinite_and_zero_cycles_have_plain_names(self):
        for source in ('for { furina skill; }', 'while 1 { furina skill; }'):
            parsed = parse('active furina; ' + source, DIALECT)
            self.assertIn('Повторять до конца симуляции', render(parsed, translator()).text())
        self.assertIn('Этот цикл не выполняется', render(document('furina skill;', start=4, end=4), translator()).text())

    def test_same_actor_schedule_is_inside_its_window_but_switching_branch_is_not(self):
        same = render(document('chasca skill; if is_even(i) { chasca burst; }'), translator())
        window = next(item for item in flatten(same.items) if item.kind == 'window')
        self.assertEqual(window.children[-1].kind, 'schedule')
        switched = render(document('chasca skill; if is_even(i) { furina skill; chasca burst; }'), translator())
        cycle = switched.items[0]
        self.assertEqual([item.kind for item in cycle.children], ['window', 'schedule'])

    def test_context_properties_are_for_selected_kind(self):
        parsed = document('if is_even(i) { chasca aim[bullets=4]:2; }')
        meaning = analyze(parsed)
        cycle, schedule = next(iter(meaning.cycles.values())), next(iter(meaning.schedules.values()))
        act = next(item for item in parsed.root.walk() if item.kind == 'action')
        self.assertEqual(context_for(parsed, cycle.node_id).properties[0].value, 4)
        self.assertEqual(context_for(parsed, schedule.node_id).kind, 'schedule')
        context = context_for(parsed, act.node_id)
        self.assertEqual(context.actor_key, 'chasca')
        self.assertEqual(context.cycle_id, cycle.node_id)
        self.assertEqual(context.properties[0].value, 2)
        self.assertEqual(context.properties[1].key, 'parameter.bullets')
        edited = apply_context_edit(parsed, act.node_id, 'repeat', 3)
        self.assertIn('aim[bullets=4]:3;', write(edited))
        edited = apply_context_edit(parsed, act.node_id, 'repeat', 2**63 - 1)
        self.assertEqual(context_for(edited, act.node_id).properties[0].value, 2**63 - 1)

    def test_all_three_locales_render_new_blocks(self):
        parsed = document('if is_even(i+1) { furina burst; }')
        for language in ('ru', 'en', 'pt-br'):
            self.assertNotIn('rotation.', render(parsed, translator(language)).text())


if __name__ == '__main__':
    unittest.main()
