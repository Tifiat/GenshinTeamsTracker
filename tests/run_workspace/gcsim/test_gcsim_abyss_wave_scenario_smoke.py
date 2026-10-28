from __future__ import annotations

from dataclasses import replace
from io import StringIO
import json
import tempfile
import unittest
from pathlib import Path

from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.gcsim.abyss_wave_scenario_smoke import main
from run_workspace.gcsim.artifact_runner import (
    GcsimArtifactRunResult,
    GcsimResultSummary,
)
from run_workspace.gcsim.snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    DEFAULT_SNAP_MONSTER_RAW_URL,
    SNAP_CACHE_STATUS_HIT,
    SNAP_REFRESH_STATUS_SUCCESS,
    SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL,
    SNAP_SOURCE_KIND_REMOTE_URL,
)
from tests.run_workspace.gcsim.test_gcsim_abyss_wave_scenario import _source_data


def _write_enemy_type_map(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "mapping_name": "test_cli_enemy_type_map",
                "enemy_types_by_nanoka_monster_id": {
                    "first": "battlehardenedgroundedgeoshroom",
                    "second": "dummy",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


class GcsimAbyssWaveScenarioSmokeTest(unittest.TestCase):
    def test_explicit_period_cache_path_writes_schema_v1_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = _source_data()
            save_abyss_floor_source_data(data, cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
            mapping_path = _write_enemy_type_map(root / "enemy_types.json")
            snap_path = root / "monster.json"
            snap_path.write_text(
                json.dumps([{"Name": "First Enemy", "Title": "First Enemy"}]),
                encoding="utf-8",
            )
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--floor",
                    "12",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--enemy-type-map",
                    str(mapping_path),
                    "--snap-monster-json",
                    str(snap_path),
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["source"]["mode"], "explicit_period")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["spawn_policy"], "group_clear")
        self.assertEqual([len(wave["targets"]) for wave in payload["waves"]], [2, 1])
        self.assertEqual(payload["waves"][0]["targets"][0]["type"], "battlehardenedgroundedgeoshroom")
        self.assertNotIn("radius", payload["waves"][0]["targets"][0])

    def test_current_period_path_uses_temp_period_file_and_cache_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = _source_data()
            save_abyss_floor_source_data(data, cache_dir=root / "cache")
            period_path = root / "period.json"
            period_path.write_text(
                json.dumps({"startDate": "2026-05-16"}),
                encoding="utf-8",
            )
            scenario_path = root / "scenario.json"
            mapping_path = _write_enemy_type_map(root / "enemy_types.json")
            stdout = StringIO()

            code = main(
                [
                    "--period-path",
                    str(period_path),
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--enemy-type-map",
                    str(mapping_path),
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())
            scenario_exists = scenario_path.is_file()

        self.assertEqual(code, 0)
        self.assertTrue(scenario_exists)
        self.assertEqual(report["source"]["mode"], "current_cached_period")

    def test_snap_monster_json_url_uses_fake_fetcher(self) -> None:
        calls: list[str] = []

        def fake_fetch(url: str, _timeout: float) -> str:
            calls.append(url)
            return json.dumps([{"Name": "First Enemy", "Title": "First Enemy"}])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
            mapping_path = _write_enemy_type_map(root / "enemy_types.json")
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--enemy-type-map",
                    str(mapping_path),
                    "--snap-monster-json",
                    DEFAULT_SNAP_MONSTER_GITHUB_URL,
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                snap_fetcher=fake_fetch,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(calls, [DEFAULT_SNAP_MONSTER_RAW_URL])
        self.assertEqual(report["snap_source"]["kind"], SNAP_SOURCE_KIND_REMOTE_URL)

    def test_default_remote_snap_monster_json_uses_fake_fetcher(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps([{"Name": "First Enemy", "Title": "First Enemy"}])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
            mapping_path = _write_enemy_type_map(root / "enemy_types.json")
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--enemy-type-map",
                    str(mapping_path),
                    "--use-default-remote-snap-monster-json",
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                snap_fetcher=fake_fetch,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(report["snap_source"]["kind"], SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL)

    def test_managed_snap_not_read_when_primary_resolves(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote should not be fetched")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
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
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(root / "snap" / "Monster.json"),
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                snap_fetcher=fake_fetch,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(report["success"])
        self.assertNotIn("checking_cached_snap_titles", report["steps"])

    def test_managed_snap_cache_resolves_scenario_without_remote(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise AssertionError("remote should not be fetched")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = _source_data()
            rows = list(data.enemy_rows)
            rows[0] = replace(
                rows[0],
                primary_display_name="Assault Specialist Mek - Pneuma",
                matched_nanoka_display_name="Assault Specialist Mek - Pneuma",
                fandom_enemy_page_url="https://genshin-impact.fandom.com/wiki/Assault_Specialist_Mek_-_Pneuma",
            )
            # Keep this test local to the CLI; source-data details are pinned elsewhere.
            from run_workspace.abyss.source_data import rebuild_abyss_floor_source_data_with_rows

            save_abyss_floor_source_data(
                rebuild_abyss_floor_source_data_with_rows(data, rows),
                cache_dir=root / "cache",
            )
            registry_path = root / "enemies_gen.go"
            registry_path.write_text(
                'package shortcut\nvar MonsterNameToID = map[string]int{\n'
                '\t"assaultspecialistmek": 1,\n'
                '\t"secondenemy": 2,\n'
                "}\n",
                encoding="utf-8",
            )
            snap_cache = root / "snap" / "Monster.json"
            snap_cache.parent.mkdir(parents=True)
            snap_cache.write_text(
                json.dumps(
                    [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
                ),
                encoding="utf-8",
            )
            scenario_path = root / "scenario.json"
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--use-cached-snap-monster-json",
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                snap_fetcher=fake_fetch,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["snap_cache"]["cache_status"], SNAP_CACHE_STATUS_HIT)
        self.assertEqual(report["audit"]["type_mapping_details"][0]["method"], "snap_title_fallback")

    def test_managed_snap_refresh_if_needed_writes_cache_and_resolves(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps(
                [{"Name": "Tenebrous Papilla: Type II", "Title": "Tenebrous Papilla"}]
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = _source_data()
            rows = list(data.enemy_rows)
            rows[0] = replace(
                rows[0],
                primary_display_name="Tenebrous Papilla: Type II",
                matched_nanoka_display_name="Tenebrous Papilla: Type II",
                fandom_enemy_page_url="https://genshin-impact.fandom.com/wiki/Tenebrous_Papilla:_Type_II",
            )
            from run_workspace.abyss.source_data import rebuild_abyss_floor_source_data_with_rows

            save_abyss_floor_source_data(
                rebuild_abyss_floor_source_data_with_rows(data, rows),
                cache_dir=root / "cache",
            )
            registry_path = root / "enemies_gen.go"
            registry_path.write_text(
                'package shortcut\nvar MonsterNameToID = map[string]int{\n'
                '\t"tenebrouspapillatypei": 1,\n'
                '\t"secondenemy": 2,\n'
                "}\n",
                encoding="utf-8",
            )
            snap_cache = root / "snap" / "Monster.json"
            scenario_path = root / "scenario.json"
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--gcsim-enemy-registry-source",
                    str(registry_path),
                    "--refresh-snap-monster-json-if-needed",
                    "--snap-monster-cache-path",
                    str(snap_cache),
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                snap_fetcher=fake_fetch,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())
            cache_written = snap_cache.is_file()

        self.assertEqual(code, 0)
        self.assertTrue(cache_written)
        self.assertEqual(report["snap_cache"]["refresh_status"], SNAP_REFRESH_STATUS_SUCCESS)
        self.assertEqual(report["audit"]["type_mapping_details"][0]["method"], "snap_title_contains_target")
        self.assertIn("rechecking_snap_titles_after_refresh", report["steps"])

    def test_missing_enemy_type_mapping_reports_not_ready_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--scenario-out",
                    str(scenario_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(scenario_path.exists())
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "not_ready")
        self.assertIn(
            "missing_enemy_type_mapping:abyss_enemy_identity_to_gcsim_type",
            report["audit"]["warnings"],
        )

    def test_optional_run_mode_uses_injected_artifact_runner(self) -> None:
        calls: list[dict] = []

        def fake_run(config_text: str, **kwargs) -> GcsimArtifactRunResult:
            calls.append({"config_text": config_text, **kwargs})
            scenario_path = Path(kwargs["gtt_wave_scenario"])
            self.assertTrue(scenario_path.is_file())
            return GcsimArtifactRunResult(
                status="passed",
                success=True,
                gtt_wave_scenario_path=str(scenario_path),
                summary=GcsimResultSummary(
                    schema_version="1",
                    sim_version="fake-sim",
                    dps_mean=123.0,
                    duration_mean=4.5,
                    total_damage_mean=553.5,
                ),
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            config_path = root / "config.txt"
            config_path.write_text("options iteration=1;", encoding="utf-8")
            mapping_path = _write_enemy_type_map(root / "enemy_types.json")
            stdout = StringIO()

            code = main(
                [
                    "--period-start",
                    "2026-05-16",
                    "--cache-dir",
                    str(root / "cache"),
                    "--chamber",
                    "1",
                    "--side",
                    "1",
                    "--enemy-type-map",
                    str(mapping_path),
                    "--run-dir",
                    str(root / "run"),
                    "--config",
                    str(config_path),
                    "--format",
                    "json",
                ],
                artifact_run_func=fake_run,
                stdout=stdout,
            )
            report = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["config_text"], "options iteration=1;")
        self.assertEqual(report["status"], "run_passed")
        self.assertEqual(report["run_result"]["summary"]["sim_version"], "fake-sim")


if __name__ == "__main__":
    unittest.main()
