from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from run_workspace.gcsim.farming_team_search import (
    TEAM_SIM_PASSED,
    FullTeamSimulationMetrics,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerTargetPackageKind,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_candidates import (
    build_gcsim_optimizer_theoretical_anytime_candidate_domain,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_race import (
    GcsimOptimizerTheoreticalAnytimeRaceError,
    GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    GcsimOptimizerTheoreticalAnytimeRacePlan,
    GcsimOptimizerTheoreticalAnytimeRaceSession,
    GcsimOptimizerTheoreticalAnytimeRaceStatus,
    _retain_proposal_diversity,
    _select_physical_finalists,
)
from run_workspace.gcsim.optimizer_theoretical_packages import (
    gcsim_theoretical_pair_package_key,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_theoretical_anytime_candidates import (
    _context,
    _pair,
    _profiles,
    _profiles_with_em_focus,
    _set_impact,
    _wide_pair_packages,
    _wearers,
)


class GcsimOptimizerTheoreticalAnytimeRaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = _context()
        self.wearers = _wearers()
        self.domain = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=self.context,
                wearers=self.wearers,
                response_profiles=_profiles(self.wearers),
                set_impact=_set_impact(
                    self.context,
                    self.wearers,
                ),
            )
        )

    def test_runs_package_main_refinement_then_32_with_caps_and_finalists(
        self,
    ) -> None:
        factory = _ScriptedSimulatorFactory()
        progress = []

        first = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            progress_callback=lambda tier, completed, total, hits, leader: (
                progress.append(
                    (
                        tier,
                        completed,
                        total,
                        hits,
                        None
                        if leader is None
                        else leader.proposal.proposal_sha256,
                    )
                )
            ),
            enable_cache=False,
            simulator_factory=factory,
        ).run()

        self.assertEqual(
            [call["fidelity"].iterations for call in factory.calls],
            [8, 8, 8, 32],
        )
        self.assertEqual(len(factory.instances[0].requests), 64)
        self.assertLessEqual(len(factory.instances[1].requests), 384)
        self.assertLessEqual(len(factory.instances[2].requests), 384)
        self.assertLessEqual(len(factory.instances[3].requests), 16)
        self.assertEqual(
            [trace.tier.tier_id for trace in first.tier_traces],
            [
                "package_screen_8",
                "main_coordinate_8",
                "main_combine_8",
                "refine_32",
            ],
        )
        self.assertEqual(
            factory.calls[0]["layout_catalog"],
            self.domain.layout_catalog,
        )
        self.assertIs(
            factory.calls[0]["profile_bank"],
            self.domain.profile_bank,
        )
        for instance, tier_id in zip(
            factory.instances,
            (
                "package_screen_8",
                "main_coordinate_8",
                "main_combine_8",
                "refine_32",
            ),
            strict=True,
        ):
            tier_progress = [row for row in progress if row[0] == tier_id]
            self.assertEqual(
                [(row[1], row[2]) for row in tier_progress],
                [
                    (completed, len(instance.requests))
                    for completed in range(len(instance.requests) + 1)
                ],
            )
        self.assertTrue(
            all(row[4] is not None for row in progress if row[1] > 0)
        )
        self.assertEqual(
            first.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED,
        )
        self.assertEqual(len(first.tier_traces), 4)
        self.assertGreater(len(first.physical_finalists), 0)
        self.assertLessEqual(len(first.physical_finalists), 6)
        self.assertEqual(
            len({item.key for item in first.physical_finalists}),
            len(first.physical_finalists),
        )
        self.assertEqual(
            len(
                {
                    tuple(choice.set_key for choice in item.choices)
                    for item in first.physical_finalists
                }
            ),
            len(first.physical_finalists),
        )
        self.assertEqual(
            tuple(
                item.metrics.dps_mean
                for item in first.finalist_evaluations
            ),
            tuple(
                sorted(
                    (
                        item.metrics.dps_mean
                        for item in first.finalist_evaluations
                    ),
                    reverse=True,
                )
            ),
        )
        self.assertTrue(
            all(
                item.tier_iterations == 32
                for item in first.finalist_evaluations
            )
        )
        repeated = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            enable_cache=False,
            simulator_factory=_ScriptedSimulatorFactory(),
        ).run()
        self.assertEqual(
            first.evidence_sha256,
            repeated.evidence_sha256,
        )

    def test_quick_tier_reserves_local_package_neighbors_before_bounded_audit(
        self,
    ) -> None:
        package_keys = tuple(f"set{index:02d}" for index in range(39))
        context = _context(modeled_keys=package_keys)
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=_profiles(self.wearers),
            set_impact=_set_impact(context, self.wearers),
        )

        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=context,
            domain=domain,
            enable_cache=False,
            simulator_factory=_ScriptedSimulatorFactory(),
        ).run()

        quick_rows = result.tier_traces[0].evaluations
        self.assertEqual(len(quick_rows), 64)
        for wearer_index, pool in enumerate(domain.wearer_pools):
            self.assertEqual(len(pool.retained_package_keys), 39)
            self.assertEqual(len(pool.anchor_package_keys), 39)
            self.assertEqual(
                len(pool.unscreened_retained_package_keys),
                0,
            )
            measured = {
                row.proposal.state.choices[
                    wearer_index
                ].state.set_key
                for row in quick_rows
            }
            ranked_anchors = sorted(
                (
                    item
                    for item in pool.alternatives
                    if item.package_anchor
                ),
                key=lambda item: (
                    -item.score,
                    item.package_key,
                    item.candidate.key,
                ),
            )
            expected_neighbors = {
                item.package_key for item in ranked_anchors[:7]
            }
            self.assertTrue(expected_neighbors.issubset(measured))
            self.assertLess(len(measured), len(pool.anchor_package_keys))
        self.assertTrue(
            any(
                "package_coordinate_neighbor"
                in row.proposal.diversity_labels
                for row in quick_rows
            )
        )

    def test_main_refinement_compares_layouts_inside_same_package_signature(
        self,
    ) -> None:
        factory = _ScriptedSimulatorFactory()
        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            enable_cache=False,
            simulator_factory=factory,
        ).run()

        package_seeds = result.tier_traces[0].selected_proposal_sha256
        seed_rows = {
            row.proposal.proposal_sha256: row
            for row in result.tier_traces[0].evaluations
        }
        refined_signatures = {
            tuple(
                choice.state.set_key
                for choice in seed_rows[proposal_id].proposal.state.choices
            )
            for proposal_id in package_seeds
        }
        coordinate_rows = result.tier_traces[1].evaluations
        for signature in refined_signatures:
            same_signature = tuple(
                row
                for row in coordinate_rows
                if tuple(
                    choice.state.set_key
                    for choice in row.proposal.state.choices
                )
                == signature
            )
            self.assertTrue(same_signature)
            for wearer_index, pool in enumerate(self.domain.wearer_pools):
                self.assertEqual(
                    {
                        choice.state.main_stat_layout_id
                        for row in same_signature
                        for choice in (row.proposal.state.choices[wearer_index],)
                    },
                    {layout_id for layout_id, _layout in pool.layouts},
                )

    def test_combination_stage_can_join_two_individually_better_mains(self) -> None:
        target_layouts = (
            self.domain.wearer_pools[0].layouts[-1][0],
            self.domain.wearer_pools[1].layouts[-1][0],
        )
        factory = _LayoutScoringSimulatorFactory(target_layouts)

        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            enable_cache=False,
            simulator_factory=factory,
        ).run()

        self.assertTrue(result.physical_finalists)
        best = result.physical_finalists[0]
        self.assertEqual(best.choices[0].main_stat_layout_id, target_layouts[0])
        self.assertEqual(best.choices[1].main_stat_layout_id, target_layouts[1])

    def test_quick_cap_never_replaces_balanced_anchor_with_focus_em(self) -> None:
        context = _context(
            modeled_keys=(
                "goldentroupe",
                "tenacity",
                "vourukasha",
                "obsidian",
                "scroll",
                "noblesse",
            )
        )
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=_profiles_with_em_focus(self.wearers),
            set_impact=_set_impact(
                context,
                self.wearers,
                score_by_key={"goldentroupe": 100_000.0},
            ),
        )

        quick = _retain_proposal_diversity(
            domain.proposals,
            limit=64,
        )
        self.assertEqual(len(quick), 64)
        for wearer_index, pool in enumerate(domain.wearer_pools):
            anchors = tuple(
                item for item in pool.alternatives
                if item.package_anchor
            )
            for anchor in anchors:
                matching = tuple(
                    proposal.state.choices[wearer_index]
                    for proposal in quick
                    if proposal.state.choices[
                        wearer_index
                    ].state.set_key == anchor.package_key
                )
                self.assertTrue(matching)
                self.assertIn(
                    anchor.candidate.key,
                    {choice.key for choice in matching},
                )

        golden_troupe_focus = tuple(
            item
            for item in domain.wearer_pools[0].alternatives
            if item.package_key == "goldentroupe"
            and item.profile_id.endswith("_focus_em")
        )
        self.assertTrue(golden_troupe_focus)
        golden_troupe_anchor = next(
            item
            for item in domain.wearer_pools[0].alternatives
            if item.package_key == "goldentroupe"
            and item.package_anchor
        )
        self.assertIn(
            golden_troupe_anchor.candidate.key,
            {
                proposal.state.choices[0].key
                for proposal in quick
            },
        )

    def test_quick_cap_gives_packages_fair_witness_ranks(self) -> None:
        context = _context()
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=_profiles_with_em_focus(self.wearers),
            set_impact=_set_impact(context, self.wearers),
        )

        quick = _retain_proposal_diversity(
            domain.proposals,
            limit=64,
        )
        for wearer_index, pool in enumerate(domain.wearer_pools):
            for package_key in domain.package_keys:
                screened = tuple(
                    item
                    for proposal in quick
                    for item in (proposal.state.choices[wearer_index],)
                    if item.state.set_key == package_key
                )
                self.assertGreaterEqual(
                    len({item.state.main_stat_layout_id for item in screened}),
                    3,
                )
                self.assertTrue(
                    any(
                        item.profile_id.endswith("_balanced")
                        for item in screened
                    )
                )

    def test_wide_two_plus_two_domain_shortlists_without_run_failure(
        self,
    ) -> None:
        set_keys = tuple(f"set{index:02d}" for index in range(13))
        context = _context(modeled_keys=set_keys)
        packages = _wide_pair_packages(context, set_keys)
        self.assertEqual(len(packages), 78)
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=_profiles_with_em_focus(self.wearers),
            set_impact=_set_impact(
                context,
                self.wearers,
                packages=packages,
            ),
            two_plus_two_packages=packages,
        )

        for pool in domain.wearer_pools:
            self.assertEqual(len(pool.retained_package_keys), 78)
            self.assertEqual(len(pool.anchor_package_keys), 30)
            self.assertEqual(
                len(pool.unscreened_retained_package_keys),
                48,
            )

        quick = _retain_proposal_diversity(
            domain.proposals,
            limit=64,
        )
        self.assertEqual(len(quick), 64)
        for wearer_index, pool in enumerate(domain.wearer_pools):
            screened_keys = {
                proposal.state.choices[wearer_index].key
                for proposal in quick
            }
            self.assertTrue(
                {
                    item.candidate.key
                    for item in pool.alternatives
                    if item.package_anchor
                }.issubset(screened_keys)
            )

        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=context,
            domain=domain,
            two_plus_two_packages=packages,
            enable_cache=False,
            simulator_factory=_ScriptedSimulatorFactory(),
        ).run()
        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED,
        )
        self.assertEqual(
            len(result.tier_traces[0].evaluations),
            64,
        )

    def test_duplicate_package_signature_keeps_stronger_stat_layout(
        self,
    ) -> None:
        by_signature = {}
        duplicate_pair = None
        for proposal in self.domain.proposals:
            signature = tuple(
                choice.state.set_key for choice in proposal.state.choices
            )
            previous = by_signature.setdefault(signature, proposal)
            if previous.state.probe_key != proposal.state.probe_key:
                duplicate_pair = (previous, proposal)
                break
        self.assertIsNotNone(duplicate_pair)
        weaker, stronger = duplicate_pair
        context_sha256 = "f" * 64
        rows = tuple(
            GcsimOptimizerTheoreticalAnytimeRaceEvaluation(
                tier_id="refine_32",
                tier_iterations=32,
                proposal_ordinal=index,
                proposal=proposal,
                evaluation_context_sha256=context_sha256,
                metrics=FullTeamSimulationMetrics(
                    status=TEAM_SIM_PASSED,
                    dps_mean=dps,
                    dps_se=1.0,
                    iterations=32,
                    cache_hit=False,
                ),
            )
            for index, (proposal, dps) in enumerate(
                ((weaker, 100.0), (stronger, 200.0))
            )
        )

        finalists = _select_physical_finalists(
            rows,
            limit=6,
            minimum=1,
            confidence_sigma=2.0,
            relative_margin=0.0075,
        )

        self.assertEqual(len(finalists), 1)
        self.assertIs(finalists[0].proposal, stronger)

    def test_progress_cancellation_stops_before_balanced_tier(self) -> None:
        factory = _ScriptedSimulatorFactory()
        holder = {}

        def on_progress(
            tier,
            completed,
            _total,
            _cache_hits,
            _leader,
        ) -> None:
            if tier == "package_screen_8" and completed == 1:
                holder["session"].cancel()

        session = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            progress_callback=on_progress,
            enable_cache=False,
            simulator_factory=factory,
        )
        holder["session"] = session

        result = session.run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus.CANCELLED,
        )
        self.assertEqual(
            [call["fidelity"].iterations for call in factory.calls],
            [8],
        )
        self.assertTrue(factory.instances[0].cancelled)
        self.assertFalse(result.physical_finalists)
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeRaceError,
            "one-shot",
        ):
            session.run()

    def test_progress_cache_hits_are_cumulative_for_non_leaders(self) -> None:
        progress = []
        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=self.domain,
            progress_callback=lambda tier, completed, total, hits, leader: (
                progress.append(
                    (
                        tier,
                        completed,
                        total,
                        hits,
                        None
                        if leader is None
                        else leader.proposal.proposal_sha256,
                    )
                )
            ),
            enable_cache=False,
            simulator_factory=_CachedNonLeaderSimulatorFactory(),
        ).run()

        self.assertEqual(
            result.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED,
        )
        for trace in result.tier_traces:
            tier = trace.tier.tier_id
            rows = [item for item in progress if item[0] == tier]
            hits = [item[3] for item in rows]
            self.assertEqual(hits, sorted(hits))
            self.assertEqual(hits[0], 0)
            self.assertEqual(hits[-1], 1)
            self.assertTrue(trace.evaluations[1].metrics.cache_hit)
            self.assertFalse(trace.evaluations[0].metrics.cache_hit)
            self.assertGreater(
                trace.evaluations[0].dps_mean,
                trace.evaluations[1].dps_mean,
            )
            self.assertEqual(rows[1][4], rows[2][4])
            self.assertEqual(rows[2][3], 1)

    def test_two_plus_two_mapping_is_frozen_into_both_tiers(self) -> None:
        pair_ab = _pair(self.context, "alpha", "beta")
        pair_bg = _pair(self.context, "beta", "gamma")
        packages = {
            gcsim_theoretical_pair_package_key(pair_bg): pair_bg,
            gcsim_theoretical_pair_package_key(pair_ab): pair_ab,
        }
        pair_domain = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=self.context,
                wearers=self.wearers,
                response_profiles=_profiles(self.wearers),
                set_impact=_set_impact(
                    self.context,
                    self.wearers,
                    packages=packages,
                ),
                two_plus_two_packages=packages,
            )
        )
        factory = _ScriptedSimulatorFactory()

        result = GcsimOptimizerTheoreticalAnytimeRaceSession(
            "prepared theoretical config",
            engine_context=self.context,
            domain=pair_domain,
            two_plus_two_packages=packages,
            enable_cache=False,
            simulator_factory=factory,
        ).run()

        self.assertEqual(
            pair_domain.package_kind,
            GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO,
        )
        self.assertTrue(result.physical_finalists)
        self.assertTrue(
            all(
                tuple(call["two_plus_two_packages"])
                == tuple(sorted(packages))
                for call in factory.calls
            )
        )
        quick_rows = result.tier_traces[0].evaluations
        for wearer_index, pool in enumerate(pair_domain.wearer_pools):
            for anchor in (
                item for item in pool.alternatives
                if item.package_anchor
            ):
                self.assertIn(
                    anchor.candidate.key,
                    {
                        row.proposal.state.choices[wearer_index].key
                        for row in quick_rows
                    },
                )

    def test_plan_and_engine_binding_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeRaceError,
            "package-8/64",
        ):
            GcsimOptimizerTheoreticalAnytimeRacePlan(
                tiers=(
                    replace(
                        GcsimOptimizerTheoreticalAnytimeRacePlan()
                        .tiers[0],
                        iterations=9,
                    ),
                    GcsimOptimizerTheoreticalAnytimeRacePlan().tiers[1],
                )
            )

        drifted = replace(
            self.domain,
            engine_binding_sha256="f" * 64,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeRaceError,
            "engine/catalog",
        ):
            GcsimOptimizerTheoreticalAnytimeRaceSession(
                "prepared theoretical config",
                engine_context=self.context,
                domain=drifted,
                simulator_factory=_ScriptedSimulatorFactory(),
            )


class _ScriptedSimulatorFactory:
    def __init__(self) -> None:
        self.calls = []
        self.instances = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        instance = _ScriptedSimulator(
            iterations=kwargs["fidelity"].iterations,
        )
        self.instances.append(instance)
        return instance


class _ScriptedSimulator:
    def __init__(self, *, iterations: int) -> None:
        self.iterations = iterations
        self.evaluation_context_sha256 = hashlib.sha256(
            f"theoretical-tier-{iterations}".encode("utf-8")
        ).hexdigest()
        self.requests = ()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def __call__(self, requests):
        self.requests = tuple(requests)
        return {
            request.state.probe_key: FullTeamSimulationMetrics(
                status=TEAM_SIM_PASSED,
                dps_mean=(
                    100_000.0
                    - request.ordinal * 100.0
                    + self.iterations
                ),
                dps_se=(
                    250.0
                    if request.ordinal % 7 == 0
                    else 10.0
                ),
                iterations=self.iterations,
                cache_hit=False,
            )
            for request in self.requests
        }


class _CachedNonLeaderSimulatorFactory:
    def __call__(self, **kwargs):
        return _CachedNonLeaderSimulator(
            iterations=kwargs["fidelity"].iterations,
        )


class _CachedNonLeaderSimulator(_ScriptedSimulator):
    def __call__(self, requests):
        self.requests = tuple(requests)
        return {
            request.state.probe_key: FullTeamSimulationMetrics(
                status=TEAM_SIM_PASSED,
                dps_mean=100_000.0 - request.ordinal,
                dps_se=10.0,
                iterations=self.iterations,
                cache_hit=request.ordinal == 1,
            )
            for request in self.requests
        }


class _LayoutScoringSimulatorFactory:
    def __init__(self, target_layouts: tuple[str, str]) -> None:
        self.target_layouts = target_layouts

    def __call__(self, **kwargs):
        return _LayoutScoringSimulator(
            iterations=kwargs["fidelity"].iterations,
            target_layouts=self.target_layouts,
        )


class _LayoutScoringSimulator(_ScriptedSimulator):
    def __init__(
        self,
        *,
        iterations: int,
        target_layouts: tuple[str, str],
    ) -> None:
        super().__init__(iterations=iterations)
        self.target_layouts = target_layouts

    def __call__(self, requests):
        self.requests = tuple(requests)
        return {
            request.state.probe_key: FullTeamSimulationMetrics(
                status=TEAM_SIM_PASSED,
                dps_mean=(
                    100_000.0
                    + 10_000.0
                    * (
                        request.state.choices[0].state.main_stat_layout_id
                        == self.target_layouts[0]
                    )
                    + 9_000.0
                    * (
                        request.state.choices[1].state.main_stat_layout_id
                        == self.target_layouts[1]
                    )
                ),
                dps_se=1.0,
                iterations=self.iterations,
                cache_hit=False,
            )
            for request in self.requests
        }


if __name__ == "__main__":
    unittest.main()
