from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
from threading import Event, Lock, Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch

import run_workspace.gcsim.farming_evaluator as farming_evaluator_module

from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationError,
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingEvaluationSession,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
    prepare_bound_gcsim_farming_evaluation,
    prepare_bound_gcsim_farming_joint_evaluation,
)
from run_workspace.gcsim.farming_search import (
    CandidateEvaluation,
    FourPieceSetState,
    SetProfileCandidate,
)
from run_workspace.gcsim.optimizer_cache import GcsimOptimizerCacheStore
from run_workspace.gcsim.optimizer_engine_context import GcsimOptimizerEngineContext


CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add set=\"goldentroupe\" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
options iteration=100 workers=20;
target lvl=100 hp=999999999;
active furina;
"""
COMPARISON_CONTEXT_SHA = "d" * 64


class GcsimFarmingBoundRequestTest(unittest.TestCase):
    def test_request_freezes_config_environment_and_exact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            environment = {"CUSTOM": "original"}

            request = prepare_bound_gcsim_farming_evaluation(
                engine_context=_context(artifact),
                candidate=_candidate("baseline"),
                config_text=CONFIG,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                investment_signature="kqm-20-liquid",
                worker_count=2,
                environment=environment,
                run_dir=root / "run",
            )
            environment["CUSTOM"] = "mutated"

            self.assertIn("options iteration=100 workers=2;", request.config_text)
            self.assertEqual(request.environment["CUSTOM"], "original")
            self.assertEqual(request.environment["GOMAXPROCS"], "2")
            self.assertEqual(request.identity.artifact_sha256, hashlib.sha256(b"engine").hexdigest())
            self.assertEqual(request.identity.engine_binding_sha256, "b" * 64)
            self.assertEqual(request.cache_identity.candidate_key, request.identity.identity_sha256)
            self.assertEqual(request.cache_identity.catalog_fingerprint, "c" * 64)
            with self.assertRaises(TypeError):
                request.environment["CUSTOM"] = "nope"  # type: ignore[index]
            with self.assertRaisesRegex(ValueError, "pinned high-HP"):
                replace(
                    request,
                    config_text=request.config_text.replace(
                        "hp=999999999",
                        "hp=1",
                    ),
                )

            different_workers = prepare_bound_gcsim_farming_evaluation(
                engine_context=_context(artifact),
                candidate=_candidate("baseline"),
                config_text=CONFIG,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                investment_signature="kqm-20-liquid",
                worker_count=1,
            )
            self.assertNotEqual(
                request.identity.identity_sha256,
                different_workers.identity.identity_sha256,
            )

    def test_direct_request_cannot_bypass_config_or_environment_cpu_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(
                artifact,
                root / "run",
                "cpu-binding",
                workers=2,
            )

            with self.assertRaisesRegex(ValueError, "canonical workers=2"):
                replace(
                    request,
                    config_text=request.config_text.replace(
                        "workers=2",
                        "workers=3",
                    ),
                )
            with self.assertRaisesRegex(ValueError, "exactly one canonical"):
                replace(
                    request,
                    config_text=request.config_text.replace(
                        "workers=2",
                        "workers=2 workers=2",
                    ),
                )
            with self.assertRaisesRegex(ValueError, "GOMAXPROCS"):
                replace(request, environment={"GOMAXPROCS": "3"})
            with self.assertRaisesRegex(ValueError, "GOMAXPROCS"):
                replace(
                    request,
                    environment={
                        "GOMAXPROCS": "2",
                        "gomaxprocs": "99",
                    },
                )
            with self.assertRaisesRegex(ValueError, "iteration=99"):
                replace(request, expected_iterations=99)

    def test_bound_builder_is_idempotent_and_normalizes_gomaxprocs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            context = _context(artifact)
            first = prepare_bound_gcsim_farming_evaluation(
                engine_context=context,
                candidate=_candidate("idempotent"),
                config_text=CONFIG,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                investment_signature="same",
                worker_count=2,
                environment={"gomaxprocs": "99", "CUSTOM": "kept"},
            )
            second = prepare_bound_gcsim_farming_evaluation(
                engine_context=context,
                candidate=_candidate("idempotent"),
                config_text=first.config_text,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                investment_signature="same",
                worker_count=2,
                environment=first.environment,
            )

            self.assertEqual(second.config_text, first.config_text)
            self.assertEqual(dict(second.environment), dict(first.environment))
            self.assertEqual(
                tuple(
                    key
                    for key in second.environment
                    if key.casefold() == "gomaxprocs"
                ),
                ("GOMAXPROCS",),
            )

    def test_builder_rejects_untrusted_unmodeled_and_illegal_rarity_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            with self.assertRaisesRegex(GcsimFarmingEvaluationError, "resealed"):
                prepare_bound_gcsim_farming_evaluation(
                    engine_context=_context(artifact, trusted=False),
                    candidate=_candidate("baseline"),
                    config_text=CONFIG,
                    comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                    investment_signature="same",
                )
            with self.assertRaisesRegex(GcsimFarmingEvaluationError, "offpiece"):
                prepare_bound_gcsim_farming_evaluation(
                    engine_context=_context(artifact, rarity=4),
                    candidate=_candidate("baseline"),
                    config_text=CONFIG,
                    comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                    investment_signature="same",
                )
            with self.assertRaisesRegex(GcsimFarmingEvaluationError, "not optimizer-ready"):
                prepare_bound_gcsim_farming_evaluation(
                    engine_context=_context(artifact, modeled=False),
                    candidate=_candidate("baseline"),
                    config_text=CONFIG,
                    comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                    investment_signature="same",
                )


class GcsimFarmingSessionTest(unittest.TestCase):
    def test_ordinary_run_is_isolated_and_parses_uncertainty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "run", "baseline", workers=2)
            factory = SuccessfulProcessFactory(dps=12345.0, iterations=100, sd=250.0)

            result = GcsimFarmingEvaluationSession(
                request,
                process_factory=factory,
            ).run()

            self.assertTrue(result.success)
            self.assertEqual(result.status, GcsimFarmingEvaluationStatus.PASSED)
            self.assertAlmostEqual(result.evaluation.standard_error, 25.0)
            self.assertEqual(result.summary.iterations, 100)
            self.assertEqual(len(factory.calls), 1)
            command, cwd, env = factory.calls[0]
            self.assertEqual(command[1:], ("-c", "config.txt", "-out", "result.json"))
            self.assertEqual(cwd, root / "run")
            self.assertEqual(env["GOMAXPROCS"], "2")
            self.assertEqual(
                (root / "run" / "config.txt").read_text(encoding="utf-8"),
                request.config_text,
            )

    def test_missing_sd_remains_unknown_not_zero_precision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            result = GcsimFarmingEvaluationSession(
                _request(artifact, root / "run", "unknown"),
                process_factory=SuccessfulProcessFactory(
                    dps=9000.0,
                    iterations=100,
                    sd=None,
                ),
            ).run()

            self.assertTrue(result.success)
            self.assertIsNone(result.summary.dps_se)
            self.assertIsNone(result.evaluation.standard_error)

    def test_process_uses_the_environment_frozen_at_bind_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "run", "environment")
            factory = SuccessfulProcessFactory(
                dps=100.0,
                iterations=100,
                sd=1.0,
            )

            with patch.dict(os.environ, {"GTT_ADDED_AFTER_BIND": "late"}):
                result = GcsimFarmingEvaluationSession(
                    request,
                    process_factory=factory,
                ).run()

            self.assertTrue(result.success)
            self.assertNotIn("GTT_ADDED_AFTER_BIND", factory.calls[0][2])

    def test_ambient_secrets_are_not_forwarded_or_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            with patch.dict(os.environ, {"GTT_FAKE_SECRET_TOKEN": "do-not-copy"}):
                request = _request(artifact, root / "run", "environment-secret")

            self.assertNotIn("GTT_FAKE_SECRET_TOKEN", request.environment)
            self.assertNotIn("do-not-copy", repr(request))

    def test_wrong_iteration_count_and_incomplete_character_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")

            wrong_iterations = GcsimFarmingEvaluationSession(
                _request(artifact, root / "wrong-iterations", "wrong-iterations"),
                process_factory=SuccessfulProcessFactory(
                    dps=100.0,
                    iterations=10,
                    sd=1.0,
                ),
            ).run()
            incomplete = GcsimFarmingEvaluationSession(
                _request(artifact, root / "incomplete", "incomplete"),
                process_factory=SuccessfulProcessFactory(
                    dps=100.0,
                    iterations=100,
                    sd=1.0,
                    incomplete_characters=("missing_impl",),
                ),
            ).run()

            self.assertEqual(
                wrong_iterations.status,
                GcsimFarmingEvaluationStatus.RESULT_INVALID,
            )
            self.assertIn("expected 100, observed 10", wrong_iterations.error)
            self.assertEqual(
                incomplete.status,
                GcsimFarmingEvaluationStatus.RESULT_INVALID,
            )
            self.assertIn("missing_impl", incomplete.error)

    def test_artifact_mutation_fails_before_process_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "run", "baseline")
            artifact.write_bytes(b"mutated")
            factory = UnexpectedProcessFactory()

            result = GcsimFarmingEvaluationSession(
                request,
                process_factory=factory,
            ).run()

            self.assertEqual(
                result.status,
                GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH,
            )
            self.assertEqual(factory.calls, 0)
            self.assertFalse((root / "run").exists())

    def test_cancel_terminates_only_active_process_and_returns_typed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            process = BlockingProcess()
            session = GcsimFarmingEvaluationSession(
                _request(artifact, root / "run", "baseline", timeout=10.0),
                process_factory=lambda *_args: process,
            )
            holder: list[GcsimFarmingEvaluationResult] = []
            thread = Thread(target=lambda: holder.append(session.run()))
            thread.start()
            self.assertTrue(process.started.wait(1.0))

            session.cancel()
            thread.join(2.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(holder[0].status, GcsimFarmingEvaluationStatus.CANCELLED)
            self.assertTrue(process.terminated)

    def test_per_candidate_timeout_terminates_process_and_ignores_partial_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            process = BlockingProcess()

            result = GcsimFarmingEvaluationSession(
                _request(artifact, root / "run", "timeout", timeout=0.04),
                process_factory=lambda *_args: process,
            ).run()

            self.assertEqual(result.status, GcsimFarmingEvaluationStatus.TIMEOUT)
            self.assertIsNone(result.evaluation)
            self.assertTrue(process.terminated)

    def test_successful_process_completion_wins_over_later_cancel_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            factory = CompletionWinsProcessFactory()
            session = GcsimFarmingEvaluationSession(
                _request(artifact, root / "run", "completion-wins"),
                process_factory=factory,
            )
            holder: list[GcsimFarmingEvaluationResult] = []
            thread = Thread(target=lambda: holder.append(session.run()))
            thread.start()
            self.assertTrue(factory.created.wait(1.0))
            process = factory.process
            self.assertIsNotNone(process)
            self.assertTrue(process.completed.wait(1.0))

            session.cancel()
            process.release.set()
            thread.join(1.0)

            self.assertFalse(thread.is_alive())
            self.assertTrue(session.cancel_requested)
            self.assertFalse(process.terminated)
            self.assertEqual(holder[0].status, GcsimFarmingEvaluationStatus.PASSED)
            self.assertEqual(holder[0].summary.dps_mean, 54321.0)


class GcsimFarmingSchedulerTest(unittest.TestCase):
    def test_scheduler_rejects_mixed_comparison_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            first = _request(artifact, root / "a", "a")
            second = _request(artifact, root / "b", "b")

            with self.assertRaisesRegex(ValueError, "one comparison context"):
                GcsimFarmingEvaluationScheduler(
                    (first, replace(second, comparison_context_sha256="e" * 64)),
                    GcsimFarmingSchedulerBudget(2, 2, 1.0),
                    enable_cache=False,
                )
            with self.assertRaisesRegex(ValueError, "one comparison context"):
                GcsimFarmingEvaluationScheduler(
                    (first, replace(second, investment_signature="other-envelope")),
                    GcsimFarmingSchedulerBudget(2, 2, 1.0),
                    enable_cache=False,
                )
            with self.assertRaisesRegex(ValueError, "one comparison context"):
                GcsimFarmingEvaluationScheduler(
                    (
                        first,
                        replace(
                            second,
                            config_text=second.config_text.replace(
                                "target lvl=100",
                                "target lvl=99",
                            ),
                        ),
                    ),
                    GcsimFarmingSchedulerBudget(2, 2, 1.0),
                    enable_cache=False,
                )

    def test_default_batch_hashes_one_shared_artifact_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine" * 1024)
            requests = tuple(
                _request(artifact, root / f"run-{key}", key)
                for key in ("a", "b", "c")
            )
            observed_witnesses = []

            class PreverifiedSession(ImmediateSession):
                def __init__(self, request, *, _verified_artifact=None):
                    observed_witnesses.append(_verified_artifact)
                    super().__init__(request, dps=100.0, sd=1.0)

            with patch.object(
                farming_evaluator_module,
                "_snapshot_artifact_until",
                wraps=farming_evaluator_module._snapshot_artifact_until,
            ) as hasher, patch.object(
                farming_evaluator_module,
                "GcsimFarmingEvaluationSession",
                PreverifiedSession,
            ):
                result = GcsimFarmingEvaluationScheduler(
                    requests,
                    GcsimFarmingSchedulerBudget(3, 3, 1.0),
                    enable_cache=False,
                ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.COMPLETED)
            self.assertEqual(hasher.call_count, 1)
            self.assertEqual(len(observed_witnesses), 3)
            self.assertTrue(all(item is not None for item in observed_witnesses))
            with self.assertRaisesRegex(ValueError, "GcsimFarmingBatchStatus"):
                replace(result, status="cancelled")
            with self.assertRaisesRegex(ValueError, "counters"):
                replace(result, successful_count=0)

    def test_default_batch_executes_verified_snapshot_after_source_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            original_bytes = b"bound-engine-content"
            artifact.write_bytes(original_bytes)
            request = _request(artifact, root / "run", "a")
            process_factory = SuccessfulProcessFactory(
                dps=100.0,
                iterations=100,
                sd=1.0,
            )
            executed_bytes: list[bytes] = []

            def inspecting_process_factory(command, cwd, env):
                executed_bytes.append(Path(command[0]).read_bytes())
                return process_factory(command, cwd, env)

            real_session = farming_evaluator_module.GcsimFarmingEvaluationSession

            class SourceReplacingSession(real_session):
                def __init__(self, item, *, _verified_artifact=None):
                    artifact.write_bytes(b"changed-after-batch-snapshot")
                    super().__init__(
                        item,
                        process_factory=inspecting_process_factory,
                        _verified_artifact=_verified_artifact,
                    )

            with patch.object(
                farming_evaluator_module,
                "GcsimFarmingEvaluationSession",
                SourceReplacingSession,
            ):
                result = GcsimFarmingEvaluationScheduler(
                    (request,),
                    GcsimFarmingSchedulerBudget(1, 1, 1.0),
                    enable_cache=False,
                ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.COMPLETED)
            command = process_factory.calls[0][0]
            self.assertNotEqual(Path(command[0]), artifact)
            self.assertEqual(executed_bytes, [original_bytes])
            self.assertEqual(artifact.read_bytes(), b"changed-after-batch-snapshot")

    def test_joint_team_scope_is_ranked_and_cached_without_fake_single_wearer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            keys = (
                (
                    "furina",
                    "goldentroupe",
                    "layout/hp-hydro-crit",
                    "",
                    "profile/hp",
                ),
                (
                    "bennett",
                    "goldentroupe",
                    "layout/er-pyro-crit",
                    "",
                    "profile/er",
                ),
            )
            request = prepare_bound_gcsim_farming_joint_evaluation(
                engine_context=_context(artifact),
                candidate_keys=keys,
                config_text=CONFIG,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA,
                investment_signature="same-investment",
                worker_count=1,
                run_dir=root / "joint-one",
            )
            store = GcsimOptimizerCacheStore(root / "cache")
            budget = GcsimFarmingSchedulerBudget(1, 1, 1.0)
            process_factory = SuccessfulProcessFactory(
                dps=50000.0,
                iterations=100,
                sd=100.0,
            )

            first = GcsimFarmingEvaluationScheduler(
                (request,),
                budget,
                cache_store=store,
                session_factory=lambda item: GcsimFarmingEvaluationSession(
                    item,
                    process_factory=process_factory,
                ),
            ).run()
            cached_request = _copy_request(request, run_dir=root / "joint-two")
            second = GcsimFarmingEvaluationScheduler(
                (cached_request,),
                budget,
                cache_store=store,
                session_factory=UnexpectedSessionFactory(),
            ).run()

            self.assertEqual(request.candidate_keys, keys)
            self.assertIsNone(request.candidate)
            self.assertTrue(first.best_found)
            self.assertIsNone(first.best_evaluation)
            self.assertEqual(first.best_result.summary.dps_mean, 50000.0)
            self.assertEqual(second.cache_hit_count, 1)
            self.assertEqual(second.best_result.candidate_keys, keys)
            self.assertIsNone(second.best_result.evaluation)

    def test_scheduler_bounds_process_count_and_sum_of_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            requests = (
                _request(artifact, root / "a", "a", workers=2),
                _request(artifact, root / "b", "b", workers=2),
                _request(artifact, root / "c", "c", workers=1),
                _request(artifact, root / "d", "d", workers=1),
            )
            tracker = ConcurrencyTracker()

            result = GcsimFarmingEvaluationScheduler(
                requests,
                GcsimFarmingSchedulerBudget(
                    max_parallel_candidates=3,
                    total_cpu_budget=3,
                    overall_deadline_seconds=2.0,
                ),
                enable_cache=False,
                session_factory=lambda request: TimedSession(request, tracker),
            ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.COMPLETED)
            self.assertEqual(result.successful_count, 4)
            self.assertLessEqual(tracker.max_processes, 3)
            self.assertLessEqual(tracker.max_cpu, 3)
            self.assertGreaterEqual(tracker.max_processes, 2)

    def test_cache_round_trip_skips_second_process_and_preserves_unknown_sd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "run-one", "baseline")
            store = GcsimOptimizerCacheStore(root / "cache")
            budget = GcsimFarmingSchedulerBudget(1, 1, 2.0)

            first = GcsimFarmingEvaluationScheduler(
                (request,),
                budget,
                cache_store=store,
                session_factory=lambda item: ImmediateSession(item, dps=777.0, sd=None),
            ).run()
            second_request = _copy_request(request, run_dir=root / "run-two")
            second = GcsimFarmingEvaluationScheduler(
                (second_request,),
                budget,
                cache_store=store,
                session_factory=UnexpectedSessionFactory(),
            ).run()

            self.assertEqual(first.cache_hit_count, 0)
            self.assertEqual(second.cache_hit_count, 1)
            self.assertEqual(second.results[0].status, GcsimFarmingEvaluationStatus.CACHED)
            self.assertEqual(second.best_evaluation.expected_dps, 777.0)
            self.assertIsNone(second.best_evaluation.standard_error)

    def test_hard_deadline_cancels_active_work_and_returns_cached_best_so_far(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            cached_request = _request(artifact, root / "cached", "cached")
            slow_request = _request(artifact, root / "slow", "slow")
            pending_request = _request(artifact, root / "pending", "pending")
            store = GcsimOptimizerCacheStore(root / "cache")
            seed = GcsimFarmingEvaluationScheduler(
                (cached_request,),
                GcsimFarmingSchedulerBudget(1, 1, 1.0),
                cache_store=store,
                session_factory=lambda item: ImmediateSession(item, dps=999.0, sd=10.0),
            ).run()
            self.assertTrue(seed.best_found)
            controls: list[DeadlineSession] = []

            def session_factory(request: GcsimFarmingEvaluationRequest) -> DeadlineSession:
                session = DeadlineSession(request)
                controls.append(session)
                return session

            started = monotonic()
            result = GcsimFarmingEvaluationScheduler(
                (
                    _copy_request(cached_request, run_dir=root / "cached-two"),
                    slow_request,
                    pending_request,
                ),
                GcsimFarmingSchedulerBudget(
                    max_parallel_candidates=1,
                    total_cpu_budget=1,
                    overall_deadline_seconds=0.08,
                ),
                cache_store=store,
                session_factory=session_factory,
            ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.DEADLINE_REACHED)
            self.assertLess(monotonic() - started, 1.0)
            self.assertTrue(result.best_found)
            self.assertEqual(result.best_evaluation.expected_dps, 999.0)
            self.assertEqual(result.cache_hit_count, 1)
            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.results[1].status, GcsimFarmingEvaluationStatus.CANCELLED)
            self.assertEqual(result.results[2].status, GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE)
            self.assertTrue(controls[0].cancelled.is_set())

    def test_slow_cache_put_cannot_turn_expired_deadline_into_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "slow-cache", "slow-cache")
            store = SlowCacheStore(delay_seconds=0.12)

            started = monotonic()
            result = GcsimFarmingEvaluationScheduler(
                (request,),
                GcsimFarmingSchedulerBudget(1, 1, 0.03),
                cache_store=store,
                session_factory=lambda item: ImmediateSession(
                    item,
                    dps=123.0,
                    sd=1.0,
                ),
            ).run()
            elapsed = monotonic() - started

            self.assertEqual(result.status, GcsimFarmingBatchStatus.DEADLINE_REACHED)
            self.assertTrue(result.best_found)
            self.assertLess(elapsed, 0.10)

    def test_external_scheduler_cancel_stops_queue_and_returns_typed_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            controls: list[DeadlineSession] = []
            created = Event()

            def session_factory(request: GcsimFarmingEvaluationRequest) -> DeadlineSession:
                session = DeadlineSession(request)
                controls.append(session)
                created.set()
                return session

            scheduler = GcsimFarmingEvaluationScheduler(
                (
                    _request(artifact, root / "slow", "slow"),
                    _request(artifact, root / "pending", "pending"),
                ),
                GcsimFarmingSchedulerBudget(1, 1, 5.0),
                enable_cache=False,
                session_factory=session_factory,
            )
            holder = []
            thread = Thread(target=lambda: holder.append(scheduler.run()))
            thread.start()
            self.assertTrue(created.wait(1.0))

            scheduler.cancel()
            thread.join(1.0)

            self.assertFalse(thread.is_alive())
            result = holder[0]
            self.assertEqual(result.status, GcsimFarmingBatchStatus.CANCELLED)
            self.assertFalse(result.best_found)
            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.results[0].status, GcsimFarmingEvaluationStatus.CANCELLED)
            self.assertEqual(
                result.results[1].status,
                GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
            )
            self.assertTrue(controls[0].cancelled.is_set())

    def test_duplicate_candidate_or_oversubscribed_request_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "a", "same", workers=2)
            duplicate = _copy_request(request, run_dir=root / "b")
            with self.assertRaisesRegex(ValueError, "identities"):
                GcsimFarmingEvaluationScheduler(
                    (request, duplicate),
                    GcsimFarmingSchedulerBudget(2, 2, 1.0),
                    enable_cache=False,
                )
            with self.assertRaisesRegex(ValueError, "total_cpu_budget"):
                GcsimFarmingEvaluationScheduler(
                    (request,),
                    GcsimFarmingSchedulerBudget(1, 1, 1.0),
                    enable_cache=False,
                )
            with self.assertRaisesRegex(ValueError, "logical CPUs"):
                GcsimFarmingSchedulerBudget(1, 10**6, 1.0)

    def test_session_result_with_wrong_provenance_is_not_ranked_or_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "right", "right")
            wrong = _request(artifact, root / "wrong", "wrong")
            store = GcsimOptimizerCacheStore(root / "cache")

            result = GcsimFarmingEvaluationScheduler(
                (request,),
                GcsimFarmingSchedulerBudget(1, 1, 1.0),
                cache_store=store,
                session_factory=lambda _item: ImmediateSession(
                    wrong,
                    dps=999999.0,
                    sd=1.0,
                ),
            ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS)
            self.assertFalse(result.best_found)
            self.assertEqual(
                result.results[0].status,
                GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
            )
            self.assertIsNone(store.get(request.cache_identity))

    def test_single_candidate_success_requires_coherent_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            request = _request(artifact, root / "missing-evaluation", "coherent")

            class MissingEvaluationSession(ImmediateSession):
                def run(self):
                    return replace(super().run(), evaluation=None)

            result = GcsimFarmingEvaluationScheduler(
                (request,),
                GcsimFarmingSchedulerBudget(1, 1, 1.0),
                enable_cache=False,
                session_factory=lambda item: MissingEvaluationSession(
                    item,
                    dps=123.0,
                    sd=1.0,
                ),
            ).run()

            self.assertEqual(result.status, GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS)
            self.assertFalse(result.best_found)
            self.assertEqual(
                result.results[0].status,
                GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
            )

            coherent = _passed_result(request, 123.0, sd=1.0)
            mismatched = CandidateEvaluation(
                candidate=request.candidate,
                expected_dps=999.0,
                investment_signature=request.investment_signature,
                standard_error=99.0,
            )
            with self.assertRaisesRegex(ValueError, "exactly match"):
                replace(coherent, evaluation=mismatched)
            with self.assertRaisesRegex(ValueError, "comparison_context_sha256"):
                replace(coherent, comparison_context_sha256="not-a-digest")


class SuccessfulProcessFactory:
    def __init__(
        self,
        *,
        dps: float,
        iterations: int,
        sd: float | None,
        incomplete_characters: tuple[str, ...] = (),
    ) -> None:
        self.dps = dps
        self.iterations = iterations
        self.sd = sd
        self.incomplete_characters = incomplete_characters
        self.calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def __call__(self, command, cwd, env):
        self.calls.append((tuple(command), cwd, dict(env)))
        payload = {
            "schema_version": "1",
            "sim_version": "fixture",
            **(
                {"incompleteCharacters": list(self.incomplete_characters)}
                if self.incomplete_characters
                else {}
            ),
            "statistics": {
                "iterations": self.iterations,
                "dps": {
                    "mean": self.dps,
                    **({} if self.sd is None else {"sd": self.sd}),
                },
            },
        }
        return SuccessfulProcess(cwd / "result.json", payload)


class SuccessfulProcess:
    def __init__(self, result_path: Path, payload: dict) -> None:
        self.result_path = result_path
        self.payload = payload
        self.returncode = 0

    def communicate(self, timeout=None):
        self.result_path.write_text(json.dumps(self.payload), encoding="utf-8")
        return "ordinary stdout", "ordinary stderr"

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class CompletionWinsProcessFactory:
    def __init__(self) -> None:
        self.created = Event()
        self.process: CompletionWinsProcess | None = None

    def __call__(self, _command, cwd, _env):
        self.process = CompletionWinsProcess(cwd / "result.json")
        self.created.set()
        return self.process


class CompletionWinsProcess:
    def __init__(self, result_path: Path) -> None:
        self.result_path = result_path
        self.completed = Event()
        self.release = Event()
        self.terminated = False
        self.returncode = None

    def communicate(self, timeout=None):
        if self.returncode is None:
            payload = {
                "schema_version": "1",
                "sim_version": "fixture",
                "statistics": {
                    "iterations": 100,
                    "dps": {"mean": 54321.0, "sd": 100.0},
                },
            }
            self.result_path.write_text(json.dumps(payload), encoding="utf-8")
            # Process completion is observable through poll() before the test
            # issues cancellation, while communicate() is deliberately held.
            self.returncode = 0
            self.completed.set()
            if not self.release.wait(1.0):
                raise AssertionError("completion race test was not released")
        return "completed", ""

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self.release.set()

    def kill(self):
        self.terminated = True
        self.returncode = -9
        self.release.set()


class BlockingProcess:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()
        self.terminated = False
        self.returncode = None

    def communicate(self, timeout=None):
        self.started.set()
        if not self.stopped.wait(timeout):
            raise subprocess.TimeoutExpired(("fake",), timeout)
        return "", ""

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self.stopped.set()

    def kill(self):
        self.returncode = -9
        self.stopped.set()


class UnexpectedProcessFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args):
        self.calls += 1
        raise AssertionError("process must not start")


class ConcurrencyTracker:
    def __init__(self) -> None:
        self.lock = Lock()
        self.processes = 0
        self.cpu = 0
        self.max_processes = 0
        self.max_cpu = 0

    def enter(self, workers: int) -> None:
        with self.lock:
            self.processes += 1
            self.cpu += workers
            self.max_processes = max(self.max_processes, self.processes)
            self.max_cpu = max(self.max_cpu, self.cpu)

    def leave(self, workers: int) -> None:
        with self.lock:
            self.processes -= 1
            self.cpu -= workers


class TimedSession:
    def __init__(self, request: GcsimFarmingEvaluationRequest, tracker: ConcurrencyTracker) -> None:
        self.request = request
        self.tracker = tracker
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self) -> GcsimFarmingEvaluationResult:
        self.tracker.enter(self.request.worker_count)
        try:
            sleep(0.04)
            return _passed_result(self.request, 100.0 + self.request.worker_count, sd=5.0)
        finally:
            self.tracker.leave(self.request.worker_count)


class ImmediateSession:
    def __init__(self, request: GcsimFarmingEvaluationRequest, *, dps: float, sd: float | None) -> None:
        self.request = request
        self.dps = dps
        self.sd = sd

    def cancel(self) -> None:
        pass

    def run(self) -> GcsimFarmingEvaluationResult:
        return _passed_result(self.request, self.dps, sd=self.sd)


class DeadlineSession:
    def __init__(self, request: GcsimFarmingEvaluationRequest) -> None:
        self.request = request
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self) -> GcsimFarmingEvaluationResult:
        self.cancelled.wait(2.0)
        return _failed_result(
            self.request,
            GcsimFarmingEvaluationStatus.CANCELLED,
            "cancelled by scheduler",
        )


class UnexpectedSessionFactory:
    def __call__(self, _request):
        raise AssertionError("cached candidate must not create a session")


class SlowCacheStore:
    def __init__(self, *, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def get(self, _identity):
        return None

    def put(self, _identity, _result):
        sleep(self.delay_seconds)


def _passed_result(
    request: GcsimFarmingEvaluationRequest,
    dps: float,
    *,
    sd: float | None,
) -> GcsimFarmingEvaluationResult:
    iterations = request.expected_iterations
    se = None if sd is None else sd / math.sqrt(iterations)
    summary = GcsimResultSummary(
        schema_version="1",
        sim_version="fixture",
        iterations=iterations,
        dps_mean=dps,
        dps_sd=sd,
        dps_se=se,
    )
    evaluation = (
        None
        if request.candidate is None
        else CandidateEvaluation(
            candidate=request.candidate,
            expected_dps=dps,
            investment_signature=request.investment_signature,
            standard_error=se,
            novelty_score=request.novelty_score,
            novelty_tags=request.novelty_tags,
        )
    )
    return GcsimFarmingEvaluationResult(
        status=GcsimFarmingEvaluationStatus.PASSED,
        success=True,
        request_identity_sha256=request.identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        evaluation=evaluation,
        summary=summary,
        engine_binding_sha256=request.engine_binding_sha256,
        artifact_sha256=request.artifact_sha256,
        source_config_sha256=request.identity.source_config_sha256,
    )


def _failed_result(
    request: GcsimFarmingEvaluationRequest,
    status: GcsimFarmingEvaluationStatus,
    error: str,
) -> GcsimFarmingEvaluationResult:
    return GcsimFarmingEvaluationResult(
        status=status,
        success=False,
        request_identity_sha256=request.identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        engine_binding_sha256=request.engine_binding_sha256,
        artifact_sha256=request.artifact_sha256,
        source_config_sha256=request.identity.source_config_sha256,
        error=error,
    )


def _request(
    artifact: Path,
    run_dir: Path,
    profile: str,
    *,
    workers: int = 1,
    timeout: float = 1.0,
) -> GcsimFarmingEvaluationRequest:
    config = CONFIG + f"# profile={profile}\n"
    return prepare_bound_gcsim_farming_evaluation(
        engine_context=_context(artifact),
        candidate=_candidate(profile),
        config_text=config,
        comparison_context_sha256=COMPARISON_CONTEXT_SHA,
        investment_signature="same-investment",
        worker_count=workers,
        timeout_seconds=timeout,
        run_dir=run_dir,
    )


def _copy_request(
    request: GcsimFarmingEvaluationRequest,
    *,
    run_dir: Path,
) -> GcsimFarmingEvaluationRequest:
    return GcsimFarmingEvaluationRequest(
        candidate=request.candidate,
        config_text=request.config_text,
        comparison_context_sha256=request.comparison_context_sha256,
        investment_signature=request.investment_signature,
        engine_id=request.engine_id,
        engine_version=request.engine_version,
        artifact_path=request.artifact_path,
        artifact_sha256=request.artifact_sha256,
        engine_binding_sha256=request.engine_binding_sha256,
        catalog_fingerprint=request.catalog_fingerprint,
        worker_count=request.worker_count,
        expected_iterations=request.expected_iterations,
        timeout_seconds=request.timeout_seconds,
        environment=request.environment,
        run_dir=str(run_dir),
        novelty_score=request.novelty_score,
        novelty_tags=request.novelty_tags,
        joint_candidate_keys=request.candidate_keys,
    )


def _candidate(profile: str) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id="furina",
            set_key="goldentroupe",
            main_stat_layout_id="layout/default",
        ),
        profile_id=f"profile/{profile}",
    )


def _context(
    artifact: Path,
    *,
    trusted: bool = True,
    rarity: int = 5,
    modeled: bool = True,
) -> GcsimOptimizerEngineContext:
    capability = GcsimArtifactSetCapability(
        key="goldentroupe",
        package_name="goldentroupe",
        key_constant="GoldenTroupe",
        max_rarity=rarity,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=modeled,
        four_piece_modeled=modeled,
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=(capability,),
    )
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(artifact.parent),
        engine_version="fixture-version",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_path=str(artifact),
        artifact_sha256=artifact_sha,
        engine_tree_sha256="e" * 64,
        catalog=catalog,
        manifest_artifact_sha256=artifact_sha,
        manifest_engine_tree_sha256="e" * 64,
        binding_sha256="b" * 64,
        trusted=trusted,
        issues=() if trusted else ("drift",),
    )


if __name__ == "__main__":
    unittest.main()
