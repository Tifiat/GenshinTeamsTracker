"""User operations are checked against independent expected GCSL ordering."""

import unittest

from run_workspace.gcsim.rotation_editor import parse, write
from run_workspace.gcsim.rotation_editor.conditions import Condition, make_if, set_condition
from run_workspace.gcsim.rotation_editor.editing import Selection, insert, move, remove, wrap
from run_workspace.gcsim.rotation_editor.model import action, node, shape
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.session import EditorSession
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, translator


class StructuralEditingTests(unittest.TestCase):
    def check_code(self, document, expected):
        actual = parse(write(document), DIALECT)
        self.assertTrue(actual.syntax_complete, actual.diagnostics)
        self.assertEqual(shape(actual.root), shape(parse(expected, DIALECT).root))

    def test_window_delete_removes_all_its_lines_and_keeps_neighbor(self):
        document = parse("active furina; furina skill; furina dash, burst; chasca skill;", DIALECT)
        window = render(document, translator()).items[0]
        self.assertEqual(window.kind, "window")
        changed = remove(document, Selection.from_view(window))
        self.check_code(changed, "active furina; chasca skill;")

    def test_grouped_window_includes_nested_condition_and_hidden_swap(self):
        document = parse("active furina; furina swap; furina skill; if .furina.onfield { furina burst; } chasca skill;", DIALECT)
        window = render(document, translator()).items[0]
        self.check_code(remove(document, Selection.from_view(window)), "active furina; chasca skill;")

    def test_insert_after_middle_action_keeps_order_and_comment(self):
        document = parse("active furina; furina skill, dash, burst; # retain\nchasca skill;", DIALECT)
        dash = document.root.get("items")[1].get("actions")[1]
        changed = insert(document, Selection(dash.node_id), action("bennett", "burst"))
        self.check_code(changed, "active furina; furina skill, dash; bennett burst; furina burst; chasca skill;")
        self.assertIn("# retain", write(changed))

    def test_wrap_single_action_keeps_both_neighbors(self):
        document = parse("active furina; furina skill, dash, burst;", DIALECT)
        dash = document.root.get("items")[1].get("actions")[1]
        changed = wrap(document, Selection(dash.node_id), make_if(document, Condition("energy_full", "furina")))
        self.check_code(changed, "active furina; furina skill; if .furina.energy >= .furina.energymax { furina dash; } furina burst;")

    def test_wrap_entire_window_uses_projected_range(self):
        document = parse("active furina; furina skill; furina burst; chasca skill;", DIALECT)
        window = render(document, translator()).items[0]
        changed = wrap(document, Selection.from_view(window), make_if(document, Condition("energy_full", "furina")))
        self.check_code(changed, "active furina; if .furina.energy >= .furina.energymax { furina skill; furina burst; } chasca skill;")

    def test_last_action_delete_removes_empty_line(self):
        document = parse("active furina; furina skill; chasca burst;", DIALECT)
        selected = document.root.get("items")[1].get("actions")[0]
        self.check_code(remove(document, Selection(selected.node_id)), "active furina; chasca burst;")

    def test_insert_into_body_hole_and_undo_redo(self):
        session = EditorSession("active furina;", DIALECT)
        block = make_if(session.current)
        session.edit_structure(insert, None, block)
        self.assertIsNone(session.code_text())
        session.edit_structure(insert, Selection(block.get("then").node_id), action("furina", "burst"))
        session.edit_option(block.node_id, "condition", Condition("energy_full", "furina"))
        code = session.code_text()
        session.undo()
        self.assertIsNone(session.code_text())
        session.redo()
        self.assertEqual(session.code_text(), code)
        self.assertTrue(session.commit().syntax_complete)

    def test_action_reorder_and_new_edit_clears_redo(self):
        session = EditorSession("active furina; furina skill, dash, burst;", DIALECT)
        dash = session.current.root.get("items")[1].get("actions")[1]
        session.edit_structure(move, Selection(dash.node_id), -1)
        self.check_code(session.current, "active furina; furina dash, skill, burst;")
        session.undo()
        session.set_code("active chasca; chasca skill;")
        self.assertFalse(session.can_redo)

    def test_clear_branch_retains_condition(self):
        document = parse("active furina; if .furina.onfield { furina skill; } else { chasca skill; }", DIALECT)
        branch = document.root.get("items")[1].get("then")
        self.check_code(remove(document, Selection(branch.node_id)), "active furina; if .furina.onfield {} else { chasca skill; }")

    def test_remove_condition_keeps_both_branches_in_order(self):
        document = parse("active furina; furina dash; if .furina.onfield { furina skill; furina burst; } else { chasca skill; } chasca burst;", DIALECT)
        condition = document.root.get("items")[2]
        self.check_code(remove(document, Selection(condition.node_id)),
                        "active furina; furina dash; furina skill; furina burst; chasca skill; chasca burst;")

    def test_remove_outer_condition_keeps_nested_condition(self):
        document = parse("active furina; if .furina.onfield { if .furina.energy > 60 { furina burst; } } else { chasca skill; }", DIALECT)
        outer = document.root.get("items")[1]
        self.check_code(remove(document, Selection(outer.node_id)),
                        "active furina; if .furina.energy > 60 { furina burst; } chasca skill;")

    def test_remove_simple_loop_keeps_body_and_undo_roundtrip(self):
        session = EditorSession("active furina; while .furina.energy < 60 { furina skill; furina dash; } chasca burst;", DIALECT)
        cycle = session.current.root.get("items")[1]
        session.edit_structure(remove, Selection(cycle.node_id))
        self.check_code(session.current, "active furina; furina skill; furina dash; chasca burst;")
        changed_code = session.code_text()
        session.undo()
        self.check_code(session.current, "active furina; while .furina.energy < 60 { furina skill; furina dash; } chasca burst;")
        session.redo()
        self.assertEqual(session.code_text(), changed_code)
        self.assertTrue(session.commit().syntax_complete)

    def test_remove_plain_for_loop_keeps_actions(self):
        document = parse("active furina; for .furina.energy < 60 { furina skill; } chasca burst;", DIALECT)
        cycle = document.root.get("items")[1]
        self.check_code(remove(document, Selection(cycle.node_id)), "active furina; furina skill; chasca burst;")

    def test_remove_counted_or_controlled_loop_rejects_unsafe_unwrap(self):
        counted = parse("active furina; for let i=0; i<4; i=i+1 { furina attack:i; }", DIALECT)
        cycle = counted.root.get("items")[1]
        with self.assertRaisesRegex(ValueError, "rotation.remove.counter"):
            remove(counted, Selection(cycle.node_id))
        controlled = parse("active furina; for { furina skill; break; }", DIALECT)
        cycle = controlled.root.get("items")[1]
        with self.assertRaisesRegex(ValueError, "rotation.remove.control"):
            remove(controlled, Selection(cycle.node_id))
        scoped = parse("active furina; if .furina.onfield { let i=1; furina skill; }", DIALECT)
        condition = scoped.root.get("items")[1]
        with self.assertRaisesRegex(ValueError, "rotation.remove.scope"):
            remove(scoped, Selection(condition.node_id))

    def test_remove_counted_loop_without_counter_dependency_keeps_actions(self):
        document = parse("active furina; for let i=0; i<4; i=i+1 { furina skill, burst; }", DIALECT)
        cycle = document.root.get("items")[1]
        self.check_code(remove(document, Selection(cycle.node_id)), "active furina; furina skill, burst;")

    def test_window_delete_still_removes_actions_inside_condition(self):
        document = parse("active furina; furina skill; if .furina.onfield { furina burst; } chasca skill;", DIALECT)
        window = render(document, translator()).items[0]
        self.check_code(remove(document, Selection.from_view(window)), "active furina; chasca skill;")


if __name__ == "__main__":
    unittest.main()
