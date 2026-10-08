"""Explicit real-button Chasca regression gate with disposable owned inputs.

Examples (from this checkout, using an installed application root):
  .venv/Scripts/python.exe -B tools/check_chasca_optimizer.py --app-root C:/path/to/GenshinTeamsTracker
  .venv/Scripts/python.exe -B tools/check_chasca_optimizer.py --app-root C:/path/to/GenshinTeamsTracker --case selected

The reviewed baseline is never rewritten. This supervisor imports no Qt or
application execution code; its child uses the application root's real
AppShell, QThread, selected engine and native consumer. Its owned managed job
is removed on success or failure, including a killed child tree. The printed
JSON is the bounded receipt; scratch outputs are not retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.support.chasca_optimizer_baseline import assert_chasca_button_baseline
from tools.experiments.gcsim.chasca_regression.run_measurement import (
    inventory, job_environment, managed_scratch, sample_processes,
    stop_owned_tree,
)


SPEC = ROOT / "tools/experiments/gcsim/chasca_regression/spec.json"
CANDIDATE = ROOT / "tools/experiments/gcsim/chasca_regression/measurement_candidate.json"
PROBE = ROOT / "tools/experiments/gcsim/chasca_regression/probe.py"
BASELINE = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/chasca_button_baseline_v1.json"
MAX_RECEIPT_BYTES = 32_768


class ChascaGateFailure(RuntimeError):
    def __init__(self, reason: str, summary: dict):
        super().__init__(reason)
        self.summary = summary


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_lf(path: Path) -> str:
    """Public JSON identity is independent of checkout CRLF conversion."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def _bounded_observation(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_RECEIPT_BYTES:
        return {}
    try:
        return _json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _runtime_hashes(app_root: Path, native: Path, engine_artifact: Path) -> dict:
    pointer = app_root / "data/gcsim/engines/active_engine.json"
    return {"active_pointer_sha256": _sha(pointer),
            "engine_artifact_sha256": _sha(engine_artifact),
            "native_binary_sha256": _sha(native)}


def _case_summary(observation: dict) -> list[dict]:
    result = []
    for row in observation.get("cases", []):
        if isinstance(row, dict):
            result.append({key: row[key] for key in (
                "mode", "elapsed_seconds", "measured_dps", "standard_error",
                "iterations", "winner_artifact_ids") if key in row})
    return result[:2]


def _preflight(app_root: Path, baseline: dict) -> tuple[Path, Path, Path]:
    if _sha_lf(SPEC) != baseline["fixture"]["spec_sha256"]:
        raise ValueError("Public Chasca spec changed; do not update baseline automatically")
    if _sha_lf(CANDIDATE) != baseline["reviewed_evidence_sha256"]:
        raise ValueError("Reviewed measurement candidate changed; preserve immutable evidence")
    spec = _json(SPEC)
    if spec["engine_id"] != baseline["engine"]["engine_id"] or (
        spec["engine_artifact_sha256"] != baseline["engine"]["artifact_sha256"]
    ):
        raise ValueError("Pinned fixture engine differs from reviewed baseline")
    if not PROBE.is_file():
        raise FileNotFoundError("Chasca button probe is missing")
    python = app_root / ".venv/Scripts/python.exe"
    binary = app_root / "native/gcsim_optimizer/gtt-optimizer.exe"
    if not python.is_file() or not binary.is_file():
        raise FileNotFoundError("Application interpreter or native optimizer is missing")
    store = app_root / "data/gcsim/engines"
    active = str(_json(store / "active_engine.json")["active_engine_id"])
    if active != baseline["engine"]["engine_id"]:
        raise ValueError("Active selected engine changed; no fallback is allowed")
    engine_root = (store / "engines" / active).resolve(strict=True)
    manifest = _json(engine_root / "gtt_engine_manifest.json")
    relative = Path(str(manifest["metadata"]["artifact_relative_path"]))
    artifact = (engine_root / relative).resolve(strict=True)
    if not artifact.is_relative_to(engine_root):
        raise ValueError("Selected engine artifact escapes its installation")
    if _sha(artifact) != baseline["engine"]["artifact_sha256"]:
        raise ValueError("Active selected engine artifact differs from reviewed baseline")
    return python, binary, artifact


def _run_child(job: Path, app_root: Path, python: Path, engine_binary: Path,
               selected_case: str | None) -> tuple[dict, dict]:
    env = job_environment(job, app_root)
    receipt = job / "chasca-observation.json"
    log_path = job / "chasca-probe.log"
    command = [str(python), "-B", "-u", str(PROBE), "--main-root", str(app_root),
               "--receipt", str(receipt)]
    if selected_case:
        command.extend(("--case", selected_case))
    process = None
    reason = None
    counts: dict = {}
    observed: set[tuple[int, int]] = set()
    sampling_available = False
    with log_path.open("xb") as log:
        process = subprocess.Popen(command, cwd=app_root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
        started = time.monotonic()
        next_sample = started
        try:
            while process.poll() is None:
                counts = inventory(job / "chasca-runs")
                if int(counts["file_backed_attempts"]) >= 20:
                    reason = "ENGINE_CALL_CAP_REACHED"
                    stop_owned_tree(process)
                    break
                now = time.monotonic()
                if now - started >= 900:
                    reason = "WATCHDOG_REACHED"
                    stop_owned_tree(process)
                    break
                if now >= next_sample:
                    available, processes = sample_processes(process.pid, engine_binary)
                    sampling_available = sampling_available or available
                    observed.update(processes)
                    next_sample = now + 0.5
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                stop_owned_tree(process)
            process.wait(timeout=15)
    counts = inventory(job / "chasca-runs")
    watch = {
        "file_backed_attempts": counts["file_backed_attempts"],
        "result_backed_invocations": counts["result_backed_invocations"],
        "sampled_descendant_processes_lower_bound": len(observed),
        "process_sampling_available": sampling_available,
        "attempt_cap": 20,
        "watchdog_seconds": 900,
        "child_exit_code": process.returncode,
    }
    if reason is not None:
        raise RuntimeError(f"{reason}; {watch}")
    if process.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        tail = tail.replace(str(app_root), "<app-root>").replace(str(job), "<managed-job>")
        raise RuntimeError(f"Chasca button child failed ({process.returncode}): {tail}")
    if counts["file_backed_attempts"] > 20:
        raise RuntimeError(f"Engine-call cap exceeded: {watch}")
    if not receipt.is_file() or receipt.stat().st_size > MAX_RECEIPT_BYTES:
        raise RuntimeError("Bounded Chasca observation is missing or oversized")
    return _json(receipt), watch


def check_chasca_optimizer(app_root: Path, *, selected_case: str | None = None) -> dict:
    app_root = Path(app_root).resolve(strict=True)
    baseline = _json(BASELINE)
    python, binary, engine_binary = _preflight(app_root, baseline)
    runtime_before = _runtime_hashes(app_root, binary, engine_binary)
    started = time.monotonic()
    observation: dict = {}
    watch: dict = {}
    job_path: Path | None = None
    failure: Exception | None = None
    cleanup_failure: Exception | None = None
    try:
        with managed_scratch() as job:
            job_path = job
            try:
                observation, watch = _run_child(job, app_root, python, engine_binary, selected_case)
                assert_chasca_button_baseline(observation, baseline, selected_case=selected_case)
            except Exception as exc:
                failure = exc
                if not observation:
                    observation = _bounded_observation(job / "chasca-observation.json")
                if not watch:
                    counts = inventory(job / "chasca-runs")
                    watch = {"file_backed_attempts": counts["file_backed_attempts"],
                             "result_backed_invocations": counts["result_backed_invocations"],
                             "attempt_cap": 20, "watchdog_seconds": 900}
    except Exception as exc:
        cleanup_failure = exc
    managed_removed = job_path is not None and not job_path.exists()
    if job_path is not None and not managed_removed and cleanup_failure is None:
        cleanup_failure = RuntimeError(f"Managed Chasca scratch cleanup failed: {job_path}")
    try:
        runtime_after = _runtime_hashes(app_root, binary, engine_binary)
    except (OSError, ValueError) as exc:
        runtime_after = {"read_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    runtime_unchanged = runtime_after == runtime_before
    if not runtime_unchanged and failure is None:
        failure = RuntimeError("Selected engine pointer/artifact or native consumer changed during gate")
    summary = {
        "case": selected_case or "both",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "fixture_spec_sha256": (observation.get("fixture") or {}).get("spec_sha256"),
        "engine_id": (observation.get("fixture") or {}).get("engine_id"),
        "app_native_binary_sha256": runtime_before["native_binary_sha256"],
        "cases": _case_summary(observation),
        "engine_invocation_evidence": watch,
        "engine_invocation_evidence_limit": "file-backed attempts and sampled process lower bound; not exhaustive OS start telemetry",
        "managed_job_removed": managed_removed,
        "runtime_inputs_unchanged": runtime_unchanged,
    }
    if failure is not None or cleanup_failure is not None:
        original = failure or cleanup_failure
        reasons = [f"{type(original).__name__}: {str(original)[:1200]}"]
        if failure is not None and cleanup_failure is not None:
            reasons.append(f"cleanup: {type(cleanup_failure).__name__}: {str(cleanup_failure)[:500]}")
        if not runtime_unchanged:
            reasons.append("selected engine pointer/artifact or native consumer changed during gate")
        raise ChascaGateFailure("; ".join(reasons), summary)
    if not managed_removed:
        raise ChascaGateFailure("Managed Chasca scratch was not removed", summary)
    return {"status": "passed", **summary}


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--app-root", type=Path, default=ROOT)
    parser.add_argument("--case", choices=("selected", "all_sets"))
    args = parser.parse_args()
    try:
        result = check_chasca_optimizer(args.app_root, selected_case=args.case)
    except ChascaGateFailure as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)[:2400], **exc.summary},
                         sort_keys=True), flush=True)
        return 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "case": args.case or "both",
                          "reason": f"{type(exc).__name__}: {str(exc)[:2400]}",
                          "managed_scratch_state": (
                              "cleanup_failed" if "scratch cleanup failed" in str(exc)
                              else "removed_or_not_allocated"),
                          "managed_scratch_owner": "tools.managed_optimizer_experiment.managed_scratch"}),
              flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
