from __future__ import annotations

from types import SimpleNamespace
import unittest

from run_workspace.gcsim.optimizer_package_feasibility import (
    gcsim_optimizer_account_target_is_physically_feasible,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerPackageFeasibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = build_oracle_account_environment()
        self.wearer = environment.wearers[0]
        self.left = environment.set_refs[0]
        self.right = environment.set_refs[1]

    def test_four_rows_in_only_three_slots_are_rejected(self) -> None:
        target = GcsimOptimizerWearerTarget(
            self.wearer,
            GcsimFourPieceTargetPackage(self.left),
        )
        run_input = _run_input(
            (
                _artifact(self.left.set_uid, "flower"),
                _artifact(self.left.set_uid, "flower"),
                _artifact(self.left.set_uid, "plume"),
                _artifact(self.left.set_uid, "sands"),
                _artifact("OffPiece", "goblet"),
                _artifact("OffPiece", "circlet"),
            )
        )

        self.assertFalse(
            gcsim_optimizer_account_target_is_physically_feasible(
                run_input,
                target,
            )
        )

    def test_four_distinct_set_slots_are_accepted(self) -> None:
        target = GcsimOptimizerWearerTarget(
            self.wearer,
            GcsimFourPieceTargetPackage(self.left),
        )
        run_input = _run_input(
            (
                _artifact(self.left.set_uid, "flower"),
                _artifact(self.left.set_uid, "plume"),
                _artifact(self.left.set_uid, "sands"),
                _artifact(self.left.set_uid, "goblet"),
                _artifact("OffPiece", "circlet"),
            )
        )

        self.assertTrue(
            gcsim_optimizer_account_target_is_physically_feasible(
                run_input,
                target,
            )
        )

    def test_two_plus_two_requires_disjoint_slot_pairs(self) -> None:
        target = GcsimOptimizerWearerTarget(
            self.wearer,
            GcsimTwoPlusTwoTargetPackage(self.left, self.right),
        )
        overlapping = _run_input(
            (
                _artifact(self.left.set_uid, "flower"),
                _artifact(self.left.set_uid, "plume"),
                _artifact(self.right.set_uid, "flower"),
                _artifact(self.right.set_uid, "plume"),
                _artifact("OffPiece", "sands"),
                _artifact("OffPiece", "goblet"),
                _artifact("OffPiece", "circlet"),
            )
        )
        disjoint = _run_input(
            (
                _artifact(self.left.set_uid, "flower"),
                _artifact(self.left.set_uid, "plume"),
                _artifact(self.right.set_uid, "sands"),
                _artifact(self.right.set_uid, "goblet"),
                _artifact("OffPiece", "circlet"),
            )
        )

        self.assertFalse(
            gcsim_optimizer_account_target_is_physically_feasible(
                overlapping,
                target,
            )
        )
        self.assertTrue(
            gcsim_optimizer_account_target_is_physically_feasible(
                disjoint,
                target,
            )
        )


def _artifact(set_uid: str, slot: str) -> SimpleNamespace:
    return SimpleNamespace(
        default_eligible=True,
        set_mapping_status="ready",
        position_key=slot,
        set_uid=set_uid,
    )


def _run_input(artifacts) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_database=SimpleNamespace(artifacts=tuple(artifacts))
    )


if __name__ == "__main__":
    unittest.main()
