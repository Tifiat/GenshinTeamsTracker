"""Measure the public Chasca fixture through actual AppShell button handlers.

Review-only prototype. Run under this checkout's managed_optimizer_experiment.py
with a 900-second whole-probe watchdog and an independent <=20 engine-call watch.
The selected engine/native binary and all application imports come from the
explicit current main checkout. The managed runner owns/cleans the DB, run
roots, temporary files and process descendants. This script exports only a
bounded measurement receipt; it never compares or updates a golden baseline.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch


def _load_main(main_root: Path):
    main_root = main_root.resolve(strict=True)
    if not (main_root / "tests" / "support" / "optimizer_button_fixture.py").is_file():
        raise ValueError("--main-root must be the current main application checkout")
    sys.dont_write_bytecode = True
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(main_root))
    from tests.ui.gcsim_browser.test_optimizer_button_backend import ButtonHarness, _APP
    from run_workspace.gcsim.settings import GcsimOptimizerSettings
    from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
    from run_workspace.gcsim.engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR
    from run_workspace.gcsim import optimizer_run_retention
    from ui.app_shell import AppShell
    if Path(inspect.getfile(AppShell)).resolve().parents[1] != main_root:
        raise RuntimeError("AppShell import resolved outside current main")
    if Path(DEFAULT_OPTIMIZER_BINARY).resolve().parents[2] != main_root:
        raise RuntimeError("Native consumer path resolved outside current main")
    if Path(DEFAULT_GCSIM_ENGINE_STORE_DIR).resolve().parents[2] != main_root:
        raise RuntimeError("Engine store path resolved outside current main")
    if Path(inspect.getfile(optimizer_run_retention)).resolve().parents[2] != main_root:
        raise RuntimeError("Managed lease helper resolved outside current main")
    # The lifecycle owner is this isolated checkout's managed runner, while
    # its imported application/lease code resolves from current main.
    managed_path = Path(__file__).resolve().parents[4] / "tools" / "managed_optimizer_experiment.py"
    module_spec = importlib.util.spec_from_file_location("_chasca_managed_runner", managed_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("Cannot load isolated managed scratch owner")
    managed_module = importlib.util.module_from_spec(module_spec)
    import_path = list(sys.path)
    try:
        module_spec.loader.exec_module(managed_module)
    finally:
        sys.path[:] = import_path
    owned_job = managed_module.owned_job
    return owned_job, ButtonHarness, _APP, GcsimOptimizerSettings, DEFAULT_OPTIMIZER_BINARY, DEFAULT_GCSIM_ENGINE_STORE_DIR


def _click(harness, app, settings_type, case: dict, rotation: str, watchdog: float):
    mode = str(case["mode"])
    harness.payloads.clear()
    harness.workspace.rotation_editor.setPlainText(rotation)
    button = (harness.workspace.optimizer_selected_button if mode == "selected"
              else harness.workspace.optimizer_all_sets_button)
    if not button.isEnabled():
        raise AssertionError(f"{mode} optimizer button disabled")
    settings = settings_type(int(case["set_groups"]), int(case["total_rows_per_group"]), False, False)
    with patch("ui.app_shell.effective_gcsim_optimizer_settings", return_value=settings):
        start = time.monotonic()
        button.click()
        deadline = start + watchdog
        while not harness.payloads or harness._gcsim_browser_run_thread is not None:
            app.processEvents()
            if time.monotonic() >= deadline:
                worker, thread = harness._gcsim_browser_run_worker, harness._gcsim_browser_run_thread
                if worker is not None:
                    worker.cancel()
                if thread is not None:
                    thread.quit()
                    thread.wait(15_000)
                raise TimeoutError(f"{mode} button exceeded {watchdog}s watchdog")
            time.sleep(0.005)
    if len(harness.payloads) != 1:
        raise AssertionError(f"{mode} returned {len(harness.payloads)} terminal payloads")
    return harness.payloads[0], round(time.monotonic() - start, 3)


def _measure(payload: dict, elapsed_s: float, case: dict, rotation: str, fixture_ids: set[int]) -> dict:
    if not payload.get("success") or payload.get("status") != "success":
        raise AssertionError(f"{case['mode']} failed: {payload.get('error')}")
    result = payload["result"]
    if result.get("status") != "success":
        raise AssertionError(f"{case['mode']} native result: {result.get('status')}")
    winner_ids = [int(item["artifact_id"]) for item in result["winner"]]
    if len(winner_ids) != 20 or len(set(winner_ids)) != 20 or not set(winner_ids) <= fixture_ids:
        raise AssertionError("Winner is not a unique 20-item synthetic team")
    formula_dps = Decimal(str(result["formula_dps"]))
    measured = result.get("measured")
    if not formula_dps.is_finite() or formula_dps <= 0 or not measured:
        raise AssertionError("Normal mode requires finite estimate and GCSIM measurement")
    measured_dps = Decimal(str(measured["dps"]))
    if not measured_dps.is_finite() or measured_dps <= 0:
        raise AssertionError("Measured GCSIM DPS must be finite and positive")
    run_dir = Path(payload["run_dir"])
    request = json.loads((run_dir / "request.json").read_bytes())
    if len(request["artifacts"]) != 600 or request["context"]["rotation"]["text"] != rotation:
        raise AssertionError("Backend input changed the synthetic inventory or rotation")
    if request["result_options"]["fast_mode"] is not False:
        raise AssertionError("Probe requires normal n=500 final verification")
    if request["engine"]["artifact_sha256"] != "7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c":
        raise AssertionError("Backend request changed the selected engine artifact")
    return {
        "mode": case["mode"], "set_groups": case["set_groups"],
        "total_rows_per_group": case["total_rows_per_group"],
        "elapsed_seconds": elapsed_s, "formula_dps": str(formula_dps),
        "measured_dps": str(measured_dps), "winner_artifact_ids": winner_ids,
        "request_sha256": hashlib.sha256((run_dir / "request.json").read_bytes()).hexdigest(),
        "engine_artifact_sha256": request["engine"]["artifact_sha256"],
        "warnings": [str(w) for w in result.get("warnings", ())][:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    own_dir = Path(__file__).resolve().parent
    receipt = args.receipt.resolve()
    if receipt.parent != own_dir or receipt.name != "measurement_candidate.json":
        raise ValueError("Only this prototype's bounded measurement_candidate.json may be exported")
    if receipt.exists():
        raise FileExistsError("Preserve the prior measured receipt; choose a reviewed replacement step")
    owned_job, ButtonHarness, app, settings_type, binary, engine_store = _load_main(args.main_root)
    if not Path(binary).is_file():
        raise FileNotFoundError("Current main native consumer is missing")
    native_sha256 = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    from fixture import SPEC_PATH, create_fixture
    spec = json.loads(SPEC_PATH.read_bytes())
    cases = tuple(spec["cases"])
    if tuple((c["mode"], c["set_groups"], c["total_rows_per_group"]) for c in cases) != (
        ("all_sets", 3, 3), ("selected", 1, 3)
    ) or int(spec["normal_iteration"]) != 500 or int(spec["engine_call_cap"]) != 20 or (
        int(spec["managed_watchdog_seconds"]), int(spec["internal_watchdog_seconds"])
    ) != (900, 870):
        raise ValueError("Unexpected measurement scope")
    # Two compact preparations per mode + at most nine and three requested
    # ordinary finalist rows = 16 expected calls. A separate process-level
    # watcher must stop the managed run at 20 actual engine invocations.
    expected_calls = 2 * len(cases) + sum(int(c["set_groups"]) * int(c["total_rows_per_group"]) for c in cases)
    if expected_calls != 16 or expected_calls > int(spec["engine_call_cap"]):
        raise ValueError("Proposed result limits exceed engine-call budget")
    job = owned_job()
    # No live settings/cache write even when the caller's environment is rich.
    for name, relative in {"APPDATA": "appdata/roaming", "LOCALAPPDATA": "appdata/local",
        "XDG_CONFIG_HOME": "xdg/config", "XDG_CACHE_HOME": "xdg/cache",
        "XDG_STATE_HOME": "xdg/state", "GTT_RULE_CACHE_DIR": "rules"}.items():
        location = job / relative
        location.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(location)
    os.environ["GTT_RULE_BUNDLED_CACHE_DIR"] = str(args.main_root / "native/gcsim_optimizer/set-rule-cache")
    fixture_root = job / "chasca-fixture"
    fixture_root.mkdir()
    db_path, team, fixture_receipt = create_fixture(fixture_root, engine_store)
    run_root = job / "chasca-runs"
    run_root.mkdir()
    paths = {"run_root": str(run_root), "engine_store_dir": str(engine_store),
             "optimizer_binary_path": str(binary)}
    harness = ButtonHarness(db_path, team, paths)
    metrics = []
    fixture_ids = set(range(1, 601))
    deadline = time.monotonic() + float(spec["internal_watchdog_seconds"])
    try:
        for case in cases:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Whole Chasca probe exceeded its internal watchdog")
            payload, elapsed_s = _click(
                harness, app, settings_type, case, spec["rotation"],
                remaining,
            )
            metrics.append(_measure(payload, elapsed_s, case, spec["rotation"], fixture_ids))
    finally:
        harness.close()
        harness.deleteLater()
        app.processEvents()
    output = {
        "status": "unreviewed_measurement_candidate", "baseline_policy": spec["baseline_policy"],
        "fixture": fixture_receipt, "cases": metrics,
        "main_native_binary_sha256": native_sha256,
        "expected_engine_calls": expected_calls,
        "actual_engine_calls": "requires_independent_process_watch",
        "engine_call_cap": int(spec["engine_call_cap"]),
    }
    # Only the bounded receipt survives managed scratch cleanup. No request,
    # account DB, config, result directory, or raw simulator output is exported.
    receipt_bytes = (json.dumps(output, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(receipt_bytes) > 32768:
        raise ValueError("Measurement receipt exceeds its bounded evidence budget")
    with receipt.open("xb") as stream:
        stream.write(receipt_bytes)
    print(json.dumps({"receipt": str(receipt), "elapsed_seconds": [m["elapsed_seconds"] for m in metrics],
                      "measured_dps": [m["measured_dps"] for m in metrics]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
