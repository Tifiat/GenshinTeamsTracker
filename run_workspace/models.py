from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


SNAPSHOT_SCHEMA_VERSION = 1
RUN_TYPE_ABYSS = "abyss"
SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL = "legacy_right_panel"
ABYSS_CHAMBER_START_SECONDS = 600

WARNING_TEAM1_LEFT_CLAMPED = "team1_left_clamped"
WARNING_TEAM2_LEFT_CLAMPED = "team2_left_clamped"
WARNING_TEAM2_ELAPSED_NEGATIVE = "team2_elapsed_negative"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _coerce_seconds(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp_seconds(value: int, *, start_seconds: int) -> int:
    return max(0, min(start_seconds, value))


@dataclass(frozen=True, slots=True)
class TeamSlotSelection:
    """Legacy-compatible team slot selection.

    Current main-window slots only expose image paths. Keep this model honest:
    do not invent character, weapon, artifact, or build ids here.
    """

    character_path: str | None = None
    weapon_path: str | None = None
    artifact_path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "character_path": self.character_path,
            "weapon_path": self.weapon_path,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True, slots=True)
class TeamComposition:
    slots: tuple[TeamSlotSelection, ...]

    def to_dict(self) -> dict[str, list[dict[str, str | None]]]:
        return {
            "slots": [slot.to_dict() for slot in self.slots],
        }


@dataclass(frozen=True, slots=True)
class AbyssTimerState:
    team1_left_seconds: int
    team2_left_seconds: int
    start_seconds: int = ABYSS_CHAMBER_START_SECONDS

    def to_dict(self) -> dict[str, int]:
        return {
            "team1_left_seconds": self.team1_left_seconds,
            "team2_left_seconds": self.team2_left_seconds,
            "start_seconds": self.start_seconds,
        }


@dataclass(frozen=True, slots=True)
class AbyssChamberResult:
    chamber_index: int
    timer_state: AbyssTimerState
    normalized_timer_state: AbyssTimerState
    team1_elapsed_seconds: int
    team2_elapsed_seconds: int
    total_elapsed_seconds: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chamber_index": self.chamber_index,
            "timer_state": self.timer_state.to_dict(),
            "normalized_timer_state": self.normalized_timer_state.to_dict(),
            "team1_elapsed_seconds": self.team1_elapsed_seconds,
            "team2_elapsed_seconds": self.team2_elapsed_seconds,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class RunSnapshotV1:
    schema_version: int
    run_type: str
    source: str
    teams: tuple[TeamComposition, ...]
    chambers: tuple[AbyssChamberResult, ...]
    total_elapsed_seconds: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_type": self.run_type,
            "source": self.source,
            "teams": [team.to_dict() for team in self.teams],
            "chambers": [chamber.to_dict() for chamber in self.chambers],
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "warnings": list(self.warnings),
        }


def calculate_abyss_chamber_result(
    timer_state: AbyssTimerState,
    *,
    chamber_index: int = 1,
) -> AbyssChamberResult:
    start_seconds = max(0, _coerce_seconds(timer_state.start_seconds))
    team1_left_raw = _coerce_seconds(timer_state.team1_left_seconds)
    team2_left_raw = _coerce_seconds(timer_state.team2_left_seconds)
    warnings: list[str] = []

    team1_left = _clamp_seconds(team1_left_raw, start_seconds=start_seconds)
    team2_left = _clamp_seconds(team2_left_raw, start_seconds=start_seconds)

    if team1_left != team1_left_raw:
        warnings.append(WARNING_TEAM1_LEFT_CLAMPED)
    if team2_left != team2_left_raw:
        warnings.append(WARNING_TEAM2_LEFT_CLAMPED)

    team1_elapsed = max(0, start_seconds - team1_left)
    team2_elapsed_raw = team1_left - team2_left
    if team2_elapsed_raw < 0:
        warnings.append(WARNING_TEAM2_ELAPSED_NEGATIVE)
        team2_elapsed = 0
    else:
        team2_elapsed = team2_elapsed_raw

    normalized_timer_state = AbyssTimerState(
        team1_left_seconds=team1_left,
        team2_left_seconds=team2_left,
        start_seconds=start_seconds,
    )
    total_elapsed = team1_elapsed + team2_elapsed

    return AbyssChamberResult(
        chamber_index=chamber_index,
        timer_state=timer_state,
        normalized_timer_state=normalized_timer_state,
        team1_elapsed_seconds=team1_elapsed,
        team2_elapsed_seconds=team2_elapsed,
        total_elapsed_seconds=total_elapsed,
        warnings=tuple(warnings),
    )


def team_slot_selection_from_legacy(slot: Any) -> TeamSlotSelection:
    return TeamSlotSelection(
        character_path=_optional_text(getattr(getattr(slot, "char", None), "image_path", None)),
        weapon_path=_optional_text(getattr(getattr(slot, "weapon", None), "image_path", None)),
        artifact_path=_optional_text(getattr(getattr(slot, "artifact", None), "image_path", None)),
    )


def team_composition_from_legacy(team_slots: Iterable[Any]) -> TeamComposition:
    return TeamComposition(
        slots=tuple(team_slot_selection_from_legacy(slot) for slot in team_slots),
    )


def abyss_timer_state_from_legacy_floor(floor: Any) -> AbyssTimerState:
    return AbyssTimerState(
        team1_left_seconds=_coerce_seconds(getattr(getattr(floor, "t1", None), "seconds_left", 0)),
        team2_left_seconds=_coerce_seconds(getattr(getattr(floor, "t2", None), "seconds_left", 0)),
    )


def build_legacy_abyss_run_snapshot(
    teams: Sequence[Iterable[Any]],
    floors: Sequence[Any],
) -> RunSnapshotV1:
    team_compositions = tuple(team_composition_from_legacy(team) for team in teams)
    chambers = tuple(
        calculate_abyss_chamber_result(
            abyss_timer_state_from_legacy_floor(floor),
            chamber_index=index,
        )
        for index, floor in enumerate(floors, start=1)
    )
    warnings = tuple(
        warning
        for chamber in chambers
        for warning in chamber.warnings
    )

    return RunSnapshotV1(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        run_type=RUN_TYPE_ABYSS,
        source=SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL,
        teams=team_compositions,
        chambers=chambers,
        total_elapsed_seconds=sum(chamber.total_elapsed_seconds for chamber in chambers),
        warnings=warnings,
    )
