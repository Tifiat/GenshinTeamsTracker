from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from threading import Event, Thread
import tempfile
from time import monotonic, sleep
import unittest

from run_workspace.gcsim.artifact_runner import parse_gcsim_result_file
from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_finalist_optimizer import (
    GcsimFinalistAttemptStatus,
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerError,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerSession,
    GcsimFinalistOptimizerStatus,
    run_gcsim_finalist_optimizer,
)
from run_workspace.gcsim.farming_profile_config import GCSIM_SUBSTAT_ROLL_VALUES
from run_workspace.gcsim.farming_search import FourPieceSetState
from run_workspace.gcsim.farming_team_search import FullTeamPhysicalState
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_engine_context import GcsimOptimizerEngineContext
from run_workspace.gcsim.optimizer_runner import (
    DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME,
    DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME,
    DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME,
    GcsimOptimizerRunRequest,
    GcsimOptimizerRunResult,
    GcsimOptimizerRunStatus,
    GcsimOptimizerSessionStatus,
    GcsimOptimizerStageDiagnostic,
    GcsimOptimizerStageName,
    GcsimOptimizerStageStatus,
)


CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="splendoroftranquilwaters" refine=1 lvl=90/90;
furina add set="gladiatorsfinale" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
options swap_delay=12 iteration=10 workers=16;
target lvl=100 hp=999999999;
active furina;
"""


class GcsimFinalistOptimizerTest(unittest.TestCase):
    def test_race_pins_validation_iterations_and_returns_ranked_full_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(
                root,
                finalists=(
                    _state("gladiatorsfinale"),
                    _state("goldentroupe"),
                ),
                budget=_budget(max_finalists=2, top_n=1),
            )
            factory = EvidenceSessionFactory(
                root / "runs",
                dps_by_set={
                    "gladiatorsfinale": 1000.0,
                    "goldentroupe": 1250.0,
                },
            )

            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=factory,
            )

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.BEST_FOUND)
            self.assertEqual(result.attempted_count, 2)
            self.assertEqual(result.successful_count, 2)
            self.assertEqual(len(result.outcomes), 1)
            self.assertEqual(
                result.best_found.state.choices[0].set_key,
                "goldentroupe",
            )
            self.assertEqual(result.best_found.dps_mean, 1250.0)
            self.assertEqual(result.best_found.iterations, 200)
            self.assertIn(
                'furina add set="goldentroupe" count=4;',
                result.best_found.optimized_config_text,
            )
            self.assertEqual(
                tuple(item.wearer_id for item in result.best_found.allocations),
                ("furina",),
            )
            self.assertEqual(
                len(result.best_found.allocations[0].add_stats_lines),
                2,
            )
            self.assertNotEqual(
                result.source_config_sha256,
                result.validation_config_sha256,
            )
            for value in (
                result.request_sha256,
                result.source_config_sha256,
                result.validation_config_sha256,
                result.layout_catalog_sha256,
                result.finalist_domain_sha256,
                result.budget_sha256,
                result.best_found.optimizer_input_sha256,
                result.best_found.optimized_config_sha256,
                result.best_found.result_json_sha256,
                result.best_found.allocation_sha256,
            ):
                self.assertRegex(value, r"^[0-9a-f]{64}$")
            self.assertEqual(len(factory.requests), 2)
            self.assertTrue(
                all(
                    "iteration=200 workers=1" in str(item.config_text)
                    for item in factory.requests
                )
            )
            self.assertTrue(
                all(item.environment["GOMAXPROCS"] == "1" for item in factory.requests)
            )
            self.assertTrue(
                all(
                    item.overall_timeout_seconds is not None
                    and 0 < item.overall_timeout_seconds <= 30
                    for item in factory.requests
                )
            )
            self.assertIn("iteration=10 workers=16", request.prepared_config_text)
            with self.assertRaises(TypeError):
                request.layout_catalog["furina"]["new"] = _layout()  # type: ignore[index]

    def test_request_rejects_wave_bad_layout_offpiece_order_and_unbounded_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = (
                (
                    "wave directive",
                    dict(config=CONFIG + "# gtt_wave duplicate_first_target=1\n"),
                ),
                (
                    "pinned high-HP dummy",
                    dict(config=CONFIG.replace("hp=999999999", "hp=1")),
                ),
                (
                    "unknown wearer/layout",
                    dict(finalists=(_state("goldentroupe", layout_id="missing"),)),
                ),
                (
                    "must not carry",
                    dict(finalists=(_state("goldentroupe", offpiece="sands"),)),
                ),
                (
                    "requires one explicit",
                    dict(finalists=(_state("instructor"),)),
                ),
                (
                    "exact canonical order",
                    dict(finalists=(_state("goldentroupe", wearer="bennett"),)),
                ),
                (
                    "exceeds",
                    dict(
                        finalists=(
                            _state("goldentroupe"),
                            _state("gladiatorsfinale"),
                        ),
                        budget=_budget(max_finalists=1, top_n=1),
                    ),
                ),
            )
            for expected, changes in cases:
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(GcsimFinalistOptimizerError, expected):
                        _request(root, **changes)

    def test_request_rejects_infeasible_optimizer_roll_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for expected, options in (
                (
                    "negative liquid cap",
                    {"fixed_substats_count": 11, "indiv_liquid_cap": 10},
                ),
                (
                    "exceeds the available",
                    {"total_liquid_substats": 1000},
                ),
            ):
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(
                        GcsimFinalistOptimizerError,
                        expected,
                    ):
                        _request(root / expected, optimizer_options=options)

    def test_semantic_roll_validation_accepts_scalarless_and_four_star_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = (
                (
                    "scalarless",
                    _state("goldentroupe"),
                    {"fine_tune": 0, "show_substat_scalars": 0},
                ),
                (
                    "four-star",
                    _state("instructor", offpiece="goblet"),
                    {"fine_tune": 0},
                ),
            )
            for label, state, options in cases:
                with self.subTest(label=label):
                    request = _request(
                        root / label,
                        finalists=(state,),
                        optimizer_options=options,
                    )
                    result = run_gcsim_finalist_optimizer(
                        request,
                        session_factory=EvidenceSessionFactory(
                            root / label / "runs"
                        ),
                    )
                    self.assertEqual(
                        result.status,
                        GcsimFinalistOptimizerStatus.BEST_FOUND,
                    )

    def test_non_typed_and_forged_runner_results_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(
                root,
                finalists=(
                    _state("gladiatorsfinale"),
                    _state("goldentroupe"),
                ),
                budget=_budget(max_finalists=2, top_n=2),
            )
            factory = EvidenceSessionFactory(
                root / "runs",
                modes=("non_typed", "forged_artifact"),
            )

            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=factory,
            )

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.NO_SUCCESS)
            self.assertEqual(result.successful_count, 0)
            self.assertEqual(result.outcomes, ())
            self.assertEqual(
                tuple(item.status for item in result.attempts),
                (
                    GcsimFinalistAttemptStatus.RESULT_REJECTED,
                    GcsimFinalistAttemptStatus.RESULT_REJECTED,
                ),
            )
            self.assertIn("non_typed", result.attempts[0].error)
            self.assertIn("bound engine", result.attempts[1].error)

    def test_wrong_iterations_or_mutated_optimized_contract_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for mode, expected in (
                ("wrong_iterations", "iteration count"),
                ("wave_output", "static-target contract"),
                ("missing_allocations", "main-stat row"),
                ("unchanged_output", "must differ"),
                ("mutated_shell", "non-stat config shell"),
                ("impossible_substats", "roll unit"),
                ("missing_substat_key", "every pinned optimizer stat"),
                ("non_integer_scalar", "integer roll count"),
                ("wrong_total_rolls", "total liquid roll budget"),
                ("over_stat_cap", "main-stat-aware liquid cap"),
                ("below_fixed_floor", "fixed-roll floor"),
                ("post_snapshot_mutation", "changed after the runner byte snapshot"),
            ):
                with self.subTest(mode=mode):
                    request = _request(root / mode)
                    factory = EvidenceSessionFactory(
                        root / mode / "runs",
                        modes=(mode,),
                    )
                    result = run_gcsim_finalist_optimizer(
                        request,
                        session_factory=factory,
                    )
                    self.assertEqual(
                        result.status,
                        GcsimFinalistOptimizerStatus.NO_SUCCESS,
                    )
                    self.assertEqual(
                        result.attempts[0].status,
                        GcsimFinalistAttemptStatus.RESULT_REJECTED,
                    )
                    self.assertIn(expected, result.attempts[0].error)

    def test_cancel_forwards_to_active_optimizer_and_preserves_typed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            blocking = BlockingSession()
            session = GcsimFinalistOptimizerSession(
                request,
                session_factory=lambda _request: blocking,
            )
            result_box: list[object] = []
            thread = Thread(target=lambda: result_box.append(session.run()))
            thread.start()
            self.assertTrue(blocking.entered.wait(timeout=2))

            session.cancel()
            thread.join(timeout=3)

            self.assertFalse(thread.is_alive())
            self.assertTrue(blocking.cancelled.is_set())
            result = result_box[0]
            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.CANCELLED)
            self.assertEqual(result.attempted_count, 1)
            self.assertEqual(
                result.attempts[0].runner_status,
                GcsimOptimizerRunStatus.CANCELLED.value,
            )

    def test_deadline_includes_session_factory_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            request = _request(
                Path(tmp),
                budget=_budget(overall_deadline_seconds=1),
            )
            created: list[NeverRunSession] = []

            def factory(_request):
                clock.value = 2
                session = NeverRunSession()
                created.append(session)
                return session

            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=factory,
                clock=clock,
            )

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.DEADLINE)
            self.assertEqual(result.stop_reason, "deadline_reached")
            self.assertEqual(result.attempted_count, 1)
            self.assertTrue(created[0].cancelled)
            self.assertFalse(created[0].run_called)
            self.assertIn("deadline_before_session_run", result.attempts[0].error)

    def test_fresh_outer_timer_covers_partial_factory_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(
                Path(tmp),
                budget=_budget(overall_deadline_seconds=0.15),
            )
            blocking = BlockingSession()

            def factory(_request):
                sleep(0.06)
                return blocking

            started = monotonic()
            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=factory,
            )
            elapsed = monotonic() - started

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.DEADLINE)
            self.assertTrue(blocking.cancelled.is_set())
            self.assertLess(elapsed, 0.75)

    def test_typed_failure_survives_engine_removal_after_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)

            def factory(run_request: GcsimOptimizerRunRequest):
                Path(run_request.artifact_path).unlink()
                return ReturningFailedSession()

            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=factory,
            )

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.NO_SUCCESS)
            self.assertEqual(
                result.attempts[0].status,
                GcsimFinalistAttemptStatus.RUN_FAILED,
            )
            self.assertEqual(
                result.attempts[0].runner_status,
                GcsimOptimizerRunStatus.CANCELLED.value,
            )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            Path(request.engine_context.artifact_path).write_bytes(
                b"mutated after frozen request"
            )

            result = run_gcsim_finalist_optimizer(
                request,
                session_factory=lambda _request: ReturningFailedSession(),
            )

            self.assertEqual(result.status, GcsimFinalistOptimizerStatus.NO_SUCCESS)
            self.assertEqual(
                result.attempts[0].status,
                GcsimFinalistAttemptStatus.RUN_FAILED,
            )

    def test_result_wrapper_rejects_forged_provenance_and_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_gcsim_finalist_optimizer(
                _request(root),
                session_factory=EvidenceSessionFactory(root / "runs"),
            )
            with self.assertRaisesRegex(
                GcsimFinalistOptimizerError,
                "request_sha256",
            ):
                replace(result, request_sha256="0" * 64)
            with self.assertRaisesRegex(
                GcsimFinalistOptimizerError,
                "canonical top-N",
            ):
                replace(result, outcomes=())
            with self.assertRaisesRegex(
                GcsimFinalistOptimizerError,
                "byte snapshot",
            ):
                replace(result.best_found, result_json_bytes=b"{}")
            forged_input = result.best_found.optimizer_input_config_text.replace(
                "refine=1",
                "refine=2",
            )
            forged_optimized = result.best_found.optimized_config_text.replace(
                "refine=1",
                "refine=2",
            )
            forged_runner = replace(
                result.best_found.runner_result,
                input_config_bytes=forged_input.encode("utf-8"),
                optimized_config_bytes=forged_optimized.encode("utf-8"),
                input_config_sha256=hashlib.sha256(
                    forged_input.encode("utf-8")
                ).hexdigest(),
                optimized_config_sha256=hashlib.sha256(
                    forged_optimized.encode("utf-8")
                ).hexdigest(),
            )
            forged_outcome = replace(
                result.best_found,
                optimizer_input_config_text=forged_input,
                optimizer_input_sha256=hashlib.sha256(
                    forged_input.encode("utf-8")
                ).hexdigest(),
                optimized_config_text=forged_optimized,
                optimized_config_sha256=hashlib.sha256(
                    forged_optimized.encode("utf-8")
                ).hexdigest(),
                runner_result=forged_runner,
            )
            forged_attempt = replace(
                result.attempts[0],
                optimizer_input_sha256=forged_outcome.optimizer_input_sha256,
                runner_result=forged_runner,
                outcome=forged_outcome,
            )
            with self.assertRaisesRegex(
                GcsimFinalistOptimizerError,
                "deterministic request/state materialization",
            ):
                replace(
                    result,
                    attempts=(forged_attempt,),
                    outcomes=(forged_outcome,),
                )
            with self.assertRaisesRegex(
                GcsimFinalistOptimizerError,
                "must not carry a passed runner result",
            ):
                replace(
                    result.attempts[0],
                    status=GcsimFinalistAttemptStatus.RUN_FAILED,
                    outcome=None,
                    error="forged failure",
                )


class EvidenceSessionFactory:
    def __init__(
        self,
        root: Path,
        *,
        dps_by_set: dict[str, float] | None = None,
        modes: tuple[str, ...] = (),
    ) -> None:
        self.root = root
        self.dps_by_set = dps_by_set or {}
        self.modes = modes
        self.requests: list[GcsimOptimizerRunRequest] = []

    def __call__(self, request: GcsimOptimizerRunRequest):
        ordinal = len(self.requests)
        self.requests.append(request)
        mode = self.modes[ordinal] if ordinal < len(self.modes) else "valid"
        return EvidenceSession(
            request,
            run_dir=self.root / f"run-{ordinal}",
            dps_by_set=self.dps_by_set,
            mode=mode,
        )


class EvidenceSession:
    def __init__(
        self,
        request: GcsimOptimizerRunRequest,
        *,
        run_dir: Path,
        dps_by_set: dict[str, float],
        mode: str,
    ) -> None:
        self.request = request
        self.run_dir = run_dir
        self.dps_by_set = dps_by_set
        self.mode = mode
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        if self.mode == "non_typed":
            return {"status": "passed"}
        if self.cancelled:
            return _cancelled_result()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        input_path = self.run_dir / DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME
        optimized_path = self.run_dir / DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME
        result_path = self.run_dir / DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME
        config = str(self.request.config_text)
        input_path.write_bytes(config.encode("utf-8"))
        optimized = re.sub(
            r"(?m)^(?P<wearer>[a-z]+) add stats hp=(?:4780|3571)\b[^;]*;$",
            lambda match: (
                match.group(0)
                + "\n"
                + _fixture_substat_row(
                    match.group("wearer"),
                    config,
                    show_scalars=int(
                        float(
                            self.request.optimizer_options.get(
                                "show_substat_scalars",
                                1,
                            )
                        )
                    )
                    > 0,
                )
            ),
            config,
        )
        if self.mode == "unchanged_output":
            optimized = config
        if self.mode == "mutated_shell":
            optimized += "wait(1);\n"
        if self.mode == "wave_output":
            optimized += "# gtt_wave duplicate_first_target=1\n"
        if self.mode == "missing_allocations":
            optimized = "\n".join(
                line for line in optimized.splitlines() if " add stats " not in line
            ) + "\n"
        if self.mode == "impossible_substats":
            optimized = optimized.replace("cr=0.0331*4", "cr=999999*4")
        if self.mode == "missing_substat_key":
            optimized = optimized.replace(" cr=0.0331*4", "")
        if self.mode == "non_integer_scalar":
            optimized = optimized.replace("cr=0.0331*4", "cr=0.0331*4.5")
        if self.mode == "wrong_total_rolls":
            optimized = optimized.replace("cr=0.0331*4", "cr=0.0331*5")
        if self.mode == "over_stat_cap":
            optimized = optimized.replace("cr=0.0331*4", "cr=0.0331*11")
        if self.mode == "below_fixed_floor":
            optimized = optimized.replace("cr=0.0331*4", "cr=0.0331*1")
        optimized_path.write_bytes(optimized.encode("utf-8"))
        set_key_match = re.search(r'furina add set="([a-z0-9]+)"', config)
        set_key = set_key_match.group(1)
        iterations_match = re.search(r"\biteration=(\d+)\b", config)
        iterations = int(iterations_match.group(1))
        if self.mode == "wrong_iterations":
            iterations += 1
        dps = self.dps_by_set.get(set_key, 1000.0)
        result_path.write_bytes(
            json.dumps(
                {
                    "schema_version": 1,
                    "sim_version": "fixture",
                    "statistics": {
                        "iterations": iterations,
                        "dps": {"mean": dps, "sd": 20.0},
                        "duration": {"mean": 20.0},
                        "total_damage": {"mean": dps * 20.0},
                    },
                }
            ).encode("utf-8"),
        )
        summary = parse_gcsim_result_file(result_path)
        artifact_sha = self.request.expected_artifact_sha256
        if self.mode == "forged_artifact":
            artifact_sha = (
                "f" * 64
                if artifact_sha != "f" * 64
                else "e" * 64
            )
        runner_result = GcsimOptimizerRunResult(
            status=GcsimOptimizerRunStatus.PASSED,
            success=True,
            session_status=GcsimOptimizerSessionStatus.PASSED,
            artifact_path=str(self.request.artifact_path),
            artifact_source="explicit",
            artifact_sha256=artifact_sha,
            engine_binding_sha256=self.request.engine_binding_sha256,
            run_dir=str(self.run_dir),
            input_config_path=str(input_path),
            optimized_config_path=str(optimized_path),
            result_path=str(result_path),
            input_config_bytes=input_path.read_bytes(),
            optimized_config_bytes=optimized_path.read_bytes(),
            result_json_bytes=result_path.read_bytes(),
            input_config_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
            optimized_config_sha256=hashlib.sha256(
                optimized_path.read_bytes()
            ).hexdigest(),
            result_json_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
            optimize=_passed_stage(GcsimOptimizerStageName.OPTIMIZE),
            simulate=_passed_stage(GcsimOptimizerStageName.SIMULATE),
            summary=summary,
            elapsed_seconds=0.01,
        )
        if self.mode == "post_snapshot_mutation":
            optimized_path.write_bytes(
                optimized.replace("cr=0.0331*4", "cr=0.0331*5").encode("utf-8")
            )
        return runner_result


class BlockingSession:
    def __init__(self) -> None:
        self.entered = Event()
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self) -> GcsimOptimizerRunResult:
        self.entered.set()
        self.cancelled.wait(timeout=3)
        return _cancelled_result()


class NeverRunSession:
    def __init__(self) -> None:
        self.cancelled = False
        self.run_called = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        self.run_called = True
        raise AssertionError("deadline must stop before session.run")


class ReturningFailedSession:
    def cancel(self) -> None:
        pass

    def run(self) -> GcsimOptimizerRunResult:
        return _cancelled_result()


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _passed_stage(name: GcsimOptimizerStageName) -> GcsimOptimizerStageDiagnostic:
    return GcsimOptimizerStageDiagnostic(
        name=name,
        status=GcsimOptimizerStageStatus.PASSED,
        command=("fixture-gcsim", name.value),
        returncode=0,
    )


def _cancelled_result() -> GcsimOptimizerRunResult:
    return GcsimOptimizerRunResult(
        status=GcsimOptimizerRunStatus.CANCELLED,
        success=False,
        session_status=GcsimOptimizerSessionStatus.CANCELLED,
        error="cancelled by test",
    )


def _request(
    root: Path,
    *,
    config: str = CONFIG,
    finalists: tuple[FullTeamPhysicalState, ...] | None = None,
    budget: GcsimFinalistOptimizerBudget | None = None,
    optimizer_options: dict[str, int | float] | None = None,
) -> GcsimFinalistOptimizerRequest:
    root.mkdir(parents=True, exist_ok=True)
    context = _context(root)
    return GcsimFinalistOptimizerRequest(
        engine_context=context,
        prepared_config_text=config,
        wearer_ids=("furina",),
        layout_catalog={"furina": {"main/hydro": _layout()}},
        finalists=finalists or (_state("goldentroupe"),),
        budget=budget or _budget(),
        optimizer_options=(
            {"fine_tune": 0}
            if optimizer_options is None
            else optimizer_options
        ),
        environment={"GTT_FINALIST_TEST": "1"},
    )


def _budget(
    *,
    max_finalists: int = 1,
    top_n: int = 1,
    overall_deadline_seconds: float = 30,
) -> GcsimFinalistOptimizerBudget:
    return GcsimFinalistOptimizerBudget(
        max_finalists=max_finalists,
        top_n=top_n,
        worker_count=1,
        validation_iterations=200,
        overall_deadline_seconds=overall_deadline_seconds,
        optimizer_timeout_seconds=10,
        simulation_timeout_seconds=10,
    )


def _state(
    set_key: str,
    *,
    layout_id: str = "main/hydro",
    offpiece: str = "",
    wearer: str = "furina",
) -> FullTeamPhysicalState:
    return FullTeamPhysicalState(
        choices=(
            FourPieceSetState(
                wearer_id=wearer,
                set_key=set_key,
                main_stat_layout_id=layout_id,
                offpiece_slot=offpiece,
            ),
        )
    )


def _layout() -> GcsimFiveStarMainStatLayout:
    return GcsimFiveStarMainStatLayout("hp%", "hydro%", "cr")


def _fixture_substat_row(
    wearer: str,
    config: str,
    *,
    show_scalars: bool,
) -> str:
    set_match = re.search(
        rf'(?m)^{re.escape(wearer)} add set="([a-z0-9]+)" count=4;$',
        config,
    )
    is_four_star = set_match is not None and set_match.group(1) == "instructor"
    rarity_modifier = 0.84 if is_four_star else 1.0
    liquid_counts = (2,) * 6 + ((0,) * 4 if is_four_star else (2,) * 4)
    terms = []
    for (key, base_value), liquid in zip(
        GCSIM_SUBSTAT_ROLL_VALUES.items(),
        liquid_counts,
        strict=True,
    ):
        total_count = 2 + liquid
        roll_unit = base_value * rarity_modifier
        if show_scalars:
            terms.append(f"{key}={roll_unit:.6g}*{total_count}")
        else:
            terms.append(f"{key}={roll_unit * total_count:.6g}")
    return f"{wearer} add stats {' '.join(terms)};"


def _context(root: Path) -> GcsimOptimizerEngineContext:
    artifact = root / "gtt-gcsim.exe"
    if not artifact.exists():
        artifact.write_bytes(b"fixture engine")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=(
            _capability("gladiatorsfinale", rarity=5),
            _capability("goldentroupe", rarity=5),
            _capability("instructor", rarity=4),
        ),
    )
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(root),
        engine_version="fixture-version",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_path=str(artifact),
        artifact_sha256=artifact_sha,
        engine_tree_sha256="e" * 64,
        catalog=catalog,
        manifest_artifact_sha256=artifact_sha,
        manifest_engine_tree_sha256="e" * 64,
        binding_sha256="b" * 64,
        trusted=True,
    )


def _capability(key: str, *, rarity: int) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=rarity,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
    )


if __name__ == "__main__":
    unittest.main()
