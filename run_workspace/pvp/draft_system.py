"""Registered PvP draft-system adapters.

Draft systems are executable GTT flow adapters. They are intentionally separate
from imported ruleset/balance data, which may provide costs, tiers, thresholds,
and seasonal restrictions but does not become an engine by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .deck import FREE_DRAFT_V0_RULESET_ID, FREE_DRAFT_V0_RULESET_NAME
from .schedule import (
    ACTION_ASSIGN_TEAM_SLOT,
    ACTION_ASSIGN_WEAPON,
    ACTION_BAN_CHARACTER,
    ACTION_FINISH_MATCH,
    ACTION_PICK_CHARACTER,
    ACTION_SET_READY,
    ACTION_SET_TIMER,
    DraftSchedule,
    build_default_free_draft_v0_schedule,
    default_free_draft_v0_config,
)


DRAFT_SYSTEM_FREE_DRAFT_V0 = FREE_DRAFT_V0_RULESET_ID
DRAFT_SYSTEM_RULESET_DATA_NONE = "none"
DRAFT_SYSTEM_RULESET_DATA_OPTIONAL = "optional"
DRAFT_SYSTEM_VERSION_FREE_DRAFT_V0 = "1"


class UnknownDraftSystemError(KeyError):
    def __init__(self, system_id: str) -> None:
        super().__init__(system_id)
        self.system_id = system_id
        self.code = "unknown_draft_system"


@dataclass(frozen=True, slots=True)
class DraftSystemDefinition:
    system_id: str
    version: str
    display_name: str
    description: str
    schedule_builder: Callable[[], DraftSchedule]
    supported_action_types: tuple[str, ...]
    teams_per_player: int
    characters_per_team: int
    picked_characters_per_player: int
    bans_per_player: int
    weapons_required: bool
    immunes_supported: bool
    mirror_supported: bool
    ruleset_data_requirement: str
    deterministic_smoke_planner_supported: bool

    def build_schedule(self) -> DraftSchedule:
        return self.schedule_builder()

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "supported_action_types": list(self.supported_action_types),
            "teams_per_player": self.teams_per_player,
            "characters_per_team": self.characters_per_team,
            "picked_characters_per_player": self.picked_characters_per_player,
            "bans_per_player": self.bans_per_player,
            "weapons_required": self.weapons_required,
            "immunes_supported": self.immunes_supported,
            "mirror_supported": self.mirror_supported,
            "ruleset_data_requirement": self.ruleset_data_requirement,
            "deterministic_smoke_planner_supported": (
                self.deterministic_smoke_planner_supported
            ),
        }


def list_draft_systems() -> tuple[DraftSystemDefinition, ...]:
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def get_draft_system(system_id: str) -> DraftSystemDefinition | None:
    return _REGISTRY.get(system_id)


def require_draft_system(system_id: str) -> DraftSystemDefinition:
    system = get_draft_system(system_id)
    if system is None:
        raise UnknownDraftSystemError(system_id)
    return system


def free_draft_v0_definition() -> DraftSystemDefinition:
    config = default_free_draft_v0_config()
    return DraftSystemDefinition(
        system_id=DRAFT_SYSTEM_FREE_DRAFT_V0,
        version=DRAFT_SYSTEM_VERSION_FREE_DRAFT_V0,
        display_name=FREE_DRAFT_V0_RULESET_NAME,
        description=(
            "Offline Free Draft v0 flow: prebans, picks, middle bans, "
            "post-draft teams, weapons, timers, and match result."
        ),
        schedule_builder=build_default_free_draft_v0_schedule,
        supported_action_types=(
            ACTION_BAN_CHARACTER,
            ACTION_PICK_CHARACTER,
            ACTION_ASSIGN_TEAM_SLOT,
            ACTION_ASSIGN_WEAPON,
            ACTION_SET_TIMER,
            ACTION_SET_READY,
            ACTION_FINISH_MATCH,
        ),
        teams_per_player=config.teams_per_player,
        characters_per_team=config.team_size,
        picked_characters_per_player=config.picks_per_player,
        bans_per_player=config.total_bans_per_player,
        weapons_required=True,
        immunes_supported=False,
        mirror_supported=False,
        ruleset_data_requirement=DRAFT_SYSTEM_RULESET_DATA_NONE,
        deterministic_smoke_planner_supported=True,
    )


_REGISTRY: dict[str, DraftSystemDefinition] = {
    DRAFT_SYSTEM_FREE_DRAFT_V0: free_draft_v0_definition(),
}
