from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event, Thread
from time import sleep
import unittest
from unittest.mock import patch
from dataclasses import replace

from run_workspace.gcsim.optimizer_runner import (
    GcsimOptimizerRunRequest,
    GcsimOptimizerRunStatus,
    GcsimOptimizerSession,
    GcsimOptimizerSessionStatus,
    GcsimOptimizerStageStatus,
    format_gcsim_optimizer_options,
    run_gcsim_optimizer,
)


class GcsimOptimizerRunnerTest(unittest.TestCase):
    def test_two_stage_run_copies_input_and_parses_final_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _artifact(root)
            run_dir = root / "run"
            source = root / "source.txt"
            source.write_text("options iteration=10;", encoding="utf-8")
            factory = SuccessfulOptimizerFactory()
            statuses: list[GcsimOptimizerSessionStatus] = []

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_path=source,
                    artifact_path=artifact,
                    run_dir=run_dir,
                    optimizer_options={
                        "show_substat_scalars": 0,
                        "fixed_substats_count": 2.0,
                        "total_liquid_substats": 20,
                        "fine_tune": 1,
                        "indiv_liquid_cap": 10,
                    },
                    verbose=True,
                    environment={"GOMAXPROCS": "3"},
                    expected_artifact_sha256=hashlib.sha256(b"fake").hexdigest(),
                    engine_binding_sha256="b" * 64,
                ),
                process_factory=factory,
                on_status=statuses.append,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.status, GcsimOptimizerRunStatus.PASSED)
            self.assertEqual(result.session_status, GcsimOptimizerSessionStatus.PASSED)
            self.assertEqual(result.artifact_source, "explicit")
            self.assertEqual(result.artifact_sha256, hashlib.sha256(b"fake").hexdigest())
            self.assertEqual(result.engine_binding_sha256, "b" * 64)
            self.assertEqual(Path(result.input_config_path).read_text(encoding="utf-8"), "options iteration=10;")
            self.assertEqual(source.read_text(encoding="utf-8"), "options iteration=10;")
            self.assertIn("optimized by fake", Path(result.optimized_config_path).read_text(encoding="utf-8"))
            self.assertEqual(result.summary.dps_mean, 43210.5)
            self.assertEqual(
                result.input_config_sha256,
                hashlib.sha256(result.input_config_bytes).hexdigest(),
            )
            self.assertEqual(
                result.optimized_config_sha256,
                hashlib.sha256(result.optimized_config_bytes).hexdigest(),
            )
            self.assertEqual(
                result.result_json_sha256,
                hashlib.sha256(result.result_json_bytes).hexdigest(),
            )
            self.assertEqual(len(factory.calls), 2)
            optimize_call, simulate_call = factory.calls
            self.assertEqual(
                optimize_call.command[1:],
                (
                    "-substatOptim",
                    "-options",
                    "total_liquid_substats=20;indiv_liquid_cap=10;fixed_substats_count=2;fine_tune=1;show_substat_scalars=0",
                    "-v",
                    "-c",
                    "optimizer-input.txt",
                    "-out",
                    "optimized.txt",
                ),
            )
            self.assertEqual(
                simulate_call.command[1:],
                ("-c", "optimized.txt", "-out", "result.json"),
            )
            self.assertEqual(optimize_call.env["GOMAXPROCS"], "3")
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.PASSED)
            self.assertEqual(result.simulate.status, GcsimOptimizerStageStatus.PASSED)
            self.assertEqual(result.optimize.stdout, "optimizer stdout")
            self.assertEqual(result.simulate.stderr, "simulation stderr")
            self.assertEqual(
                statuses,
                [
                    GcsimOptimizerSessionStatus.PREPARING,
                    GcsimOptimizerSessionStatus.OPTIMIZING,
                    GcsimOptimizerSessionStatus.SIMULATING,
                    GcsimOptimizerSessionStatus.PASSED,
                ],
            )
            payload = result.to_dict()
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["optimize"]["name"], "optimize")

    def test_in_memory_crlf_input_is_preserved_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = "options iteration=10;\r\nactive bennett;\r\n"

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text=config,
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    expected_artifact_sha256=hashlib.sha256(b"fake").hexdigest(),
                ),
                process_factory=SuccessfulOptimizerFactory(),
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.PASSED)
            self.assertEqual(result.input_config_bytes, config.encode("utf-8"))
            self.assertEqual(
                Path(result.input_config_path).read_bytes(),
                config.encode("utf-8"),
            )

    def test_runner_rejects_optimizer_evidence_changed_during_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=10;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    expected_artifact_sha256=hashlib.sha256(b"fake").hexdigest(),
                ),
                process_factory=MutatingEvidenceFactory(),
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.EVIDENCE_CHANGED)
            self.assertIn("changed during execution", result.error)

    def test_optimizer_options_are_canonical_and_strictly_validated(self) -> None:
        self.assertEqual(
            format_gcsim_optimizer_options(
                {
                    "fine_tune": 0,
                    "indiv_liquid_cap": 8,
                    "total_liquid_substats": 15,
                }
            ),
            "total_liquid_substats=15;indiv_liquid_cap=8;fine_tune=0",
        )
        invalid_options = (
            ({"unknown": 1}, "Unknown GCSIM optimizer option"),
            ({"total_liquid_substats": -1}, "non-negative integer"),
            ({"indiv_liquid_cap": 2.5}, "non-negative integer"),
            ({"fixed_substats_count": float("inf")}, "non-negative integer"),
            ({"fine_tune": 2}, "must be 0 or 1"),
            ({"show_substat_scalars": True}, "non-negative integer"),
        )
        for index, (options, expected_error) in enumerate(invalid_options):
            with self.subTest(index=index, options=options):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    result = run_gcsim_optimizer(
                        GcsimOptimizerRunRequest(
                            config_text="options iteration=1;",
                            artifact_path=_artifact(root),
                            run_dir=root / "run",
                            optimizer_options=options,
                        ),
                        process_factory=UnexpectedFactory(),
                    )
                    self.assertEqual(
                        result.status,
                        GcsimOptimizerRunStatus.INVALID_REQUEST,
                    )
                    self.assertIn(expected_error, result.error)
                    self.assertFalse((root / "run").exists())

    def test_request_mappings_are_defensive_immutable_snapshots(self) -> None:
        options = {"fine_tune": 0}
        environment = {"GOMAXPROCS": "2"}
        request = GcsimOptimizerRunRequest(
            config_text="options iteration=1;",
            optimizer_options=options,
            environment=environment,
        )
        options["fine_tune"] = 1
        environment["GOMAXPROCS"] = "99"

        self.assertEqual(request.optimizer_options["fine_tune"], 0)
        self.assertEqual(request.environment["GOMAXPROCS"], "2")
        with self.assertRaises(TypeError):
            request.optimizer_options["fine_tune"] = 1  # type: ignore[index]

    def test_request_freezes_sanitized_environment_before_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _artifact(root)
            factory = SuccessfulOptimizerFactory()
            with patch.dict(
                os.environ,
                {
                    "PATH": "before-request",
                    "GTT_AMBIENT_SECRET": "must-not-leak",
                },
                clear=False,
            ):
                request = GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=artifact,
                    run_dir=root / "run",
                    environment={"GOMAXPROCS": "2", "GTT_EXPLICIT": "kept"},
                )
                os.environ["PATH"] = "after-request"
                os.environ["GTT_LATE_SECRET"] = "must-not-leak"
                result = run_gcsim_optimizer(request, process_factory=factory)

            self.assertTrue(result.success)
            for call in factory.calls:
                self.assertEqual(call.env["PATH"], "before-request")
                self.assertEqual(call.env["GOMAXPROCS"], "2")
                self.assertEqual(call.env["GTT_EXPLICIT"], "kept")
                self.assertNotIn("GTT_AMBIENT_SECRET", call.env)
                self.assertNotIn("GTT_LATE_SECRET", call.env)

    def test_pre_frozen_environment_is_used_exactly_without_ambient_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = SuccessfulOptimizerFactory()
            with patch.dict(os.environ, {"PATH": "ambient-must-not-merge"}, clear=False):
                request = GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    environment={"GOMAXPROCS": "2", "ONLY_EXPLICIT": "yes"},
                    environment_is_frozen=True,
                )
                result = run_gcsim_optimizer(request, process_factory=factory)

            self.assertTrue(result.success)
            self.assertEqual(
                factory.calls[0].env,
                {"GOMAXPROCS": "2", "ONLY_EXPLICIT": "yes"},
            )

    def test_executes_private_verified_snapshot_when_source_changes_late(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "fake-gcsim.exe"
            artifact.write_bytes(b"verified-bytes")
            factory = SourceReplacingFactory(artifact)
            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=artifact,
                    run_dir=root / "run",
                    expected_artifact_sha256=hashlib.sha256(b"verified-bytes").hexdigest(),
                ),
                process_factory=factory,
            )

            self.assertTrue(result.success)
            self.assertEqual(artifact.read_bytes(), b"tampered-after-verification")
            executed = tuple(Path(call.command[0]) for call in factory.calls)
            self.assertEqual(len(set(executed)), 1)
            self.assertNotEqual(executed[0], artifact)
            self.assertEqual(executed[0].read_bytes(), b"verified-bytes")

    def test_overall_timeout_is_shared_across_optimizer_and_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = SlowSuccessfulOptimizerFactory(delay_seconds=0.03)
            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    optimizer_timeout_seconds=1,
                    simulation_timeout_seconds=1,
                    overall_timeout_seconds=0.01,
                ),
                process_factory=factory,
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.SIMULATION_TIMEOUT)
            self.assertEqual(len(factory.calls), 1)
            self.assertEqual(result.simulate.status, GcsimOptimizerStageStatus.TIMEOUT)
            self.assertIn("overall deadline", result.error)

    def test_result_and_stage_invariants_reject_forged_passed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=SuccessfulOptimizerFactory(),
            )

            with self.assertRaises(ValueError):
                replace(result, success=False)
            with self.assertRaises(ValueError):
                replace(result, simulate=None)
            with self.assertRaises(ValueError):
                replace(
                    result.optimize,
                    status=GcsimOptimizerStageStatus.FAILED,
                    error="",
                )

    def test_bound_artifact_hash_mismatch_fails_before_process_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    expected_artifact_sha256="0" * 64,
                    engine_binding_sha256="1" * 64,
                ),
                process_factory=UnexpectedFactory(),
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.status,
                GcsimOptimizerRunStatus.ARTIFACT_IDENTITY_MISMATCH,
            )
            self.assertIn("does not match", result.error)

    def test_optimizer_failure_stops_before_simulation_and_keeps_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = FailedOptimizerFactory()

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=factory,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status, GcsimOptimizerRunStatus.OPTIMIZER_FAILED)
            self.assertEqual(result.optimize.returncode, 7)
            self.assertEqual(result.optimize.stdout, "partial output")
            self.assertEqual(result.optimize.stderr, "invalid optimizer config")
            self.assertIsNone(result.simulate)
            self.assertEqual(len(factory.calls), 1)
            self.assertTrue(Path(result.input_config_path).is_file())

    def test_missing_optimized_config_is_reported_without_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = MissingOutputFactory()

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=factory,
            )

            self.assertEqual(
                result.status,
                GcsimOptimizerRunStatus.OPTIMIZED_CONFIG_MISSING,
            )
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.PASSED)
            self.assertIsNone(result.simulate)
            self.assertEqual(len(factory.calls), 1)

    def test_simulation_result_parse_failure_keeps_both_stage_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = InvalidResultFactory()

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=factory,
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.RESULT_INVALID)
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.PASSED)
            self.assertEqual(result.simulate.status, GcsimOptimizerStageStatus.PASSED)
            self.assertIn("Could not parse GCSIM result JSON", result.error)
            self.assertEqual(len(factory.calls), 2)

    def test_parseable_but_semantically_invalid_result_fails_closed(self) -> None:
        invalid_payloads = (
            {},
            {"statistics": {"iterations": 0, "dps": {"mean": 10}}},
            {"statistics": {"iterations": 10, "dps": {"mean": "NaN"}}},
            {
                "statistics": {
                    "iterations": 10,
                    "dps": {"mean": 10, "sd": -1},
                }
            },
        )
        for index, payload in enumerate(invalid_payloads):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = run_gcsim_optimizer(
                    GcsimOptimizerRunRequest(
                        config_text="options iteration=1;",
                        artifact_path=_artifact(root),
                        run_dir=root / "run",
                    ),
                    process_factory=SemanticInvalidResultFactory(payload),
                )

                self.assertFalse(result.success)
                self.assertEqual(result.status, GcsimOptimizerRunStatus.RESULT_INVALID)
                self.assertNotEqual(result.error, "")

    def test_cancel_terminates_active_optimizer_process_and_skips_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = BlockingFactory()
            session = GcsimOptimizerSession(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    optimizer_timeout_seconds=30,
                ),
                process_factory=factory,
            )
            holder: list = []
            worker = Thread(target=lambda: holder.append(session.run()), daemon=True)

            worker.start()
            self.assertTrue(factory.started.wait(timeout=2))
            session.cancel()
            worker.join(timeout=2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(holder), 1)
            result = holder[0]
            self.assertEqual(result.status, GcsimOptimizerRunStatus.CANCELLED)
            self.assertEqual(result.session_status, GcsimOptimizerSessionStatus.CANCELLED)
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.CANCELLED)
            self.assertIsNone(result.simulate)
            self.assertTrue(factory.process.terminate_called)
            self.assertTrue(session.cancel_requested)

    def test_cancel_at_stage_boundary_never_regresses_back_to_simulating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = SuccessfulOptimizerFactory()
            session_holder: list[GcsimOptimizerSession] = []

            def cancel_before_simulation(status: GcsimOptimizerSessionStatus) -> None:
                if status is GcsimOptimizerSessionStatus.SIMULATING:
                    session_holder[0].cancel()

            session = GcsimOptimizerSession(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=factory,
                on_status=cancel_before_simulation,
            )
            session_holder.append(session)

            result = session.run()

            self.assertEqual(result.status, GcsimOptimizerRunStatus.CANCELLED)
            self.assertEqual(session.status, GcsimOptimizerSessionStatus.CANCELLED)
            self.assertEqual(len(factory.calls), 1)

    def test_cancel_after_terminal_result_does_not_overwrite_session_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = GcsimOptimizerSession(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=SuccessfulOptimizerFactory(),
            )

            result = session.run()
            session.cancel()

            self.assertEqual(result.status, GcsimOptimizerRunStatus.PASSED)
            self.assertEqual(session.status, GcsimOptimizerSessionStatus.PASSED)

    def test_optimizer_timeout_terminates_process_and_is_distinct_from_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = BlockingFactory()

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                    optimizer_timeout_seconds=0.01,
                ),
                process_factory=factory,
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.OPTIMIZER_TIMEOUT)
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.TIMEOUT)
            self.assertTrue(factory.process.terminate_called)
            self.assertFalse(result.success)

    def test_invalid_input_contract_does_not_create_run_directory_or_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = UnexpectedFactory()

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    config_path=root / "also.txt",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=factory,
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.INVALID_REQUEST)
            self.assertFalse((root / "run").exists())

    def test_existing_explicit_run_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            sentinel = run_dir / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=run_dir,
                ),
                process_factory=UnexpectedFactory(),
            )

            self.assertEqual(result.status, GcsimOptimizerRunStatus.RUN_DIR_EXISTS)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_process_start_failure_is_typed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_gcsim_optimizer(
                GcsimOptimizerRunRequest(
                    config_text="options iteration=1;",
                    artifact_path=_artifact(root),
                    run_dir=root / "run",
                ),
                process_factory=StartFailureFactory(),
            )

            self.assertEqual(
                result.status,
                GcsimOptimizerRunStatus.OPTIMIZER_START_FAILED,
            )
            self.assertEqual(result.optimize.status, GcsimOptimizerStageStatus.START_FAILED)
            self.assertIn("cannot execute", result.error)


class FakeProcess:
    def __init__(
        self,
        command,
        cwd: Path,
        env,
        action,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.command = tuple(command)
        self.cwd = cwd
        self.env = dict(env)
        self.action = action
        self.final_returncode = returncode
        self.returncode = None
        self.stdout = stdout
        self.stderr = stderr
        self.terminate_called = False
        self.kill_called = False

    def communicate(self, timeout=None):
        if self.returncode is None:
            self.action(self.command, self.cwd)
            self.returncode = self.final_returncode
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_called = True
        self.returncode = -15

    def kill(self):
        self.kill_called = True
        self.returncode = -9


class SuccessfulOptimizerFactory:
    def __init__(self) -> None:
        self.calls: list[FakeProcess] = []

    def __call__(self, command, cwd, env):
        if "-substatOptim" in command:
            process = FakeProcess(
                command,
                cwd,
                env,
                _write_optimized_config,
                stdout="optimizer stdout",
            )
        else:
            process = FakeProcess(
                command,
                cwd,
                env,
                _write_result,
                stdout="simulation stdout",
                stderr="simulation stderr",
            )
        self.calls.append(process)
        return process


class SourceReplacingFactory(SuccessfulOptimizerFactory):
    def __init__(self, source: Path) -> None:
        super().__init__()
        self.source = source

    def __call__(self, command, cwd, env):
        if not self.calls:
            self.source.write_bytes(b"tampered-after-verification")
        return super().__call__(command, cwd, env)


class MutatingEvidenceFactory(SuccessfulOptimizerFactory):
    def __call__(self, command, cwd, env):
        if "-substatOptim" in command:
            return super().__call__(command, cwd, env)

        def write_result_then_mutate(current_command, current_cwd):
            _write_result(current_command, current_cwd)
            optimized = current_cwd / "optimized.txt"
            optimized.write_bytes(optimized.read_bytes() + b"\n# tampered")

        process = FakeProcess(command, cwd, env, write_result_then_mutate)
        self.calls.append(process)
        return process


class SlowSuccessfulOptimizerFactory(SuccessfulOptimizerFactory):
    def __init__(self, *, delay_seconds: float) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds

    def __call__(self, command, cwd, env):
        if "-substatOptim" in command:
            def delayed_write(current_command, current_cwd):
                sleep(self.delay_seconds)
                _write_optimized_config(current_command, current_cwd)

            process = FakeProcess(command, cwd, env, delayed_write)
            self.calls.append(process)
            return process
        return super().__call__(command, cwd, env)


class FailedOptimizerFactory:
    def __init__(self) -> None:
        self.calls: list[FakeProcess] = []

    def __call__(self, command, cwd, env):
        process = FakeProcess(
            command,
            cwd,
            env,
            _no_output,
            returncode=7,
            stdout="partial output",
            stderr="invalid optimizer config",
        )
        self.calls.append(process)
        return process


class MissingOutputFactory:
    def __init__(self) -> None:
        self.calls: list[FakeProcess] = []

    def __call__(self, command, cwd, env):
        process = FakeProcess(command, cwd, env, _no_output)
        self.calls.append(process)
        return process


class InvalidResultFactory(SuccessfulOptimizerFactory):
    def __call__(self, command, cwd, env):
        if "-substatOptim" in command:
            process = FakeProcess(command, cwd, env, _write_optimized_config)
        else:
            process = FakeProcess(command, cwd, env, _write_invalid_result)
        self.calls.append(process)
        return process


class SemanticInvalidResultFactory(SuccessfulOptimizerFactory):
    def __init__(self, payload) -> None:
        super().__init__()
        self.payload = payload

    def __call__(self, command, cwd, env):
        if "-substatOptim" in command:
            process = FakeProcess(command, cwd, env, _write_optimized_config)
        else:
            process = FakeProcess(
                command,
                cwd,
                env,
                lambda current_command, current_cwd: _write_result_payload(
                    current_command,
                    current_cwd,
                    self.payload,
                ),
            )
        self.calls.append(process)
        return process


class BlockingProcess:
    def __init__(self, command) -> None:
        self.command = tuple(command)
        self.returncode = None
        self.terminate_called = False
        self.kill_called = False

    def communicate(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return "stopped stdout", "stopped stderr"

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_called = True
        self.returncode = -15

    def kill(self):
        self.kill_called = True
        self.returncode = -9


class BlockingFactory:
    def __init__(self) -> None:
        self.started = Event()
        self.process = None

    def __call__(self, command, _cwd, _env):
        self.process = BlockingProcess(command)
        self.started.set()
        return self.process


class UnexpectedFactory:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError("process factory must not be called")


class StartFailureFactory:
    def __call__(self, *_args, **_kwargs):
        raise OSError("cannot execute")


def _artifact(root: Path) -> Path:
    path = root / "fake-gcsim.exe"
    path.write_bytes(b"fake")
    return path


def _write_optimized_config(command, cwd: Path) -> None:
    input_path = cwd / command[list(command).index("-c") + 1]
    output_path = cwd / command[list(command).index("-out") + 1]
    output_path.write_text(
        input_path.read_text(encoding="utf-8") + "\n# optimized by fake",
        encoding="utf-8",
    )


def _write_result(command, cwd: Path) -> None:
    config_path = cwd / command[list(command).index("-c") + 1]
    assert "optimized by fake" in config_path.read_text(encoding="utf-8")
    output_path = cwd / command[list(command).index("-out") + 1]
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sim_version": "fake-two-stage",
                "statistics": {
                    "iterations": 10,
                    "dps": {"mean": 43210.5, "sd": 100.0},
                    "duration": {"mean": 12.0},
                    "total_damage": {"mean": 518526},
                },
            }
        ),
        encoding="utf-8",
    )


def _write_invalid_result(command, cwd: Path) -> None:
    output_path = cwd / command[list(command).index("-out") + 1]
    output_path.write_text("not json", encoding="utf-8")


def _write_result_payload(command, cwd: Path, payload) -> None:
    output_path = cwd / command[list(command).index("-out") + 1]
    output_path.write_text(json.dumps(payload), encoding="utf-8")


def _no_output(_command, _cwd: Path) -> None:
    return None


if __name__ == "__main__":
    unittest.main()
