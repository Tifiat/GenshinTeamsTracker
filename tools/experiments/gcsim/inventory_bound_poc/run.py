"""Limited-inventory bound concept, not a production optimizer or fallback.

Uses the dated Flins virtual witness and the active product engine. The Go
overlay compares an experimental bound/search with exhaustive production-formula
scoring. Fixture pool selection is deliberately small, NOT a product shortlist.
Replace this experiment only after its finite acceptance gate in the archetype
audit. All generated graphs/build caches are owned by managed_optimizer_experiment;
only one compact, versioned receipt survives, never a sequence of raw captures.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs, _bound_artifact_registry_source
from run_workspace.gcsim.optimizer_rotation_policy import normalize_optimizer_rotation_shell
from run_workspace.gcsim.selected_team_config import VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE
from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
    SLOTS, _build_config, _json, _top_builds, _virtual_selected_team,
)
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request


def stat_vector(artifact):
    result = {}
    for row in [artifact["main_stat"], *artifact["substats"]]:
        result[row["key"]] = result.get(row["key"], 0.0) + float(row["value"])
    return result


def choose_pool(items, preferred=None, limit=4):
    """Diagnostic diversity only: full vectors survive, including an exact witness."""
    if not items:
        raise ValueError("Empty diagnostic slot")
    ordered = sorted(items, key=lambda item: item["artifact_id"])
    result = []
    if preferred is not None:
        result.append(next(a for a in ordered if a["artifact_id"] == preferred))
    for key in ("crit_rate", "crit_damage", "atk_percent", "em"):
        best = max(ordered, key=lambda a: stat_vector(a).get(key, 0))
        if best not in result:
            result.append(best)
    for item in ordered:
        if item not in result:
            result.append(item)
    return result[:limit]


def run_go(scratch, *, synthetic_only=False):
    overlay = scratch / "overlay.json"
    here = Path(__file__).resolve().parent
    overlay.write_text(json.dumps({"Replace": {
        str(ROOT / "native/gcsim_optimizer/internal/evaluator/inventory_bound_poc_test.go"): str(here / "bounds_test.go"),
    }}), encoding="utf-8")
    env = dict(os.environ, GTT_BOUND_INPUT=str(scratch / "input.json"),
               GTT_BOUND_OUTPUT=str(scratch / "result.json"))
    test = "TestInventoryBoundSyntheticSafety" if synthetic_only else "TestInventoryBoundConcept"
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                    "./internal/evaluator", "-run", test, "-count=1", "-v", "-timeout", "360s"],
                   cwd=ROOT / "native/gcsim_optimizer", env=env, check=True)


def write_compact_receipt(path, output):
    payload = (json.dumps(output, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    if len(payload) > 64 * 1024:
        raise ValueError("Compact POC receipt exceeded its 64 KiB retention limit")
    with path.open("xb") as stream:
        stream.write(payload)


def main():
    # Refuse unmanaged invocation rather than leave an accidental Go cache behind.
    scratch = Path(os.environ["GTT_SCRATCH_DIR"]).resolve(strict=True)
    if Path(os.environ["GOCACHE"]).resolve().parent != scratch:
        raise ValueError("Run with tools/managed_optimizer_experiment.py")
    if sys.argv[1:] == ["--synthetic-only"]:
        run_go(scratch, synthetic_only=True)
        return
    if sys.argv[1:]:
        raise ValueError("Only --synthetic-only is supported")
    receipt = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json"
    if receipt.exists():
        raise FileExistsError(receipt)
    started = time.perf_counter()
    manifest = _json("tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json")
    team = manifest["teams"]["lunar_charged"]
    db_path = ROOT / manifest["db_path"]
    prepared_dir = scratch / "prepared"
    prepared_dir.mkdir()
    prepared = _prepare_inputs(
        _request(dict(team, mode="all_sets"), db_path=db_path, run_root=scratch),
        prepared_dir,
        virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    )
    request = prepared["request"]
    engine = request["engine"]
    source_receipt = _json("tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_all_sets_lineage5_exact_recheck_v1.json")
    if engine["artifact_sha256"] != source_receipt["runs"][0]["engine_identity"]["artifact_sha256"]:
        raise ValueError("Active engine changed: rebaseline this dated experiment explicitly")
    engine_root = Path(engine["binary_path"]).parent.parent
    sources = prepare_all_set_effect_sources(engine_root, engine)
    witness = _top_builds(source_receipt)
    reserved = {a for w, slots in witness.items() if w != "flins" for a in slots.values()}
    available = [a for a in request["artifacts"] if a["artifact_id"] not in reserved]
    by_id = {a["artifact_id"]: a for a in available}
    rotation = normalize_optimizer_rotation_shell((ROOT / team["rotation_file"]).read_text(encoding="utf-8"))
    rotation_path = scratch / "rotation.txt"
    rotation_path.write_text(rotation.optimizer_text, encoding="utf-8")
    cases = []
    # Set labels are derived from the two dated physical witnesses, not gameplay rules.
    old_virtual = _top_builds(_json("tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_lunar_charged_lineage5_recheck_v1.json"))
    families = [
        ("witness_4p", by_id[witness["flins"]["flower"]]["set_uid"], witness["flins"]),
        ("inactive_4p", by_id[old_virtual["ineffa"]["flower"]]["set_uid"], old_virtual["ineffa"]),
        ("zero_bonus", None, None),
    ]
    for name, family, preferred in families:
        pools = []
        used_families = set()
        for slot in SLOTS:
            items = [a for a in available if a["slot"] == slot]
            if family is None:
                counts = {}
                for a in items:
                    counts[a["set_uid"]] = counts.get(a["set_uid"], 0) + 1
                chosen = sorted((s for s in counts if s not in used_families), key=lambda s: (-counts[s], s))[0]
                used_families.add(chosen)
                items = [a for a in items if a["set_uid"] == chosen]
            elif by_id[preferred[slot]]["set_uid"] == family:
                items = [a for a in items if a["set_uid"] == family]
            pools.append(choose_pool(items, preferred[slot] if preferred else None))
        ids = {w: dict(slots) for w, slots in witness.items()}
        ids["flins"] = {s: pool[0]["artifact_id"] for s, pool in zip(SLOTS, pools)}
        flat_ids = [a for slots in ids.values() for a in slots.values()]
        assert len(flat_ids) == len(set(flat_ids)) == 20
        config = _build_config(
            db_path=db_path, profiles=team["virtual_profiles"],
            selected_team=_virtual_selected_team(team["virtual_profiles"]),
            rotation_path=rotation_path, registry_path=_bound_artifact_registry_source(engine_root),
            ids_by_wearer=ids, case_root=scratch / name, iterations=500,
        )
        cases.append({"name": name, "set_uid": family, "config": config,
                      "reference_ids": ids, "actor": "flins",
                      "pools": [[{"id": a["artifact_id"], "set_uid": a["set_uid"],
                                  "slot": a["slot"], "stats": stat_vector(a)} for a in pool] for pool in pools]})
    input_payload = {"engine": engine, "catalog_sha256": sources["catalog_sha256"],
                     "seeds": request["stochastic"]["seeds"], "cases": cases}
    input_path = scratch / "input.json"
    input_path.write_text(json.dumps(input_payload), encoding="utf-8")
    output_path = scratch / "result.json"
    run_go(scratch)
    output = json.loads(output_path.read_text(encoding="utf-8"))
    # Minimal reproducible inputs, not the account request or unbounded captured graphs.
    output.update({"schema_version": 1, "engine": engine, "seeds": input_payload["seeds"],
                   "catalog_sha256": sources["catalog_sha256"], "inputs": cases,
                   "total_before_cleanup_seconds": time.perf_counter() - started,
                   "scope": "research_only_three_one_actor_domains_fixed_other_fifteen_ids_not_UI_or_full_inventory_acceptance"})
    write_compact_receipt(receipt, output)
    print(f"Compact evidence: {receipt.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
