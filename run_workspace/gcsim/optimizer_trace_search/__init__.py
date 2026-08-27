"""Isolated formula-guided artifact search strategies.

Nothing in this package owns UI, engine execution, account mutation or product
composition. Strategies remain non-authoritative until their explicit gates
pass.
"""

from .continuous_target import (
    CONTINUOUS_TARGET_KIND,
    CONTINUOUS_TARGET_SCHEMA_VERSION,
    ContinuousAllocationValue,
    ContinuousMainStatLane,
    ContinuousTargetConfig,
    ContinuousTargetPoint,
    ContinuousTargetResult,
    MainStatSelection,
    solve_continuous_main_stat_lanes,
    solve_continuous_target,
)
from .selected_composition import (
    SELECTED_COMPOSITION_KIND,
    SELECTED_COMPOSITION_SCHEMA_VERSION,
    SelectedCompleteAssignment,
    SelectedCompleteAssignmentScore,
    SelectedCompositionScoreBatch,
    SelectedCompositionScoringSession,
    build_selected_complete_assignment,
    compile_selected_composition_scoring_session,
    score_selected_complete_assignment,
    score_selected_complete_assignments,
)


__all__ = [
    "CONTINUOUS_TARGET_KIND",
    "CONTINUOUS_TARGET_SCHEMA_VERSION",
    "ContinuousAllocationValue",
    "ContinuousMainStatLane",
    "ContinuousTargetConfig",
    "ContinuousTargetPoint",
    "ContinuousTargetResult",
    "MainStatSelection",
    "solve_continuous_main_stat_lanes",
    "solve_continuous_target",
    "SELECTED_COMPOSITION_KIND",
    "SELECTED_COMPOSITION_SCHEMA_VERSION",
    "SelectedCompleteAssignment",
    "SelectedCompleteAssignmentScore",
    "SelectedCompositionScoreBatch",
    "SelectedCompositionScoringSession",
    "build_selected_complete_assignment",
    "compile_selected_composition_scoring_session",
    "score_selected_complete_assignment",
    "score_selected_complete_assignments",
]
