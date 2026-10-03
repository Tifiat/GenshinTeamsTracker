"""Shared Go process lifecycle, cancellation, Finish and run retention.

No item search, damage formula, set selection or UI widget logic belongs here.
"""

from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from hoyolab_export.paths import PROJECT_ROOT
from .optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_SCHEMA_VERSION, GCSIM_OPTIMIZER_GO_PROGRESS_KIND,
    GCSIM_OPTIMIZER_GO_RESULT_KIND, write_diagnostic_json as _write_json,
)
from .optimizer_go_inputs import prepare_optimizer_inputs
from .optimizer_go_requests import GcsimOptimizerGoError, GcsimOptimizerGoRequest, GCSIM_OPTIMIZER_ADAPTER_TIMINGS_KIND
from .optimizer_run_retention import prune_go_optimizer_runs_best_effort, run_directory_lease

ProgressCallback = Callable[[dict[str, Any]], None]


class GcsimOptimizerGoSession:
    """Common single-use process lifecycle; modes supply their backend hooks."""

    run_mode = ""
    result_schema_kind = GCSIM_OPTIMIZER_GO_RESULT_KIND
    result_filename = "selected-result.json"
    mode_label = "Optimizer"
    request_validation_mode = "validate-request"

    def __init__(
        self,
        request: GcsimOptimizerGoRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.request = request
        self._progress_callback = progress_callback
        self._cancelled = threading.Event()
        self._process_lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()
        self._finish_requested = threading.Event()
        self._finish_lock = threading.Lock()
        self._run_dir: Path | None = None

    def cancel(self) -> None:
        self._cancelled.set()
        with self._process_lock:
            processes = tuple(self._processes)
        for process in processes:
            if process.poll() is None:
                _stop_process(process)

    def request_finish(self) -> None:
        """Ask Selected/All to finish search and score its current best set."""

        self._finish_requested.set()
        with self._finish_lock:
            if self._run_dir is not None:
                self._persist_finish_marker(self._run_dir)

    def run(self) -> dict[str, Any]:
        run_dir = _new_run_dir(self.request.run_root, mode=self.run_mode)
        started = time.monotonic()
        phase_started = started
        timings: dict[str, Any] = {
            "schema_version": 1,
            "schema_kind": GCSIM_OPTIMIZER_ADAPTER_TIMINGS_KIND,
            "mode": self.run_mode,
            "prepare_inputs_ms": None,
            "request_preflight_ms": None,
            "formula_inputs_ms": None,
            "optimizer_process_ms": None,
            "total_elapsed_ms": None,
            "terminal_status": "running",
        }
        leases = ExitStack()
        lease_started = False
        failure_payload: dict[str, Any] | None = None
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            leases.enter_context(run_directory_lease(run_dir))
            lease_started = True
            with self._finish_lock:
                self._run_dir = run_dir
                if self._finish_requested.is_set():
                    self._persist_finish_marker(run_dir)
            phase_started = time.monotonic()
            prepared = prepare_optimizer_inputs(
                self.request,
                run_dir,
                mode=self.run_mode,
            )
            timings["prepare_inputs_ms"] = _elapsed_ms(phase_started)
            self._require_not_cancelled()
            self._require_search_not_finished_before_result()
            phase_started = time.monotonic()
            self._validate_optimizer_request(run_dir=run_dir, started=started)
            timings["request_preflight_ms"] = _elapsed_ms(phase_started)
            self._require_not_cancelled()
            phase_started = time.monotonic()
            compact = self._prepare_formula_inputs(
                prepared=prepared,
                run_dir=run_dir,
                started=started,
            )
            timings["formula_inputs_ms"] = _elapsed_ms(phase_started)
            self._require_not_cancelled()
            self._require_search_not_finished_before_result()
            phase_started = time.monotonic()
            result = self._run_go_optimizer(
                prepared=prepared,
                compact=compact,
                run_dir=run_dir,
                started=started,
            )
            timings["optimizer_process_ms"] = _elapsed_ms(phase_started)
            timings["terminal_status"] = "success"
            return {
                "success": True,
                "status": "success",
                "result": result,
                "request_sha256": prepared["request_sha256"],
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "adapter_timings": timings,
                "mode": self.run_mode,
                "adapter_warnings": list(prepared.get("adapter_warnings") or ()),
            }
        except GcsimOptimizerGoError as exc:
            status = "cancelled" if exc.code == "cancelled" else "failed"
            timings["terminal_status"] = status
            payload = {
                "success": False,
                "status": status,
                "error_code": exc.code,
                "error": str(exc),
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "adapter_timings": timings,
            }
            failure_payload = payload
            return payload
        except Exception as exc:  # noqa: BLE001 - process/UI failure boundary.
            timings["terminal_status"] = "failed"
            payload = {
                "success": False,
                "status": "failed",
                "error_code": "unexpected_error",
                "error": str(exc),
                "run_dir": str(run_dir),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "adapter_timings": timings,
            }
            failure_payload = payload
            return payload

        finally:
            timings["total_elapsed_ms"] = _elapsed_ms(started)
            with self._finish_lock:
                if self._run_dir == run_dir:
                    self._run_dir = None
            timings["finish_requested"] = self._finish_requested.is_set()
            if failure_payload is not None:
                failure_payload["adapter_timings"] = timings
                _write_json(run_dir / self.result_filename, failure_payload)
            if run_dir.is_dir():
                try:
                    _write_json(run_dir / "adapter-timings.json", timings)
                except OSError:
                    pass  # Timing diagnostics must not hide the product result.
            try:
                if lease_started:
                    retention = prune_go_optimizer_runs_best_effort(self.request.run_root, run_dir)
                    try:
                        _write_json(run_dir / "retention.json", retention)
                    except OSError:
                        pass  # diagnostic failure must not hide the actual result
            finally:
                leases.close()

    def _persist_finish_marker(self, run_dir: Path) -> None:
        (run_dir / "finish-requested").touch(exist_ok=True)

    def _require_search_not_finished_before_result(self) -> None:
        if self.run_mode in {"selected", "all_sets"} and self._finish_requested.is_set():
            raise GcsimOptimizerGoError("finish_no_result", "Search stopped before a complete build was found.")

    def _prepare_formula_inputs(self, *, prepared, run_dir, started):
        raise NotImplementedError("Each mode supplies its formula inputs.")

    def _optimizer_environment(self) -> dict[str, str]:
        return dict(os.environ)

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
            raise GcsimOptimizerGoError(
                "optimizer_binary_missing",
                f"{self.mode_label} optimizer binary is missing. Reinstall/update the application.",
            )
        output_path = run_dir / "optimizer-output.json"
        stderr_path = run_dir / "optimizer-progress.jsonl"
        command = self._optimizer_command(binary, run_dir)
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
                env=self._optimizer_environment(),
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
                            row["finish_requested"] = self._finish_requested.is_set()
                            row["cancellation_requested"] = self._cancelled.is_set()
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
            raise GcsimOptimizerGoError("cancelled", f"{self.mode_label} optimization cancelled.")
        if process.returncode != 0:
            details = "\n".join(stderr_lines[-8:]).strip()
            raise GcsimOptimizerGoError(
                "finish_no_result" if "finish_no_result:" in details else "optimizer_process_failed",
                f"{self.mode_label} optimizer failed with code {process.returncode}: {details}",
            )
        try:
            wrapper = json.loads(output_path.read_text(encoding="utf-8"))
            result = wrapper["product_result"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise GcsimOptimizerGoError(
                "optimizer_result_invalid",
                f"{self.mode_label} optimizer returned an invalid result: {exc}",
            ) from exc
        if result.get("schema_kind") != self.result_schema_kind:
            raise GcsimOptimizerGoError(
                "optimizer_result_schema_mismatch",
                f"{self.mode_label} optimizer result schema does not match the application.",
            )
        if result.get("request_sha256") != prepared["request_sha256"]:
            raise GcsimOptimizerGoError(
                "optimizer_result_identity_mismatch",
                f"{self.mode_label} optimizer result belongs to another request.",
            )
        if result.get("status") != "success":
            raise GcsimOptimizerGoError(
                "optimizer_result_failed",
                str((result.get("error") or {}).get("message") or f"{self.mode_label} failed."),
            )
        _write_json(run_dir / self.result_filename, result)
        return result

    def _optimizer_command(self, binary: Path, run_dir: Path) -> tuple[str, ...]:
        raise NotImplementedError("Each mode supplies its command.")

    def _validate_optimizer_request(self, *, run_dir: Path, started: float) -> None:
        """Fail before formula capture when the installed executable is stale."""

        binary = Path(self.request.optimizer_binary_path).expanduser().resolve()
        if not binary.is_file():
            raise GcsimOptimizerGoError(
                "optimizer_binary_missing",
                f"{self.mode_label} optimizer binary is missing. Reinstall/update the application.",
            )
        stdout_path = run_dir / "optimizer-request-preflight.stdout.json"
        stderr_path = run_dir / "optimizer-request-preflight.stderr.txt"
        command = (
            str(binary),
            self.request_validation_mode,
            str(run_dir / "request.json"),
        )
        with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as stderr:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_process_group_flags(),
            )
            self._register_process(process)
            try:
                timeout_ms = _remaining_ms(started, self.request.product_timeout_ms)
                if self.run_mode == "theory":
                    timeout_ms = min(15_000, timeout_ms)
                _wait_process(
                    process,
                    cancel_event=self._cancelled,
                    timeout_ms=timeout_ms,
                )
            finally:
                self._unregister_process(process)
        if self._cancelled.is_set():
            raise GcsimOptimizerGoError(
                "cancelled", f"{self.mode_label} optimization cancelled."
            )
        if process.returncode != 0:
            details = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:].strip()
            raise GcsimOptimizerGoError(
                "optimizer_binary_contract_mismatch",
                f"Installed {self.mode_label} optimizer is incompatible with this application: {details}",
            )

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
            raise GcsimOptimizerGoError("cancelled", "Selected optimization cancelled.")
        if process.returncode != 0:
            details = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise GcsimOptimizerGoError(
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
            raise GcsimOptimizerGoError("cancelled", "Selected optimization cancelled.")

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
                "finish_requested": self._finish_requested.is_set(),
            }
        )


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
    if type(timeout_ms) is not int or timeout_ms < 0:
        raise GcsimOptimizerGoError(
            "timeout_invalid", "Process timeout must be non-negative."
        )
    deadline = None if timeout_ms == 0 else time.monotonic() + timeout_ms / 1000.0
    while process.poll() is None:
        if cancel_event.is_set():
            _stop_process(process)
            return
        if deadline is not None and time.monotonic() >= deadline:
            _stop_process(process)
            raise GcsimOptimizerGoError(
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
    if type(total_ms) is not int or total_ms < 0:
        raise GcsimOptimizerGoError(
            "timeout_invalid", "Process timeout must be non-negative."
        )
    if total_ms == 0:
        return 0
    remaining = total_ms - int((time.monotonic() - started) * 1000)
    if remaining <= 0:
        raise GcsimOptimizerGoError(
            "product_timeout", "Selected exceeded its configured product timeout."
        )
    return remaining


def _elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def _new_run_dir(root: str | Path, *, mode: str = "selected") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(root).expanduser().resolve() / f"{mode}-{stamp}-{uuid4().hex[:8]}"
