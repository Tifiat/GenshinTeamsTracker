from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HistoryAbyssChamberSnapshot,
    HistoryAbyssScenarioSnapshot,
    HistoryAbyssSideResultSnapshot,
    HistoryAbyssTimerSnapshot,
    HistoryArtifactBuildSnapshot,
    HistoryBonusSourceSnapshot,
    HistoryCharacterSnapshot,
    HistoryResultSummarySnapshot,
    HistoryScenarioSnapshot,
    HistorySetBonusSnapshot,
    HistorySnapshotBundle,
    HistoryStatRowSnapshot,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
    HistoryWeaponSnapshot,
)
from run_workspace.history_snapshot_right_panel import (
    build_history_snapshot_right_panel_view_model,
    first_occupied_history_slot,
)


class HistorySnapshotRightPanelAdapterTest(unittest.TestCase):
    def test_adapter_selects_first_occupied_slot_and_resolves_bundle_assets(self) -> None:
        bundle = _bundle()
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "saved-run"
            model = build_history_snapshot_right_panel_view_model(
                bundle,
                bundle_dir=bundle_dir,
            )

        self.assertEqual(first_occupied_history_slot(bundle), (0, 1))
        self.assertEqual(model.selected_details.character_name, "Mona")
        self.assertTrue(model.teams[0].slots[1].is_selected)
        self.assertEqual(
            model.teams[0].slots[1].portrait_path,
            str(bundle_dir / "assets" / "mona.png"),
        )
        self.assertEqual(model.selected_details.weapon_name, "The Widsith")
        self.assertEqual(model.selected_details.stat_rows[0].value, "70%")
        self.assertEqual(model.selected_details.bonus_sources[0].label, "Hydro resonance")
        self.assertFalse(model.external_bonuses_enabled)
        self.assertTrue(model.chamber_rows[0].timer_editable)
        self.assertEqual(model.chamber_rows[0].factual_team1, "100,000")
        self.assertEqual(model.chamber_rows[0].sim_team1, "50s / 120k")

    def test_adapter_navigates_between_frozen_occupied_slots(self) -> None:
        model = build_history_snapshot_right_panel_view_model(
            _bundle(),
            bundle_dir=Path("bundle"),
            selected_team_index=1,
            selected_slot_index=0,
        )

        self.assertEqual(model.selected_details.character_name, "Nahida")
        self.assertTrue(model.teams[1].slots[0].is_selected)
        self.assertFalse(model.teams[0].slots[1].is_selected)


def _bundle() -> HistorySnapshotBundle:
    mona_slot = HistoryTeamSlotSnapshot(
        slot_index=1,
        character=HistoryCharacterSnapshot(
            name="Mona",
            level=90,
            constellation=1,
            element="Hydro",
            portrait_ref="assets/mona.png",
        ),
        weapon=HistoryWeaponSnapshot(
            name="The Widsith",
            level=90,
            refinement=5,
            icon_ref="assets/widsith.png",
            passive_tooltip="Saved passive",
            stat_rows=(
                HistoryStatRowSnapshot("Base ATK", "510", key="base_atk"),
            ),
        ),
        artifact_build=HistoryArtifactBuildSnapshot(
            build_name="Emblem",
            active_set_bonuses=(
                HistorySetBonusSnapshot(
                    set_uid="emblem",
                    set_name="Emblem of Severed Fate",
                    piece_count=4,
                    icon_ref="assets/emblem.png",
                ),
            ),
            crit_value=180.0,
        ),
        stat_rows=(HistoryStatRowSnapshot("CR", "70%", icon_label="CR"),),
        bonus_sources=(
            HistoryBonusSourceSnapshot(
                source_kind="team",
                source_id="hydro",
                label="Hydro resonance",
                icon_ref="assets/hydro.png",
                short_effects=("HP +25%",),
            ),
        ),
    )
    nahida_slot = HistoryTeamSlotSnapshot(
        slot_index=0,
        character=HistoryCharacterSnapshot(name="Nahida", element="Dendro"),
    )
    return HistorySnapshotBundle(
        bundle_id="history-adapter-test",
        created_at="2026-06-18T00:00:00Z",
        run_type=HISTORY_RUN_TYPE_ABYSS,
        source="test",
        content_language="en",
        external_bonuses_enabled=False,
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                slots=(HistoryTeamSlotSnapshot(slot_index=0), mona_slot),
            ),
            HistoryTeamSnapshot(team_index=1, slots=(nahida_slot,)),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_ABYSS,
            abyss=HistoryAbyssScenarioSnapshot(
                chambers=(
                    HistoryAbyssChamberSnapshot(
                        chamber_index=1,
                        chamber_label="C1",
                        timer=HistoryAbyssTimerSnapshot(
                            team1_left_seconds=540,
                            team2_left_seconds=480,
                            team1_elapsed_seconds=60,
                            team2_elapsed_seconds=60,
                            total_elapsed_seconds=120,
                        ),
                        side_results=(
                            HistoryAbyssSideResultSnapshot(
                                side=1,
                                team_index=0,
                                elapsed_seconds=60,
                                total_hp=6_000_000,
                                factual_dps=100_000,
                            ),
                            HistoryAbyssSideResultSnapshot(
                                side=2,
                                team_index=1,
                                elapsed_seconds=60,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        result_summaries=(
            HistoryResultSummarySnapshot(
                result_type="factual_dps",
                team_index=0,
                chamber_index=1,
                side=1,
                dps=100_000,
                elapsed_seconds=60,
            ),
            HistoryResultSummarySnapshot(
                result_type="sim_dps",
                team_index=0,
                chamber_index=1,
                side=1,
                dps=120_000,
                elapsed_seconds=50,
                payload={"status": "passed"},
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
