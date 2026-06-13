from __future__ import annotations

import unittest

from run_workspace.models import AbyssTimerState
from run_workspace.right_panel_prototype_view_model import (
    FACT_DPS_HP_MODE_MULTI_TARGET,
    FACT_DPS_HP_MODE_SOLO,
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    RightPanelGcsimChamberResult,
)
from run_workspace.session import (
    RUN_SESSION_SCHEMA_VERSION,
    RunSessionController,
)


class RunSessionControllerTest(unittest.TestCase):
    def test_default_session_state(self) -> None:
        session = RunSessionController.empty()

        self.assertEqual(session.state.schema_version, RUN_SESSION_SCHEMA_VERSION)
        self.assertEqual(session.mode, MODE_ABYSS)
        self.assertEqual(len(session.team_state.teams), 2)
        self.assertEqual(len(session.state.dps_dummy.team_state.teams), 1)
        self.assertEqual(session.selected_team_index, -1)
        self.assertEqual(session.selected_slot_index, -1)
        self.assertTrue(session.external_bonuses_enabled)
        self.assertEqual(
            session.abyss_timer_states[0],
            AbyssTimerState(team1_left_seconds=600, team2_left_seconds=600),
        )
        self.assertEqual(session.abyss_t2_manual_by_chamber, (False, False, False))
        self.assertEqual(session.gcsim_chamber_results, ())
        self.assertEqual(
            session.gcsim_status_view_model(
                target_mode=FACT_DPS_HP_MODE_SOLO,
            ).status,
            "GCSIM: not run",
        )

    def test_mode_switch_preserves_per_mode_team_state_and_clears_selection(self) -> None:
        session = RunSessionController.empty()
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma"},
        )
        session.set_selection(0, 0)

        session.set_mode(MODE_DPS_DUMMY)

        self.assertEqual(session.mode, MODE_DPS_DUMMY)
        self.assertEqual(len(session.team_state.teams), 1)
        self.assertEqual(session.selected_team_index, -1)
        self.assertEqual(session.selected_slot_index, -1)
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000089", "name": "Furina"},
        )
        session.set_selection(0, 0)

        session.set_mode(MODE_ABYSS)

        self.assertEqual(len(session.team_state.teams), 2)
        self.assertEqual(
            session.team_state.team(0).slot(0).character.id,
            "10000050",
        )
        self.assertEqual(
            session.state.dps_dummy.team_state.team(0).slot(0).character.id,
            "10000089",
        )
        self.assertEqual(session.selected_team_index, -1)
        self.assertEqual(session.selected_slot_index, -1)

    def test_abyss_t2_follows_manual_and_clamps_when_t1_crosses(self) -> None:
        session = RunSessionController.empty()

        self.assertTrue(session.set_abyss_timer_seconds(0, 1, 590))
        self.assertEqual(session.abyss_timer_states[0].team1_left_seconds, 590)
        self.assertEqual(session.abyss_timer_states[0].team2_left_seconds, 590)
        self.assertFalse(session.abyss_t2_manual_by_chamber[0])

        self.assertTrue(session.set_abyss_timer_seconds(0, 2, 585))
        self.assertEqual(session.abyss_timer_states[0].team2_left_seconds, 585)
        self.assertTrue(session.abyss_t2_manual_by_chamber[0])

        self.assertTrue(session.set_abyss_timer_seconds(0, 1, 586))
        self.assertEqual(session.abyss_timer_states[0].team1_left_seconds, 586)
        self.assertEqual(session.abyss_timer_states[0].team2_left_seconds, 585)
        self.assertTrue(session.abyss_t2_manual_by_chamber[0])

        self.assertTrue(session.set_abyss_timer_seconds(0, 1, 580))
        self.assertEqual(session.abyss_timer_states[0].team1_left_seconds, 580)
        self.assertEqual(session.abyss_timer_states[0].team2_left_seconds, 580)
        self.assertFalse(session.abyss_t2_manual_by_chamber[0])

        session.set_mode(MODE_DPS_DUMMY)
        self.assertFalse(session.set_abyss_timer_seconds(0, 1, 550))

    def test_reset_active_abyss_returns_defaults(self) -> None:
        session = RunSessionController.empty()
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma"},
        )
        session.set_selection(0, 0)
        session.set_abyss_timer_seconds(0, 1, 580)
        session.gcsim_chamber_results = (_gcsim_result(),)

        session.reset_active_run()

        default_session = RunSessionController.empty()
        self.assertEqual(session.mode, MODE_ABYSS)
        self.assertEqual(session.team_state, default_session.team_state)
        self.assertEqual(
            session.abyss_timer_states,
            default_session.abyss_timer_states,
        )
        self.assertEqual(
            session.abyss_t2_manual_by_chamber,
            default_session.abyss_t2_manual_by_chamber,
        )
        self.assertEqual(session.gcsim_chamber_results, ())
        self.assertEqual(session.selected_team_index, -1)
        self.assertEqual(session.selected_slot_index, -1)

    def test_reset_abyss_preserves_dps_dummy_team_state(self) -> None:
        session = RunSessionController.empty()
        session.set_mode(MODE_DPS_DUMMY)
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000089", "name": "Furina"},
        )
        dps_state = session.team_state
        session.set_mode(MODE_ABYSS)
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma"},
        )
        session.set_abyss_timer_seconds(0, 1, 555)

        session.reset_active_run()

        self.assertEqual(session.state.dps_dummy.team_state, dps_state)
        self.assertTrue(session.state.abyss.team_state.team(0).slot(0).is_empty)
        self.assertEqual(
            session.abyss_timer_states,
            RunSessionController.empty().abyss_timer_states,
        )

    def test_reset_dps_dummy_preserves_abyss_state(self) -> None:
        session = RunSessionController.empty()
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma"},
        )
        session.set_abyss_timer_seconds(0, 2, 570)
        session.gcsim_chamber_results = (_gcsim_result(),)
        session.set_mode(MODE_DPS_DUMMY)
        abyss_state = session.state.abyss
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000089", "name": "Furina"},
        )
        session.set_selection(0, 0)

        session.reset_active_run()

        self.assertEqual(session.mode, MODE_DPS_DUMMY)
        self.assertEqual(session.state.abyss, abyss_state)
        self.assertTrue(session.team_state.team(0).slot(0).is_empty)
        self.assertEqual(session.selected_team_index, -1)
        self.assertEqual(session.selected_slot_index, -1)

    def test_abyss_reset_restores_t2_follow_flags_and_timer_defaults(self) -> None:
        session = RunSessionController.empty()
        session.set_abyss_timer_seconds(0, 2, 585)
        self.assertTrue(session.abyss_t2_manual_by_chamber[0])

        session.reset_active_run()

        self.assertEqual(
            session.abyss_timer_states,
            RunSessionController.empty().abyss_timer_states,
        )
        self.assertEqual(session.abyss_t2_manual_by_chamber, (False, False, False))

    def test_gcsim_results_clear_and_replace_at_session_boundary(self) -> None:
        session = RunSessionController.empty()
        team0_old = _gcsim_result(chamber=2, team_index=0, side=1, dps_mean=111000)
        team1 = _gcsim_result(chamber=1, team_index=1, side=2, dps_mean=222000)
        session.gcsim_chamber_results = (team0_old, team1)

        session.clear_gcsim_results(team_index=0)

        self.assertEqual(session.gcsim_chamber_results, (team1,))

        team0_new = _gcsim_result(chamber=1, team_index=0, side=1, dps_mean=333000)
        session.replace_gcsim_results_for_team(0, (team0_new,))

        self.assertEqual(session.gcsim_chamber_results, (team1, team0_new))
        self.assertEqual(
            session.gcsim_status_view_model(
                target_mode=FACT_DPS_HP_MODE_SOLO,
            ).status,
            "GCSIM: complete",
        )

        session.clear_gcsim_results()

        self.assertEqual(session.gcsim_chamber_results, ())

    def test_selected_gcsim_result_replaces_matching_slot_and_drops_stale_team_rows(
        self,
    ) -> None:
        session = RunSessionController.empty()
        matching = _gcsim_result(
            chamber=1,
            team_index=0,
            side=1,
            rotation_hash="same-rotation",
            dps_mean=111000,
        )
        stale_same_team = _gcsim_result(
            chamber=2,
            team_index=0,
            side=1,
            rotation_hash="old-rotation",
            dps_mean=222000,
        )
        other_team = _gcsim_result(
            chamber=1,
            team_index=1,
            side=2,
            rotation_hash="other-team-rotation",
            dps_mean=333000,
        )
        incoming = _gcsim_result(
            chamber=1,
            team_index=0,
            side=1,
            rotation_hash="same-rotation",
            dps_mean=444000,
        )
        session.gcsim_chamber_results = (matching, stale_same_team, other_team)

        session.store_gcsim_chamber_result(incoming)

        self.assertEqual(
            [
                (result.team_index, result.side, result.chamber, result.dps_mean)
                for result in session.gcsim_chamber_results
            ],
            [(1, 2, 1, 333000), (0, 1, 1, 444000)],
        )
        self.assertEqual(
            session.gcsim_status_view_model(
                target_mode=FACT_DPS_HP_MODE_MULTI_TARGET,
            ).status,
            "GCSIM: stale",
        )


def _gcsim_result(
    *,
    chamber: int = 1,
    team_index: int = 0,
    side: int = 1,
    dps_mean: float = 100000,
    rotation_hash: str = "same-rotation",
) -> RightPanelGcsimChamberResult:
    return RightPanelGcsimChamberResult(
        chamber=chamber,
        team_index=team_index,
        side=side,
        status="run_passed",
        clear_time_seconds=50.0,
        dps_mean=dps_mean,
        total_damage_mean=5_000_000,
        scenario_total_hp=5_000_000,
        mode=MODE_ABYSS,
        period_start="2026-06-01",
        floor=12,
        target_mode=FACT_DPS_HP_MODE_SOLO,
        rotation_hash=rotation_hash,
    )


if __name__ == "__main__":
    unittest.main()
