"""Research report for mapping parsed tournament rulesets onto PvP v0.

This module is intentionally report-only. It consumes the parked
`TournamentRulesetV1` source parser and explains which fields are usable by the
current backend without turning Gentor/Abyss/custom rules into executable PvP
logic prematurely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from hoyolab_export.tournament_ruleset import (
    KNOWN_TIER_RESTRICTION_TYPES,
    TournamentRulesetV1,
)


ISSUE_NO_CHARACTER_COSTS = "no_character_costs"
ISSUE_NO_WEAPON_COSTS = "no_weapon_costs"
ISSUE_TIER_RESTRICTIONS_NOT_ENFORCED = "tier_restrictions_not_enforced"
ISSUE_UNKNOWN_TIER_RESTRICTION_TYPE = "unknown_tier_restriction_type"
ISSUE_SPECIAL_BANS_NOT_ENFORCED = "special_bans_not_enforced"
ISSUE_UNSUPPORTED_SCRIPT_RULE = "unsupported_script_rule"
ISSUE_UNSUPPORTED_IMMUNE_OR_MIRROR_RULE = "unsupported_immune_or_mirror_rule"
ISSUE_UNSUPPORTED_TRAVELER_RULESET_ENTRY = "unsupported_traveler_ruleset_entry"
ISSUE_SCHEDULE_MISSING_EXPLICIT_FLOW = "schedule_missing_explicit_flow"
ISSUE_SCHEDULE_DERIVATION_REQUIRES_ADAPTER = "schedule_derivation_requires_adapter"
ISSUE_SCHEDULE_MISSING_DRAFT_CONFIG = "schedule_missing_draft_config"

SCHEDULE_STATUS_MISSING_DRAFT_CONFIG = "missing_draft_config"
SCHEDULE_STATUS_MISSING_EXPLICIT_FLOW = "missing_explicit_flow"
SCHEDULE_STATUS_REQUIRES_SCRIPT_ADAPTER = "requires_script_adapter"
SCHEDULE_STATUS_REQUIRES_RULESET_ADAPTER = "requires_ruleset_adapter"

TRAVELER_CHARACTER_IDS = frozenset({"10000005", "10000007"})
TRAVELER_NAMES = frozenset({"traveler"})


@dataclass(frozen=True, slots=True)
class RulesetApplicabilityIssue:
    code: str
    severity: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class RulesetScheduleDerivationReport:
    status: str
    supported: bool
    reason: str
    missing_fields: tuple[str, ...] = ()
    unsupported_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "reason": self.reason,
            "missing_fields": list(self.missing_fields),
            "unsupported_fields": list(self.unsupported_fields),
        }


@dataclass(frozen=True, slots=True)
class RulesetApplicabilityReport:
    ruleset_name: str
    source: str
    source_url: str
    parser_status: str
    character_cost_count: int
    weapon_cost_count: int
    weapon_override_count: int
    tier_count: int
    has_character_costs: bool
    has_weapon_costs: bool
    has_character_weapon_overrides: bool
    has_tiers: bool
    has_tier_restrictions: bool
    has_deck_point_limit: bool
    has_draft_config_inputs: bool
    has_special_bans: bool
    has_unsupported_script_rules: bool
    has_unsupported_immune_or_mirror_rules: bool
    has_unsupported_traveler_entries: bool
    cost_preview_supported: bool
    schedule_derivation: RulesetScheduleDerivationReport
    issues: tuple[RulesetApplicabilityIssue, ...] = ()

    @property
    def ready_for_cost_preview(self) -> bool:
        return self.cost_preview_supported

    @property
    def ready_for_schedule_execution(self) -> bool:
        return self.schedule_derivation.supported

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_name": self.ruleset_name,
            "source": self.source,
            "source_url": self.source_url,
            "parser_status": self.parser_status,
            "character_cost_count": self.character_cost_count,
            "weapon_cost_count": self.weapon_cost_count,
            "weapon_override_count": self.weapon_override_count,
            "tier_count": self.tier_count,
            "has_character_costs": self.has_character_costs,
            "has_weapon_costs": self.has_weapon_costs,
            "has_character_weapon_overrides": self.has_character_weapon_overrides,
            "has_tiers": self.has_tiers,
            "has_tier_restrictions": self.has_tier_restrictions,
            "has_deck_point_limit": self.has_deck_point_limit,
            "has_draft_config_inputs": self.has_draft_config_inputs,
            "has_special_bans": self.has_special_bans,
            "has_unsupported_script_rules": self.has_unsupported_script_rules,
            "has_unsupported_immune_or_mirror_rules": (
                self.has_unsupported_immune_or_mirror_rules
            ),
            "has_unsupported_traveler_entries": self.has_unsupported_traveler_entries,
            "cost_preview_supported": self.cost_preview_supported,
            "ready_for_schedule_execution": self.ready_for_schedule_execution,
            "schedule_derivation": self.schedule_derivation.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def build_ruleset_applicability_report(
    ruleset: TournamentRulesetV1,
) -> RulesetApplicabilityReport:
    issues: list[RulesetApplicabilityIssue] = []
    character_cost_count = sum(
        1 for item in ruleset.characters if item.costs_by_constellation
    )
    weapon_cost_count = sum(1 for item in ruleset.weapons if item.costs_by_refinement)
    tier_restrictions = tuple(
        restriction
        for tier in ruleset.tiers
        for restriction in tier.restrictions
    )
    unknown_tier_restrictions = tuple(
        restriction
        for restriction in tier_restrictions
        if restriction.restriction_type not in KNOWN_TIER_RESTRICTION_TYPES
    )
    traveler_entries = tuple(
        item
        for item in ruleset.characters
        if item.character_id in TRAVELER_CHARACTER_IDS
        or item.name.strip().casefold() in TRAVELER_NAMES
    )
    has_immune_or_mirror = _mentions_immune_or_mirror(ruleset)

    if character_cost_count == 0:
        issues.append(
            _issue(
                ISSUE_NO_CHARACTER_COSTS,
                "error",
                "Ruleset has no parsed character constellation costs.",
            )
        )
    if weapon_cost_count == 0:
        issues.append(
            _issue(
                ISSUE_NO_WEAPON_COSTS,
                "warning",
                "Ruleset has no parsed weapon refinement costs.",
            )
        )
    if tier_restrictions:
        issues.append(
            _issue(
                ISSUE_TIER_RESTRICTIONS_NOT_ENFORCED,
                "warning",
                "PvP v0 reports tier restrictions but does not enforce them yet.",
                {"count": len(tier_restrictions)},
            )
        )
    if unknown_tier_restrictions:
        issues.append(
            _issue(
                ISSUE_UNKNOWN_TIER_RESTRICTION_TYPE,
                "warning",
                "Ruleset contains tier restriction types outside the known parser set.",
                {
                    "restriction_types": sorted(
                        {item.restriction_type for item in unknown_tier_restrictions}
                    )
                },
            )
        )
    if ruleset.special_bans:
        issues.append(
            _issue(
                ISSUE_SPECIAL_BANS_NOT_ENFORCED,
                "warning",
                "PvP v0 does not enforce ruleset-level special/permanent bans yet.",
                {"count": len(ruleset.special_bans)},
            )
        )
    if ruleset.draft_config.script_code:
        issues.append(
            _issue(
                ISSUE_UNSUPPORTED_SCRIPT_RULE,
                "warning",
                "Ruleset contains custom script draft logic; PvP v0 does not execute it.",
                {"field": "draft_config.script_code"},
            )
        )
    if has_immune_or_mirror:
        issues.append(
            _issue(
                ISSUE_UNSUPPORTED_IMMUNE_OR_MIRROR_RULE,
                "warning",
                "Ruleset text mentions immune/mirror concepts that PvP v0 has reserved but not implemented.",
            )
        )
    if traveler_entries:
        issues.append(
            _issue(
                ISSUE_UNSUPPORTED_TRAVELER_RULESET_ENTRY,
                "warning",
                "Ruleset includes Traveler entries, while PvP v0 deck validation rejects Traveler conservatively.",
                {"count": len(traveler_entries)},
            )
        )

    schedule_derivation = analyze_ruleset_schedule_derivation(ruleset)
    issues.extend(_schedule_issues(schedule_derivation))

    return RulesetApplicabilityReport(
        ruleset_name=ruleset.name,
        source=ruleset.source,
        source_url=ruleset.source_url,
        parser_status="parsed_tournament_ruleset_v1",
        character_cost_count=character_cost_count,
        weapon_cost_count=weapon_cost_count,
        weapon_override_count=len(ruleset.weapon_overrides),
        tier_count=len(ruleset.tiers),
        has_character_costs=character_cost_count > 0,
        has_weapon_costs=weapon_cost_count > 0,
        has_character_weapon_overrides=bool(ruleset.weapon_overrides),
        has_tiers=bool(ruleset.tiers),
        has_tier_restrictions=bool(tier_restrictions),
        has_deck_point_limit=ruleset.draft_config.deck_point_limit is not None,
        has_draft_config_inputs=_has_draft_config_inputs(ruleset),
        has_special_bans=bool(ruleset.special_bans),
        has_unsupported_script_rules=bool(ruleset.draft_config.script_code),
        has_unsupported_immune_or_mirror_rules=has_immune_or_mirror,
        has_unsupported_traveler_entries=bool(traveler_entries),
        cost_preview_supported=character_cost_count > 0,
        schedule_derivation=schedule_derivation,
        issues=tuple(issues),
    )


def analyze_ruleset_schedule_derivation(
    ruleset: TournamentRulesetV1,
) -> RulesetScheduleDerivationReport:
    if ruleset.draft_config.script_code:
        return RulesetScheduleDerivationReport(
            status=SCHEDULE_STATUS_REQUIRES_SCRIPT_ADAPTER,
            supported=False,
            reason=(
                "The parsed ruleset has custom script code. PvP v0 intentionally "
                "does not execute or translate source-site scripts."
            ),
            missing_fields=(
                "explicit_pick_ban_flow",
                "seat_order",
                "per_step_action_counts",
            ),
            unsupported_fields=("draft_config.script_code",),
        )

    if _has_draft_config_inputs(ruleset):
        return RulesetScheduleDerivationReport(
            status=SCHEDULE_STATUS_MISSING_EXPLICIT_FLOW,
            supported=False,
            reason=(
                "The ruleset has useful draft knobs, but not a complete explicit "
                "pick/ban flow that can become a DraftSchedule safely."
            ),
            missing_fields=(
                "explicit_pick_ban_flow",
                "seat_order",
                "per_step_action_counts",
            ),
        )

    return RulesetScheduleDerivationReport(
        status=SCHEDULE_STATUS_MISSING_DRAFT_CONFIG,
        supported=False,
        reason="The ruleset has no parsed draft config inputs.",
        missing_fields=(
            "draft_config",
            "explicit_pick_ban_flow",
            "seat_order",
            "per_step_action_counts",
        ),
    )


def _has_draft_config_inputs(ruleset: TournamentRulesetV1) -> bool:
    draft = ruleset.draft_config
    return any(
        (
            draft.challenge_type,
            draft.deck_point_limit is not None,
            draft.initial_bans is not None,
            draft.extra_ban_interval is not None,
            draft.joker_interval is not None,
            draft.joker_limit is not None,
            draft.weapon_ban_location,
            draft.weapon_ban_count is not None,
            draft.script_code,
            draft.notes,
        )
    )


def _schedule_issues(
    schedule_derivation: RulesetScheduleDerivationReport,
) -> tuple[RulesetApplicabilityIssue, ...]:
    if schedule_derivation.supported:
        return ()
    if schedule_derivation.status == SCHEDULE_STATUS_MISSING_DRAFT_CONFIG:
        return (
            _issue(
                ISSUE_SCHEDULE_MISSING_DRAFT_CONFIG,
                "warning",
                "No draft config was parsed, so no PvP schedule can be derived.",
                {"missing_fields": list(schedule_derivation.missing_fields)},
            ),
        )
    if schedule_derivation.status == SCHEDULE_STATUS_MISSING_EXPLICIT_FLOW:
        return (
            _issue(
                ISSUE_SCHEDULE_MISSING_EXPLICIT_FLOW,
                "warning",
                "Draft config is not enough to derive a deterministic PvP schedule.",
                {"missing_fields": list(schedule_derivation.missing_fields)},
            ),
            _issue(
                ISSUE_SCHEDULE_DERIVATION_REQUIRES_ADAPTER,
                "warning",
                "A source-specific schedule adapter is required before execution.",
                {"status": schedule_derivation.status},
            ),
        )
    return (
        _issue(
            ISSUE_SCHEDULE_DERIVATION_REQUIRES_ADAPTER,
            "warning",
            "A source-specific schedule adapter is required before execution.",
            {
                "status": schedule_derivation.status,
                "unsupported_fields": list(schedule_derivation.unsupported_fields),
            },
        ),
    )


def _mentions_immune_or_mirror(ruleset: TournamentRulesetV1) -> bool:
    text = " ".join(
        (
            ruleset.notes,
            ruleset.draft_config.notes,
            " ".join(ruleset.special_bans),
        )
    ).casefold()
    return "immune" in text or "mirror" in text


def _issue(
    code: str,
    severity: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> RulesetApplicabilityIssue:
    return RulesetApplicabilityIssue(
        code=code,
        severity=severity,
        message=message,
        details=details or {},
    )
