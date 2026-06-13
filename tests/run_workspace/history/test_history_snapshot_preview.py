from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HistoryAbyssChamberSnapshot,
    HistoryAbyssScenarioSnapshot,
    HistoryAbyssSideResultSnapshot,
    HistoryAbyssTimerSnapshot,
    HistoryArtifactBuildSnapshot,
    HistoryCharacterSnapshot,
    HistoryDpsDummyScenarioSnapshot,
    HistoryResultSummarySnapshot,
    HistoryScenarioSnapshot,
    HistorySetBonusSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleStore,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
    HistoryWeaponSnapshot,
)
from run_workspace.history_snapshot_preview import (
    default_history_snapshot_preview_path,
    render_history_snapshot_preview,
)


class HistorySnapshotPreviewTests(unittest.TestCase):
    def test_renderer_creates_png_for_minimal_abyss_snapshot(self) -> None:
        bundle = _abyss_preview_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "history-root"
            snapshot_path = HistorySnapshotBundleStore(root).write_bundle_grouped(bundle)
            original_snapshot_text = snapshot_path.read_text(encoding="utf-8")
            output_path = default_history_snapshot_preview_path(snapshot_path)

            result = render_history_snapshot_preview(bundle, output_path=output_path)

            self.assertTrue(result.success, result.error_text)
            self.assertEqual(result.output_path, output_path)
            self.assertGreater(result.width, 0)
            self.assertGreater(result.height, 0)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(
                snapshot_path.read_text(encoding="utf-8"),
                original_snapshot_text,
            )

    def test_renderer_creates_png_for_minimal_dps_dummy_snapshot(self) -> None:
        bundle = _dps_dummy_preview_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "history-root"
            snapshot_path = HistorySnapshotBundleStore(root).write_bundle_grouped(bundle)
            output_path = default_history_snapshot_preview_path(snapshot_path)

            result = render_history_snapshot_preview(bundle, output_path=output_path)

            self.assertTrue(result.success, result.error_text)
            self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(output_path.stat().st_size, 0)

    def test_missing_image_refs_do_not_fail_rendering(self) -> None:
        bundle = _abyss_preview_bundle(
            portrait_ref="missing/portrait.png",
            weapon_icon_ref="missing/weapon.png",
            set_icon_ref="missing/set.png",
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "preview.png"

            result = render_history_snapshot_preview(bundle, output_path=output_path)

            self.assertTrue(result.success, result.error_text)
            self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


def _abyss_preview_bundle(
    *,
    portrait_ref: str = "",
    weapon_icon_ref: str = "",
    set_icon_ref: str = "",
) -> HistorySnapshotBundle:
    return HistorySnapshotBundle(
        bundle_id="preview-abyss",
        created_at="2026-06-13T12:00:00Z",
        run_type=HISTORY_RUN_TYPE_ABYSS,
        source="unit_test",
        content_language="en-us",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                label="Team 1",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            name="Thoma",
                            portrait_ref=portrait_ref,
                        ),
                        weapon=HistoryWeaponSnapshot(
                            name="Favonius Lance",
                            icon_ref=weapon_icon_ref,
                        ),
                        artifact_build=HistoryArtifactBuildSnapshot(
                            build_name="Shield support",
                            active_set_bonuses=(
                                HistorySetBonusSnapshot(
                                    set_name="Retracing Bolide",
                                    piece_count=2,
                                    icon_ref=set_icon_ref,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            HistoryTeamSnapshot(
                team_index=1,
                label="Team 2",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(name="Furina"),
                        weapon=HistoryWeaponSnapshot(name="Splendor"),
                    ),
                ),
            ),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_ABYSS,
            abyss=HistoryAbyssScenarioSnapshot(
                period_start="2026-06-01",
                period_end="2026-06-16",
                floor=12,
                chambers=(
                    HistoryAbyssChamberSnapshot(
                        chamber_index=1,
                        chamber_label="12-1",
                        timer=HistoryAbyssTimerSnapshot(
                            team1_left_seconds=540,
                            team2_left_seconds=510,
                            team1_elapsed_seconds=60,
                            team2_elapsed_seconds=30,
                            total_elapsed_seconds=90,
                        ),
                        side_results=(
                            HistoryAbyssSideResultSnapshot(
                                side=1,
                                team_index=0,
                                elapsed_seconds=60,
                                total_hp=6000000,
                                factual_dps=100000,
                                sim_result_ref="sim-1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
        result_summaries=(
            HistoryResultSummarySnapshot(
                result_type="factual_dps",
                label="Fact T1 DPS",
                team_index=0,
                chamber_index=1,
                side=1,
                dps=100000,
                elapsed_seconds=60,
            ),
            HistoryResultSummarySnapshot(
                result_type="sim_dps",
                label="Sim T1 DPS",
                team_index=0,
                chamber_index=1,
                side=1,
                dps=123456,
                elapsed_seconds=60,
                payload={"sim_result_ref": "sim-1"},
            ),
        ),
        warnings=("preview_fixture_warning",),
    )


def _dps_dummy_preview_bundle() -> HistorySnapshotBundle:
    return HistorySnapshotBundle(
        bundle_id="preview-dps-dummy",
        created_at="2026-06-13T12:10:00Z",
        run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
        source="unit_test",
        content_language="en-us",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                label="Team",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(name="Furina"),
                        weapon=HistoryWeaponSnapshot(name="Splendor"),
                    ),
                ),
            ),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
            dps_dummy=HistoryDpsDummyScenarioSnapshot(
                target_label="Training dummy",
                target_hp=1000000,
                duration_seconds=20.0,
                factual_damage=1000000.0,
                factual_dps=50000.0,
                result_status="measured",
            ),
        ),
        result_summaries=(
            HistoryResultSummarySnapshot(
                result_type="factual_dps",
                label="Dummy factual DPS",
                team_index=0,
                dps=50000.0,
                damage=1000000.0,
                elapsed_seconds=20.0,
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
