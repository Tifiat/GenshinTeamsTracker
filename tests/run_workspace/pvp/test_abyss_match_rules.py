from __future__ import annotations

import unittest
from dataclasses import replace

from hoyolab_export.traveler import traveler_variant_id
from run_workspace.pvp.abyss_match_rules import (
    AbyssMatchRulesError,
    abyss_immune_context,
    build_abyss_match_schedule,
    calculate_abyss_weapon_budget,
    validate_abyss_match_deck,
    validate_abyss_match_pair,
)
from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck import (
    DRAFT_DECK_KIND,
    DraftCharacter,
    DraftDeck,
    DraftDeckRulesetRef,
    DraftWeaponStack,
)
from run_workspace.pvp.free_draft_board import validate_free_draft_board_projection_dict
from run_workspace.pvp.free_draft_controller import (
    FreeDraftController,
    FreeDraftControllerActionRejected,
)
from run_workspace.pvp.match_result import (
    ChamberTimer,
    PlayerMatchTimers,
    calculate_abyss_match_result,
    calculate_match_result,
)
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import CharacterWeaponAssignment, PlayerWeaponAssignment


_FLOW = [
    ("IMMUNE_BAN", 0), ("IMMUNE_BAN", 1),
    ("IMMUNE_PICK", 0), ("IMMUNE_PICK", 1),
    ("BAN", 0), ("BAN", 1), ("BAN", 0), ("BAN", 1),
    ("PICK", 0), ("PICK", 1), ("PICK", 1), ("PICK", 0),
    ("PICK", 0), ("PICK", 1), ("IMMUNE", 0), ("IMMUNE", 1),
    ("BAN", 1), ("BAN", 0),
    ("PICK", 1), ("PICK", 0), ("PICK", 0), ("PICK", 1),
    ("PICK", 1), ("PICK", 0), ("IMMUNE", 0), ("IMMUNE", 1),
]


def _rules(*, first_action: str = "IMMUNE_BAN", cap: int = 30,
           step: int = 10) -> AbyssRuleset:
    flow = [(first_action, 0), *_FLOW[1:]]
    agents = [
        {"_id": f"{i + 100:024x}", "enkaId": str(1000 + i),
         "attribute": 17, "specialty": 5, "name": {"en": f"Character {i}"}}
        for i in range(24)
    ]
    engines = [
        {"_id": f"{500 + i:024x}", "enkaId": str(2000 + i), "specialty": 5}
        for i in range(2)
    ]
    system = {
        "_id": "000000000000000000000001",
        "updatedAt": "2026-10-09T00:00:00Z",
        "main": {"title": "Synthetic pinned Abyss", "mode": "shiyu"},
        "costs": {
            "system": "DEFAULT", "costLimit": 0,
            "agents": [{"agent": row["_id"], "costs": [10] * 7 + [0, 0]}
                       for row in agents],
            "engines": [
                {"engine": engines[0]["_id"], "costs": [5] * 5 + [2]},
                {"engine": engines[1]["_id"], "costs": [2] * 5 + [1]},
            ],
            "agentsBundles": [],
            "tiers": [{"tier": 0, "minCost": 1, "maxCost": 100}],
        },
        "draft": {
            "minMaxCosts": {"agents": [0, 0], "engines": [0, 0]},
            "minMaxCount": {"agents": [0, 0], "engines": [0, 0]},
        },
        "preset": {"rules": [], "ddAgents": []},
        "phasePicks": {
            "flow": [{"type": kind, "player": f"player{player}"} for kind, player in flow],
            "absoluteImmune": [], "prebanCostStep": 60,
            "pickTime": 60000, "reserveTime": 300000,
        },
        "phaseTeams": {"maxEnginesCost": cap, "maxEnginesCostStep": step},
        "phaseStage": {"isEnabled": False},
        "phaseMatch": {"freeRestarts": 3, "paidRestarts": [5, 5, 10]},
    }
    return AbyssRuleset.from_source(system, agents, engines)


def _deck(rules: AbyssRuleset) -> DraftDeck:
    return DraftDeck(
        1, DRAFT_DECK_KIND, "Synthetic roster",
        ruleset_ref=DraftDeckRulesetRef(f"abyss:{rules.system_id}", rules.title),
        characters=tuple(DraftCharacter(str(1000 + i), f"Character {i}", "PYRO",
                                        "SWORD", 5, 90, 0) for i in range(24)),
        weapons=(DraftWeaponStack("2000", "Sword A", "SWORD", 5, 90, 1, 8),
                 DraftWeaponStack("2001", "Sword B", "SWORD", 5, 90, 1, 8)),
    )


def _rules_with_traveler() -> AbyssRuleset:
    payload = _rules().to_dict()
    anemo_source_id = "e" * 24
    pyro_source_id = "f" * 24
    for source_id, attribute, cost in (
        (anemo_source_id, 11, 0),
        (pyro_source_id, 17, 0),
    ):
        payload["characters"].append({
            "source_id": source_id,
            "game_id": "10000007",
            "attribute": attribute,
            "names": {"en": "Traveler"},
            "constellation_costs": [cost] * 7,
            "level_percent": 0,
            "level_flat": 0,
            "specification": None,
            "disable_french_cap": False,
            "specialty": 5,
        })
    payload["weapons"][0]["character_overrides"].append({
        "source_id": pyro_source_id,
        "game_id": "10000007",
        "attribute": 17,
        "refinement_costs": [13] * 5,
    })
    return AbyssRuleset.from_dict(payload)


class AbyssMatchRulesTests(unittest.TestCase):
    def test_pinned_flow_and_controller_replay(self) -> None:
        rules = _rules()
        deck = _deck(rules)
        self.assertTrue(validate_abyss_match_deck(deck, rules).ready)
        schedule = build_abyss_match_schedule(rules)
        self.assertEqual(len(schedule.steps), 26)
        self.assertEqual(schedule.steps[0].actions[0].action_type, ACTION_IMMUNE_BAN_CHARACTER)
        controller = FreeDraftController.from_abyss_decks(deck, deck, rules)
        self.assertTrue(controller.state.setup_ready)
        self.assertEqual(controller.state.draft_system.version, rules.content_hash)
        self.assertEqual(validate_free_draft_board_projection_dict(controller.to_board_dict()), ())
        controller.complete_draft_with_first_legal_targets()
        self.assertTrue(controller.session_state.is_complete)
        self.assertEqual(validate_free_draft_board_projection_dict(controller.to_board_dict()), ())
        self.assertEqual(len(controller.session_state.accepted_actions), 26)
        self.assertEqual(len(controller.session_state.picked_character_ids_for(SEAT_PLAYER_1)), 8)
        self.assertEqual(len(controller.session_state.picked_character_ids_for(SEAT_PLAYER_2)), 8)
        self.assertEqual(controller._replay_state_hash(), controller.session_state.state_hash())

    def test_immune_preparation_and_shared_immune_pick(self) -> None:
        rules = _rules()
        deck = _deck(rules)
        controller = FreeDraftController.from_abyss_decks(deck, deck, rules)
        for character_id in ("1000", "1001", "1002", "1003"):
            controller.apply_current_action(character_id)
        self.assertEqual(controller.session_state.current_requirement.action_type, ACTION_BAN_CHARACTER)
        self.assertNotIn("1002", {item.character_id for item in controller.get_legal_targets()})
        self.assertIn("1000", {item.character_id for item in controller.get_legal_targets()})
        for character_id in ("1000", "1001", "1004", "1005",
                             "1006", "1007", "1008", "1009", "1010", "1011"):
            controller.apply_current_action(character_id)
        self.assertEqual(controller.session_state.current_requirement.action_type, ACTION_IMMUNE_CHARACTER)
        controller.apply_current_action("1002")
        self.assertIn("1002", {item.character_id for item in controller.get_legal_targets()})
        board = controller.to_board_dict()
        shared = next(row for row in board["unified_pool"]["entries"]
                      if row["character_id"] == "1002")
        self.assertEqual(shared["zone"], "pool")
        self.assertEqual(shared["action"]["type"], ACTION_IMMUNE_CHARACTER)
        self.assertEqual(validate_free_draft_board_projection_dict(board), ())
        controller.apply_current_action("1002")
        board = controller.to_board_dict()
        self.assertEqual(validate_free_draft_board_projection_dict(board), ())
        self.assertIn("1002", board["unified_pool"]["result_zones"][SEAT_PLAYER_1]["picked"])
        self.assertIn("1002", board["unified_pool"]["result_zones"][SEAT_PLAYER_2]["picked"])
        self.assertIn("1002", controller.session_state.picked_character_ids_for(SEAT_PLAYER_1))
        self.assertIn("1002", controller.session_state.picked_character_ids_for(SEAT_PLAYER_2))
        self.assertEqual(controller.session_state.immune_ban_character_ids, ("1000", "1001"))
        self.assertEqual(controller.session_state.immune_pick_character_ids, ("1002", "1003"))

    def test_budget_uses_both_staged_seats_and_rejects_unsupported_action(self) -> None:
        rules = _rules()
        deck = _deck(rules)
        sword_a, sword_b = (item.stack_key for item in deck.weapons)
        expensive = PlayerWeaponAssignment(SEAT_PLAYER_1, tuple(
            CharacterWeaponAssignment(str(1000 + i), sword_a) for i in range(8)))
        cheap = PlayerWeaponAssignment(SEAT_PLAYER_2, tuple(
            CharacterWeaponAssignment(str(1000 + i), sword_b) for i in range(8)))
        equal = PlayerWeaponAssignment(SEAT_PLAYER_2, tuple(
            CharacterWeaponAssignment(str(1000 + i), sword_a) for i in range(8)))
        unbalanced = calculate_abyss_weapon_budget(
            rules, {SEAT_PLAYER_1: deck, SEAT_PLAYER_2: deck},
            {SEAT_PLAYER_1: expensive, SEAT_PLAYER_2: cheap})
        self.assertEqual(unbalanced["per_seat"][SEAT_PLAYER_1]["total"], 40)
        self.assertEqual(unbalanced["per_seat"][SEAT_PLAYER_1]["current_limit"], 30)
        self.assertFalse(unbalanced["per_seat"][SEAT_PLAYER_1]["within_limit"])
        balanced = calculate_abyss_weapon_budget(
            rules, {SEAT_PLAYER_1: deck, SEAT_PLAYER_2: deck},
            {SEAT_PLAYER_1: expensive, SEAT_PLAYER_2: equal})
        self.assertEqual(balanced["per_seat"][SEAT_PLAYER_1]["current_limit"], 40)
        self.assertTrue(balanced["per_seat"][SEAT_PLAYER_1]["within_limit"])
        with self.assertRaises(AbyssMatchRulesError) as error:
            build_abyss_match_schedule(_rules(first_action="MIRROR"))
        self.assertEqual(error.exception.code, "abyss_pick_flow_unsupported")

    def test_traveler_alias_and_element_select_assigned_weapon_price(self) -> None:
        rules = _rules_with_traveler()
        base = _deck(rules)
        traveler_id = str(traveler_variant_id(10000005, "Pyro"))
        traveler = replace(
            base.characters[0],
            character_id=traveler_id,
            display_name="Traveler (Pyro)",
            element="PYRO",
        )
        deck = replace(base, characters=(traveler,) + base.characters[1:])
        assignment = PlayerWeaponAssignment(
            SEAT_PLAYER_1,
            (CharacterWeaponAssignment(traveler_id, deck.weapons[0].stack_key),),
        )

        report = calculate_abyss_weapon_budget(
            rules,
            {SEAT_PLAYER_1: deck, SEAT_PLAYER_2: deck},
            {SEAT_PLAYER_1: assignment},
        )

        self.assertEqual(report["per_seat"][SEAT_PLAYER_1]["rows"][0]["cost"], 13)

    def test_traveler_variant_is_a_costless_immunity_exception(self) -> None:
        rules = _rules_with_traveler()
        base = _deck(rules)
        traveler_id = str(traveler_variant_id(10000005, "Pyro"))
        player_1 = replace(
            base,
            characters=(replace(base.characters[0], character_id=traveler_id,
                                display_name="Traveler (Pyro)", element="PYRO",
                                constellation=0),) + base.characters[1:],
        )
        player_2 = replace(
            base,
            characters=(replace(base.characters[0], character_id=traveler_id,
                                display_name="Traveler (Pyro)", element="PYRO",
                                constellation=6),) + base.characters[1:],
        )

        eligible, _ = abyss_immune_context(player_1, player_2, rules)

        self.assertIn(traveler_id, eligible)

    def test_same_anchor_with_different_elements_is_not_a_shared_immune_candidate(self) -> None:
        rules = _rules_with_traveler()
        base = _deck(rules)
        player_1 = replace(
            base,
            characters=(replace(base.characters[0], character_id="10000005",
                                display_name="Traveler (Anemo)", element="ANEMO"),)
            + base.characters[1:],
        )
        player_2 = replace(
            base,
            characters=(replace(base.characters[0], character_id="10000005",
                                display_name="Traveler (Pyro)", element="PYRO"),)
            + base.characters[1:],
        )

        eligible, _ = abyss_immune_context(player_1, player_2, rules)

        self.assertNotIn("10000005", eligible)

    def test_ordinary_assigned_weapon_price_still_requires_exact_element(self) -> None:
        rules = _rules()
        base = _deck(rules)
        character = replace(base.characters[0], element="HYDRO")
        deck = replace(base, characters=(character,) + base.characters[1:])
        assignment = PlayerWeaponAssignment(
            SEAT_PLAYER_1,
            (CharacterWeaponAssignment(character.character_id, deck.weapons[0].stack_key),),
        )

        report = calculate_abyss_weapon_budget(
            rules,
            {SEAT_PLAYER_1: deck, SEAT_PLAYER_2: deck},
            {SEAT_PLAYER_1: assignment},
        )

        self.assertIsNone(report["per_seat"][SEAT_PLAYER_1]["rows"][0]["cost"])
        self.assertIn(
            "abyss_assigned_weapon_price_unknown",
            report["per_seat"][SEAT_PLAYER_1]["issue_codes"],
        )

    def test_restart_penalty_changes_winner_without_changing_raw_timers(self) -> None:
        player_1 = PlayerMatchTimers(SEAT_PLAYER_1, (ChamberTimer("room", "one", 90),))
        player_2 = PlayerMatchTimers(SEAT_PLAYER_2, (ChamberTimer("room", "one", 94),))
        self.assertEqual(calculate_match_result(player_1, player_2).winner_seat, SEAT_PLAYER_1)
        result = calculate_abyss_match_result(
            player_1, player_2,
            restarts_by_seat={SEAT_PLAYER_1: 4, SEAT_PLAYER_2: 0},
            free_restarts=3, paid_restarts=(5, 5, 10), source_hash="pinned",
        )
        self.assertEqual(result.winner_seat, SEAT_PLAYER_2)
        self.assertEqual(result.seconds_difference, 1)
        self.assertEqual(result.to_dict()["totals"][SEAT_PLAYER_1], 90)
        self.assertEqual(result.to_dict()["source_scoring"]["per_seat"][SEAT_PLAYER_1]["adjusted_seconds"], 95)
        capped = calculate_abyss_match_result(
            player_1, player_2,
            restarts_by_seat={SEAT_PLAYER_1: 10, SEAT_PLAYER_2: 0},
            free_restarts=3, paid_restarts=(5, 5, 10), source_hash="pinned",
        )
        self.assertEqual(capped.to_dict()["source_scoring"]["per_seat"][SEAT_PLAYER_1]["penalty_seconds"], 20)
        self.assertNotIn("source_scoring", calculate_match_result(player_1, player_2).to_dict())

    def test_controller_requires_restart_counts_and_keeps_bundle_unsupported(self) -> None:
        rules = _rules()
        deck = _deck(rules)
        controller = FreeDraftController.from_abyss_decks(deck, deck, rules)
        controller.complete_draft_with_first_legal_targets()
        controller.assign_deterministic_teams_and_weapons()
        player_1 = PlayerMatchTimers(SEAT_PLAYER_1, (ChamberTimer("room", "one", 90),))
        player_2 = PlayerMatchTimers(SEAT_PLAYER_2, (ChamberTimer("room", "one", 94),))
        with self.assertRaises(FreeDraftControllerActionRejected) as error:
            controller.set_match_timers(player_1, player_2)
        self.assertEqual(error.exception.code, "abyss_restart_counts_missing")
        result = controller.set_match_timers(
            player_1, player_2,
            restarts_by_seat={SEAT_PLAYER_1: 4, SEAT_PLAYER_2: 0},
        )
        self.assertEqual(result.winner_seat, SEAT_PLAYER_2)
        self.assertIn("source_scoring", controller.to_board_dict()["summary"]["result"])
        with self.assertRaises(FreeDraftControllerActionRejected) as error:
            controller.build_session_bundle()
        self.assertEqual(error.exception.code, "abyss_session_bundle_unsupported")

    def test_missing_mode_and_enabled_stage_fail_closed(self) -> None:
        payload = _rules().to_dict()
        payload["source"].pop("mode")
        with self.assertRaises(AbyssMatchRulesError) as error:
            FreeDraftController.from_abyss_decks(
                _deck(AbyssRuleset.from_dict(payload)),
                _deck(AbyssRuleset.from_dict(payload)),
                AbyssRuleset.from_dict(payload),
            )
        self.assertEqual(error.exception.code, "abyss_source_mode_missing")
        payload["source"]["mode"] = "shiyu"
        payload["phase_stage"]["enabled"] = True
        rules = AbyssRuleset.from_dict(payload)
        with self.assertRaises(AbyssMatchRulesError) as error:
            FreeDraftController.from_abyss_decks(_deck(rules), _deck(rules), rules)
        self.assertEqual(error.exception.code, "abyss_stage_phase_unsupported")

    def test_pair_requires_four_distinct_shared_immune_candidates(self) -> None:
        rules = _rules()
        full = _deck(rules)
        left = replace(full, characters=full.characters[:12])
        for shared_count in (0, 3, 4):
            right = replace(full, characters=(
                full.characters[:shared_count]
                + full.characters[12:24 - shared_count]
            ))
            report = validate_abyss_match_pair(left, right, rules)
            controller = FreeDraftController.from_abyss_decks(left, right, rules)
            self.assertEqual(report.ready, shared_count == 4)
            self.assertEqual(controller.state.setup_ready, shared_count == 4)
            if shared_count < 4:
                issue = report.errors[0]
                self.assertEqual(issue.code, "abyss_shared_immune_candidates_insufficient")
                self.assertEqual(issue.details["actual"], shared_count)
                self.assertEqual(issue.details["minimum"], 4)

        payload = rules.to_dict()
        payload["characters"][0]["constellation_costs"][1] = 11
        priced_rules = AbyssRuleset.from_dict(payload)
        priced_left = replace(_deck(priced_rules), characters=_deck(priced_rules).characters[:12])
        right_chars = full.characters[:4] + full.characters[12:20]
        priced_right = replace(_deck(priced_rules), characters=(
            replace(right_chars[0], constellation=1), *right_chars[1:]
        ))
        report = validate_abyss_match_pair(priced_left, priced_right, priced_rules)
        self.assertEqual(report.errors[0].details["actual"], 3)
        self.assertFalse(FreeDraftController.from_abyss_decks(
            priced_left, priced_right, priced_rules
        ).state.setup_ready)


if __name__ == "__main__":
    unittest.main()
