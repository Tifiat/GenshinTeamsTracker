"""Source-shaped Ascend/Reverse/French flows; only synthetic rosters."""
from dataclasses import replace
import unittest

from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.abyss_match_rules import calculate_abyss_prebans, validate_abyss_match_pair
from run_workspace.pvp.free_draft_board import validate_free_draft_board_projection_dict
from run_workspace.pvp.free_draft_controller import FreeDraftController, FreeDraftControllerActionRejected
from run_workspace.pvp.schedule import ACTION_MIRROR_CHARACTER
from tests.run_workspace.pvp.test_abyss_match_rules import _rules, _deck


ASCEND = [('BAN',0),('BAN',1),('BAN',0),('BAN',1),('PICK',0),('PICK',1),
          ('PICK',1),('PICK',0),('PICK',0),('PICK',1),('PICK',1),('PICK',0),
          ('BAN',1),('BAN',0),('PICK',1),('PICK',0),('PICK',0),('PICK',1),
          ('PICK',1),('PICK',0),('MIRROR',0),('MIRROR',1)]
FRENCH = [('BAN',0),('BAN',1),('BAN',0),('BAN',1),('PICK',0),('PICK',1),
          ('PICK',1),('PICK',0),('PICK',0),('PICK',1),('PICK',0),('PICK',1),
          ('BAN',1),('BAN',0),('PICK',1),('PICK',0),('PICK',0),('PICK',1),
          ('PICK',1),('PICK',0),('PICK',0),('PICK',1)]
REVERSE = [('BAN',0),('BAN',1),('BAN',0),('BAN',1),('IMMUNE',0),('IMMUNE',1),
           ('PICK',1),('PICK',0),('PICK',0),('PICK',1),('PICK',0),('PICK',1),
           ('BAN',1),('BAN',0),('IMMUNE',1),('IMMUNE',0),('PICK',0),('PICK',1),
           ('PICK',1),('PICK',0),('PICK',0),('PICK',1)]


def flow_rules(flow, *, french=False, absolute=False):
    data = _rules().to_dict()
    data['phase_picks']['flow'] = [{'type': kind, 'player': f'player{seat}'} for kind,seat in flow]
    if absolute:
        data['phase_picks']['absolute_immune'] = [data['characters'][0]['source_id']]
    if french:
        data['source']['cost_system'] = 'FRENCH_COST'
    return AbyssRuleset.from_dict(data)


class OtherAbyssFlowsTest(unittest.TestCase):
    def assert_board(self, controller):
        self.assertEqual(validate_free_draft_board_projection_dict(controller.to_board_dict()), ())

    def advance(self, controller, count):
        for _ in range(count):
            target = controller.get_legal_targets()[0].character_id
            controller.apply_current_action(target)
            self.assert_board(controller)

    def test_mirror_can_copy_opponent_pick_for_actor_only(self):
        rules = flow_rules(ASCEND)
        controller = FreeDraftController.from_abyss_decks(_deck(rules), _deck(rules), rules)
        self.assertTrue(controller.state.setup_ready)
        self.assertTrue(controller.state.draft_system.mirror_supported)
        self.advance(controller, 20)
        state = controller.session_state
        self.assertEqual(state.current_requirement.action_type, ACTION_MIRROR_CHARACTER)
        opponent_pick = state.player_2_picked_character_ids[0]
        legal = {row.character_id for row in controller.get_legal_targets()}
        self.assertIn(opponent_pick, legal)
        pool_row = next(row for row in controller.to_board_dict()['unified_pool']['entries']
                        if row['character_id'] == opponent_pick)
        self.assertEqual(pool_row['zone'], 'pool')
        self.assertEqual(pool_row['action']['type'], ACTION_MIRROR_CHARACTER)
        controller.apply_current_action(opponent_pick)
        self.assertEqual(len(controller.session_state.player_1_picked_character_ids), 8)
        self.assertEqual(len(controller.session_state.player_2_picked_character_ids), 7)
        own_previous = state.player_1_picked_character_ids[0]
        controller.apply_current_action(own_previous)
        self.assertTrue(controller.session_state.is_complete)
        self.assert_board(controller)
        self.assertEqual(controller.to_board_dict()['progress']['per_seat']['player_2']['expected_picks'], 8)
        self.assertEqual(controller._replay_state_hash(), controller.session_state.state_hash())

    def test_mirror_can_take_unpicked_own_card_but_cannot_repeat_mirror(self):
        rules = flow_rules(ASCEND)
        controller = FreeDraftController.from_abyss_decks(_deck(rules), _deck(rules), rules)
        self.advance(controller, 20)
        previous = set(controller.session_state.player_1_picked_character_ids
                       + controller.session_state.player_2_picked_character_ids)
        target = next(row.character_id for row in controller.get_legal_targets()
                      if row.character_id not in previous)
        controller.apply_current_action(target)
        self.assertNotIn(target, controller.session_state.player_2_picked_character_ids)
        with self.assertRaises(FreeDraftControllerActionRejected):
            controller.apply_current_action(target)
        self.advance(controller, 1)
        self.assertTrue(controller.session_state.is_complete)

    def test_reverse_and_french_do_not_require_shared_preparation_rosters(self):
        for flow, french in ((REVERSE,False), (FRENCH,True)):
            with self.subTest(french=french):
                rules = flow_rules(flow, french=french)
                base = _deck(rules)
                left = replace(base, characters=base.characters[:12])
                right = replace(base, characters=base.characters[12:])
                self.assertTrue(validate_abyss_match_pair(left, right, rules).ready)
                controller = FreeDraftController.from_abyss_decks(left, right, rules)
                self.assertTrue(controller.state.setup_ready)
                self.advance(controller, 22)
                self.assertTrue(controller.session_state.is_complete)
                self.assertEqual(len(controller.session_state.player_1_picked_character_ids), 8)
                self.assertEqual(len(controller.session_state.player_2_picked_character_ids), 8)

    def test_reverse_absolute_immune_is_unbannable_and_can_be_used_once_by_each_seat(self):
        rules = flow_rules(REVERSE, absolute=True)
        controller = FreeDraftController.from_abyss_decks(_deck(rules), _deck(rules), rules)
        with self.assertRaises(FreeDraftControllerActionRejected):
            controller.apply_current_action('1000')
        self.advance(controller, 4)
        controller.apply_current_action('1000')
        controller.apply_current_action('1000')
        self.assert_board(controller)
        self.assertIn('1000', controller.session_state.player_1_picked_character_ids)
        self.assertIn('1000', controller.session_state.player_2_picked_character_ids)
        with self.assertRaises(FreeDraftControllerActionRejected):
            controller.apply_current_action('1000')
        self.advance(controller, 16)
        self.assertTrue(controller.session_state.is_complete)

    def test_french_compensation_uses_signed_capped_sum_for_receiving_seat(self):
        data = flow_rules(FRENCH, french=True).to_dict()
        data['french_difference_cap'] = 20
        for row in data['characters']:
            row['constellation_costs'] = [0, 0, 0, 0, 0, 0, 0]
        data['characters'][0]['constellation_costs'][0] = 100
        data['characters'][1]['constellation_costs'][0] = 30
        data['characters'][2]['constellation_costs'][0] = 30
        rules = AbyssRuleset.from_dict(data)
        base = _deck(rules)
        left = replace(base, characters=(base.characters[0],) + base.characters[3:])
        right = replace(base, characters=base.characters[1:])
        report = calculate_abyss_prebans(left, right, rules, preban_cost_step=20)
        self.assertEqual((report.total_player_1, report.total_player_2), (100, 60))
        self.assertEqual((report.difference, report.count, report.seat), (20, 1, 'player_1'))
        self.assertEqual(report.cost_method, 'FRENCH_COST')
