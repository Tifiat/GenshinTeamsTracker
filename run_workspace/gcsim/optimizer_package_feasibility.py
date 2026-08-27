"""Cheap physical package-feasibility checks over the frozen artifact DB."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from itertools import combinations

from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_PACKAGE_SLOTS = (
    "flower",
    "plume",
    "sands",
    "goblet",
    "circlet",
)


def gcsim_optimizer_eligible_slots_by_set(
    run_input: GcsimOptimizerRunInput,
) -> Mapping[str, frozenset[str]]:
    """Return usable five-star slot coverage by concrete set UID."""

    rows: dict[str, set[str]] = defaultdict(set)
    for artifact in run_input.artifact_database.artifacts:
        if (
            artifact.default_eligible
            and artifact.set_mapping_status == "ready"
            and artifact.position_key in GCSIM_OPTIMIZER_PACKAGE_SLOTS
        ):
            rows[artifact.set_uid].add(artifact.position_key)
    return {
        set_uid: frozenset(slots)
        for set_uid, slots in rows.items()
    }


def gcsim_optimizer_account_target_is_physically_feasible(
    run_input: GcsimOptimizerRunInput,
    target: GcsimOptimizerWearerTarget,
) -> bool:
    """Check that a package can occupy four slots plus one legal off-piece."""

    slots_by_set = gcsim_optimizer_eligible_slots_by_set(run_input)
    all_slots = frozenset(
        artifact.position_key
        for artifact in run_input.artifact_database.artifacts
        if (
            artifact.default_eligible
            and artifact.position_key in GCSIM_OPTIMIZER_PACKAGE_SLOTS
        )
    )
    if all_slots != frozenset(GCSIM_OPTIMIZER_PACKAGE_SLOTS):
        return False
    package = target.package
    if isinstance(package, GcsimFourPieceTargetPackage):
        return len(slots_by_set.get(package.set_ref.set_uid, ())) >= 4
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        left_slots = slots_by_set.get(package.set_a.set_uid, ())
        right_slots = slots_by_set.get(package.set_b.set_uid, ())
        return any(
            set(left).isdisjoint(right)
            for left in combinations(sorted(left_slots), 2)
            for right in combinations(sorted(right_slots), 2)
        )
    return False


__all__ = [
    "GCSIM_OPTIMIZER_PACKAGE_SLOTS",
    "gcsim_optimizer_account_target_is_physically_feasible",
    "gcsim_optimizer_eligible_slots_by_set",
]
