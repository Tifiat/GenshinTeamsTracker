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
from typing import Callable, Mapping, Sequence

from .engine_store import (
    DEFAULT_GCSIM_ENGINE_STORE_DIR,
    GcsimEngineStoreError,
    GcsimEngineStore,
    PROJECT_ROOT,
)
from .runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS, _trim_probe_text


DEFAULT_GCSIM_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "runs"
DEFAULT_GCSIM_CONFIG_FILENAME = "config.txt"
DEFAULT_GCSIM_RESULT_FILENAME = "result.json"
MAX_RESULT_LIST_ITEMS = 50

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

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "success": self.success,
            "engine_id": self.engine_id,
            "engine_path": self.engine_path,
            "artifact_path": self.artifact_path,
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
        }


def run_active_gcsim_artifact(
    config_text: str,
    *,
    gtt_wave_scenario: str | Path | None = None,
    store_dir: str | Path | None = None,
    run_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    runner: ArtifactRunner | None = None,
) -> GcsimArtifactRunResult:
    store = GcsimEngineStore(store_dir or DEFAULT_GCSIM_ENGINE_STORE_DIR)
    try:
        active = store.get_active_engine()
    except GcsimEngineStoreError as exc:
        return _run_result(
            status="active_engine_invalid",
            success=False,
            error=str(exc),
        )
    if active is None:
        return _run_result(
            status="no_active_engine",
            success=False,
            error="No active GCSIM engine is configured.",
        )

    artifact_path = _active_artifact_path(active.path, active.manifest.metadata)
    if artifact_path is None:
        return _run_result(
            status="artifact_path_missing",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            error="Active GCSIM engine manifest does not contain an artifact path.",
        )
    if not artifact_path.exists():
        return _run_result(
            status="artifact_missing",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            error=f"Active GCSIM artifact is missing: {artifact_path}",
        )

    actual_run_dir = Path(run_dir) if run_dir is not None else _new_run_dir()
    actual_run_dir.mkdir(parents=True, exist_ok=True)
    config_path = actual_run_dir / DEFAULT_GCSIM_CONFIG_FILENAME
    result_path = actual_run_dir / DEFAULT_GCSIM_RESULT_FILENAME
    config_path.write_text(str(config_text), encoding="utf-8")
    scenario_path = _resolve_optional_path(gtt_wave_scenario)

    command = [str(artifact_path)]
    if scenario_path is not None:
        command.extend(("-gtt-wave-scenario", str(scenario_path)))
    command.extend(("-c", config_path.name, "-out", result_path.name))
    command = tuple(command)
    command_runner = runner or _subprocess_runner
    env = dict(os.environ)
    try:
        completed = command_runner(command, actual_run_dir, env, int(timeout_seconds))
    except subprocess.TimeoutExpired as exc:
        return _run_result(
            status="timeout",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="GCSIM artifact run timed out.",
        )
    except OSError as exc:
        return _run_result(
            status="run_failed",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            error=str(exc),
        )

    if completed.returncode != 0:
        return _run_result(
            status="run_failed",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error=f"GCSIM artifact exited with {completed.returncode}.",
        )
    if not result_path.exists():
        return _run_result(
            status="result_missing",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error="GCSIM artifact did not create the expected result JSON.",
        )

    try:
        summary = parse_gcsim_result_file(result_path)
    except GcsimResultParseError as exc:
        return _run_result(
            status="result_invalid",
            success=False,
            engine_id=active.engine_id,
            engine_path=active.path,
            artifact_path=artifact_path,
            run_dir=actual_run_dir,
            config_path=config_path,
            gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
            result_path=result_path,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error=str(exc),
        )

    return _run_result(
        status="passed",
        success=True,
        engine_id=active.engine_id,
        engine_path=active.path,
        artifact_path=artifact_path,
        run_dir=actual_run_dir,
        config_path=config_path,
        gtt_wave_scenario_path="" if scenario_path is None else scenario_path,
        result_path=result_path,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        summary=summary,
    )


class GcsimResultParseError(RuntimeError):
    """Raised when a GCSIM result JSON file cannot be parsed at all."""


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
) -> GcsimArtifactRunResult:
    return GcsimArtifactRunResult(
        status=str(status),
        success=bool(success),
        engine_id=str(engine_id),
        engine_path=str(engine_path) if str(engine_path) else "",
        artifact_path=str(artifact_path) if str(artifact_path) else "",
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
    )
