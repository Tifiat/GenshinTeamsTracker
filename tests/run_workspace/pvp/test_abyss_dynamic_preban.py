from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from run_workspace.pvp.abyss_match_rules import (
    AbyssMatchRulesError,
    abyss_immune_context,
    build_abyss_match_definition,
    calculate_abyss_prebans,
    validate_abyss_match_pair,
)
from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.schedule import (
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    ACTION_PREBAN_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    DraftAction,
    DraftActionRejected,
    REJECT_CHARACTER_ALREADY_BANNED,
    REJECT_CHARACTER_ABSOLUTELY_IMMUNE,
    REJECT_CHARACTER_GLOBALLY_BANNED,
    REJECT_IMMUNE_CHOICES_INSUFFICIENT,
    apply_draft_action,
    create_draft_session,
)
from tests.run_workspace.pvp.test_abyss_match_rules import _deck, _rules


def _priced_pair(gap: int | float):
    payload = _rules().to_dict()
    payload["characters"][0]["constellation_costs"][1] = 10 + gap
    rules = AbyssRuleset.from_dict(payload)
    deck = _deck(rules)
    expensive = replace(deck, characters=(replace(deck.characters[0], constellation=1),)
                        + deck.characters[1:])
    return rules, deck, expensive


class AbyssDynamicPrebanTests(unittest.TestCase):
    def test_cost_boundaries_and_seat_assignment(self) -> None:
        for gap, count in ((0, 0), (59, 0), (60, 1), (119, 1), (120, 2)):
            with self.subTest(gap=gap):
                rules, cheap, expensive = _priced_pair(gap)
                report = calculate_abyss_prebans(cheap, expensive, rules)
                self.assertEqual(report.difference, Decimal(gap))
                self.assertEqual(report.cost_step, 60)
                self.assertEqual(report.count, count)
                self.assertEqual(report.seat, SEAT_PLAYER_1 if count else None)
                swapped = calculate_abyss_prebans(expensive, cheap, rules)
                self.assertEqual(swapped.count, count)
                self.assertEqual(swapped.seat, SEAT_PLAYER_2 if count else None)
                schedule = build_abyss_match_definition(rules, preban_report=report).build_schedule()
                self.assertEqual(len(schedule.steps), 26 + count)
                self.assertEqual(
                    [step.actions[0].action_type for step in schedule.steps[:count]],
                    [ACTION_PREBAN_CHARACTER] * count,
                )
                self.assertEqual(schedule.steps[count].actions[0].action_type,
                                 ACTION_IMMUNE_BAN_CHARACTER)

    def test_step_disabled_decimal_and_unknown_cost(self) -> None:
        rules, cheap, expensive = _priced_pair(59.9)
        report = calculate_abyss_prebans(cheap, expensive, rules)
        self.assertEqual(report.difference, Decimal("59.9"))
        self.assertEqual(report.count, 0)
        self.assertEqual(calculate_abyss_prebans(cheap, expensive, rules,
                                                preban_cost_step=0).count, 0)
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(AbyssMatchRulesError) as raised:
                calculate_abyss_prebans(cheap, expensive, rules, preban_cost_step=value)
            self.assertEqual(raised.exception.code, "abyss_preban_step_invalid")
        unknown = replace(cheap, characters=(replace(cheap.characters[0], constellation=None),)
                          + cheap.characters[1:])
        with self.assertRaises(AbyssMatchRulesError) as raised:
            calculate_abyss_prebans(unknown, expensive, rules)
        self.assertEqual(raised.exception.code, "abyss_preban_cost_unknown")

    def test_bundle_adjustment_does_not_change_preban_total(self) -> None:
        rules, cheap, expensive = _priced_pair(0)
        payload = rules.to_dict()
        source = payload["characters"][0]
        payload["bundles"] = [{"cost": 60, "members": [{
            "source_id": source["source_id"], "game_id": source["game_id"],
            "attribute": source["attribute"], "constellation_min": 1,
            "constellation_max": 1,
        }]}]
        rules = AbyssRuleset.from_dict(payload)
        report = calculate_abyss_prebans(cheap, expensive, rules)
        # Source helper nl in agent-list.component-BELlgTBD.js computes a
        # bundle adjustment, but normal-array reduce returns the agent sum.
        # https://abyss.darte.gg/assets/agent-list.component-BELlgTBD.js
        self.assertEqual(report.difference, Decimal(0))
        self.assertEqual(report.count, 0)

    def test_roster_bound_and_pair_admission(self) -> None:
        rules, cheap, expensive = _priced_pair(1500)
        with self.assertRaises(AbyssMatchRulesError) as raised:
            calculate_abyss_prebans(cheap, expensive, rules)
        self.assertEqual(raised.exception.code, "abyss_preban_roster_insufficient")

        rules, cheap, expensive = _priced_pair(120)
        report = calculate_abyss_prebans(cheap, expensive, rules)
        self.assertTrue(validate_abyss_match_pair(cheap, expensive, rules,
                                                  preban_report=report).ready)
        short = replace(expensive, characters=expensive.characters[:12])
        issues = validate_abyss_match_pair(cheap, short, rules, preban_report=report)
        self.assertIn("abyss_roster_too_small_for_draft", issues.issue_codes())

    def test_preban_is_global_and_keeps_immune_preparation_viable(self) -> None:
        rules, cheap, expensive = _priced_pair(60)
        report = calculate_abyss_prebans(cheap, expensive, rules)
        eligible, absolute = abyss_immune_context(cheap, expensive, rules)
        schedule = build_abyss_match_definition(rules, preban_report=report).build_schedule()
        initial = create_draft_session(cheap, expensive, schedule=schedule, validate_decks=False,
                                     rules_content_hash=rules.content_hash,
                                     immune_eligible_character_ids=eligible,
                                     absolute_immune_character_ids=absolute)
        state = initial
        first = eligible[0]
        state = apply_draft_action(state, DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, first))
        self.assertIn(first, state.banned_character_ids)
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(state, DraftAction(SEAT_PLAYER_1, ACTION_IMMUNE_BAN_CHARACTER, first))
        self.assertEqual(raised.exception.code, REJECT_CHARACTER_GLOBALLY_BANNED)
        state = replace(state, step_index=9)
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(state, DraftAction(state.current_seat, ACTION_PICK_CHARACTER, first))
        self.assertEqual(raised.exception.code, REJECT_CHARACTER_GLOBALLY_BANNED)
        state = replace(state, step_index=0)
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(state, DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, first))
        self.assertEqual(raised.exception.code, REJECT_CHARACTER_ALREADY_BANNED)

        constrained = replace(initial, immune_eligible_character_ids=eligible[:4])
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(constrained, DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, first))
        self.assertEqual(raised.exception.code, REJECT_IMMUNE_CHOICES_INSUFFICIENT)

    def test_absolute_immune_cannot_be_prebanned(self) -> None:
        rules, cheap, expensive = _priced_pair(60)
        payload = rules.to_dict()
        payload["phase_picks"]["absolute_immune"] = [payload["characters"][1]["source_id"]]
        rules = AbyssRuleset.from_dict(payload)
        report = calculate_abyss_prebans(cheap, expensive, rules)
        self.assertTrue(validate_abyss_match_pair(cheap, expensive, rules,
                                                  preban_report=report).ready)
        eligible, absolute = abyss_immune_context(cheap, expensive, rules)
        state = create_draft_session(
            cheap, expensive,
            schedule=build_abyss_match_definition(rules, preban_report=report).build_schedule(),
            validate_decks=False, rules_content_hash=rules.content_hash,
            immune_eligible_character_ids=eligible, absolute_immune_character_ids=absolute,
        )
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(state, DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, "1001"))
        self.assertEqual(raised.exception.code, REJECT_CHARACTER_ABSOLUTELY_IMMUNE)


if __name__ == "__main__":
    unittest.main()
