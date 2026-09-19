"""All Sets process adapter over the common account/worker/result boundary.

Only serializes verified source text once. The Go process owns every capture,
guide refresh, artifact search and ordinary finalist evaluation. No Python math.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .optimizer_go_all_sources import prepare_all_set_effect_sources
from .engine_store import GcsimEngineStore, GcsimEngineStoreError
from .optimizer_go_selected import (
    GcsimOptimizerGoSelectedError,
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
    _write_canonical,
)
from .selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerGoAllSetsRequest(GcsimOptimizerGoSelectedRequest):
    product_timeout_ms: int = 600_000


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


class GcsimOptimizerGoAllSetsSession(GcsimOptimizerGoSelectedSession):
    run_mode = "all_sets"
    virtual_artifact_policy = VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE

    def _prepare_formula_inputs(self, *, prepared, run_dir, started):
        del started
        self._require_not_cancelled()
        engine = prepared["request"]["engine"]
        root = Path(engine["binary_path"]).resolve().parent.parent
        try:
            sources = prepare_all_set_effect_sources(root, engine)
        except (OSError, ValueError, KeyError) as exc:
            raise GcsimOptimizerGoSelectedError(
                "all_sets_source_unavailable", str(exc)
            ) from exc
        self._require_not_cancelled()
        _write_canonical(run_dir / "set-sources.json", sources)
        return {}  # No compact panel is materialized or round-tripped by Python.

    def _optimizer_command(self, binary: Path, run_dir: Path) -> tuple[str, ...]:
        return (str(binary), "optimize-all-sets", str(run_dir / "request.json"),
                str(run_dir / "set-sources.json"), str(run_dir / "verification"))
