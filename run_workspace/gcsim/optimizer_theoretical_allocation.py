"""Readable product evidence for validated theoretical GCSIM allocations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re

from .farming_finalist_optimizer import GcsimFinalistOptimizerOutcome
from .farming_profile_config import (
    DEFAULT_FIXED_SUBSTATS_COUNT,
    GCSIM_SUBSTAT_ROLL_VALUES,
)
from .optimizer_config import GcsimFiveStarMainStatLayout
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_THEORETICAL_SUBSTAT_AXES,
    GcsimOptimizerTheoreticalAllocationWitness,
    GcsimOptimizerTheoreticalStatRoll,
    GcsimOptimizerTheoreticalWearerAllocation,
    GcsimOptimizerWearerIdentity,
)


_ADD_STATS_RE = re.compile(
    r"^\s*(?P<wearer>[a-z]+)\s+add\s+stats\b(?P<body>[^;]*);\s*$",
    re.IGNORECASE,
)
_SCALAR_TERM_RE = re.compile(
    r"^(?P<axis>hp%|atk%|def%|hp|atk|def|er|em|cr|cd)="
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    r"\*(?P<count>\d+)$"
)


class GcsimOptimizerTheoreticalAllocationError(ValueError):
    """Raised when validated optimizer evidence cannot be projected losslessly."""


def build_gcsim_optimizer_theoretical_allocation_witness(
    *,
    request_sha256: str,
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    outcome: GcsimFinalistOptimizerOutcome,
    layout_catalog: Mapping[
        str,
        Mapping[str, GcsimFiveStarMainStatLayout],
    ],
    fixed_rolls_per_axis: int = DEFAULT_FIXED_SUBSTATS_COUNT,
) -> GcsimOptimizerTheoreticalAllocationWitness:
    """Project one already-validated finalist into the versioned UI contract."""

    if not isinstance(outcome, GcsimFinalistOptimizerOutcome):
        raise GcsimOptimizerTheoreticalAllocationError(
            "outcome must be validated finalist evidence"
        )
    canonical_wearers = tuple(wearers)
    if (
        not 1 <= len(canonical_wearers) <= 4
        or any(
            not isinstance(item, GcsimOptimizerWearerIdentity)
            for item in canonical_wearers
        )
        or tuple(item.team_slot for item in canonical_wearers)
        != tuple(range(1, len(canonical_wearers) + 1))
    ):
        raise GcsimOptimizerTheoreticalAllocationError(
            "allocation projection requires canonical wearers"
        )
    if (
        isinstance(fixed_rolls_per_axis, bool)
        or not isinstance(fixed_rolls_per_axis, int)
        or fixed_rolls_per_axis < 0
    ):
        raise GcsimOptimizerTheoreticalAllocationError(
            "fixed_rolls_per_axis must be a non-negative integer"
        )
    wearer_by_key = {
        item.gcsim_character_key: item for item in canonical_wearers
    }
    if tuple(item.wearer_id for item in outcome.allocations) != tuple(
        wearer_by_key
    ):
        raise GcsimOptimizerTheoreticalAllocationError(
            "finalist allocation order differs from source wearers"
        )

    rows = []
    for allocation in outcome.allocations:
        try:
            layout = layout_catalog[allocation.wearer_id][
                allocation.main_stat_layout_id
            ]
        except (KeyError, TypeError) as exc:
            raise GcsimOptimizerTheoreticalAllocationError(
                "finalist allocation references an unknown main-stat layout"
            ) from exc
        if not isinstance(layout, GcsimFiveStarMainStatLayout):
            raise GcsimOptimizerTheoreticalAllocationError(
                "layout catalog contains an untyped main-stat layout"
            )
        counts = _parse_total_roll_counts(
            allocation.add_stats_lines,
            wearer=allocation.wearer_id,
        )
        if any(
            counts[axis] < fixed_rolls_per_axis
            for axis in GCSIM_OPTIMIZER_THEORETICAL_SUBSTAT_AXES
        ):
            raise GcsimOptimizerTheoreticalAllocationError(
                "optimizer allocation is below its fixed-roll floor"
            )
        rolls = tuple(
            GcsimOptimizerTheoreticalStatRoll(
                axis_key=axis,
                fixed_rolls=fixed_rolls_per_axis,
                liquid_rolls=counts[axis] - fixed_rolls_per_axis,
            )
            for axis in GCSIM_OPTIMIZER_THEORETICAL_SUBSTAT_AXES
        )
        rows.append(
            GcsimOptimizerTheoreticalWearerAllocation(
                wearer=wearer_by_key[allocation.wearer_id],
                package_key=allocation.set_key,
                main_stat_layout_id=allocation.main_stat_layout_id,
                main_stats_by_slot={
                    "sands": layout.sands,
                    "goblet": layout.goblet,
                    "circlet": layout.circlet,
                },
                rolls=rolls,
                total_liquid_rolls=sum(
                    item.liquid_rolls for item in rolls
                ),
                gcsim_add_stats_lines=allocation.add_stats_lines,
            )
        )
    return GcsimOptimizerTheoreticalAllocationWitness(
        request_sha256=request_sha256,
        source_allocation_sha256=outcome.allocation_sha256,
        wearer_allocations=tuple(rows),
    )


def _parse_total_roll_counts(
    lines: Sequence[str],
    *,
    wearer: str,
) -> dict[str, int]:
    expected = set(GCSIM_SUBSTAT_ROLL_VALUES)
    candidates: list[dict[str, int]] = []
    for line in lines:
        match = _ADD_STATS_RE.match(line)
        if match is None or match.group("wearer").casefold() != wearer:
            continue
        counts: dict[str, int] = {}
        for token in match.group("body").strip().split():
            term = _SCALAR_TERM_RE.match(token)
            if term is None:
                counts = {}
                break
            axis = term.group("axis")
            if axis in counts:
                counts = {}
                break
            counts[axis] = int(term.group("count"))
        if set(counts) == expected:
            candidates.append(counts)
    if len(candidates) != 1:
        raise GcsimOptimizerTheoreticalAllocationError(
            "finalist lacks one exact scalar substat allocation row"
        )
    return candidates[0]


__all__ = [
    "GcsimOptimizerTheoreticalAllocationError",
    "build_gcsim_optimizer_theoretical_allocation_witness",
]
