"""Ruleset/balance application reports for PvP decks and bundles.

This layer applies parsed ruleset data to existing PvP backend contracts. It is
report-only: it prices and explains known restrictions without deriving or
executing draft schedules from imported ruleset data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from hoyolab_export.tournament_ruleset import (
    TournamentRulesetV1,
    load_tournament_ruleset_json,
)

from .deck import DraftDeck
from .ruleset_applicability import build_ruleset_applicability_report
from .ruleset_costs import (
    MATCH_BY_DISPLAY_NAME,
    MATCH_BY_ID,
    MATCH_NONE,
    WEAPON_COST_MODE_ASSIGNED,
    RulesetDeckCostReport,
    RulesetEntryCost,
    calculate_draft_deck_ruleset_cost,
)
from .schedule import PVP_SEATS, SEAT_PLAYER_1
from .session import PlayerWeaponAssignment
from .session_bundle import PvpSessionBundle


RULESET_BALANCE_REPORT_SCHEMA_VERSION = 1

REPORT_STATUS_READY = "ready"
REPORT_STATUS_PARTIAL = "partial"
REPORT_STATUS_NOT_READY = "not_ready"

RESTRICTION_STATUS_ENFORCED = "enforced"
RESTRICTION_STATUS_REPORT_ONLY = "report_only"
RESTRICTION_STATUS_UNSUPPORTED = "unsupported"
RESTRICTION_STATUS_NOT_ENFORCED = "not_enforced"
RESTRICTION_STATUS_REQUIRES_DRAFT_SYSTEM_ADAPTER = "requires_draft_system_adapter"
RESTRICTION_STATUS_REQUIRES_SOURCE_SPECIFIC_ADAPTER = (
    "requires_source_specific_adapter"
)

ISSUE_RULESET_BALANCE_NO_CHARACTER_COSTS = "ruleset_balance_no_character_costs"
ISSUE_RULESET_BALANCE_COST_ERRORS = "ruleset_balance_cost_errors"
ISSUE_RULESET_BALANCE_MAPPING_FALLBACK = "ruleset_balance_mapping_fallback"
ISSUE_RULESET_BALANCE_UNMATCHED_ENTRY = "ruleset_balance_unmatched_entry"
ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS = (
    "ruleset_balance_override_requires_assignments"
)
ISSUE_RULESET_BALANCE_TIER_RESTRICTIONS_NOT_ENFORCED = (
    "ruleset_balance_tier_restrictions_not_enforced"
)
ISSUE_RULESET_BALANCE_POINT_LIMIT_REPORT_ONLY = (
    "ruleset_balance_point_limit_report_only"
)
ISSUE_RULESET_BALANCE_WEAPON_BAN_POLICY_REPORT_ONLY = (
    "ruleset_balance_weapon_ban_policy_report_only"
)
ISSUE_RULESET_BALANCE_JOKER_CONFIG_REPORT_ONLY = (
    "ruleset_balance_joker_config_report_only"
)
ISSUE_RULESET_BALANCE_SCRIPT_UNSUPPORTED = "ruleset_balance_script_unsupported"
ISSUE_RULESET_BALANCE_SCHEDULE_REQUIRES_ADAPTER = (
    "ruleset_balance_schedule_requires_adapter"
)
ISSUE_RULESET_BALANCE_SPECIAL_BANS_NOT_ENFORCED = (
    "ruleset_balance_special_bans_not_enforced"
)
ISSUE_RULESET_BALANCE_IMMUNE_OR_MIRROR_UNSUPPORTED = (
    "ruleset_balance_immune_or_mirror_unsupported"
)


@dataclass(frozen=True, slots=True)
class RulesetBalanceIssue:
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
class RulesetRestrictionReport:
    code: str
    field: str
    status: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "status": self.status,
            "message": self.message,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class RulesetDeckMatchingSummary:
    character_id_matches: int = 0
    character_fallback_name_matches: int = 0
    character_unmatched: int = 0
    weapon_id_matches: int = 0
    weapon_fallback_name_matches: int = 0
    weapon_unmatched: int = 0

    @property
    def fallback_mapping_count(self) -> int:
        return self.character_fallback_name_matches + self.weapon_fallback_name_matches

    def to_dict(self) -> dict[str, int]:
        return {
            "character_id_matches": self.character_id_matches,
            "character_fallback_name_matches": self.character_fallback_name_matches,
            "character_unmatched": self.character_unmatched,
            "weapon_id_matches": self.weapon_id_matches,
            "weapon_fallback_name_matches": self.weapon_fallback_name_matches,
            "weapon_unmatched": self.weapon_unmatched,
            "fallback_mapping_count": self.fallback_mapping_count,
        }


@dataclass(frozen=True, slots=True)
class RulesetDeckCostSummary:
    character_cost_total: float
    weapon_cost_total: float
    total_cost: float
    costs_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_cost_total": self.character_cost_total,
            "weapon_cost_total": self.weapon_cost_total,
            "total_cost": self.total_cost,
            "costs_ready": self.costs_ready,
        }


@dataclass(frozen=True, slots=True)
class RulesetCharacterBalanceRow:
    character_id: str
    display_name: str
    constellation: int | None
    level: int | None
    matched_by: str
    base_cost: float
    level_extra_cost: float
    total_cost: float
    issue_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "display_name": self.display_name,
            "constellation": self.constellation,
            "level": self.level,
            "matched_by": self.matched_by,
            "base_cost": self.base_cost,
            "level_extra_cost": self.level_extra_cost,
            "total_cost": self.total_cost,
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class RulesetWeaponBalanceRow:
    weapon_id: str
    display_name: str
    refinement: int | None
    level: int | None
    count: int
    matched_by: str
    base_cost: float
    override_cost: float | None
    total_cost: float
    issue_codes: tuple[str, ...] = ()
    character_id: str = ""
    weapon_stack_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "display_name": self.display_name,
            "refinement": self.refinement,
            "level": self.level,
            "count": self.count,
            "matched_by": self.matched_by,
            "base_cost": self.base_cost,
            "override_cost": self.override_cost,
            "total_cost": self.total_cost,
            "issue_codes": list(self.issue_codes),
            "character_id": self.character_id,
            "weapon_stack_key": self.weapon_stack_key,
        }


@dataclass(frozen=True, slots=True)
class RulesetDeckApplicationReport:
    schema_version: int
    ruleset_summary: Mapping[str, Any]
    deck_summary: Mapping[str, Any]
    matching_summary: RulesetDeckMatchingSummary
    cost_summary: RulesetDeckCostSummary
    character_rows: tuple[RulesetCharacterBalanceRow, ...]
    weapon_rows: tuple[RulesetWeaponBalanceRow, ...]
    restrictions: tuple[RulesetRestrictionReport, ...]
    issues: tuple[RulesetBalanceIssue, ...]
    status: str

    @property
    def ready(self) -> bool:
        return self.status != REPORT_STATUS_NOT_READY

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ruleset_summary": dict(sorted(self.ruleset_summary.items())),
            "deck_summary": dict(sorted(self.deck_summary.items())),
            "matching_summary": self.matching_summary.to_dict(),
            "cost_summary": self.cost_summary.to_dict(),
            "character_rows": [item.to_dict() for item in self.character_rows],
            "weapon_rows": [item.to_dict() for item in self.weapon_rows],
            "restrictions": [item.to_dict() for item in self.restrictions],
            "issues": [item.to_dict() for item in self.issues],
            "status": self.status,
            "ready": self.ready,
        }


def apply_ruleset_balance_to_deck(
    deck: DraftDeck,
    ruleset: TournamentRulesetV1,
    *,
    seat: str = "",
    weapon_assignment: PlayerWeaponAssignment | Mapping[str, str] | None = None,
) -> RulesetDeckApplicationReport:
    assignment_map = _assignment_map(weapon_assignment)
    cost_report = calculate_draft_deck_ruleset_cost(
        deck,
        ruleset,
        weapon_assignments_by_character_id=assignment_map,
    )
    applicability = build_ruleset_applicability_report(ruleset)
    restrictions = _restriction_reports(ruleset, bool(assignment_map))
    issues = _application_issues(cost_report, applicability, restrictions, bool(assignment_map))
    character_rows = _character_rows(deck, cost_report)
    weapon_rows = _weapon_rows(deck, cost_report, assignment_map)
    matching = _matching_summary(cost_report)
    cost_summary = RulesetDeckCostSummary(
        character_cost_total=cost_report.character_total,
        weapon_cost_total=cost_report.weapon_total,
        total_cost=cost_report.total_cost,
        costs_ready=cost_report.ready,
    )
    status = _report_status(cost_report, issues)
    return RulesetDeckApplicationReport(
        schema_version=RULESET_BALANCE_REPORT_SCHEMA_VERSION,
        ruleset_summary={
            "ruleset_name": ruleset.name,
            "source": ruleset.source,
            "source_url": ruleset.source_url,
            "language": ruleset.language,
            "parser_status": applicability.parser_status,
            "applicability_issue_codes": list(applicability.issue_codes()),
        },
        deck_summary={
            "deck_name": deck.deck_name,
            "seat": seat,
            "nickname": deck.player.nickname,
            "character_count": len(deck.characters),
            "weapon_stack_count": len(deck.weapons),
            "weapon_cost_mode": cost_report.weapon_cost_mode,
        },
        matching_summary=matching,
        cost_summary=cost_summary,
        character_rows=character_rows,
        weapon_rows=weapon_rows,
        restrictions=restrictions,
        issues=tuple(issues),
        status=status,
    )


def apply_ruleset_balance_to_bundle(
    bundle: PvpSessionBundle,
    ruleset: TournamentRulesetV1,
    *,
    seats: tuple[str, ...] = PVP_SEATS,
) -> Mapping[str, Any]:
    reports = {
        seat: apply_ruleset_balance_to_deck(
            bundle.decks[seat],
            ruleset,
            seat=seat,
            weapon_assignment=bundle.weapon_assignments.get(seat),
        )
        for seat in seats
        if seat in bundle.decks
    }
    return _bundle_balance_summary(ruleset, reports)


def attach_ruleset_balance_summary_to_bundle(
    bundle: PvpSessionBundle,
    ruleset: TournamentRulesetV1,
    *,
    seats: tuple[str, ...] = PVP_SEATS,
) -> PvpSessionBundle:
    summary = apply_ruleset_balance_to_bundle(bundle, ruleset, seats=seats)
    reports = {**dict(bundle.reports), "ruleset_balance": summary}
    balance_ref = {
        "ruleset_name": ruleset.name,
        "source": ruleset.source,
        "source_url": ruleset.source_url,
        "language": ruleset.language,
    }
    return replace(bundle, balance_ref=balance_ref, reports=reports)


def load_ruleset_balance_smoke_ruleset(path: str | Path) -> TournamentRulesetV1:
    return load_tournament_ruleset_json(path)


def _application_issues(
    cost_report: RulesetDeckCostReport,
    applicability: Any,
    restrictions: tuple[RulesetRestrictionReport, ...],
    has_assignments: bool,
) -> list[RulesetBalanceIssue]:
    issues: list[RulesetBalanceIssue] = []
    cost_error_codes = sorted(
        {issue.code for issue in cost_report.issues if issue.severity == "error"}
    )
    fallback_codes = sorted(
        {issue.code for issue in cost_report.issues if "fallback" in issue.code}
    )
    unmatched = (
        cost_report.character_entries
        and any(item.matched_by == MATCH_NONE for item in cost_report.character_entries)
    ) or any(item.matched_by == MATCH_NONE for item in cost_report.weapon_entries)
    if not applicability.has_character_costs:
        issues.append(
            _issue(
                ISSUE_RULESET_BALANCE_NO_CHARACTER_COSTS,
                "error",
                "Ruleset has no parsed character costs.",
            )
        )
    if cost_error_codes:
        issues.append(
            _issue(
                ISSUE_RULESET_BALANCE_COST_ERRORS,
                "error",
                "Ruleset balance application has cost errors.",
                details={"cost_issue_codes": cost_error_codes},
            )
        )
    if fallback_codes:
        issues.append(
            _issue(
                ISSUE_RULESET_BALANCE_MAPPING_FALLBACK,
                "warning",
                "Some deck entries matched only by display-name fallback.",
                details={"cost_issue_codes": fallback_codes},
            )
        )
    if unmatched:
        issues.append(
            _issue(
                ISSUE_RULESET_BALANCE_UNMATCHED_ENTRY,
                "error",
                "One or more deck entries did not match the ruleset.",
            )
        )
    if not has_assignments and applicability.has_character_weapon_overrides:
        issues.append(
            _issue(
                ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS,
                "warning",
                "Character-specific weapon overrides require weapon assignment context.",
            )
        )
    for restriction in restrictions:
        if restriction.status == RESTRICTION_STATUS_UNSUPPORTED:
            severity = "warning"
        elif restriction.status in {
            RESTRICTION_STATUS_REPORT_ONLY,
            RESTRICTION_STATUS_NOT_ENFORCED,
            RESTRICTION_STATUS_REQUIRES_DRAFT_SYSTEM_ADAPTER,
            RESTRICTION_STATUS_REQUIRES_SOURCE_SPECIFIC_ADAPTER,
        }:
            severity = "warning"
        else:
            continue
        issues.append(
            _issue(
                restriction.code,
                severity,
                restriction.message,
                path=restriction.field,
                details=restriction.details,
            )
        )
    return issues


def _restriction_reports(
    ruleset: TournamentRulesetV1,
    has_assignments: bool,
) -> tuple[RulesetRestrictionReport, ...]:
    restrictions: list[RulesetRestrictionReport] = []
    tier_restrictions = tuple(
        restriction
        for tier in ruleset.tiers
        for restriction in tier.restrictions
    )
    if tier_restrictions:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_TIER_RESTRICTIONS_NOT_ENFORCED,
                "tiers.restrictions",
                RESTRICTION_STATUS_NOT_ENFORCED,
                "Tier restrictions are known but not enforced by PvP v0 yet.",
                {"count": len(tier_restrictions)},
            )
        )
    if ruleset.draft_config.deck_point_limit is not None:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_POINT_LIMIT_REPORT_ONLY,
                "draft_config.deck_point_limit",
                RESTRICTION_STATUS_REPORT_ONLY,
                "Deck point limit is reported but not enforced by this layer.",
                {"deck_point_limit": ruleset.draft_config.deck_point_limit},
            )
        )
    if ruleset.draft_config.weapon_ban_location or ruleset.draft_config.weapon_ban_count is not None:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_WEAPON_BAN_POLICY_REPORT_ONLY,
                "draft_config.weapon_ban",
                RESTRICTION_STATUS_REPORT_ONLY,
                "Weapon ban config is reported but not executed by this layer.",
                {
                    "weapon_ban_location": ruleset.draft_config.weapon_ban_location,
                    "weapon_ban_count": ruleset.draft_config.weapon_ban_count,
                },
            )
        )
    if (
        ruleset.draft_config.joker_interval is not None
        or ruleset.draft_config.joker_limit is not None
        or ruleset.draft_config.extra_ban_interval is not None
    ):
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_JOKER_CONFIG_REPORT_ONLY,
                "draft_config.joker_extra_bans",
                RESTRICTION_STATUS_REPORT_ONLY,
                "Joker/extra-ban config is reported but not executed by this layer.",
                {
                    "joker_interval": ruleset.draft_config.joker_interval,
                    "joker_limit": ruleset.draft_config.joker_limit,
                    "extra_ban_interval": ruleset.draft_config.extra_ban_interval,
                },
            )
        )
    if ruleset.draft_config.script_code:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_SCRIPT_UNSUPPORTED,
                "draft_config.script_code",
                RESTRICTION_STATUS_UNSUPPORTED,
                "Custom source scripts are unsupported and are never executed.",
                {"script_code_present": True},
            )
        )
    if ruleset.draft_config.challenge_type or ruleset.draft_config.initial_bans is not None:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_SCHEDULE_REQUIRES_ADAPTER,
                "draft_config.schedule",
                RESTRICTION_STATUS_REQUIRES_DRAFT_SYSTEM_ADAPTER,
                "Draft config knobs are not an executable schedule.",
                {
                    "challenge_type": ruleset.draft_config.challenge_type,
                    "initial_bans": ruleset.draft_config.initial_bans,
                },
            )
        )
    if ruleset.special_bans:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_SPECIAL_BANS_NOT_ENFORCED,
                "special_bans",
                RESTRICTION_STATUS_NOT_ENFORCED,
                "Ruleset-level special/permanent bans are not enforced yet.",
                {"count": len(ruleset.special_bans)},
            )
        )
    if _mentions_immune_or_mirror(ruleset):
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_IMMUNE_OR_MIRROR_UNSUPPORTED,
                "notes",
                RESTRICTION_STATUS_UNSUPPORTED,
                "Immune/mirror concepts are reserved but unsupported in v0.",
            )
        )
    if ruleset.weapon_overrides and not has_assignments:
        restrictions.append(
            _restriction(
                ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS,
                "weapon_overrides",
                RESTRICTION_STATUS_REPORT_ONLY,
                "Weapon overrides were not evaluated because no assignments were provided.",
                {"override_count": len(ruleset.weapon_overrides)},
            )
        )
    return tuple(restrictions)


def _character_rows(
    deck: DraftDeck,
    cost_report: RulesetDeckCostReport,
) -> tuple[RulesetCharacterBalanceRow, ...]:
    return tuple(
        RulesetCharacterBalanceRow(
            character_id=character.character_id,
            display_name=character.display_name,
            constellation=character.constellation,
            level=character.level,
            matched_by=entry.matched_by,
            base_cost=entry.breakdown.get("constellation_cost", 0),
            level_extra_cost=entry.breakdown.get("level_extra_cost", 0),
            total_cost=entry.cost,
            issue_codes=_issue_codes_for_path(cost_report, f"characters[{index}]"),
        )
        for index, (character, entry) in enumerate(
            zip(deck.characters, cost_report.character_entries)
        )
    )


def _weapon_rows(
    deck: DraftDeck,
    cost_report: RulesetDeckCostReport,
    assignment_map: Mapping[str, str] | None,
) -> tuple[RulesetWeaponBalanceRow, ...]:
    if cost_report.weapon_cost_mode == WEAPON_COST_MODE_ASSIGNED and assignment_map:
        rows: list[RulesetWeaponBalanceRow] = []
        for index, (character_id, weapon_ref) in enumerate(sorted(assignment_map.items())):
            stack = deck.weapon_stack_by_key.get(weapon_ref) or _stack_by_weapon_id(deck, weapon_ref)
            entry = cost_report.weapon_entries[index]
            rows.append(
                RulesetWeaponBalanceRow(
                    weapon_id=stack.weapon_id if stack else weapon_ref,
                    display_name=stack.display_name if stack else entry.display_name,
                    refinement=stack.refinement if stack else None,
                    level=stack.level if stack else None,
                    count=1,
                    matched_by=entry.matched_by,
                    base_cost=entry.breakdown.get("base_refinement_cost", 0),
                    override_cost=entry.breakdown.get("override_cost") or None,
                    total_cost=entry.cost,
                    issue_codes=_issue_codes_for_path(
                        cost_report,
                        f"weapon_assignments[{index}]",
                    ),
                    character_id=character_id,
                    weapon_stack_key=stack.stack_key if stack else weapon_ref,
                )
            )
        return tuple(rows)
    return tuple(
        RulesetWeaponBalanceRow(
            weapon_id=stack.weapon_id,
            display_name=stack.display_name,
            refinement=stack.refinement,
            level=stack.level,
            count=stack.count or 0,
            matched_by=entry.matched_by,
            base_cost=entry.breakdown.get("per_copy_cost", 0),
            override_cost=None,
            total_cost=entry.cost,
            issue_codes=_issue_codes_for_path(cost_report, f"weapons[{index}]"),
            weapon_stack_key=stack.stack_key,
        )
        for index, (stack, entry) in enumerate(zip(deck.weapons, cost_report.weapon_entries))
    )


def _matching_summary(cost_report: RulesetDeckCostReport) -> RulesetDeckMatchingSummary:
    return RulesetDeckMatchingSummary(
        character_id_matches=sum(
            1 for item in cost_report.character_entries if item.matched_by == MATCH_BY_ID
        ),
        character_fallback_name_matches=sum(
            1
            for item in cost_report.character_entries
            if item.matched_by == MATCH_BY_DISPLAY_NAME
        ),
        character_unmatched=sum(
            1 for item in cost_report.character_entries if item.matched_by == MATCH_NONE
        ),
        weapon_id_matches=sum(
            1 for item in cost_report.weapon_entries if item.matched_by == MATCH_BY_ID
        ),
        weapon_fallback_name_matches=sum(
            1 for item in cost_report.weapon_entries if item.matched_by == MATCH_BY_DISPLAY_NAME
        ),
        weapon_unmatched=sum(
            1 for item in cost_report.weapon_entries if item.matched_by == MATCH_NONE
        ),
    )


def _bundle_balance_summary(
    ruleset: TournamentRulesetV1,
    reports: Mapping[str, RulesetDeckApplicationReport],
) -> Mapping[str, Any]:
    return {
        "schema_version": RULESET_BALANCE_REPORT_SCHEMA_VERSION,
        "ruleset": {
            "name": ruleset.name,
            "source": ruleset.source,
            "source_url": ruleset.source_url,
            "language": ruleset.language,
        },
        "seats": {
            seat: {
                "status": report.status,
                "total_cost": report.cost_summary.total_cost,
                "character_cost_total": report.cost_summary.character_cost_total,
                "weapon_cost_total": report.cost_summary.weapon_cost_total,
                "costs_ready": report.cost_summary.costs_ready,
                "issue_codes": list(report.issue_codes()),
                "matching_summary": report.matching_summary.to_dict(),
            }
            for seat, report in sorted(reports.items())
        },
    }


def _assignment_map(
    weapon_assignment: PlayerWeaponAssignment | Mapping[str, str] | None,
) -> Mapping[str, str] | None:
    if weapon_assignment is None:
        return None
    if isinstance(weapon_assignment, PlayerWeaponAssignment):
        return {
            item.character_id: item.weapon_stack_key
            for item in weapon_assignment.assignments
        }
    return dict(weapon_assignment)


def _report_status(
    cost_report: RulesetDeckCostReport,
    issues: list[RulesetBalanceIssue],
) -> str:
    if not cost_report.ready or any(issue.severity == "error" for issue in issues):
        return REPORT_STATUS_NOT_READY
    if issues:
        return REPORT_STATUS_PARTIAL
    return REPORT_STATUS_READY


def _issue_codes_for_path(
    cost_report: RulesetDeckCostReport,
    path: str,
) -> tuple[str, ...]:
    return tuple(issue.code for issue in cost_report.issues if issue.path == path)


def _stack_by_weapon_id(deck: DraftDeck, weapon_id: str) -> Any:
    matches = [item for item in deck.weapons if item.weapon_id == weapon_id]
    return matches[0] if len(matches) == 1 else None


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> RulesetBalanceIssue:
    return RulesetBalanceIssue(
        code=code,
        severity=severity,
        message=message,
        path=path,
        details=details or {},
    )


def _restriction(
    code: str,
    field: str,
    status: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> RulesetRestrictionReport:
    return RulesetRestrictionReport(
        code=code,
        field=field,
        status=status,
        message=message,
        details=details or {},
    )


def _mentions_immune_or_mirror(ruleset: TournamentRulesetV1) -> bool:
    text = " ".join((ruleset.notes, ruleset.draft_config.notes)).casefold()
    return "immune" in text or "mirror" in text
