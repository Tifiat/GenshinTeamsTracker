from __future__ import annotations

from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.abyss.source_data import rebuild_abyss_floor_source_data_with_rows
from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.gcsim.artifact_runner import (
    GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY,
    GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION,
    GcsimArtifactRunResult,
    GcsimResultSummary,
)
from run_workspace.gcsim.smoke_cases import (
    CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG,
    MANUAL_CONFIG_MINIMAL_PATH,
    get_smoke_case,
    main,
    run_smoke_case,
)
from run_workspace.gcsim.snap_monster_titles import SNAP_CACHE_STATUS_HIT
from tests.run_workspace.gcsim.test_gcsim_abyss_wave_scenario import _source_data


class GcsimSmokeCasesTest(unittest.TestCase):
    def test_catalog_exposes_named_case_with_project_local_config(self) -> None:
        case = get_smoke_case(CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG)

        self.assertEqual(case.period_start, "2026-04-16")
        self.assertEqual(case.floor, 12)
        self.assertEqual(case.chamber, 3)
        self.assertEqual(case.side, 2)
        self.assertEqual(case.expected_enemy, "Tenebrous Papilla: Type II")
        self.assertEqual(case.expected_gcsim_type, "tenebrouspapillatypei")
        self.assertEqual(case.expected_method, "snap_title_contains_target")
        self.assertEqual(case.manual_config_path, MANUAL_CONFIG_MINIMAL_PATH)
        self.assertTrue(case.manual_config_path.is_file())
        self.assertIn("run_workspace", case.manual_config_path.parts)

    def test_case_runner_uses_defaults_cache_first_snap_and_fake_artifact(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote Snap should not be fetched when cache resolves")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "abyss-cache"
            save_abyss_floor_source_data(_case_source_data(), cache_dir=cache_dir)
            registry_path = _write_registry(root, "tenebrouspapillatypei", "secondenemy")
            snap_cache = root / "snap" / "Monster.json"
            snap_cache.parent.mkdir(parents=True)
            snap_cache.write_text(
                json.dumps(
                    [{"Name": "Tenebrous Papilla: Type II", "Title": "Tenebrous Papilla"}]
                ),
                encoding="utf-8",
            )
            calls: list[dict] = []

            def fake_artifact_run(config_text: str, **kwargs) -> GcsimArtifactRunResult:
                calls.append({"config_text": config_text, **kwargs})
                scenario_path = Path(kwargs["gtt_wave_scenario"])
                payload = json.loads(scenario_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["waves"][0]["targets"][0]["type"], "tenebrouspapillatypei")
                self.assertIn("active bennett", config_text)
                return GcsimArtifactRunResult(
                    status="passed",
                    success=True,
                    artifact_source="active_engine",
                    active_artifact_status="ready",
                    artifact_preflight_status="gtt_wave_scenario_contract_ready",
                    observed_gtt_patch_version=GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION,
                    observed_gtt_capabilities=(
                        "gtt_engine_marker",
                        GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY,
                    ),
                    required_gtt_patch_version=GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION,
                    required_gtt_capability=GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY,
                    gtt_wave_scenario_path=str(scenario_path),
                    timing_seconds={
                        "artifact_preflight_seconds": 0.01,
                        "artifact_run_seconds": 0.02,
                    },
                    summary=GcsimResultSummary(
                        schema_version="1",
                        sim_version="fake-sim",
                        dps_mean=0.0,
                        duration_mean=0.03333333333333333,
                        total_damage_mean=0.0,
                    ),
                )

            report = run_smoke_case(
                CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG,
                registry_source=registry_path,
                cache_dir=cache_dir,
                snap_cache_path=snap_cache,
                run_dir=root / "run",
                artifact_run_func=fake_artifact_run,
                snap_fetcher=fake_fetch,
            )

        self.assertTrue(report["success"])
        self.assertEqual(report["case"]["case_id"], CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG)
        self.assertEqual(report["source"]["period_start"], "2026-04-16")
        self.assertEqual(report["source"]["floor"], 12)
        self.assertEqual(report["manual_config_path"], str(MANUAL_CONFIG_MINIMAL_PATH))
        self.assertTrue(report["scenario_path"])
        self.assertEqual(report["wave_count"], 1)
        self.assertEqual(report["target_count"], 1)
        self.assertEqual(
            report["enemy_resolution_method_counts"]["snap_title_contains_target"],
            1,
        )
        self.assertEqual(report["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_HIT)
        self.assertEqual(report["snap_cache"]["refresh_status"], "remote_not_needed")
        self.assertIn("checking_cached_snap_titles", report["steps"])
        self.assertIn("running_gcsim_artifact", report["steps"])
        self.assertEqual(report["artifact"]["preflight_status"], "gtt_wave_scenario_contract_ready")
        self.assertEqual(report["artifact"]["run_status"], "passed")
        self.assertEqual(report["summary"]["sim_version"], "fake-sim")
        self.assertEqual(len(calls), 1)

    def test_cli_json_report_includes_case_and_run_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "abyss-cache"
            save_abyss_floor_source_data(_case_source_data(), cache_dir=cache_dir)
            registry_path = _write_registry(root, "tenebrouspapillatypei", "secondenemy")
            snap_cache = root / "snap" / "Monster.json"
            snap_cache.parent.mkdir(parents=True)
            snap_cache.write_text(
                json.dumps(
                    [{"Name": "Tenebrous Papilla: Type II", "Title": "Tenebrous Papilla"}]
                ),
                encoding="utf-8",
            )

            def fake_artifact_run(_config_text: str, **kwargs) -> GcsimArtifactRunResult:
                return GcsimArtifactRunResult(
                    status="passed",
                    success=True,
                    artifact_source="active_engine",
                    active_artifact_status="ready",
                    artifact_preflight_status="gtt_wave_scenario_contract_ready",
                    gtt_wave_scenario_path=str(kwargs["gtt_wave_scenario"]),
                    summary=GcsimResultSummary(sim_version="fake-sim"),
                )

            stdout = StringIO()
            code = main(
                [
                    "--case",
                    CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG,
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--cache-dir",
                    str(cache_dir),
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--run-dir",
                    str(root / "run"),
                    "--format",
                    "json",
                ],
                stdout=stdout,
                artifact_run_func=fake_artifact_run,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["case"]["case_id"], CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG)
        self.assertTrue(payload["scenario_path"])
        self.assertEqual(payload["artifact"]["run_status"], "passed")
        self.assertIn("running_gcsim_artifact", payload["steps"])


def _case_source_data():
    data = _source_data()
    rows = list(data.enemy_rows)
    row = replace(
        rows[0],
        floor=12,
        chamber=3,
        side=2,
        wave=1,
        enemy_count=1,
        primary_display_name="Tenebrous Papilla: Type II",
        matched_nanoka_display_name="Tenebrous Papilla: Type II",
        fandom_enemy_page_url="https://genshin-impact.fandom.com/wiki/Tenebrous_Papilla:_Type_II",
        display_level=100,
        nanoka_hp=3327601.0,
    )
    rebuilt = rebuild_abyss_floor_source_data_with_rows(data, [row])
    return replace(
        rebuilt,
        floor=12,
        period=replace(rebuilt.period, start_date="2026-04-16"),
    )


def _write_registry(root: Path, *target_types: str) -> Path:
    path = root / "enemies_gen.go"
    rows = "".join(f'\t"{target_type}": {index + 1},\n' for index, target_type in enumerate(target_types))
    path.write_text(
        "package shortcut\nvar MonsterNameToID = map[string]int{\n" + rows + "}\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
