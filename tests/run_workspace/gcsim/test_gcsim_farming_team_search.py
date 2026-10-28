from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from run_workspace.gcsim import farming_team_search as team_search_module
from run_workspace.gcsim.farming_search import (
    CandidateEvaluation,
    FourPieceSetState,
    SearchSurvivor,
    SetProfileCandidate,
    SURVIVOR_NOVEL_BRANCH,
    SURVIVOR_UNCERTAIN,
)
from run_workspace.gcsim.farming_team_search import (
    TEAM_SEARCH_CANCELLED,
    TEAM_SEARCH_DEADLINE_REACHED,
    TEAM_SEARCH_DOMAIN_EXHAUSTED,
    TEAM_SEARCH_NO_SUCCESS,
    TEAM_SEARCH_POLICY_EXHAUSTED,
    TEAM_SEARCH_ROUND_LIMIT_REACHED,
    TEAM_SIM_FAILED,
    TEAM_SIM_CANCELLED,
    TEAM_SIM_PASSED,
    FullTeamCandidatePool,
    FullTeamComposerBudget,
    FullTeamComposerError,
    FullTeamComposerRequest,
    FullTeamProbeState,
    FullTeamSimulationMetrics,
    compose_full_team_four_piece_states,
)


CONTEXT_SHA = "a" * 64
INVESTMENT = "gcsim-v2.42.2-kqm-envelope-v1"


class GcsimFarmingTeamSearchTest(unittest.TestCase):
    def test_probe_and_physical_identity_are_deliberately_distinct(self) -> None:
        left = _candidate("furina", "goldentroupe", profile="focus/hp%")
        right = _candidate("furina", "goldentroupe", profile="focus/em")
        left_state = FullTeamProbeState((left,))
        right_state = FullTeamProbeState((right,))

        self.assertNotEqual(left_state.probe_key, right_state.probe_key)
        self.assertEqual(left_state.physical_key, right_state.physical_key)

    def test_candidate_pool_order_does_not_change_trace_or_winner(self) -> None:
        pools_a = (
            _pool("furina", ("weak", "strong"), heuristic=(10.0, 20.0)),
            _pool("bennett", ("noblesse", "instructor"), heuristic=(30.0, 5.0)),
        )
        pools_b = (
            FullTeamCandidatePool("furina", tuple(reversed(pools_a[0].survivors))),
            FullTeamCandidatePool("bennett", tuple(reversed(pools_a[1].survivors))),
        )
        budget = _budget(max_total=12, coordinate=4, pair=2)

        def score(state: FullTeamProbeState) -> float:
            sets = tuple(choice.state.set_key for choice in state.choices)
            return {
                ("weak", "noblesse"): 100.0,
                ("strong", "noblesse"): 120.0,
                ("weak", "instructor"): 80.0,
                ("strong", "instructor"): 90.0,
            }[sets]

        first = compose_full_team_four_piece_states(
            _request(pools_a, budget),
            _simulator(score),
        )
        second = compose_full_team_four_piece_states(
            _request(pools_b, budget),
            _simulator(score),
        )

        self.assertEqual(first.best_found.probe_key, second.best_found.probe_key)
        self.assertEqual(
            tuple(record.probe_key for record in first.records),
            tuple(record.probe_key for record in second.records),
        )
        self.assertEqual(first.request_sha256, second.request_sha256)
        self.assertEqual(
            first.candidate_domain_sha256,
            second.candidate_domain_sha256,
        )
        self.assertEqual(first.budget_sha256, second.budget_sha256)

    def test_result_freezes_budget_and_hashes_every_search_input_layer(self) -> None:
        pools = (
            _pool("furina", ("seta", "setb"), heuristic=(20.0, 10.0)),
            _pool("bennett", ("setc", "setd"), heuristic=(20.0, 10.0)),
        )
        budget = _budget(max_total=4, coordinate=2, pair=1)
        request = _request(pools, budget)
        simulator = _simulator(lambda _state: 100.0)

        original = compose_full_team_four_piece_states(request, simulator)
        changed_budget = compose_full_team_four_piece_states(
            replace(
                request,
                budget=replace(budget, max_total_evaluations=5),
            ),
            simulator,
        )
        changed_domain = compose_full_team_four_piece_states(
            _request(
                (
                    _pool(
                        "furina",
                        ("seta", "setb", "sete"),
                        heuristic=(20.0, 10.0, 5.0),
                    ),
                    pools[1],
                ),
                budget,
            ),
            simulator,
        )
        explicit_seed = FullTeamProbeState(
            tuple(pool.survivors[-1].evaluation.candidate for pool in pools)
        )
        changed_seeds = compose_full_team_four_piece_states(
            replace(request, explicit_seeds=(explicit_seed,)),
            simulator,
        )
        changed_context = compose_full_team_four_piece_states(
            replace(request, evaluation_context_sha256="b" * 64),
            simulator,
        )

        self.assertEqual(original.provenance_schema_version, 2)
        self.assertEqual(original.budget_snapshot, budget)
        self.assertLessEqual(
            original.requested_evaluations,
            original.budget_snapshot.max_total_evaluations,
        )
        for digest in (
            original.request_sha256,
            original.candidate_domain_sha256,
            original.budget_sha256,
        ):
            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, digest.casefold())
            self.assertTrue(all(character in "0123456789abcdef" for character in digest))

        self.assertNotEqual(original.budget_sha256, changed_budget.budget_sha256)
        self.assertNotEqual(original.request_sha256, changed_budget.request_sha256)
        self.assertEqual(
            original.candidate_domain_sha256,
            changed_budget.candidate_domain_sha256,
        )

        self.assertNotEqual(
            original.candidate_domain_sha256,
            changed_domain.candidate_domain_sha256,
        )
        self.assertNotEqual(original.request_sha256, changed_domain.request_sha256)
        self.assertEqual(original.budget_sha256, changed_domain.budget_sha256)

        self.assertEqual(
            original.candidate_domain_sha256,
            changed_seeds.candidate_domain_sha256,
        )
        self.assertEqual(original.budget_sha256, changed_seeds.budget_sha256)
        self.assertNotEqual(original.request_sha256, changed_seeds.request_sha256)

        self.assertEqual(
            original.candidate_domain_sha256,
            changed_context.candidate_domain_sha256,
        )
        self.assertEqual(original.budget_sha256, changed_context.budget_sha256)
        self.assertNotEqual(original.request_sha256, changed_context.request_sha256)

    def test_result_rejects_incoherent_terminal_trace_and_counters(self) -> None:
        pools = (_pool("furina", ("a", "b"), heuristic=(20.0, 10.0)),)
        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=2, coordinate=1, pair=0)),
            _simulator(
                lambda state: 200.0
                if state.choices[0].state.set_key == "b"
                else 100.0
            ),
        )
        forged_seed_request = replace(
            result.records[1].request,
            phase="seed",
            round_index=0,
            parent_probe_keys=(),
            changed_wearer_ids=(),
        )
        forged_seed_record = replace(
            result.records[1],
            request=forged_seed_request,
        )
        cases = (
            (
                "unknown status",
                {"status": "forged", "stop_reason": "forged"},
                "status",
            ),
            (
                "status mismatch",
                {"stop_reason": TEAM_SEARCH_CANCELLED},
                "must match",
            ),
            (
                "request count",
                {"requested_evaluations": 1},
                "record count",
            ),
            ("cache count", {"cache_hits": 1}, "cache_hits"),
            ("negative rounds", {"rounds_completed": -1}, "rounds_completed"),
            (
                "record order",
                {"records": tuple(reversed(result.records))},
                "ordinal order",
            ),
            (
                "seed phase budget",
                {"records": (result.records[0], forged_seed_record)},
                "seed records",
            ),
            ("beam", {"beam": ()}, "beam"),
            ("best", {"best_found": None}, "best_found"),
            ("finalists", {"physical_finalists": ()}, "physical_finalists"),
            ("negative elapsed", {"elapsed_seconds": -1.0}, "elapsed_seconds"),
            ("infinite elapsed", {"elapsed_seconds": float("inf")}, "elapsed_seconds"),
            ("NaN elapsed", {"elapsed_seconds": float("nan")}, "elapsed_seconds"),
        )
        for label, changes, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(FullTeamComposerError, message):
                    replace(result, **changes)

    def test_mixed_investment_signatures_fail_closed(self) -> None:
        pool = _pool("furina", ("seta", "setb"))
        changed = SearchSurvivor(
            evaluation=CandidateEvaluation(
                candidate=pool.survivors[1].evaluation.candidate,
                expected_dps=2.0,
                investment_signature="different",
            ),
            reasons=("test",),
        )
        request = _request(
            (FullTeamCandidatePool("furina", (pool.survivors[0], changed)),),
            _budget(),
        )

        with self.assertRaisesRegex(FullTeamComposerError, "investment signature"):
            compose_full_team_four_piece_states(request, _simulator(lambda _state: 1.0))

    def test_missing_or_misordered_wearer_pool_is_rejected(self) -> None:
        with self.assertRaisesRegex(FullTeamComposerError, "canonical order"):
            FullTeamComposerRequest(
                evaluation_context_sha256=CONTEXT_SHA,
                wearer_ids=("furina", "bennett"),
                candidate_pools=(
                    _pool("bennett", ("noblesse",)),
                    _pool("furina", ("goldentroupe",)),
                ),
                budget=_budget(),
            )

    def test_coordinate_move_finds_a_simple_full_team_improvement(self) -> None:
        pools = (
            _pool("furina", ("seta", "setb"), heuristic=(10.0, 5.0)),
            _pool("bennett", ("setc",), heuristic=(10.0,)),
        )

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=3, coordinate=2, pair=0)),
            _simulator(
                lambda state: 200.0
                if state.choices[0].state.set_key == "setb"
                else 100.0
            ),
        )

        self.assertEqual(result.best_found.request.state.choices[0].state.set_key, "setb")
        self.assertTrue(
            any(record.request.phase == "coordinate" for record in result.records)
        )

    def test_small_coordinate_budget_visits_selector_preserved_novel_branch(self) -> None:
        leader = _survivor(_candidate("furina", "leader"), heuristic=30.0)
        raw_second = _survivor(_candidate("furina", "rawsecond"), heuristic=20.0)
        novel = SearchSurvivor(
            evaluation=CandidateEvaluation(
                candidate=_candidate("furina", "unexpected", profile="focus/em"),
                expected_dps=5.0,
                investment_signature=INVESTMENT,
                standard_error=5.0,
                novelty_score=10.0,
                novelty_tags=("em-response",),
            ),
            reasons=(SURVIVOR_NOVEL_BRANCH,),
        )
        pools = (FullTeamCandidatePool("furina", (leader, raw_second, novel)),)

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=2, coordinate=1, pair=0)),
            _simulator(
                lambda state: 200.0
                if state.choices[0].state.set_key == "unexpected"
                else 100.0
            ),
        )

        self.assertEqual(
            result.best_found.request.state.choices[0].state.set_key,
            "unexpected",
        )
        self.assertTrue(
            any(
                tag == "source-novelty/furina/em-response"
                for tag in result.best_found.structural_tags
            )
        )

    def test_uncertain_tail_does_not_bury_novel_branch_in_bounded_frontier(self) -> None:
        leader = _survivor(_candidate("furina", "leader"), heuristic=100.0)
        uncertain = tuple(
            SearchSurvivor(
                evaluation=CandidateEvaluation(
                    candidate=_candidate("furina", f"uncertain{index}"),
                    expected_dps=99.0 - index,
                    investment_signature=INVESTMENT,
                    standard_error=10.0,
                ),
                reasons=(SURVIVOR_UNCERTAIN,),
            )
            for index in range(3)
        )
        novel = SearchSurvivor(
            evaluation=CandidateEvaluation(
                candidate=_candidate(
                    "furina",
                    "novel",
                    profile="focus/em",
                ),
                expected_dps=1.0,
                investment_signature=INVESTMENT,
                standard_error=1.0,
                novelty_score=10.0,
                novelty_tags=("nonlinear",),
            ),
            reasons=(SURVIVOR_NOVEL_BRANCH,),
        )
        pool = FullTeamCandidatePool("furina", (leader, *uncertain, novel))

        result = compose_full_team_four_piece_states(
            _request((pool,), _budget(max_total=2, coordinate=1, pair=0)),
            _simulator(lambda _state: 100.0),
        )

        self.assertEqual(
            tuple(
                record.request.state.choices[0].state.set_key
                for record in result.records
            ),
            ("leader", "novel"),
        )

    def test_small_coordinate_budget_rotates_across_wearers_between_rounds(self) -> None:
        first_pool = _pool(
            "furina",
            ("leader", "alternative"),
            heuristic=(100.0, 90.0),
        )
        second_leader = _survivor(
            _candidate("bennett", "baseline"),
            heuristic=100.0,
        )
        second_novel = SearchSurvivor(
            evaluation=CandidateEvaluation(
                candidate=_candidate("bennett", "novel", profile="focus/em"),
                expected_dps=1.0,
                investment_signature=INVESTMENT,
                standard_error=1.0,
                novelty_score=10.0,
                novelty_tags=("nonlinear",),
            ),
            reasons=(SURVIVOR_NOVEL_BRANCH,),
        )
        pools = (
            first_pool,
            FullTeamCandidatePool("bennett", (second_leader, second_novel)),
        )

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=3, coordinate=1, pair=0)),
            _simulator(
                lambda state: 1000.0
                if state.choices[1].state.set_key == "novel"
                else (
                    200.0
                    if state.choices[0].state.set_key == "leader"
                    else 100.0
                )
            ),
        )

        self.assertEqual(
            tuple(
                tuple(choice.state.set_key for choice in record.request.state.choices)
                for record in result.records
            ),
            (
                ("leader", "baseline"),
                ("alternative", "baseline"),
                ("leader", "novel"),
            ),
        )
        self.assertEqual(result.best_found.request.state.choices[1].state.set_key, "novel")

    def test_pair_move_escapes_a_synthetic_local_minimum(self) -> None:
        pools = (
            _pool("furina", ("a", "b"), heuristic=(20.0, 10.0)),
            _pool("bennett", ("c", "d"), heuristic=(20.0, 10.0)),
        )

        def score(state: FullTeamProbeState) -> float:
            sets = tuple(choice.state.set_key for choice in state.choices)
            return {
                ("a", "c"): 100.0,
                ("b", "c"): 90.0,
                ("a", "d"): 90.0,
                ("b", "d"): 140.0,
            }[sets]

        result = compose_full_team_four_piece_states(
            _request(
                pools,
                _budget(
                    max_total=4,
                    coordinate=2,
                    pair=1,
                    beam_width=2,
                ),
            ),
            _simulator(score),
        )

        self.assertEqual(
            tuple(choice.state.set_key for choice in result.best_found.request.state.choices),
            ("b", "d"),
        )
        self.assertEqual(result.best_found.request.phase, "pair")

    def test_small_pair_budget_rotates_across_wearer_pairs_between_rounds(self) -> None:
        pools = (
            _pool("furina", ("f0", "f1", "f2"), heuristic=(30.0, 20.0, 10.0)),
            _pool("bennett", ("b0", "b1", "b2"), heuristic=(30.0, 20.0, 10.0)),
            _pool("xiangling", ("x0", "novel"), heuristic=(30.0, 1.0)),
        )
        budget = replace(
            _budget(max_total=3, coordinate=0, pair=1, beam_width=1),
            max_rounds=2,
        )

        result = compose_full_team_four_piece_states(
            _request(pools, budget),
            _simulator(
                lambda state: 1000.0
                if state.choices[2].state.set_key == "novel"
                else (
                    200.0
                    if tuple(choice.state.set_key for choice in state.choices)
                    == ("f0", "b0", "x0")
                    else 100.0
                )
            ),
        )

        self.assertEqual(
            tuple(record.request.changed_wearer_ids for record in result.records),
            ((), ("furina", "bennett"), ("furina", "xiangling")),
        )
        self.assertEqual(result.best_found.request.state.choices[2].state.set_key, "novel")

    def test_duplicate_sets_are_simulated_and_not_collapsed(self) -> None:
        pools = (
            _pool("furina", ("buff", "personal"), heuristic=(20.0, 10.0)),
            _pool("bennett", ("buff", "personal"), heuristic=(20.0, 10.0)),
        )
        observed: list[tuple[str, ...]] = []

        def score(state: FullTeamProbeState) -> float:
            sets = tuple(choice.state.set_key for choice in state.choices)
            observed.append(sets)
            # Synthetic non-stacking penalty makes one personal set optimal.
            return 80.0 if sets == ("buff", "buff") else 110.0

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=4, coordinate=2, pair=1)),
            _simulator(score),
        )

        self.assertIn(("buff", "buff"), observed)
        self.assertNotEqual(
            tuple(choice.state.set_key for choice in result.best_found.request.state.choices),
            ("buff", "buff"),
        )
        duplicate_record = next(
            record
            for record in result.records
            if tuple(choice.state.set_key for choice in record.request.state.choices)
            == ("buff", "buff")
        )
        self.assertIn("duplicate-set/buff/2", duplicate_record.structural_tags)

    def test_same_physical_state_with_two_profiles_yields_one_finalist(self) -> None:
        first = _survivor(
            _candidate("furina", "goldentroupe", profile="focus/hp%"),
            heuristic=20.0,
        )
        second = _survivor(
            _candidate("furina", "goldentroupe", profile="focus/em"),
            heuristic=10.0,
        )
        pools = (FullTeamCandidatePool("furina", (first, second)),)

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=2, coordinate=1, pair=0)),
            _simulator(
                lambda state: 120.0
                if state.choices[0].profile_id == "focus/em"
                else 100.0
            ),
        )

        self.assertEqual(result.requested_evaluations, 2)
        self.assertEqual(len(result.physical_finalists), 1)
        self.assertEqual(
            result.physical_finalists[0].choices[0].set_key,
            "goldentroupe",
        )

    def test_unique_state_is_never_requested_twice_and_cache_hits_consume_budget(self) -> None:
        pools = (
            _pool("furina", ("a", "b", "c"), heuristic=(30.0, 20.0, 10.0)),
            _pool("bennett", ("d", "e"), heuristic=(20.0, 10.0)),
        )
        seen = set()

        def simulator(requests):
            outcomes = {}
            for item in requests:
                self.assertNotIn(item.state.probe_key, seen)
                seen.add(item.state.probe_key)
                outcomes[item.state.probe_key] = FullTeamSimulationMetrics(
                    status=TEAM_SIM_PASSED,
                    dps_mean=100.0 + item.ordinal,
                    dps_se=1.0,
                    iterations=10,
                    cache_hit=True,
                )
            return outcomes

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=5, coordinate=3, pair=2)),
            simulator,
        )

        self.assertEqual(result.requested_evaluations, 5)
        self.assertEqual(result.cache_hits, 5)
        self.assertEqual(len(seen), 5)

    def test_cancel_returns_best_already_evaluated_state(self) -> None:
        pools = (_pool("furina", ("a", "b")),)
        cancelled = {"value": False}

        def simulator(requests):
            cancelled["value"] = True
            return {
                item.state.probe_key: FullTeamSimulationMetrics(
                    status=TEAM_SIM_PASSED,
                    dps_mean=123.0,
                    dps_se=None,
                    iterations=10,
                )
                for item in requests
            }

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=2, coordinate=1, pair=0)),
            simulator,
            is_cancelled=lambda: cancelled["value"],
        )

        self.assertEqual(result.status, TEAM_SEARCH_CANCELLED)
        self.assertIsNotNone(result.best_found)
        self.assertIsNone(result.best_found.metrics.dps_se)

    def test_simulator_side_cancel_is_terminal_without_external_event(self) -> None:
        pools = (_pool("furina", ("a", "b")),)

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=2, coordinate=1, pair=0)),
            lambda requests: {
                item.state.probe_key: FullTeamSimulationMetrics(
                    status=TEAM_SIM_CANCELLED,
                    error="adapter cancelled directly",
                )
                for item in requests
            },
        )

        self.assertEqual(result.status, TEAM_SEARCH_CANCELLED)
        self.assertEqual(result.stop_reason, TEAM_SEARCH_CANCELLED)
        self.assertIsNone(result.best_found)

    def test_pre_cancel_does_not_call_simulator_and_preserves_terminal_status(self) -> None:
        pools = (_pool("furina", ("a",)),)
        calls = []

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=1, coordinate=0, pair=0)),
            lambda requests: calls.append(requests) or {},
            is_cancelled=lambda: True,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, TEAM_SEARCH_CANCELLED)
        self.assertEqual(result.stop_reason, TEAM_SEARCH_CANCELLED)
        self.assertEqual(result.requested_evaluations, 0)
        self.assertIsNone(result.best_found)

    def test_pre_seed_deadline_preserves_deadline_status_without_fake_zero(self) -> None:
        pools = (_pool("furina", ("a",)),)
        times = iter((0.0, 1000.0, 1000.0))
        calls = []

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=1, coordinate=0, pair=0)),
            lambda requests: calls.append(requests) or {},
            clock=lambda: next(times, 1000.0),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, TEAM_SEARCH_DEADLINE_REACHED)
        self.assertEqual(result.stop_reason, TEAM_SEARCH_DEADLINE_REACHED)
        self.assertIsNone(result.best_found)

    def test_preprocessing_consumes_the_same_hard_deadline(self) -> None:
        pools = (_pool("furina", ("a",)),)
        request = _request(pools, _budget(max_total=1, coordinate=0, pair=0))
        now = {"value": 0.0}
        calls = []
        original_validation = team_search_module._validated_sorted_pools

        def delayed_validation(value):
            validated = original_validation(value)
            now["value"] = request.budget.max_seconds + 1.0
            return validated

        base_simulator = _simulator(lambda _state: 100.0)

        def simulator(requests):
            calls.append(requests)
            return base_simulator(requests)

        with patch.object(
            team_search_module,
            "_validated_sorted_pools",
            delayed_validation,
        ):
            result = compose_full_team_four_piece_states(
                request,
                simulator,
                clock=lambda: now["value"],
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, TEAM_SEARCH_DEADLINE_REACHED)
        self.assertEqual(result.elapsed_seconds, request.budget.max_seconds + 1.0)
        self.assertEqual(result.requested_evaluations, 0)

    def test_failed_simulation_is_not_converted_into_zero_dps(self) -> None:
        pools = (_pool("furina", ("a",)),)

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=1, coordinate=0, pair=0)),
            lambda requests: {
                item.state.probe_key: FullTeamSimulationMetrics(
                    status=TEAM_SIM_FAILED,
                    error="synthetic failure",
                )
                for item in requests
            },
        )

        self.assertEqual(result.status, TEAM_SEARCH_NO_SUCCESS)
        self.assertIsNone(result.best_found)
        self.assertEqual(result.records[0].metrics.dps_mean, None)

    def test_batch_simulator_must_return_exactly_the_requested_keys(self) -> None:
        pools = (_pool("furina", ("a",)),)
        with self.assertRaisesRegex(FullTeamComposerError, "mismatched probe keys"):
            compose_full_team_four_piece_states(
                _request(pools, _budget(max_total=1, coordinate=0, pair=0)),
                lambda _requests: {},
            )

    def test_zero_move_budget_is_not_reported_as_domain_exhaustion(self) -> None:
        pools = (_pool("furina", ("a", "b")),)
        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=8, coordinate=0, pair=0)),
            _simulator(lambda _state: 100.0),
        )

        self.assertEqual(result.status, TEAM_SEARCH_POLICY_EXHAUSTED)
        self.assertEqual(result.requested_evaluations, 1)

    def test_round_limit_does_not_claim_completion_with_unseen_states(self) -> None:
        pools = (_pool("furina", ("a", "b", "c")),)
        budget = replace(
            _budget(max_total=8, coordinate=1, pair=0),
            max_rounds=1,
        )
        result = compose_full_team_four_piece_states(
            _request(pools, budget),
            _simulator(lambda _state: 100.0),
        )

        self.assertEqual(result.status, TEAM_SEARCH_ROUND_LIMIT_REACHED)
        self.assertEqual(result.requested_evaluations, 2)

    def test_domain_exhaustion_requires_no_unseen_neighbor(self) -> None:
        pools = (_pool("furina", ("a",)),)
        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=8, coordinate=2, pair=0)),
            _simulator(lambda _state: 100.0),
        )

        self.assertEqual(result.status, TEAM_SEARCH_DOMAIN_EXHAUSTED)
        self.assertEqual(result.requested_evaluations, 1)

    def test_unseen_pair_behind_failed_coordinates_is_policy_exhaustion(self) -> None:
        pools = (
            _pool("furina", ("a", "b")),
            _pool("bennett", ("c", "d")),
        )

        def simulator(requests):
            outcomes = {}
            for item in requests:
                sets = tuple(choice.state.set_key for choice in item.state.choices)
                outcomes[item.state.probe_key] = (
                    FullTeamSimulationMetrics(
                        status=TEAM_SIM_PASSED,
                        dps_mean=100.0,
                        dps_se=1.0,
                        iterations=10,
                    )
                    if sets == ("a", "c")
                    else FullTeamSimulationMetrics(
                        status=TEAM_SIM_FAILED,
                        error="synthetic valley",
                    )
                )
            return outcomes

        result = compose_full_team_four_piece_states(
            _request(pools, _budget(max_total=8, coordinate=2, pair=0)),
            simulator,
        )

        visited = {
            tuple(choice.state.set_key for choice in record.request.state.choices)
            for record in result.records
        }
        self.assertEqual(result.status, TEAM_SEARCH_POLICY_EXHAUSTED)
        self.assertEqual(visited, {("a", "c"), ("b", "c"), ("a", "d")})
        self.assertNotIn(("b", "d"), visited)

    def test_duplicate_child_records_one_coherent_canonical_parent_edge(self) -> None:
        pools = (
            _pool("furina", ("a", "b")),
            _pool("bennett", ("c", "d")),
        )
        first = FullTeamProbeState(
            tuple(pool.survivors[0].evaluation.candidate for pool in pools)
        )
        second = FullTeamProbeState(
            tuple(pool.survivors[1].evaluation.candidate for pool in pools)
        )
        budget = replace(
            _budget(max_total=5, coordinate=3, pair=0, beam_width=2),
            max_seed_evaluations=2,
            max_rounds=1,
        )
        request = replace(
            _request(pools, budget),
            explicit_seeds=(first, second),
        )

        result = compose_full_team_four_piece_states(
            request,
            _simulator(lambda _state: 100.0),
        )

        records_by_key = {record.probe_key: record for record in result.records}
        coordinate_records = tuple(
            record for record in result.records if record.request.phase == "coordinate"
        )
        self.assertEqual(len(coordinate_records), 2)
        for record in coordinate_records:
            self.assertEqual(len(record.request.parent_probe_keys), 1)
            parent = records_by_key[record.request.parent_probe_keys[0]]
            actual_changed = tuple(
                wearer
                for wearer, parent_choice, child_choice in zip(
                    request.wearer_ids,
                    parent.request.state.choices,
                    record.request.state.choices,
                    strict=True,
                )
                if parent_choice.key != child_choice.key
            )
            self.assertEqual(record.request.changed_wearer_ids, actual_changed)

    def test_invalid_passed_metrics_fail_closed(self) -> None:
        with self.assertRaisesRegex(FullTeamComposerError, "positive iteration"):
            FullTeamSimulationMetrics(
                status=TEAM_SIM_PASSED,
                dps_mean=100.0,
                iterations=0,
            )


def _candidate(
    wearer: str,
    set_key: str,
    *,
    profile: str = "balanced",
    layout: str = "hp-hydro-crit",
    offpiece: str = "",
) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=wearer,
            set_key=set_key,
            main_stat_layout_id=layout,
            offpiece_slot=offpiece,
        ),
        profile_id=profile,
    )


def _survivor(
    candidate: SetProfileCandidate,
    *,
    heuristic: float,
    signature: str = INVESTMENT,
) -> SearchSurvivor:
    return SearchSurvivor(
        evaluation=CandidateEvaluation(
            candidate=candidate,
            expected_dps=heuristic,
            investment_signature=signature,
            standard_error=1.0,
        ),
        reasons=("test",),
    )


def _pool(
    wearer: str,
    set_keys: tuple[str, ...],
    *,
    heuristic: tuple[float, ...] | None = None,
) -> FullTeamCandidatePool:
    values = heuristic or tuple(float(len(set_keys) - index) for index in range(len(set_keys)))
    return FullTeamCandidatePool(
        wearer_id=wearer,
        survivors=tuple(
            _survivor(_candidate(wearer, set_key), heuristic=value)
            for set_key, value in zip(set_keys, values, strict=True)
        ),
    )


def _budget(
    *,
    max_total: int = 8,
    coordinate: int = 4,
    pair: int = 2,
    beam_width: int = 3,
) -> FullTeamComposerBudget:
    return FullTeamComposerBudget(
        max_total_evaluations=max_total,
        max_seed_evaluations=1,
        max_rounds=2,
        max_coordinate_evaluations_per_round=coordinate,
        max_pair_evaluations_per_round=pair,
        pair_frontier_per_wearer=2,
        beam_width=beam_width,
        beam_top_slots=1,
        beam_uncertain_slots=1 if beam_width >= 2 else 0,
        beam_novelty_slots=1 if beam_width >= 3 else 0,
        max_physical_finalists=5,
        confidence_sigma=1.0,
        relative_uncertainty_margin=0.01,
        max_seconds=60.0,
        per_evaluation_timeout_seconds=10.0,
    )


def _request(
    pools: tuple[FullTeamCandidatePool, ...],
    budget: FullTeamComposerBudget,
) -> FullTeamComposerRequest:
    return FullTeamComposerRequest(
        evaluation_context_sha256=CONTEXT_SHA,
        wearer_ids=tuple(pool.wearer_id for pool in pools),
        candidate_pools=pools,
        budget=budget,
    )


def _simulator(score):
    def run(requests):
        return {
            item.state.probe_key: FullTeamSimulationMetrics(
                status=TEAM_SIM_PASSED,
                dps_mean=float(score(item.state)),
                dps_se=1.0,
                iterations=10,
            )
            for item in requests
        }

    return run


if __name__ == "__main__":
    unittest.main()
