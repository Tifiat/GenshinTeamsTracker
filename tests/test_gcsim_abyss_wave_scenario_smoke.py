from __future__ import annotations

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
from tests.test_gcsim_abyss_wave_scenario import _source_data


class GcsimAbyssWaveScenarioSmokeTest(unittest.TestCase):
    def test_explicit_period_cache_path_writes_schema_v1_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = _source_data()
            save_abyss_floor_source_data(data, cache_dir=root / "cache")
            scenario_path = root / "scenario.json"
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
                    "--radius",
                    "1.2",
                    "--resist",
                    "0.1",
                    "--position",
                    "0,0",
                    "--position",
                    "3,0",
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
                    "--radius",
                    "1.2",
                    "--resist",
                    "0.1",
                    "--position",
                    "0,0",
                    "--position",
                    "3,0",
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

    def test_missing_fixture_policy_reports_not_ready_without_writing(self) -> None:
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
            "missing_fixture_policy:radius_pos_resist",
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
                    "--radius",
                    "1.2",
                    "--resist",
                    "0.1",
                    "--position",
                    "0,0",
                    "--position",
                    "3,0",
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
