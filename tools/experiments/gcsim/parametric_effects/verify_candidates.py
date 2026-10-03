"""Bounded ordinary n500 checks for the 2026-09-20 source-search candidates.

Temporary single-Flins research gate, owned by the Go optimizer design. It uses
the active installed runner, not the candidate source overlay. Inputs/results
exist only in the caller's managed job; stdout is the compact receipt. Remove
with the parametric experiment helpers after the real product-path gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
ACTORS = ("columbina", "flins", "ineffa", "jahoda")


def validate_assignments(rows: list) -> None:
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2:
        raise ValueError("At most two candidate checks plus the control")
    for row in rows:
        if set(row) != {"name", "assignment"} or row["name"] not in {"restricted", "expanded"}:
            raise ValueError("Unknown candidate receipt shape")
        a = row["assignment"]
        if not isinstance(a, list) or len(a) != 4 or any(not isinstance(ids, list) or len(ids) != 5 for ids in a):
            raise ValueError("Expected four five-item assignments")
        ids = [value for parts in a for value in parts]
        if any(type(x) is not int or x <= 0 for x in ids) or len(set(ids)) != 20:
            raise ValueError("Expected twenty unique positive physical IDs")


def main() -> None:
    job = owned_job()  # fail before imports/account/active-engine reads
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignments", required=True)
    rows = json.loads(parser.parse_args().assignments)
    validate_assignments(rows)
    from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
        SLOTS, _build_config, _non_artifact_hash, _ordinary_budget,
        _virtual_selected_team, _scratch_environment, _bound_artifact_registry_source,
        normalize_optimizer_rotation_shell, load_active_gcsim_optimizer_engine_context,
        run_active_gcsim_artifact,
    )
    manifest = json.loads((ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json").read_bytes())
    witness = json.loads((ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json").read_bytes())
    team = manifest["teams"]["lunar_charged"]
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.artifact_sha256 != witness["engine"]["artifact_sha256"]:
        raise ValueError("Active engine differs from the captured source identity")
    registry = _bound_artifact_registry_source(Path(engine.engine_root))
    profiles = team["virtual_profiles"]
    selected_team = _virtual_selected_team(profiles)
    rotation = normalize_optimizer_rotation_shell((ROOT / team["rotation_file"]).read_text(encoding="utf-8"))
    expected = _non_artifact_hash(_ordinary_budget(witness["inputs"][0]["config"], iterations=500, workers=4))
    cases = [(row["name"], {actor: dict(zip(SLOTS, row["assignment"][i])) for i, actor in enumerate(ACTORS)}) for row in rows]
    cases.append(("saved_strong_control", witness["inputs"][0]["reference_ids"]))
    with _scratch_environment(job):
        rotation_path = job / "rotation.optimizer.txt"
        rotation_path.write_text(rotation.optimizer_text, encoding="utf-8")
        for i, (name, ids) in enumerate(cases):
            start = time.perf_counter()
            case = job / f"case-{i}"
            config = _build_config(db_path=ROOT / manifest["db_path"], profiles=profiles, selected_team=selected_team,
                                   rotation_path=rotation_path, registry_path=registry, ids_by_wearer=ids,
                                   case_root=case, iterations=500)
            if _non_artifact_hash(config) != expected:
                raise ValueError("Non-artifact config differs from saved source control")
            result = run_active_gcsim_artifact(config, run_dir=case / "ordinary", timeout_seconds=90,
                                              expected_engine_id=engine.engine_id)
            if not result.success or result.summary.iterations != 500:
                raise RuntimeError(f"Ordinary verification failed: {result.status}: {result.error}")
            receipt = dict(name=name, assignment=ids, iterations=500, dps=result.summary.dps_mean,
                           standard_error=result.summary.dps_se, duration_mean=result.summary.duration_mean,
                           failed_actions=list(result.summary.failed_actions), seconds=time.perf_counter()-start,
                           non_artifact_sha256=expected, config_sha256=hashlib.sha256(config.encode()).hexdigest(),
                           engine_id=engine.engine_id, engine_sha256=engine.artifact_sha256)
            print("CANDIDATE_ORDINARY " + json.dumps(receipt), flush=True)
    after = load_active_gcsim_optimizer_engine_context()
    if (engine.engine_id, engine.artifact_sha256) != (after.engine_id, after.artifact_sha256):
        raise RuntimeError("Active engine changed during verification")


if __name__ == "__main__":
    main()
