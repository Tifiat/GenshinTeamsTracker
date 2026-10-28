"""Serializable PvP session bundle and replay verifier.

The bundle is a backend/debug snapshot contract for local sessions. It is not
History persistence and does not imply a UI storage layer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .deck import DraftDeck, draft_deck_from_mapping, load_draft_deck
from .draft_system import (
    DRAFT_SYSTEM_FREE_DRAFT_V0,
    DraftSystemDefinition,
    UnknownDraftSystemError,
    require_draft_system,
)
from .match_result import (
    ChamberTimer,
    MatchResult,
    PlayerMatchTimers,
    TechnicalLoss,
    calculate_match_result,
)
from .schedule import (
    PVP_SEATS,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    DraftActionRequirement,
    DraftSchedule,
    DraftScheduleStep,
)
from .session import (
    CharacterWeaponAssignment,
    DraftAction,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    create_draft_session,
    replay_draft_actions,
    validate_team_assignment,
    validate_weapon_assignment,
)
from .validation import SEVERITY_ERROR, validate_draft_deck


PVP_SESSION_BUNDLE_SCHEMA_VERSION = 1
PVP_SESSION_BUNDLE_KIND = "gtt.pvp_session_bundle"
DEFAULT_SESSION_BUNDLE_OUTPUT_DIR = Path("data") / "pvp" / "sessions"

ISSUE_BUNDLE_SCHEMA_VERSION_INVALID = "bundle_schema_version_invalid"
ISSUE_BUNDLE_KIND_INVALID = "bundle_kind_invalid"
ISSUE_BUNDLE_MISSING_FIELD = "bundle_missing_field"
ISSUE_BUNDLE_MISSING_DECK = "bundle_missing_deck"
ISSUE_BUNDLE_DECK_LOAD_FAILED = "bundle_deck_load_failed"
ISSUE_BUNDLE_DECK_INVALID = "bundle_deck_invalid"
ISSUE_BUNDLE_UNKNOWN_DRAFT_SYSTEM = "bundle_unknown_draft_system"
ISSUE_BUNDLE_SCHEDULE_MISMATCH = "bundle_schedule_mismatch"
ISSUE_BUNDLE_SCHEDULE_HASH_MISMATCH = "bundle_schedule_hash_mismatch"
ISSUE_BUNDLE_ACTION_LOG_INVALID = "bundle_action_log_invalid"
ISSUE_BUNDLE_DRAFT_REPLAY_FAILED = "bundle_draft_replay_failed"
ISSUE_BUNDLE_FINAL_STATE_HASH_MISMATCH = "bundle_final_state_hash_mismatch"
ISSUE_BUNDLE_REPLAY_HASH_MISMATCH = "bundle_replay_hash_mismatch"
ISSUE_BUNDLE_ASSIGNMENT_LOAD_FAILED = "bundle_assignment_load_failed"
ISSUE_BUNDLE_TEAM_ASSIGNMENT_INVALID = "bundle_team_assignment_invalid"
ISSUE_BUNDLE_WEAPON_ASSIGNMENT_INVALID = "bundle_weapon_assignment_invalid"
ISSUE_BUNDLE_MATCH_RESULT_INVALID = "bundle_match_result_invalid"
ISSUE_BUNDLE_MATCH_RESULT_MISMATCH = "bundle_match_result_mismatch"


class SessionBundleLoadError(ValueError):
    """Raised when a PvP session bundle cannot be parsed as the v0 contract."""


@dataclass(frozen=True, slots=True)
class PvpSessionBundleDraftSystemRef:
    system_id: str
    version: str
    display_name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "system_id": self.system_id,
            "version": self.version,
            "display_name": self.display_name,
        }


@dataclass(frozen=True, slots=True)
class PvpSessionBundle:
    schema_version: int
    kind: str
    session_id: str
    created_at_utc: str
    source: Mapping[str, Any]
    draft_system: PvpSessionBundleDraftSystemRef
    ruleset_ref: Mapping[str, Any]
    balance_ref: Mapping[str, Any]
    seats: Mapping[str, Mapping[str, Any]]
    decks: Mapping[str, DraftDeck]
    schedule: DraftSchedule
    schedule_hash: str
    accepted_actions: tuple[DraftAction, ...]
    final_state_hash: str
    replay_state_hash: str
    team_assignments: Mapping[str, PlayerTeamAssignment]
    weapon_assignments: Mapping[str, PlayerWeaponAssignment]
    match_result: MatchResult
    reports: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "session_id": self.session_id,
            "created_at_utc": self.created_at_utc,
            "source": dict(sorted(self.source.items())),
            "draft_system": self.draft_system.to_dict(),
            "ruleset_ref": dict(sorted(self.ruleset_ref.items())),
            "balance_ref": dict(sorted(self.balance_ref.items())),
            "seats": {
                seat: dict(sorted(self.seats.get(seat, {}).items()))
                for seat in PVP_SEATS
            },
            "decks": {
                seat: self.decks[seat].to_dict()
                for seat in PVP_SEATS
                if seat in self.decks
            },
            "schedule": self.schedule.to_dict(),
            "schedule_hash": self.schedule_hash,
            "draft": {
                "accepted_actions": [item.to_dict() for item in self.accepted_actions],
                "final_state_hash": self.final_state_hash,
                "replay_state_hash": self.replay_state_hash,
            },
            "assignments": {
                "teams": {
                    seat: self.team_assignments[seat].to_dict()
                    for seat in PVP_SEATS
                    if seat in self.team_assignments
                },
                "weapons": {
                    seat: self.weapon_assignments[seat].to_dict()
                    for seat in PVP_SEATS
                    if seat in self.weapon_assignments
                },
            },
            "result": self.match_result.to_dict(),
            "reports": dict(sorted(self.reports.items())),
        }


@dataclass(frozen=True, slots=True)
class PvpSessionBundleVerificationIssue:
    code: str
    severity: str
    message: str = ""
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
class PvpSessionBundleVerificationReport:
    issues: tuple[PvpSessionBundleVerificationIssue, ...] = ()
    draft_system_id: str = ""
    draft_system_version: str = ""
    schedule_hash: str = ""
    stored_final_state_hash: str = ""
    replay_state_hash: str = ""
    action_count: int = 0
    schedule_steps_count: int = 0

    @property
    def ready(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "ready" if self.ready else "invalid"

    @property
    def errors(self) -> tuple[PvpSessionBundleVerificationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == SEVERITY_ERROR)

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "status": self.status,
            "draft_system_id": self.draft_system_id,
            "draft_system_version": self.draft_system_version,
            "schedule_hash": self.schedule_hash,
            "stored_final_state_hash": self.stored_final_state_hash,
            "replay_state_hash": self.replay_state_hash,
            "action_count": self.action_count,
            "schedule_steps_count": self.schedule_steps_count,
            "issues": [item.to_dict() for item in self.issues],
        }


def build_session_bundle(
    *,
    decks: Mapping[str, DraftDeck],
    accepted_actions: tuple[DraftAction, ...],
    final_state_hash: str,
    replay_state_hash: str,
    team_assignments: Mapping[str, PlayerTeamAssignment],
    weapon_assignments: Mapping[str, PlayerWeaponAssignment],
    match_result: MatchResult,
    source_mode: str,
    reports: Mapping[str, Any] | None = None,
    draft_system: DraftSystemDefinition | None = None,
    system_id: str = DRAFT_SYSTEM_FREE_DRAFT_V0,
    ruleset_ref: Mapping[str, Any] | None = None,
    balance_ref: Mapping[str, Any] | None = None,
    session_id: str = "",
    created_at_utc: str = "",
) -> PvpSessionBundle:
    system = draft_system or require_draft_system(system_id)
    schedule = system.build_schedule()
    schedule_hash = calculate_schedule_hash(schedule)
    player_1_deck = decks[SEAT_PLAYER_1]
    session_id = session_id or f"pvp-session-{source_mode}-{final_state_hash[:12]}"
    return PvpSessionBundle(
        schema_version=PVP_SESSION_BUNDLE_SCHEMA_VERSION,
        kind=PVP_SESSION_BUNDLE_KIND,
        session_id=session_id,
        created_at_utc=created_at_utc or _utc_now(),
        source={
            "app": "GenshinTeamsTracker",
            "module": "run_workspace.pvp.session_bundle",
            "source_mode": source_mode,
            "privacy": "embedded_decks_no_artifacts_auth_raw_dumps_paths_or_sqlite_ids",
        },
        draft_system=PvpSessionBundleDraftSystemRef(
            system_id=system.system_id,
            version=system.version,
            display_name=system.display_name,
        ),
        ruleset_ref=(
            dict(ruleset_ref)
            if ruleset_ref is not None
            else player_1_deck.ruleset_ref.to_dict()
        ),
        balance_ref=dict(balance_ref or {}),
        seats={
            seat: {
                "seat": seat,
                "nickname": decks[seat].player.nickname,
                "deck_name": decks[seat].deck_name,
            }
            for seat in PVP_SEATS
            if seat in decks
        },
        decks={seat: decks[seat] for seat in PVP_SEATS if seat in decks},
        schedule=schedule,
        schedule_hash=schedule_hash,
        accepted_actions=accepted_actions,
        final_state_hash=final_state_hash,
        replay_state_hash=replay_state_hash,
        team_assignments={
            seat: team_assignments[seat]
            for seat in PVP_SEATS
            if seat in team_assignments
        },
        weapon_assignments={
            seat: weapon_assignments[seat]
            for seat in PVP_SEATS
            if seat in weapon_assignments
        },
        match_result=match_result,
        reports=dict(reports or {}),
    )


def build_session_bundle_from_full_loop_report(
    report: Any,
    *,
    session_id: str = "",
    created_at_utc: str = "",
) -> PvpSessionBundle:
    decks = {
        SEAT_PLAYER_1: load_draft_deck(report.player_1.deck_path),
        SEAT_PLAYER_2: load_draft_deck(report.player_2.deck_path),
    }
    return build_session_bundle(
        decks=decks,
        accepted_actions=report.accepted_actions,
        final_state_hash=report.state_hash,
        replay_state_hash=report.replay_state_hash,
        team_assignments={
            SEAT_PLAYER_1: report.player_1.teams,
            SEAT_PLAYER_2: report.player_2.teams,
        },
        weapon_assignments={
            SEAT_PLAYER_1: report.player_1.weapons,
            SEAT_PLAYER_2: report.player_2.weapons,
        },
        match_result=report.match_result,
        source_mode="synthetic",
        reports={
            "scenario_name": report.scenario_name,
            "schedule_steps_count": report.schedule_steps_count,
            "action_count": report.action_count,
            "validation_status_by_seat": {
                SEAT_PLAYER_1: report.player_1.validation_status,
                SEAT_PLAYER_2: report.player_2.validation_status,
            },
        },
        session_id=session_id,
        created_at_utc=created_at_utc,
    )


def build_session_bundle_from_account_full_loop_report(
    report: Any,
    *,
    session_id: str = "",
    created_at_utc: str = "",
) -> PvpSessionBundle:
    if report.action_plan is None or report.action_plan.final_state is None:
        raise SessionBundleLoadError("Account full-loop report has no final draft state.")
    if (
        report.player_1_team_plan is None
        or report.player_2_team_plan is None
        or report.player_1_weapon_plan is None
        or report.player_2_weapon_plan is None
        or report.match_result is None
    ):
        raise SessionBundleLoadError("Account full-loop report is missing assignments.")
    return build_session_bundle(
        decks={
            SEAT_PLAYER_1: report.export_report.deck,
            SEAT_PLAYER_2: report.player_2_deck,
        },
        accepted_actions=report.action_plan.actions,
        final_state_hash=report.action_plan.final_state.state_hash(),
        replay_state_hash=report.replay_state_hash,
        team_assignments={
            SEAT_PLAYER_1: report.player_1_team_plan.assignment,
            SEAT_PLAYER_2: report.player_2_team_plan.assignment,
        },
        weapon_assignments={
            SEAT_PLAYER_1: report.player_1_weapon_plan.assignment,
            SEAT_PLAYER_2: report.player_2_weapon_plan.assignment,
        },
        match_result=report.match_result,
        source_mode="account",
        reports={
            "export_counts": report.export_report.counts.to_dict(),
            "export_issue_codes": list(report.export_report.issue_codes()),
            "account_full_loop_issue_codes": list(report.issue_codes()),
            "planner_issue_codes": list(report.action_plan.issue_codes()),
        },
        session_id=session_id,
        created_at_utc=created_at_utc,
    )


def verify_session_bundle(
    bundle: PvpSessionBundle | Mapping[str, Any],
) -> PvpSessionBundleVerificationReport:
    payload = bundle.to_dict() if isinstance(bundle, PvpSessionBundle) else bundle
    if not isinstance(payload, Mapping):
        return PvpSessionBundleVerificationReport(
            issues=(
                _issue(
                    ISSUE_BUNDLE_KIND_INVALID,
                    "Session bundle root must be an object.",
                    path="",
                ),
            )
        )

    issues: list[PvpSessionBundleVerificationIssue] = []
    schema_version = _optional_int(payload.get("schema_version"))
    if schema_version != PVP_SESSION_BUNDLE_SCHEMA_VERSION:
        issues.append(
            _issue(
                ISSUE_BUNDLE_SCHEMA_VERSION_INVALID,
                "Unsupported PvP session bundle schema version.",
                path="schema_version",
                details={
                    "expected": PVP_SESSION_BUNDLE_SCHEMA_VERSION,
                    "actual": schema_version,
                },
            )
        )
    if _text(payload.get("kind")) != PVP_SESSION_BUNDLE_KIND:
        issues.append(
            _issue(
                ISSUE_BUNDLE_KIND_INVALID,
                "Invalid PvP session bundle kind.",
                path="kind",
                details={"expected": PVP_SESSION_BUNDLE_KIND},
            )
        )

    draft_system_payload = _mapping(payload.get("draft_system"))
    system_id = _text(draft_system_payload.get("system_id"))
    system: DraftSystemDefinition | None = None
    try:
        system = require_draft_system(system_id)
    except UnknownDraftSystemError:
        issues.append(
            _issue(
                ISSUE_BUNDLE_UNKNOWN_DRAFT_SYSTEM,
                "PvP session bundle references an unknown draft system.",
                path="draft_system.system_id",
                details={"system_id": system_id},
            )
        )

    decks = _load_bundle_decks(payload, issues)
    if system is None or len(decks) != len(PVP_SEATS):
        return _verification_report(payload, issues, system, action_count=0)

    expected_schedule = system.build_schedule()
    expected_schedule_hash = calculate_schedule_hash(expected_schedule)
    stored_schedule_hash = _text(payload.get("schedule_hash"))
    if _mapping(payload.get("schedule")) != expected_schedule.to_dict():
        issues.append(
            _issue(
                ISSUE_BUNDLE_SCHEDULE_MISMATCH,
                "Bundle schedule snapshot differs from the registered draft system.",
                path="schedule",
            )
        )
    if stored_schedule_hash != expected_schedule_hash:
        issues.append(
            _issue(
                ISSUE_BUNDLE_SCHEDULE_HASH_MISMATCH,
                "Bundle schedule hash differs from the registered draft system.",
                path="schedule_hash",
                details={
                    "expected": expected_schedule_hash,
                    "actual": stored_schedule_hash,
                },
            )
        )

    draft_payload = _mapping(payload.get("draft"))
    actions = _load_actions(draft_payload.get("accepted_actions"), issues)
    stored_final_hash = _text(draft_payload.get("final_state_hash"))
    stored_replay_hash = _text(draft_payload.get("replay_state_hash"))
    replay_hash = ""
    replayed_state = None
    if actions is not None:
        try:
            initial_state = create_draft_session(
                decks[SEAT_PLAYER_1],
                decks[SEAT_PLAYER_2],
                schedule=expected_schedule,
            )
            replayed_state = replay_draft_actions(initial_state, actions)
            replay_hash = replayed_state.state_hash()
        except Exception as exc:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_DRAFT_REPLAY_FAILED,
                    "Bundle accepted action log failed reducer replay.",
                    path="draft.accepted_actions",
                    details={
                        "error": str(exc),
                        "code": getattr(exc, "code", ""),
                    },
                )
            )
    if replayed_state is not None:
        if replay_hash != stored_final_hash:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_FINAL_STATE_HASH_MISMATCH,
                    "Replayed draft state hash differs from stored final state hash.",
                    path="draft.final_state_hash",
                    details={"expected": stored_final_hash, "actual": replay_hash},
                )
            )
        if stored_replay_hash and replay_hash != stored_replay_hash:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_REPLAY_HASH_MISMATCH,
                    "Replayed draft state hash differs from stored replay hash.",
                    path="draft.replay_state_hash",
                    details={"expected": stored_replay_hash, "actual": replay_hash},
                )
            )
        _verify_assignments(payload, replayed_state, issues)

    _verify_match_result(payload, issues)
    return _verification_report(
        payload,
        issues,
        system,
        action_count=len(actions or ()),
        replay_state_hash=replay_hash,
        schedule_hash=expected_schedule_hash,
    )


def pvp_session_bundle_from_mapping(payload: Mapping[str, Any]) -> PvpSessionBundle:
    if not isinstance(payload, Mapping):
        raise SessionBundleLoadError("PvP session bundle root must be an object.")
    draft_system_payload = _mapping(payload.get("draft_system"))
    decks_payload = _mapping(payload.get("decks"))
    assignments_payload = _mapping(payload.get("assignments"))
    draft_payload = _mapping(payload.get("draft"))
    return PvpSessionBundle(
        schema_version=_optional_int(payload.get("schema_version")) or 0,
        kind=_text(payload.get("kind")),
        session_id=_text(payload.get("session_id")),
        created_at_utc=_text(payload.get("created_at_utc")),
        source=dict(_mapping(payload.get("source"))),
        draft_system=PvpSessionBundleDraftSystemRef(
            system_id=_text(draft_system_payload.get("system_id")),
            version=_text(draft_system_payload.get("version")),
            display_name=_text(draft_system_payload.get("display_name")),
        ),
        ruleset_ref=dict(_mapping(payload.get("ruleset_ref"))),
        balance_ref=dict(_mapping(payload.get("balance_ref"))),
        seats=dict(_mapping(payload.get("seats"))),
        decks={
            seat: draft_deck_from_mapping(_mapping(decks_payload.get(seat)))
            for seat in PVP_SEATS
        },
        schedule=_schedule_from_mapping(_mapping(payload.get("schedule"))),
        schedule_hash=_text(payload.get("schedule_hash")),
        accepted_actions=tuple(
            _action_from_mapping(item)
            for item in _list(draft_payload.get("accepted_actions"))
        ),
        final_state_hash=_text(draft_payload.get("final_state_hash")),
        replay_state_hash=_text(draft_payload.get("replay_state_hash")),
        team_assignments={
            seat: _team_assignment_from_mapping(
                _mapping(_mapping(assignments_payload.get("teams")).get(seat))
            )
            for seat in PVP_SEATS
        },
        weapon_assignments={
            seat: _weapon_assignment_from_mapping(
                _mapping(_mapping(assignments_payload.get("weapons")).get(seat))
            )
            for seat in PVP_SEATS
        },
        match_result=_match_result_from_mapping(_mapping(payload.get("result"))),
        reports=dict(_mapping(payload.get("reports"))),
    )


def load_session_bundle_from_json_text(text: str) -> PvpSessionBundle:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SessionBundleLoadError(f"Invalid PvP session bundle JSON: {exc.msg}.") from exc
    return pvp_session_bundle_from_mapping(payload)


def session_bundle_to_json_text(bundle: PvpSessionBundle, *, indent: int = 2) -> str:
    return json.dumps(bundle.to_dict(), ensure_ascii=False, indent=indent) + "\n"


def write_session_bundle(bundle: PvpSessionBundle, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_bundle_to_json_text(bundle), encoding="utf-8")
    return path


def default_session_bundle_output_path(
    *,
    created_at_utc: str | None = None,
    session_id: str = "",
    output_dir: str | Path = DEFAULT_SESSION_BUNDLE_OUTPUT_DIR,
) -> Path:
    stamp = _filename_timestamp(created_at_utc or _utc_now())
    name = session_id or f"pvp_session_{stamp}"
    return Path(output_dir) / f"{_filename_safe(name)}.json"


def calculate_schedule_hash(schedule: DraftSchedule) -> str:
    payload = json.dumps(
        schedule.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calculate_bundle_hash(bundle: PvpSessionBundle) -> str:
    payload = json.dumps(
        bundle.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_bundle_decks(
    payload: Mapping[str, Any],
    issues: list[PvpSessionBundleVerificationIssue],
) -> dict[str, DraftDeck]:
    decks_payload = _mapping(payload.get("decks"))
    decks: dict[str, DraftDeck] = {}
    for seat in PVP_SEATS:
        if seat not in decks_payload:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_MISSING_DECK,
                    "Bundle is missing an embedded deck for this seat.",
                    path=f"decks.{seat}",
                    details={"seat": seat},
                )
            )
            continue
        try:
            deck = draft_deck_from_mapping(_mapping(decks_payload.get(seat)))
        except Exception as exc:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_DECK_LOAD_FAILED,
                    "Embedded deck could not be parsed.",
                    path=f"decks.{seat}",
                    details={"seat": seat, "error": str(exc)},
                )
            )
            continue
        report = validate_draft_deck(deck)
        if not report.ready:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_DECK_INVALID,
                    "Embedded deck failed PvP deck validation.",
                    path=f"decks.{seat}",
                    details={"seat": seat, "issue_codes": list(report.issue_codes())},
                )
            )
        decks[seat] = deck
    return decks


def _load_actions(
    value: Any,
    issues: list[PvpSessionBundleVerificationIssue],
) -> tuple[DraftAction, ...] | None:
    if not isinstance(value, list):
        issues.append(
            _issue(
                ISSUE_BUNDLE_MISSING_FIELD,
                "Bundle draft accepted_actions must be a list.",
                path="draft.accepted_actions",
            )
        )
        return None
    actions: list[DraftAction] = []
    for index, item in enumerate(value):
        try:
            actions.append(_action_from_mapping(_mapping(item)))
        except Exception as exc:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_ACTION_LOG_INVALID,
                    "Bundle action log contains an invalid action entry.",
                    path=f"draft.accepted_actions[{index}]",
                    details={"error": str(exc)},
                )
            )
            return None
    return tuple(actions)


def _verify_assignments(
    payload: Mapping[str, Any],
    replayed_state: Any,
    issues: list[PvpSessionBundleVerificationIssue],
) -> None:
    assignments_payload = _mapping(payload.get("assignments"))
    teams_payload = _mapping(assignments_payload.get("teams"))
    weapons_payload = _mapping(assignments_payload.get("weapons"))
    for seat in PVP_SEATS:
        try:
            team = _team_assignment_from_mapping(_mapping(teams_payload.get(seat)))
            weapon = _weapon_assignment_from_mapping(_mapping(weapons_payload.get(seat)))
        except Exception as exc:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_ASSIGNMENT_LOAD_FAILED,
                    "Bundle assignment payload could not be parsed.",
                    path=f"assignments.{seat}",
                    details={"seat": seat, "error": str(exc)},
                )
            )
            continue
        team_report = validate_team_assignment(replayed_state, team)
        if not team_report.ready:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_TEAM_ASSIGNMENT_INVALID,
                    "Bundle team assignment failed validation.",
                    path=f"assignments.teams.{seat}",
                    details={"seat": seat, "issue_codes": list(team_report.issue_codes())},
                )
            )
        weapon_report = validate_weapon_assignment(replayed_state, team, weapon)
        if not weapon_report.ready:
            issues.append(
                _issue(
                    ISSUE_BUNDLE_WEAPON_ASSIGNMENT_INVALID,
                    "Bundle weapon assignment failed validation.",
                    path=f"assignments.weapons.{seat}",
                    details={
                        "seat": seat,
                        "issue_codes": list(weapon_report.issue_codes()),
                    },
                )
            )


def _verify_match_result(
    payload: Mapping[str, Any],
    issues: list[PvpSessionBundleVerificationIssue],
) -> None:
    try:
        result = _match_result_from_mapping(_mapping(payload.get("result")))
    except Exception as exc:
        issues.append(
            _issue(
                ISSUE_BUNDLE_MATCH_RESULT_INVALID,
                "Bundle match result could not be parsed.",
                path="result",
                details={"error": str(exc)},
            )
        )
        return
    recalculated = calculate_match_result(
        result.player_1_timers,
        result.player_2_timers,
        technical_losses=result.technical_losses,
    )
    expected = {
        "status": recalculated.status,
        "winner_seat": recalculated.winner_seat,
        "seconds_difference": recalculated.seconds_difference,
        "totals": recalculated.to_dict()["totals"],
    }
    actual = {
        "status": result.status,
        "winner_seat": result.winner_seat,
        "seconds_difference": result.seconds_difference,
        "totals": result.to_dict()["totals"],
    }
    if actual != expected:
        issues.append(
            _issue(
                ISSUE_BUNDLE_MATCH_RESULT_MISMATCH,
                "Bundle match result does not match recalculated timer result.",
                path="result",
                details={"expected": expected, "actual": actual},
            )
        )


def _verification_report(
    payload: Mapping[str, Any],
    issues: list[PvpSessionBundleVerificationIssue],
    system: DraftSystemDefinition | None,
    *,
    action_count: int,
    replay_state_hash: str = "",
    schedule_hash: str = "",
) -> PvpSessionBundleVerificationReport:
    draft_payload = _mapping(payload.get("draft"))
    return PvpSessionBundleVerificationReport(
        issues=tuple(issues),
        draft_system_id=system.system_id if system else _text(_mapping(payload.get("draft_system")).get("system_id")),
        draft_system_version=system.version if system else "",
        schedule_hash=schedule_hash,
        stored_final_state_hash=_text(draft_payload.get("final_state_hash")),
        replay_state_hash=replay_state_hash,
        action_count=action_count,
        schedule_steps_count=len(system.build_schedule().steps) if system else 0,
    )


def _schedule_from_mapping(payload: Mapping[str, Any]) -> DraftSchedule:
    return DraftSchedule(
        ruleset_id=_text(payload.get("ruleset_id")),
        steps=tuple(
            DraftScheduleStep(
                phase=_text(step.get("phase")),
                seat=_text(step.get("seat")),
                actions=tuple(
                    DraftActionRequirement(_text(action.get("type")))
                    for action in _list(step.get("actions"))
                    if isinstance(action, Mapping)
                ),
            )
            for step in _list(payload.get("steps"))
            if isinstance(step, Mapping)
        ),
    )


def _action_from_mapping(payload: Mapping[str, Any]) -> DraftAction:
    return DraftAction(
        seat=_text(payload.get("seat")),
        action_type=_text(payload.get("type")),
        character_id=_text(payload.get("character_id")),
        action_id=_text(payload.get("action_id")),
        sequence=_optional_int(payload.get("sequence")),
        payload=dict(_mapping(payload.get("payload"))),
    )


def _team_assignment_from_mapping(payload: Mapping[str, Any]) -> PlayerTeamAssignment:
    return PlayerTeamAssignment(
        seat=_text(payload.get("seat")),
        teams=tuple(
            TeamAssignment(
                team_index=_optional_int(item.get("team_index")) or 0,
                character_ids=tuple(_text(value) for value in _list(item.get("character_ids"))),
            )
            for item in _list(payload.get("teams"))
            if isinstance(item, Mapping)
        ),
    )


def _weapon_assignment_from_mapping(payload: Mapping[str, Any]) -> PlayerWeaponAssignment:
    return PlayerWeaponAssignment(
        seat=_text(payload.get("seat")),
        assignments=tuple(
            CharacterWeaponAssignment(
                character_id=_text(item.get("character_id")),
                weapon_stack_key=_text(item.get("weapon_stack_key")),
            )
            for item in _list(payload.get("assignments"))
            if isinstance(item, Mapping)
        ),
    )


def _match_result_from_mapping(payload: Mapping[str, Any]) -> MatchResult:
    return MatchResult(
        player_1_timers=_player_timers_from_mapping(
            _mapping(payload.get("player_1_timers"))
        ),
        player_2_timers=_player_timers_from_mapping(
            _mapping(payload.get("player_2_timers"))
        ),
        status=_text(payload.get("status")),
        winner_seat=_text(payload.get("winner_seat")) or None,
        seconds_difference=_optional_int(payload.get("seconds_difference")) or 0,
        technical_losses=tuple(
            TechnicalLoss(
                seat=_text(item.get("seat")),
                reason=_text(item.get("reason")),
                issue_codes=tuple(_text(code) for code in _list(item.get("issue_codes"))),
            )
            for item in _list(payload.get("technical_losses"))
            if isinstance(item, Mapping)
        ),
    )


def _player_timers_from_mapping(payload: Mapping[str, Any]) -> PlayerMatchTimers:
    return PlayerMatchTimers(
        seat=_text(payload.get("seat")),
        chambers=tuple(
            ChamberTimer(
                room_id=_text(item.get("room_id")),
                chamber_id=_text(item.get("chamber_id")),
                elapsed_seconds=_optional_int(item.get("elapsed_seconds")) or 0,
            )
            for item in _list(payload.get("chambers"))
            if isinstance(item, Mapping)
        ),
    )


def _issue(
    code: str,
    message: str,
    *,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> PvpSessionBundleVerificationIssue:
    return PvpSessionBundleVerificationIssue(
        code=code,
        severity=SEVERITY_ERROR,
        message=message,
        path=path,
        details=details or {},
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _filename_timestamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())[:14] or "unknown"


def _filename_safe(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return safe.strip("_") or "pvp_session_bundle"
