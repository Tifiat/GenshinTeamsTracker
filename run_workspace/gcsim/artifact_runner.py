"""Backend-only runner for an active built GTT-GCSIM artifact.

This module is the first narrow execution boundary after the engine lifecycle
prototype: it reads the active engine manifest, runs the already-built
`gtt-gcsim.exe` with caller-provided config text, and parses only a minimal
summary from the uncompressed JSON result. It intentionally does not generate
account/team configs, implement sequential waves, or integrate with UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Callable, Mapping, Sequence

from .engine_store import (
    DEFAULT_GCSIM_ENGINE_STORE_DIR,
    GcsimEngineStoreError,
    GcsimEngineStore,
    PROJECT_ROOT,
)
from .runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS, _trim_probe_text
from .shipped_artifact import (
    GcsimShippedArtifactResolution,
    resolve_shipped_gcsim_artifact,
)


DEFAULT_GCSIM_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "runs"
DEFAULT_GCSIM_CONFIG_FILENAME = "config.txt"
DEFAULT_GCSIM_RESULT_FILENAME = "result.json"
MAX_RESULT_LIST_ITEMS = 50
GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION = "gtt-wave-scenario-v1"
GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY = "gtt_wave_scenario_payload"
GTT_WAVE_SCENARIO_CONTRACT_MISMATCH_STATUS = "artifact_wave_scenario_contract_mismatch"

ArtifactRunner = Callable[
    [Sequence[str], Path, Mapping[str, str], int],
    subprocess.CompletedProcess[str],
]


@dataclass(frozen=True, slots=True)
class GcsimResultSummary:
    schema_version: str = ""
    sim_version: str = ""
    dps_mean: float | None = None
    duration_mean: float | None = None
    total_damage_mean: float | None = None
    warnings: tuple[str, ...] = ()
    failed_actions: tuple[str, ...] = ()
    incomplete_characters: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "sim_version": self.sim_version,
            "dps_mean": self.dps_mean,
            "duration_mean": self.duration_mean,
            "total_damage_mean": self.total_damage_mean,
            "warnings": list(self.warnings),
            "failed_actions": list(self.failed_actions),
            "incomplete_characters": list(self.incomplete_characters),
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactRunResult:
    status: str
    success: bool
    engine_id: str = ""
    engine_path: str = ""
    artifact_path: str = ""
    artifact_source: str = ""
    active_artifact_status: str = ""
    shipped_fallback_status: str = ""
    run_dir: str = ""
    config_path: str = ""
    gtt_wave_scenario_path: str = ""
    result_path: str = ""
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    summary: GcsimResultSummary = field(default_factory=GcsimResultSummary)
    error: str = ""
    artifact_preflight_status: str = ""
    artifact_preflight_command: tuple[str, ...] = ()
    artifact_preflight_returncode: int | None = None
    artifact_preflight_stdout: str = ""
    artifact_preflight_stderr: str = ""
    observed_gtt_patch_version: str = ""
    observed_gtt_capabilities: tuple[str, ...] = ()
    required_gtt_patch_version: str = ""
    required_gtt_capability: str = ""
    timing_seconds: dict[str, float] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "success": self.success,
            "engine_id": self.engine_id,
            "engine_path": self.engine_path,
            "artifact_path": self.artifact_path,
            "artifact_source": self.artifact_source,
            "active_artifact_status": self.active_artifact_status,
            "shipped_fallback_status": self.shipped_fallback_status,
            "run_dir": self.run_dir,
            "config_path": self.config_path,
            "gtt_wave_scenario_path": self.gtt_wave_scenario_path,
            "result_path": self.result_path,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "summary": self.summary.to_dict(),
            "error": self.error,
            "artifact_preflight_status": self.artifact_preflight_status,
            "artifact_preflight_command": list(self.artifact_preflight_command),
            "artifact_preflight_returncode": self.artifact_preflight_returncode,
            "artifact_preflight_stdout": self.artifact_preflight_stdout,
            "artifact_preflight_stderr": self.artifact_preflight_stderr,
            "observed_gtt_patch_version": self.observed_gtt_patch_version,
            "observed_gtt_capabilities": list(self.observed_gtt_capabilities),
            "required_gtt_patch_version": self.required_gtt_patch_version,
            "required_gtt_capability": self.required_gtt_capability,
            "timing_seconds": self.timing_seconds,
        }


def run_active_gcsim_artifact(
    config_text: str,
    *,
    gtt_wave_scenario: str | Path | None = None,
    store_dir: str | Path | None = None,
    run_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    runner: ArtifactRunner | None = None,
    enable_shipped_fallback: bool = False,
    shipped_fallback_artifact_path: str | Path | None = None,
) -> GcsimArtifactRunResult:
    store = GcsimEngineStore(store_dir or DEFAULT_GCSIM_ENGINE_STORE_DIR)
    try:
        active = store.get_active_engine()
    except GcsimEngineStoreError as exc:
        fallback = _resolve_fallback(
            enabled=enable_shipped_fallback,
            candidate_path=shipped_fallback_artifact_path,
        )
        if fallback.ready:
            return _run_artifact_process(
                config_text,
                gtt_wave_scenario=gtt_wave_scenario,
                run_dir=run_dir,
                timeout_seconds=timeout_seconds,
                runner=runner,
                artifact_path=Path(fallback.artifact_path),
                artifact_source="shipped_fallback",
                active_artifact_status="active_engine_invalid",
                shipped_fallback_status=fallback.status,
            )
        return _run_result(
            status="active_engine_invalid",
            success=False,
            active_artifact_status="active_engine_invalid",
            shipped_fallback_status=fallback.status,
            error=str(exc),
        )
    if active is None:
        fallback = _resolve_fallback(
            enabled=enable_shipped_fallback,
            candidate_path=shipped_fallback_artifact_path,
        )
        if fallback.ready:
            return _run_artifact_process(
                config_text,
                gtt_wave_scenario=gtt_wave_scenario,
                run_dir=run_dir,
                timeout_seconds=timeout_seconds,
                runner=runner,
                artifact_path=Path(fallback.artifact_path),
                artifact_source="shipped_fallback",
                active_artifact_status="no_active_engine",
                shipped_fallback_status=fallback.status,
            )
        return _run_result(
            status="no_active_engine",
            success=False,
            active_artifact_status="no_active_engine",
            shipped_fallback_status=fallback.status,
            error="No active GCSIM engine is configured.",
        )

    artifact_path = _active_artifact_path(active.path, active.manifest.metadata)
    if artifact_path is None:
        fallback = _resolve_fallback(
            enabled=enable_shipped_fallback,
            candidate_path=shipped_fallback_artifact_path,
        )
        if fallback.ready:
            return _run_artifact_process(
                config_text,
                gtt_wave_scenario=gtt_wave_scenario,
                run_dir=run_dir,
                timeout_seconds=timeout_seconds,
                runner=runner,
                engine_id=active.engine_id,
                engine_path=active.path,
                artifact_path=Path(fallback.artifact_path),
                artifact_source="shipped_fallback",
                active_artifact_status="artifact_path_missing",
                shipped_fallback_status=fallback.status,
            )
        return _run_result(
            status="artifact_path_missing",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            active_artifact_status="artifact_path_missing",
            shipped_fallback_status=fallback.status,
            error="Active GCSIM engine manifest does not contain an artifact path.",
        )
    if not artifact_path.exists():
        fallback = _resolve_fallback(
            enabled=enable_shipped_fallback,
            candidate_path=shipped_fallback_artifact_path,
        )
        if fallback.ready:
            return _run_artifact_process(
                config_text,
                gtt_wave_scenario=gtt_wave_scenario,
                run_dir=run_dir,
                timeout_seconds=timeout_seconds,
                runner=runner,
                engine_id=active.engine_id,
                engine_path=active.path,
                artifact_path=Path(fallback.artifact_path),
                artifact_source="shipped_fallback",
                active_artifact_status="artifact_missing",
                shipped_fallback_status=fallback.status,
            )
        return _run_result(
            status="artifact_missing",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            active_artifact_status="artifact_missing",
            shipped_fallback_status=fallback.status,
            error=f"Active GCSIM artifact is missing: {artifact_path}",
        )

    return _run_artifact_process(
        config_text,
        gtt_wave_scenario=gtt_wave_scenario,
        run_dir=run_dir,
        timeout_seconds=timeout_seconds,
        runner=runner,
        engine_id=active.engine_id,
        engine_path=active.path,
        artifact_path=artifact_path,
        artifact_source="active_engine",
        active_artifact_status="ready",
    )


def _run_artifact_process(
    config_text: str,
    *,
    gtt_wave_scenario: str | Path | None,
    run_dir: str | Path | None,
    timeout_seconds: int,
    runner: ArtifactRunner | None,
    artifact_path: Path,
    artifact_source: str,
    active_artifact_status: str = "",
    shipped_fallback_status: str = "",
    engine_id: str = "",
    engine_path: str | Path = "",
) -> GcsimArtifactRunResult:
    actual_run_dir = Path(run_dir) if run_dir is not None else _new_run_dir()
    actual_run_dir.mkdir(parents=True, exist_ok=True)
    config_path = actual_run_dir / DEFAULT_GCSIM_CONFIG_FILENAME
    result_path = actual_run_dir / DEFAULT_GCSIM_RESULT_FILENAME
    scenario_path = _resolve_optional_path(gtt_wave_scenario)
    command_runner = runner or _subprocess_runner
    env = dict(os.environ)

    preflight = _preflight_wave_scenario_contract(
        artifact_path,
        artifact_source=artifact_source,
        active_artifact_status=active_artifact_status,
        shipped_fallback_status=shipped_fallback_status,
        timeout_seconds=timeout_seconds,
        runner=command_runner,
        env=env,
        enabled=scenario_path is not None,
    )
    if preflight is not None and not preflight.ready:
        return _run_result(
            status=GTT_WAVE_SCENARIO_CONTRACT_MISMATCH_STATUS,
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            artifact_preflight_status=preflight.status,
            artifact_preflight_command=preflight.command,
            artifact_preflight_returncode=preflight.returncode,
            artifact_preflight_stdout=preflight.stdout,
            artifact_preflight_stderr=preflight.stderr,
            observed_gtt_patch_version=preflight.observed_patch_version,
            observed_gtt_capabilities=preflight.observed_capabilities,
            required_gtt_patch_version=preflight.required_patch_version,
            required_gtt_capability=preflight.required_capability,
            timing_seconds=preflight.timing_seconds,
            error=preflight.error,
        )

    config_path.write_text(str(config_text), encoding="utf-8")

    command = [str(artifact_path)]
    if scenario_path is not None:
        command.extend(("-gtt-wave-scenario", str(scenario_path)))
    command.extend(("-c", config_path.name, "-out", result_path.name))
    command = tuple(command)
    run_started = perf_counter()
    try:
        completed = command_runner(command, actual_run_dir, env, int(timeout_seconds))
        run_seconds = perf_counter() - run_started
    except subprocess.TimeoutExpired as exc:
        return _run_result(
            status="timeout",
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            **_preflight_result_kwargs(preflight),
            timing_seconds=_merge_timing(preflight, artifact_run_seconds=perf_counter() - run_started),
            error="GCSIM artifact run timed out.",
        )
    except OSError as exc:
        return _run_result(
            status="run_failed",
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            **_preflight_result_kwargs(preflight),
            timing_seconds=_merge_timing(preflight, artifact_run_seconds=perf_counter() - run_started),
            error=str(exc),
        )

    if completed.returncode != 0:
        return _run_result(
            status="run_failed",
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            **_preflight_result_kwargs(preflight),
            timing_seconds=_merge_timing(preflight, artifact_run_seconds=run_seconds),
            error=f"GCSIM artifact exited with {completed.returncode}.",
        )
    if not result_path.exists():
        return _run_result(
            status="result_missing",
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            **_preflight_result_kwargs(preflight),
            timing_seconds=_merge_timing(preflight, artifact_run_seconds=run_seconds),
            error="GCSIM artifact did not create the expected result JSON.",
        )

    try:
        summary = parse_gcsim_result_file(result_path)
    except GcsimResultParseError as exc:
        return _run_result(
            status="result_invalid",
            success=False,
            engine_id=engine_id,
            engine_path=engine_path,
            artifact_path=artifact_path,
            artifact_source=artifact_source,
            active_artifact_status=active_artifact_status,
            shipped_fallback_status=shipped_fallback_status,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            **_preflight_result_kwargs(preflight),
            timing_seconds=_merge_timing(preflight, artifact_run_seconds=run_seconds),
            error=str(exc),
        )

    return _run_result(
        status="passed",
        success=True,
        engine_id=engine_id,
        engine_path=engine_path,
        artifact_path=artifact_path,
        artifact_source=artifact_source,
        active_artifact_status=active_artifact_status,
        shipped_fallback_status=shipped_fallback_status,
        run_dir=actual_run_dir,
        config_path=config_path,
        gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
        result_path=result_path,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        summary=summary,
        **_preflight_result_kwargs(preflight),
        timing_seconds=_merge_timing(preflight, artifact_run_seconds=run_seconds),
    )


class GcsimResultParseError(RuntimeError):
    """Raised when a GCSIM result JSON file cannot be parsed at all."""


@dataclass(frozen=True, slots=True)
class GcsimArtifactContractPreflight:
    status: str
    ready: bool
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    observed_patch_version: str = ""
    observed_capabilities: tuple[str, ...] = ()
    required_patch_version: str = GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION
    required_capability: str = GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY
    error: str = ""
    timing_seconds: dict[str, float] | None = None


def _preflight_wave_scenario_contract(
    artifact_path: Path,
    *,
    artifact_source: str,
    active_artifact_status: str,
    shipped_fallback_status: str,
    timeout_seconds: int,
    runner: ArtifactRunner,
    env: Mapping[str, str],
    enabled: bool,
) -> GcsimArtifactContractPreflight | None:
    if not enabled:
        return None
    command = (str(artifact_path), "-gtt-info")
    started = perf_counter()
    try:
        completed = runner(command, artifact_path.parent, env, int(timeout_seconds))
    except subprocess.TimeoutExpired as exc:
        return _contract_preflight_result(
            status="gtt_info_timeout",
            ready=False,
            command=command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            timing_seconds={"artifact_preflight_seconds": perf_counter() - started},
            error="GTT-GCSIM artifact -gtt-info timed out; rebuild active GTT-GCSIM artifact from current patch stack.",
        )
    except OSError as exc:
        return _contract_preflight_result(
            status="gtt_info_failed",
            ready=False,
            command=command,
            timing_seconds={"artifact_preflight_seconds": perf_counter() - started},
            error=f"GTT-GCSIM artifact -gtt-info failed for {artifact_source}: {exc}; rebuild active GTT-GCSIM artifact from current patch stack.",
        )
    timing = {"artifact_preflight_seconds": perf_counter() - started}
    if completed.returncode != 0:
        return _contract_preflight_result(
            status="gtt_info_failed",
            ready=False,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timing_seconds=timing,
            error=f"GTT-GCSIM artifact -gtt-info exited with {completed.returncode}; rebuild active GTT-GCSIM artifact from current patch stack.",
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _contract_preflight_result(
            status="gtt_info_invalid_json",
            ready=False,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timing_seconds=timing,
            error=f"GTT-GCSIM artifact -gtt-info returned invalid JSON: {exc}; rebuild active GTT-GCSIM artifact from current patch stack.",
        )
    observed_version = _text_value(payload, "gtt_patch_version", "gttPatchVersion")
    observed_capabilities = _capabilities_from_gtt_info(payload)
    ready = (
        observed_version == GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION
        and GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY in set(observed_capabilities)
    )
    if ready:
        return _contract_preflight_result(
            status="gtt_wave_scenario_contract_ready",
            ready=True,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            observed_patch_version=observed_version,
            observed_capabilities=observed_capabilities,
            timing_seconds=timing,
        )
    missing: list[str] = []
    if observed_version != GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION:
        missing.append(
            f"required patch version {GTT_WAVE_SCENARIO_REQUIRED_PATCH_VERSION}, observed {observed_version or '<missing>'}"
        )
    if GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY not in set(observed_capabilities):
        missing.append(f"required capability {GTT_WAVE_SCENARIO_REQUIRED_CAPABILITY}")
    return _contract_preflight_result(
        status="gtt_wave_scenario_contract_missing",
        ready=False,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        observed_patch_version=observed_version,
        observed_capabilities=observed_capabilities,
        timing_seconds=timing,
        error=(
            "GTT-GCSIM artifact cannot run -gtt-wave-scenario: "
            + "; ".join(missing)
            + f". artifact_source={artifact_source} active_artifact_status={active_artifact_status} "
            + f"shipped_fallback_status={shipped_fallback_status}. "
            + "Rebuild active GTT-GCSIM artifact from current patch stack."
        ),
    )


def _contract_preflight_result(
    *,
    status: str,
    ready: bool,
    command: Sequence[str],
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
    observed_patch_version: str = "",
    observed_capabilities: Sequence[str] = (),
    timing_seconds: dict[str, float] | None = None,
    error: str = "",
) -> GcsimArtifactContractPreflight:
    return GcsimArtifactContractPreflight(
        status=status,
        ready=ready,
        command=tuple(str(part) for part in command),
        returncode=returncode,
        stdout=_trim_probe_text(stdout),
        stderr=_trim_probe_text(stderr),
        observed_patch_version=str(observed_patch_version or ""),
        observed_capabilities=tuple(str(item) for item in observed_capabilities),
        timing_seconds=_rounded_timing(timing_seconds),
        error=_trim_probe_text(error),
    )


def _preflight_result_kwargs(
    preflight: GcsimArtifactContractPreflight | None,
) -> dict:
    if preflight is None:
        return {}
    return {
        "artifact_preflight_status": preflight.status,
        "artifact_preflight_command": preflight.command,
        "artifact_preflight_returncode": preflight.returncode,
        "artifact_preflight_stdout": preflight.stdout,
        "artifact_preflight_stderr": preflight.stderr,
        "observed_gtt_patch_version": preflight.observed_patch_version,
        "observed_gtt_capabilities": preflight.observed_capabilities,
        "required_gtt_patch_version": preflight.required_patch_version,
        "required_gtt_capability": preflight.required_capability,
    }


def _merge_timing(
    preflight: GcsimArtifactContractPreflight | None,
    **timing: float,
) -> dict[str, float]:
    result = dict(preflight.timing_seconds or {}) if preflight is not None else {}
    result.update(timing)
    return _rounded_timing(result) or {}


def _capabilities_from_gtt_info(payload: Mapping) -> tuple[str, ...]:
    value = payload.get("capabilities")
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _rounded_timing(timing_seconds: dict[str, float] | None) -> dict[str, float] | None:
    if timing_seconds is None:
        return None
    return {
        key: round(float(value), 6)
        for key, value in sorted(timing_seconds.items())
    }


def parse_gcsim_result_file(path: str | Path) -> GcsimResultSummary:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GcsimResultParseError(f"Could not parse GCSIM result JSON: {exc}") from exc
    return parse_gcsim_result_payload(payload)


def parse_gcsim_result_payload(payload: object) -> GcsimResultSummary:
    if not isinstance(payload, dict):
        raise GcsimResultParseError("GCSIM result JSON root must be an object.")
    statistics = _dict_value(payload, "statistics")
    if statistics is None:
        statistics = {}
    return GcsimResultSummary(
        schema_version=_text_value(payload, "schema_version", "schemaVersion"),
        sim_version=_text_value(payload, "sim_version", "simVersion"),
        dps_mean=_stat_mean(statistics, "dps"),
        duration_mean=_stat_mean(statistics, "duration"),
        total_damage_mean=_stat_mean(statistics, "total_damage", "totalDamage"),
        warnings=_string_list_value(statistics, "warnings"),
        failed_actions=_string_list_value(statistics, "failed_actions", "failedActions"),
        incomplete_characters=_string_list_value(
            payload,
            "incomplete_characters",
            "incompleteCharacters",
        ),
    )


def _active_artifact_path(engine_path: Path, metadata: Mapping[str, str]) -> Path | None:
    for key in ("artifact_relative_path", "artifact_path"):
        raw = str(metadata.get(key, "") or "").strip()
        if not raw:
            continue
        path = Path(raw)
        if path.is_absolute():
            return path
        return engine_path / path
    return None


def _resolve_fallback(
    *,
    enabled: bool,
    candidate_path: str | Path | None,
) -> GcsimShippedArtifactResolution:
    return resolve_shipped_gcsim_artifact(
        enabled=enabled,
        candidate_path=candidate_path,
    )


def _resolve_optional_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _subprocess_runner(
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        timeout=int(timeout_seconds),
        check=False,
        capture_output=True,
        text=True,
    )


def _new_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return DEFAULT_GCSIM_RUNS_DIR / f"run-{stamp}"


def _dict_value(data: Mapping, *keys: str) -> dict | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return None


def _text_value(data: Mapping, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value)
    return ""


def _stat_mean(statistics: Mapping, *keys: str) -> float | None:
    item = _dict_value(statistics, *keys)
    if item is None:
        return None
    return _number_value(item.get("mean"))


def _number_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_list_value(data: Mapping, *keys: str) -> tuple[str, ...]:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            return (_format_result_item(value),)
        return tuple(_format_result_item(item) for item in value[:MAX_RESULT_LIST_ITEMS])
    return ()


def _format_result_item(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _run_result(
    *,
    status: str,
    success: bool,
    engine_id: str = "",
    engine_path: str | Path = "",
    artifact_path: str | Path = "",
    artifact_source: str = "",
    active_artifact_status: str = "",
    shipped_fallback_status: str = "",
    run_dir: str | Path = "",
    config_path: str | Path = "",
    gtt_wave_scenario_path: str | Path = "",
    result_path: str | Path = "",
    command: Sequence[str] = (),
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
    summary: GcsimResultSummary | None = None,
    error: str = "",
    artifact_preflight_status: str = "",
    artifact_preflight_command: Sequence[str] = (),
    artifact_preflight_returncode: int | None = None,
    artifact_preflight_stdout: str = "",
    artifact_preflight_stderr: str = "",
    observed_gtt_patch_version: str = "",
    observed_gtt_capabilities: Sequence[str] = (),
    required_gtt_patch_version: str = "",
    required_gtt_capability: str = "",
    timing_seconds: dict[str, float] | None = None,
) -> GcsimArtifactRunResult:
    return GcsimArtifactRunResult(
        status=str(status),
        success=bool(success),
        engine_id=str(engine_id),
        engine_path=str(engine_path) if str(engine_path) else "",
        artifact_path=str(artifact_path) if str(artifact_path) else "",
        artifact_source=str(artifact_source),
        active_artifact_status=str(active_artifact_status),
        shipped_fallback_status=str(shipped_fallback_status),
        run_dir=str(run_dir) if str(run_dir) else "",
        config_path=str(config_path) if str(config_path) else "",
        gtt_wave_scenario_path=str(gtt_wave_scenario_path)
        if str(gtt_wave_scenario_path)
        else "",
        result_path=str(result_path) if str(result_path) else "",
        command=tuple(str(part) for part in command),
        returncode=returncode,
        stdout=_trim_probe_text(stdout),
        stderr=_trim_probe_text(stderr),
        summary=summary or GcsimResultSummary(),
        error=_trim_probe_text(error),
        artifact_preflight_status=str(artifact_preflight_status),
        artifact_preflight_command=tuple(str(part) for part in artifact_preflight_command),
        artifact_preflight_returncode=artifact_preflight_returncode,
        artifact_preflight_stdout=_trim_probe_text(artifact_preflight_stdout),
        artifact_preflight_stderr=_trim_probe_text(artifact_preflight_stderr),
        observed_gtt_patch_version=str(observed_gtt_patch_version),
        observed_gtt_capabilities=tuple(str(item) for item in observed_gtt_capabilities),
        required_gtt_patch_version=str(required_gtt_patch_version),
        required_gtt_capability=str(required_gtt_capability),
        timing_seconds=_rounded_timing(timing_seconds),
    )
