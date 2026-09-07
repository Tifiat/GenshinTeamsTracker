"""Production Selected-Sets boundary for the standalone Go optimizer.

Python owns one coarse-grained application/process adapter only: materialize the
current UI team into a canonical request, ask the bound engine for the fixed
compact seed panel, start one Go optimizer process, and return its strict
product result. Candidate generation/evaluation never crosses this boundary.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Mapping
from uuid import uuid4

from hoyolab_export.paths import PROJECT_ROOT

from .engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR, load_engine_manifest
from .optimizer_artifact_database import load_gcsim_optimizer_artifact_database_input
from .optimizer_artifact_materializer import materialize_gcsim_optimizer_artifact_stat_vector
from .optimizer_engine_context import (
    GcsimOptimizerEngineContextError,
    load_active_gcsim_optimizer_engine_context,
)
from .optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
    GCSIM_OPTIMIZER_GO_PROGRESS_KIND,
    GCSIM_OPTIMIZER_GO_REQUEST_KIND,
    GCSIM_OPTIMIZER_GO_RESULT_KIND,
    GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
    GCSIM_OPTIMIZER_GO_STRATEGY_ID,
    canonical_json_bytes,
    canonical_sha256,
    text_sha256,
)
from .optimizer_go_selected_inputs import (
    bind_selected_report_config_and_snapshot,
    enforce_gcsim_optimizer_mvp_energy_policy,
    load_selected_equipped_team_snapshot,
)
from .selected_team_config import build_selected_team_full_config_report
from .settings import GcsimRunSettings


DEFAULT_SELECTED_SEEDS = (742_031_889, 742_031_890)
# The working prototype must return a result under ordinary desktop load. The
# 190-second value remains the performance acceptance target recorded in the
# handoff; 360 seconds is the temporary user-facing kill boundary.
DEFAULT_PRODUCT_TIMEOUT_MS = 360_000
DEFAULT_DEVELOPMENT_TIMEOUT_MS = 360_000
DEFAULT_OPTIMIZER_BINARY = (
    PROJECT_ROOT / "native" / "gcsim_optimizer" / "gtt-optimizer.exe"
)
DEFAULT_SELECTED_RUN_ROOT = PROJECT_ROOT / "data" / "gcsim" / "optimizer-go-runs"
REQUIRED_ENGINE_CAPABILITIES = frozenset(
    {"gtt_compact_equation_v1", "gtt_trace_equation_v6"}
)

_CHARACTER_RE = re.compile(r"(?im)^\s*([a-z0-9_]+)\s+char\b")
_WEAPON_RE = re.compile(
    r'(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+weapon="(?P<weapon>[^"]+)"'
)
_TARGET_RE = re.compile(r"(?im)^\s*target\b[^;]*;")
_STAT_KEY = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "hp%": "hp_percent",
    "atk%": "atk_percent",
    "def%": "def_percent",
    "em": "em",
    "er": "energy_recharge",
    "cr": "crit_rate",
    "cd": "crit_damage",
    "pyro%": "pyro_damage_bonus",
    "hydro%": "hydro_damage_bonus",
    "electro%": "electro_damage_bonus",
    "cryo%": "cryo_damage_bonus",
    "anemo%": "anemo_damage_bonus",
    "geo%": "geo_damage_bonus",
    "dendro%": "dendro_damage_bonus",
    "phys%": "physical_damage_bonus",
    "heal": "healing_bonus",
}

ProgressCallback = Callable[[dict[str, Any]], None]


class GcsimOptimizerGoSelectedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerGoSelectedRequest:
    db_path: str
    selected_team: Mapping[str, Any]
    team_index: int
    rotation_shell_text: str
    infinite_energy_enabled: bool = True
    engine_store_dir: str = str(DEFAULT_GCSIM_ENGINE_STORE_DIR)
    optimizer_binary_path: str = str(DEFAULT_OPTIMIZER_BINARY)
    run_root: str = str(DEFAULT_SELECTED_RUN_ROOT)
    seeds: tuple[int, ...] = DEFAULT_SELECTED_SEEDS
    product_timeout_ms: int = DEFAULT_PRODUCT_TIMEOUT_MS


class GcsimOptimizerGoSelectedSession:
    """One cancellable Selected request; instances are single-use."""

    def __init__(
        self,
        request: GcsimOptimizerGoSelectedRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.request = request
        self._progress_callback = progress_callback
        self._cancelled = threading.Event()
        self._process_lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._process_lock:
            processes = tuple(self._processes)
        for process in processes:
            if process.poll() is None:
                _stop_process(process)

    def run(self) -> dict[str, Any]:
        run_dir = _new_run_dir(self.request.run_root)
        started = time.monotonic()
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            prepared = _prepare_inputs(self.request, run_dir)
            self._require_not_cancelled()
            compact = self._capture_compact_panel(
                prepared=prepared,
                run_dir=run_dir,
                started=started,
            )
            self._require_not_cancelled()
            result = self._run_go_optimizer(
                prepared=prepared,
                compact=compact,
                run_dir=run_dir,
                started=started,
            )
            return {
                "success": True,
                "status": "success",
                "result": result,
                "request_sha256": prepared["request_sha256"],
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except GcsimOptimizerGoSelectedError as exc:
            status = "cancelled" if exc.code == "cancelled" else "failed"
            payload = {
                "success": False,
                "status": status,
                "error_code": exc.code,
                "error": str(exc),
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
            _write_json(run_dir / "selected-result.json", payload)
            return payload
        except Exception as exc:  # noqa: BLE001 - process/UI failure boundary.
            payload = {
                "success": False,
                "status": "failed",
                "error_code": "unexpected_error",
                "error": str(exc),
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
            _write_json(run_dir / "selected-result.json", payload)
            return payload

    def _capture_compact_panel(
        self,
        *,
        prepared: dict[str, Any],
        run_dir: Path,
        started: float,
    ) -> dict[str, Any]:
        request_payload = prepared["request"]
        config_path = run_dir / "prepared-config.txt"
        config_path.write_bytes(
            request_payload["context"]["prepared_config"]["text"].encode("utf-8")
        )
        seeds = tuple(self.request.seeds)

        def capture(seed: int) -> dict[str, Any]:
            trace_request_path = run_dir / f"compact-request-{seed}.json"
            member_path = run_dir / f"compact-member-{seed}.json"
            trace_request = {
                "schema_version": 1,
                "context_sha256": request_payload["context"]["trace_context_sha256"],
                "seed": str(seed),
                "iterations": 1,
                "workers": 1,
                "ignore_burst_energy": bool(self.request.infinite_energy_enabled),
                "output_mode": "compact_ir_v1",
            }
            _write_json(trace_request_path, trace_request)
            command = (
                request_payload["engine"]["binary_path"],
                "-c",
                str(config_path),
                "-out",
                str(member_path),
                "-gtt-trace-equation",
                str(trace_request_path),
            )
            self._run_process(
                command,
                cwd=run_dir,
                timeout_ms=_remaining_ms(started, self.request.product_timeout_ms),
                stdout_path=run_dir / f"compact-{seed}.stdout.txt",
                stderr_path=run_dir / f"compact-{seed}.stderr.txt",
            )
            try:
                member = json.loads(member_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise GcsimOptimizerGoSelectedError(
                    "compact_output_invalid",
                    f"GCSIM did not return valid compact evidence for seed {seed}: {exc}",
                ) from exc
            if int(member.get("seed", 0)) != seed:
                raise GcsimOptimizerGoSelectedError(
                    "compact_seed_mismatch",
                    f"Compact evidence seed mismatch for {seed}.",
                )
            return member

        self._emit_progress(
            prepared["request_sha256"],
            sequence=0,
            stage="loading_evidence",
            completed=0,
            total=len(seeds),
            started=started,
        )
        members_by_seed: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(2, len(seeds))) as pool:
            futures = {pool.submit(capture, seed): seed for seed in seeds}
            for completed, future in enumerate(as_completed(futures), start=1):
                seed = futures[future]
                members_by_seed[seed] = future.result()
                self._require_not_cancelled()
                self._emit_progress(
                    prepared["request_sha256"],
                    sequence=completed,
                    stage="loading_evidence",
                    completed=completed,
                    total=len(seeds),
                    started=started,
                )
        members = [members_by_seed[seed] for seed in seeds]
        compact = {
            "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
            "schema_kind": GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
            "request_sha256": prepared["request_sha256"],
            "engine_binding_sha256": request_payload["engine"]["binding_sha256"],
            "context_sha256": request_payload["context"]["trace_context_sha256"],
            "members": members,
        }
        _write_canonical(run_dir / "compact.json", compact)
        return compact

    def _run_go_optimizer(
        self,
        *,
        prepared: dict[str, Any],
        compact: dict[str, Any],
        run_dir: Path,
        started: float,
    ) -> dict[str, Any]:
        binary = Path(self.request.optimizer_binary_path).expanduser().resolve()
        if not binary.is_file():
            raise GcsimOptimizerGoSelectedError(
                "optimizer_binary_missing",
                "Selected optimizer binary is missing. Reinstall/update the application.",
            )
        request_path = run_dir / "request.json"
        compact_path = run_dir / "compact.json"
        output_path = run_dir / "optimizer-output.json"
        stderr_path = run_dir / "optimizer-progress.jsonl"
        command = (
            str(binary),
            "verify-fgbs",
            str(request_path),
            str(compact_path),
            str(run_dir / "verification"),
            "all",
        )
        stderr_lines: list[str] = []
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=output,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_process_group_flags(),
            )
            self._register_process(process)
            assert process.stderr is not None

            def read_progress() -> None:
                with stderr_path.open("w", encoding="utf-8", newline="\n") as log:
                    for line in process.stderr:
                        log.write(line)
                        log.flush()
                        stderr_lines.append(line.rstrip())
                        row = _progress_row(line, sequence_offset=2 * len(self.request.seeds))
                        if row is not None and self._progress_callback is not None:
                            self._progress_callback(row)

            reader = threading.Thread(target=read_progress, daemon=True)
            reader.start()
            try:
                _wait_process(
                    process,
                    cancel_event=self._cancelled,
                    timeout_ms=_remaining_ms(started, self.request.product_timeout_ms),
                )
            finally:
                reader.join(timeout=2)
                self._unregister_process(process)
        if self._cancelled.is_set():
            raise GcsimOptimizerGoSelectedError("cancelled", "Selected optimization cancelled.")
        if process.returncode != 0:
            details = "\n".join(stderr_lines[-8:]).strip()
            raise GcsimOptimizerGoSelectedError(
                "optimizer_process_failed",
                f"Selected optimizer failed with code {process.returncode}: {details}",
            )
        try:
            wrapper = json.loads(output_path.read_text(encoding="utf-8"))
            result = wrapper["product_result"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise GcsimOptimizerGoSelectedError(
                "optimizer_result_invalid",
                f"Selected optimizer returned an invalid result: {exc}",
            ) from exc
        if result.get("schema_kind") != GCSIM_OPTIMIZER_GO_RESULT_KIND:
            raise GcsimOptimizerGoSelectedError(
                "optimizer_result_schema_mismatch",
                "Selected optimizer result schema does not match the application.",
            )
        if result.get("request_sha256") != prepared["request_sha256"]:
            raise GcsimOptimizerGoSelectedError(
                "optimizer_result_identity_mismatch",
                "Selected optimizer result belongs to another request.",
            )
        if result.get("status") != "success":
            raise GcsimOptimizerGoSelectedError(
                "optimizer_result_failed",
                str((result.get("error") or {}).get("message") or "Selected failed."),
            )
        _write_json(run_dir / "selected-result.json", result)
        return result

    def _run_process(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        timeout_ms: int,
        stdout_path: Path,
        stderr_path: Path,
    ) -> None:
        with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as stderr:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_process_group_flags(),
            )
            self._register_process(process)
            try:
                _wait_process(process, cancel_event=self._cancelled, timeout_ms=timeout_ms)
            finally:
                self._unregister_process(process)
        if self._cancelled.is_set():
            raise GcsimOptimizerGoSelectedError("cancelled", "Selected optimization cancelled.")
        if process.returncode != 0:
            details = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise GcsimOptimizerGoSelectedError(
                "compact_engine_failed",
                f"GCSIM compact evidence failed with code {process.returncode}: {details.strip()}",
            )

    def _register_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            self._processes.add(process)

    def _unregister_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            self._processes.discard(process)

    def _require_not_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise GcsimOptimizerGoSelectedError("cancelled", "Selected optimization cancelled.")

    def _emit_progress(
        self,
        request_sha256: str,
        *,
        sequence: int,
        stage: str,
        completed: int,
        total: int,
        started: float,
    ) -> None:
        if self._progress_callback is None:
            return
        self._progress_callback(
            {
                "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
                "schema_kind": GCSIM_OPTIMIZER_GO_PROGRESS_KIND,
                "request_sha256": request_sha256,
                "sequence": sequence,
                "stage": stage,
                "completed_work": completed,
                "total_work": total,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "cancellation_requested": self._cancelled.is_set(),
            }
        )


def _prepare_inputs(
    request: GcsimOptimizerGoSelectedRequest,
    run_dir: Path,
) -> dict[str, Any]:
    if len(request.seeds) < 2 or len(set(request.seeds)) != len(request.seeds):
        raise GcsimOptimizerGoSelectedError(
            "seed_panel_invalid", "Selected requires at least two unique seeds."
        )
    if request.product_timeout_ms <= 0:
        raise GcsimOptimizerGoSelectedError("timeout_invalid", "Selected timeout is invalid.")
    try:
        engine_context = load_active_gcsim_optimizer_engine_context(
            store_dir=request.engine_store_dir
        )
    except GcsimOptimizerEngineContextError as exc:
        raise GcsimOptimizerGoSelectedError(
            "optimizer_engine_unavailable",
            f"Active GCSIM engine cannot run Selected: {exc}",
        ) from exc
    capabilities = frozenset(engine_context.capabilities)
    missing = sorted(REQUIRED_ENGINE_CAPABILITIES - capabilities)
    if missing:
        raise GcsimOptimizerGoSelectedError(
            "optimizer_engine_capability_missing",
            "Active GCSIM engine cannot run Selected; missing: " + ", ".join(missing),
        )
    rotation_path = run_dir / "rotation.from-ui.txt"
    rotation_path.write_text(request.rotation_shell_text, encoding="utf-8")
    report = build_selected_team_full_config_report(
        db_path=request.db_path,
        selected_team=request.selected_team,
        team_index=max(0, int(request.team_index)),
        rotation_shell_path=rotation_path,
        run_dir=run_dir,
        write_config=False,
        run_settings=GcsimRunSettings(boosted_energy_enabled=False),
    )
    if not report.ready or report.issues:
        raise GcsimOptimizerGoSelectedError(
            "selected_config_not_ready",
            f"Current team cannot be prepared for Selected: {report.issues!r}",
        )
    config_text = enforce_gcsim_optimizer_mvp_energy_policy(
        report.full_config.assembly.config_text,
        ignore_burst_energy=bool(request.infinite_energy_enabled),
    )
    character_keys = tuple(match.group(1).casefold() for match in _CHARACTER_RE.finditer(config_text))
    if len(character_keys) != 4 or len(set(character_keys)) != 4:
        raise GcsimOptimizerGoSelectedError(
            "selected_team_requires_four_characters",
            "Selected requires exactly four distinct prepared characters.",
        )
    loaded = load_gcsim_optimizer_artifact_database_input(
        request.db_path, engine_context=engine_context
    )
    if not loaded.ready or loaded.database_input is None:
        raise GcsimOptimizerGoSelectedError(
            "artifact_database_not_ready",
            f"Artifact database cannot be used by Selected: {loaded.issues!r}",
        )
    database = loaded.database_input
    snapshot = load_selected_equipped_team_snapshot(
        request.db_path,
        artifact_database=database,
        character_keys=character_keys,
    )
    wearers = bind_selected_report_config_and_snapshot(
        report.team.payload,
        config_text=config_text,
        artifact_database=database,
        snapshot=snapshot,
    )
    target_matches = tuple(match.group(0).strip() for match in _TARGET_RE.finditer(config_text))
    if len(target_matches) != 1:
        raise GcsimOptimizerGoSelectedError(
            "selected_target_invalid", "Selected requires exactly one DPS target line."
        )
    target_text = target_matches[0] + "\n"
    engine_manifest = load_engine_manifest(Path(engine_context.engine_root))
    source_manifest_path = Path(engine_context.engine_root) / "build" / "gtt-source-manifest-body.json"
    if not source_manifest_path.is_file():
        raise GcsimOptimizerGoSelectedError(
            "source_manifest_missing", "Selected engine source manifest is missing."
        )
    source_manifest_sha256 = _file_sha256(source_manifest_path)
    patch_manifest_sha256 = str(
        engine_manifest.patch_metadata.get("patch_stack_sha256", "") or ""
    ).casefold()
    if not _is_sha256(patch_manifest_sha256):
        raise GcsimOptimizerGoSelectedError(
            "patch_manifest_missing", "Selected engine patch identity is missing."
        )
    engine_binding_sha256 = canonical_sha256(
        {
            "kind": "gtt.standalone_engine_binding.v1",
            "artifact_sha256": engine_context.artifact_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_manifest_sha256": patch_manifest_sha256,
        }
    )
    trace_context_sha256 = canonical_sha256(
        {
            "kind": "gtt.optimizer.selected.trace_context.v1",
            "engine_binding_sha256": engine_binding_sha256,
            "artifact_database_input_sha256": database.artifact_database_input_sha256,
            "equipment_rows_sha256": snapshot.equipment_rows_sha256,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "prepared_config_sha256": text_sha256(config_text),
            "rotation_sha256": text_sha256(request.rotation_shell_text),
            "target_sha256": text_sha256(target_text),
            "seeds": list(request.seeds),
            "ignore_burst_energy": bool(request.infinite_energy_enabled),
        }
    )
    context = {
        "prepared_config": _source_text(config_text),
        "rotation": _source_text(request.rotation_shell_text),
        "target": _source_text(target_text),
    }
    context["context_sha256"] = canonical_sha256(
        {
            "prepared_config_sha256": context["prepared_config"]["sha256"],
            "rotation_sha256": context["rotation"]["sha256"],
            "target_sha256": context["target"]["sha256"],
        }
    )
    context["trace_context_sha256"] = trace_context_sha256
    request_payload = {
        "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
        "schema_kind": GCSIM_OPTIMIZER_GO_REQUEST_KIND,
        "strategy_id": GCSIM_OPTIMIZER_GO_STRATEGY_ID,
        "engine": {
            "binary_path": str(Path(engine_context.artifact_path).resolve()).replace("\\", "/"),
            "artifact_sha256": engine_context.artifact_sha256,
            "binding_sha256": engine_binding_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_manifest_sha256": patch_manifest_sha256,
            "capabilities": sorted(capabilities),
        },
        "context": context,
        "wearers": _request_wearers(config_text, wearers),
        "artifacts": _request_artifacts(database, wearers[0].actor_key, snapshot),
        "legality": {
            "fixed_four_piece": True,
            "max_off_set_pieces_per_wearer": 1,
            "globally_unique_artifact_ids": True,
            "default_minimum_rarity": 5,
            "authorized_lower_rarity_artifact_ids": [],
        },
        "stochastic": {
            "mode": "equal_weight_fixed_panel_v1",
            "seeds": sorted(request.seeds),
        },
        "budgets": {
            "product_timeout_ms": int(request.product_timeout_ms),
            "development_timeout_ms": DEFAULT_DEVELOPMENT_TIMEOUT_MS,
        },
        "cancellation": {"mode": "process_interrupt_v1"},
    }
    request_sha256 = canonical_sha256(request_payload)
    _write_canonical(run_dir / "request.json", request_payload)
    return {
        "request": request_payload,
        "request_sha256": request_sha256,
        "snapshot": snapshot,
    }


def _request_wearers(config_text: str, wearers: tuple[Any, ...]) -> list[dict[str, Any]]:
    weapons = {
        match.group("actor").casefold(): match.group("weapon").casefold()
        for match in _WEAPON_RE.finditer(config_text)
    }
    output = []
    for wearer in sorted(wearers, key=lambda row: row.actor_key):
        selected = [key for key, count in wearer.active_sets if count >= 4]
        if len(selected) != 1:
            raise GcsimOptimizerGoSelectedError(
                "selected_fixed_set_missing",
                f"{wearer.actor_key} needs one currently equipped 4p/5p set.",
            )
        output.append(
            {
                "wearer_key": wearer.actor_key,
                "weapon_key": weapons[wearer.actor_key],
                "selected_set_uid": selected[0],
                "current_artifacts": [
                    {
                        "wearer_key": wearer.actor_key,
                        "slot": slot,
                        "artifact_id": artifact_id,
                    }
                    for slot, artifact_id in wearer.artifact_ids_by_slot
                ],
            }
        )
    return output


def _request_artifacts(database: Any, reference_actor: str, snapshot: Any) -> list[dict[str, Any]]:
    reference = next(
        row.wearer for row in snapshot.wearers if row.wearer.gcsim_character_key == reference_actor
    )
    artifacts: list[dict[str, Any]] = []
    for artifact in database.artifacts:
        if not artifact.default_eligible or not artifact.gcsim_set_key:
            continue
        materialized = materialize_gcsim_optimizer_artifact_stat_vector(
            artifact, wearer=reference
        )
        if not materialized.ready or materialized.stat_vector is None:
            raise GcsimOptimizerGoSelectedError(
                "artifact_materialization_failed",
                f"Artifact {artifact.artifact_id} cannot be materialized.",
            )
        main = [row for row in materialized.stat_vector.contributions if row.source_kind == "main"]
        substats = [
            row for row in materialized.stat_vector.contributions if row.source_kind == "substat"
        ]
        if len(main) != 1:
            raise GcsimOptimizerGoSelectedError(
                "artifact_main_stat_invalid", f"Artifact {artifact.artifact_id} has invalid main stat."
            )
        artifacts.append(
            {
                "artifact_id": artifact.artifact_id,
                "slot": artifact.position_key,
                "set_uid": artifact.gcsim_set_key.casefold(),
                "rarity": artifact.rarity,
                "level": artifact.level,
                "main_stat": {
                    "key": _go_stat_key(main[0].gcsim_key),
                    "value": main[0].normalized_value,
                },
                "substats": sorted(
                    (
                        {
                            "key": _go_stat_key(row.gcsim_key),
                            "value": row.normalized_value,
                        }
                        for row in substats
                    ),
                    key=lambda row: row["key"],
                ),
            }
        )
    return artifacts


def format_gcsim_optimizer_go_selected_result(payload: Mapping[str, Any]) -> str:
    if not payload.get("success"):
        title = "Selected Sets cancelled" if payload.get("status") == "cancelled" else "Selected Sets failed"
        return "\n".join(
            (
                title,
                f"Reason: {payload.get('error') or '-'}",
                f"Debug: {payload.get('run_dir') or '-'}",
            )
        )
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    measured = result.get("measured") if isinstance(result.get("measured"), Mapping) else {}
    assignments: dict[str, list[str]] = {}
    for row in result.get("winner") or ():
        assignments.setdefault(str(row.get("wearer_key") or "?"), []).append(
            f"{row.get('slot')}={row.get('artifact_id')}"
        )
    lines = [
        "Selected Sets complete",
        f"Final DPS: {measured.get('dps') or '-'}",
        f"Standard error: {measured.get('standard_error') or '-'}",
        f"Formula estimate: {result.get('formula_dps') or '-'}",
        f"Formula residual: {result.get('formula_residual') or '-'}",
    ]
    for wearer in sorted(assignments):
        lines.append(f"{wearer}: " + ", ".join(assignments[wearer]))
    warnings = tuple(result.get("warnings") or ())
    if warnings:
        lines.append("Warnings: " + ", ".join(str(value) for value in warnings))
    lines.append(f"Debug: {result.get('debug_receipt_path') or payload.get('run_dir') or '-'}")
    return "\n".join(lines)


def _source_text(text: str) -> dict[str, str]:
    return {"text": text, "sha256": text_sha256(text)}


def _go_stat_key(value: str) -> str:
    try:
        return _STAT_KEY[value]
    except KeyError as exc:
        raise GcsimOptimizerGoSelectedError(
            "artifact_stat_unsupported", f"Unsupported artifact stat {value!r}."
        ) from exc


def _progress_row(line: str, *, sequence_offset: int = 0) -> dict[str, Any] | None:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict) or row.get("schema_kind") != GCSIM_OPTIMIZER_GO_PROGRESS_KIND:
        return None
    result = dict(row)
    result["sequence"] = int(result.get("sequence", 0)) + max(0, int(sequence_offset))
    return result


def _wait_process(
    process: subprocess.Popen[str],
    *,
    cancel_event: threading.Event,
    timeout_ms: int,
) -> None:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    while process.poll() is None:
        if cancel_event.is_set():
            _stop_process(process)
            return
        if time.monotonic() >= deadline:
            _stop_process(process)
            raise GcsimOptimizerGoSelectedError(
                "product_timeout", "Selected exceeded its configured product timeout."
            )
        time.sleep(0.05)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def _process_group_flags() -> int:
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0


def _remaining_ms(started: float, total_ms: int) -> int:
    remaining = total_ms - int((time.monotonic() - started) * 1000)
    if remaining <= 0:
        raise GcsimOptimizerGoSelectedError(
            "product_timeout", "Selected exceeded its configured product timeout."
        )
    return remaining


def _new_run_dir(root: str | Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(root).expanduser().resolve() / f"selected-{stamp}-{uuid4().hex[:8]}"


def _write_canonical(path: Path, payload: Any) -> None:
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


__all__ = [
    "DEFAULT_OPTIMIZER_BINARY",
    "DEFAULT_SELECTED_RUN_ROOT",
    "GcsimOptimizerGoSelectedError",
    "GcsimOptimizerGoSelectedRequest",
    "GcsimOptimizerGoSelectedSession",
    "format_gcsim_optimizer_go_selected_result",
]
