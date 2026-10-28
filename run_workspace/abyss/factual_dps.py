from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .current_fixture import CURRENT_HP_KIND


REASON_MISSING_HP = "missing_hp"
REASON_ZERO_OR_NEGATIVE_TIME = "zero_or_negative_time"


class SupportsSideHp(Protocol):
    def total_hp_for_kind(self, hp_kind: str = CURRENT_HP_KIND) -> int:
        ...


@dataclass(frozen=True, slots=True)
class FactualDpsResult:
    dps: float | None
    unavailable_reason: str = ""

    @property
    def is_available(self) -> bool:
        return self.dps is not None

    @property
    def rounded_dps(self) -> int | None:
        if self.dps is None:
            return None
        return int(round(self.dps))


def calculate_factual_dps(
    *,
    total_hp: int | None,
    elapsed_seconds: int | float,
) -> FactualDpsResult:
    if total_hp is None:
        return FactualDpsResult(dps=None, unavailable_reason=REASON_MISSING_HP)

    elapsed = float(elapsed_seconds)
    if elapsed <= 0:
        return FactualDpsResult(
            dps=None,
            unavailable_reason=REASON_ZERO_OR_NEGATIVE_TIME,
        )

    return FactualDpsResult(dps=float(total_hp) / elapsed)


def calculate_side_factual_dps(
    side: SupportsSideHp,
    *,
    elapsed_seconds: int | float,
    hp_kind: str = CURRENT_HP_KIND,
) -> FactualDpsResult:
    return calculate_factual_dps(
        total_hp=side.total_hp_for_kind(hp_kind),
        elapsed_seconds=elapsed_seconds,
    )