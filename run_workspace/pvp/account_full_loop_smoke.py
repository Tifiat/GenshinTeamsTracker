"""Backend-only full-loop smoke over a local account Free Draft deck.

The smoke exports player 1 from the existing local account deck boundary, copies
that deck into an independent player 2 scope, then lets the deterministic
planner exercise the draft reducer, team assignment, weapon assignment, replay,
and match result paths. It does not start UI code or write deck files.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from .account_deck_copy import copy_deck_for_player_2
from .account_deck_export import (
    AccountDeckDataProvider,
    AccountDeckExportOptions,
    AccountDeckExportReport,
    LocalAccountSQLiteDeckDataProvider,
    export_free_draft_deck_from_account,
)
from .draft_system import (
    DRAFT_SYSTEM_FREE_DRAFT_V0,
    DraftSystemDefinition,
    require_draft_system,
)
from .free_draft_planner import (
    FreeDraftActionPlanReport,
    FreeDraftTeamPlanReport,
    FreeDraftWeaponPlanReport,
    plan_free_draft_actions,
    plan_free_draft_team_assignment,
    plan_free_draft_weapon_assignment,
)
from .match_result import (
    ChamberTimer,
    MatchResult,
    PlayerMatchTimers,
    calculate_match_result,
)
from .schedule import SEAT_PLAYER_1, SEAT_PLAYER_2, DraftSchedule
from .session import (
    DraftSessionState,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    replay_draft_actions,
)
from .validation import (
    SEVERITY_ERROR,
    DeckValidationReport,
    validate_draft_deck,
)


ISSUE_ACCOUNT_DECK_EXPORT_INVALID = "account_deck_export_invalid"
ISSUE_PLAYER_1_DECK_INVALID = "player_1_deck_invalid"
ISSUE_PLAYER_2_DECK_INVALID = "player_2_deck_invalid"
ISSUE_DRAFT_PLAN_NOT_READY = "draft_plan_not_ready"
ISSUE_DRAFT_REPLAY_FAILED = "draft_replay_failed"
ISSUE_DRAFT_REPLAY_DIVERGED = "draft_replay_diverged"
ISSUE_TEAM_PLAN_NOT_READY = "team_plan_not_ready"
ISSUE_WEAPON_PLAN_NOT_READY = "weapon_plan_not_ready"


@dataclass(frozen=True, slots=True)
class AccountFullLoopSmokeIssue:
    code: str
    severity: str
    message: str = ""
    seat: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "seat": self.seat,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class AccountFullLoopSeatSummary:
    seat: str
    nickname: str
    deck_name: str
    validation_status: str
    character_count: int
    weapon_stack_count: int
    banned_character_ids: tuple[str, ...] = ()
    picked_character_ids: tuple[str, ...] = ()
    teams: PlayerTeamAssignment | None = None
    weapons: PlayerWeaponAssignment | None = None
    team_status: str = "not_run"
    weapon_status: str = "not_run"
    timer_total_seconds: int = 0
    weapon_stack_usage: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "nickname": self.nickname,
            "deck_name": self.deck_name,
            "validation_status": self.validation_status,
            "character_count": self.character_count,
            "weapon_stack_count": self.weapon_stack_count,
            "banned_character_ids": list(self.banned_character_ids),
            "picked_character_ids": list(self.picked_character_ids),
            "teams": self.teams.to_dict() if self.teams is not None else None,
            "weapons": self.weapons.to_dict() if self.weapons is not None else None,
            "team_status": self.team_status,
            "weapon_status": self.weapon_status,
            "timer_total_seconds": self.timer_total_seconds,
            "weapon_stack_usage": dict(sorted(self.weapon_stack_usage.items())),
        }


@dataclass(frozen=True, slots=True)
class AccountFullLoopSmokeReport:
    export_report: AccountDeckExportReport
    player_2_deck: DraftDeck
    player_1_validation: DeckValidationReport
    player_2_validation: DeckValidationReport
    action_plan: FreeDraftActionPlanReport | None = None
    player_1_team_plan: FreeDraftTeamPlanReport | None = None
    player_2_team_plan: FreeDraftTeamPlanReport | None = None
    player_1_weapon_plan: FreeDraftWeaponPlanReport | None = None
    player_2_weapon_plan: FreeDraftWeaponPlanReport | None = None
    match_result: MatchResult | None = None
    replay_state_hash: str = ""
    issues: tuple[AccountFullLoopSmokeIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.export_report.ready
            and self.player_1_validation.ready
            and self.player_2_validation.ready
            and self.action_plan is not None
            and self.action_plan.ready
            and self.player_1_team_plan is not None
            and self.player_1_team_plan.ready
            and self.player_2_team_plan is not None
            and self.player_2_team_plan.ready
            and self.player_1_weapon_plan is not None
            and self.player_1_weapon_plan.ready
            and self.player_2_weapon_plan is not None
            and self.player_2_weapon_plan.ready
            and self.match_result is not None
            and not _has_error_issues(self.issues)
        )

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        counts = self.export_report.counts
        final_state = self._final_state()
        return {
            "ready": self.ready,
            "source_summary": dict(sorted(self.export_report.source_summary.items())),
            "export": {
                "ready": self.export_report.ready,
                "issue_codes": list(self.export_report.issue_codes()),
                "validation_report": self.export_report.validation_report.to_dict(),
                "counts": counts.to_dict(),
            },
            "player_1_validation": self.player_1_validation.to_dict(),
            "player_2_validation": self.player_2_validation.to_dict(),
            "player_2_copy": {
                "same_object": self.export_report.deck is self.player_2_deck,
                "same_character_ids": (
                    sorted(self.export_report.deck.character_ids)
                    == sorted(self.player_2_deck.character_ids)
                ),
                "deck_name": self.player_2_deck.deck_name,
                "nickname": self.player_2_deck.player.nickname,
            },
            "planner": (
                self.action_plan.to_dict() if self.action_plan is not None else None
            ),
            "player_1": self._seat_summary(SEAT_PLAYER_1, final_state).to_dict(),
            "player_2": self._seat_summary(SEAT_PLAYER_2, final_state).to_dict(),
            "match_result": (
                self.match_result.to_dict() if self.match_result is not None else None
            ),
            "state_hash": final_state.state_hash() if final_state is not None else "",
            "replay_state_hash": self.replay_state_hash,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def _final_state(self) -> DraftSessionState | None:
        if self.action_plan is None:
            return None
        return self.action_plan.final_state

    def _seat_summary(
        self,
        seat: str,
        final_state: DraftSessionState | None,
    ) -> AccountFullLoopSeatSummary:
        deck = self.export_report.deck if seat == SEAT_PLAYER_1 else self.player_2_deck
        validation = (
            self.player_1_validation if seat == SEAT_PLAYER_1 else self.player_2_validation
        )
        team_plan = (
            self.player_1_team_plan if seat == SEAT_PLAYER_1 else self.player_2_team_plan
        )
        weapon_plan = (
            self.player_1_weapon_plan
            if seat == SEAT_PLAYER_1
            else self.player_2_weapon_plan
        )
        return AccountFullLoopSeatSummary(
            seat=seat,
            nickname=deck.player.nickname,
            deck_name=deck.deck_name,
            validation_status=validation.status,
            character_count=len(deck.characters),
            weapon_stack_count=len(deck.weapons),
            banned_character_ids=(
                final_state.banned_character_ids_for(seat)
                if final_state is not None
                else ()
            ),
            picked_character_ids=(
                final_state.picked_character_ids_for(seat)
                if final_state is not None
                else ()
            ),
            teams=team_plan.assignment if team_plan is not None else None,
            weapons=weapon_plan.assignment if weapon_plan is not None else None,
            team_status=team_plan.validation_report.status if team_plan else "not_run",
            weapon_status=(
                weapon_plan.validation_report.status if weapon_plan else "not_run"
            ),
            timer_total_seconds=_timer_total_for(
                self.match_result,
                seat,
            ),
            weapon_stack_usage=weapon_plan.stack_usage if weapon_plan else {},
        )


def run_account_full_loop_smoke(
    *,
    provider: AccountDeckDataProvider | None = None,
    options: AccountDeckExportOptions | None = None,
    schedule: DraftSchedule | None = None,
    draft_system: DraftSystemDefinition | None = None,
    system_id: str = DRAFT_SYSTEM_FREE_DRAFT_V0,
) -> AccountFullLoopSmokeReport:
    export = export_free_draft_deck_from_account(
        provider or LocalAccountSQLiteDeckDataProvider(),
        options=options or AccountDeckExportOptions(),
    )
    player_1_deck = export.deck
    player_2_deck = copy_deck_for_player_2(player_1_deck)
    player_1_validation = validate_draft_deck(player_1_deck)
    player_2_validation = validate_draft_deck(player_2_deck)
    issues: list[AccountFullLoopSmokeIssue] = []

    if not export.ready:
        issues.append(
            _issue(
                ISSUE_ACCOUNT_DECK_EXPORT_INVALID,
                "Account export did not produce a ready PvP deck.",
                details={
                    "export_issue_codes": list(export.issue_codes()),
                    "validation_issue_codes": list(
                        export.validation_report.issue_codes()
                    ),
                },
            )
        )
    if not player_1_validation.ready:
        issues.append(
            _issue(
                ISSUE_PLAYER_1_DECK_INVALID,
                "Player 1 deck failed validation.",
                seat=SEAT_PLAYER_1,
                details={"issue_codes": list(player_1_validation.issue_codes())},
            )
        )
    if not player_2_validation.ready:
        issues.append(
            _issue(
                ISSUE_PLAYER_2_DECK_INVALID,
                "Player 2 copied deck failed validation.",
                seat=SEAT_PLAYER_2,
                details={"issue_codes": list(player_2_validation.issue_codes())},
            )
        )

    if issues:
        return AccountFullLoopSmokeReport(
            export_report=export,
            player_2_deck=player_2_deck,
            player_1_validation=player_1_validation,
            player_2_validation=player_2_validation,
            issues=tuple(issues),
        )

    draft_system = draft_system or require_draft_system(system_id)
    action_plan = plan_free_draft_actions(
        player_1_deck,
        player_2_deck,
        schedule=schedule,
        draft_system=draft_system,
    )
    if not action_plan.ready:
        issues.append(
            _issue(
                ISSUE_DRAFT_PLAN_NOT_READY,
                "Deterministic account draft planner did not complete.",
                details={"issue_codes": list(action_plan.issue_codes())},
            )
        )
        return AccountFullLoopSmokeReport(
            export_report=export,
            player_2_deck=player_2_deck,
            player_1_validation=player_1_validation,
            player_2_validation=player_2_validation,
            action_plan=action_plan,
            issues=tuple(issues),
        )

    replay_state_hash = ""
    if action_plan.initial_state is not None and action_plan.final_state is not None:
        try:
            replayed = replay_draft_actions(
                action_plan.initial_state,
                action_plan.actions,
            )
        except Exception as exc:
            issues.append(
                _issue(
                    ISSUE_DRAFT_REPLAY_FAILED,
                    "Accepted action replay failed.",
                    details={"error": str(exc)},
                )
            )
        else:
            replay_state_hash = replayed.state_hash()
            if replayed.to_dict() != action_plan.final_state.to_dict():
                issues.append(
                    _issue(
                        ISSUE_DRAFT_REPLAY_DIVERGED,
                        "Accepted action replay diverged from final draft state.",
                    )
                )
            elif replay_state_hash != action_plan.final_state.state_hash():
                issues.append(
                    _issue(
                        ISSUE_DRAFT_REPLAY_DIVERGED,
                        "Accepted action replay hash diverged from final draft state.",
                    )
                )

    final_state = action_plan.final_state
    player_1_team = plan_free_draft_team_assignment(final_state, SEAT_PLAYER_1)
    player_2_team = plan_free_draft_team_assignment(final_state, SEAT_PLAYER_2)
    _append_plan_issue_if_needed(issues, player_1_team, SEAT_PLAYER_1)
    _append_plan_issue_if_needed(issues, player_2_team, SEAT_PLAYER_2)

    player_1_weapons = plan_free_draft_weapon_assignment(final_state, player_1_team.assignment)
    player_2_weapons = plan_free_draft_weapon_assignment(final_state, player_2_team.assignment)
    _append_plan_issue_if_needed(issues, player_1_weapons, SEAT_PLAYER_1)
    _append_plan_issue_if_needed(issues, player_2_weapons, SEAT_PLAYER_2)

    result = calculate_match_result(_player_1_timers(), _player_2_timers())
    return AccountFullLoopSmokeReport(
        export_report=export,
        player_2_deck=player_2_deck,
        player_1_validation=player_1_validation,
        player_2_validation=player_2_validation,
        action_plan=action_plan,
        player_1_team_plan=player_1_team,
        player_2_team_plan=player_2_team,
        player_1_weapon_plan=player_1_weapons,
        player_2_weapon_plan=player_2_weapons,
        match_result=result,
        replay_state_hash=replay_state_hash,
        issues=tuple(issues),
    )


def format_account_full_loop_smoke_report(
    report: AccountFullLoopSmokeReport,
) -> str:
    counts = report.export_report.counts
    source = report.export_report.source_summary
    player_1 = report._seat_summary(SEAT_PLAYER_1, report._final_state())
    player_2 = report._seat_summary(SEAT_PLAYER_2, report._final_state())
    result = report.match_result
    planner = report.action_plan
    issue_codes = ", ".join(report.issue_codes()) or "none"
    planner_codes = ", ".join(planner.issue_codes()) if planner is not None else "not_run"
    if not planner_codes:
        planner_codes = "none"

    return "\n".join(
        (
            "PvP account full-loop smoke",
            (
                "Source: "
                f"provider={source.get('provider', 'unknown')}, "
                f"db_exists={str(source.get('db_exists', 'n/a')).lower()}"
            ),
            (
                "Exported: "
                f"characters={counts.characters_exported}/{counts.characters_seen}, "
                f"weapons={counts.weapons_exported}/{counts.weapon_stacks_seen}, "
                f"traveler_skipped={counts.traveler_entries_skipped}, "
                f"missing_id_skipped={counts.entries_skipped_missing_id}, "
                f"invalid_skipped={counts.entries_skipped_unsupported_shape}"
            ),
            (
                "Validation: "
                f"{SEAT_PLAYER_1}={report.player_1_validation.status}, "
                f"{SEAT_PLAYER_2}={report.player_2_validation.status}, "
                f"ready={str(report.ready).lower()}"
            ),
            (
                "Player 2 copy: "
                f"same_object={str(report.export_report.deck is report.player_2_deck).lower()}, "
                f"characters={len(report.player_2_deck.characters)}, "
                f"weapons={len(report.player_2_deck.weapons)}"
            ),
            (
                "Planner: "
                f"ready={str(planner.ready).lower() if planner else 'false'}, "
                f"schedule={planner.schedule_steps_count if planner else 0} steps, "
                f"actions={planner.action_count if planner else 0}, "
                f"issues={planner_codes}"
            ),
            _seat_line(player_1),
            _seat_line(player_2),
            (
                "Result: "
                f"status={result.status if result else 'not_run'}, "
                f"winner={result.winner_seat if result else None}, "
                f"diff={result.seconds_difference if result else 0}s"
            ),
            f"State hash: {report._final_state().state_hash() if report._final_state() else ''}",
            f"Replay hash: {report.replay_state_hash}",
            f"Report issue codes: {issue_codes}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run backend-only PvP Free Draft full-loop smoke over local account "
            "SQLite runtime data."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    parser.add_argument("--db", default="", help="Optional account SQLite DB path.")
    parser.add_argument("--deck-name", default="", help="Deck name metadata.")
    parser.add_argument("--nickname", default="", help="Optional player nickname metadata.")
    parser.add_argument(
        "--language",
        default="unknown",
        help="Privacy-safe display language metadata to place in the deck source.",
    )
    args = parser.parse_args(argv)

    options = AccountDeckExportOptions(
        deck_name=args.deck_name or "Local Account Free Draft Deck",
        nickname=args.nickname,
        language=args.language,
    )
    provider = LocalAccountSQLiteDeckDataProvider(args.db or None)
    try:
        report = run_account_full_loop_smoke(provider=provider, options=options)
    except Exception as exc:
        print(f"PvP account full-loop smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_account_full_loop_smoke_report(report))
    return 0 if report.ready else 1


def _append_plan_issue_if_needed(
    issues: list[AccountFullLoopSmokeIssue],
    plan: FreeDraftTeamPlanReport | FreeDraftWeaponPlanReport,
    seat: str,
) -> None:
    if plan.ready:
        return
    code = (
        ISSUE_TEAM_PLAN_NOT_READY
        if isinstance(plan, FreeDraftTeamPlanReport)
        else ISSUE_WEAPON_PLAN_NOT_READY
    )
    issues.append(
        _issue(
            code,
            "Generated post-draft plan did not validate.",
            seat=seat,
            details={"issue_codes": list(plan.issue_codes())},
        )
    )


def _player_1_timers() -> PlayerMatchTimers:
    return PlayerMatchTimers(
        seat=SEAT_PLAYER_1,
        chambers=(
            ChamberTimer("abyss-12", "chamber-1", 90),
            ChamberTimer("abyss-12", "chamber-2", 105),
            ChamberTimer("abyss-12", "chamber-3", 120),
        ),
    )


def _player_2_timers() -> PlayerMatchTimers:
    return PlayerMatchTimers(
        seat=SEAT_PLAYER_2,
        chambers=(
            ChamberTimer("abyss-12", "chamber-1", 100),
            ChamberTimer("abyss-12", "chamber-2", 115),
            ChamberTimer("abyss-12", "chamber-3", 130),
        ),
    )


def _timer_total_for(result: MatchResult | None, seat: str) -> int:
    if result is None:
        return 0
    if seat == SEAT_PLAYER_1:
        return result.player_1_timers.total_elapsed_seconds
    return result.player_2_timers.total_elapsed_seconds


def _seat_line(summary: AccountFullLoopSeatSummary) -> str:
    return (
        f"{summary.seat}: "
        f"bans={len(summary.banned_character_ids)}, "
        f"picks={len(summary.picked_character_ids)}, "
        f"teams={summary.team_status} {_compact_teams(summary.teams)}, "
        f"weapons={summary.weapon_status} "
        f"{len(summary.weapons.assignments) if summary.weapons else 0}, "
        f"timer={summary.timer_total_seconds}s"
    )


def _compact_teams(assignment: PlayerTeamAssignment | None) -> str:
    if assignment is None:
        return "not_run"
    return ",".join(str(len(team.character_ids)) for team in assignment.teams)


def _issue(
    code: str,
    message: str,
    *,
    seat: str = "",
    details: Mapping[str, Any] | None = None,
) -> AccountFullLoopSmokeIssue:
    return AccountFullLoopSmokeIssue(
        code=code,
        severity=SEVERITY_ERROR,
        message=message,
        seat=seat,
        details=details or {},
    )


def _has_error_issues(issues: tuple[AccountFullLoopSmokeIssue, ...]) -> bool:
    return any(issue.severity == SEVERITY_ERROR for issue in issues)


if __name__ == "__main__":
    raise SystemExit(main())
