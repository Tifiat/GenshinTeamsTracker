"""Display-only helpers shared by saved Run panels and History cards."""
from __future__ import annotations

from run_workspace.right_panel_prototype_view_model import _artifact_main_stat_badge

LEGACY_BUILD_WARNINGS = frozenset({
    "set_bonus_formulas_not_included", "conditional_set_bonuses_not_included",
})


def history_build_stat_badge(build) -> str:
    """Use live Run's property-id formatter, never initials of translated labels."""
    if build is None:
        return ""
    slots = [
        {"pos": item.position, "main_property_type": item.main_stat.key,
         "main_property_name": item.main_stat.label}
        for item in build.artifact_slots if item.main_stat is not None
    ]
    return _artifact_main_stat_badge({"slots": slots}) if slots else ""
