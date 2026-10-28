from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.abyss.source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
    AbyssPeriod,
    AbyssWaveSourceData,
)
from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.history_browser_catalog import load_history_browser_catalog
from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HistoryAbyssScenarioSnapshot,
    HistoryCharacterSnapshot,
    HistoryScenarioSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleStore,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
)


class HistoryBrowserCatalogTest(unittest.TestCase):
    def test_catalog_merges_cache_only_and_snapshot_periods_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            snapshot_root = root / "snapshots"
            save_abyss_floor_source_data(
                _source_data("2026-05-16"),
                cache_dir=cache_dir,
            )
            save_abyss_floor_source_data(
                _source_data("2026-04-16"),
                cache_dir=cache_dir,
            )
            bundle = _bundle("run-1", "2026-06-16")
            HistorySnapshotBundleStore(snapshot_root).write_bundle_grouped(bundle)
            period_path = root / "period.json"
            period_path.write_text(
                json.dumps({"startDate": "2026-04-16"}),
                encoding="utf-8",
            )
            before = period_path.read_bytes()

            catalog = load_history_browser_catalog(
                snapshot_root,
                abyss_cache_dir=cache_dir,
                current_period_path=period_path,
            )

            self.assertEqual(
                [item.period_start for item in catalog.periods],
                ["2026-06-16", "2026-05-16", "2026-04-16"],
            )
            self.assertEqual(catalog.current_period_start, "2026-04-16")
            self.assertEqual(len(catalog.periods[0].runs), 1)
            self.assertEqual(len(catalog.periods[1].runs), 0)
            self.assertTrue(catalog.periods[1].from_cache)
            self.assertEqual(period_path.read_bytes(), before)

    def test_snapshot_visual_rejects_absolute_non_bundle_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _bundle("run-absolute", "2026-06-16", portrait="C:/live.png")
            HistorySnapshotBundleStore(root).write_bundle_grouped(bundle)

            catalog = load_history_browser_catalog(root, abyss_cache_dir=root / "none")

            slot = catalog.periods[0].runs[0].teams[0].slots[0]
            self.assertEqual(slot.portrait_path, "")


def _bundle(
    bundle_id: str,
    period_start: str,
    *,
    portrait: str = "",
) -> HistorySnapshotBundle:
    return HistorySnapshotBundle(
        bundle_id=bundle_id,
        created_at="2026-06-19T12:00:00Z",
        run_type=HISTORY_RUN_TYPE_ABYSS,
        source="test",
        content_language="en",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            name="Furina",
                            portrait_ref=portrait,
                        ),
                    ),
                ),
            ),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_ABYSS,
            abyss=HistoryAbyssScenarioSnapshot(
                period_start=period_start,
                floor=12,
            ),
        ),
    )


def _source_data(period_start: str) -> AbyssFloorSourceData:
    enemy = AbyssEnemySourceRow(
        floor=12,
        chamber=1,
        side=1,
        side_name="First Half",
        wave=1,
        enemy_count=2,
        display_level=100,
        primary_display_name="Test Enemy",
        fandom_enemy_page_url=None,
        fandom_icon_url=None,
        matched_nanoka_display_name=None,
        nanoka_monster_id=None,
        nanoka_icon_url=None,
        nanoka_enemy_detail_url=None,
        nanoka_hp=500_000,
        hp_source="test",
        match_method="test",
        match_confidence="high",
    )
    wave = AbyssWaveSourceData(
        wave=1,
        enemies=(enemy,),
        solo_target_hp=500_000,
        multi_target_hp=1_000_000,
        selected_solo_enemy_name="Test Enemy",
    )
    side = AbyssChamberSideSourceData(
        floor=12,
        chamber=1,
        side=1,
        side_name="First Half",
        waves=(wave,),
        solo_target_hp=500_000,
        multi_target_hp=1_000_000,
    )
    return AbyssFloorSourceData(
        floor=12,
        period=AbyssPeriod(period_start, "2026-06-01", "test"),
        source_urls={},
        enemy_rows=(enemy,),
        side_summaries=(side,),
    )


if __name__ == "__main__":
    unittest.main()
