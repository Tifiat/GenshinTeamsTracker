"""Selected compact capture over the common Go process boundary.

Public Selected names remain stable. Other modes use the common session/input
modules directly, not Selected's formula-capture implementation.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any

from hoyolab_export.paths import PROJECT_ROOT
from .optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_SCHEMA_VERSION, GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
    write_canonical as _write_canonical, write_diagnostic_json as _write_json,
)
from .optimizer_go_requests import (
    GcsimOptimizerGoError as GcsimOptimizerGoSelectedError,
    GcsimOptimizerGoRequest as GcsimOptimizerGoSelectedRequest,
    DEFAULT_OPTIMIZER_BINARY, DEFAULT_PRODUCT_TIMEOUT_MS,
    DEFAULT_SELECTED_RUN_ROOT, DEFAULT_SELECTED_SEEDS,
    REQUIRED_ENGINE_CAPABILITIES, FINITE_ENERGY_ENGINE_CAPABILITY,
)
from .optimizer_go_session import (
    GcsimOptimizerGoSession, _remaining_ms,
    _progress_row, _wait_process, _stop_process,
)
from .optimizer_go_inputs import (
    prepare_optimizer_inputs, VIRTUAL_ARTIFACT_POLICY_BY_MODE,
    _bound_artifact_registry_source, _optimizer_result_options, _request_artifacts,
    _request_wearers,
    _request_theory_wearers, _report_issue_statuses, _TARGET_RE,
)
from .optimizer_go_result_text import (
    format_gcsim_optimizer_go_selected_result,
    format_optimizer_warning as _format_optimizer_warning,
)
from .selected_team_config import VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD


class GcsimOptimizerGoSelectedSession(GcsimOptimizerGoSession):
    """Selected-specific compact capture and native command."""

    run_mode = "selected"
    mode_label = "Selected"
    virtual_artifact_policy = VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD

    def _prepare_formula_inputs(self, *, prepared, run_dir, started):
        return self._capture_compact_panel(
            prepared=prepared, run_dir=run_dir, started=started
        )

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
                # Formula/energy capture must observe the complete intended
                # rotation. Ordinary finalist verification still uses the
                # prepared config's real energy policy.
                "ignore_burst_energy": True,
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

    def _optimizer_command(self, binary: Path, run_dir: Path) -> tuple[str, ...]:
        return (str(binary), "verify-fgbs", str(run_dir / "request.json"),
                str(run_dir / "compact.json"), str(run_dir / "verification"), "all",
                "--finish-file", str(run_dir / "finish-requested"))



def _prepare_inputs(request, run_dir, *, virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD):
    """Compatibility facade for historical probes; product callers pass a mode."""
    for mode, policy in VIRTUAL_ARTIFACT_POLICY_BY_MODE.items():
        if policy == virtual_artifact_policy:
            return prepare_optimizer_inputs(request, run_dir, mode=mode)
    raise GcsimOptimizerGoSelectedError(
        "optimizer_mode_invalid", f"Unknown virtual artifact policy: {virtual_artifact_policy!r}."
    )


__all__ = [
    "DEFAULT_OPTIMIZER_BINARY", "DEFAULT_SELECTED_RUN_ROOT",
    "GcsimOptimizerGoSelectedError", "GcsimOptimizerGoSelectedRequest",
    "GcsimOptimizerGoSelectedSession", "format_gcsim_optimizer_go_selected_result",
]
