"""All Sets process adapter over the common account/worker/result boundary.

Only serializes verified source text once. The Go process owns every capture,
guide refresh, artifact search and ordinary finalist evaluation. No Python math.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from hoyolab_export.paths import PROJECT_ROOT
from .optimizer_go_all_sources import NEUTRAL_INPUTS_CAPABILITY, prepare_all_set_effect_sources
from .engine_store import GcsimEngineStore, GcsimEngineStoreError
from .optimizer_go_contracts import write_canonical
from .optimizer_go_requests import (
    GcsimOptimizerGoError,
    GcsimOptimizerGoRequest,
)
from .optimizer_go_session import GcsimOptimizerGoSession
from .selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerGoAllSetsRequest(GcsimOptimizerGoRequest):
    product_timeout_ms: int = 0


def all_sets_available() -> bool:
    """Cheap display gate only. A run still verifies binary/source identities."""
    try:
        installed = GcsimEngineStore().get_active_engine()
        if installed is None:
            return False
        capabilities = json.loads(installed.manifest.metadata.get("gtt_capabilities", "[]"))
        return isinstance(capabilities, list) and "gtt_effect_inputs_v1" in capabilities
    except (GcsimEngineStoreError, OSError, ValueError, TypeError):
        return False


class GcsimOptimizerGoAllSetsSession(GcsimOptimizerGoSession):
    run_mode = "all_sets"
    mode_label = "All Sets"
    virtual_artifact_policy = VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE

    def _optimizer_environment(self) -> dict[str, str]:
        env = super()._optimizer_environment()
        # Shipped source-only plans are immutable; updates/new engine rules go
        # into a bounded disposable runtime cache, never into program assets.
        env.setdefault("GTT_RULE_BUNDLED_CACHE_DIR", str(
            PROJECT_ROOT / "native/gcsim_optimizer/set-rule-cache"))
        root = Path(env["GTT_SCRATCH_DIR"]) if env.get("GTT_SCRATCH_DIR") else PROJECT_ROOT / "data/gcsim"
        env.setdefault("GTT_RULE_CACHE_DIR", str(root / "set-rule-cache"))
        return env

    def _prepare_formula_inputs(self, *, prepared, run_dir, started):
        del started
        self._require_not_cancelled()
        engine = prepared["request"]["engine"]
        root = Path(engine["binary_path"]).resolve().parent.parent
        try:
            # Keep Theory and finite-energy All Sets on their existing route.
            # The new observer and consumer are promoted together; an older
            # active engine must not receive a falsely neutral source envelope.
            neutral = (self.run_mode == "all_sets" and self.request.infinite_energy_enabled
                       and NEUTRAL_INPUTS_CAPABILITY in engine.get("capabilities", ()))
            sources = prepare_all_set_effect_sources(root, engine, include_neutral_rules=neutral)
        except (OSError, ValueError, KeyError) as exc:
            raise GcsimOptimizerGoError(
                "all_sets_source_unavailable", str(exc)
            ) from exc
        self._require_not_cancelled()
        write_canonical(run_dir / "set-sources.json", sources)
        return {}  # No compact panel is materialized or round-tripped by Python.

    def _optimizer_command(self, binary: Path, run_dir: Path) -> tuple[str, ...]:
        return (str(binary), "optimize-all-sets", str(run_dir / "request.json"),
                str(run_dir / "set-sources.json"), str(run_dir / "verification"),
                "--finish-file", str(run_dir / "finish-requested"))
