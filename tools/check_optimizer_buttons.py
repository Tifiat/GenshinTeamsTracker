"""Run the reviewed real-backend button gate in disposable public data.

Uses this checkout's installed native consumer and selected GCSIM engine unless
explicit read-only paths are supplied. Does not build/install anything or use
the user's account. All generated databases, settings and runs are cleaned.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import managed_scratch
from run_workspace.gcsim.optimizer_process_paths import optimizer_process_workdir


def button_gate_environment(job: Path, engine_store: Path, optimizer_binary: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name, relative in {
        "TMP": "temp", "TEMP": "temp",
        "APPDATA": "appdata/roaming", "LOCALAPPDATA": "appdata/local",
        "XDG_CONFIG_HOME": "xdg/config", "XDG_CACHE_HOME": "xdg/cache",
        "XDG_STATE_HOME": "xdg/state", "GTT_RULE_CACHE_DIR": "rules",
    }.items():
        path = job / relative
        path.mkdir(parents=True, exist_ok=True)
        environment[name] = str(path)
    environment.update({
        "GTT_SCRATCH_DIR": str(job),
        "GTT_OPTIMIZER_BUTTON_GATE": "1",
        "GTT_OPTIMIZER_BUTTON_BASELINE_CANDIDATE": "0",
        "GTT_OPTIMIZER_BUTTON_ENGINE_STORE": str(engine_store),
        "GTT_OPTIMIZER_BUTTON_TEST_BINARY": str(optimizer_binary),
        "GTT_RULE_BUNDLED_CACHE_DIR": str(ROOT / "native/gcsim_optimizer/set-rule-cache"),
        "QT_QPA_PLATFORM": "offscreen", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONPATH": str(ROOT),
    })
    return environment


def run_button_gate(engine_store: Path, optimizer_binary: Path, *, timeout_seconds: int = 540,
                    case: str = "") -> int:
    engine_store = engine_store.resolve(strict=True)
    optimizer_binary = optimizer_binary.resolve(strict=True)
    if not engine_store.is_dir() or not optimizer_binary.is_file():
        raise ValueError("Selected engine store and native optimizer must exist")
    if not 1 <= timeout_seconds <= 600:
        raise ValueError("The test watchdog must be between 1 and 600 seconds")
    observations = None
    with managed_scratch() as job:
        env = button_gate_environment(job, engine_store, optimizer_binary)
        env["GTT_OPTIMIZER_BUTTON_CASE"] = case
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "unittest", "-v", "-f",
             "tests.ui.gcsim_browser.test_optimizer_button_backend"],
            cwd=optimizer_process_workdir(ROOT), env=env, stdin=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        try:
            code = process.wait(timeout=timeout_seconds)
            output = job / "button-gate-measurements.json"
            if output.is_file():
                observations = json.loads(output.read_bytes())
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=15,
                    )
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=15)
    # Only bounded scalars survive; no fixture DB or raw capture is retained.
    print(json.dumps({"status": "pass" if code == 0 else "fail",
        "cases": [{"mode": row["mode"], "fast_mode": row["fast_mode"], "elapsed_ms": row["elapsed_ms"],
                   "formula_dps": row["formula_dps"], "measured": row["measured"]}
                  for row in (observations or [])], "managed_job_cleaned": True}, indent=2))
    return code


def main() -> int:
    from run_workspace.gcsim.engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR
    from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY

    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--engine-store", type=Path, default=DEFAULT_GCSIM_ENGINE_STORE_DIR)
    parser.add_argument("--optimizer-binary", type=Path, default=DEFAULT_OPTIMIZER_BINARY)
    parser.add_argument("--case", choices=("selected_fast", "all_sets_fast", "selected_verified", "all_sets_verified"),
                        default="", help="rerun only the named case after confirming the computer is idle")
    args = parser.parse_args()
    return run_button_gate(args.engine_store, args.optimizer_binary, case=args.case)


if __name__ == "__main__":
    raise SystemExit(main())
