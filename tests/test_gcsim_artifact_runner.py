from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from run_workspace.gcsim.artifact_runner import (
    GcsimResultParseError,
    parse_gcsim_result_payload,
    run_active_gcsim_artifact,
)
from run_workspace.gcsim.engine_store import GcsimEngineStore


class GcsimArtifactRunnerTest(unittest.TestCase):
    def test_runner_refuses_without_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=root / "store",
                runner=UnexpectedRunner(),
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "no_active_engine")

    def test_runner_refuses_when_manifest_has_no_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_active_engine(root, metadata={})

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=root / "store",
                runner=UnexpectedRunner(),
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "artifact_path_missing")

    def test_runner_refuses_when_active_engine_pointer_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "store"
            store.mkdir(parents=True)
            (store / "active_engine.json").write_text(
                json.dumps({"schema_version": 1, "active_engine_id": "missing-engine"}),
                encoding="utf-8",
            )

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=store,
                runner=UnexpectedRunner(),
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "active_engine_invalid")

    def test_runner_refuses_when_artifact_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_active_engine(
                root,
                metadata={"artifact_relative_path": "build/gtt-gcsim.exe"},
            )

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=root / "store",
                runner=UnexpectedRunner(),
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "artifact_missing")

    def test_successful_fake_artifact_run_writes_config_and_parses_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_active_engine(
                root,
                metadata={"artifact_relative_path": "build/gtt-gcsim.exe"},
                artifact_bytes=b"fake exe",
            )
            runner = FakeArtifactRunner(_write_result_json)

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=root / "store",
                run_dir=root / "run",
                runner=runner,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.status, "passed")
            self.assertEqual(result.returncode, 0)
            self.assertTrue(Path(result.config_path).exists())
            self.assertTrue(Path(result.result_path).exists())
            self.assertEqual(Path(result.config_path).read_text(encoding="utf-8"), "options iteration=1;")
            self.assertIn("-c", result.command)
            self.assertIn("-out", result.command)
            self.assertEqual(result.summary.schema_version, "1")
            self.assertEqual(result.summary.sim_version, "sim-test")
            self.assertEqual(result.summary.dps_mean, 12345.5)
            self.assertEqual(result.summary.duration_mean, 9.25)
            self.assertEqual(result.summary.total_damage_mean, 114000.0)
            self.assertEqual(result.summary.warnings, ("warn one",))
            self.assertEqual(result.summary.failed_actions, ("bad action",))
            self.assertEqual(result.summary.incomplete_characters, ("char_missing",))
            self.assertEqual(len(runner.calls), 1)

    def test_nonzero_artifact_exit_returns_controlled_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_active_engine(
                root,
                metadata={"artifact_relative_path": "build/gtt-gcsim.exe"},
                artifact_bytes=b"fake exe",
            )
            runner = FakeArtifactRunner(
                subprocess.CompletedProcess(
                    args=["gtt-gcsim.exe"],
                    returncode=2,
                    stdout="partial stdout",
                    stderr="config error",
                )
            )

            result = run_active_gcsim_artifact(
                "bad config",
                store_dir=root / "store",
                run_dir=root / "run",
                runner=runner,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "run_failed")
            self.assertEqual(result.returncode, 2)
            self.assertIn("partial stdout", result.stdout)
            self.assertIn("config error", result.stderr)

    def test_timeout_returns_controlled_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_active_engine(
                root,
                metadata={"artifact_relative_path": "build/gtt-gcsim.exe"},
                artifact_bytes=b"fake exe",
            )
            runner = FakeArtifactRunner(
                subprocess.TimeoutExpired(
                    cmd=["gtt-gcsim.exe"],
                    timeout=1,
                    output="late stdout",
                    stderr="late stderr",
                )
            )

            result = run_active_gcsim_artifact(
                "options iteration=1;",
                store_dir=root / "store",
                run_dir=root / "run",
                timeout_seconds=1,
                runner=runner,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, "timeout")
            self.assertIn("late stdout", result.stdout)
            self.assertIn("late stderr", result.stderr)

    def test_parser_tolerates_missing_optional_fields(self) -> None:
        summary = parse_gcsim_result_payload({})

        self.assertEqual(summary.schema_version, "")
        self.assertEqual(summary.sim_version, "")
        self.assertIsNone(summary.dps_mean)
        self.assertIsNone(summary.duration_mean)
        self.assertIsNone(summary.total_damage_mean)
        self.assertEqual(summary.warnings, ())
        self.assertEqual(summary.failed_actions, ())
        self.assertEqual(summary.incomplete_characters, ())

    def test_parser_extracts_camel_case_and_numeric_string_fields(self) -> None:
        summary = parse_gcsim_result_payload(
            {
                "schemaVersion": "2",
                "simVersion": "v-test",
                "statistics": {
                    "dps": {"mean": "10.5"},
                    "duration": {"mean": 3},
                    "totalDamage": {"mean": "31.5"},
                    "failedActions": [{"line": 1}],
                },
                "incompleteCharacters": ["missing_impl"],
            }
        )

        self.assertEqual(summary.schema_version, "2")
        self.assertEqual(summary.sim_version, "v-test")
        self.assertEqual(summary.dps_mean, 10.5)
        self.assertEqual(summary.duration_mean, 3.0)
        self.assertEqual(summary.total_damage_mean, 31.5)
        self.assertEqual(summary.failed_actions, ('{"line": 1}',))
        self.assertEqual(summary.incomplete_characters, ("missing_impl",))

    def test_parser_rejects_non_object_root(self) -> None:
        with self.assertRaises(GcsimResultParseError):
            parse_gcsim_result_payload([])


class FakeArtifactRunner:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, command, cwd, env, timeout):
        self.calls.append(
            {
                "command": tuple(command),
                "cwd": cwd,
                "env": dict(env),
                "timeout": timeout,
            }
        )
        if isinstance(self.result, BaseException):
            raise self.result
        if callable(self.result):
            return self.result(command, cwd, env, timeout)
        return self.result


class UnexpectedRunner:
    def __call__(self, command, cwd, env, timeout):  # pragma: no cover - failure helper.
        raise AssertionError(f"Runner should not be called: {command}")


def _write_result_json(command, cwd: Path, _env, _timeout):
    config_index = list(command).index("-c") + 1
    result_index = list(command).index("-out") + 1
    config_path = cwd / command[config_index]
    assert config_path.read_text(encoding="utf-8") == "options iteration=1;"
    result_path = cwd / command[result_index]
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sim_version": "sim-test",
                "statistics": {
                    "dps": {"mean": 12345.5},
                    "duration": {"mean": 9.25},
                    "total_damage": {"mean": 114000},
                    "warnings": ["warn one"],
                    "failed_actions": ["bad action"],
                },
                "incomplete_characters": ["char_missing"],
            }
        ),
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(
        args=list(command),
        returncode=0,
        stdout="sim ok",
        stderr="",
    )


def _install_active_engine(
    root: Path,
    *,
    metadata: dict[str, str],
    artifact_bytes: bytes | None = None,
) -> None:
    source = root / "source"
    source.mkdir(parents=True)
    (source / "engine.txt").write_text("engine", encoding="utf-8")
    artifact_relative = metadata.get("artifact_relative_path")
    if artifact_relative and artifact_bytes is not None:
        artifact_path = source / artifact_relative
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
    result = GcsimEngineStore(root / "store").prepare_engine_update(
        source_dir=source,
        source_label="engine",
        engine_id="engine-v1",
        metadata=metadata,
    )
    assert result.success


if __name__ == "__main__":
    unittest.main()
