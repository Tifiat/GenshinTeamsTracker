from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.optimizer_anytime_selected_service import (
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
    GcsimOptimizerAnytimeSelectedSession,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWorkPlan,
    GcsimTwoPlusTwoTargetPackage,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment
from .test_gcsim_optimizer_anytime_selected_service import (
    _ImmediateSessionFactory,
    _ResponseDiscovery,
    _plan,
)


class GcsimOptimizerAccountTwoPlusTwoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        base_plan = _plan()
        self.plan = replace(
            base_plan,
            candidates=replace(
                base_plan.candidates,
                max_builds_per_target=16,
                max_builds_per_wearer=64,
            ),
        )
        pools = tuple(
            GcsimOptimizerWearerSetPool(
                wearer,
                (
                    self.environment.set_refs[index],
                    self.environment.set_refs[(index + 1) % 4],
                ),
            )
            for index, wearer in enumerate(self.environment.wearers)
        )
        overrides = tuple(
            replace(
                override,
                allowed_set_uids=tuple(
                    item.set_uid for item in pools[index].allowed_sets
                ),
            )
            for index, override in enumerate(
                self.environment.request.four_star_overrides
            )
        )
        request = replace(
            self.environment.request,
            selected_set_pools=pools,
            four_star_overrides=overrides,
            include_2p2p=True,
            work_plan=GcsimOptimizerWorkPlan(
                operation=self.environment.request.operation,
                plan_id=GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
                plan_version=GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
                parameters=self.plan.to_dict(),
            ),
        )
        built = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=self.environment.shell,
            artifact_database=self.environment.database,
            engine_context=self.environment.engine,
        )
        assert built.ready and built.run_input is not None
        self.run_input = built.run_input

    def test_pair_identity_is_canonical_and_rejects_same_set(self) -> None:
        set_a, set_b = self.run_input.request.selected_set_pools[
            0
        ].allowed_sets

        forward = GcsimTwoPlusTwoTargetPackage(set_a, set_b)
        reverse = GcsimTwoPlusTwoTargetPackage(set_b, set_a)

        self.assertEqual(forward, reverse)
        self.assertEqual(forward.identity_sha256, reverse.identity_sha256)
        with self.assertRaisesRegex(ValueError, "two different"):
            GcsimTwoPlusTwoTargetPackage(set_a, set_a)

    def test_anytime_target_domain_contains_each_canonical_pair(self) -> None:
        session = self._session()

        targets_by_wearer, issues = session._build_targets()

        self.assertEqual(issues, ())
        self.assertEqual(tuple(slot for slot, _rows in targets_by_wearer), (1, 2, 3, 4))
        for _slot, targets in targets_by_wearer:
            pairs = tuple(
                target
                for target in targets
                if isinstance(target.package, GcsimTwoPlusTwoTargetPackage)
            )
            self.assertEqual(len(pairs), 1)

    def test_anytime_pair_search_returns_exact_twenty_id_build(self) -> None:
        result = self._session().run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertIsNotNone(result.best_found)
        ids = tuple(
            artifact_id
            for assignment in (
                result.best_found.account_assignment.wearer_assignments
            )
            for artifact_id in assignment.artifact_ids
        )
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20)
        self.assertTrue(
            all(
                any(
                    isinstance(
                        target.package,
                        GcsimTwoPlusTwoTargetPackage,
                    )
                    for target in targets
                )
                for _slot, targets in result.targets_by_wearer
            )
        )

    def _session(self):
        return GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
        )


if __name__ == "__main__":
    unittest.main()
