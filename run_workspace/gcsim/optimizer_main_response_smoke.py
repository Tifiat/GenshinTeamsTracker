"""Explicit active-engine smoke for Milestone 4 response probes."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from .artifact_runner import run_active_gcsim_artifact
from .farming_pipeline import GcsimFarmingScreeningFidelity
from .farming_profile_config import (
    build_default_gcsim_screening_profile_bank,
)
from .farming_search import FourPieceSetState, SetProfileCandidate
from .optimizer_config import GcsimFiveStarMainStatLayout
from .optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from .optimizer_main_response import (
    GcsimOptimizerFourPieceMainDomain,
    GcsimOptimizerReachableMainLayout,
    GcsimOptimizerResponseProbeKind,
    build_gcsim_optimizer_response_probe_plan,
    gcsim_optimizer_main_layout_id,
    materialize_gcsim_optimizer_response_probe,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
)
from .prepared_config_adapter import (
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
    build_prepared_team_full_config_report_from_json,
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMainResponseSmokeResult:
    success: bool
    evaluated_probe_count: int
    reference_dps: float | None = None
    em_exchange_dps: float | None = None
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "evaluated_probe_count": self.evaluated_probe_count,
            "reference_dps": self.reference_dps,
            "em_exchange_dps": self.em_exchange_dps,
            "error": self.error,
        }


def run_optimizer_main_response_real_smoke(
    *,
    iterations: int = 10,
    timeout_seconds: int = 120,
) -> GcsimOptimizerMainResponseSmokeResult:
    try:
        engine = load_active_gcsim_optimizer_engine_context()
        prepared = build_prepared_team_full_config_report_from_json(
            DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
            rotation_shell_path=(
                CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH
            ),
            write_config=False,
        )
        if not prepared.ready:
            return _failed(f"prepared config not ready: {prepared.issues!r}")
        wearer_ids = ("chasca", "ororon", "furina", "bennett")
        layouts = {
            "chasca": GcsimFiveStarMainStatLayout(
                "atk%",
                "anemo%",
                "cr",
            ),
            "ororon": GcsimFiveStarMainStatLayout(
                "er",
                "electro%",
                "cr",
            ),
            "furina": GcsimFiveStarMainStatLayout(
                "hp%",
                "hydro%",
                "cr",
            ),
            "bennett": GcsimFiveStarMainStatLayout(
                "er",
                "pyro%",
                "cr",
            ),
        }
        set_keys = {
            "chasca": "obsidiancodex",
            "ororon": "scrolloftheheroofcindercity",
            "furina": "goldentroupe",
            "bennett": "noblesseoblige",
        }
        layout_ids = {
            wearer: gcsim_optimizer_main_layout_id(layout)
            for wearer, layout in layouts.items()
        }
        layout_catalog = {
            wearer: {layout_ids[wearer]: layouts[wearer]}
            for wearer in wearer_ids
        }
        frozen_baselines = tuple(
            SetProfileCandidate(
                FourPieceSetState(
                    wearer_id=wearer,
                    set_key=set_keys[wearer],
                    main_stat_layout_id=layout_ids[wearer],
                ),
                "baseline",
            )
            for wearer in wearer_ids
            if wearer != "chasca"
        )
        wearer = GcsimOptimizerWearerIdentity(
            team_slot=1,
            account_character_id=30_001,
            gcsim_character_key="chasca",
        )
        package = GcsimFourPieceTargetPackage(
            GcsimOptimizerSetReference(
                set_uid="ObsidianCodex",
                gcsim_set_key="obsidiancodex",
                engine_binding_sha256=engine.binding_sha256,
                catalog_fingerprint=engine.catalog.source_fingerprint,
            )
        )
        evidence = tuple(
            (slot, (index,))
            for index, slot in enumerate(
                GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                start=1,
            )
        )
        domain = GcsimOptimizerFourPieceMainDomain(
            run_input_sha256="f" * 64,
            wearer=wearer,
            package=package,
            reachable_layouts=(
                GcsimOptimizerReachableMainLayout(
                    layout=layouts["chasca"],
                    supporting_artifact_ids_by_slot=evidence,
                    maximum_target_piece_count=4,
                ),
            ),
            eligible_artifact_ids_by_slot=evidence,
            excluded_artifact_counts=(),
        )
        plan = build_gcsim_optimizer_response_probe_plan(
            domain,
            frozen_team_context_sha256="a" * 64,
            exchange_scales=(1, 4, 8),
            interaction_axes=(("em", "atk%"),),
        )
        selected = (
            next(
                item
                for item in plan.probes
                if item.kind
                is GcsimOptimizerResponseProbeKind.REFERENCE
            ),
            next(
                item
                for item in plan.probes
                if item.kind
                is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
                and item.focus_axes == ("em",)
                and item.exchange_rolls == 4
            ),
        )
        dps_values: list[float] = []
        profile_bank = build_default_gcsim_screening_profile_bank()
        fidelity = GcsimFarmingScreeningFidelity(iterations, 1)
        with tempfile.TemporaryDirectory(prefix="gtt-m4-response-smoke-") as tmp:
            for index, probe in enumerate(selected):
                materialized = materialize_gcsim_optimizer_response_probe(
                    prepared.assembly.config_text,
                    probe=probe,
                    frozen_baseline_states=frozen_baselines,
                    wearer_ids=wearer_ids,
                    layout_catalog=layout_catalog,
                    profile_bank=profile_bank,
                    engine_context=engine,
                    fidelity=fidelity,
                )
                run = run_active_gcsim_artifact(
                    materialized.config_text,
                    run_dir=Path(tmp) / str(index),
                    timeout_seconds=timeout_seconds,
                )
                if not run.success or run.summary.dps_mean is None:
                    return _failed(
                        run.error or run.stderr or run.status,
                        evaluated_probe_count=len(dps_values),
                    )
                dps_values.append(run.summary.dps_mean)
        return GcsimOptimizerMainResponseSmokeResult(
            success=True,
            evaluated_probe_count=2,
            reference_dps=dps_values[0],
            em_exchange_dps=dps_values[1],
        )
    except (LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _failed(str(exc))


def _failed(
    error: str,
    *,
    evaluated_probe_count: int = 0,
) -> GcsimOptimizerMainResponseSmokeResult:
    return GcsimOptimizerMainResponseSmokeResult(
        success=False,
        evaluated_probe_count=evaluated_probe_count,
        error=error,
    )


def main() -> int:
    result = run_optimizer_main_response_real_smoke()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
