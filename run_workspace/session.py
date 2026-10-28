"""Typed live Run Session ownership for the AppShell adapter.

This is the first narrow extraction from `ui.app_shell.AppShellController`.
It owns current in-memory run state only: mode, per-mode TeamBuilder state,
selection, Abyss timers/follow flags, external-bonus toggle state, and compact
runtime GCSIM chamber results. Durable save/history snapshots remain future
work in `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from run_workspace.models import (
    AbyssTimerState,
    clamp_abyss_timer_edit_seconds,
    default_abyss_timer_states,
)
from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    RightPanelGcsimChamberResult,
    RightPanelGcsimStatusViewModel,
)
from run_workspace.team_builder import TeamBuilderState, create_empty_team_builder_state


RUN_SESSION_SCHEMA_VERSION = 1
MODE_TEAM_COUNTS = {
    MODE_ABYSS: 2,
    MODE_DPS_DUMMY: 1,
}


def normalize_run_mode(mode: str) -> str:
    return MODE_DPS_DUMMY if mode == MODE_DPS_DUMMY else MODE_ABYSS


def empty_team_state_for_mode(mode: str) -> TeamBuilderState:
    return create_empty_team_builder_state(
        team_count=MODE_TEAM_COUNTS[normalize_run_mode(mode)]
    )


@dataclass(frozen=True, slots=True)
class AbyssRunState:
    team_state: TeamBuilderState = field(
        default_factory=lambda: empty_team_state_for_mode(MODE_ABYSS)
    )
    timer_states: tuple[AbyssTimerState, ...] = field(
        default_factory=default_abyss_timer_states
    )
    t2_manual_by_chamber: tuple[bool, ...] = ()
    gcsim_chamber_results: tuple[RightPanelGcsimChamberResult, ...] = ()

    def __post_init__(self) -> None:
        if len(self.t2_manual_by_chamber) != len(self.timer_states):
            object.__setattr__(
                self,
                "t2_manual_by_chamber",
                tuple(False for _ in self.timer_states),
            )

    def with_team_state(self, team_state: TeamBuilderState) -> "AbyssRunState":
        return replace(self, team_state=team_state)

    def with_timer_seconds(
        self,
        chamber_index: int,
        team_number: int,
        seconds_left: int,
    ) -> tuple[bool, "AbyssRunState"]:
        index = int(chamber_index)
        if index < 0 or index >= len(self.timer_states):
            return False, self
        team = int(team_number)
        if team not in (1, 2):
            return False, self

        current = self.timer_states[index]
        t2_manual = list(self.t2_manual_by_chamber)
        if team == 1:
            seconds = clamp_abyss_timer_edit_seconds(seconds_left)
            team2_left_seconds = current.team2_left_seconds
            if t2_manual[index]:
                if seconds < team2_left_seconds:
                    team2_left_seconds = seconds
                    t2_manual[index] = False
            else:
                team2_left_seconds = seconds
            if (
                current.team1_left_seconds == seconds
                and current.team2_left_seconds == team2_left_seconds
                and tuple(t2_manual) == self.t2_manual_by_chamber
            ):
                return False, self
            updated = AbyssTimerState(
                team1_left_seconds=seconds,
                team2_left_seconds=team2_left_seconds,
                start_seconds=current.start_seconds,
            )
        else:
            seconds = clamp_abyss_timer_edit_seconds(
                seconds_left,
                start_seconds=current.team1_left_seconds,
            )
            if current.team2_left_seconds == seconds and t2_manual[index]:
                return False, self
            t2_manual[index] = True
            updated = AbyssTimerState(
                team1_left_seconds=current.team1_left_seconds,
                team2_left_seconds=seconds,
                start_seconds=current.start_seconds,
            )

        states = list(self.timer_states)
        states[index] = updated
        return True, replace(
            self,
            timer_states=tuple(states),
            t2_manual_by_chamber=tuple(t2_manual),
        )

    def with_gcsim_chamber_results(
        self,
        results: tuple[RightPanelGcsimChamberResult, ...],
    ) -> "AbyssRunState":
        return replace(self, gcsim_chamber_results=tuple(results))

    def clear_gcsim_results(self, team_index: int | None = None) -> "AbyssRunState":
        if team_index is None:
            return self.with_gcsim_chamber_results(())
        normalized_team_index = int(team_index)
        return self.with_gcsim_chamber_results(
            tuple(
                result
                for result in self.gcsim_chamber_results
                if int(result.team_index) != normalized_team_index
            )
        )

    def clear_gcsim_chamber_result(
        self,
        *,
        team_index: int,
        chamber: int,
        side: int,
    ) -> "AbyssRunState":
        normalized_team_index = int(team_index)
        normalized_chamber = int(chamber)
        normalized_side = int(side)
        return self.with_gcsim_chamber_results(
            tuple(
                result
                for result in self.gcsim_chamber_results
                if not _same_gcsim_result_slot(
                    result,
                    team_index=normalized_team_index,
                    chamber=normalized_chamber,
                    side=normalized_side,
                )
            )
        )

    def replace_gcsim_results_for_team(
        self,
        team_index: int,
        results: tuple[RightPanelGcsimChamberResult, ...],
    ) -> "AbyssRunState":
        normalized_team_index = int(team_index)
        retained = tuple(
            result
            for result in self.gcsim_chamber_results
            if int(result.team_index) != normalized_team_index
        )
        return self.with_gcsim_chamber_results((*retained, *tuple(results)))

    def store_gcsim_chamber_result(
        self,
        result: RightPanelGcsimChamberResult,
    ) -> "AbyssRunState":
        retained = []
        for existing in self.gcsim_chamber_results:
            if _same_gcsim_result_slot(
                existing,
                team_index=result.team_index,
                chamber=result.chamber,
                side=result.side,
            ):
                continue
            if (
                int(existing.team_index) == int(result.team_index)
                and int(existing.side) == int(result.side)
                and not _compatible_gcsim_chamber_result(existing, result)
            ):
                continue
            retained.append(existing)
        return self.with_gcsim_chamber_results((*retained, result))

    def gcsim_status_view_model(
        self,
        *,
        target_mode: str,
    ) -> RightPanelGcsimStatusViewModel:
        if not self.gcsim_chamber_results:
            return RightPanelGcsimStatusViewModel(status="GCSIM: not run")
        stale = any(
            result.target_mode != target_mode or result.mode != MODE_ABYSS
            for result in self.gcsim_chamber_results
        )
        if stale:
            return RightPanelGcsimStatusViewModel(status="GCSIM: stale")
        if all(result.passed for result in self.gcsim_chamber_results):
            return RightPanelGcsimStatusViewModel(status="GCSIM: complete")
        if any(result.passed for result in self.gcsim_chamber_results):
            return RightPanelGcsimStatusViewModel(status="GCSIM: partial")
        return RightPanelGcsimStatusViewModel(status="GCSIM: failed")


@dataclass(frozen=True, slots=True)
class DpsDummyRunState:
    team_state: TeamBuilderState = field(
        default_factory=lambda: empty_team_state_for_mode(MODE_DPS_DUMMY)
    )

    def with_team_state(self, team_state: TeamBuilderState) -> "DpsDummyRunState":
        return replace(self, team_state=team_state)


@dataclass(frozen=True, slots=True)
class RunSessionState:
    active_mode: str = MODE_ABYSS
    selected_team_index: int = -1
    selected_slot_index: int = -1
    external_bonuses_enabled: bool = True
    abyss: AbyssRunState = field(default_factory=AbyssRunState)
    dps_dummy: DpsDummyRunState = field(default_factory=DpsDummyRunState)
    schema_version: int = RUN_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_mode", normalize_run_mode(self.active_mode))

    @classmethod
    def empty(cls) -> "RunSessionState":
        return cls()

    @property
    def team_state(self) -> TeamBuilderState:
        if self.active_mode == MODE_DPS_DUMMY:
            return self.dps_dummy.team_state
        return self.abyss.team_state

    @property
    def mode_states(self) -> dict[str, TeamBuilderState]:
        return {
            MODE_ABYSS: self.abyss.team_state,
            MODE_DPS_DUMMY: self.dps_dummy.team_state,
        }

    def with_team_state(self, team_state: TeamBuilderState) -> "RunSessionState":
        if self.active_mode == MODE_DPS_DUMMY:
            return replace(self, dps_dummy=self.dps_dummy.with_team_state(team_state))
        return replace(self, abyss=self.abyss.with_team_state(team_state))

    def with_mode_states(
        self,
        mode_states: dict[str, TeamBuilderState],
    ) -> "RunSessionState":
        abyss = self.abyss
        dps_dummy = self.dps_dummy
        if MODE_ABYSS in mode_states:
            abyss = abyss.with_team_state(mode_states[MODE_ABYSS])
        if MODE_DPS_DUMMY in mode_states:
            dps_dummy = dps_dummy.with_team_state(mode_states[MODE_DPS_DUMMY])
        return replace(self, abyss=abyss, dps_dummy=dps_dummy)

    def clear_selection(self) -> "RunSessionState":
        return replace(self, selected_team_index=-1, selected_slot_index=-1)

    def reset_active_run(self) -> "RunSessionState":
        if self.active_mode == MODE_DPS_DUMMY:
            return replace(
                self,
                dps_dummy=DpsDummyRunState(),
                selected_team_index=-1,
                selected_slot_index=-1,
            )
        return replace(
            self,
            abyss=AbyssRunState(),
            selected_team_index=-1,
            selected_slot_index=-1,
        )


@dataclass
class RunSessionController:
    """Mutable adapter around immutable typed session state."""

    state: RunSessionState = field(default_factory=RunSessionState.empty)

    @classmethod
    def empty(cls) -> "RunSessionController":
        return cls(RunSessionState.empty())

    @property
    def mode(self) -> str:
        return self.state.active_mode

    @property
    def team_state(self) -> TeamBuilderState:
        return self.state.team_state

    @team_state.setter
    def team_state(self, team_state: TeamBuilderState) -> None:
        self.state = self.state.with_team_state(team_state)

    @property
    def mode_states(self) -> dict[str, TeamBuilderState]:
        return self.state.mode_states

    @mode_states.setter
    def mode_states(self, mode_states: dict[str, TeamBuilderState]) -> None:
        self.state = self.state.with_mode_states(dict(mode_states))

    @property
    def selected_team_index(self) -> int:
        return self.state.selected_team_index

    @property
    def selected_slot_index(self) -> int:
        return self.state.selected_slot_index

    @property
    def external_bonuses_enabled(self) -> bool:
        return self.state.external_bonuses_enabled

    @external_bonuses_enabled.setter
    def external_bonuses_enabled(self, enabled: bool) -> None:
        self.state = replace(self.state, external_bonuses_enabled=bool(enabled))

    @property
    def abyss_timer_states(self) -> tuple[AbyssTimerState, ...]:
        return self.state.abyss.timer_states

    @property
    def abyss_t2_manual_by_chamber(self) -> tuple[bool, ...]:
        return self.state.abyss.t2_manual_by_chamber

    @property
    def gcsim_chamber_results(self) -> tuple[RightPanelGcsimChamberResult, ...]:
        return self.state.abyss.gcsim_chamber_results

    @gcsim_chamber_results.setter
    def gcsim_chamber_results(
        self,
        results: tuple[RightPanelGcsimChamberResult, ...],
    ) -> None:
        self._set_abyss(self.state.abyss.with_gcsim_chamber_results(tuple(results)))

    def set_mode(self, mode: str) -> None:
        previous_mode = self.mode
        normalized_mode = normalize_run_mode(mode)
        self.state = replace(self.state, active_mode=normalized_mode).clear_selection()
        if previous_mode != normalized_mode and normalized_mode != MODE_ABYSS:
            self.clear_gcsim_results()

    def set_selection(self, team_index: int, slot_index: int) -> None:
        self.state = replace(
            self.state,
            selected_team_index=int(team_index),
            selected_slot_index=int(slot_index),
        )

    def toggle_slot_selection(self, team_index: int, slot_index: int) -> None:
        if (
            self.selected_team_index == int(team_index)
            and self.selected_slot_index == int(slot_index)
        ):
            self.clear_selection()
            return
        self.set_selection(team_index, slot_index)

    def clear_selection(self) -> None:
        self.state = self.state.clear_selection()

    def reset_active_run(self) -> None:
        self.state = self.state.reset_active_run()

    def set_abyss_timer_seconds(
        self,
        chamber_index: int,
        team_number: int,
        seconds_left: int,
    ) -> bool:
        if self.mode != MODE_ABYSS:
            return False
        changed, abyss = self.state.abyss.with_timer_seconds(
            chamber_index,
            team_number,
            seconds_left,
        )
        if changed:
            self._set_abyss(abyss)
        return changed

    def clear_gcsim_results(self, team_index: int | None = None) -> None:
        self._set_abyss(self.state.abyss.clear_gcsim_results(team_index))

    def clear_gcsim_chamber_result(
        self,
        *,
        team_index: int,
        chamber: int,
        side: int,
    ) -> None:
        self._set_abyss(
            self.state.abyss.clear_gcsim_chamber_result(
                team_index=team_index,
                chamber=chamber,
                side=side,
            )
        )

    def replace_gcsim_results_for_team(
        self,
        team_index: int,
        results: tuple[RightPanelGcsimChamberResult, ...],
    ) -> None:
        self._set_abyss(
            self.state.abyss.replace_gcsim_results_for_team(team_index, results)
        )

    def store_gcsim_chamber_result(
        self,
        result: RightPanelGcsimChamberResult,
    ) -> None:
        self._set_abyss(self.state.abyss.store_gcsim_chamber_result(result))

    def gcsim_status_view_model(
        self,
        *,
        target_mode: str,
    ) -> RightPanelGcsimStatusViewModel:
        if self.mode != MODE_ABYSS:
            return RightPanelGcsimStatusViewModel(status="GCSIM: not configured")
        return self.state.abyss.gcsim_status_view_model(target_mode=target_mode)

    def _set_abyss(self, abyss: AbyssRunState) -> None:
        self.state = replace(self.state, abyss=abyss)


def _same_gcsim_result_slot(
    result: RightPanelGcsimChamberResult,
    *,
    team_index: int,
    chamber: int,
    side: int,
) -> bool:
    return (
        int(result.team_index) == int(team_index)
        and int(result.chamber) == int(chamber)
        and int(result.side) == int(side)
    )


def _compatible_gcsim_chamber_result(
    current: RightPanelGcsimChamberResult,
    incoming: RightPanelGcsimChamberResult,
) -> bool:
    return (
        current.mode == incoming.mode
        and current.period_start == incoming.period_start
        and int(current.floor) == int(incoming.floor)
        and current.target_mode == incoming.target_mode
        and current.rotation_hash == incoming.rotation_hash
    )


__all__ = [
    "AbyssRunState",
    "DpsDummyRunState",
    "MODE_TEAM_COUNTS",
    "RUN_SESSION_SCHEMA_VERSION",
    "RunSessionController",
    "RunSessionState",
    "empty_team_state_for_mode",
    "normalize_run_mode",
]
