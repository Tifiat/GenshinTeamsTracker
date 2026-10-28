"""Retained future Theory/All-Sets continuous-target mathematics.

Selected runtime search moved to ``native/gcsim_optimizer`` at GOB-5.  This
package deliberately exposes only the isolated continuous-target reference;
removed Python Selected strategies must not reappear as hidden fallbacks.
"""

from __future__ import annotations

from importlib import import_module
from typing import Final


_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CONTINUOUS_TARGET_KIND": (".continuous_target", "CONTINUOUS_TARGET_KIND"),
    "CONTINUOUS_TARGET_SCHEMA_VERSION": (
        ".continuous_target",
        "CONTINUOUS_TARGET_SCHEMA_VERSION",
    ),
    "ContinuousAllocationValue": (
        ".continuous_target",
        "ContinuousAllocationValue",
    ),
    "ContinuousMainStatLane": (".continuous_target", "ContinuousMainStatLane"),
    "ContinuousTargetConfig": (".continuous_target", "ContinuousTargetConfig"),
    "ContinuousTargetPoint": (".continuous_target", "ContinuousTargetPoint"),
    "ContinuousTargetResult": (".continuous_target", "ContinuousTargetResult"),
    "MainStatSelection": (".continuous_target", "MainStatSelection"),
    "solve_continuous_main_stat_lanes": (
        ".continuous_target",
        "solve_continuous_main_stat_lanes",
    ),
    "solve_continuous_target": (".continuous_target", "solve_continuous_target"),
    "SUPPORT_CONTINUOUS_GUIDE_KIND": (
        ".continuous_target_support",
        "SUPPORT_CONTINUOUS_GUIDE_KIND",
    ),
    "SUPPORT_CONTINUOUS_SCHEMA_VERSION": (
        ".continuous_target_support",
        "SUPPORT_CONTINUOUS_SCHEMA_VERSION",
    ),
    "SUPPORT_CONTINUOUS_TARGET_KIND": (
        ".continuous_target_support",
        "SUPPORT_CONTINUOUS_TARGET_KIND",
    ),
    "ContinuousGuideCandidate": (
        ".continuous_target_support",
        "ContinuousGuideCandidate",
    ),
    "ContinuousGuidePrediction": (
        ".continuous_target_support",
        "ContinuousGuidePrediction",
    ),
    "SupportAwareContinuousGuideResult": (
        ".continuous_target_support",
        "SupportAwareContinuousGuideResult",
    ),
    "SupportAwareContinuousTargetResult": (
        ".continuous_target_support",
        "SupportAwareContinuousTargetResult",
    ),
    "rank_candidates_by_support_continuous_target": (
        ".continuous_target_support",
        "rank_candidates_by_support_continuous_target",
    ),
    "solve_support_aware_continuous_target": (
        ".continuous_target_support",
        "solve_support_aware_continuous_target",
    ),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *_EXPORTS))
