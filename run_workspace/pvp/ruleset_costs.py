"""Deck cost preview against parsed tournament rulesets.

The hardcoded matching behavior here is deliberately conservative: ids win,
display-name fallback is reported as a mapping gap, and character-specific
weapon overrides are only a preview until real ruleset/catalog id alignment is
implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from hoyolab_export.catalog_mapping import normalize_catalog_name
from hoyolab_export.tournament_ruleset import (
    RulesetCharacterCost,
    RulesetWeaponCost,
    RulesetWeaponOverride,
    TournamentRulesetV1,
)

from .deck import DraftCharacter, DraftDeck, DraftWeaponStack


ISSUE_CHARACTER_COST_UNKNOWN = "character_cost_unknown"
ISSUE_WEAPON_COST_UNKNOWN = "weapon_cost_unknown"
ISSUE_CHARACTER_MATCHED_BY_DISPLAY_NAME_FALLBACK = (
    "character_matched_by_display_name_fallback"
)
ISSUE_WEAPON_MATCHED_BY_DISPLAY_NAME_FALLBACK = (
    "weapon_matched_by_display_name_fallback"
)
ISSUE_CHARACTER_CONSTELLATION_COST_MISSING = (
    "character_constellation_cost_missing"
)
ISSUE_WEAPON_REFINEMENT_COST_MISSING = "weapon_refinement_cost_missing"
ISSUE_WEAPON_OVERRIDE_NAME_ONLY_MAPPING = "weapon_override_name_only_mapping"
ISSUE_WEAPON_ASSIGNMENT_CHARACTER_UNKNOWN = "weapon_assignment_character_unknown"
ISSUE_WEAPON_ASSIGNMENT_STACK_UNKNOWN = "weapon_assignment_stack_unknown"
ISSUE_CHARACTER_MATCH_AMBIGUOUS = "character_match_ambiguous"
ISSUE_WEAPON_MATCH_AMBIGUOUS = "weapon_match_ambiguous"

MATCH_BY_ID = "id"
MATCH_BY_DISPLAY_NAME = "display_name"
MATCH_NONE = "none"

WEAPON_COST_MODE_POOL = "pool"
WEAPON_COST_MODE_ASSIGNED = "assigned"


@dataclass(frozen=True, slots=True)
class RulesetCostIssue:
    code: str
    severity: str
    message: str
    path: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class RulesetEntryCost:
    kind: str
    entry_id: str
    display_name: str
    cost: float
    quantity: int = 1
    matched_by: str = MATCH_NONE
    source: str = ""
    breakdown: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "entry_id": self.entry_id,
            "display_name": self.display_name,
            "cost": self.cost,
            "quantity": self.quantity,
            "matched_by": self.matched_by,
            "source": self.source,
            "breakdown": dict(sorted(self.breakdown.items())),
        }


@dataclass(frozen=True, slots=True)
class RulesetDeckCostReport:
    ruleset_name: str
    deck_name: str
    weapon_cost_mode: str
    character_total: float
    weapon_total: float
    total_cost: float
    character_entries: tuple[RulesetEntryCost, ...] = ()
    weapon_entries: tuple[RulesetEntryCost, ...] = ()
    issues: tuple[RulesetCostIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_name": self.ruleset_name,
            "deck_name": self.deck_name,
            "weapon_cost_mode": self.weapon_cost_mode,
            "character_total": self.character_total,
            "weapon_total": self.weapon_total,
            "total_cost": self.total_cost,
            "ready": self.ready,
            "character_entries": [
                item.to_dict() for item in self.character_entries
            ],
            "weapon_entries": [item.to_dict() for item in self.weapon_entries],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class _CharacterMatch:
    rule: RulesetCharacterCost | None
    matched_by: str


@dataclass(frozen=True, slots=True)
class _WeaponMatch:
    rule: RulesetWeaponCost | None
    matched_by: str


def calculate_draft_deck_ruleset_cost(
    deck: DraftDeck,
    ruleset: TournamentRulesetV1,
    *,
    weapon_assignments_by_character_id: Mapping[str, str] | None = None,
) -> RulesetDeckCostReport:
    issues: list[RulesetCostIssue] = []
    character_entries = tuple(
        _character_entry_cost(deck_character, ruleset, issues, index)
        for index, deck_character in enumerate(deck.characters)
    )

    if weapon_assignments_by_character_id is None:
        weapon_cost_mode = WEAPON_COST_MODE_POOL
        weapon_entries = tuple(
            _weapon_pool_entry_cost(stack, ruleset, issues, index)
            for index, stack in enumerate(deck.weapons)
        )
    else:
        weapon_cost_mode = WEAPON_COST_MODE_ASSIGNED
        weapon_entries = tuple(
            _assigned_weapon_entry_cost(
                deck,
                ruleset,
                character_id,
                weapon_ref,
                issues,
                index,
            )
            for index, (character_id, weapon_ref) in enumerate(
                sorted(weapon_assignments_by_character_id.items())
            )
        )

    character_total = _round_cost(sum(item.cost for item in character_entries))
    weapon_total = _round_cost(sum(item.cost for item in weapon_entries))
    return RulesetDeckCostReport(
        ruleset_name=ruleset.name,
        deck_name=deck.deck_name,
        weapon_cost_mode=weapon_cost_mode,
        character_total=character_total,
        weapon_total=weapon_total,
        total_cost=_round_cost(character_total + weapon_total),
        character_entries=character_entries,
        weapon_entries=weapon_entries,
        issues=tuple(issues),
    )


def _character_entry_cost(
    deck_character: DraftCharacter,
    ruleset: TournamentRulesetV1,
    issues: list[RulesetCostIssue],
    index: int,
) -> RulesetEntryCost:
    path = f"characters[{index}]"
    match = _match_character(deck_character, ruleset, issues, path)
    if match.rule is None:
        issues.append(
            _issue(
                ISSUE_CHARACTER_COST_UNKNOWN,
                "error",
                "No ruleset character cost matched this deck character.",
                path,
                {
                    "character_id": deck_character.character_id,
                    "display_name": deck_character.display_name,
                },
            )
        )
        return RulesetEntryCost(
            kind="character",
            entry_id=deck_character.character_id,
            display_name=deck_character.display_name,
            cost=0,
            matched_by=MATCH_NONE,
        )

    constellation = deck_character.constellation or 0
    base_cost = match.rule.costs_by_constellation.get(constellation)
    if base_cost is None:
        issues.append(
            _issue(
                ISSUE_CHARACTER_CONSTELLATION_COST_MISSING,
                "error",
                "Ruleset character row lacks a cost for this constellation.",
                path,
                {
                    "character_id": deck_character.character_id,
                    "display_name": deck_character.display_name,
                    "constellation": constellation,
                },
            )
        )
        base_cost = 0

    level_extra = _level_extra_cost(deck_character, match.rule)
    if not match.rule.count_for_deck:
        base_cost = 0
        level_extra = 0

    return RulesetEntryCost(
        kind="character",
        entry_id=deck_character.character_id,
        display_name=deck_character.display_name,
        cost=_round_cost(base_cost + level_extra),
        matched_by=match.matched_by,
        source=match.rule.name,
        breakdown={
            "constellation_cost": _round_cost(base_cost),
            "level_extra_cost": _round_cost(level_extra),
        },
    )


def _weapon_pool_entry_cost(
    stack: DraftWeaponStack,
    ruleset: TournamentRulesetV1,
    issues: list[RulesetCostIssue],
    index: int,
) -> RulesetEntryCost:
    path = f"weapons[{index}]"
    match = _match_weapon(stack, ruleset, issues, path)
    if match.rule is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_COST_UNKNOWN,
                "error",
                "No ruleset weapon cost matched this deck weapon stack.",
                path,
                {
                    "weapon_id": stack.weapon_id,
                    "display_name": stack.display_name,
                },
            )
        )
        return RulesetEntryCost(
            kind="weapon",
            entry_id=stack.weapon_id,
            display_name=stack.display_name,
            cost=0,
            quantity=stack.count or 0,
            matched_by=MATCH_NONE,
        )

    refinement = stack.refinement or 1
    per_copy_cost = match.rule.costs_by_refinement.get(refinement)
    if per_copy_cost is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_REFINEMENT_COST_MISSING,
                "error",
                "Ruleset weapon row lacks a cost for this refinement.",
                path,
                {
                    "weapon_id": stack.weapon_id,
                    "display_name": stack.display_name,
                    "refinement": refinement,
                },
            )
        )
        per_copy_cost = 0
    quantity = stack.count or 0
    return RulesetEntryCost(
        kind="weapon",
        entry_id=stack.weapon_id,
        display_name=stack.display_name,
        cost=_round_cost(per_copy_cost * quantity),
        quantity=quantity,
        matched_by=match.matched_by,
        source=match.rule.name,
        breakdown={"per_copy_cost": _round_cost(per_copy_cost)},
    )


def _assigned_weapon_entry_cost(
    deck: DraftDeck,
    ruleset: TournamentRulesetV1,
    character_id: str,
    weapon_ref: str,
    issues: list[RulesetCostIssue],
    index: int,
) -> RulesetEntryCost:
    path = f"weapon_assignments[{index}]"
    character = deck.character_by_id.get(character_id)
    if character is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_ASSIGNMENT_CHARACTER_UNKNOWN,
                "error",
                "Weapon assignment references a character outside the deck.",
                path,
                {"character_id": character_id},
            )
        )
        return RulesetEntryCost("weapon", weapon_ref, "", 0)

    stack = _stack_for_ref(deck, weapon_ref)
    if stack is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_ASSIGNMENT_STACK_UNKNOWN,
                "error",
                "Weapon assignment references an unknown weapon stack.",
                path,
                {"weapon_ref": weapon_ref, "character_id": character_id},
            )
        )
        return RulesetEntryCost("weapon", weapon_ref, "", 0)

    weapon_match = _match_weapon(stack, ruleset, issues, path)
    character_match = _match_character(character, ruleset, issues, path)
    if weapon_match.rule is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_COST_UNKNOWN,
                "error",
                "No ruleset weapon cost matched this assigned weapon.",
                path,
                {"weapon_id": stack.weapon_id, "display_name": stack.display_name},
            )
        )
        return RulesetEntryCost("weapon", stack.weapon_id, stack.display_name, 0)

    refinement = stack.refinement or 1
    override = _matching_override(ruleset, character_match.rule, character, weapon_match.rule)
    cost_source = weapon_match.rule.name
    cost_table = weapon_match.rule.costs_by_refinement
    if override is not None:
        cost_source = f"{override.weapon_name} -> {override.character_name}"
        cost_table = override.costs_by_refinement
        issues.append(
            _issue(
                ISSUE_WEAPON_OVERRIDE_NAME_ONLY_MAPPING,
                "warning",
                "Character-specific weapon override matched by normalized names; no stable override ids exist yet.",
                path,
                {
                    "character": override.character_name,
                    "weapon": override.weapon_name,
                },
            )
        )

    cost = cost_table.get(refinement)
    if cost is None:
        issues.append(
            _issue(
                ISSUE_WEAPON_REFINEMENT_COST_MISSING,
                "error",
                "Ruleset weapon cost table lacks a cost for this refinement.",
                path,
                {
                    "weapon_id": stack.weapon_id,
                    "display_name": stack.display_name,
                    "refinement": refinement,
                },
            )
        )
        cost = 0

    return RulesetEntryCost(
        kind="weapon",
        entry_id=stack.weapon_id,
        display_name=stack.display_name,
        cost=_round_cost(cost),
        quantity=1,
        matched_by=weapon_match.matched_by,
        source=cost_source,
        breakdown={"assigned_cost": _round_cost(cost)},
    )


def _match_character(
    deck_character: DraftCharacter,
    ruleset: TournamentRulesetV1,
    issues: list[RulesetCostIssue],
    path: str,
) -> _CharacterMatch:
    if deck_character.character_id:
        for item in ruleset.characters:
            if item.character_id and item.character_id == deck_character.character_id:
                return _CharacterMatch(item, MATCH_BY_ID)

    candidates = [
        item
        for item in ruleset.characters
        if normalize_catalog_name(item.name)
        == normalize_catalog_name(deck_character.display_name)
    ]
    if len(candidates) > 1:
        issues.append(
            _issue(
                ISSUE_CHARACTER_MATCH_AMBIGUOUS,
                "error",
                "Multiple ruleset character rows matched by display name.",
                path,
                {"display_name": deck_character.display_name},
            )
        )
        return _CharacterMatch(None, MATCH_NONE)
    if candidates:
        issues.append(
            _issue(
                ISSUE_CHARACTER_MATCHED_BY_DISPLAY_NAME_FALLBACK,
                "warning",
                "Ruleset/deck character ids did not align; matched by display name.",
                path,
                {
                    "character_id": deck_character.character_id,
                    "display_name": deck_character.display_name,
                },
            )
        )
        return _CharacterMatch(candidates[0], MATCH_BY_DISPLAY_NAME)
    return _CharacterMatch(None, MATCH_NONE)


def _match_weapon(
    stack: DraftWeaponStack,
    ruleset: TournamentRulesetV1,
    issues: list[RulesetCostIssue],
    path: str,
) -> _WeaponMatch:
    if stack.weapon_id:
        for item in ruleset.weapons:
            if item.weapon_id and item.weapon_id == stack.weapon_id:
                return _WeaponMatch(item, MATCH_BY_ID)

    candidates = [
        item
        for item in ruleset.weapons
        if normalize_catalog_name(item.name) == normalize_catalog_name(stack.display_name)
    ]
    if len(candidates) > 1:
        issues.append(
            _issue(
                ISSUE_WEAPON_MATCH_AMBIGUOUS,
                "error",
                "Multiple ruleset weapon rows matched by display name.",
                path,
                {"display_name": stack.display_name},
            )
        )
        return _WeaponMatch(None, MATCH_NONE)
    if candidates:
        issues.append(
            _issue(
                ISSUE_WEAPON_MATCHED_BY_DISPLAY_NAME_FALLBACK,
                "warning",
                "Ruleset/deck weapon ids did not align; matched by display name.",
                path,
                {
                    "weapon_id": stack.weapon_id,
                    "display_name": stack.display_name,
                },
            )
        )
        return _WeaponMatch(candidates[0], MATCH_BY_DISPLAY_NAME)
    return _WeaponMatch(None, MATCH_NONE)


def _matching_override(
    ruleset: TournamentRulesetV1,
    character_rule: RulesetCharacterCost | None,
    deck_character: DraftCharacter,
    weapon_rule: RulesetWeaponCost,
) -> RulesetWeaponOverride | None:
    character_name = character_rule.name if character_rule else deck_character.display_name
    for override in ruleset.weapon_overrides:
        if normalize_catalog_name(override.weapon_name) != normalize_catalog_name(
            weapon_rule.name
        ):
            continue
        if normalize_catalog_name(override.character_name) == normalize_catalog_name(
            character_name
        ):
            return override
    return None


def _stack_for_ref(deck: DraftDeck, weapon_ref: str) -> DraftWeaponStack | None:
    if weapon_ref in deck.weapon_stack_by_key:
        return deck.weapon_stack_by_key[weapon_ref]
    matches = [item for item in deck.weapons if item.weapon_id == weapon_ref]
    if len(matches) == 1:
        return matches[0]
    return None


def _level_extra_cost(
    deck_character: DraftCharacter,
    rule: RulesetCharacterCost,
) -> float:
    level = deck_character.level or 0
    if level >= 100 and rule.level_100_extra_cost is not None:
        return rule.level_100_extra_cost
    if level >= 95 and rule.level_95_extra_cost is not None:
        return rule.level_95_extra_cost
    return 0


def _issue(
    code: str,
    severity: str,
    message: str,
    path: str,
    details: Mapping[str, Any] | None = None,
) -> RulesetCostIssue:
    return RulesetCostIssue(
        code=code,
        severity=severity,
        message=message,
        path=path,
        details=details or {},
    )


def _round_cost(value: float) -> float:
    return round(float(value), 6)
