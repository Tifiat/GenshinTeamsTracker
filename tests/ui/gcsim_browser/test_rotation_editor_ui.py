"""Qt interaction checks with public data and no AppShell/bootstrap."""

import os
os.environ.setdefault("GTT_LANGUAGE", "ru")

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit, QLabel

from localization import set_language, tr
from run_workspace.gcsim.rotation_editor import Dialect, parse
from run_workspace.gcsim.rotation_editor.conditions import Condition
from run_workspace.gcsim.rotation_editor.editing import Selection
from run_workspace.gcsim.rotation_editor.integration import EditorEnvironment, load_environment
from run_workspace.gcsim.rotation_editor.model import action, shape
from run_workspace.gcsim.rotation_editor.options import EngineIdentity, CharacterOptions, ActionOption, ParameterOption
from run_workspace.gcsim.rotation_editor.team import TeamContext, TeamMember
from run_workspace.gcsim.rotation_editor.semantics import ScheduleChoice, analyze
from ui.gcsim_browser.rotation_editor import RotationEditorWindow
from ui.gcsim_browser.rotation_properties import ConditionControl, ScheduleControl, VariantControl


APP = QApplication.instance() or QApplication([])
set_language("ru")
DIALECT = Dialect({key: key for key in ("furina", "chasca", "bennett", "ororon")}, identity="gcsim-v2.45.0-gcsl")
NAMES = {key: tr("rotation.character." + key) for key in DIALECT.character_aliases}
OPTIONS = {key: CharacterOptions(key, EngineIdentity("fixture", "public"), tuple(ActionOption(name, False) for name in DIALECT.actions),
    (ParameterOption("aim", "bullets", "fixture"),) if key == "chasca" else (ParameterOption("skill", "hold", "fixture"),) if key == "bennett" else (), (), "fixture")
           for key in DIALECT.character_aliases}
TEAM = TeamContext("fixture:0", tuple(TeamMember(key, NAMES[key], "fixture:" + key) for key in DIALECT.character_aliases))


class RotationEditorUiTests(unittest.TestCase):
    def make_window(self, source="active furina; furina skill, dash, burst;"):
        window = RotationEditorWindow(source, DIALECT, names=NAMES, allowed_actors=tuple(NAMES), character_options=OPTIONS)
        window.show()
        APP.processEvents()
        self.addCleanup(window.close)
        return window

    def click_button(self, window, caption, panel=None):
        APP.processEvents()
        buttons = [button for button in (panel or window).findChildren(QPushButton) if button.isVisible()
                   and (button.text() == caption or button.accessibleName() == caption)]
        self.assertEqual(len(buttons), 1, caption)
        QTest.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
        APP.processEvents()

    def test_open_does_not_rewrite_import_and_cycle_option_roundtrips(self):
        source = "# import\nactive furina; for let i=0; i<4; i=i+1 { furina skill; }"
        window = self.make_window(source)
        self.assertEqual(window.session.code_text(), source)
        self.click_button(window, "Цикл из 4 ротаций")
        count = window.properties_scroll.findChildren(QLineEdit)[0]
        count.setText("3")
        self.click_button(window, tr("rotation.editor.change"))
        expected = parse("active furina; for let i=0; i<3; i=i+1 { furina skill; }", DIALECT)
        actual = parse(window.session.code_text(), DIALECT)
        self.assertEqual(shape(actual.root), shape(expected.root))
        self.assertIn("# import", window.session.code_text())
        self.click_button(window, tr("rotation.editor.undo"))
        self.assertEqual(window.session.code_text(), source)
        self.click_button(window, tr("rotation.editor.redo"))
        self.assertIn("i<3", window.session.code_text())

    def test_empty_slots_disable_apply_then_filling_produces_same_tree(self):
        window = self.make_window("active furina;")
        self.click_button(window, tr("rotation.editor.page.conditions"))
        self.click_button(window, tr("rotation.editor.add_if"))
        self.assertFalse(window.apply_button.isEnabled())
        control = window.properties_scroll.findChildren(ConditionControl)[0]
        control.kind.setCurrentIndex(control.kind.findData("energy_full"))
        control.actor.setCurrentIndex(control.actor.findData("furina"))
        self.click_button(window, tr("rotation.editor.change"))
        self.assertFalse(window.apply_button.isEnabled())
        block = window.session.current.root.get("items")[-1]
        window.select(Selection(block.get("then").node_id, "hole"))
        window.add_statement(action("furina", "burst"))
        self.assertTrue(window.apply_button.isEnabled())
        expected = parse("active furina; if .furina.energy >= .furina.energymax { furina burst; }", DIALECT)
        self.assertEqual(shape(parse(window.session.code_text(), DIALECT).root), shape(expected.root))
        spy = QSignalSpy(window.applied)
        self.click_button(window, tr("rotation.editor.apply"))
        self.assertEqual(spy.count(), 1)

    def test_character_navigation_has_back_and_action_insert(self):
        window = self.make_window()
        groups = tuple(window.command_groups.values())
        self.assertTrue(all(button.isVisible() and button.geometry().bottom() < window.commands_scroll.geometry().top()
                            for button in groups))
        self.click_button(window, tr("rotation.editor.page.characters"))
        self.click_button(window, "Часка")
        window.resize(800, 520)
        APP.processEvents()
        scrollbar = window.commands_scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(scrollbar.maximum())
        self.assertTrue(all(button.isVisible() for button in groups))
        scrollbar.setValue(0)
        self.assertTrue(any(button.text() == tr("rotation.editor.back") and button.isVisible()
                            for button in window.commands_scroll.findChildren(QPushButton)))
        self.assertFalse(any(button.text() == tr("rotation.action.skill") and button.isVisible()
                             for button in window.properties_scroll.findChildren(QPushButton)))
        self.click_button(window, tr("rotation.action.skill"), window.commands_scroll)
        self.assertIn("chasca skill", window.session.code_text())
        self.assertEqual(window._command_actor, "chasca")
        self.assertTrue(all(button.isVisible() for button in groups))
        self.click_button(window, tr("rotation.editor.back"), window.commands_scroll)
        self.assertTrue(any(button.text() == "Фурина" and button.isVisible() for button in window.commands_scroll.findChildren(QPushButton)))
        self.assertEqual(window.session.current.find(window.selection.node_id).kind, "action")

    def test_group_tabs_stay_visible_and_preserve_selection(self):
        window = self.make_window()
        selected = window.session.current.root.get("items")[1].get("actions")[0]
        window.select(Selection(selected.node_id, "action"))
        self.click_button(window, tr("rotation.editor.page.cycles"))
        self.assertTrue(window.command_groups["cycles"].isChecked())
        self.assertTrue(any(button.text() == tr("rotation.editor.add_cycle") and button.isVisible()
                            for button in window.commands_scroll.findChildren(QPushButton)))
        self.click_button(window, tr("rotation.editor.page.characters"))
        self.click_button(window, "Часка", window.commands_scroll)
        self.assertEqual(window.selection.node_id, selected.node_id)
        self.assertTrue(all(button.isVisible() for button in window.command_groups.values()))
        self.assertFalse(any(button.text() == tr("rotation.action.aim") and button.isVisible()
                             for button in window.properties_scroll.findChildren(QPushButton)))
        self.click_button(window, tr("rotation.action.aim"), window.commands_scroll)
        self.assertEqual(window.session.current.find(window.selection.node_id).kind, "action")
        self.assertIn("chasca aim", window.session.code_text())

    def test_code_typing_and_undo_use_current_draft(self):
        original = "active furina; furina skill;"
        window = self.make_window(original)
        window.tabs.setCurrentIndex(1)
        window.code.setPlainText("active chasca; chasca burst;")
        window.flush_code()
        self.assertIn("chasca burst", window.session.code_text())
        self.click_button(window, tr("rotation.editor.undo"))
        self.assertEqual(window.code.toPlainText(), original)
        window.code.setPlainText("active chasca; if")
        window.flush_code()
        self.assertFalse(window.apply_button.isEnabled())
        self.assertEqual(window.code.toPlainText(), "active chasca; if")
        window.add_statement(action("furina", "skill"))
        self.assertEqual(window.code.toPlainText(), "active chasca; if")

    def test_delete_projected_window_and_undo(self):
        source = "active furina; furina skill; furina burst; chasca skill;"
        window = self.make_window(source)
        self.click_button(window, "Фурина", window.readable_scroll)
        self.click_button(window, tr("rotation.editor.delete"))
        self.assertNotIn("furina skill", window.session.code_text())
        self.assertNotIn("furina burst", window.session.code_text())
        self.assertIn("chasca skill", window.session.code_text())
        self.click_button(window, tr("rotation.editor.undo"))
        self.assertEqual(window.session.code_text(), source)

    def test_compound_property_retains_nested_logic_and_large_schedule(self):
        value = Condition("all", children=(Condition("energy_full", "furina"),
            Condition("any", children=(Condition("on_field", "chasca"), Condition("not", children=(Condition("mode", "furina", "ousia"),))))))
        control = ConditionControl(NAMES, value)
        self.assertEqual(control.value(), value)
        schedule = ScheduleChoice(every=1000000000, first=999999999)
        self.assertEqual(ScheduleControl(schedule).value(), schedule)

    def test_unknown_profile_has_no_special_condition_buttons(self):
        window = RotationEditorWindow("active furina; furina skill;", Dialect(DIALECT.character_aliases), names=NAMES)
        self.addCleanup(window.close)
        buttons = [button.text() for button in window.findChildren(QPushButton)]
        self.assertNotIn(tr("rotation.editor.add_if"), buttons)
        self.assertNotIn(tr("rotation.editor.add_while"), buttons)

    def test_roster_limits_every_character_control_and_foreign_apply(self):
        window = RotationEditorWindow('active furina; furina skill;', DIALECT, names=NAMES,
            allowed_actors=('furina',), character_options=OPTIONS)
        window.show()
        self.addCleanup(window.close)
        self.click_button(window, tr('rotation.editor.page.characters'))
        choices = [button.text() for button in window.commands_scroll.findChildren(QPushButton) if button.isVisible()]
        self.assertIn('Фурина', choices)
        self.assertNotIn('Часка', choices)
        window.add_statement(action('chasca', 'skill'))
        self.assertNotIn('chasca skill', window.session.code_text())
        self.assertIn(tr('rotation.editor.team_outside'), window.property_status.text())
        window.tabs.setCurrentIndex(1)
        window.code.setPlainText('active chasca; chasca skill;')
        window.flush_code()
        self.assertFalse(window.apply_button.isEnabled())
        condition = ConditionControl(window.names)
        self.assertEqual([condition.actor.itemData(index) for index in range(condition.actor.count())], ['', 'furina'])

    def test_variant_is_not_offered_without_parameter_metadata(self):
        descriptor = replace(OPTIONS['chasca'], parameters=())
        window = RotationEditorWindow('active chasca; chasca aim;', DIALECT, names=NAMES,
            allowed_actors=('chasca',), character_options={'chasca': descriptor})
        window.show()
        self.addCleanup(window.close)
        selected = window.session.current.root.get('items')[1].get('actions')[0]
        window.select(Selection(selected.node_id, 'action'))
        self.assertFalse(window.properties_scroll.findChildren(VariantControl))
        self.assertTrue(any(item.text() == tr('rotation.editor.options_missing') for item in window.properties_scroll.findChildren(QLabel)))

    def test_added_action_and_delete_stay_inside_condition_and_character_page(self):
        window = self.make_window('active chasca; if .chasca.nightsoul.state {}')
        block = window.session.current.root.get('items')[1]
        window.select(Selection(block.get('then').node_id, 'branch'))
        self.click_button(window, tr('rotation.editor.page.characters'))
        self.click_button(window, 'Часка', window.commands_scroll)
        self.click_button(window, tr('rotation.action.aim'), window.commands_scroll)
        selected = window.session.current.find(window.selection.node_id)
        self.assertEqual(selected.kind, 'action')
        self.assertEqual(window._command_group, 'characters')
        self.assertEqual(window._command_actor, 'chasca')
        self.assertTrue(window.properties_scroll.findChildren(VariantControl))
        self.assertIn(block.node_id, [item.node_id for item in analyze(window.session.current).ancestors(selected.node_id)])
        self.click_button(window, tr('rotation.editor.delete'))
        self.assertEqual(window.selection.node_id, block.get('then').node_id)
        self.assertEqual(window._command_actor, 'chasca')
        self.click_button(window, tr('rotation.action.aim'), window.commands_scroll)
        self.assertEqual(window.session.current.find(window.selection.node_id).kind, 'action')

    def test_readable_tab_is_live_compact_text_of_main_code_and_applied_draft(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        self.addCleanup(browser.close)
        browser.rotation_team_provider = lambda index: TEAM
        environment = EditorEnvironment(DIALECT, EngineIdentity('fixture', 'public'), OPTIONS, True)
        with patch.object(browser, '_load_rotation_environment', return_value=environment):
            browser.rotation_tabs.setCurrentIndex(1)
            self.assertIn('Фурина: Элементальный навык, Рывок, Взрыв стихии', browser.readable_text.toPlainText())
            source = 'active bennett; bennett burst, skill;'
            browser.rotation_editor.setPlainText(source)
            browser._refresh_readable()
            self.assertIn('Беннет: Взрыв стихии, Элементальный навык', browser.readable_text.toPlainText())
            self.assertNotIn('Часка', browser.readable_text.toPlainText())
            self.assertEqual(browser.rotation_editor.toPlainText(), source)
            browser._open_rotation_editor()
            self.addCleanup(browser._rotation_window.close)
            browser._rotation_window.add_statement(action('furina', 'burst'))
            browser._rotation_window.apply()
            browser._refresh_readable()
            self.assertIn('Фурина: Взрыв стихии', browser.readable_text.toPlainText())

    def test_team_tab_and_live_membership_change_cannot_apply_old_context(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        self.addCleanup(browser.close)
        team1 = TeamContext('fixture:1', (TeamMember('chasca', 'Часка'),))
        browser.rotation_team_provider = lambda index: TEAM if index == 0 else team1
        environment = EditorEnvironment(DIALECT, EngineIdentity('fixture', 'public'), OPTIONS, True)
        with patch.object(browser, '_load_rotation_environment', return_value=environment):
            browser._open_rotation_editor()
            window = browser._rotation_window
            self.addCleanup(window.close)
            original = browser.rotation_editor.toPlainText()
            browser.team_tabs.setCurrentIndex(1)
            self.assertEqual(tuple(window.names), ('chasca',))
            window.apply()
            self.assertEqual(browser.rotation_editor.toPlainText(), original)
            browser._open_rotation_editor()
            self.assertIs(browser._rotation_window, window)
            self.assertEqual(browser._rotation_team_context.binding, team1.binding)

    def test_binding_block_survives_edit_even_when_same_characters_still_fit(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        self.addCleanup(browser.close)
        teams = [TEAM]
        browser.rotation_team_provider = lambda index: teams[0]
        environment = EditorEnvironment(DIALECT, EngineIdentity('fixture', 'public'), OPTIONS, True)
        with patch.object(browser, '_load_rotation_environment', return_value=environment):
            browser._open_rotation_editor()
            window = browser._rotation_window
            self.addCleanup(window.close)
            teams[0] = replace(TEAM, members=tuple(replace(member, constellation=1) for member in TEAM.members))
            browser.refresh_rotation_team_context()
            window.add_statement(action('furina', 'burst'))
            self.assertFalse(window.apply_button.isEnabled())
            browser._open_rotation_editor()
            self.assertTrue(window.apply_button.isEnabled())

    def test_chasca_variant_is_an_explicit_edit_with_visible_preconditions(self):
        source = "active chasca; chasca skill, aim;"
        window = self.make_window(source)
        selected = window.session.current.root.get("items")[1].get("actions")[1]
        window.select(Selection(selected.node_id, "action"))
        APP.processEvents()
        self.assertEqual(window.session.code_text(), source)
        variant = window.properties_scroll.findChildren(VariantControl)[0]
        variant.amount.setCurrentIndex(variant.amount.findData(4))
        # There are separate Apply buttons for repeat and personal variant.
        buttons = [button for button in window.properties_scroll.findChildren(QPushButton)
                   if button.isVisible() and button.text() == tr("rotation.editor.change")]
        self.assertEqual(len(buttons), 2)
        QTest.mouseClick(buttons[1], Qt.MouseButton.LeftButton)
        APP.processEvents()
        code = window.session.code_text()
        self.assertIn(".chasca.cons < 6", code)
        self.assertIn("if !(.chasca.nightsoul.state)", code)
        self.assertIn("aim[bullets=4]", code)
        self.assertTrue(window.session.current.syntax_complete)

    def test_new_cycle_uses_latest_pending_code_counter_names(self):
        window = self.make_window()
        window.tabs.setCurrentIndex(1)
        window.code.setPlainText("active furina; let _rotation=42;")
        self.click_button(window, tr("rotation.editor.page.cycles"))
        self.click_button(window, tr("rotation.editor.add_cycle"))
        loop = window.session.current.root.get("items")[-1]
        self.assertEqual(loop.get("initial").get("name").get("value"), "_rotation1")

    def test_details_toggle_does_not_overwrite_pending_code(self):
        window = self.make_window()
        window.tabs.setCurrentIndex(1)
        draft = "active chasca; chasca burst; # latest raw edit"
        window.code.setPlainText(draft)
        window.details.setChecked(True)
        self.assertEqual(window.session.code_text(), draft)
        self.assertEqual(window.code.toPlainText(), draft)

    def test_stale_property_callback_cannot_edit_new_pending_code(self):
        window = self.make_window()
        selected = window.session.current.root.get("items")[1].get("actions")[0]
        window.select(Selection(selected.node_id, "action"))
        APP.processEvents()
        buttons = [button for button in window.properties_scroll.findChildren(QPushButton)
                   if button.text() == tr("rotation.editor.change") and button.isVisible()]
        count = window.properties_scroll.findChildren(QLineEdit)[0]
        count.setText("4")
        window.tabs.setCurrentIndex(1)
        draft = "active chasca; chasca burst;"
        window.code.setPlainText(draft)
        QTest.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
        APP.processEvents()
        self.assertEqual(window.session.code_text(), draft)
        self.assertEqual(window.status.text(), tr("rotation.editor.code_updated"))

    def test_else_branch_remains_unfilled_until_explicit_action(self):
        window = self.make_window("active furina; if .furina.onfield { furina skill; }")
        block = window.session.current.root.get("items")[1]
        window.select(Selection(block.node_id, "if"))
        self.click_button(window, tr("rotation.editor.add_else"))
        self.assertIsNone(window.session.code_text())
        self.assertFalse(window.apply_button.isEnabled())
        other = window.session.current.find(block.node_id).get("otherwise")
        window.select(Selection(other.node_id, "hole"))
        window.add_statement(action("chasca", "skill"))
        self.assertIn("else", window.session.code_text())
        self.assertTrue(window.apply_button.isEnabled())

    def test_browser_opens_and_applies_but_protects_external_change(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        browser.rotation_team_provider = lambda index: TEAM
        self.addCleanup(browser.close)
        environment = EditorEnvironment(DIALECT, EngineIdentity("fixture", "public"), OPTIONS, True)
        with patch.object(browser, "_load_rotation_environment", return_value=environment):
            browser._open_rotation_editor()
            window = browser._rotation_window
            self.addCleanup(window.close)
            window.add_statement(action("bennett", "skill"))
            window.apply()
            self.assertIn("bennett skill", browser.rotation_editor.toPlainText())
            self.assertEqual(window.status.text(), tr("rotation.editor.applied"))
            browser.rotation_editor.setPlainText("active chasca; chasca burst;")
            window.add_statement(action("bennett", "burst"))
            window.apply()
            self.assertEqual(browser.rotation_editor.toPlainText(), "active chasca; chasca burst;")
            self.assertEqual(window.status.text(), tr("rotation.editor.external_change"))
            browser._open_rotation_editor()
            self.assertIs(browser._rotation_window, window)
            self.assertIn("bennett burst", window.session.code_text())

    def test_browser_does_not_apply_after_engine_changed(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        browser.rotation_team_provider = lambda index: TEAM
        self.addCleanup(browser.close)
        first = EditorEnvironment(DIALECT, EngineIdentity("fixture", "first"), OPTIONS, True)
        second = replace(first, identity=EngineIdentity("fixture", "second"))
        with patch.object(browser, "_load_rotation_environment", return_value=first):
            browser._open_rotation_editor()
        window = browser._rotation_window
        self.addCleanup(window.close)
        original = browser.rotation_editor.toPlainText()
        window.add_statement(action("bennett", "skill"))
        with patch.object(browser, "_load_rotation_environment", return_value=second):
            window.apply()
        self.assertEqual(browser.rotation_editor.toPlainText(), original)
        self.assertEqual(window.status.text(), tr("rotation.editor.engine_change"))

    def test_failed_code_flush_keeps_raw_draft_on_engine_reopen(self):
        from ui.gcsim_browser.window import GcsimBrowserWorkspace
        browser = GcsimBrowserWorkspace()
        browser.rotation_team_provider = lambda index: TEAM
        self.addCleanup(browser.close)
        first = EditorEnvironment(DIALECT, EngineIdentity("fixture", "first"), OPTIONS, True)
        second = replace(first, identity=EngineIdentity("fixture", "second"))
        with patch.object(browser, "_load_rotation_environment", return_value=first):
            browser._open_rotation_editor()
        window = browser._rotation_window
        self.addCleanup(window.close)
        window.tabs.setCurrentIndex(1)
        raw = "active chasca; chasca burst; # raw draft not accepted by parser"
        window.code.setPlainText(raw)
        with patch.object(browser, "_load_rotation_environment", return_value=second), \
             patch("run_workspace.gcsim.rotation_editor.session.parse", side_effect=ValueError("input limit")):
            browser._open_rotation_editor()
        self.assertIs(browser._rotation_window, window)
        self.assertEqual(window.code.toPlainText(), raw)
        self.assertFalse(window.apply_button.isEnabled())


class EnvironmentTests(unittest.TestCase):
    def test_folder_name_cannot_admit_audited_profile(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "gcsim-v2.45.0"
            keys = root / "pkg/core/keys"
            shortcut = root / "pkg/shortcut"
            keys.mkdir(parents=True)
            shortcut.mkdir(parents=True)
            (keys / "character.dm.go").write_text("const (\nFurina Char = iota // furina\n)\n", encoding="utf-8")
            (shortcut / "character.dm.go").write_text('var CharNameToKey = map[string]keys.Char{\n"furina": keys.Furina,\n}\n', encoding="utf-8")
            installation = SimpleNamespace(path=root, engine_id=root.name,
                manifest=SimpleNamespace(engine_tree_hash="synthetic", metadata={"upstream_repo": "genshinsim/gcsim", "upstream_ref": "v2.45.0"}))
            environment = load_environment(installation)
            self.assertFalse(environment.audited)
            self.assertEqual(environment.dialect.identity, "gcsl-syntax-v1")
            self.assertEqual(environment.identity.source_revision, "")

    def test_metadata_and_alias_change_invalidate_context_even_same_engine_id(self):
        installation = SimpleNamespace(path=Path("unused"), engine_id="same",
            manifest=SimpleNamespace(engine_tree_hash="synthetic", metadata={}))
        with patch("run_workspace.gcsim.rotation_editor.integration.source_fingerprint", return_value="narrow"), \
             patch("run_workspace.gcsim.rotation_editor.integration.load_source_dialect", return_value=Dialect({"furina": "furina"})), \
             patch("run_workspace.gcsim.rotation_editor.integration.load_local_tables", return_value=({}, {}, {})) as tables:
            first = load_environment(installation)
            tables.return_value = ({"furina": [{"ability": "skill", "invalid": True}]}, {}, {})
            second = load_environment(installation)
            self.assertNotEqual(first.identity, second.identity)


if __name__ == "__main__":
    unittest.main()
