"""Live same-context acceptance for the FAST trace-equation evaluator.

This module intentionally owns no optimizer search.  It proves that one exact
current-equipment config is consumed by both the one-seed trace/FAST path and a
normal GCSIM run.  Every identity check is fail-closed; historical results and
saved development traces are not accepted inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from time import perf_counter
from typing import Any

from hoyolab_export.account_storage import DEFAULT_ACCOUNT_DB_PATH

from ..account_prepared_config import (
    DEFAULT_ACCOUNT_CHASCA_TEAM,
    build_account_prepared_full_config_report,
)
from ..artifact_runner import parse_gcsim_result_file
from ..engine_store import load_engine_manifest
from ..optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    load_gcsim_optimizer_artifact_database_input,
)
from ..optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from ..optimizer_engine_context import (
    GcsimOptimizerEngineContext,
    load_active_gcsim_optimizer_engine_context,
)
from ..optimizer_stat_response import enforce_gcsim_optimizer_mvp_energy_policy
from ..optimizer_trace_selected_candidates import (
    SelectedEquippedTeamSnapshot,
    load_selected_equipped_team_snapshot,
)
from ..prepared_config_adapter import CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH
from .coarse_rotation_objective import (
    RotationFormulaMode,
    compile_rotation_formula_filters,
    evaluate_rotation_formula_filter,
)
from .contracts import (
    TraceContractError,
    TraceExtractionRequest,
    TraceObjective,
    canonical_json,
    canonical_sha256,
)
from .engine_adapter import decode_engine_trace_v6
from .source_dependencies import (
    SourceManifestBinding,
    decode_source_manifest_body,
)


SAME_CONTEXT_ACCEPTANCE_KIND = "gtt.trace_equation.same_context_acceptance"
SAME_CONTEXT_ACCEPTANCE_SCHEMA_VERSION = 1
DEFAULT_TRACE_SEED = 742_031_889
DEFAULT_GCSIM_ITERATIONS = 1000
DEFAULT_RELATIVE_TOLERANCE = 0.01
DEFAULT_STANDARD_ERROR_MULTIPLIER = 3.0

_OPTIONS_RE = re.compile(r"(?im)^\s*options\b(?P<body>[^;]*);")
_ITERATION_RE = re.compile(r"(?i)\biteration\s*=\s*(\d+)")
_TARGET_RE = re.compile(r"(?im)^\s*target\b[^;]*;")
_CHARACTER_RE = re.compile(r"(?im)^\s*([a-z0-9_]+)\s+char\b")
_STATS_RE = re.compile(
    r"(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+stats\s+(?P<body>[^;]+);"
)
_STAT_TOKEN_RE = re.compile(r"(?P<key>[a-z]+%?)=(?P<value>[-+0-9.eE]+)")
_SET_RE = re.compile(
    r'(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+set="(?P<set>[^"]+)"'
    r"\s+count=(?P<count>\d+);"
)


@dataclass(frozen=True, slots=True)
class SameContextWearerInput:
    actor_key: str
    artifact_ids_by_slot: tuple[tuple[str, int], ...]
    aggregate_artifact_stats: tuple[tuple[str, float], ...]
    active_sets: tuple[tuple[str, int], ...]

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(value for _slot, value in self.artifact_ids_by_slot)

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "artifact_ids_by_slot": dict(self.artifact_ids_by_slot),
            "aggregate_artifact_stats": dict(self.aggregate_artifact_stats),
            "active_sets": dict(self.active_sets),
        }


@dataclass(frozen=True, slots=True)
class SameContextAcceptanceInput:
    database_path: str
    engine_store_dir: str
    rotation_shell_path: str
    rotation_shell_sha256: str
    config_text: str
    config_file_sha256: str
    engine_source_config_sha256: str
    context_sha256: str
    target_contract_sha256: str
    target_line: str
    iterations: int
    ignore_burst_energy: bool
    engine_context: GcsimOptimizerEngineContext
    snapshot: SelectedEquippedTeamSnapshot
    wearers: tuple[SameContextWearerInput, ...]

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(
            artifact_id
            for wearer in self.wearers
            for artifact_id in wearer.artifact_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "engine_store_dir": self.engine_store_dir,
            "rotation_shell_path": self.rotation_shell_path,
            "rotation_shell_sha256": self.rotation_shell_sha256,
            "config_file_sha256": self.config_file_sha256,
            "engine_source_config_sha256": self.engine_source_config_sha256,
            "context_sha256": self.context_sha256,
            "target_contract_sha256": self.target_contract_sha256,
            "target_line": self.target_line,
            "iterations": self.iterations,
            "ignore_burst_energy": self.ignore_burst_energy,
            "engine_id": self.engine_context.engine_id,
            "engine_artifact_sha256": self.engine_context.artifact_sha256,
            "engine_binding_sha256": self.engine_context.binding_sha256,
            "artifact_database_input_sha256": (
                self.snapshot.artifact_database_input_sha256
            ),
            "equipment_rows_sha256": self.snapshot.equipment_rows_sha256,
            "snapshot_sha256": self.snapshot.snapshot_sha256,
            "artifact_count": len(self.artifact_ids),
            "artifact_ids": list(self.artifact_ids),
            "wearers": [wearer.to_dict() for wearer in self.wearers],
        }


@dataclass(frozen=True, slots=True)
class SameContextAcceptanceResult:
    acceptance_input: SameContextAcceptanceInput
    trace_source_config_sha256: str
    trace_target_sha256: str
    trace_raw_payload_sha256: str
    trace_duration_frames: int
    trace_hit_count: int
    fast_channel_count: int
    standard_group_count: int
    fast_dps: float
    fast_damage: float
    fast_damage_by_actor: tuple[tuple[str, float], ...]
    gcsim_dps_mean: float
    gcsim_dps_se: float
    gcsim_iterations: int
    absolute_error_dps: float
    relative_error: float
    relative_tolerance_dps: float
    statistical_tolerance_dps: float
    allowed_error_dps: float
    passed: bool
    run_dir: str
    timings_seconds: tuple[tuple[str, float], ...]
    schema_version: int = SAME_CONTEXT_ACCEPTANCE_SCHEMA_VERSION
    kind: str = SAME_CONTEXT_ACCEPTANCE_KIND

    @property
    def acceptance_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "input": self.acceptance_input.to_dict(),
            "trace_source_config_sha256": self.trace_source_config_sha256,
            "trace_target_sha256": self.trace_target_sha256,
            "trace_raw_payload_sha256": self.trace_raw_payload_sha256,
            "trace_duration_frames": self.trace_duration_frames,
            "trace_hit_count": self.trace_hit_count,
            "fast_channel_count": self.fast_channel_count,
            "standard_group_count": self.standard_group_count,
            "fast_dps": self.fast_dps,
            "fast_damage": self.fast_damage,
            "fast_damage_by_actor": dict(self.fast_damage_by_actor),
            "gcsim_dps_mean": self.gcsim_dps_mean,
            "gcsim_dps_se": self.gcsim_dps_se,
            "gcsim_iterations": self.gcsim_iterations,
            "absolute_error_dps": self.absolute_error_dps,
            "relative_error": self.relative_error,
            "relative_error_percent": self.relative_error * 100.0,
            "relative_tolerance_dps": self.relative_tolerance_dps,
            "statistical_tolerance_dps": self.statistical_tolerance_dps,
            "allowed_error_dps": self.allowed_error_dps,
            "passed": self.passed,
            "run_dir": self.run_dir,
            "timings_seconds": dict(self.timings_seconds),
        }
        if include_hash:
            row["acceptance_sha256"] = self.acceptance_sha256
        return row


def build_current_same_context_acceptance_input(
    *,
    engine_store_dir: str | Path,
    database_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    rotation_shell_path: str | Path = (
        CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH
    ),
    team_names: tuple[str, ...] = DEFAULT_ACCOUNT_CHASCA_TEAM,
    iterations: int = DEFAULT_GCSIM_ITERATIONS,
) -> SameContextAcceptanceInput:
    """Materialize and identity-bind one exact current-equipment config."""

    if iterations != DEFAULT_GCSIM_ITERATIONS:
        raise TraceContractError("same-context acceptance requires n=1000")
    database = Path(database_path).expanduser().resolve()
    rotation = Path(rotation_shell_path).expanduser().resolve()
    store = Path(engine_store_dir).expanduser().resolve()
    if not database.is_file():
        raise TraceContractError("same-context artifact database is missing")
    if not rotation.is_file():
        raise TraceContractError("same-context rotation shell is missing")

    context = load_active_gcsim_optimizer_engine_context(store_dir=store)
    if not context.trusted or context.issues:
        raise TraceContractError("same-context engine binding is not trusted")

    report = build_account_prepared_full_config_report(
        db_path=database,
        team_names=team_names,
        rotation_shell_path=rotation,
        write_config=False,
    )
    if not report.ready or report.issues:
        raise TraceContractError(
            f"same-context prepared config is not ready: {report.issues!r}"
        )
    if any(
        row.weapon_selection_method != "current_equipped_weapon"
        for row in report.team.characters
    ):
        raise TraceContractError(
            "same-context config requires current equipped weapons"
        )

    config_text = enforce_gcsim_optimizer_mvp_energy_policy(
        report.full_config.assembly.config_text
    )
    _require_exact_iteration(config_text, iterations)
    character_keys = tuple(key.casefold() for key in _config_character_keys(config_text))
    expected_keys = tuple(
        str(character["mapping"]["gcsim_key"]).casefold()
        for character in report.team.payload.get("characters", ())
    )
    if character_keys != expected_keys or len(character_keys) != 4:
        raise TraceContractError("same-context character order mismatch")

    loaded = load_gcsim_optimizer_artifact_database_input(
        database,
        engine_context=context,
    )
    if not loaded.ready or loaded.database_input is None:
        raise TraceContractError(
            f"same-context artifact database is not ready: {loaded.issues!r}"
        )
    artifact_database = loaded.database_input
    snapshot = load_selected_equipped_team_snapshot(
        database,
        artifact_database=artifact_database,
        character_keys=character_keys,
    )
    wearers = bind_report_config_and_snapshot(
        report.team.payload,
        config_text=config_text,
        artifact_database=artifact_database,
        snapshot=snapshot,
    )
    artifact_ids = tuple(
        artifact_id
        for wearer in wearers
        for artifact_id in wearer.artifact_ids
    )
    if len(artifact_ids) != 20 or len(set(artifact_ids)) != 20:
        raise TraceContractError(
            "same-context acceptance requires twenty unique artifact IDs"
        )

    target_matches = tuple(match.group(0).strip() for match in _TARGET_RE.finditer(config_text))
    if len(target_matches) != 1:
        raise TraceContractError("same-context config requires one target line")
    target_line = target_matches[0]
    target_contract_sha256 = canonical_sha256(
        {"kind": "gtt.same_context.target.v1", "line": target_line}
    )
    rotation_sha256 = _sha256_bytes(rotation.read_bytes())
    config_file_sha256 = _sha256_text(config_text)
    engine_source_config_sha256 = _sha256_text(
        _gcsim_single_file_resolved_config(config_text)
    )
    context_sha256 = canonical_sha256(
        {
            "kind": "gtt.trace_equation.same_context_input.v1",
            "engine_artifact_sha256": context.artifact_sha256,
            "engine_binding_sha256": context.binding_sha256,
            "artifact_database_input_sha256": (
                snapshot.artifact_database_input_sha256
            ),
            "equipment_rows_sha256": snapshot.equipment_rows_sha256,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "artifact_ids": list(artifact_ids),
            "config_file_sha256": config_file_sha256,
            "engine_source_config_sha256": engine_source_config_sha256,
            "rotation_shell_sha256": rotation_sha256,
            "target_contract_sha256": target_contract_sha256,
            "iterations": iterations,
            "ignore_burst_energy": True,
        }
    )
    return SameContextAcceptanceInput(
        database_path=str(database),
        engine_store_dir=str(store),
        rotation_shell_path=str(rotation),
        rotation_shell_sha256=rotation_sha256,
        config_text=config_text,
        config_file_sha256=config_file_sha256,
        engine_source_config_sha256=engine_source_config_sha256,
        context_sha256=context_sha256,
        target_contract_sha256=target_contract_sha256,
        target_line=target_line,
        iterations=iterations,
        ignore_burst_energy=True,
        engine_context=context,
        snapshot=snapshot,
        wearers=wearers,
    )


def run_same_context_acceptance(
    acceptance_input: SameContextAcceptanceInput,
    *,
    run_dir: str | Path,
    trace_seed: int = DEFAULT_TRACE_SEED,
    timeout_seconds: int = 300,
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
    standard_error_multiplier: float = DEFAULT_STANDARD_ERROR_MULTIPLIER,
) -> SameContextAcceptanceResult:
    """Run trace/FAST and normal n=1000 GCSIM from one physical config file."""

    if not isinstance(acceptance_input, SameContextAcceptanceInput):
        raise TraceContractError("acceptance_input must be typed")
    if trace_seed <= 0:
        raise TraceContractError("trace_seed must be positive")
    if timeout_seconds <= 0:
        raise TraceContractError("timeout_seconds must be positive")
    if not math.isfinite(relative_tolerance) or relative_tolerance <= 0:
        raise TraceContractError("relative_tolerance must be positive")
    if (
        not math.isfinite(standard_error_multiplier)
        or standard_error_multiplier <= 0
    ):
        raise TraceContractError("standard_error_multiplier must be positive")

    started = perf_counter()
    root = Path(run_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    config_path = root / "config.txt"
    trace_request_path = root / "trace-request.json"
    trace_path = root / "trace.json"
    gcsim_result_path = root / "gcsim-n1000.json"

    # Explicit bytes avoid Windows newline translation changing the identity.
    config_path.write_bytes(acceptance_input.config_text.encode("utf-8"))
    if (
        _sha256_bytes(config_path.read_bytes())
        != acceptance_input.config_file_sha256
    ):
        raise TraceContractError("same-context config changed while writing")
    trace_request = {
        "schema_version": 1,
        "context_sha256": acceptance_input.context_sha256,
        "seed": str(trace_seed),
        "iterations": 1,
        "workers": 1,
        "ignore_burst_energy": acceptance_input.ignore_burst_energy,
    }
    trace_request_path.write_bytes(
        (json.dumps(trace_request, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )
    prepared_at = perf_counter()

    engine_path = Path(acceptance_input.engine_context.artifact_path).resolve()
    trace_command = (
        str(engine_path),
        "-c",
        str(config_path),
        "-out",
        str(trace_path),
        "-gtt-trace-equation",
        str(trace_request_path),
    )
    _run_checked(trace_command, cwd=root, timeout_seconds=timeout_seconds)
    trace_executed_at = perf_counter()
    raw = json.loads(trace_path.read_text(encoding="utf-8"))
    if raw.get("capability") != "gtt_trace_equation_v6":
        raise TraceContractError("same-context engine did not emit trace v6")
    if raw.get("context_sha256") != acceptance_input.context_sha256:
        raise TraceContractError("trace context identity mismatch")
    if (
        raw.get("source_config_sha256")
        != acceptance_input.engine_source_config_sha256
    ):
        raise TraceContractError(
            "trace did not consume the expected engine-normalized config"
        )
    if tuple(raw.get("character_keys", ())) != acceptance_input.snapshot.character_keys:
        raise TraceContractError("trace character order differs from equipment snapshot")

    trace_request_contract = TraceExtractionRequest(
        context_sha256=str(raw["context_sha256"]),
        source_config_sha256=str(raw["source_config_sha256"]),
        compiled_action_sha256=str(raw["compiled_action_sha256"]),
        target_sha256=str(raw["target_sha256"]),
        engine_artifact_sha256=acceptance_input.engine_context.artifact_sha256,
        engine_binding_sha256=acceptance_input.engine_context.binding_sha256,
        formula_version=str(raw["formula_version"]),
        formula_sha256=str(raw["formula_sha256"]),
        seed=int(raw["seed"]),
        objective=TraceObjective.TEAM_DPS,
        character_keys=tuple(raw["character_keys"]),
        required_capabilities=("gtt_trace_equation_v6",),
    )
    engine_root = Path(acceptance_input.engine_context.engine_root)
    engine_manifest = load_engine_manifest(engine_root)
    manifest_body = decode_source_manifest_body(
        (engine_root / "build" / "gtt-source-manifest-body.json").read_text(
            encoding="utf-8"
        )
    )
    binding = SourceManifestBinding.from_engine_manifest(
        manifest_body=manifest_body,
        engine_manifest=engine_manifest,
        engine_binding_sha256=acceptance_input.engine_context.binding_sha256,
    )
    trace = decode_engine_trace_v6(
        canonical_json(raw),
        request=trace_request_contract,
        source_manifest_binding=binding,
    )
    decoded_at = perf_counter()
    filters = compile_rotation_formula_filters(trace)
    fast_score = evaluate_rotation_formula_filter(
        filters,
        RotationFormulaMode.FAST,
        (),
    )
    if fast_score.candidate_dps is None:
        raise TraceContractError("FAST did not produce a DPS value")
    fast_dps = float(fast_score.candidate_dps)
    fast_evaluated_at = perf_counter()

    normal_command = (
        str(engine_path),
        "-c",
        str(config_path),
        "-out",
        str(gcsim_result_path),
    )
    _run_checked(normal_command, cwd=root, timeout_seconds=timeout_seconds)
    gcsim_finished_at = perf_counter()
    # Both process invocations referenced this exact file.  Recheck after both
    # runs so a mutation cannot hide between the trace and normal simulation.
    if (
        _sha256_bytes(config_path.read_bytes())
        != acceptance_input.config_file_sha256
    ):
        raise TraceContractError("same-context config mutated between engine runs")
    summary = parse_gcsim_result_file(gcsim_result_path)
    if summary.iterations != acceptance_input.iterations:
        raise TraceContractError(
            f"normal GCSIM iterations mismatch: {summary.iterations!r}"
        )
    if summary.dps_mean is None or summary.dps_se is None:
        raise TraceContractError("normal GCSIM result lacks DPS mean/SE")
    gcsim_mean = float(summary.dps_mean)
    gcsim_se = float(summary.dps_se)
    if not all(math.isfinite(value) for value in (fast_dps, gcsim_mean, gcsim_se)):
        raise TraceContractError("same-context result contains non-finite values")
    if gcsim_mean <= 0 or gcsim_se < 0:
        raise TraceContractError("same-context GCSIM statistics are invalid")

    absolute_error = abs(fast_dps - gcsim_mean)
    relative_error = absolute_error / gcsim_mean
    relative_limit = gcsim_mean * relative_tolerance
    statistical_limit = gcsim_se * standard_error_multiplier
    allowed_error = max(relative_limit, statistical_limit)
    result = SameContextAcceptanceResult(
        acceptance_input=acceptance_input,
        trace_source_config_sha256=str(raw["source_config_sha256"]),
        trace_target_sha256=str(raw["target_sha256"]),
        trace_raw_payload_sha256=canonical_sha256(raw),
        trace_duration_frames=trace.duration_frames,
        trace_hit_count=len(trace.terminal_trace.hits),
        fast_channel_count=filters.fast.coarse_channel_count,
        standard_group_count=filters.fast.standard_group_count,
        fast_dps=fast_dps,
        fast_damage=float(fast_score.candidate_damage),
        fast_damage_by_actor=tuple(fast_score.candidate_damage_by_actor),
        gcsim_dps_mean=gcsim_mean,
        gcsim_dps_se=gcsim_se,
        gcsim_iterations=int(summary.iterations),
        absolute_error_dps=absolute_error,
        relative_error=relative_error,
        relative_tolerance_dps=relative_limit,
        statistical_tolerance_dps=statistical_limit,
        allowed_error_dps=allowed_error,
        passed=absolute_error <= allowed_error,
        run_dir=str(root),
        timings_seconds=(
            ("prepare_input_files", prepared_at - started),
            ("trace_engine", trace_executed_at - prepared_at),
            ("decode_trace", decoded_at - trace_executed_at),
            ("compile_and_evaluate_fast", fast_evaluated_at - decoded_at),
            ("gcsim_n1000", gcsim_finished_at - fast_evaluated_at),
            ("total", gcsim_finished_at - started),
        ),
    )
    (root / "acceptance-report.json").write_bytes(
        (json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )
    return result


def bind_report_config_and_snapshot(
    payload: dict[str, Any],
    *,
    config_text: str,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    snapshot: SelectedEquippedTeamSnapshot,
) -> tuple[SameContextWearerInput, ...]:
    characters = tuple(payload.get("characters", ()))
    if len(characters) != len(snapshot.wearers):
        raise TraceContractError("prepared config/equipment wearer count mismatch")
    config_stats = _config_stats(config_text)
    config_sets = _config_sets(config_text)
    bound: list[SameContextWearerInput] = []
    slot_order = ("flower", "plume", "sands", "goblet", "circlet")
    for character, selected in zip(characters, snapshot.wearers, strict=True):
        actor = str(character["mapping"]["gcsim_key"]).casefold()
        if actor != selected.wearer.gcsim_character_key:
            raise TraceContractError("prepared config/equipment actor mismatch")
        build = character.get("artifact_build") or {}
        prepared_ids = tuple(
            int(build.get("artifact_ids_by_pos", {}).get(str(index)))
            for index in range(1, 6)
        )
        snapshot_ids = tuple(
            selected.assignment.artifact_ids_by_slot[slot]
            for slot in slot_order
        )
        if prepared_ids != snapshot_ids:
            raise TraceContractError(
                f"prepared config artifact IDs differ for {actor}"
            )

        totals: dict[str, Decimal] = {}
        for slot, artifact_id in zip(slot_order, snapshot_ids, strict=True):
            artifact = artifact_database.artifact_by_id(artifact_id)
            if artifact is None or artifact.position_key != slot:
                raise TraceContractError(
                    f"same-context artifact {artifact_id} is missing or in wrong slot"
                )
            materialized = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=selected.wearer,
            )
            if not materialized.ready or materialized.stat_vector is None:
                raise TraceContractError(
                    f"same-context artifact {artifact_id} did not materialize"
                )
            for stat_key, value in materialized.stat_vector.normalized_stats:
                totals[stat_key] = totals.get(stat_key, Decimal(0)) + Decimal(value)
        expected_stats = tuple(
            sorted((key, float(value)) for key, value in totals.items() if value != 0)
        )
        if not _stat_maps_close(dict(expected_stats), config_stats.get(actor, {})):
            raise TraceContractError(
                f"prepared config aggregate artifact stats differ for {actor}"
            )

        expected_sets = tuple(
            sorted(
                (
                    str(row["mapping"]["gcsim_key"]).casefold(),
                    int(row["count"]),
                )
                for row in build.get("set_counts", ())
                if int(row.get("count", 0)) >= 2
            )
        )
        if expected_sets != config_sets.get(actor, ()):
            raise TraceContractError(
                f"prepared config artifact sets differ for {actor}"
            )
        bound.append(
            SameContextWearerInput(
                actor_key=actor,
                artifact_ids_by_slot=tuple(zip(slot_order, snapshot_ids, strict=True)),
                aggregate_artifact_stats=expected_stats,
                active_sets=expected_sets,
            )
        )
    return tuple(bound)


# Transitional private alias for older focused tests/tools. Production callers
# use the public name so Selected input construction does not depend on a
# development-only helper.
_bind_report_config_and_snapshot = bind_report_config_and_snapshot


def _config_character_keys(config_text: str) -> tuple[str, ...]:
    return tuple(match.group(1).casefold() for match in _CHARACTER_RE.finditer(config_text))


def _config_stats(config_text: str) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for match in _STATS_RE.finditer(config_text):
        actor = match.group("actor").casefold()
        values = {
            token.group("key").casefold(): float(token.group("value"))
            for token in _STAT_TOKEN_RE.finditer(match.group("body"))
        }
        if not values or actor in output:
            raise TraceContractError("same-context config has invalid add stats rows")
        output[actor] = values
    return output


def _config_sets(config_text: str) -> dict[str, tuple[tuple[str, int], ...]]:
    output: dict[str, list[tuple[str, int]]] = {}
    for match in _SET_RE.finditer(config_text):
        output.setdefault(match.group("actor").casefold(), []).append(
            (match.group("set").casefold(), int(match.group("count")))
        )
    return {actor: tuple(sorted(rows)) for actor, rows in output.items()}


def _stat_maps_close(left: dict[str, float], right: dict[str, float]) -> bool:
    if set(left) != set(right):
        return False
    return all(math.isclose(left[key], right[key], rel_tol=0.0, abs_tol=1e-9) for key in left)


def _require_exact_iteration(config_text: str, expected: int) -> None:
    options = tuple(_OPTIONS_RE.finditer(config_text))
    if len(options) != 1:
        raise TraceContractError("same-context config requires one options row")
    match = _ITERATION_RE.search(options[0].group("body"))
    if match is None or int(match.group(1)) != expected:
        raise TraceContractError("same-context config iteration mismatch")
    if not re.search(
        r"(?i)\bignore_burst_energy\s*=\s*true\b",
        options[0].group("body"),
    ):
        raise TraceContractError("same-context config energy policy mismatch")


def _run_checked(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TraceContractError(f"same-context engine execution failed: {exc}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[-2000:]
        stdout = (completed.stdout or "").strip()[-2000:]
        raise TraceContractError(
            "same-context engine returned non-zero status "
            f"{completed.returncode}: stderr={stderr!r} stdout={stdout!r}"
        )


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _gcsim_single_file_resolved_config(value: str) -> str:
    """Mirror simulator.ReadConfig for a generated config without imports."""

    normalized = value.replace("\r\n", "\n")
    rows = normalized.split("\n")
    if any(re.fullmatch(r'import\s+".+"', row) for row in rows):
        raise TraceContractError(
            "same-context acceptance does not permit imported config fragments"
        )
    return "".join(f"{row}\n" for row in rows)


__all__ = [
    "DEFAULT_GCSIM_ITERATIONS",
    "DEFAULT_RELATIVE_TOLERANCE",
    "DEFAULT_STANDARD_ERROR_MULTIPLIER",
    "DEFAULT_TRACE_SEED",
    "SAME_CONTEXT_ACCEPTANCE_KIND",
    "SAME_CONTEXT_ACCEPTANCE_SCHEMA_VERSION",
    "SameContextAcceptanceInput",
    "SameContextAcceptanceResult",
    "SameContextWearerInput",
    "bind_report_config_and_snapshot",
    "build_current_same_context_acceptance_input",
    "run_same_context_acceptance",
]
