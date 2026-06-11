from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .deck import FREE_DRAFT_V0_RULESET_ID, FREE_DRAFT_V0_RULESET_NAME


SEAT_PLAYER_1 = "player_1"
SEAT_PLAYER_2 = "player_2"
PVP_SEATS = (SEAT_PLAYER_1, SEAT_PLAYER_2)

PHASE_PREBAN = "preban"
PHASE_PICK = "pick"

ACTION_BAN_CHARACTER = "ban_character"
ACTION_PICK_CHARACTER = "pick_character"
ACTION_ASSIGN_TEAM_SLOT = "assign_team_slot"
ACTION_ASSIGN_WEAPON = "assign_weapon"
ACTION_SET_TIMER = "set_timer"
ACTION_SET_READY = "set_ready"
ACTION_FINISH_MATCH = "finish_match"


@dataclass(frozen=True, slots=True)
class FreeDraftV0Config:
    ruleset_id: str = FREE_DRAFT_V0_RULESET_ID
    ruleset_name: str = FREE_DRAFT_V0_RULESET_NAME
    teams_per_player: int = 2
    team_size: int = 4
    picks_per_player: int = 8
    total_bans_per_player: int = 3
    middle_bans_per_player: int = 1
    prebans_per_player: int = 2
    costs_enabled: bool = False
    tiers_enabled: bool = False
    immune_enabled: bool = False
    traveler_supported: bool = False

    @property
    def minimum_characters_per_deck(self) -> int:
        return self.picks_per_player + self.total_bans_per_player

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_name": self.ruleset_name,
            "teams_per_player": self.teams_per_player,
            "team_size": self.team_size,
            "picks_per_player": self.picks_per_player,
            "total_bans_per_player": self.total_bans_per_player,
            "middle_bans_per_player": self.middle_bans_per_player,
            "prebans_per_player": self.prebans_per_player,
            "costs_enabled": self.costs_enabled,
            "tiers_enabled": self.tiers_enabled,
            "immune_enabled": self.immune_enabled,
            "traveler_supported": self.traveler_supported,
        }


@dataclass(frozen=True, slots=True)
class DraftActionRequirement:
    action_type: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.action_type}


@dataclass(frozen=True, slots=True)
class DraftScheduleStep:
    phase: str
    seat: str
    actions: tuple[DraftActionRequirement, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "seat": self.seat,
            "actions": [item.to_dict() for item in self.actions],
        }


@dataclass(frozen=True, slots=True)
class DraftSchedule:
    ruleset_id: str
    steps: tuple[DraftScheduleStep, ...]

    def expected_action_counts(self) -> dict[str, dict[str, int]]:
        counts = {
            seat: {
                ACTION_BAN_CHARACTER: 0,
                ACTION_PICK_CHARACTER: 0,
            }
            for seat in PVP_SEATS
        }
        for step in self.steps:
            seat_counts = counts.setdefault(step.seat, {})
            for action in step.actions:
                seat_counts[action.action_type] = (
                    seat_counts.get(action.action_type, 0) + 1
                )
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "steps": [step.to_dict() for step in self.steps],
        }


def default_free_draft_v0_config() -> FreeDraftV0Config:
    return FreeDraftV0Config()


def build_default_free_draft_v0_schedule() -> DraftSchedule:
    return DraftSchedule(
        ruleset_id=FREE_DRAFT_V0_RULESET_ID,
        steps=(
            _step(PHASE_PREBAN, SEAT_PLAYER_1, ACTION_BAN_CHARACTER),
            _step(PHASE_PREBAN, SEAT_PLAYER_2, ACTION_BAN_CHARACTER),
            _step(PHASE_PREBAN, SEAT_PLAYER_1, ACTION_BAN_CHARACTER),
            _step(PHASE_PREBAN, SEAT_PLAYER_2, ACTION_BAN_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_BAN_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_BAN_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
            _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER),
        ),
    )


def _step(
    phase: str,
    seat: str,
    *actions: str,
) -> DraftScheduleStep:
    return DraftScheduleStep(
        phase=phase,
        seat=seat,
        actions=tuple(DraftActionRequirement(action) for action in actions),
    )
