"""Actual Play/dispatch/clock path with disposable source-shaped rules."""
import unittest

from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.draft_options import DraftMatchOptions
from tests.run_workspace.pvp.test_abyss_other_flows import ASCEND, FRENCH, REVERSE
from tests.ui.pvp_browser.test_preban_clock_flow import PrebanClockFlowTest
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


class OtherFlowIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PrebanClockFlowTest.setUpClass()

    def setUp(self):
        self.fixture = PrebanClockFlowTest('test_timer_can_be_disabled_and_bad_penalties_block_start')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.workspace = self.fixture.workspace

    def set_flow(self, flow, *, french=False, untimed=False):
        data = self.fixture.rules.to_dict()
        data['phase_picks']['flow'] = [{'type': kind, 'player': f'player{seat}'} for kind,seat in flow]
        if french:
            data['source']['cost_system'] = 'FRENCH_COST'
        if untimed:
            data['phase_picks']['pick_time'] = 0
        self.fixture.rules = AbyssRuleset.from_dict(data)
        self.fixture.save_rules()

    def advance(self, count):
        for _ in range(count):
            self.assertTrue(self.workspace.apply_draft_card_click(self.fixture.action()))

    def test_french_setup_explains_cap_and_full_dispatch_reaches_assignment(self):
        self.set_flow(FRENCH, french=True)
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.assertIn('French Cost', panel.preban_preview_label.text())
        self.assertTrue(panel.start_button.isEnabled())
        panel.start_button.click()
        self.advance(22)
        self.assertTrue(self.workspace.continue_to_assignment())

    def test_mirror_dispatch_and_auto_expiry_add_exactly_one_actor_card(self):
        self.set_flow(ASCEND)
        self.assertTrue(self.workspace.start_local_draft('local', 'second',
            match_options=DraftMatchOptions(pick_time_ms=1000, reserve_time_ms=0)))
        self.advance(20)
        board = self.workspace.draft_board_dict()
        self.assertEqual(board['current_requirement']['expected_action_type'], 'mirror_character')
        self.fixture.now[0] = 1.1
        self.workspace._tick_draft_clock()
        state = self.workspace.active_draft_session.controller.session_state
        self.assertEqual(len(state.player_1_picked_character_ids), 8)
        self.assertEqual(len(state.player_2_picked_character_ids), 7)
        self.assertEqual(state.accepted_actions[-1].action_type, 'mirror_character')
        self.workspace._tick_draft_clock()
        self.assertEqual(len(self.workspace.active_draft_session.controller.accepted_actions), 21)
        self.advance(1)
        self.assertTrue(self.workspace.continue_to_assignment())

    def test_reverse_source_has_no_preparation_and_untimed_default(self):
        self.set_flow(REVERSE, untimed=True)
        panel = PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.assertFalse(panel.timer_enabled_check.isChecked())
        panel.start_button.click()
        self.assertFalse(self.workspace._draft_tick_timer.isActive())
        self.advance(4)
        self.assertEqual(self.workspace.draft_board_dict()['current_requirement']['expected_action_type'],
                         'immune_character')
        self.advance(18)
        self.assertTrue(self.workspace.continue_to_assignment())
