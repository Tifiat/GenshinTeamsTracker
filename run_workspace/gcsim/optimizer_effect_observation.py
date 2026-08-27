"""Typed Python contract for engine capability ``gtt_effect_observation_v1``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_stat_response import (
    GcsimResponseChange,
    GcsimStatResponseIntervention,
    GcsimStatResponseObjective,
    GcsimStatResponseTarget,
)


GCSIM_EFFECT_OBSERVATION_SCHEMA_VERSION = 1
GCSIM_EFFECT_OBSERVATION_CAPABILITY = "gtt_effect_observation_v1"


class GcsimEffectObservationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GcsimEffectObservationRequest:
    context_sha256: str
    objective: GcsimStatResponseObjective
    iterations: int
    workers: int
    master_seed: int
    baseline_changes: tuple[GcsimResponseChange, ...]
    interventions: tuple[GcsimStatResponseIntervention, ...]
    ignore_burst_energy: bool = True
    schema_version: int = GCSIM_EFFECT_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if len(self.context_sha256) != 64 or self.context_sha256.casefold() != self.context_sha256:
            raise GcsimEffectObservationError("invalid context SHA-256")
        if not 1 <= self.iterations <= 1024 or not 1 <= self.workers <= min(64, self.iterations):
            raise GcsimEffectObservationError("invalid iterations/workers")
        if not 0 <= len(self.interventions) <= 256:
            raise GcsimEffectObservationError("effect batch exceeds 256 interventions")
        if self.master_seed <= 0 or not self.ignore_burst_energy:
            raise GcsimEffectObservationError("invalid aligned-seed/energy policy")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context_sha256": self.context_sha256,
            "objective": self.objective.value,
            "iterations": self.iterations,
            "workers": self.workers,
            "master_seed": str(self.master_seed),
            "ignore_burst_energy": self.ignore_burst_energy,
            "baseline_changes": [x.to_dict() for x in self.baseline_changes],
            "interventions": [x.to_dict() for x in self.interventions],
        }

    @property
    def request_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class GcsimEffectExposure:
    character_index: int
    element: str
    attack_tag: int
    reaction: str
    time_bucket: int
    expected_damage: float
    hit_count: int
    snapshot_stats: Mapping[str, float]
    effective_resistance: float
    effective_defense_multiplier: float
    effective_reaction_multiplier: float
    active_stat_modifiers: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class GcsimEffectTransition:
    frame: int
    character_index: int
    modifier_key: str
    transition: str
    expiry_frame: int
    duration_frames: int
    stat_amounts: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class GcsimEffectSample:
    seed: int
    duration_frames: int
    team_expected_dps: float
    character_expected_dps: tuple[float, float, float, float]
    exposures: tuple[GcsimEffectExposure, ...]
    transitions: tuple[GcsimEffectTransition, ...]


@dataclass(frozen=True, slots=True)
class GcsimEffectObservationRow:
    observation_id: str
    samples: tuple[GcsimEffectSample, ...]
    paired_team_mean: float | None
    paired_team_se: float | None


@dataclass(frozen=True, slots=True)
class GcsimEffectObservationResult:
    context_sha256: str
    request_sha256: str
    character_keys: tuple[str, str, str, str]
    seed_panel_sha256: str
    baseline: GcsimEffectObservationRow
    interventions: tuple[GcsimEffectObservationRow, ...]

    @property
    def observation_by_id(self) -> Mapping[str, GcsimEffectObservationRow]:
        return {self.baseline.observation_id: self.baseline, **{x.observation_id: x for x in self.interventions}}


def run_gcsim_effect_observation(*, engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str, target: GcsimStatResponseTarget,
    request: GcsimEffectObservationRequest, timeout_seconds: float = 180.0) -> GcsimEffectObservationResult:
    if not engine_context.trusted or GCSIM_EFFECT_OBSERVATION_CAPABILITY not in engine_context.capabilities:
        raise GcsimEffectObservationError("trusted engine with gtt_effect_observation_v1 required")
    if target.objective is not request.objective:
        raise GcsimEffectObservationError("target objective mismatch")
    with TemporaryDirectory(prefix="gtt-effect-observation-v1-") as tmp:
        root = Path(tmp); config = root / "config.txt"; req = root / "request.json"; out = root / "result.json"
        config.write_text(prepared_config_text, encoding="utf-8")
        req.write_text(json.dumps(request.to_dict(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        command = [engine_context.artifact_path, "-c", str(config), "-gtt-effect-observation", str(req), "-out", str(out)]
        if target.wave_scenario_path: command += ["-gtt-wave-scenario", target.wave_scenario_path]
        try:
            completed = subprocess.run(command, cwd=engine_context.engine_root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise GcsimEffectObservationError(f"effect observation exceeded {timeout_seconds:g}s") from exc
        if completed.returncode != 0:
            raise GcsimEffectObservationError((completed.stderr or completed.stdout or "")[:2000])
        payload = json.loads(out.read_text(encoding="utf-8"))
    result = parse_gcsim_effect_observation_result(payload)
    if result.context_sha256 != request.context_sha256 or result.request_sha256 != request.request_sha256:
        raise GcsimEffectObservationError("effect observation identity mismatch")
    return result


def parse_gcsim_effect_observation_result(payload: object) -> GcsimEffectObservationResult:
    root = _map(payload)
    if root.get("schema_version") != 1 or root.get("capability") != GCSIM_EFFECT_OBSERVATION_CAPABILITY:
        raise GcsimEffectObservationError("unsupported effect observation payload")
    return GcsimEffectObservationResult(
        context_sha256=str(root["context_sha256"]), request_sha256=str(root["request_sha256"]),
        character_keys=tuple(str(x) for x in root["character_keys"]), seed_panel_sha256=str(root["seed_panel_sha256"]),
        baseline=_parse_row(root["baseline"]), interventions=tuple(_parse_row(x) for x in root["interventions"]),
    )


def affected_expected_damage(row: GcsimEffectObservationRow, modifier_group: str) -> float:
    """Damage exposure carrying a canonical/raw modifier group.

    Activations with no subsequent affected hit intentionally return zero.
    """

    total = 0.0
    for sample in row.samples:
        for exposure in sample.exposures:
            if any(str(mod.get("modifier_key", "")) == modifier_group for mod in exposure.active_stat_modifiers):
                total += exposure.expected_damage
    return total


def marechaussee_stack_count(exposure: GcsimEffectExposure) -> int | None:
    for modifier in exposure.active_stat_modifiers:
        if modifier.get("modifier_key") != "mh-4pc": continue
        amounts = _map(modifier.get("stat_amounts", {}))
        value = float(amounts.get("cr", 0.0))
        stacks = round(value / 0.12)
        return stacks if stacks in range(4) and abs(value - 0.12 * stacks) < 1e-9 else None
    return 0


def _parse_row(value: object) -> GcsimEffectObservationRow:
    row = _map(value); paired = row.get("paired_delta")
    return GcsimEffectObservationRow(str(row["id"]), tuple(_parse_sample(x) for x in row["samples"]),
        None if paired is None else float(_map(_map(paired)["team_expected_dps"])["mean"]),
        None if paired is None else float(_map(_map(paired)["team_expected_dps"])["standard_error"]))


def _parse_sample(value: object) -> GcsimEffectSample:
    row = _map(value); obs = _map(row["effect_observation"])
    exposures = tuple(GcsimEffectExposure(
        int(x["character_index"]), str(x["element"]), int(x["attack_tag"]), str(x["reaction"]), int(x["time_bucket"]),
        float(x["expected_damage"]), int(x["hit_count"]), _map(x["damage_weighted_snapshot_stats"]),
        float(x["damage_weighted_effective_resistance"]), float(x["damage_weighted_effective_defense_multiplier"]),
        float(x["damage_weighted_effective_reaction_multiplier"]), tuple(_map(m) for m in x["active_stat_modifiers"]))
        for x in (_map(v) for v in obs["exposures"]))
    transitions = tuple(GcsimEffectTransition(int(x["frame"]), int(x["character_index"]), str(x["modifier_key"]),
        str(x["transition"]), int(x["expiry_frame"]), int(x["duration_frames"]), _map(x["stat_amounts"]))
        for x in (_map(v) for v in obs["modifier_transitions"]))
    dps = tuple(float(x) for x in row["character_expected_dps"])
    if len(dps) != 4: raise GcsimEffectObservationError("effect sample must cover four characters")
    return GcsimEffectSample(int(row["seed"]), int(row["duration_frames"]), float(row["team_expected_dps"]), dps, exposures, transitions)


def _map(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping): raise GcsimEffectObservationError("expected typed object")
    return value


__all__ = [name for name in globals() if name.startswith("Gcsim") or name.startswith("run_gcsim") or name.startswith("parse_gcsim") or name.startswith("GCSIM_")]
