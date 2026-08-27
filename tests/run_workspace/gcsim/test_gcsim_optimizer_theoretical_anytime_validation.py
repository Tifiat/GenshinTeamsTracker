from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import run_workspace.gcsim.optimizer_theoretical_anytime_validation as validation_module
from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_finalist_optimizer import (
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerSession,
)
from run_workspace.gcsim.farming_profile_config import (
    apply_gcsim_screening_runtime_options,
)
from run_workspace.gcsim.farming_search import FourPieceSetState
from run_workspace.gcsim.farming_team_search import FullTeamPhysicalState
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from run_workspace.gcsim.optimizer_cache import GcsimOptimizerCacheStore
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWorkPlan,
    build_gcsim_optimizer_source_simulation_identity,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_validation import (
    GcsimOptimizerTheoreticalValidatedEvaluation,
    GcsimOptimizerTheoreticalValidationError,
    GcsimOptimizerTheoreticalValidationPlan,
    GcsimOptimizerTheoreticalValidationSession,
    GcsimOptimizerTheoreticalValidationStatus,
)

from tests.run_workspace.gcsim.test_gcsim_farming_evaluator import (
    _passed_result,
)
from tests.run_workspace.gcsim.test_gcsim_farming_finalist_optimizer import (
    EvidenceSessionFactory,
)


_WEARER_IDS = ("furina", "bennett", "xiangling", "xingqiu")
_LAYOUT_ID = "main/hydro"


class GcsimOptimizerTheoreticalAnytimeValidationTests(
    unittest.TestCase
):
    def test_enabled_cache_resolves_default_store_for_expensive_finalists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=1)
            session = GcsimOptimizerTheoreticalValidationSession(
                fixture.request,
                engine_context=fixture.context,
                prepared_config_text=fixture.config,
                layout_catalog=fixture.layouts,
                finalists=(
                    _state(
                        fixture.set_keys[0],
                        fallback=fixture.set_keys[0],
                    ),
                ),
                plan=GcsimOptimizerTheoreticalValidationPlan(),
                enable_cache=True,
            )

        self.assertIsInstance(session.cache_store, GcsimOptimizerCacheStore)

    def test_plan_cannot_authorize_more_than_six_substat_optimizations(
        self,
    ) -> None:
        with self.assertRaises(
            GcsimOptimizerTheoreticalValidationError
        ):
            GcsimOptimizerTheoreticalValidationPlan(
                max_finalists=7,
                top_n=6,
            )

    def test_substat_optimization_is_capped_at_six_and_validates_at_200(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=8)
            finalists = tuple(
                _state(key, fallback=fixture.set_keys[0])
                for key in fixture.set_keys
            )
            runner_factory = EvidenceSessionFactory(
                fixture.root / "optimizer-runs",
                dps_by_set={
                    key: 10_000.0 - index * 1_000.0
                    for index, key in enumerate(fixture.set_keys)
                },
            )
            optimizer_factory = _OptimizerFactory(runner_factory)

            result = _session(
                fixture,
                finalists=finalists,
                optimizer_factory=optimizer_factory,
            ).run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
        )
        self.assertEqual(len(optimizer_factory.requests), 1)
        finalist_request = optimizer_factory.requests[0]
        self.assertEqual(len(finalist_request.finalists), 6)
        self.assertEqual(finalist_request.budget.max_finalists, 6)
        self.assertEqual(finalist_request.budget.top_n, 6)
        self.assertEqual(
            finalist_request.budget.validation_iterations,
            200,
        )
        self.assertEqual(
            dict(finalist_request.optimizer_options),
            {"fine_tune": 0, "optimize_er": 0},
        )
        # One optimizer execution owns one and only one substatOptim pass.
        self.assertEqual(len(runner_factory.requests), 6)
        self.assertTrue(
            all(
                _runtime_option(request.config_text, "iteration") == 200
                for request in runner_factory.requests
            )
        )
        self.assertEqual(result.requested_rerace_count, 0)
        self.assertTrue(result.evaluations)
        self.assertTrue(
            all(item.iterations == 200 for item in result.evaluations)
        )

    def test_close_leaders_rerace_ordinary_optimized_configs_at_1000(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=2)
            finalists = tuple(
                _state(key, fallback=fixture.set_keys[0])
                for key in fixture.set_keys
            )
            runner_factory = EvidenceSessionFactory(
                fixture.root / "optimizer-runs",
                dps_by_set={
                    fixture.set_keys[0]: 1_000.0,
                    fixture.set_keys[1]: 998.0,
                },
            )
            optimizer_factory = _OptimizerFactory(runner_factory)
            rerace_factory = _OrdinaryEvaluationFactory(
                {
                    fixture.set_keys[0]: 995.0,
                    fixture.set_keys[1]: 1_005.0,
                }
            )
            progress = []

            result = _session(
                fixture,
                finalists=finalists,
                optimizer_factory=optimizer_factory,
                evaluation_factory=rerace_factory,
                progress_callback=lambda *event: progress.append(event),
            ).run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
        )
        self.assertEqual(len(runner_factory.requests), 2)
        self.assertEqual(len(rerace_factory.requests), 2)
        self.assertEqual(result.requested_rerace_count, 2)
        self.assertEqual(result.best_found.iterations, 1000)
        self.assertEqual(
            result.best_found.state.choices[0].set_key,
            fixture.set_keys[1],
        )

        optimized_by_set = {
            outcome.state.choices[0].set_key: outcome.optimized_config_text
            for outcome in result.finalist_result.all_successful_outcomes
        }
        for request in rerace_factory.requests:
            set_key = request.candidate_keys[0][1]
            self.assertEqual(request.expected_iterations, 1000)
            self.assertEqual(request.worker_count, 1)
            self.assertEqual(
                request.config_text,
                apply_gcsim_screening_runtime_options(
                    optimized_by_set[set_key],
                    iterations=1000,
                    workers=1,
                ),
            )
            self.assertNotIn("-substatOptim", request.config_text)
            self.assertGreater(
                request.config_text.count(" add stats "),
                len(_WEARER_IDS),
            )
        # Rerace went through ordinary evaluation; it did not create another
        # optimizer runner request.
        self.assertEqual(len(runner_factory.requests), len(finalists))

        self.assertEqual(progress[0][:3], ("validate_200", 0, 2))
        self.assertEqual(progress[0][3], 0)
        self.assertIsNone(progress[0][4])
        self.assertTrue(
            any(
                stage == "validate_200"
                and completed == planned == 2
                and leader is not None
                and leader.iterations == 200
                for stage, completed, planned, _hits, leader in progress
            )
        )
        self.assertTrue(
            any(
                stage == "rerace_1000"
                and completed == 0
                and planned == 2
                and leader is not None
                and leader.iterations == 200
                for stage, completed, planned, _hits, leader in progress
            )
        )
        self.assertTrue(
            any(
                stage == "rerace_1000"
                and completed == planned == 2
                and leader is not None
                and leader.iterations == 1000
                for stage, completed, planned, _hits, leader in progress
            )
        )
        self.assertTrue(
            all(
                leader is None or leader.iterations >= 200
                for _stage, _completed, _planned, _hits, leader in progress
            )
        )
        self.assertTrue(
            all(item.iterations >= 200 for item in result.evaluations)
        )

    def test_distant_leader_does_not_rerace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=2)
            finalists = tuple(
                _state(key, fallback=fixture.set_keys[0])
                for key in fixture.set_keys
            )
            runner_factory = EvidenceSessionFactory(
                fixture.root / "optimizer-runs",
                dps_by_set={
                    fixture.set_keys[0]: 1_000.0,
                    fixture.set_keys[1]: 800.0,
                },
            )
            optimizer_factory = _OptimizerFactory(runner_factory)
            rerace_factory = _OrdinaryEvaluationFactory({})

            result = _session(
                fixture,
                finalists=finalists,
                optimizer_factory=optimizer_factory,
                evaluation_factory=rerace_factory,
            ).run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
        )
        self.assertEqual(result.requested_rerace_count, 0)
        self.assertEqual(rerace_factory.requests, [])
        self.assertTrue(
            all(item.iterations == 200 for item in result.evaluations)
        )

    def test_live_cache_hits_are_cumulative_within_validation_and_rerace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = _fixture(root, set_count=2)
            finalists = tuple(
                _state(key, fallback=fixture.set_keys[0])
                for key in fixture.set_keys
            )
            cache = GcsimOptimizerCacheStore(root / "cache")
            runner_factory = EvidenceSessionFactory(
                root / "optimizer-runs",
                dps_by_set={
                    fixture.set_keys[0]: 1_000.0,
                    fixture.set_keys[1]: 998.0,
                },
            )

            def finalist_session(request, **kwargs):
                return GcsimFinalistOptimizerSession(
                    request,
                    session_factory=runner_factory,
                    **kwargs,
                )

            common = dict(
                engine_context=fixture.context,
                prepared_config_text=fixture.config,
                layout_catalog=fixture.layouts,
                finalists=finalists,
                plan=GcsimOptimizerTheoreticalValidationPlan(),
                cache_store=cache,
                enable_cache=True,
            )
            first_rerace = _OrdinaryEvaluationFactory(
                {
                    fixture.set_keys[0]: 995.0,
                    fixture.set_keys[1]: 1_005.0,
                }
            )
            with patch.object(
                validation_module,
                "GcsimFinalistOptimizerSession",
                finalist_session,
            ):
                first = GcsimOptimizerTheoreticalValidationSession(
                    fixture.request,
                    evaluation_session_factory=first_rerace,
                    **common,
                ).run()

            progress = []
            second_rerace = _OrdinaryEvaluationFactory(
                {
                    fixture.set_keys[0]: 995.0,
                    fixture.set_keys[1]: 1_005.0,
                }
            )
            before_second = len(runner_factory.requests)
            with patch.object(
                validation_module,
                "GcsimFinalistOptimizerSession",
                finalist_session,
            ):
                second = GcsimOptimizerTheoreticalValidationSession(
                    fixture.request,
                    progress_callback=lambda *event: progress.append(event),
                    evaluation_session_factory=second_rerace,
                    **common,
                ).run()

        self.assertEqual(
            first.status,
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
        )
        self.assertEqual(
            second.status,
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
        )
        self.assertEqual(len(runner_factory.requests), before_second)
        self.assertEqual(second_rerace.requests, [])
        self.assertTrue(
            all(attempt.cache_hit for attempt in second.finalist_result.attempts)
        )
        self.assertTrue(
            all(result.cache_hit for result in second.rerace_results)
        )

        for stage in ("validate_200", "rerace_1000"):
            rows = [event for event in progress if event[0] == stage]
            self.assertEqual(
                [event[1] for event in rows],
                list(range(len(finalists) + 1)),
            )
            hits = [event[3] for event in rows]
            self.assertEqual(hits, sorted(hits))
            self.assertEqual(hits[0], 0)
            self.assertEqual(hits[-1], len(finalists))
            self.assertEqual(hits, [0, 1, 2])

    def test_pre_cancel_stops_before_substat_optimization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=1)
            runner_factory = EvidenceSessionFactory(
                fixture.root / "optimizer-runs"
            )
            optimizer_factory = _OptimizerFactory(runner_factory)
            progress = []
            session = _session(
                fixture,
                finalists=(
                    _state(
                        fixture.set_keys[0],
                        fallback=fixture.set_keys[0],
                    ),
                ),
                optimizer_factory=optimizer_factory,
                progress_callback=lambda *event: progress.append(event),
            )

            session.cancel()
            result = session.run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalValidationStatus.CANCELLED,
        )
        self.assertEqual(result.evaluations, ())
        self.assertEqual(result.requested_rerace_count, 0)
        self.assertEqual(runner_factory.requests, [])
        self.assertTrue(progress)
        self.assertTrue(
            all(
                leader is None or leader.iterations >= 200
                for _stage, _completed, _planned, _hits, leader in progress
            )
        )

    def test_lower_fidelity_outcome_cannot_enter_displayable_result(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _fixture(Path(tmp), set_count=1)
            state = _state(
                fixture.set_keys[0],
                fallback=fixture.set_keys[0],
            )
            request = GcsimFinalistOptimizerRequest(
                engine_context=fixture.context,
                prepared_config_text=fixture.config,
                wearer_ids=_WEARER_IDS,
                layout_catalog=fixture.layouts,
                finalists=(state,),
                budget=GcsimFinalistOptimizerBudget(
                    max_finalists=1,
                    top_n=1,
                    worker_count=1,
                    validation_iterations=32,
                    overall_deadline_seconds=30.0,
                    optimizer_timeout_seconds=10.0,
                    simulation_timeout_seconds=10.0,
                ),
                optimizer_options={"fine_tune": 0, "optimize_er": 0},
            )
            finalist = GcsimFinalistOptimizerSession(
                request,
                session_factory=EvidenceSessionFactory(
                    fixture.root / "lower-fidelity-runs"
                ),
            ).run()

        self.assertEqual(finalist.outcomes[0].iterations, 32)
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalValidationError,
            "200-iteration",
        ):
            GcsimOptimizerTheoreticalValidatedEvaluation(
                request_sha256=fixture.request.request_sha256,
                finalist_outcome=finalist.outcomes[0],
            )


class _Fixture:
    def __init__(
        self,
        *,
        root: Path,
        context: GcsimOptimizerEngineContext,
        config: str,
        request: GcsimOptimizerOperationRequest,
        set_keys: tuple[str, ...],
    ) -> None:
        self.root = root
        self.context = context
        self.config = config
        self.request = request
        self.set_keys = set_keys
        layout = GcsimFiveStarMainStatLayout("hp%", "hydro%", "cr")
        self.layouts = {
            wearer: {_LAYOUT_ID: layout}
            for wearer in _WEARER_IDS
        }


class _OptimizerFactory:
    def __init__(self, runner_factory: EvidenceSessionFactory) -> None:
        self.runner_factory = runner_factory
        self.requests: list[GcsimFinalistOptimizerRequest] = []

    def __call__(self, request: GcsimFinalistOptimizerRequest):
        self.requests.append(request)
        return GcsimFinalistOptimizerSession(
            request,
            session_factory=self.runner_factory,
        )


class _OrdinaryEvaluationFactory:
    def __init__(self, dps_by_set: dict[str, float]) -> None:
        self.dps_by_set = dict(dps_by_set)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return _OrdinaryEvaluationSession(
            request,
            dps=self.dps_by_set[request.candidate_keys[0][1]],
        )


class _OrdinaryEvaluationSession:
    def __init__(self, request, *, dps: float) -> None:
        self.request = request
        self.dps = dps
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        if self.cancelled:
            raise AssertionError("ordinary rerace was unexpectedly cancelled")
        return _passed_result(self.request, self.dps, sd=20.0)


def _session(
    fixture: _Fixture,
    *,
    finalists: tuple[FullTeamPhysicalState, ...],
    optimizer_factory: _OptimizerFactory,
    evaluation_factory: _OrdinaryEvaluationFactory | None = None,
    progress_callback=None,
) -> GcsimOptimizerTheoreticalValidationSession:
    return GcsimOptimizerTheoreticalValidationSession(
        fixture.request,
        engine_context=fixture.context,
        prepared_config_text=fixture.config,
        layout_catalog=fixture.layouts,
        finalists=finalists,
        plan=GcsimOptimizerTheoreticalValidationPlan(),
        progress_callback=progress_callback,
        enable_cache=False,
        finalist_session_factory=optimizer_factory,
        evaluation_session_factory=evaluation_factory,
    )


def _fixture(root: Path, *, set_count: int) -> _Fixture:
    root.mkdir(parents=True, exist_ok=True)
    set_keys = tuple(f"set{index}" for index in range(set_count))
    artifact = root / "gtt-gcsim.exe"
    artifact.write_bytes(b"fixture engine")
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=tuple(_capability(key) for key in set_keys),
    )
    context = GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(root),
        engine_version="fixture-version",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_path=str(artifact),
        artifact_sha256=artifact_sha256,
        engine_tree_sha256="e" * 64,
        catalog=catalog,
        manifest_artifact_sha256=artifact_sha256,
        manifest_engine_tree_sha256="e" * 64,
        binding_sha256="b" * 64,
        trusted=True,
    )
    config = _config(set_keys[0])
    wearers = tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=None,
            gcsim_character_key=wearer,
        )
        for index, wearer in enumerate(_WEARER_IDS, start=1)
    )
    source = build_gcsim_optimizer_source_simulation_identity(
        engine_context=context,
        prepared_config_text=config,
        wearers=wearers,
    )
    request = GcsimOptimizerOperationRequest(
        operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        source_simulation=source,
        work_plan=GcsimOptimizerWorkPlan(
            operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            plan_id="theoretical_anytime_validation_fixture",
            plan_version=1,
        ),
    )
    return _Fixture(
        root=root,
        context=context,
        config=config,
        request=request,
        set_keys=set_keys,
    )


def _capability(key: str) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=5,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
    )


def _state(
    first_set: str,
    *,
    fallback: str,
) -> FullTeamPhysicalState:
    return FullTeamPhysicalState(
        choices=tuple(
            FourPieceSetState(
                wearer_id=wearer,
                set_key=first_set if index == 0 else fallback,
                main_stat_layout_id=_LAYOUT_ID,
            )
            for index, wearer in enumerate(_WEARER_IDS)
        )
    )


def _config(set_key: str) -> str:
    rows = []
    for wearer in _WEARER_IDS:
        rows.extend(
            (
                f"{wearer} char lvl=90/90 cons=0 talent=9,9,9;",
                (
                    f'{wearer} add weapon="favoniussword" '
                    "refine=1 lvl=90/90;"
                ),
                f'{wearer} add set="{set_key}" count=4;',
                (
                    f"{wearer} add stats hp=4780 atk=311 "
                    "hp%=0.466 hydro%=0.466 cr=0.311;"
                ),
            )
        )
    rows.extend(
        (
            "options swap_delay=12 iteration=10 workers=1;",
            "target lvl=100 hp=999999999;",
            "active furina;",
        )
    )
    return "\n".join(rows) + "\n"


def _runtime_option(config_text: str | None, option: str) -> int:
    match = re.search(
        rf"\b{re.escape(option)}=(\d+)\b",
        str(config_text),
    )
    if match is None:
        raise AssertionError(f"missing runtime option: {option}")
    return int(match.group(1))


if __name__ == "__main__":
    unittest.main()
