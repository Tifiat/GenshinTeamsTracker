"""Run the one authorized managed measurement of the public Chasca fixture."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import managed_scratch

PROBE = ROOT / "tools/experiments/gcsim/chasca_regression/probe.py"
SPEC = ROOT / "tools/experiments/gcsim/chasca_regression/spec.json"
CANDIDATE = PROBE.parent / "measurement_candidate.json"
RECEIPT = ROOT / "docs/optimizer-evidence/2026-10-08-chasca-regression/measurement-run-01.json"
PREPARATION = ROOT / "docs/optimizer-evidence/2026-10-08-chasca-regression/preparation-03.json"
MAIN_FILES = (
    "run_workspace/gcsim/optimizer_go_inputs.py", "run_workspace/gcsim/optimizer_go_requests.py",
    "run_workspace/gcsim/optimizer_go_selected.py", "run_workspace/gcsim/optimizer_go_all.py",
    "run_workspace/gcsim/optimizer_go_all_sources.py", "run_workspace/gcsim/optimizer_go_session.py",
    "run_workspace/gcsim/optimizer_go_contracts.py", "run_workspace/gcsim/optimizer_run_retention.py",
    "run_workspace/gcsim/selected_team_config.py", "run_workspace/gcsim/virtual_roster.py",
    "run_workspace/gcsim/optimizer_engine_context.py", "run_workspace/gcsim/engine_store.py",
    "run_workspace/gcsim/artifact_set_catalog.py", "hoyolab_export/artifact_db.py",
    "hoyolab_export/artifact_fingerprint.py", "hoyolab_export/stat_normalization.py",
    "ui/app_shell.py", "tests/support/optimizer_button_fixture.py",
    "tests/ui/gcsim_browser/test_optimizer_button_backend.py",
)
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(main: Path) -> dict:
    store = main / "data/gcsim/engines"
    pointer_path = store / "active_engine.json"
    pointer = json.loads(pointer_path.read_bytes())
    engine_id = str(pointer["active_engine_id"])
    engine = store / "engines" / engine_id
    manifest_path = engine / "gtt_engine_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    metadata = manifest["metadata"]
    sources = [{"path": name, "sha256": sha(main / name)} for name in MAIN_FILES]
    head = subprocess.run(["git", "-C", str(main), "rev-parse", "HEAD"],
                          capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    return {
        "main_head": head, "active_engine_id": engine_id,
        "active_pointer_sha256": sha(pointer_path),
        "native_binary_sha256": sha(main / "native/gcsim_optimizer/gtt-optimizer.exe"),
        "engine_manifest_sha256": sha(manifest_path),
        "engine_manifest_tree_sha256": str(manifest["engine_tree_hash"]),
        "engine_artifact_relative_path": str(metadata["artifact_relative_path"]),
        "engine_artifact_sha256": sha(engine / str(metadata["artifact_relative_path"])),
        "source_hashes": sources,
    }


def inventory(root: Path) -> dict:
    compact = list(root.rglob("compact-request-*.json")) if root.is_dir() else []
    compact_done = sum(p.with_name(p.name.replace("compact-request-", "compact-member-", 1)).is_file()
                       for p in compact)
    captures = list(root.rglob("capture-request.json")) if root.is_dir() else []
    capture_done = sum(p.with_name("member.json").is_file() for p in captures)
    configs = {p.parent for p in root.rglob("config.txt") if root.is_dir()
               and any(part.casefold() == "final-n500" for part in p.parts)}
    done = sum((p / "result.json").is_file() for p in configs)
    attempts = len(compact) + len(captures) + len(configs)
    return {
        "python_compact_requests": len(compact), "python_compact_results": compact_done,
        "native_capture_requests": len(captures), "native_capture_results": capture_done,
        "final_n500_config_dirs": len(configs), "final_n500_result_files": done,
        "file_backed_attempts": attempts,
        "result_backed_invocations": compact_done + capture_done + done,
    }


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_bytes())
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def scalar_values(payload: dict, keys: tuple[str, ...]) -> dict:
    """Keep only bounded scalar counters/timings; never copy nested search data."""
    result = {}
    for key in keys:
        value = payload.get(key)
        if value is None or isinstance(value, (int, float, bool)):
            result[key] = value
        elif isinstance(value, str) and len(value) <= 160:
            result[key] = value
    return result


def completed_modes(root: Path) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for path in root.rglob("selected-result.json"):
        result = read_json(path)
        timing = read_json(path.parent / "adapter-timings.json")
        if result is None or timing is None:
            continue
        mode = "all_sets" if path.parent.name.startswith("all_sets-") else "selected"
        measured = result.get("measured") if isinstance(result.get("measured"), dict) else {}
        row = {
            "mode": mode, "status": result.get("status"), "formula_dps": result.get("formula_dps"),
            "measured": {k: measured[k] for k in ("dps", "standard_error", "iterations") if k in measured},
            "adapter_timings": {k: timing[k] for k in (
                "prepare_inputs_ms", "request_preflight_ms", "formula_inputs_ms",
                "optimizer_process_ms", "total_elapsed_ms", "terminal_status") if k in timing},
        }
        if mode == "all_sets":
            data = read_json(path.parent / "verification/all-sets-result.json") or {}
            keys = ("search_stop_reason", "capture_members", "search_expansions",
                    "guides", "queued", "unqueued_across_guides", "pending", "guide_seconds",
                    "proposal_seconds", "search_seconds", "total_elapsed_ms",
                    "source_preparation_seconds", "search_algorithm")
            row["search_and_verification"] = scalar_values(data, keys)
        else:
            debug = next(iter(path.parent.rglob("gob7-result.json")), None)
            data = read_json(debug) if debug else None
            data = data or {}
            search = data.get("search") if isinstance(data.get("search"), dict) else {}
            keys = ("completed_cycles", "accepted_steps", "pair_generated", "pair_evaluated",
                    "pair_invalid", "pair_duplicates", "stop_reason")
            row["search_and_verification"] = {
                **scalar_values(search, keys),
                **scalar_values(data, ("compile_elapsed_ms", "search_elapsed_ms", "total_elapsed_ms")),
            }
        rows.append(row)
    return sorted(rows, key=lambda row: 0 if row["mode"] == "all_sets" else 1)


def sample_processes(pid: int, binary: Path) -> tuple[bool, set[tuple[int, int]]]:
    try:
        import psutil
    except ImportError:
        return False, set()
    expected, found = os.path.normcase(os.path.realpath(binary)), set()
    try:
        children = psutil.Process(pid).children(recursive=True)
    except (psutil.Error, OSError):
        return True, found
    for child in children:
        try:
            if os.path.normcase(os.path.realpath(child.exe())) == expected:
                found.add((child.pid, int(child.create_time() * 1000)))
        except (psutil.Error, OSError):
            pass
    return True, found


def stop_owned_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=20, check=False)
    else:
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def job_environment(job: Path, main: Path) -> dict[str, str]:
    variables = {
        "TMP": "tmp", "TEMP": "temp", "TMPDIR": "tmpdir", "USERPROFILE": "profile",
        "APPDATA": "appdata/roaming", "LOCALAPPDATA": "appdata/local",
        "XDG_CONFIG_HOME": "xdg/config", "XDG_CACHE_HOME": "xdg/cache",
        "XDG_DATA_HOME": "xdg/data", "XDG_STATE_HOME": "xdg/state", "XDG_RUNTIME_DIR": "xdg/runtime",
        "PYTHONPYCACHEPREFIX": "python-cache", "GTT_RULE_CACHE_DIR": "rules",
        "GOCACHE": "go-cache", "GOTMPDIR": "go-temp", "GOMODCACHE": "go-modcache",
    }
    env = os.environ.copy()
    for name, relative in variables.items():
        path = job / relative
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env.update({
        "GTT_SCRATCH_DIR": str(job), "GTT_MANAGED_GO_CACHE": str(job / "go-cache"),
        "GTT_RULE_BUNDLED_CACHE_DIR": str(main / "native/gcsim_optimizer/set-rule-cache"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "QT_QPA_PLATFORM": "offscreen", "GOPROXY": "off", "GOTOOLCHAIN": "local",
    })
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-root", type=Path, default=Path(r"C:\Users\user\Desktop\GenshinTeamsTracker"))
    args = parser.parse_args()
    main = args.main_root.resolve(strict=True)
    python = main / ".venv/Scripts/python.exe"
    if not python.is_file() or not PROBE.is_file():
        raise FileNotFoundError("Current-main Python or frozen probe is missing")
    if CANDIDATE.exists() or RECEIPT.exists():
        raise FileExistsError("Prior measurement exists; refusing overwrite")
    spec = json.loads(SPEC.read_bytes())
    expected = 2 * len(spec["cases"]) + sum(
        int(c["set_groups"]) * int(c["total_rows_per_group"]) for c in spec["cases"])
    if ([(c["mode"], c["set_groups"], c["total_rows_per_group"]) for c in spec["cases"]]
            != [("all_sets", 3, 3), ("selected", 1, 3)]
            or expected != 16 or int(spec["normal_iteration"]) != 500
            or int(spec["engine_call_cap"]) != 20):
        raise ValueError("Measurement scope differs from authorization")
    before = snapshot(main)
    prior = read_json(PREPARATION)
    if not prior or not isinstance(prior.get("main_snapshot_after"), dict):
        raise RuntimeError("Proven preparation-03 snapshot is unavailable")
    proven = prior["main_snapshot_after"]
    for key in ("active_engine_id", "active_pointer_sha256", "native_binary_sha256",
                "engine_manifest_sha256", "engine_manifest_tree_sha256",
                "engine_artifact_relative_path", "engine_artifact_sha256"):
        if before.get(key) != proven.get(key):
            raise RuntimeError(f"Current main differs from proven preparation snapshot: {key}")
    proven_sources = {row["path"]: row["sha256"] for row in proven.get("source_hashes", [])}
    current_sources = {row["path"]: row["sha256"] for row in before["source_hashes"]}
    if any(current_sources.get(name) != digest for name, digest in proven_sources.items()):
        raise RuntimeError("Current main optimizer inputs differ from preparation-03 source hashes")
    if before["active_engine_id"] != spec["engine_id"] or before["engine_artifact_sha256"] != spec["engine_artifact_sha256"]:
        raise RuntimeError("Selected engine differs from the frozen public fixture")

    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    job = process = log_path = None
    reason = failure = None
    exit_code = None
    counts, modes, observed = {}, [], set()
    sampled_available = False
    cleanup = False
    try:
        with managed_scratch() as job:
            run_root = job / "chasca-runs"
            env = job_environment(job, main)
            log_path = job / "probe.log"
            command = [str(python), "-B", "-u", str(PROBE),
                       "--main-root", str(main), "--receipt", str(CANDIDATE)]
            print(json.dumps({"stage": "started", "watchdog_seconds": 900,
                              "expected_attempts": expected, "attempt_cap": 20}), flush=True)
            with log_path.open("xb") as log:
                process = subprocess.Popen(command, cwd=main, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT)
                launched, next_sample = time.monotonic(), time.monotonic()
                announced = set()
                try:
                    while process.poll() is None:
                        now = time.monotonic()
                        counts = inventory(run_root)
                        for row in completed_modes(run_root):
                            mode = row["mode"]
                            if mode not in announced:
                                announced.add(mode)
                                modes.append(row)
                                print(json.dumps({
                                    "stage": "case_complete", "case": mode,
                                    "backend_elapsed_ms": row["adapter_timings"].get("total_elapsed_ms"),
                                    "measured": row["measured"],
                                    "file_backed_attempts": counts["file_backed_attempts"],
                                    "result_backed_invocations": counts["result_backed_invocations"],
                                }, separators=(",", ":")), flush=True)
                        if int(counts.get("file_backed_attempts", 0)) >= 20:
                            reason = "file_backed_attempt_cap_reached"
                            stop_owned_tree(process)
                            break
                        if now - launched >= 900:
                            reason = "watchdog_reached"
                            stop_owned_tree(process)
                            break
                        if now >= next_sample:
                            engine_binary = (main / "data/gcsim/engines/engines" / str(spec["engine_id"])
                                             / str(before["engine_artifact_relative_path"]))
                            available, pids = sample_processes(process.pid, engine_binary)
                            sampled_available = sampled_available or available
                            observed.update(pids)
                            next_sample = now + 0.5
                        time.sleep(0.2)
                finally:
                    # Never let the managed context clean a job while its owned child tree is live.
                    if process.poll() is None:
                        stop_owned_tree(process)
                    process.wait(timeout=15)
                exit_code = process.returncode
                counts, modes = inventory(run_root), completed_modes(run_root)
                if reason:
                    failure = {"kind": reason}
                elif exit_code != 0:
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:]
                    tail = tail.replace(str(main), "<main>").replace(str(job), "<managed-job>")
                    failure = {"kind": "probe_failed", "exit_code": exit_code, "log_tail": tail}
                elif not CANDIDATE.is_file():
                    failure = {"kind": "candidate_receipt_missing", "exit_code": exit_code}
                else:
                    print(json.dumps({"stage": "probe_complete", "candidate_sha256": sha(CANDIDATE),
                                      "attempts": counts.get("file_backed_attempts"),
                                      "result_outputs": counts.get("result_backed_invocations")},
                                     separators=(",", ":")), flush=True)
    except Exception as error:
        failure = failure or {"kind": "supervisor_error", "type": type(error).__name__, "message": str(error)[:600]}
    finally:
        cleanup = job is not None and not job.exists()

    after = snapshot(main)
    unchanged = before == after
    candidate = read_json(CANDIDATE) if CANDIDATE.is_file() else None
    summary = None
    if candidate:
        summary = {
            "status": candidate.get("status"),
            "cases": [{k: item[k] for k in ("mode", "elapsed_seconds", "formula_dps",
                                             "measured_dps", "warnings") if k in item}
                      for item in candidate.get("cases", []) if isinstance(item, dict)],
            "expected_engine_calls": candidate.get("expected_engine_calls"),
            "engine_call_cap": candidate.get("engine_call_cap"),
        }
    status = "passed" if failure is None and cleanup and unchanged and summary else "failed"
    receipt = {
        "schema_kind": "chasca_optimizer_measurement_run_v1", "status": status,
        "started_utc": started, "elapsed_seconds": round(time.monotonic() - timer, 3),
        "scope": {"modes": ["all_sets", "selected"], "watchdog_seconds": 900,
                  "expected_file_backed_attempts": expected, "attempt_cap": 20,
                  "normal_iterations": 500, "engine_builds": 0, "native_builds": 0,
                  "installation_writes": 0},
        "preparation_head_delta": {
            "preparation_head": proven["main_head"],
            "measurement_head": before["main_head"],
            "parent_review": "documentation-only delta; source and runtime identities match preparation-03",
            "paths": [
                "docs/handoff/CATALOG.md",
                "docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md",
                "docs/handoff/READABLE_ROTATION_EDITOR.md",
                "docs/rotation-evidence/2026-10-08_dictionary.md",
            ],
        },
        "main_snapshot_before": before, "main_snapshot_after": after,
        "main_source_pointer_native_engine_unchanged": unchanged,
        "candidate_sha256": sha(CANDIDATE) if CANDIDATE.is_file() else None,
        "candidate_summary": summary, "mode_backend_summaries": modes,
        "engine_invocation_evidence": {
            **counts,
            "interpretation": "File-backed attempts/results, not OS process-start telemetry; reviewed sources use one launch per compact request and finalist config.",
            "sampled_descendant_processes_lower_bound": len(observed),
            "process_sampling_available": sampled_available,
        },
        "probe_exit_code": exit_code, "failure": failure,
        "managed_job_removed": cleanup,
        "managed_cleanup_owner": "tools.managed_optimizer_experiment.managed_scratch",
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    if len(data) > 32768:
        raise ValueError("Run receipt exceeds 32 KiB")
    with RECEIPT.open("xb") as stream:
        stream.write(data)
    print(json.dumps({"stage": "receipt_saved", "status": status, "receipt": str(RECEIPT),
                      "candidate": str(CANDIDATE) if CANDIDATE.exists() else None,
                      "cleanup": cleanup, "source_unchanged": unchanged,
                      "attempts": counts.get("file_backed_attempts"),
                      "result_outputs": counts.get("result_backed_invocations"),
                      "sampled_process_lower_bound": len(observed)}, separators=(",", ":")), flush=True)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
