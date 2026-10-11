"""Executable, pinned local match rules derived from an Abyss source snapshot."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Any

from hoyolab_export.traveler import traveler_element, traveler_source_id

from .abyss_rules import AbyssRuleset, _ELEMENT_ATTRIBUTE, _character_rule_candidates, evaluate_deck
from .deck import DraftDeck
from .french_cost import calculate_french_cost_difference
from .draft_completion import draft_completion
from .draft_system import DraftSystemDefinition, DRAFT_SYSTEM_RULESET_DATA_REQUIRED
from .tier_allocation import allocate_requirements
from .validation import (
    DeckValidationReport,
    SEVERITY_ERROR,
    ValidationIssue,
    validate_draft_deck,
)
from .schedule import (
    ACTION_ASSIGN_TEAM_SLOT,
    ACTION_ASSIGN_WEAPON,
    ACTION_BAN_CHARACTER,
    ACTION_FINISH_MATCH,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    ACTION_PICK_CHARACTER,
    ACTION_MIRROR_CHARACTER,
    ACTION_PREBAN_CHARACTER,
    ACTION_SET_READY,
    ACTION_SET_TIMER,
    DraftActionRequirement,
    DraftSchedule,
    DraftScheduleStep,
    PHASE_PICK,
    PHASE_PREBAN,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    with_first_seat,
)
from .session import PlayerWeaponAssignment, create_draft_session


class AbyssMatchRulesError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AbyssPrebanReport:
    total_player_1: Decimal
    total_player_2: Decimal
    difference: Decimal
    cost_step: int
    count: int
    seat: str | None
    cost_method: str = "DEFAULT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_player_1": float(self.total_player_1),
            "total_player_2": float(self.total_player_2),
            "difference": float(self.difference),
            "cost_step": self.cost_step,
            "count": self.count,
            "seat": self.seat,
            "cost_method": self.cost_method,
        }


_SOURCE_ACTIONS = {
    "BAN": ACTION_BAN_CHARACTER,
    "PICK": ACTION_PICK_CHARACTER,
    "IMMUNE_BAN": ACTION_IMMUNE_BAN_CHARACTER,
    "IMMUNE_PICK": ACTION_IMMUNE_PICK_CHARACTER,
    "IMMUNE": ACTION_IMMUNE_CHARACTER,
    "MIRROR": ACTION_MIRROR_CHARACTER,
}
_SOURCE_SEATS = {"player0": SEAT_PLAYER_1, "player1": SEAT_PLAYER_2}
_PREPARATORY_ACTIONS = frozenset({ACTION_IMMUNE_BAN_CHARACTER, ACTION_IMMUNE_PICK_CHARACTER})
_PICK_ACTIONS = frozenset({ACTION_PICK_CHARACTER, ACTION_IMMUNE_CHARACTER, ACTION_MIRROR_CHARACTER})
_COSTLESS_VARIANT_EXCEPTIONS = frozenset({
    "10000005", "10000007", "10000023", "10000025", "10000031", "10000032", "10000043",
})


def build_abyss_match_schedule(rules: AbyssRuleset, *, first_seat: str = SEAT_PLAYER_1) -> DraftSchedule:
    """Accept only the source flow shape the local reducer can execute."""
    phase = rules.to_dict().get("phase_picks")
    if not isinstance(phase, dict):
        raise AbyssMatchRulesError("abyss_pick_phase_missing", "Pinned rules have no pick phase.")
    flow = phase["flow"]
    counts: dict[str, Counter[str]] = {seat: Counter() for seat in _SOURCE_SEATS.values()}
    steps: list[DraftScheduleStep] = []
    preparatory_open = True
    for row in flow:
        action_type = _SOURCE_ACTIONS.get(row["type"])
        if action_type is None:
            raise AbyssMatchRulesError(
                "abyss_pick_action_unsupported", f"Unsupported source action: {row['type']}."
            )
        seat = _SOURCE_SEATS[row["player"]]
        if action_type in _PREPARATORY_ACTIONS:
            if not preparatory_open:
                raise AbyssMatchRulesError(
                    "abyss_pick_flow_unsupported", "Preparatory immune actions must precede the main draft."
                )
            phase_name = PHASE_PREBAN
        else:
            preparatory_open = False
            phase_name = PHASE_PICK
        counts[seat][action_type] += 1
        steps.append(DraftScheduleStep(phase_name, seat, (DraftActionRequirement(action_type),)))
    for seat, seat_counts in counts.items():
        preparation = (seat_counts[ACTION_IMMUNE_BAN_CHARACTER],
                       seat_counts[ACTION_IMMUNE_PICK_CHARACTER])
        main_counts = (seat_counts[ACTION_PICK_CHARACTER],
                       seat_counts[ACTION_IMMUNE_CHARACTER], seat_counts[ACTION_MIRROR_CHARACTER])
        supported_shape = (
            preparation == (1, 1) and main_counts[2] == 0 and sum(main_counts) == 8
            or preparation == (0, 0) and main_counts in ((8, 0, 0), (7, 0, 1), (6, 2, 0))
        )
        if seat_counts[ACTION_BAN_CHARACTER] != 3 or not supported_shape:
            raise AbyssMatchRulesError(
                "abyss_pick_flow_unsupported", f"Unsupported action counts for {seat}."
            )
    return with_first_seat(DraftSchedule(ruleset_id=f"abyss:{rules.system_id}", steps=tuple(steps)), first_seat)


def calculate_abyss_prebans(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    rules: AbyssRuleset,
    *,
    preban_cost_step: int | None = None,
) -> AbyssPrebanReport:
    """Assign one extra global ban per full source character-cost step."""
    phase = rules.to_dict().get("phase_picks")
    if phase is None:
        raise AbyssMatchRulesError("abyss_pick_phase_missing", "Pinned rules have no pick phase.")
    step = phase["preban_cost_step"] if preban_cost_step is None else preban_cost_step
    if type(step) is not int or step < 0:
        raise AbyssMatchRulesError("abyss_preban_step_invalid", "Preban cost step must be a nonnegative integer.")
    totals: list[Decimal] = []
    for deck in (player_1_deck, player_2_deck):
        rows = evaluate_deck(deck, rules).character_rows
        prices = [row["cost"] for row in rows]
        if any(price is None for price in prices):
            raise AbyssMatchRulesError("abyss_preban_cost_unknown", "A roster has an unknown character cost.")
        # The source's normal-array reduce returns the agent sum before its
        # nullish fallback, so matched bundle adjustments do not enter prebans.
        total = sum((Decimal(str(price)) for price in prices), Decimal(0))
        if not total.is_finite():
            raise AbyssMatchRulesError("abyss_preban_cost_unknown", "A roster has a nonfinite character cost.")
        totals.append(total)
    cost_method = rules.to_dict()["source"].get("cost_system", "DEFAULT")
    signed = (calculate_french_cost_difference(player_1_deck, player_2_deck, rules).signed_difference
              if cost_method == "FRENCH_COST" else totals[0] - totals[1])
    difference = abs(signed)
    count = int(difference // step) if step else 0
    seat = (SEAT_PLAYER_1 if signed < 0 else SEAT_PLAYER_2
            if signed > 0 else None) if count else None
    if count:
        expensive = player_2_deck if seat == SEAT_PLAYER_1 else player_1_deck
        if count > len(expensive.character_ids):
            raise AbyssMatchRulesError("abyss_preban_roster_insufficient", "The price gap requires more prebans than the opposing roster contains.")
    return AbyssPrebanReport(totals[0], totals[1], difference, step, count, seat, cost_method)


def build_abyss_match_definition(
    rules: AbyssRuleset, *, preban_report: AbyssPrebanReport | None = None,
    first_seat: str = SEAT_PLAYER_1,
) -> DraftSystemDefinition:
    """Bind a source version to one local hot-seat draft system instance."""
    data = rules.to_dict()
    if "mode" not in data["source"]:
        raise AbyssMatchRulesError("abyss_source_mode_missing", "Pinned rules need a source-mode update.")
    if data["source"]["mode"] != "shiyu":
        raise AbyssMatchRulesError("abyss_match_mode_unsupported", "Only Shiyu elapsed-time scoring is supported.")
    if "phase_teams" not in data:
        raise AbyssMatchRulesError("abyss_team_phase_missing", "Pinned rules have no team phase.")
    if "phase_stage" not in data:
        raise AbyssMatchRulesError("abyss_stage_phase_missing", "Pinned rules have no stage phase declaration.")
    if data["phase_stage"]["enabled"]:
        raise AbyssMatchRulesError("abyss_stage_phase_unsupported", "Enabled stage phases are unsupported.")
    schedule = build_abyss_match_schedule(rules, first_seat=first_seat)
    if preban_report is not None and preban_report.count:
        if preban_report.count < 0 or preban_report.seat not in (SEAT_PLAYER_1, SEAT_PLAYER_2):
            raise AbyssMatchRulesError("abyss_preban_report_invalid", "Invalid preban report.")
        extra = tuple(DraftScheduleStep(
            PHASE_PREBAN, preban_report.seat,
            (DraftActionRequirement(ACTION_PREBAN_CHARACTER),),
        ) for _ in range(preban_report.count))
        schedule = DraftSchedule(schedule.ruleset_id, extra + schedule.steps)
    if "phase_match" not in data:
        raise AbyssMatchRulesError("abyss_match_phase_missing", "Pinned rules have no match scoring phase.")
    return DraftSystemDefinition(
        system_id=f"abyss:{rules.system_id}",
        version=rules.content_hash,
        display_name=rules.title,
        description="Local Abyss source flow bound to a pinned public rules version.",
        schedule_builder=lambda: schedule,
        supported_action_types=(
            ACTION_PREBAN_CHARACTER,
            ACTION_IMMUNE_BAN_CHARACTER,
            ACTION_IMMUNE_PICK_CHARACTER,
            ACTION_BAN_CHARACTER,
            ACTION_PICK_CHARACTER,
            ACTION_MIRROR_CHARACTER,
            ACTION_IMMUNE_CHARACTER,
            ACTION_ASSIGN_TEAM_SLOT,
            ACTION_ASSIGN_WEAPON,
            ACTION_SET_READY,
            ACTION_SET_TIMER,
            ACTION_FINISH_MATCH,
        ),
        teams_per_player=2,
        characters_per_team=4,
        picked_characters_per_player=8,
        bans_per_player=3,
        weapons_required=True,
        immunes_supported=True,
        mirror_supported=any(action.action_type == ACTION_MIRROR_CHARACTER
                             for step in schedule.steps for action in step.actions),
        ruleset_data_requirement=DRAFT_SYSTEM_RULESET_DATA_REQUIRED,
        deterministic_smoke_planner_supported=False,
    )


def validate_abyss_match_deck(deck: DraftDeck, rules: AbyssRuleset) -> DeckValidationReport:
    """Check source-known roster legality before entering a local source flow.

    Source parity is not claimed: an inconclusive tier allocation is a blocker,
    while assignment-dependent weapon price is checked after assigning weapons.
    """
    issues = list(validate_draft_deck(deck, check_free_draft_minimum=False).issues)
    data = rules.to_dict()
    if deck.ruleset_ref.ruleset_id != f"abyss:{rules.system_id}":
        issues.append(_error("abyss_ruleset_mismatch", "ruleset_ref.ruleset_id"))
    try:
        schedule = build_abyss_match_definition(rules).build_schedule()
    except AbyssMatchRulesError as exc:
        issues.append(_error(exc.code, "rules", message=str(exc)))
        return DeckValidationReport(tuple(issues))
    opponent_bans = max(
        sum(action.action_type == ACTION_BAN_CHARACTER
            for step in schedule.steps if step.seat != seat for action in step.actions)
        for seat in _SOURCE_SEATS.values()
    )
    minimum = 8 + opponent_bans
    if len(deck.character_ids) < minimum:
        issues.append(_error("abyss_roster_too_small_for_draft", "characters",
                             details={"minimum": minimum, "actual": len(deck.character_ids)}))

    report = evaluate_deck(deck, rules)
    if any(check["status"] == "unknown" for check in report.weapon_roster["checks"]):
        issues.append(_error("abyss_weapon_roster_budget_unknown", "weapons"))
    required_by_source = {
        row["source_id"]: row for row in data["characters"]
    }
    for finding in report.issues:
        if finding.severity != SEVERITY_ERROR:
            continue
        if finding.code == "required_characters_missing":
            for source_id in finding.details.get("source_ids", ()):
                character = required_by_source[source_id]
                issues.append(_error(
                    "abyss_required_character_missing", "characters",
                    message="Required source character is missing from this roster.",
                    details={
                        "source_id": source_id,
                        "game_id": character["game_id"],
                        "attribute": character["attribute"],
                        "names": character["names"],
                    },
                ))
        else:
            issues.append(_error(f"abyss_{finding.code}", "characters", details=dict(finding.details)))
    allocation = allocate_requirements(report.character_rows, data["preset_rules"])
    if allocation["status"] != "pass":
        issues.append(_error(
            "abyss_tier_allocation_failed" if allocation["status"] == "fail"
            else "abyss_tier_allocation_unknown",
            "characters", details={"reason": allocation.get("reason", "")},
        ))
    return DeckValidationReport(tuple(issues))


def abyss_immune_context(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    rules: AbyssRuleset,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return source-client preparatory candidates and absolute immune IDs."""
    data = rules.to_dict()
    phase = data.get("phase_picks")
    if phase is None:
        raise AbyssMatchRulesError("abyss_pick_phase_missing", "Pinned rules have no pick phase.")
    source_by_id = {row["source_id"]: row for row in data["characters"]}
    absolute_ids = tuple(sorted({
        source_by_id[source_id]["game_id"] for source_id in phase["absolute_immune"]
    }))
    absolute_set = set(absolute_ids)
    rows_1 = {row["character_id"]: row for row in evaluate_deck(player_1_deck, rules).character_rows}
    rows_2 = {row["character_id"]: row for row in evaluate_deck(player_2_deck, rules).character_rows}
    deck_1 = player_1_deck.character_by_id
    deck_2 = player_2_deck.character_by_id
    eligible: list[str] = []
    for character_id in sorted(rows_1.keys() & rows_2.keys()):
        if character_id in absolute_set:
            continue
        if traveler_source_id(character_id) is not None:
            element_1 = traveler_element(character_id, deck_1[character_id].element)
            element_2 = traveler_element(character_id, deck_2[character_id].element)
            if (
                not element_1
                or element_1 != element_2
                or rows_1[character_id]["source_id"] is None
                or rows_1[character_id]["source_id"] != rows_2[character_id]["source_id"]
            ):
                continue
        one = rows_1[character_id]["cost"]
        two = rows_2[character_id]["cost"]
        if one or two:
            if one is not None and one == two:
                eligible.append(character_id)
        elif (deck_1[character_id].constellation == deck_2[character_id].constellation
              or character_id in _COSTLESS_VARIANT_EXCEPTIONS
              or traveler_source_id(character_id) is not None):
            eligible.append(character_id)
    return tuple(eligible), absolute_ids


def validate_abyss_match_pair(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    rules: AbyssRuleset,
    *,
    preban_report: AbyssPrebanReport | None = None,
    require_ban_targets: bool = True,
    first_seat: str = SEAT_PLAYER_1,
) -> DeckValidationReport:
    """Ensure the pair can complete its four distinct preparatory choices."""
    try:
        schedule = build_abyss_match_schedule(rules)
    except AbyssMatchRulesError as exc:
        return DeckValidationReport((_error(exc.code, "phase_picks", message=str(exc)),))
    required = sum(
        action.action_type in _PREPARATORY_ACTIONS
        for step in schedule.steps for action in step.actions
    )
    eligible, absolute_ids = abyss_immune_context(player_1_deck, player_2_deck, rules)
    issues = list(_pair_report_from_eligible(eligible, required, rules).issues)
    for target_seat, target in ((SEAT_PLAYER_1, player_1_deck),
                                (SEAT_PLAYER_2, player_2_deck)):
        opponent_seat = SEAT_PLAYER_2 if target_seat == SEAT_PLAYER_1 else SEAT_PLAYER_1
        ordinary_bans = sum(
            action.action_type == ACTION_BAN_CHARACTER
            for step in schedule.steps if step.seat == opponent_seat
            for action in step.actions
        )
        extra_bans = (preban_report.count if preban_report is not None
                      and preban_report.seat == opponent_seat else 0)
        minimum = 8 + ordinary_bans + extra_bans
        if len(target.character_ids) < minimum:
            issues.append(_error("abyss_roster_too_small_for_draft", "characters",
                                 details={"seat": target_seat, "minimum": minimum,
                                          "actual": len(target.character_ids)}))
    if preban_report is not None and preban_report.count:
        if preban_report.seat not in (SEAT_PLAYER_1, SEAT_PLAYER_2) or preban_report.count < 0:
            issues.append(_error("abyss_preban_report_invalid", "phase_picks"))
        else:
            target = player_2_deck if preban_report.seat == SEAT_PLAYER_1 else player_1_deck
            target_seat = SEAT_PLAYER_2 if preban_report.seat == SEAT_PLAYER_1 else SEAT_PLAYER_1
            available = len(target.character_ids - set(absolute_ids)) - required
            if available < preban_report.count:
                issues.append(_error("abyss_preban_targets_insufficient", "decks",
                                     details={"minimum": preban_report.count,
                                              "actual": max(0, available), "seat": target_seat}))
    if not issues:
        initial = create_draft_session(
            player_1_deck, player_2_deck,
            schedule=build_abyss_match_definition(rules, preban_report=preban_report,
                                                   first_seat=first_seat).build_schedule(),
            validate_decks=False, rules_content_hash=rules.content_hash,
            immune_eligible_character_ids=eligible, absolute_immune_character_ids=absolute_ids,
        )
        if draft_completion(initial, require_ban_targets=require_ban_targets).status == "impossible":
            issues.append(_error("abyss_draft_completion_impossible", "decks"))
    return DeckValidationReport(tuple(issues))


def _pair_report_from_eligible(
    eligible: tuple[str, ...], required: int, rules: AbyssRuleset,
) -> DeckValidationReport:
    if len(eligible) >= required:
        return DeckValidationReport()
    return DeckValidationReport((_error(
        "abyss_shared_immune_candidates_insufficient", "decks",
        message="Both rosters need enough shared immune candidates for the source flow.",
        details={"minimum": required, "actual": len(eligible),
                 "source_hash": rules.content_hash},
    ),))


def calculate_abyss_weapon_budget(
    rules: AbyssRuleset,
    decks: dict[str, DraftDeck],
    assignments: dict[str, PlayerWeaponAssignment],
) -> dict[str, Any]:
    """Price assigned weapons and project the public client's cumulative cap."""
    data = rules.to_dict()
    team_phase = data.get("phase_teams")
    if team_phase is None:
        raise AbyssMatchRulesError("abyss_team_phase_missing", "Pinned rules have no team phase.")
    base = team_phase["max_engines_cost"]
    step = team_phase["max_engines_cost_step"]
    source_weapons = {row["game_id"]: row for row in data["weapons"]}
    source_characters: dict[str, list[dict[str, Any]]] = {}
    for row in data["characters"]:
        source_characters.setdefault(row["game_id"], []).append(row)
    per_seat: dict[str, dict[str, Any]] = {}
    for seat in (SEAT_PLAYER_1, SEAT_PLAYER_2):
        deck = decks[seat]
        assignment = assignments.get(seat)
        rows: list[dict[str, Any]] = []
        issues: list[str] = []
        total: Decimal | None = Decimal(0)
        for item in assignment.assignments if assignment is not None else ():
            character = deck.character_by_id.get(item.character_id)
            stack = deck.weapon_stack_by_key.get(item.weapon_stack_key)
            cost: int | float | None = None
            source_character = None
            if character is not None:
                if traveler_source_id(character.character_id) is not None:
                    candidates, ambiguous = _character_rule_candidates(
                        character.character_id, character.element, source_characters
                    )
                    source_character = candidates[0] if len(candidates) == 1 and not ambiguous else None
                else:
                    candidates = source_characters.get(character.character_id, ())
                    attribute = _ELEMENT_ATTRIBUTE.get(character.element.upper())
                    exact = [row for row in candidates if row["attribute"] == attribute]
                    source_character = exact[0] if len(exact) == 1 else None
            source_weapon = source_weapons.get(stack.weapon_id) if stack is not None else None
            if (source_character is None or source_weapon is None or stack is None
                    or stack.refinement is None or not 1 <= stack.refinement <= 5):
                issues.append("abyss_assigned_weapon_price_unknown")
            else:
                refinement_index = stack.refinement - 1
                override = next((row for row in source_weapon["character_overrides"]
                                 if row["source_id"] == source_character["source_id"]), None)
                if override is not None:
                    cost = override["refinement_costs"][refinement_index]
                else:
                    character_specialty = source_character.get("specialty")
                    weapon_specialty = source_weapon.get("specialty")
                    if character_specialty is None or weapon_specialty is None:
                        issues.append("abyss_assigned_weapon_specialty_unknown")
                    elif character_specialty != weapon_specialty:
                        cost = source_weapon["off_specialty_cost"]
                    else:
                        cost = source_weapon["refinement_costs"][refinement_index]
            if cost is None:
                total = None
            elif total is not None:
                total += Decimal(str(cost))
            rows.append({"character_id": item.character_id,
                         "weapon_stack_key": item.weapon_stack_key, "cost": cost})
        per_seat[seat] = {"total": _plain_number(total), "rows": rows,
                          "assignment_count": len(rows), "issue_codes": list(dict.fromkeys(issues))}
    first = per_seat[SEAT_PLAYER_1]["total"]
    second = per_seat[SEAT_PLAYER_2]["total"]
    for seat, own, other in ((SEAT_PLAYER_1, first, second), (SEAT_PLAYER_2, second, first)):
        limit = _weapon_limit(other if other is not None else 0, base, step)
        per_seat[seat]["current_limit"] = limit
        per_seat[seat]["within_limit"] = own is not None and Decimal(str(own)) <= Decimal(str(limit))
    return {
        "source_hash": rules.content_hash,
        "max_engines_cost": base,
        "max_engines_cost_step": step,
        "per_seat": per_seat,
        "complete": all(seat in assignments for seat in (SEAT_PLAYER_1, SEAT_PLAYER_2)),
    }


def _weapon_limit(other_total: int | float, base: int | float, step: int | float) -> int | float:
    lower = Decimal(str(other_total))
    floor = Decimal(str(base))
    interval = Decimal(str(step))
    if lower <= floor or interval == 0:
        return base
    bands = ((lower - floor) / interval).to_integral_value(rounding=ROUND_CEILING)
    return _plain_number(floor + interval * bands)


def _plain_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _error(code: str, path: str, *, message: str = "",
           details: dict[str, Any] | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, severity=SEVERITY_ERROR, message=message,
                           path=path, details=details or {})
