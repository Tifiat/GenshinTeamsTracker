"""Typed GTT-GCSIM paired stat-response contract and ephemeral runner.

The optimizer uses this boundary to ask one engine process for a source
control, a synthetic equal baseline, and many stat interventions.  Every row
uses the same seed panel and engine-side expected crit damage.  This avoids
the old error where unrelated complete builds were compared with independent
RNG and their total DPS difference was treated as a stat weight.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import subprocess
from time import monotonic
from tempfile import TemporaryDirectory
from typing import Any

from .optimizer_engine_context import GcsimOptimizerEngineContext


GCSIM_STAT_RESPONSE_SCHEMA_VERSION = 2
GCSIM_STAT_RESPONSE_CAPABILITY = "gtt_stat_response_v2"
GCSIM_SET_RESPONSE_CAPABILITY = "gtt_set_response_v1"

# Stats stored in a character profile by GCSIM.  Character/weapon base stats,
# talents, constellations and set effects remain in the config and therefore
# remain real.  Only artifact-like additive stats are neutralized.
GCSIM_STAT_RESPONSE_ARTIFACT_AXES = (
    "hp",
    "atk",
    "def",
    "hp%",
    "atk%",
    "def%",
    "em",
    "er",
    "cr",
    "cd",
    "pyro%",
    "hydro%",
    "electro%",
    "cryo%",
    "anemo%",
    "geo%",
    "dendro%",
    "phys%",
    "heal",
)

GCSIM_STAT_RESPONSE_MAIN_VALUES = {
    "hp%": 0.466,
    "atk%": 0.466,
    "def%": 0.583,
    "em": 187.0,
    "er": 0.518,
    "cr": 0.311,
    "cd": 0.622,
    "pyro%": 0.466,
    "hydro%": 0.466,
    "electro%": 0.466,
    "cryo%": 0.466,
    "anemo%": 0.466,
    "geo%": 0.466,
    "dendro%": 0.466,
    "phys%": 0.583,
    "heal": 0.359,
}

# One five-star average roll.  These are response units, not a promise that
# every stored artifact roll is exactly the average value.
GCSIM_STAT_RESPONSE_ROLL_VALUES = {
    "hp": 253.94,
    "atk": 16.54,
    "def": 19.68,
    "hp%": 0.0496,
    "atk%": 0.0496,
    "def%": 0.0620,
    "em": 19.82,
    "er": 0.0551,
    "cr": 0.0331,
    "cd": 0.0662,
}


class GcsimStatResponseError(RuntimeError):
    """Raised when the v2 response boundary cannot be trusted."""


class GcsimStatResponseCancelled(GcsimStatResponseError):
    """Raised after terminating an in-flight paired response process."""


class GcsimStatResponseObjective(str, Enum):
    DPS = "dps"
    CLEAR_TIME = "clear_time"


class GcsimStatResponseChangeMode(str, Enum):
    ADD = "add"
    SET = "set"


@dataclass(frozen=True, slots=True)
class GcsimStatResponseTarget:
    objective: GcsimStatResponseObjective
    target_sha256: str
    wave_scenario_path: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.objective, GcsimStatResponseObjective):
            raise GcsimStatResponseError("response objective must be typed")
        _require_sha256(self.target_sha256, "target_sha256")
        scenario = str(self.wave_scenario_path or "").strip()
        if self.objective is GcsimStatResponseObjective.CLEAR_TIME:
            if not scenario:
                raise GcsimStatResponseError(
                    "clear-time response requires the selected chamber scenario"
                )
            resolved = Path(scenario).expanduser().resolve()
            if not resolved.is_file():
                raise GcsimStatResponseError(
                    f"selected chamber scenario is missing: {resolved}"
                )
            actual = _sha256_file(resolved)
            if actual != self.target_sha256:
                raise GcsimStatResponseError(
                    "selected chamber scenario differs from target_sha256"
                )
            object.__setattr__(self, "wave_scenario_path", str(resolved))
        elif scenario:
            raise GcsimStatResponseError(
                "DPS response cannot silently carry a chamber scenario"
            )


@dataclass(frozen=True, slots=True)
class GcsimStatResponseChange:
    character_index: int
    stat: str
    mode: GcsimStatResponseChangeMode
    value: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.character_index, bool)
            or not isinstance(self.character_index, int)
            or self.character_index not in range(4)
        ):
            raise GcsimStatResponseError("character_index must be in 0..3")
        if self.stat not in GCSIM_STAT_RESPONSE_ARTIFACT_AXES:
            raise GcsimStatResponseError(f"unsupported response stat: {self.stat!r}")
        if not isinstance(self.mode, GcsimStatResponseChangeMode):
            raise GcsimStatResponseError("response change mode must be typed")
        value = float(self.value)
        if not isfinite(value):
            raise GcsimStatResponseError("response change value must be finite")
        if self.mode is GcsimStatResponseChangeMode.SET and value < 0:
            raise GcsimStatResponseError("set response value must be non-negative")
        object.__setattr__(self, "value", value)

    def to_dict(self) -> dict[str, object]:
        # Match Go encoding/json for typed float64 values: integral values are
        # emitted without a decimal point and participate in request_sha256.
        encoded_value: int | float = (
            int(self.value) if self.value.is_integer() else self.value
        )
        return {
            "character_index": self.character_index,
            "stat": self.stat,
            "mode": self.mode.value,
            "value": encoded_value,
        }


@dataclass(frozen=True, slots=True)
class GcsimSetResponseChange:
    """One engine-modeled artifact-set assignment for a paired intervention."""

    character_index: int
    set_key: str
    set_count: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.character_index, bool)
            or not isinstance(self.character_index, int)
            or self.character_index not in range(4)
        ):
            raise GcsimStatResponseError("character_index must be in 0..3")
        key = str(self.set_key).strip().casefold()
        if (
            not key
            or key != self.set_key
            or not re.fullmatch(r"[a-z][a-z0-9]*", key)
        ):
            raise GcsimStatResponseError(
                "set response key must be a lowercase GCSIM identifier"
            )
        if (
            isinstance(self.set_count, bool)
            or not isinstance(self.set_count, int)
            or self.set_count not in {0, 2, 4}
        ):
            raise GcsimStatResponseError("set response count must be 0, 2, or 4")
        object.__setattr__(self, "set_key", key)

    def to_dict(self) -> dict[str, object]:
        return {
            "character_index": self.character_index,
            # The engine uses one tagged-union struct. These zero-value stat
            # fields remain serialized so Python and Go hash the same request.
            "stat": "",
            "mode": "",
            "value": 0,
            "set_key": self.set_key,
            "set_count": self.set_count,
        }


GcsimResponseChange = GcsimStatResponseChange | GcsimSetResponseChange


@dataclass(frozen=True, slots=True)
class GcsimStatResponseIntervention:
    intervention_id: str
    changes: tuple[GcsimResponseChange, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.intervention_id, str)
            or not self.intervention_id
            or self.intervention_id != self.intervention_id.strip()
            or self.intervention_id in {"source", "baseline"}
        ):
            raise GcsimStatResponseError(
                "intervention_id must be non-empty, trimmed, and non-reserved"
            )
        changes = tuple(self.changes)
        _validate_change_panel(changes, allow_empty=False)
        object.__setattr__(self, "changes", changes)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.intervention_id,
            "changes": [item.to_dict() for item in self.changes],
        }


@dataclass(frozen=True, slots=True)
class GcsimStatResponseRequest:
    context_sha256: str
    objective: GcsimStatResponseObjective
    iterations: int
    workers: int
    master_seed: int
    baseline_changes: tuple[GcsimResponseChange, ...]
    interventions: tuple[GcsimStatResponseIntervention, ...]
    ignore_burst_energy: bool = True
    schema_version: int = GCSIM_STAT_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_STAT_RESPONSE_SCHEMA_VERSION:
            raise GcsimStatResponseError("unsupported stat-response request schema")
        _require_sha256(self.context_sha256, "context_sha256")
        if not isinstance(self.objective, GcsimStatResponseObjective):
            raise GcsimStatResponseError("response objective must be typed")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations not in range(1, 1025)
        ):
            raise GcsimStatResponseError("iterations must be in 1..1024")
        if (
            isinstance(self.workers, bool)
            or not isinstance(self.workers, int)
            or self.workers < 1
            or self.workers > min(self.iterations, 64)
        ):
            raise GcsimStatResponseError(
                "workers must be in 1..min(iterations, 64)"
            )
        if (
            isinstance(self.master_seed, bool)
            or not isinstance(self.master_seed, int)
            or self.master_seed <= 0
            or self.master_seed > 2**63 - 1
        ):
            raise GcsimStatResponseError(
                "master_seed must be a positive signed 64-bit integer"
            )
        if self.ignore_burst_energy is not True:
            raise GcsimStatResponseError(
                "MVP optimizer response must ignore burst energy; ER is constrained by an explicit floor"
            )
        baseline = tuple(self.baseline_changes)
        interventions = tuple(self.interventions)
        _validate_change_panel(baseline, allow_empty=True)
        if len(interventions) > 256:
            raise GcsimStatResponseError("at most 256 interventions are allowed")
        ids = tuple(item.intervention_id for item in interventions)
        if len(set(ids)) != len(ids):
            raise GcsimStatResponseError("intervention IDs must be unique")
        object.__setattr__(self, "baseline_changes", baseline)
        object.__setattr__(self, "interventions", interventions)

    @property
    def request_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        # Field order mirrors the Go struct because its request hash uses
        # encoding/json over the parsed typed value.
        return {
            "schema_version": self.schema_version,
            "context_sha256": self.context_sha256,
            "objective": self.objective.value,
            "iterations": self.iterations,
            "workers": self.workers,
            "master_seed": str(self.master_seed),
            "ignore_burst_energy": self.ignore_burst_energy,
            "baseline_changes": [item.to_dict() for item in self.baseline_changes],
            "interventions": [item.to_dict() for item in self.interventions],
        }


@dataclass(frozen=True, slots=True)
class GcsimStatResponseEstimate:
    count: int
    mean: float
    sample_sd: float
    standard_error: float

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or self.count < 1:
            raise GcsimStatResponseError("response estimate count must be positive")
        for name in ("mean", "sample_sd", "standard_error"):
            value = float(getattr(self, name))
            if not isfinite(value) or (name != "mean" and value < 0):
                raise GcsimStatResponseError(f"invalid response estimate {name}")


@dataclass(frozen=True, slots=True)
class GcsimStatResponseSummary:
    duration_seconds: GcsimStatResponseEstimate
    team_expected_damage: GcsimStatResponseEstimate
    team_expected_dps: GcsimStatResponseEstimate
    character_expected_dps: tuple[GcsimStatResponseEstimate, ...]

    def __post_init__(self) -> None:
        if len(self.character_expected_dps) != 4:
            raise GcsimStatResponseError("response summary must cover four characters")
        counts = {
            self.duration_seconds.count,
            self.team_expected_damage.count,
            self.team_expected_dps.count,
            *(item.count for item in self.character_expected_dps),
        }
        if len(counts) != 1:
            raise GcsimStatResponseError("response summary counts are incoherent")


@dataclass(frozen=True, slots=True)
class GcsimStatResponseSample:
    seed: int
    duration_frames: int
    duration_seconds: float
    team_expected_damage: float
    team_expected_dps: float
    character_expected_damage: tuple[float, ...]
    character_expected_dps: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.seed <= 0 or self.duration_frames <= 0 or self.duration_seconds <= 0:
            raise GcsimStatResponseError("response sample seed/duration is invalid")
        if len(self.character_expected_damage) != 4 or len(self.character_expected_dps) != 4:
            raise GcsimStatResponseError("response sample must cover four characters")
        values = (
            self.duration_seconds,
            self.team_expected_damage,
            self.team_expected_dps,
            *self.character_expected_damage,
            *self.character_expected_dps,
        )
        if any(not isfinite(float(value)) for value in values):
            raise GcsimStatResponseError("response sample contains non-finite values")


@dataclass(frozen=True, slots=True)
class GcsimStatResponseObservation:
    observation_id: str
    samples: tuple[GcsimStatResponseSample, ...]
    summary: GcsimStatResponseSummary
    paired_delta: GcsimStatResponseSummary | None = None

    def __post_init__(self) -> None:
        if not self.observation_id or self.observation_id != self.observation_id.strip():
            raise GcsimStatResponseError("observation ID is invalid")
        if not self.samples or len(self.samples) != self.summary.team_expected_dps.count:
            raise GcsimStatResponseError("observation samples/summary are incoherent")
        seeds = tuple(item.seed for item in self.samples)
        if seeds != tuple(sorted(seeds)) or len(set(seeds)) != len(seeds):
            raise GcsimStatResponseError("observation seeds must be sorted and unique")


@dataclass(frozen=True, slots=True)
class GcsimStatResponseResult:
    context_sha256: str
    request_sha256: str
    objective: GcsimStatResponseObjective
    ignore_burst_energy: bool
    character_keys: tuple[str, ...]
    seed_panel_sha256: str
    source: GcsimStatResponseObservation
    baseline: GcsimStatResponseObservation
    interventions: tuple[GcsimStatResponseObservation, ...]
    schema_version: int = GCSIM_STAT_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_STAT_RESPONSE_SCHEMA_VERSION:
            raise GcsimStatResponseError("unsupported stat-response result schema")
        _require_sha256(self.context_sha256, "context_sha256")
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(self.seed_panel_sha256, "seed_panel_sha256")
        if self.ignore_burst_energy is not True:
            raise GcsimStatResponseError("optimizer response did not ignore burst energy")
        if len(self.character_keys) != 4 or len(set(self.character_keys)) != 4:
            raise GcsimStatResponseError("response character keys must cover the team")
        observations = (self.source, self.baseline, *self.interventions)
        expected_seeds = tuple(item.seed for item in self.source.samples)
        if any(tuple(sample.seed for sample in item.samples) != expected_seeds for item in observations):
            raise GcsimStatResponseError("response observations use different seed panels")
        if self.source.observation_id != "source" or self.source.paired_delta is not None:
            raise GcsimStatResponseError("source response observation is malformed")
        if self.baseline.observation_id != "baseline" or self.baseline.paired_delta is None:
            raise GcsimStatResponseError("synthetic baseline observation is malformed")
        if any(item.paired_delta is None for item in self.interventions):
            raise GcsimStatResponseError("response intervention lacks paired delta")

    @property
    def observation_by_id(self) -> Mapping[str, GcsimStatResponseObservation]:
        return {
            item.observation_id: item
            for item in (self.source, self.baseline, *self.interventions)
        }


def build_gcsim_stat_response_probe_request(
    *,
    context_sha256: str,
    objective: GcsimStatResponseObjective,
    iterations: int = 8,
    workers: int = 1,
    master_seed: int | None = None,
) -> GcsimStatResponseRequest:
    """Build the complete equal-baseline response panel for four characters."""

    _require_sha256(context_sha256, "context_sha256")
    baseline = tuple(
        GcsimStatResponseChange(
            character_index=character_index,
            stat=axis,
            mode=GcsimStatResponseChangeMode.SET,
            # Raw CR 0.95 plus the character base 0.05 removes short-run crit RNG.
            value=0.95 if axis == "cr" else 0.0,
        )
        for character_index in range(4)
        for axis in GCSIM_STAT_RESPONSE_ARTIFACT_AXES
    )
    interventions: list[GcsimStatResponseIntervention] = []
    for character_index in range(4):
        for axis, value in GCSIM_STAT_RESPONSE_MAIN_VALUES.items():
            # CR is measured by removing the guaranteed-crit reference below;
            # adding CR above 100% cannot affect expected damage.
            if axis == "cr":
                continue
            interventions.append(
                _single_add_intervention(
                    f"c{character_index}/main/{axis}",
                    character_index,
                    axis,
                    value,
                )
            )
        for axis, value in GCSIM_STAT_RESPONSE_ROLL_VALUES.items():
            if axis == "cr":
                continue
            interventions.append(
                _single_add_intervention(
                    f"c{character_index}/roll/{axis}",
                    character_index,
                    axis,
                    value,
                )
            )
        interventions.append(
            GcsimStatResponseIntervention(
                intervention_id=f"c{character_index}/crit/drop",
                changes=(
                    GcsimStatResponseChange(
                        character_index=character_index,
                        stat="cr",
                        mode=GcsimStatResponseChangeMode.SET,
                        value=0.0,
                    ),
                ),
            )
        )
    if master_seed is None:
        master_seed = int(context_sha256[:16], 16) % (2**63 - 1) or 1
    return GcsimStatResponseRequest(
        context_sha256=context_sha256,
        objective=objective,
        iterations=iterations,
        workers=workers,
        master_seed=master_seed,
        baseline_changes=baseline,
        interventions=tuple(interventions),
        ignore_burst_energy=True,
    )


def build_gcsim_stat_response_crit_relevance_request(
    response: GcsimStatResponseResult,
    *,
    iterations: int,
    workers: int,
    master_seed: int | None = None,
) -> GcsimStatResponseRequest:
    """Build the cheap second pass that judges crit on a complete synthetic team.

    The first pass discovers useful directions from a neutral state.  Judging
    crit there overstates a support's personal damage because the real damage
    dealers are also naked.  This pass equips every character with one legal
    main per variable slot plus a bounded equal roll budget, then removes crit
    from one character at a time.
    """

    observations = response.observation_by_id
    first_baseline_dps = max(
        response.baseline.summary.team_expected_dps.mean,
        1.0,
    )
    legal_by_slot = (
        ("sands", ("hp%", "atk%", "def%", "em", "er")),
        (
            "goblet",
            (
                "hp%",
                "atk%",
                "def%",
                "em",
                "pyro%",
                "hydro%",
                "electro%",
                "cryo%",
                "anemo%",
                "geo%",
                "dendro%",
                "phys%",
            ),
        ),
        ("circlet", ("hp%", "atk%", "def%", "em", "cr", "cd", "heal")),
    )
    baseline_values: list[dict[str, float]] = [
        {axis: 0.0 for axis in GCSIM_STAT_RESPONSE_ARTIFACT_AXES}
        for _ in range(4)
    ]
    for character_index, values in enumerate(baseline_values):
        # Flower/plume are fixed parts of a complete five-star build.
        values["hp"] = 4_780.0
        values["atk"] = 311.0
        values["cr"] = 0.95
        main_utility: dict[str, float] = {}
        crit_drop = observations[f"c{character_index}/crit/drop"]
        assert crit_drop.paired_delta is not None
        crit_full_loss = max(
            -crit_drop.paired_delta.team_expected_dps.mean,
            0.0,
        )
        for axis in GCSIM_STAT_RESPONSE_MAIN_VALUES:
            if axis == "cr":
                main_utility[axis] = (
                    crit_full_loss
                    * GCSIM_STAT_RESPONSE_MAIN_VALUES["cr"]
                    / 0.95
                )
            else:
                main_utility[axis] = _positive_paired_dps_utility(
                    observations[f"c{character_index}/main/{axis}"],
                    baseline_dps=first_baseline_dps,
                    scale=1.0,
                )
        for _slot, legal_axes in legal_by_slot:
            axis = max(
                legal_axes,
                key=lambda item: (main_utility.get(item, 0.0), item),
            )
            if main_utility.get(axis, 0.0) > 0:
                values[axis] += GCSIM_STAT_RESPONSE_MAIN_VALUES[axis]

        roll_rows: list[tuple[float, str]] = []
        for axis in GCSIM_STAT_RESPONSE_ROLL_VALUES:
            if axis == "cr":
                continue
            utility = _positive_paired_dps_utility(
                observations[f"c{character_index}/roll/{axis}"],
                baseline_dps=first_baseline_dps,
                scale=1.0,
            )
            if utility > 0:
                roll_rows.append((utility, axis))
        # Twenty liquid rolls, spread over at most four measured directions.
        # This is not a build recommendation; it only restores realistic team
        # damage shares before the crit-materiality decision.
        selected_rolls = tuple(
            axis
            for _utility, axis in sorted(
                roll_rows,
                key=lambda item: (-item[0], item[1]),
            )[:4]
        )
        if selected_rolls:
            for roll_index in range(20):
                axis = selected_rolls[roll_index % len(selected_rolls)]
                values[axis] += GCSIM_STAT_RESPONSE_ROLL_VALUES[axis]

    baseline = tuple(
        GcsimStatResponseChange(
            character_index=character_index,
            stat=axis,
            mode=GcsimStatResponseChangeMode.SET,
            value=values[axis],
        )
        for character_index, values in enumerate(baseline_values)
        for axis in GCSIM_STAT_RESPONSE_ARTIFACT_AXES
    )
    interventions = tuple(
        GcsimStatResponseIntervention(
            intervention_id=f"c{character_index}/crit/drop",
            changes=(
                GcsimStatResponseChange(
                    character_index=character_index,
                    stat="cr",
                    mode=GcsimStatResponseChangeMode.SET,
                    value=0.0,
                ),
            ),
        )
        for character_index in range(4)
    )
    context_sha256 = _canonical_sha256(
        {
            "schema_version": GCSIM_STAT_RESPONSE_SCHEMA_VERSION,
            "kind": "complete_synthetic_crit_relevance",
            "first_context_sha256": response.context_sha256,
            "first_request_sha256": response.request_sha256,
            "first_seed_panel_sha256": response.seed_panel_sha256,
        }
    )
    if master_seed is None:
        master_seed = int(context_sha256[:16], 16) % (2**63 - 1) or 1
    return GcsimStatResponseRequest(
        context_sha256=context_sha256,
        objective=response.objective,
        iterations=iterations,
        workers=workers,
        master_seed=master_seed,
        baseline_changes=baseline,
        interventions=interventions,
        ignore_burst_energy=True,
    )


def build_gcsim_stat_response_context_sha256(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    target: GcsimStatResponseTarget,
    package_identity_sha256: str,
) -> str:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimStatResponseError("engine_context must be typed")
    if not engine_context.trusted or engine_context.issues:
        raise GcsimStatResponseError("stat response requires a trusted engine")
    if not isinstance(prepared_config_text, str) or not prepared_config_text.strip():
        raise GcsimStatResponseError("prepared config must be non-empty")
    _require_sha256(package_identity_sha256, "package_identity_sha256")
    return _canonical_sha256(
        {
            "schema_version": GCSIM_STAT_RESPONSE_SCHEMA_VERSION,
            "engine_binding_sha256": engine_context.binding_sha256,
            "prepared_config_sha256": hashlib.sha256(
                prepared_config_text.encode("utf-8")
            ).hexdigest(),
            "target_sha256": target.target_sha256,
            "objective": target.objective.value,
            "package_identity_sha256": package_identity_sha256,
            "ignore_burst_energy": True,
        }
    )


def enforce_gcsim_optimizer_mvp_energy_policy(config: str) -> str:
    """Return an optimizer-only config where burst availability is unlimited.

    ER minimums remain candidate constraints.  This flag deliberately does not
    alter normal chamber runs outside the optimizer.
    """

    if not isinstance(config, str) or not config.strip():
        raise GcsimStatResponseError("optimizer config must be non-empty")
    options = re.search(r"(?im)^\s*options\b[^;]*;", config)
    if options is None:
        return "options ignore_burst_energy=true;\n" + config
    line = options.group(0)
    if re.search(r"(?i)\bignore_burst_energy\s*=", line):
        replacement = re.sub(
            r"(?i)\bignore_burst_energy\s*=\s*(?:true|false)",
            "ignore_burst_energy=true",
            line,
        )
    else:
        replacement = line[:-1].rstrip() + " ignore_burst_energy=true;"
    return config[: options.start()] + replacement + config[options.end() :]


def run_gcsim_stat_response(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    target: GcsimStatResponseTarget,
    request: GcsimStatResponseRequest,
    timeout_seconds: float = 300.0,
    environment: Mapping[str, str] | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    is_cancelled: Callable[[], bool] | None = None,
) -> GcsimStatResponseResult:
    """Run the paired batch in one temporary directory and validate all bytes."""

    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimStatResponseError("engine_context must be typed")
    if not engine_context.trusted or engine_context.issues:
        raise GcsimStatResponseError("stat response requires a trusted engine")
    if GCSIM_STAT_RESPONSE_CAPABILITY not in set(engine_context.capabilities):
        raise GcsimStatResponseError(
            "active GTT-GCSIM engine lacks gtt_stat_response_v2; rebuild it from the current patch stack"
        )
    if not isinstance(target, GcsimStatResponseTarget):
        raise GcsimStatResponseError("response target must be typed")
    if request.objective is not target.objective:
        raise GcsimStatResponseError("request objective differs from frozen target")
    if not isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise GcsimStatResponseError("response timeout must be finite and positive")
    expected_characters = _character_keys_from_prepared_config(prepared_config_text)
    with TemporaryDirectory(prefix="gtt-stat-response-v2-") as tmp:
        root = Path(tmp)
        config_path = root / "config.txt"
        request_path = root / "request.json"
        output_path = root / "result.json"
        config_path.write_text(prepared_config_text, encoding="utf-8")
        request_path.write_text(
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        command = [
            engine_context.artifact_path,
            "-c",
            str(config_path),
            "-gtt-stat-response",
            str(request_path),
            "-out",
            str(output_path),
        ]
        if target.wave_scenario_path:
            command.extend(("-gtt-wave-scenario", target.wave_scenario_path))
        try:
            if command_runner is subprocess.run and is_cancelled is not None:
                completed = _run_cancellable_response_command(
                    tuple(command),
                    cwd=engine_context.engine_root,
                    timeout_seconds=timeout_seconds,
                    environment=environment,
                    is_cancelled=is_cancelled,
                )
            else:
                completed = command_runner(
                    tuple(command),
                    cwd=engine_context.engine_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    env=None if environment is None else dict(environment),
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise GcsimStatResponseError(
                f"GTT-GCSIM stat response exceeded {timeout_seconds:g}s"
            ) from exc
        except OSError as exc:
            raise GcsimStatResponseError(
                f"could not start GTT-GCSIM stat response: {exc}"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise GcsimStatResponseError(
                f"GTT-GCSIM stat response exited with {completed.returncode}: {detail[:2000]}"
            )
        if not output_path.is_file():
            raise GcsimStatResponseError("GTT-GCSIM stat response produced no result")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GcsimStatResponseError(
                f"GTT-GCSIM stat response result is unreadable: {exc}"
            ) from exc
    result = parse_gcsim_stat_response_result(payload)
    if result.context_sha256 != request.context_sha256:
        raise GcsimStatResponseError("response context hash differs from request")
    if result.request_sha256 != request.request_sha256:
        raise GcsimStatResponseError("engine request hash differs from Python contract")
    if result.character_keys != expected_characters:
        raise GcsimStatResponseError(
            "response character order differs from the prepared config"
        )
    expected_ids = tuple(item.intervention_id for item in request.interventions)
    if tuple(item.observation_id for item in result.interventions) != expected_ids:
        raise GcsimStatResponseError("response intervention order differs from request")
    return result


def _run_cancellable_response_command(
    command: tuple[str, ...],
    *,
    cwd: str,
    timeout_seconds: float,
    environment: Mapping[str, str] | None,
    is_cancelled: Callable[[], bool],
) -> subprocess.CompletedProcess[str]:
    if is_cancelled():
        raise GcsimStatResponseCancelled(
            "GTT-GCSIM stat response was cancelled before start"
        )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=None if environment is None else dict(environment),
    )
    deadline = monotonic() + timeout_seconds
    while True:
        if is_cancelled():
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise GcsimStatResponseCancelled(
                "GTT-GCSIM stat response was cancelled"
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                command,
                timeout_seconds,
                output=stdout,
                stderr=stderr,
            )
        try:
            stdout, stderr = process.communicate(timeout=min(remaining, 0.2))
        except subprocess.TimeoutExpired:
            continue
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout,
            stderr,
        )


def derive_gcsim_optimizer_anytime_profiles_from_stat_response(
    result: GcsimStatResponseResult,
    wearers: Sequence[object],
    *,
    crit_relevance_result: GcsimStatResponseResult | None = None,
) -> tuple[object, ...]:
    """Translate paired response into the existing compact candidate kernel.

    Zero means measured-irrelevant, not "unknown but keep it just in case".
    Diversity profiles are created only around directions that the paired
    batch actually found useful.
    """

    from .optimizer_anytime_candidates import (
        GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
        GcsimOptimizerAnytimeStatProfile,
    )

    wearer_rows = tuple(wearers)
    if len(wearer_rows) != 4:
        raise GcsimStatResponseError("response profiles require four wearers")
    if tuple(getattr(item, "team_slot", None) for item in wearer_rows) != (1, 2, 3, 4):
        raise GcsimStatResponseError("response wearers must use canonical slots 1..4")
    if tuple(
        item.gcsim_character_key.casefold() for item in wearer_rows
    ) != tuple(item.casefold() for item in result.character_keys):
        raise GcsimStatResponseError(
            "response character order differs from the frozen wearer order"
        )
    if crit_relevance_result is not None and (
        crit_relevance_result.objective is not result.objective
        or crit_relevance_result.character_keys != result.character_keys
        or {
            item.observation_id
            for item in crit_relevance_result.interventions
        }
        != {f"c{index}/crit/drop" for index in range(4)}
    ):
        raise GcsimStatResponseError(
            "crit relevance response differs from the primary response team"
        )
    observations = result.observation_by_id
    crit_observations = (
        crit_relevance_result.observation_by_id
        if crit_relevance_result is not None
        else observations
    )
    crit_baseline_dps = max(
        (
            crit_relevance_result.baseline.summary.team_expected_dps.mean
            if crit_relevance_result is not None
            else result.baseline.summary.team_expected_dps.mean
        ),
        1.0,
    )
    baseline_dps = max(result.baseline.summary.team_expected_dps.mean, 1.0)
    evidence_sha256 = _canonical_sorted_sha256(
        {
            "schema_version": GCSIM_STAT_RESPONSE_SCHEMA_VERSION,
            "context_sha256": result.context_sha256,
            "request_sha256": result.request_sha256,
            "seed_panel_sha256": result.seed_panel_sha256,
            "crit_relevance_request_sha256": (
                crit_relevance_result.request_sha256
                if crit_relevance_result is not None
                else ""
            ),
            "crit_relevance_seed_panel_sha256": (
                crit_relevance_result.seed_panel_sha256
                if crit_relevance_result is not None
                else ""
            ),
            "character_keys": list(result.character_keys),
        }
    )
    all_profiles: list[object] = []
    legal_by_slot = {
        "sands": ("hp%", "atk%", "def%", "em", "er"),
        "goblet": (
            "hp%",
            "atk%",
            "def%",
            "em",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
            "phys%",
        ),
        "circlet": ("hp%", "atk%", "def%", "em", "cr", "cd", "heal"),
    }
    for character_index, wearer in enumerate(wearer_rows):
        utilities: dict[str, float] = {}
        stat_statuses: dict[str, str] = {
            axis: "negligible" for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        }
        for axis in GCSIM_STAT_RESPONSE_ROLL_VALUES:
            if axis == "cr":
                continue
            observation = observations[f"c{character_index}/roll/{axis}"]
            status, utility = _paired_response_classification(
                observation,
                baseline_dps=baseline_dps,
            )
            stat_statuses[axis] = status
            utilities[axis] = utility
        crit_drop = crit_observations[f"c{character_index}/crit/drop"]
        assert crit_drop.paired_delta is not None
        crit_status, crit_full_loss = _paired_response_classification(
            crit_drop,
            baseline_dps=crit_baseline_dps,
            direction=-1.0,
            relative_threshold=0.005,
        )
        crit_material = crit_status in {"dominant", "secondary"}
        stat_statuses["cr"] = crit_status
        utilities["cr"] = (
            crit_full_loss * GCSIM_STAT_RESPONSE_ROLL_VALUES["cr"] / 0.95
            if crit_material
            else 0.0
        )
        _promote_relative_response_statuses(stat_statuses, utilities)
        base_weights = tuple(
            (
                utilities.get(axis, 0.0)
                / GCSIM_STAT_RESPONSE_ROLL_VALUES[axis]
                if axis in GCSIM_STAT_RESPONSE_ROLL_VALUES
                else 0.0
            )
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )

        main_utility: dict[str, float] = {}
        main_statuses: dict[str, str] = {}
        for axis in GCSIM_STAT_RESPONSE_MAIN_VALUES:
            if axis == "cr":
                main_statuses[axis] = crit_status
                main_utility[axis] = (
                    crit_full_loss
                    * GCSIM_STAT_RESPONSE_MAIN_VALUES["cr"]
                    / 0.95
                    if crit_material
                    else 0.0
                )
                continue
            status, utility = _paired_response_classification(
                observations[f"c{character_index}/main/{axis}"],
                baseline_dps=baseline_dps,
            )
            main_statuses[axis] = status
            main_utility[axis] = utility
        _promote_relative_response_statuses(main_statuses, main_utility)
        main_scores = tuple(
            (slot, axis, main_utility.get(axis, 0.0))
            for slot, axes in legal_by_slot.items()
            for axis in axes
        )
        useful_axes = tuple(
            axis
            for axis, utility in sorted(
                utilities.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if stat_statuses[axis] in {"dominant", "secondary"}
        )
        labels = ["paired_response_v2", "equal_synthetic_baseline"]
        if not crit_material:
            labels.append("crit_immaterial")
        useful_mains = tuple(
            axis
            for axis, utility in sorted(
                main_utility.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if main_statuses[axis] in {"dominant", "secondary"}
        )
        if len(useful_mains) == 1:
            labels.append(f"any_{useful_mains[0]}_main")

        variants: list[tuple[str, dict[str, float], tuple[str, ...]]] = [
            ("balanced", {}, ()),
        ]
        if utilities.get("cr", 0.0) > 0 and utilities.get("cd", 0.0) > 0:
            variants.extend(
                (
                    ("crit_chance", {"cr": 1.45, "cd": 0.85}, ("crit_balance",)),
                    ("crit_damage", {"cr": 0.85, "cd": 1.35}, ("crit_balance",)),
                )
            )
        for axis in tuple(
            item for item in useful_axes if item not in {"cr", "cd"}
        )[:2]:
            variants.append(
                (
                    f"focus_{axis.replace('%', 'pct')}",
                    {axis: 1.35},
                    (f"response_focus:{axis}",),
                )
            )

        seen_profiles: set[tuple[tuple[float, ...], tuple[tuple[str, str, float], ...]]] = set()
        for profile_id, multipliers, extra_labels in variants:
            weights = tuple(
                value * multipliers.get(axis, 1.0)
                for axis, value in zip(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                    base_weights,
                    strict=True,
                )
            )
            scaled_mains = tuple(
                (slot, axis, score * multipliers.get(axis, 1.0))
                for slot, axis, score in main_scores
            )
            identity = (weights, scaled_mains)
            if identity in seen_profiles:
                continue
            seen_profiles.add(identity)
            all_profiles.append(
                GcsimOptimizerAnytimeStatProfile(
                    wearer=wearer,
                    profile_id=profile_id,
                    stat_weights=weights,
                    main_scores=scaled_mains,
                    evidence_sha256=evidence_sha256,
                    feature_labels=tuple((*labels, *extra_labels)),
                    stat_classifications=tuple(
                        (axis, stat_statuses[axis])
                        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                    ),
                    main_classifications=tuple(
                        (slot, axis, main_statuses[axis])
                        for slot, axes in legal_by_slot.items()
                        for axis in axes
                    ),
                )
            )
    return tuple(all_profiles)


def parse_gcsim_stat_response_result(payload: object) -> GcsimStatResponseResult:
    root = _mapping(payload, "response result")
    _require_keys(
        root,
        {
            "schema_version",
            "context_sha256",
            "request_sha256",
            "objective",
            "ignore_burst_energy",
            "character_keys",
            "seed_panel_sha256",
            "source",
            "baseline",
            "interventions",
        },
        "response result",
    )
    try:
        objective = GcsimStatResponseObjective(root["objective"])
    except (TypeError, ValueError) as exc:
        raise GcsimStatResponseError("response objective is invalid") from exc
    return GcsimStatResponseResult(
        schema_version=_integer(root["schema_version"], "schema_version"),
        context_sha256=str(root["context_sha256"]),
        request_sha256=str(root["request_sha256"]),
        objective=objective,
        ignore_burst_energy=_boolean(
            root["ignore_burst_energy"], "ignore_burst_energy"
        ),
        character_keys=tuple(str(item) for item in _sequence(root["character_keys"], "character_keys")),
        seed_panel_sha256=str(root["seed_panel_sha256"]),
        source=_parse_observation(root["source"]),
        baseline=_parse_observation(root["baseline"]),
        interventions=tuple(
            _parse_observation(item)
            for item in _sequence(root["interventions"], "interventions")
        ),
    )


def _parse_observation(payload: object) -> GcsimStatResponseObservation:
    value = _mapping(payload, "observation")
    allowed = {"id", "samples", "summary", "paired_delta"}
    if set(value) - allowed or not {"id", "samples", "summary"}.issubset(value):
        raise GcsimStatResponseError("observation fields are invalid")
    paired = value.get("paired_delta")
    return GcsimStatResponseObservation(
        observation_id=str(value["id"]),
        samples=tuple(
            _parse_sample(item)
            for item in _sequence(value["samples"], "samples")
        ),
        summary=_parse_summary(value["summary"]),
        paired_delta=None if paired is None else _parse_summary(paired),
    )


def _positive_paired_dps_utility(
    observation: GcsimStatResponseObservation,
    *,
    baseline_dps: float,
    scale: float,
) -> float:
    paired = observation.paired_delta
    if paired is None:
        raise GcsimStatResponseError(
            f"observation {observation.observation_id!r} lacks paired delta"
        )
    estimate = paired.team_expected_dps
    # A half-SE discount avoids treating ordinary noise as useful while still
    # preserving modest real directions in the short diagnostic batch.
    conservative = estimate.mean - 0.5 * estimate.standard_error
    threshold = max(baseline_dps * 0.00005, 1.0)
    if conservative <= threshold:
        return 0.0
    return conservative * scale


def _paired_response_classification(
    observation: GcsimStatResponseObservation,
    *,
    baseline_dps: float,
    direction: float = 1.0,
    relative_threshold: float = 0.00005,
) -> tuple[str, float]:
    """Classify paired evidence without turning uncertainty into zero-value proof."""

    paired = observation.paired_delta
    if paired is None:
        raise GcsimStatResponseError(
            f"observation {observation.observation_id!r} lacks paired delta"
        )
    estimate = paired.team_expected_dps
    mean = estimate.mean * direction
    standard_error = estimate.standard_error
    threshold = max(baseline_dps * relative_threshold, 1.0)
    useful_lower_bound = mean - 0.5 * standard_error
    negligible_upper_bound = mean + 2.0 * standard_error
    if useful_lower_bound > threshold:
        return "secondary", useful_lower_bound
    if negligible_upper_bound <= threshold:
        return "negligible", 0.0
    return "uncertain", 0.0


def _promote_relative_response_statuses(
    statuses: dict[str, str],
    utilities: Mapping[str, float],
) -> None:
    useful = tuple(
        value
        for axis, value in utilities.items()
        if statuses.get(axis) == "secondary" and value > 0
    )
    if not useful:
        return
    dominant_floor = max(useful) * 0.8
    for axis, value in utilities.items():
        if statuses.get(axis) == "secondary" and value >= dominant_floor:
            statuses[axis] = "dominant"


def _parse_sample(payload: object) -> GcsimStatResponseSample:
    value = _mapping(payload, "sample")
    _require_keys(
        value,
        {
            "seed",
            "duration_frames",
            "duration_seconds",
            "team_expected_damage",
            "team_expected_dps",
            "character_expected_damage",
            "character_expected_dps",
        },
        "sample",
    )
    try:
        seed = int(str(value["seed"]), 10)
    except ValueError as exc:
        raise GcsimStatResponseError("sample seed is invalid") from exc
    return GcsimStatResponseSample(
        seed=seed,
        duration_frames=_integer(value["duration_frames"], "duration_frames"),
        duration_seconds=_number(value["duration_seconds"], "duration_seconds"),
        team_expected_damage=_number(value["team_expected_damage"], "team_expected_damage"),
        team_expected_dps=_number(value["team_expected_dps"], "team_expected_dps"),
        character_expected_damage=tuple(
            _number(item, "character_expected_damage")
            for item in _sequence(value["character_expected_damage"], "character_expected_damage")
        ),
        character_expected_dps=tuple(
            _number(item, "character_expected_dps")
            for item in _sequence(value["character_expected_dps"], "character_expected_dps")
        ),
    )


def _parse_summary(payload: object) -> GcsimStatResponseSummary:
    value = _mapping(payload, "summary")
    _require_keys(
        value,
        {
            "duration_seconds",
            "team_expected_damage",
            "team_expected_dps",
            "character_expected_dps",
        },
        "summary",
    )
    return GcsimStatResponseSummary(
        duration_seconds=_parse_estimate(value["duration_seconds"]),
        team_expected_damage=_parse_estimate(value["team_expected_damage"]),
        team_expected_dps=_parse_estimate(value["team_expected_dps"]),
        character_expected_dps=tuple(
            _parse_estimate(item)
            for item in _sequence(value["character_expected_dps"], "character_expected_dps")
        ),
    )


def _parse_estimate(payload: object) -> GcsimStatResponseEstimate:
    value = _mapping(payload, "estimate")
    _require_keys(
        value,
        {"count", "mean", "sample_sd", "standard_error"},
        "estimate",
    )
    return GcsimStatResponseEstimate(
        count=_integer(value["count"], "count"),
        mean=_number(value["mean"], "mean"),
        sample_sd=_number(value["sample_sd"], "sample_sd"),
        standard_error=_number(value["standard_error"], "standard_error"),
    )


def _single_add_intervention(
    intervention_id: str,
    character_index: int,
    stat: str,
    value: float,
) -> GcsimStatResponseIntervention:
    return GcsimStatResponseIntervention(
        intervention_id=intervention_id,
        changes=(
            GcsimStatResponseChange(
                character_index=character_index,
                stat=stat,
                mode=GcsimStatResponseChangeMode.ADD,
                value=value,
            ),
        ),
    )


def _validate_change_panel(
    changes: Sequence[GcsimResponseChange],
    *,
    allow_empty: bool,
) -> None:
    if (not allow_empty and not changes) or len(changes) > 128:
        raise GcsimStatResponseError("response change panel must contain 1..128 changes")
    if any(
        not isinstance(
            item,
            (GcsimStatResponseChange, GcsimSetResponseChange),
        )
        for item in changes
    ):
        raise GcsimStatResponseError("response changes must be typed")
    keys = tuple(
        (
            item.character_index,
            (
                f"stat:{item.stat}"
                if isinstance(item, GcsimStatResponseChange)
                else f"set:{item.set_key}"
            ),
        )
        for item in changes
    )
    if len(set(keys)) != len(keys):
        raise GcsimStatResponseError(
            "response change panel repeats a character stat/set"
        )


def _character_keys_from_prepared_config(config: str) -> tuple[str, ...]:
    import re

    keys = tuple(
        match.group(1).casefold()
        for match in re.finditer(
            r"(?m)^\s*([A-Za-z][A-Za-z0-9_]*)\s+char\b",
            config,
        )
    )
    if len(keys) != 4 or len(set(keys)) != 4:
        raise GcsimStatResponseError(
            "prepared response config must contain four unique character declarations"
        )
    return keys


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise GcsimStatResponseError(f"{name} must be a JSON object")
    return value


def _sequence(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise GcsimStatResponseError(f"{name} must be a JSON array")
    return value


def _require_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise GcsimStatResponseError(f"{name} fields differ from schema v2")


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GcsimStatResponseError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GcsimStatResponseError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise GcsimStatResponseError(f"{name} must be finite")
    return result


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise GcsimStatResponseError(f"{name} must be boolean")
    return value


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _canonical_sorted_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimStatResponseError(f"{field_name} must be lowercase SHA-256")


__all__ = [
    "GCSIM_STAT_RESPONSE_ARTIFACT_AXES",
    "GCSIM_STAT_RESPONSE_CAPABILITY",
    "GCSIM_STAT_RESPONSE_MAIN_VALUES",
    "GCSIM_STAT_RESPONSE_ROLL_VALUES",
    "GCSIM_STAT_RESPONSE_SCHEMA_VERSION",
    "GCSIM_SET_RESPONSE_CAPABILITY",
    "GcsimResponseChange",
    "GcsimSetResponseChange",
    "GcsimStatResponseChange",
    "GcsimStatResponseChangeMode",
    "GcsimStatResponseCancelled",
    "GcsimStatResponseError",
    "GcsimStatResponseEstimate",
    "GcsimStatResponseIntervention",
    "GcsimStatResponseObjective",
    "GcsimStatResponseObservation",
    "GcsimStatResponseRequest",
    "GcsimStatResponseResult",
    "GcsimStatResponseSample",
    "GcsimStatResponseSummary",
    "GcsimStatResponseTarget",
    "build_gcsim_stat_response_context_sha256",
    "build_gcsim_stat_response_crit_relevance_request",
    "build_gcsim_stat_response_probe_request",
    "derive_gcsim_optimizer_anytime_profiles_from_stat_response",
    "enforce_gcsim_optimizer_mvp_energy_policy",
    "parse_gcsim_stat_response_result",
    "run_gcsim_stat_response",
]
