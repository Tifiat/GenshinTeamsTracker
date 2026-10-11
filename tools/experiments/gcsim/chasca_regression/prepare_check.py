"""Cheap disposable-input check, no Qt/application/engine process.

The managed supervisor must execute this as a child and await its exit before
cleanup, so no SQLite handle or exception traceback can retain the fixture DB.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys
import traceback


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.main_root.resolve(strict=True)))
    from run_workspace.gcsim.engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR
    from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
    from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
    from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedRequest
    from run_workspace.gcsim.optimizer_go_inputs import prepare_optimizer_inputs
    from fixture import create_fixture, SPEC_PATH

    rows = []
    record = {"status": "started", "engine_calls": 0, "modes": rows}
    try:
        spec = json.loads(SPEC_PATH.read_bytes())
        fixture_root = args.job / "chasca-fixture"
        fixture_root.mkdir()
        database, team, inventory = create_fixture(fixture_root, DEFAULT_GCSIM_ENGINE_STORE_DIR)
        record["fixture"] = inventory
        for case in spec["cases"]:
            mode = case["mode"]
            directory = args.job / ("prepared-" + mode)
            directory.mkdir()
            request_class = GcsimOptimizerGoAllSetsRequest if mode == "all_sets" else GcsimOptimizerGoSelectedRequest
            request = request_class(db_path=str(database), selected_team=team,
                rotation_shell_text=spec["rotation"], team_index=0,
                engine_store_dir=str(DEFAULT_GCSIM_ENGINE_STORE_DIR),
                optimizer_binary_path=str(DEFAULT_OPTIMIZER_BINARY),
                run_root=str(args.job / "unused-runs"), infinite_energy_enabled=True,
                set_group_limit=case["set_groups"], builds_per_group=case["total_rows_per_group"],
                fast_mode=False, expanded_limits=False)
            prepared = prepare_optimizer_inputs(request, directory, mode=mode)
            payload = prepared["request"]
            assert len(payload["artifacts"]) == 600
            assert len(payload["wearers"]) == 4
            assert payload["result_options"]["fast_mode"] is False
            assert payload["result_options"]["set_group_limit"] == case["set_groups"]
            assert payload["result_options"]["builds_per_group"] == case["total_rows_per_group"]
            assert payload["engine"]["artifact_sha256"] == spec["engine_artifact_sha256"]
            rows.append({"mode": mode, "request_sha256": prepared["request_sha256"],
                         "artifact_count": len(payload["artifacts"]), "wearer_count": 4})
        record["status"] = "prepared_both_modes"
    except Exception as error:
        record.update(status="preparation_failure", error_type=type(error).__name__,
                      error=str(error)[:1000], traceback=traceback.format_exc()[-4000:])
    finally:
        gc.collect()
        (args.job / "preparation-child-result.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"status": record["status"], "prepared_modes": len(rows)}), flush=True)
    return 0 if record["status"] == "prepared_both_modes" else 1


if __name__ == "__main__":
    raise SystemExit(main())
