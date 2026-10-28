"""Pure GCSIM level text helpers for future config generation.

The helper mirrors the project's existing character ascension breakpoint
assumptions without importing UI or account snapshot code. It only formats
level readiness; it does not generate a full GCSIM config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATUS_READY = "ready"
STATUS_MISSING_LEVEL = "missing_level"
STATUS_INVALID_LEVEL = "invalid_level"

PHASE_PROMOTE_BEFORE_ASCENSION = "promote_level_before_ascension"
PHASE_PROMOTE_AFTER_ASCENSION = "promote_level_after_ascension"
PHASE_PROMOTE_NON_BREAKPOINT = "non_breakpoint_level"
PHASE_MISSING_PROMOTE_ASSUMED_AFTER_ASCENSION = (
    "missing_promote_level_assumed_after_ascension"
)
PHASE_FINAL_CAP = "final_cap"
PHASE_MISSING_LEVEL = "missing_level"
PHASE_INVALID_LEVEL = "invalid_level"

WARNING_PROMOTE_LEVEL_MISSING_ASSUMED_AFTER_ASCENSION = (
    "promote_level_missing_assumed_after_ascension"
)

_ASCENSION_BREAKPOINTS = {
    20: (0, 1, 40),
    40: (1, 2, 50),
    50: (2, 3, 60),
    60: (3, 4, 70),
    70: (4, 5, 80),
    80: (5, 6, 90),
}


@dataclass(frozen=True, slots=True)
class GcsimLevelResolution:
    status: str
    current_level: int | None = None
    max_level: int | None = None
    gcsim_level_text: str = ""
    phase_source: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_level": self.current_level,
            "max_level": self.max_level,
            "gcsim_level_text": self.gcsim_level_text,
            "phase_source": self.phase_source,
            "warnings": list(self.warnings),
        }


def resolve_gcsim_level_text(
    level: Any,
    promote_level: Any = None,
) -> GcsimLevelResolution:
    """Resolve account level/promote data into GCSIM current/max text.

    Breakpoint levels use the same before/after promote phases as the account
    stat snapshot code. Missing promote data on a breakpoint follows the
    project assumption that the character is after ascension.
    """

    current_level = _optional_int(level)
    if current_level is None:
        return GcsimLevelResolution(
            status=STATUS_MISSING_LEVEL,
            phase_source=PHASE_MISSING_LEVEL,
        )
    if current_level <= 0:
        return GcsimLevelResolution(
            status=STATUS_INVALID_LEVEL,
            current_level=current_level,
            phase_source=PHASE_INVALID_LEVEL,
        )

    if current_level >= 90:
        return _ready(current_level, current_level, PHASE_FINAL_CAP)

    breakpoint = _ASCENSION_BREAKPOINTS.get(current_level)
    if breakpoint is None:
        return _ready(current_level, current_level, PHASE_PROMOTE_NON_BREAKPOINT)

    before_promote, after_promote, after_max_level = breakpoint
    promote = _optional_int(promote_level)
    if promote is None:
        return _ready(
            current_level,
            after_max_level,
            PHASE_MISSING_PROMOTE_ASSUMED_AFTER_ASCENSION,
            warnings=(WARNING_PROMOTE_LEVEL_MISSING_ASSUMED_AFTER_ASCENSION,),
        )
    if promote >= after_promote:
        return _ready(current_level, after_max_level, PHASE_PROMOTE_AFTER_ASCENSION)
    if promote <= before_promote:
        return _ready(current_level, current_level, PHASE_PROMOTE_BEFORE_ASCENSION)

    return _ready(current_level, current_level, PHASE_PROMOTE_BEFORE_ASCENSION)


def _ready(
    current_level: int,
    max_level: int,
    phase_source: str,
    *,
    warnings: tuple[str, ...] = (),
) -> GcsimLevelResolution:
    return GcsimLevelResolution(
        status=STATUS_READY,
        current_level=current_level,
        max_level=max_level,
        gcsim_level_text=f"{current_level}/{max_level}",
        phase_source=phase_source,
        warnings=warnings,
    )


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
