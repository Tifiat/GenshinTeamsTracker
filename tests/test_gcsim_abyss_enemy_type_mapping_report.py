from __future__ import annotations

from io import StringIO
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from run_workspace.abyss.source_data import rebuild_abyss_floor_source_data_with_rows
from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.gcsim.abyss_enemy_type_mapping_report import (
    build_abyss_enemy_type_coverage_report,
    main,
)
from run_workspace.gcsim.abyss_wave_scenario import (
    AbyssEnemyTypeMapping,
    AbyssEnemyTypeMappingRecord,
    IDENTITY_KIND_FANDOM_PAGE_TITLE,
    IDENTITY_KIND_NANOKA_MONSTER_ID,
)
from run_workspace.gcsim.enemy_type_registry import (
    GcsimEnemyTypeRegistry,
    MATCH_METHOD_AMBIGUOUS,
    MATCH_METHOD_COMPATIBLE_BASE_NAME,
    MATCH_METHOD_EXACT_NORMALIZED_NAME,
    MATCH_METHOD_MANUAL_ALIAS,
    MATCH_METHOD_MANUAL_MAPPING,
    MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
    MATCH_METHOD_SNAP_TITLE_FALLBACK,
    normalize_gcsim_enemy_name,
)
from run_workspace.gcsim.snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    DEFAULT_SNAP_MONSTER_RAW_URL,
    SNAP_CACHE_STATUS_HIT,
    SNAP_CACHE_STATUS_INVALID,
    SNAP_CACHE_STATUS_MISSING,
    SNAP_REFRESH_STATUS_NOT_NEEDED,
    SNAP_REFRESH_STATUS_SUCCESS,
    SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL,
    SNAP_SOURCE_KIND_REMOTE_URL,
    SnapMonsterTitleCandidate,
    SnapMonsterTitleIndex,
)
from tests.test_gcsim_abyss_wave_scenario import _source_data


def _cache_data(*, period_start: str = "2026-05-16", floor: int = 12):
    data = _source_data()
    rows = [replace(row, floor=floor) for row in data.enemy_rows]
    rebuilt = rebuild_abyss_floor_source_data_with_rows(data, rows)
    return replace(
        rebuilt,
        floor=floor,
        period=replace(rebuilt.period, start_date=period_start),
    )


def _cache_data_with_enemy_names(*names: str, period_start: str = "2026-05-16", floor: int = 12):
    data = _cache_data(period_start=period_start, floor=floor)
    rows = list(data.enemy_rows)
    for index, name in enumerate(names):
        rows[index] = replace(
            rows[index],
            primary_display_name=name,
            matched_nanoka_display_name=name,
            fandom_enemy_page_url=f"https://genshin-impact.fandom.com/wiki/{name.replace(' ', '_')}",
        )
    return rebuild_abyss_floor_source_data_with_rows(data, rows)


def _mapping() -> AbyssEnemyTypeMapping:
    return AbyssEnemyTypeMapping(
        records=(
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                source_id="first",
                gcsim_type="battlehardenedgroundedgeoshroom",
            ),
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_FANDOM_PAGE_TITLE,
                source_id="Second Enemy",
                gcsim_type="dummy",
            ),
        ),
        mapping_name="coverage_mapping",
    )


def _snap_titles(*pairs: tuple[str, str]) -> SnapMonsterTitleIndex:
    grouped: dict[str, list[SnapMonsterTitleCandidate]] = {}
    for name, title in pairs:
        candidate = SnapMonsterTitleCandidate(source_name=name, title=title)
        grouped.setdefault(candidate.normalized_source_name, []).append(candidate)
    return SnapMonsterTitleIndex(
        {key: tuple(value) for key, value in grouped.items()}
    )


class GcsimAbyssEnemyTypeMappingReportTest(unittest.TestCase):
    def test_coverage_report_counts_resolved_missing_and_hp_gaps(self) -> None:
        data = _source_data()
        rows = list(data.enemy_rows)
        rows[1] = replace(rows[1], nanoka_hp=None)
        data = rebuild_abyss_floor_source_data_with_rows(data, rows)

        report = build_abyss_enemy_type_coverage_report([data], _mapping())

        self.assertEqual(report.total_rows, 2)
        self.assertEqual(report.resolved_by_method[MATCH_METHOD_MANUAL_MAPPING], 2)
        self.assertEqual(report.resolved_by_source_kind[IDENTITY_KIND_NANOKA_MONSTER_ID], 1)
        self.assertEqual(report.resolved_by_source_kind[IDENTITY_KIND_FANDOM_PAGE_TITLE], 1)
        self.assertEqual(report.missing_mappings, 0)
        self.assertEqual(report.ambiguous_mappings, 0)
        self.assertEqual(report.hp_present_type_missing, 0)
        self.assertEqual(report.type_present_hp_missing, 1)
        self.assertEqual(report.resolved_rows[0]["method"], MATCH_METHOD_MANUAL_MAPPING)

    def test_coverage_report_lists_unresolved_identities(self) -> None:
        data = _source_data()
        report = build_abyss_enemy_type_coverage_report(
            [data],
            AbyssEnemyTypeMapping(
                records=(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="first",
                        gcsim_type="dummy",
                    ),
                )
            ),
        )

        self.assertEqual(report.missing_mappings, 1)
        self.assertEqual(report.hp_present_type_missing, 1)
        self.assertEqual(report.unresolved_rows[0]["enemy"], "Second Enemy")
        self.assertGreater(len(report.unresolved_rows[0]["available_identities"]), 0)

    def test_coverage_report_counts_registry_methods_and_ambiguity(self) -> None:
        data = _source_data()

        exact_report = build_abyss_enemy_type_coverage_report(
            [data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(("firstenemy", "secondenemy")),
        )
        compatible_report = build_abyss_enemy_type_coverage_report(
            [data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(("battlehardenedfirstenemy", "secondenemy")),
        )
        alias_data = rebuild_abyss_floor_source_data_with_rows(
            data,
            [
                replace(
                    data.enemy_rows[0],
                    primary_display_name="Alias Enemy",
                    matched_nanoka_display_name=None,
                    fandom_enemy_page_url="https://genshin-impact.fandom.com/wiki/Alias_Enemy",
                ),
                data.enemy_rows[1],
            ],
        )
        alias_report = build_abyss_enemy_type_coverage_report(
            [alias_data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(
                ("firstenemy", "secondenemy"),
                manual_aliases={normalize_gcsim_enemy_name("Alias Enemy"): "firstenemy"},
            ),
        )
        ambiguous_report = build_abyss_enemy_type_coverage_report(
            [data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(
                ("battlehardenedfirstenemy", "veteranfirstenemy", "secondenemy")
            ),
        )

        self.assertEqual(exact_report.resolved_by_method[MATCH_METHOD_EXACT_NORMALIZED_NAME], 2)
        self.assertEqual(
            compatible_report.resolved_by_method[MATCH_METHOD_COMPATIBLE_BASE_NAME],
            1,
        )
        self.assertEqual(alias_report.resolved_by_method[MATCH_METHOD_MANUAL_ALIAS], 1)
        self.assertEqual(ambiguous_report.ambiguous_mappings, 1)
        self.assertEqual(ambiguous_report.ambiguous_rows[0]["method"], MATCH_METHOD_AMBIGUOUS)

    def test_coverage_report_counts_snap_title_fallback_separately(self) -> None:
        data = _cache_data_with_enemy_names(
            "Assault Specialist Mek - Pneuma",
            "Second Enemy",
        )

        report = build_abyss_enemy_type_coverage_report(
            [data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(
                ("assaultspecialistmek", "secondenemy")
            ),
            snap_title_index=_snap_titles(
                ("Assault Specialist Mek - Pneuma", "Assault Specialist Mek")
            ),
        )

        self.assertEqual(report.missing_mappings, 0)
        self.assertEqual(report.resolved_by_method[MATCH_METHOD_SNAP_TITLE_FALLBACK], 1)
        self.assertEqual(report.resolved_rows[0]["gcsim_type"], "assaultspecialistmek")

    def test_coverage_report_counts_snap_title_contains_target_separately(self) -> None:
        data = _cache_data_with_enemy_names(
            "Tenebrous Papilla: Type II",
            "Second Enemy",
        )

        report = build_abyss_enemy_type_coverage_report(
            [data],
            None,
            enemy_type_registry=GcsimEnemyTypeRegistry(
                ("secondenemy", "tenebrouspapillatypei")
            ),
            snap_title_index=_snap_titles(
                ("Tenebrous Papilla: Type II", "Tenebrous Papilla")
            ),
        )

        self.assertEqual(report.missing_mappings, 0)
        self.assertEqual(
            report.resolved_by_method[MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET],
            1,
        )
        self.assertEqual(report.resolved_rows[0]["gcsim_type"], "tenebrouspapillatypei")

    def test_cli_json_report_loads_temp_cache_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            mapping_path = root / "mapping.json"
            mapping_path.write_text(
                json.dumps(
                    {
                        "mapping_name": "cli_mapping",
                        "records": [
                            {
                                "source_kind": IDENTITY_KIND_NANOKA_MONSTER_ID,
                                "source_id": "first",
                                "gcsim_type": "dummy",
                            },
                            {
                                "source_kind": IDENTITY_KIND_FANDOM_PAGE_TITLE,
                                "source_id": "Second Enemy",
                                "gcsim_type": "dummy",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            code = main(
                [
                    "--enemy-type-map",
                    str(mapping_path),
                    "--cache-file",
                    str(cache_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["report"]["total_rows"], 2)
        self.assertEqual(payload["report"]["missing_mappings"], 0)

    def test_cli_json_report_can_use_registry_source_without_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            registry_path = root / "enemies_gen.go"
            registry_path.write_text(
                'package shortcut\nvar MonsterNameToID = map[string]int{\n'
                '\t"firstenemy": 1,\n'
                '\t"secondenemy": 2,\n'
                "}\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(
            payload["report"]["resolved_by_method"][MATCH_METHOD_EXACT_NORMALIZED_NAME],
            2,
        )

    def test_managed_snap_not_read_when_primary_resolves_all_rows(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote should not be fetched")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            registry_path = _write_registry(root, "firstenemy", "secondenemy")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--use-cached-snap-monster-json",
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(root / "missing" / "Monster.json"),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["report"]["missing_mappings"], 0)
        self.assertEqual(payload["report"]["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_NOT_NEEDED)
        self.assertNotIn("checking_cached_snap_titles", payload["report"]["steps"])
        timing = payload["report"]["timing_seconds"]
        self.assertIn("primary_matching_seconds", timing)
        self.assertIn("total_report_seconds", timing)
        self.assertNotIn("cached_snap_load_seconds", timing)
        self.assertNotIn("remote_refresh_index_seconds", timing)

    def test_managed_snap_cache_resolves_without_remote_fetch(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote should not be fetched")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            snap_cache = _write_snap_cache(
                root,
                ("Assault Specialist Mek - Pneuma", "Assault Specialist Mek"),
            )
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--use-cached-snap-monster-json",
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        report = payload["report"]
        self.assertEqual(code, 0)
        self.assertEqual(report["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_HIT)
        self.assertEqual(report["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_NOT_NEEDED)
        self.assertEqual(report["resolved_by_method"][MATCH_METHOD_SNAP_TITLE_FALLBACK], 1)
        self.assertEqual(
            report["snap_cache"]["snap_resolution_counts"]["cached_snap_title_fallback"],
            1,
        )
        self.assertIn("cached_snap_load_seconds", report["timing_seconds"])
        self.assertIn("cached_snap_matching_seconds", report["timing_seconds"])
        self.assertNotIn("remote_refresh_index_seconds", report["timing_seconds"])

    def test_managed_snap_missing_cache_refreshes_and_resolves(self) -> None:
        calls: list[str] = []

        def fake_fetch(url: str, _timeout: float) -> str:
            calls.append(url)
            return json.dumps(
                [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=root / "cache",
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            snap_cache = root / "snap" / "Monster.json"
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())
            cache_written = snap_cache.is_file()

        self.assertEqual(code, 0)
        self.assertEqual(calls, [DEFAULT_SNAP_MONSTER_RAW_URL])
        self.assertTrue(cache_written)
        self.assertEqual(payload["report"]["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_MISSING)
        self.assertEqual(payload["report"]["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_SUCCESS)
        self.assertIn("rechecking_snap_titles_after_refresh", payload["report"]["steps"])
        timing = payload["report"]["timing_seconds"]
        self.assertIn("cached_snap_load_seconds", timing)
        self.assertIn("remote_refresh_index_seconds", timing)
        self.assertIn("refreshed_snap_matching_seconds", timing)

    def test_managed_snap_stale_cache_refreshes_and_retries(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps(
                [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=root / "cache",
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            snap_cache = _write_snap_cache(root, ("Unrelated", "Unrelated"))
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--use-cached-snap-monster-json",
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["report"]["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_HIT)
        self.assertEqual(payload["report"]["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_SUCCESS)
        self.assertEqual(
            payload["report"]["snap_cache"]["snap_resolution_counts"]["refreshed_snap_title_fallback"],
            1,
        )

    def test_managed_snap_insufficient_cache_without_refresh_keeps_missing(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote should not be fetched")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=root / "cache",
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            snap_cache = _write_snap_cache(root, ("Unrelated", "Unrelated"))
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--use-cached-snap-monster-json",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertEqual(payload["report"]["missing_mappings"], 1)
        self.assertEqual(payload["report"]["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_NOT_NEEDED)
        self.assertIn("cached_snap_matching_seconds", payload["report"]["timing_seconds"])

    def test_managed_snap_invalid_cache_can_refresh(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps(
                [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=root / "cache",
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            snap_cache = root / "snap" / "Monster.json"
            snap_cache.parent.mkdir(parents=True)
            snap_cache.write_text("{not-json", encoding="utf-8")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["report"]["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_INVALID)
        self.assertEqual(payload["report"]["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_SUCCESS)

    def test_managed_snap_remote_failure_is_controlled(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise OSError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=root / "cache",
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-file",
                    str(cache_path),
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(root / "snap" / "Monster.json"),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 2)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "input_error")
        self.assertIn("remote fetch failed", payload["error"])

    def test_cli_json_report_accepts_snap_monster_json_with_scan_cache_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(
                root,
                "assaultspecialistmek",
                "secondenemy",
            )
            snap_path = root / "monster.json"
            snap_path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Assault Specialist Mek - Pneuma",
                            "Title": "Assault Specialist Mek",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--snap-monster-json",
                    str(snap_path),
                    "--scan-cache-dir",
                    str(cache_root),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(
            payload["report"]["resolved_by_method"][MATCH_METHOD_SNAP_TITLE_FALLBACK],
            1,
        )

    def test_cli_json_report_accepts_snap_monster_json_url_with_fake_fetch(self) -> None:
        calls: list[str] = []

        def fake_fetch(url: str, _timeout: float) -> str:
            calls.append(url)
            return json.dumps(
                [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Assault Specialist Mek - Pneuma",
                    "Second Enemy",
                ),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(root, "assaultspecialistmek", "secondenemy")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--snap-monster-json",
                    DEFAULT_SNAP_MONSTER_GITHUB_URL,
                    "--scan-cache-dir",
                    str(cache_root),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(calls, [DEFAULT_SNAP_MONSTER_RAW_URL])
        self.assertEqual(payload["report"]["snap_source"]["kind"], SNAP_SOURCE_KIND_REMOTE_URL)
        self.assertEqual(
            payload["report"]["resolved_by_method"][MATCH_METHOD_SNAP_TITLE_FALLBACK],
            1,
        )

    def test_cli_json_report_accepts_default_remote_snap_with_fake_fetch(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps(
                [{"Name": "Tenebrous Papilla: Type II", "Title": "Tenebrous Papilla"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Tenebrous Papilla: Type II",
                    "Second Enemy",
                ),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(root, "secondenemy", "tenebrouspapillatypei")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--use-default-remote-snap-monster-json",
                    "--scan-cache-dir",
                    str(cache_root),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["report"]["snap_source"]["kind"], SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL)
        self.assertEqual(
            payload["report"]["resolved_by_method"][MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET],
            1,
        )

    def test_cli_json_report_reports_snap_network_failure_as_input_error(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise OSError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            registry_path = _write_registry(root, "firstenemy", "secondenemy")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--snap-monster-json",
                    DEFAULT_SNAP_MONSTER_RAW_URL,
                    "--cache-file",
                    str(cache_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                snap_fetcher=fake_fetch,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 2)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "input_error")
        self.assertIn("remote fetch failed", payload["error"])

    def test_bulk_scanner_finds_multiple_cache_files_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names("First Enemy", "Missing Enemy"),
                cache_dir=cache_root,
            )
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names(
                    "Battle-Hardened First Enemy",
                    "Grounded Geoshroom",
                    period_start="2026-06-16",
                ),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(
                root,
                "firstenemy",
                "battlehardenedgroundedgeoshroom",
                "veterangroundedgeoshroom",
            )
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--scan-cache-dir",
                    str(cache_root),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())
            report = payload["report"]

        self.assertEqual(code, 1)
        self.assertEqual(report["cache_file_count"], 2)
        self.assertEqual(report["total_rows"], 4)
        self.assertEqual(report["resolved_by_method"][MATCH_METHOD_EXACT_NORMALIZED_NAME], 1)
        self.assertEqual(report["resolved_by_method"][MATCH_METHOD_COMPATIBLE_BASE_NAME], 1)
        self.assertEqual(report["missing_mappings"], 1)
        self.assertEqual(report["ambiguous_mappings"], 1)
        self.assertEqual(report["hp_present_type_missing"], 1)
        self.assertEqual(report["unresolved_rows"][0]["enemy"], "Missing Enemy")
        self.assertGreater(len(report["unresolved_rows"][0]["available_identities"]), 0)
        self.assertEqual(
            report["ambiguous_rows"][0]["resolution"]["ambiguous_types"],
            ["battlehardenedgroundedgeoshroom", "veterangroundedgeoshroom"],
        )

    def test_bulk_scanner_period_and_floor_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data(period_start="2026-05-16", floor=12),
                cache_dir=cache_root,
            )
            save_abyss_floor_source_data(
                _cache_data(period_start="2026-06-16", floor=11),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(root, "firstenemy", "secondenemy")
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--scan-cache-dir",
                    str(cache_root),
                    "--period-start",
                    "2026-06-16",
                    "--floor",
                    "11",
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["report"]["cache_file_count"], 1)
        selected_path = Path(payload["report"]["cache_files"][0])
        self.assertEqual(selected_path.parent.name, "2026-06-16")
        self.assertEqual(selected_path.name, "floor_11.json")

    def test_bulk_text_output_is_compact_with_missing_and_ambiguous_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            save_abyss_floor_source_data(
                _cache_data_with_enemy_names("Missing Enemy", "Grounded Geoshroom"),
                cache_dir=cache_root,
            )
            registry_path = _write_registry(
                root,
                "battlehardenedgroundedgeoshroom",
                "veterangroundedgeoshroom",
            )
            stdout = StringIO()

            code = main(
                [
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--scan-cache-dir",
                    str(cache_root),
                    "--format",
                    "text",
                ],
                stdout=stdout,
            )
            text = stdout.getvalue()

        self.assertEqual(code, 1)
        self.assertIn("cache_files=1", text)
        self.assertIn("missing=1", text)
        self.assertIn("ambiguous=1", text)
        self.assertIn("unresolved_rows=", text)
        self.assertIn("ambiguous_rows=", text)


def _write_registry(root: Path, *target_types: str) -> Path:
    path = root / "enemies_gen.go"
    rows = "".join(f'\t"{target_type}": {index + 1},\n' for index, target_type in enumerate(target_types))
    path.write_text(
        "package shortcut\nvar MonsterNameToID = map[string]int{\n" + rows + "}\n",
        encoding="utf-8",
    )
    return path


def _write_snap_cache(root: Path, *pairs: tuple[str, str]) -> Path:
    path = root / "snap" / "Monster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([{"Name": name, "Title": title} for name, title in pairs]),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
