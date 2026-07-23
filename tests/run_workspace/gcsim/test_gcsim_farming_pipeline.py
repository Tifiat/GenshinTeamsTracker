from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
)
from run_workspace.gcsim.farming_pipeline import (
    GcsimFarmingFullTeamBatchSimulator,
    GcsimFarmingMaterializedProbe,
    GcsimFarmingPipelineError,
    GcsimFarmingScreeningFidelity,
    build_gcsim_farming_evaluation_context_sha256,
    materialize_gcsim_full_team_probe_state,
    materialize_gcsim_one_wearer_candidate,
)
from run_workspace.gcsim.farming_profile_config import (
    GCSIM_BALANCED_REFERENCE_WEIGHTS,
    build_default_gcsim_screening_profile_bank,
    build_gcsim_screening_investment_signature,
)
from run_workspace.gcsim.farming_search import (
    FourPieceSetState,
    SetProfileCandidate,
    StatProfileBank,
)
from run_workspace.gcsim.farming_team_search import (
    TEAM_SIM_PASSED,
    TEAM_SIM_TIMEOUT,
    FullTeamComposerError,
    FullTeamProbeState,
    FullTeamSimulationRequest,
)
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_engine_context import GcsimOptimizerEngineContext


PREPARED_CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="splendoroftranquilwaters" refine=1 lvl=90/90;
furina add set="gladiatorsfinale" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
bennett char lvl=90/90 cons=6 talent=9,9,10;
bennett add weapon="aquilafavonia" refine=1 lvl=90/90;
bennett add set="gladiatorsfinale" count=4;
bennett add stats hp=4780 atk=311 er=0.518 pyro%=0.466 cr=0.311;
options swap_delay=12 iteration=1000 workers=16;
target lvl=100 hp=999999999;
active furina;
"""

WEARERS = ("furina", "bennett")
FIDELITY = GcsimFarmingScreeningFidelity(iterations=25, worker_count=1)
INVESTMENT_SIGNATURE = build_gcsim_screening_investment_signature()


class GcsimFarmingMaterializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_bank = build_default_gcsim_screening_profile_bank()
        self.layouts = _layouts()

    def test_full_team_materializes_exact_sets_layouts_offpiece_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            state = _joint_state(
                furina_set="goldentroupe",
                furina_profile="focus/hp%",
                bennett_set="instructor",
                bennett_profile="focus/er",
                bennett_offpiece="sands",
            )

            proof = materialize_gcsim_full_team_probe_state(
                PREPARED_CONFIG,
                state=state,
                wearer_ids=WEARERS,
                layout_catalog=self.layouts,
                profile_bank=self.profile_bank,
                engine_context=context,
                fidelity=FIDELITY,
            )

            self.assertEqual(proof.candidate_keys, state.probe_key)
            self.assertEqual(proof.investment_signature, INVESTMENT_SIGNATURE)
            self.assertEqual(
                proof.set_assignments,
                (("furina", "goldentroupe"), ("bennett", "instructor")),
            )
            self.assertEqual(
                proof.offpiece_assignments,
                (("bennett", "sands"),),
            )
            self.assertEqual(
                proof.profile_assignments,
                (("furina", "focus/hp%"), ("bennett", "focus/er")),
            )
            self.assertIn('furina add set="goldentroupe" count=4;', proof.config_text)
            self.assertIn('bennett add set="instructor" count=4;', proof.config_text)
            self.assertIn(
                "bennett add stats hp=3571 atk=232 er=0.518 pyro%=0.348 cr=0.232;",
                proof.config_text,
            )
            self.assertIn("furina add stats atk%=", proof.config_text)
            self.assertIn("bennett add stats atk%=", proof.config_text)
            self.assertIn(
                "options swap_delay=12 iteration=25 workers=1;",
                proof.config_text,
            )
            self.assertNotIn("iteration=1000", proof.config_text)

    def test_one_wearer_probe_uses_explicit_other_wearer_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = _candidate(
                "furina",
                "goldentroupe",
                "furina-default",
                "focus/hp%",
            )
            baseline = _candidate(
                "bennett",
                "noblesseoblige",
                "bennett-default",
                "baseline",
            )

            proof = materialize_gcsim_one_wearer_candidate(
                PREPARED_CONFIG,
                candidate=target,
                frozen_baseline_states=(baseline,),
                wearer_ids=WEARERS,
                layout_catalog=self.layouts,
                profile_bank=self.profile_bank,
                engine_context=_context(Path(tmp)),
                fidelity=FIDELITY,
            )

            self.assertEqual(proof.state.choices, (target, baseline))
            self.assertIn('bennett add set="noblesseoblige" count=4;', proof.config_text)

            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "every other wearer exactly in canonical order",
            ):
                materialize_gcsim_one_wearer_candidate(
                    PREPARED_CONFIG,
                    candidate=target,
                    frozen_baseline_states=(),
                    wearer_ids=WEARERS,
                    layout_catalog=self.layouts,
                    profile_bank=self.profile_bank,
                    engine_context=_context(Path(tmp)),
                    fidelity=FIDELITY,
                )

    def test_missing_or_misordered_explicit_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            state = _joint_state()
            missing_layout = {
                "furina": {},
                "bennett": self.layouts["bennett"],
            }
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "non-empty"):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG,
                    state=state,
                    wearer_ids=WEARERS,
                    layout_catalog=missing_layout,
                    profile_bank=self.profile_bank,
                    engine_context=context,
                    fidelity=FIDELITY,
                )
            unknown_profile = FullTeamProbeState(
                choices=(
                    _candidate(
                        "furina",
                        "goldentroupe",
                        "furina-default",
                        "does-not-exist",
                    ),
                    state.choices[1],
                )
            )
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "missing explicit profile"):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG,
                    state=unknown_profile,
                    wearer_ids=WEARERS,
                    layout_catalog=self.layouts,
                    profile_bank=self.profile_bank,
                    engine_context=context,
                    fidelity=FIDELITY,
                )
            reversed_state = FullTeamProbeState(choices=tuple(reversed(state.choices)))
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "canonical order"):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG,
                    state=reversed_state,
                    wearer_ids=WEARERS,
                    layout_catalog=self.layouts,
                    profile_bank=self.profile_bank,
                    engine_context=context,
                    fidelity=FIDELITY,
                )
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "character declarations"):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG.replace(
                        "furina char", "bennett char", 1
                    ),
                    state=state,
                    wearer_ids=WEARERS,
                    layout_catalog=self.layouts,
                    profile_bank=self.profile_bank,
                    engine_context=context,
                    fidelity=FIDELITY,
                )

    def test_materialized_proof_blocks_independent_state_config_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            proof = materialize_gcsim_full_team_probe_state(
                PREPARED_CONFIG,
                state=_joint_state(),
                wearer_ids=WEARERS,
                layout_catalog=self.layouts,
                profile_bank=self.profile_bank,
                engine_context=context,
                fidelity=FIDELITY,
            )

            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "must be produced by the farming render pipeline",
            ):
                replace(proof, config_text="options iteration=1 workers=1;")

            request = proof.build_evaluator_request(
                engine_context=context,
                timeout_seconds=4.0,
            )
            self.assertEqual(request.candidate_keys, proof.state.probe_key)
            self.assertEqual(request.config_text, proof.config_text)
            self.assertEqual(request.investment_signature, proof.investment_signature)
            self.assertEqual(request.environment["GOMAXPROCS"], "1")
            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "environment differs",
            ):
                proof.build_evaluator_request(
                    engine_context=context,
                    timeout_seconds=4.0,
                    environment={"GODEBUG": "different"},
                )


class GcsimFarmingEvaluationContextTest(unittest.TestCase):
    def test_fidelity_and_prepared_config_enforce_static_target_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "ordinary farming evaluator"):
            GcsimFarmingScreeningFidelity(25, 1, contract="different")
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            common = dict(
                state=_joint_state(),
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=build_default_gcsim_screening_profile_bank(),
                engine_context=context,
                fidelity=FIDELITY,
            )
            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "exactly one static target",
            ):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG.replace(
                        "target lvl=100 hp=999999999;",
                        "target lvl=100 hp=999999999;\ntarget lvl=100 hp=1;",
                    ),
                    **common,
                )
            for poisoned in (
                PREPARED_CONFIG.replace(
                    "options swap_delay=12 iteration=1000 workers=16;",
                    "options swap_delay=12 iteration=1000 workers=16; "
                    "target lvl=100 hp=1;",
                ),
                PREPARED_CONFIG.replace(
                    "options swap_delay=12 iteration=1000 workers=16;",
                    "options swap_delay=12 iteration=1000 workers=16; "
                    "xiangling char lvl=90/90 cons=0 talent=1,1,1;",
                ),
                PREPARED_CONFIG.replace(
                    "furina add weapon=",
                    "furina add\n weapon=",
                ),
                PREPARED_CONFIG.replace(
                    "options swap_delay=12 iteration=1000 workers=16;",
                    'let x string = "foo\rbar"; target lvl=100 hp=1;\n'
                    "options swap_delay=12 iteration=1000 workers=16;",
                ),
                PREPARED_CONFIG.replace(
                    'furina add set="gladiatorsfinale" count=4;',
                    'furina add set="gladiatorsfinale" count=4; '
                    "# ignored by GCSIM\u2028target lvl=100 hp=1;",
                ),
                PREPARED_CONFIG.replace(
                    'furina add set="gladiatorsfinale" count=4;',
                    'furina add set="gladiatorsfinale" count=4; '
                    "# ignored by GCSIM\rtarget lvl=100 hp=1;",
                ),
            ):
                with self.subTest(poisoned=poisoned), self.assertRaisesRegex(
                    GcsimFarmingPipelineError,
                    "canonical semicolon-terminated row",
                ):
                    materialize_gcsim_full_team_probe_state(
                        poisoned,
                        **common,
                    )
            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "explicit positive hp",
            ):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG.replace(" hp=999999999", ""),
                    **common,
                )
            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "one explicit positive hp",
            ):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG.replace(
                        "hp=999999999",
                        "hp=999999999 hp=1",
                    ),
                    **common,
                )
            with self.assertRaisesRegex(
                GcsimFarmingPipelineError,
                "must not carry a type profile",
            ):
                materialize_gcsim_full_team_probe_state(
                    PREPARED_CONFIG.replace(
                        "hp=999999999",
                        "hp=999999999 type=dummy",
                    ),
                    **common,
                )
            for directive in (
                "# gtt_wave duplicate_first_target=1\n",
                "# gtt_wave_prototype duplicate_first_target=1\n",
                "// gtt_wave_prototype duplicate_first_target=1\n",
            ):
                with self.subTest(directive=directive), self.assertRaisesRegex(
                    GcsimFarmingPipelineError,
                    "wave directive",
                ):
                    materialize_gcsim_full_team_probe_state(
                        PREPARED_CONFIG + directive,
                        **common,
                    )

    def test_context_is_canonical_and_changes_with_frozen_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            bank = build_default_gcsim_screening_profile_bank()
            first = build_gcsim_farming_evaluation_context_sha256(
                engine_context=context,
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=bank,
                reference_weights=GCSIM_BALANCED_REFERENCE_WEIGHTS,
                fidelity=FIDELITY,
            )
            reordered_layouts = {
                "bennett": dict(reversed(tuple(_layouts()["bennett"].items()))),
                "furina": dict(reversed(tuple(_layouts()["furina"].items()))),
            }
            reordered_bank = StatProfileBank(
                axes=bank.axes,
                profiles=tuple(reversed(bank.profiles)),
            )
            second = build_gcsim_farming_evaluation_context_sha256(
                engine_context=context,
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=reordered_layouts,
                profile_bank=reordered_bank,
                reference_weights=tuple(reversed(GCSIM_BALANCED_REFERENCE_WEIGHTS)),
                fidelity=FIDELITY,
            )
            changed_fidelity = build_gcsim_farming_evaluation_context_sha256(
                engine_context=context,
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=bank,
                reference_weights=GCSIM_BALANCED_REFERENCE_WEIGHTS,
                fidelity=GcsimFarmingScreeningFidelity(26, 1),
            )
            changed_environment = build_gcsim_farming_evaluation_context_sha256(
                engine_context=context,
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=bank,
                reference_weights=GCSIM_BALANCED_REFERENCE_WEIGHTS,
                fidelity=FIDELITY,
                environment={"GODEBUG": "artifactscan=1"},
            )

            self.assertEqual(first, second)
            self.assertNotEqual(first, changed_fidelity)
            self.assertNotEqual(first, changed_environment)
            self.assertEqual(len(first), 64)

    def test_context_rejects_untrusted_engine_and_mixed_investment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common = dict(
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=build_default_gcsim_screening_profile_bank(),
                reference_weights=GCSIM_BALANCED_REFERENCE_WEIGHTS,
                fidelity=FIDELITY,
            )
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "resealed trusted"):
                build_gcsim_farming_evaluation_context_sha256(
                    engine_context=_context(Path(tmp), trusted=False),
                    **common,
                )
            with self.assertRaisesRegex(GcsimFarmingPipelineError, "investment signature"):
                build_gcsim_farming_evaluation_context_sha256(
                    engine_context=_context(Path(tmp)),
                    investment_signature="another-contract",
                    **common,
                )


class GcsimFarmingBatchAdapterTest(unittest.TestCase):
    def test_adapter_materializes_batch_runs_one_scheduler_and_maps_typed_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = RecordingSchedulerFactory(
                statuses=(
                    GcsimFarmingEvaluationStatus.PASSED,
                    GcsimFarmingEvaluationStatus.TIMEOUT,
                )
            )
            adapter = GcsimFarmingFullTeamBatchSimulator(
                engine_context=_context(Path(tmp)),
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=build_default_gcsim_screening_profile_bank(),
                fidelity=FIDELITY,
                scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 20.0),
                enable_cache=False,
                scheduler_factory=factory,
            )
            requests = (
                _simulation_request(adapter.evaluation_context_sha256, _joint_state(), 0),
                _simulation_request(
                    adapter.evaluation_context_sha256,
                    _joint_state(
                        furina_set="instructor",
                        furina_offpiece="goblet",
                        furina_profile="focus/em",
                    ),
                    1,
                ),
            )

            outcomes = adapter(requests)

            self.assertEqual(factory.calls, 1)
            self.assertEqual(len(factory.requests), 2)
            self.assertGreater(factory.budget.overall_deadline_seconds, 0.0)
            self.assertLessEqual(factory.budget.overall_deadline_seconds, 3.0)
            self.assertEqual(tuple(outcomes), tuple(item.state.probe_key for item in requests))
            self.assertEqual(outcomes[requests[0].state.probe_key].status, TEAM_SIM_PASSED)
            self.assertEqual(outcomes[requests[0].state.probe_key].dps_mean, 1000.0)
            self.assertEqual(outcomes[requests[0].state.probe_key].dps_se, 5.0)
            self.assertEqual(outcomes[requests[1].state.probe_key].status, TEAM_SIM_TIMEOUT)
            self.assertTrue(
                all("iteration=25 workers=1" in item.config_text for item in factory.requests)
            )
            self.assertTrue(
                all(item.environment["GOMAXPROCS"] == "1" for item in factory.requests)
            )
            self.assertEqual(
                tuple(item.candidate_keys for item in factory.requests),
                tuple(item.state.probe_key for item in requests),
            )

    def test_adapter_context_binds_the_effective_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common = dict(
                engine_context=_context(Path(tmp)),
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=build_default_gcsim_screening_profile_bank(),
                fidelity=FIDELITY,
                scheduler_budget=GcsimFarmingSchedulerBudget(1, 1, 20.0),
                enable_cache=False,
                scheduler_factory=RecordingSchedulerFactory(
                    statuses=(GcsimFarmingEvaluationStatus.PASSED,)
                ),
            )
            first = GcsimFarmingFullTeamBatchSimulator(
                **common,
                environment={"GODEBUG": "artifactscan=1", "GOMAXPROCS": "99"},
            )
            second = GcsimFarmingFullTeamBatchSimulator(
                **common,
                environment={"GODEBUG": "artifactscan=2"},
            )

            self.assertNotEqual(
                first.evaluation_context_sha256,
                second.evaluation_context_sha256,
            )
            self.assertEqual(first.environment["GOMAXPROCS"], "1")

    def test_adapter_rejects_context_mix_and_reordered_scheduler_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = RecordingSchedulerFactory(
                statuses=(
                    GcsimFarmingEvaluationStatus.PASSED,
                    GcsimFarmingEvaluationStatus.PASSED,
                ),
                reverse_results=True,
            )
            adapter = GcsimFarmingFullTeamBatchSimulator(
                engine_context=_context(Path(tmp)),
                prepared_config_text=PREPARED_CONFIG,
                wearer_ids=WEARERS,
                layout_catalog=_layouts(),
                profile_bank=build_default_gcsim_screening_profile_bank(),
                fidelity=FIDELITY,
                scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 20.0),
                enable_cache=False,
                scheduler_factory=factory,
            )
            with self.assertRaisesRegex(FullTeamComposerError, "different evaluation context"):
                adapter((_simulation_request("f" * 64, _joint_state(), 0),))

            requests = (
                _simulation_request(adapter.evaluation_context_sha256, _joint_state(), 0),
                _simulation_request(
                    adapter.evaluation_context_sha256,
                    _joint_state(furina_profile="focus/em"),
                    1,
                ),
            )
            with self.assertRaisesRegex(FullTeamComposerError, "result order"):
                adapter(requests)


class RecordingSchedulerFactory:
    def __init__(
        self,
        *,
        statuses: tuple[GcsimFarmingEvaluationStatus, ...],
        reverse_results: bool = False,
    ) -> None:
        self.statuses = statuses
        self.reverse_results = reverse_results
        self.calls = 0
        self.requests = ()
        self.budget = None

    def __call__(self, requests, budget):
        self.calls += 1
        self.requests = tuple(requests)
        self.budget = budget
        return FakeScheduler(
            self.requests,
            self.statuses,
            reverse_results=self.reverse_results,
        )


class FakeScheduler:
    def __init__(self, requests, statuses, *, reverse_results=False) -> None:
        self.requests = requests
        self.statuses = statuses
        self.reverse_results = reverse_results
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> GcsimFarmingBatchResult:
        results = tuple(
            _evaluation_result(request, status, index)
            for index, (request, status) in enumerate(
                zip(self.requests, self.statuses, strict=True)
            )
        )
        if self.reverse_results:
            results = tuple(reversed(results))
        successful = tuple(item for item in results if item.success)
        return GcsimFarmingBatchResult(
            status=(
                GcsimFarmingBatchStatus.COMPLETED
                if len(successful) == len(results)
                else GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS
            ),
            comparison_context_sha256=self.requests[0].comparison_context_sha256,
            results=results,
            best_result=successful[0] if successful else None,
            best_evaluation=None,
            requested_count=len(results),
            successful_count=len(successful),
            cache_hit_count=0,
            failed_count=len(results) - len(successful),
            skipped_count=0,
            max_parallel_candidates=2,
            total_cpu_budget=2,
            deadline_seconds=3.0,
            elapsed_seconds=0.01,
        )


def _evaluation_result(request, status, index) -> GcsimFarmingEvaluationResult:
    identity = request.identity
    success = status in {
        GcsimFarmingEvaluationStatus.PASSED,
        GcsimFarmingEvaluationStatus.CACHED,
    }
    return GcsimFarmingEvaluationResult(
        status=status,
        success=success,
        request_identity_sha256=identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        summary=(
            GcsimResultSummary(
                iterations=request.expected_iterations,
                dps_mean=1000.0 + index,
                dps_sd=25.0,
                dps_se=25.0 / (request.expected_iterations**0.5),
            )
            if success
            else GcsimResultSummary()
        ),
        cache_hit=status is GcsimFarmingEvaluationStatus.CACHED,
        engine_binding_sha256=identity.engine_binding_sha256,
        artifact_sha256=identity.artifact_sha256,
        source_config_sha256=identity.source_config_sha256,
        error="synthetic timeout" if status is GcsimFarmingEvaluationStatus.TIMEOUT else "",
    )


def _simulation_request(
    context_sha256: str,
    state: FullTeamProbeState,
    ordinal: int,
) -> FullTeamSimulationRequest:
    return FullTeamSimulationRequest(
        context_sha256=context_sha256,
        state=state,
        ordinal=ordinal,
        phase="test",
        round_index=0,
        parent_probe_keys=(),
        changed_wearer_ids=(),
        timeout_seconds=3.0,
    )


def _layouts():
    return {
        "furina": {
            "furina-default": GcsimFiveStarMainStatLayout(
                sands="hp%",
                goblet="hydro%",
                circlet="cr",
            ),
            "furina-em": GcsimFiveStarMainStatLayout(
                sands="em",
                goblet="hydro%",
                circlet="cd",
            ),
        },
        "bennett": {
            "bennett-default": GcsimFiveStarMainStatLayout(
                sands="er",
                goblet="pyro%",
                circlet="cr",
            ),
            "bennett-heal": GcsimFiveStarMainStatLayout(
                sands="er",
                goblet="hp%",
                circlet="heal",
            ),
        },
    }


def _candidate(
    wearer: str,
    set_key: str,
    layout_id: str,
    profile_id: str,
    *,
    offpiece: str = "",
) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=wearer,
            set_key=set_key,
            main_stat_layout_id=layout_id,
            offpiece_slot=offpiece,
        ),
        profile_id=profile_id,
    )


def _joint_state(
    *,
    furina_set: str = "goldentroupe",
    furina_profile: str = "baseline",
    furina_offpiece: str = "",
    bennett_set: str = "noblesseoblige",
    bennett_profile: str = "baseline",
    bennett_offpiece: str = "",
) -> FullTeamProbeState:
    return FullTeamProbeState(
        choices=(
            _candidate(
                "furina",
                furina_set,
                "furina-default",
                furina_profile,
                offpiece=furina_offpiece,
            ),
            _candidate(
                "bennett",
                bennett_set,
                "bennett-default",
                bennett_profile,
                offpiece=bennett_offpiece,
            ),
        )
    )


def _context(root: Path, *, trusted: bool = True) -> GcsimOptimizerEngineContext:
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / "gtt-gcsim.exe"
    artifact.write_bytes(b"engine")
    capabilities = tuple(
        GcsimArtifactSetCapability(
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
        for key, rarity in (
            ("goldentroupe", 5),
            ("noblesseoblige", 5),
            ("instructor", 4),
        )
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=capabilities,
    )
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(root),
        engine_version="v2.42.2",
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
