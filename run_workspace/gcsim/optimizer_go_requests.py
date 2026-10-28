"""Shared immutable request types for the three Go optimizer adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from hoyolab_export.paths import PROJECT_ROOT
from .engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR
from .optimizer_run_retention import DEFAULT_GO_RUN_ROOT


DEFAULT_SELECTED_SEEDS = (742_031_889, 742_031_890)
# A zero product timeout means the optimizer runs until it completes or the
# user cancels. Positive timeouts remain available to bounded diagnostics.
DEFAULT_PRODUCT_TIMEOUT_MS = 0
DEFAULT_DEVELOPMENT_TIMEOUT_MS = 360_000
DEFAULT_OPTIMIZER_BINARY = (
    PROJECT_ROOT / "native" / "gcsim_optimizer" / "gtt-optimizer.exe"
)
DEFAULT_SELECTED_RUN_ROOT = DEFAULT_GO_RUN_ROOT
GCSIM_OPTIMIZER_ADAPTER_TIMINGS_KIND = "gtt_gcsim_optimizer_adapter_timings_v1"
REQUIRED_ENGINE_CAPABILITIES = frozenset(
    {"gtt_compact_equation_v1", "gtt_trace_equation_v6"}
)
FINITE_ENERGY_ENGINE_CAPABILITY = "gtt_energy_ledger_v1"

class GcsimOptimizerGoError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerGoRequest:
    db_path: str
    selected_team: Mapping[str, Any]
    team_index: int
    rotation_shell_text: str
    infinite_energy_enabled: bool = True
    set_group_limit: int = 3
    builds_per_group: int = 2
    expanded_limits: bool = False
    fast_mode: bool = False
    engine_store_dir: str = str(DEFAULT_GCSIM_ENGINE_STORE_DIR)
    expected_engine_id: str = ""
    optimizer_binary_path: str = str(DEFAULT_OPTIMIZER_BINARY)
    run_root: str = str(DEFAULT_SELECTED_RUN_ROOT)
    seeds: tuple[int, ...] = DEFAULT_SELECTED_SEEDS
    product_timeout_ms: int = DEFAULT_PRODUCT_TIMEOUT_MS
