"""Backend-only Free Draft v0 controller for future local UI surfaces.

This module is the thin runtime API over the existing draft-system registry,
reducer, validators, deterministic smoke helpers, and session-bundle contract.
It is not a UI layer, not an optimizer, and not a ruleset/source adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .account_deck_export import (
    AccountDeckDataProvider,
    AccountDeckExportOptions,
    AccountDeckExportReport,
    LocalAccountSQLiteDeckDataProvider,
    export_free_draft_deck_from_account,
)
from .account_deck_copy import copy_deck_for_player_2
from .deck import (
    DraftCharacter,
    DraftDeck,
    draft_deck_from_mapping,
    load_draft_deck,
)
from .draft_system import (
    DRAFT_SYSTEM_FREE_DRAFT_V0,
    DraftSystemDefinition,
    require_draft_system,
)
from .free_draft_planner import (
    FreeDraftTeamPlanReport,
    FreeDraftWeaponPlanReport,
    plan_free_draft_team_assignment,
    plan_free_draft_weapon_assignment,
)
from .match_result import (
    ChamberTimer,
    MatchResult,
    PlayerMatchTimers,
    calculate_match_result,
)
from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    PVP_SEATS,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    DraftSchedule,
)
from .session import (
    DraftAction,
    DraftActionRejected,
    DraftSessionState,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    apply_draft_action,
    create_draft_session,
    replay_draft_actions,
    validate_team_assignment,
    validate_weapon_assignment,
)
from .session_bundle import (
    PvpSessionBundle,
    PvpSessionBundleVerificationReport,
    build_session_bundle,
    pvp_session_bundle_from_mapping,
    verify_session_bundle,
)
from .validation import (
    SEVERITY_ERROR,
    DeckValidationReport,
    validate_draft_deck,
)


ISSUE_CONTROLLER_DECK_INVALID = "free_draft_controller_deck_invalid"
ISSUE_CONTROLLER_ACCOUNT_EXPORT_INVALID = "free_draft_controller_account_export_invalid"
ISSUE_CONTROLLER_ACTION_REJECTED = "free_draft_controller_action_rejected"
ISSUE_CONTROLLER_NO_LEGAL_TARGET = "free_draft_controller_no_legal_target"
ISSUE_CONTROLLER_ASSIGNMENT_INVALID = "free_draft_controller_assignment_invalid"
ISSUE_CONTROLLER_BUNDLE_NOT_READY = "free_draft_controller_bundle_not_ready"
ISSUE_CONTROLLER_BUNDLE_VERIFY_FAILED = "free_draft_controller_bundle_verify_failed"
ISSUE_CONTROLLER_REPLAY_FAILED = "free_draft_controller_replay_failed"


class FreeDraftControllerActionRejected(ValueError):
    """Raised when a controller command cannot be accepted by the reducer/API."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        reducer_code: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.reducer_code = reducer_code
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class FreeDraftControllerIssue:
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
class FreeDraftTargetSummary:
    character_id: str
    display_name: str
    element: str
    weapon_type: str
    rarity: int | None
    level: int | None
    constellation: int | None
    status: str = "legal"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.character_id,
            "display_name": self.display_name,
            "element": self.element,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "level": self.level,
            "constellation": self.constellation,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FreeDraftProjection:
    draft_system: Mapping[str, Any]
    status: Mapping[str, Any]
    current_requirement: Mapping[str, Any] | None
    progress: Mapping[str, Any]
    seats: Mapping[str, Any]
    draft_state: Mapping[str, Any]
    legal_targets: tuple[FreeDraftTargetSummary, ...]
    assignments: Mapping[str, Any]
    result: Mapping[str, Any] | None
    issue_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_system": dict(self.draft_system),
            "status": dict(self.status),
            "current_requirement": (
                dict(self.current_requirement)
                if self.current_requirement is not None
                else None
            ),
            "progress": dict(self.progress),
            "seats": _plain_mapping(self.seats),
            "draft_state": _plain_mapping(self.draft_state),
            "legal_targets": [target.to_dict() for target in self.legal_targets],
            "assignments": _plain_mapping(self.assignments),
            "result": dict(self.result) if self.result is not None else None,
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class FreeDraftControllerState:
    draft_system: DraftSystemDefinition
    player_1_deck: DraftDeck
    player_2_deck: DraftDeck
    player_1_validation: DeckValidationReport
    player_2_validation: DeckValidationReport
    session_state: DraftSessionState
    source_mode: str = "synthetic"
    account_export_report: AccountDeckExportReport | None = None
    team_assignments: Mapping[str, PlayerTeamAssignment] = field(default_factory=dict)
    weapon_assignments: Mapping[str, PlayerWeaponAssignment] = field(default_factory=dict)
    match_result: MatchResult | None = None
    issues: tuple[FreeDraftControllerIssue, ...] = ()

    @property
    def setup_ready(self) -> bool:
        return self.player_1_validation.ready and self.player_2_validation.ready

    def decks_by_seat(self) -> dict[str, DraftDeck]:
        return {
            SEAT_PLAYER_1: self.player_1_deck,
            SEAT_PLAYER_2: self.player_2_deck,
        }

    def validation_by_seat(self) -> dict[str, DeckValidationReport]:
        return {
            SEAT_PLAYER_1: self.player_1_validation,
            SEAT_PLAYER_2: self.player_2_validation,
        }


class FreeDraftController:
    """Manual local Free Draft controller over the existing reducer state."""

    def __init__(self, state: FreeDraftControllerState) -> None:
        self.state = state

    @classmethod
    def from_decks(
        cls,
        player_1_deck: DraftDeck,
        player_2_deck: DraftDeck,
        *,
        draft_system: DraftSystemDefinition | None = None,
        system_id: str = DRAFT_SYSTEM_FREE_DRAFT_V0,
        source_mode: str = "synthetic",
    ) -> "FreeDraftController":
        system = draft_system or require_draft_system(system_id)
        schedule = system.build_schedule()
        player_1_validation = validate_draft_deck(player_1_deck)
        player_2_validation = validate_draft_deck(player_2_deck)
        session_state = create_draft_session(
            player_1_deck,
            player_2_deck,
            schedule=schedule,
            validate_decks=False,
        )
        issues = _deck_issues(player_1_validation, player_2_validation)
        return cls(
            FreeDraftControllerState(
                draft_system=system,
                player_1_deck=player_1_deck,
                player_2_deck=player_2_deck,
                player_1_validation=player_1_validation,
                player_2_validation=player_2_validation,
                session_state=session_state,
                source_mode=source_mode,
                issues=issues,
            )
        )

    @classmethod
    def from_deck_files(
        cls,
        player_1_deck_path: str | Path,
        player_2_deck_path: str | Path,
        **kwargs: Any,
    ) -> "FreeDraftController":
        return cls.from_decks(
            load_draft_deck(player_1_deck_path),
            load_draft_deck(player_2_deck_path),
            **kwargs,
        )

    @classmethod
    def from_deck_mappings(
        cls,
        player_1_payload: Mapping[str, Any],
        player_2_payload: Mapping[str, Any],
        **kwargs: Any,
    ) -> "FreeDraftController":
        return cls.from_decks(
            draft_deck_from_mapping(player_1_payload),
            draft_deck_from_mapping(player_2_payload),
            **kwargs,
        )

    @classmethod
    def from_account_export(
        cls,
        *,
        provider: AccountDeckDataProvider | None = None,
        options: AccountDeckExportOptions | None = None,
        draft_system: DraftSystemDefinition | None = None,
        system_id: str = DRAFT_SYSTEM_FREE_DRAFT_V0,
    ) -> "FreeDraftController":
        export = export_free_draft_deck_from_account(
            provider or LocalAccountSQLiteDeckDataProvider(),
            options=options or AccountDeckExportOptions(),
        )
        controller = cls.from_decks(
            export.deck,
            copy_deck_for_player_2(export.deck),
            draft_system=draft_system,
            system_id=system_id,
            source_mode="account",
        )
        issues = list(controller.state.issues)
        if not export.ready:
            issues.append(
                _issue(
                    ISSUE_CONTROLLER_ACCOUNT_EXPORT_INVALID,
                    "Account export did not produce a ready Free Draft deck.",
                    details={
                        "export_issue_codes": list(export.issue_codes()),
                        "validation_issue_codes": list(
                            export.validation_report.issue_codes()
                        ),
                    },
                )
            )
        controller.state = replace(
            controller.state,
            account_export_report=export,
            issues=tuple(issues),
        )
        return controller

    @classmethod
    def from_session_bundle(
        cls,
        bundle: PvpSessionBundle | Mapping[str, Any],
    ) -> "FreeDraftController":
        parsed = (
            bundle
            if isinstance(bundle, PvpSessionBundle)
            else pvp_session_bundle_from_mapping(bundle)
        )
        controller = cls.from_decks(
            parsed.decks[SEAT_PLAYER_1],
            parsed.decks[SEAT_PLAYER_2],
            system_id=parsed.draft_system.system_id,
            source_mode=str(parsed.source.get("source_mode", "bundle")),
        )
        try:
            replayed = replay_draft_actions(
                controller.state.session_state,
                parsed.accepted_actions,
            )
        except Exception as exc:
            controller._append_issue(
                _issue(
                    ISSUE_CONTROLLER_REPLAY_FAILED,
                    "Session bundle actions could not be replayed into the controller.",
                    details={"error": str(exc), "code": getattr(exc, "code", "")},
                )
            )
            return controller
        controller.state = replace(
            controller.state,
            session_state=replayed,
            team_assignments=dict(parsed.team_assignments),
            weapon_assignments=dict(parsed.weapon_assignments),
            match_result=parsed.match_result,
        )
        return controller

    @property
    def session_state(self) -> DraftSessionState:
        return self.state.session_state

    @property
    def accepted_actions(self) -> tuple[DraftAction, ...]:
        return self.session_state.accepted_actions

    def issue_codes(self) -> tuple[str, ...]:
        codes: list[str] = [issue.code for issue in self.state.issues]
        for report in self.state.validation_by_seat().values():
            codes.extend(report.issue_codes())
        return tuple(dict.fromkeys(code for code in codes if code))

    def get_legal_targets(
        self,
        *,
        include_excluded: bool = False,
    ) -> tuple[FreeDraftTargetSummary, ...]:
        requirement = self.session_state.current_requirement
        seat = self.session_state.current_seat
        if requirement is None or seat is None:
            return ()
        if requirement.action_type not in {ACTION_BAN_CHARACTER, ACTION_PICK_CHARACTER}:
            return ()

        targets: list[FreeDraftTargetSummary] = []
        for character in _candidate_characters(
            self.session_state,
            seat,
            requirement.action_type,
        ):
            try:
                apply_draft_action(
                    self.session_state,
                    DraftAction(
                        seat=seat,
                        action_type=requirement.action_type,
                        character_id=character.character_id,
                    ),
                )
            except DraftActionRejected as exc:
                if include_excluded:
                    targets.append(
                        _target_summary(
                            character,
                            status="excluded",
                            reason=exc.code,
                        )
                    )
                continue
            targets.append(_target_summary(character))
        return tuple(targets)

    def apply_ban_character(self, character_id: str) -> DraftAction:
        return self.apply_current_action(character_id, expected_action_type=ACTION_BAN_CHARACTER)

    def apply_pick_character(self, character_id: str) -> DraftAction:
        return self.apply_current_action(character_id, expected_action_type=ACTION_PICK_CHARACTER)

    def apply_current_action(
        self,
        target_id: str,
        *,
        expected_action_type: str | None = None,
    ) -> DraftAction:
        requirement = self.session_state.current_requirement
        seat = self.session_state.current_seat
        if requirement is None or seat is None:
            raise FreeDraftControllerActionRejected(
                "draft_complete",
                "The Free Draft schedule is already complete.",
            )
        if expected_action_type and requirement.action_type != expected_action_type:
            raise FreeDraftControllerActionRejected(
                "wrong_action_type",
                "The current schedule requirement does not match this command.",
                details={
                    "expected": expected_action_type,
                    "actual": requirement.action_type,
                },
            )
        return self.apply_manual_action(
            seat=seat,
            action_type=requirement.action_type,
            character_id=target_id,
        )

    def apply_manual_action(
        self,
        *,
        seat: str,
        action_type: str,
        character_id: str,
    ) -> DraftAction:
        action = DraftAction(
            seat=seat,
            action_type=action_type,
            character_id=character_id,
            action_id=f"free-draft-controller-{len(self.accepted_actions) + 1}",
            sequence=len(self.accepted_actions) + 1,
        )
        try:
            next_state = apply_draft_action(self.session_state, action)
        except DraftActionRejected as exc:
            raise FreeDraftControllerActionRejected(
                exc.code,
                "Draft action was rejected by the Free Draft reducer.",
                reducer_code=exc.code,
                details=action.to_dict(),
            ) from exc
        self.state = replace(self.state, session_state=next_state)
        return action

    def complete_draft_with_first_legal_targets(self) -> tuple[DraftAction, ...]:
        accepted: list[DraftAction] = []
        while not self.session_state.is_complete:
            legal_targets = self.get_legal_targets()
            if not legal_targets:
                raise FreeDraftControllerActionRejected(
                    ISSUE_CONTROLLER_NO_LEGAL_TARGET,
                    "No legal target is available for the current requirement.",
                    details=self._current_requirement_dict() or {},
                )
            accepted.append(self.apply_current_action(legal_targets[0].character_id))
        return tuple(accepted)

    def set_team_assignment(self, assignment: PlayerTeamAssignment) -> None:
        validation = validate_team_assignment(self.session_state, assignment)
        if not validation.ready:
            raise FreeDraftControllerActionRejected(
                ISSUE_CONTROLLER_ASSIGNMENT_INVALID,
                "Team assignment failed Free Draft validation.",
                details={
                    "seat": assignment.seat,
                    "issue_codes": list(validation.issue_codes()),
                },
            )
        assignments = dict(self.state.team_assignments)
        assignments[assignment.seat] = assignment
        self.state = replace(self.state, team_assignments=assignments)

    def set_weapon_assignment(self, assignment: PlayerWeaponAssignment) -> None:
        team_assignment = self.state.team_assignments.get(assignment.seat)
        if team_assignment is None:
            raise FreeDraftControllerActionRejected(
                ISSUE_CONTROLLER_ASSIGNMENT_INVALID,
                "Weapon assignment requires a valid team assignment first.",
                details={"seat": assignment.seat},
            )
        validation = validate_weapon_assignment(
            self.session_state,
            team_assignment,
            assignment,
        )
        if not validation.ready:
            raise FreeDraftControllerActionRejected(
                ISSUE_CONTROLLER_ASSIGNMENT_INVALID,
                "Weapon assignment failed Free Draft validation.",
                details={
                    "seat": assignment.seat,
                    "issue_codes": list(validation.issue_codes()),
                },
            )
        assignments = dict(self.state.weapon_assignments)
        assignments[assignment.seat] = assignment
        self.state = replace(self.state, weapon_assignments=assignments)

    def assign_deterministic_teams_and_weapons(
        self,
    ) -> tuple[
        Mapping[str, FreeDraftTeamPlanReport],
        Mapping[str, FreeDraftWeaponPlanReport],
    ]:
        team_reports = {
            seat: plan_free_draft_team_assignment(self.session_state, seat)
            for seat in PVP_SEATS
        }
        for seat, report in team_reports.items():
            if not report.ready:
                raise FreeDraftControllerActionRejected(
                    ISSUE_CONTROLLER_ASSIGNMENT_INVALID,
                    "Deterministic team assignment failed validation.",
                    details={"seat": seat, "issue_codes": list(report.issue_codes())},
                )
            self.set_team_assignment(report.assignment)

        weapon_reports = {
            seat: plan_free_draft_weapon_assignment(
                self.session_state,
                team_reports[seat].assignment,
            )
            for seat in PVP_SEATS
        }
        for seat, report in weapon_reports.items():
            if not report.ready:
                raise FreeDraftControllerActionRejected(
                    ISSUE_CONTROLLER_ASSIGNMENT_INVALID,
                    "Deterministic weapon assignment failed validation.",
                    details={"seat": seat, "issue_codes": list(report.issue_codes())},
                )
            self.set_weapon_assignment(report.assignment)
        return team_reports, weapon_reports

    def set_match_timers(
        self,
        player_1_timers: PlayerMatchTimers,
        player_2_timers: PlayerMatchTimers,
    ) -> MatchResult:
        result = calculate_match_result(player_1_timers, player_2_timers)
        self.state = replace(self.state, match_result=result)
        return result

    def set_deterministic_timers(self) -> MatchResult:
        return self.set_match_timers(_player_1_timers(), _player_2_timers())

    def build_session_bundle(
        self,
        *,
        session_id: str = "",
        created_at_utc: str = "",
    ) -> PvpSessionBundle:
        if not self.session_state.is_complete:
            raise FreeDraftControllerActionRejected(
                ISSUE_CONTROLLER_BUNDLE_NOT_READY,
                "A session bundle requires a completed draft.",
            )
        missing = [
            key
            for key, ready in {
                "team_assignments": set(self.state.team_assignments) == set(PVP_SEATS),
                "weapon_assignments": set(self.state.weapon_assignments) == set(PVP_SEATS),
                "match_result": self.state.match_result is not None,
            }.items()
            if not ready
        ]
        if missing:
            raise FreeDraftControllerActionRejected(
                ISSUE_CONTROLLER_BUNDLE_NOT_READY,
                "A session bundle requires assignments and a match result.",
                details={"missing": missing},
            )
        replay_hash = self._replay_state_hash()
        return build_session_bundle(
            decks=self.state.decks_by_seat(),
            accepted_actions=self.accepted_actions,
            final_state_hash=self.session_state.state_hash(),
            replay_state_hash=replay_hash,
            team_assignments=self.state.team_assignments,
            weapon_assignments=self.state.weapon_assignments,
            match_result=self.state.match_result,
            source_mode=self.state.source_mode,
            reports={
                "controller_issue_codes": list(self.issue_codes()),
                "controller_projection_status": dict(self.to_projection().status),
            },
            draft_system=self.state.draft_system,
            session_id=session_id,
            created_at_utc=created_at_utc,
        )

    def verify_session_bundle(
        self,
        *,
        session_id: str = "",
        created_at_utc: str = "",
    ) -> PvpSessionBundleVerificationReport:
        report = verify_session_bundle(
            self.build_session_bundle(
                session_id=session_id,
                created_at_utc=created_at_utc,
            )
        )
        if not report.ready:
            self._append_issue(
                _issue(
                    ISSUE_CONTROLLER_BUNDLE_VERIFY_FAILED,
                    "Controller-built session bundle failed verification.",
                    details={"issue_codes": list(report.issue_codes())},
                )
            )
        return report

    def to_projection(
        self,
        *,
        include_debug_targets: bool = False,
    ) -> FreeDraftProjection:
        return FreeDraftProjection(
            draft_system=self._draft_system_dict(),
            status=self._status_dict(),
            current_requirement=self._current_requirement_dict(),
            progress=self._progress_dict(),
            seats=self._seats_dict(),
            draft_state=self._draft_state_dict(),
            legal_targets=self.get_legal_targets(include_excluded=include_debug_targets),
            assignments=self._assignments_dict(),
            result=(
                self.state.match_result.to_dict()
                if self.state.match_result is not None
                else None
            ),
            issue_codes=self.issue_codes(),
        )

    def to_board_projection(self, *, debug: bool = False):
        from .free_draft_board import build_free_draft_board_projection

        return build_free_draft_board_projection(self, debug=debug)

    def get_board_projection(self, *, debug: bool = False):
        return self.to_board_projection(debug=debug)

    def to_board_dict(self, *, debug: bool = False) -> dict[str, Any]:
        return self.to_board_projection(debug=debug).to_dict()

    def _append_issue(self, issue: FreeDraftControllerIssue) -> None:
        self.state = replace(self.state, issues=self.state.issues + (issue,))

    def _draft_system_dict(self) -> dict[str, Any]:
        system = self.state.draft_system
        return {
            "system_id": system.system_id,
            "version": system.version,
            "display_name": system.display_name,
        }

    def _status_dict(self) -> dict[str, Any]:
        return {
            "setup_ready": self.state.setup_ready,
            "draft_started": bool(self.accepted_actions),
            "draft_finished": self.session_state.is_complete,
            "assignments_ready": (
                set(self.state.team_assignments) == set(PVP_SEATS)
                and set(self.state.weapon_assignments) == set(PVP_SEATS)
            ),
            "result_ready": self.state.match_result is not None,
            "issue_codes": list(self.issue_codes()),
        }

    def _current_requirement_dict(self) -> dict[str, Any] | None:
        if self.session_state.is_complete:
            return None
        requirement = self.session_state.current_requirement
        if requirement is None:
            return None
        step = self.session_state.schedule.steps[self.session_state.step_index]
        return {
            "phase": step.phase,
            "step_index": self.session_state.step_index,
            "action_index": self.session_state.action_index,
            "active_seat": step.seat,
            "expected_action_type": requirement.action_type,
        }

    def _progress_dict(self) -> dict[str, Any]:
        expected_counts = self.session_state.schedule.expected_action_counts()
        return {
            "schedule_steps_total": len(self.session_state.schedule.steps),
            "actions_total_expected": _expected_action_total(self.session_state.schedule),
            "actions_accepted": len(self.accepted_actions),
            "per_seat": {
                seat: {
                    "expected_bans": expected_counts[seat].get(ACTION_BAN_CHARACTER, 0),
                    "actual_bans": len(self.session_state.banned_character_ids_for(seat)),
                    "expected_picks": expected_counts[seat].get(ACTION_PICK_CHARACTER, 0),
                    "actual_picks": len(self.session_state.picked_character_ids_for(seat)),
                }
                for seat in PVP_SEATS
            },
        }

    def _seats_dict(self) -> dict[str, Any]:
        return {
            seat: _seat_summary(
                seat,
                self.state.decks_by_seat()[seat],
                self.state.validation_by_seat()[seat],
            )
            for seat in PVP_SEATS
        }

    def _draft_state_dict(self) -> dict[str, Any]:
        return {
            "banned_character_ids": list(self.session_state.banned_character_ids),
            "banned_character_ids_by_seat": {
                seat: list(self.session_state.banned_character_ids_for(seat))
                for seat in PVP_SEATS
            },
            "picked_character_ids_by_seat": {
                seat: list(self.session_state.picked_character_ids_for(seat))
                for seat in PVP_SEATS
            },
            "state_hash": self.session_state.state_hash(),
        }

    def _assignments_dict(self) -> dict[str, Any]:
        return {
            "teams": {
                seat: _team_assignment_summary(
                    self.session_state,
                    self.state.team_assignments.get(seat),
                )
                for seat in PVP_SEATS
            },
            "weapons": {
                seat: _weapon_assignment_summary(
                    self.session_state,
                    self.state.team_assignments.get(seat),
                    self.state.weapon_assignments.get(seat),
                )
                for seat in PVP_SEATS
            },
        }

    def _replay_state_hash(self) -> str:
        initial = create_draft_session(
            self.state.player_1_deck,
            self.state.player_2_deck,
            schedule=self.state.draft_system.build_schedule(),
            validate_decks=False,
        )
        replayed = replay_draft_actions(initial, self.accepted_actions)
        return replayed.state_hash()


def _candidate_characters(
    state: DraftSessionState,
    seat: str,
    action_type: str,
) -> tuple[DraftCharacter, ...]:
    if action_type == ACTION_PICK_CHARACTER:
        return tuple(sorted(state.deck_for(seat).characters, key=_character_sort_key))
    if action_type == ACTION_BAN_CHARACTER:
        characters: list[DraftCharacter] = []
        seen: set[str] = set()
        for deck in (state.deck_for(state.opponent_seat(seat)), state.deck_for(seat)):
            for character in sorted(deck.characters, key=_character_sort_key):
                if not character.character_id or character.character_id in seen:
                    continue
                seen.add(character.character_id)
                characters.append(character)
        return tuple(characters)
    return ()


def _target_summary(
    character: DraftCharacter,
    *,
    status: str = "legal",
    reason: str = "",
) -> FreeDraftTargetSummary:
    return FreeDraftTargetSummary(
        character_id=character.character_id,
        display_name=character.display_name,
        element=character.element,
        weapon_type=character.weapon_type,
        rarity=character.rarity,
        level=character.level,
        constellation=character.constellation,
        status=status,
        reason=reason,
    )


def _seat_summary(
    seat: str,
    deck: DraftDeck,
    validation: DeckValidationReport,
) -> dict[str, Any]:
    return {
        "seat": seat,
        "nickname": deck.player.nickname,
        "deck_name": deck.deck_name,
        "character_count": len(deck.characters),
        "weapon_stack_count": len(deck.weapons),
        "validation_status": validation.status,
        "validation_issue_codes": list(validation.issue_codes()),
    }


def _team_assignment_summary(
    state: DraftSessionState,
    assignment: PlayerTeamAssignment | None,
) -> dict[str, Any]:
    if assignment is None:
        return {"status": "not_set", "team_count": 0, "team_sizes": []}
    validation = validate_team_assignment(state, assignment)
    return {
        "status": validation.status,
        "team_count": len(assignment.teams),
        "team_sizes": [len(team.character_ids) for team in assignment.teams],
        "teams": [team.to_dict() for team in assignment.teams],
        "issue_codes": list(validation.issue_codes()),
    }


def _weapon_assignment_summary(
    state: DraftSessionState,
    team_assignment: PlayerTeamAssignment | None,
    assignment: PlayerWeaponAssignment | None,
) -> dict[str, Any]:
    if assignment is None:
        return {"status": "not_set", "assignment_count": 0}
    if team_assignment is None:
        return {
            "status": "invalid",
            "assignment_count": len(assignment.assignments),
            "issue_codes": [ISSUE_CONTROLLER_ASSIGNMENT_INVALID],
        }
    validation = validate_weapon_assignment(state, team_assignment, assignment)
    return {
        "status": validation.status,
        "assignment_count": len(assignment.assignments),
        "assignments": [item.to_dict() for item in assignment.assignments],
        "issue_codes": list(validation.issue_codes()),
    }


def _deck_issues(
    player_1_validation: DeckValidationReport,
    player_2_validation: DeckValidationReport,
) -> tuple[FreeDraftControllerIssue, ...]:
    issues: list[FreeDraftControllerIssue] = []
    for seat, report in (
        (SEAT_PLAYER_1, player_1_validation),
        (SEAT_PLAYER_2, player_2_validation),
    ):
        if report.ready:
            continue
        issues.append(
            _issue(
                ISSUE_CONTROLLER_DECK_INVALID,
                "Free Draft controller was created with an invalid deck.",
                path=f"decks.{seat}",
                details={"seat": seat, "issue_codes": list(report.issue_codes())},
            )
        )
    return tuple(issues)


def _issue(
    code: str,
    message: str,
    *,
    severity: str = SEVERITY_ERROR,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> FreeDraftControllerIssue:
    return FreeDraftControllerIssue(
        code=code,
        severity=severity,
        message=message,
        path=path,
        details=details or {},
    )


def _expected_action_total(schedule: DraftSchedule) -> int:
    return sum(len(step.actions) for step in schedule.steps)


def _character_sort_key(character: DraftCharacter) -> tuple[str, str]:
    return (character.character_id.strip(), character.display_name.casefold())


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


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            payload[key] = _plain_mapping(item)
        elif isinstance(item, tuple):
            payload[key] = list(item)
        else:
            payload[key] = item
    return payload


__all__ = [
    "ISSUE_CONTROLLER_ACCOUNT_EXPORT_INVALID",
    "ISSUE_CONTROLLER_ACTION_REJECTED",
    "ISSUE_CONTROLLER_ASSIGNMENT_INVALID",
    "ISSUE_CONTROLLER_BUNDLE_NOT_READY",
    "ISSUE_CONTROLLER_BUNDLE_VERIFY_FAILED",
    "ISSUE_CONTROLLER_DECK_INVALID",
    "ISSUE_CONTROLLER_NO_LEGAL_TARGET",
    "ISSUE_CONTROLLER_REPLAY_FAILED",
    "FreeDraftController",
    "FreeDraftControllerActionRejected",
    "FreeDraftControllerIssue",
    "FreeDraftControllerState",
    "FreeDraftProjection",
    "FreeDraftTargetSummary",
]
