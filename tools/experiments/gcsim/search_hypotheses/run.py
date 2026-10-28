"""Isolated source-overlay hypotheses; never install or capture from GCSIM.

Owner: Go optimizer design, isolated Chasca speed gate (2026-09-27).
Delete expanded output with managed_optimizer_experiment.py; retain compact
receipts through integration acceptance, then retire this research harness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(root, relative, before, after):
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if text.count(before) != 1:
        raise ValueError(f"Overlay drift: {relative}: expected exactly one match")
    path.write_text(text.replace(before, after), encoding="utf-8")


def apply_timing_overlay(root):
    """Shared neutral timing fields, independent of the capture provider."""
    # Split the existing total binding measurement; do not change arithmetic or
    # include build time in claims about search/preparation speed.
    replace_once(root, "internal/setcontext/neutral_program_cache.go", '"sort"', '"sort"\n\t"time"')
    replace_once(root, "internal/setcontext/neutral.go", "RuleSeconds, BindSeconds, ViewSeconds         float64", "RuleSeconds, BindSeconds, ViewSeconds         float64\n\tConstantBindSeconds, SymbolicBindSeconds float64")
    for method, field, parameter in [("bindConstants", "ConstantBindSeconds", "values []float64"),
                                     ("bindProgram", "SymbolicBindSeconds", "effects map[string]*formula.InputExpression")]:
        header = f"func (m *NeutralModel) {method}({parameter}) (*formula.ParametricProgram, error) {{"
        replace_once(root, "internal/setcontext/neutral_program_cache.go", header,
                     header + f"\n\tstarted := time.Now()\n\tdefer func() {{ m.stats.{field} += time.Since(started).Seconds() }}()")


def overlay(root, variant):
    replace_once(root, "cmd/gtt-optimizer/all_sets.go",
                 "setcontext.NewEffectEngineProvider(binding, captureRoot)",
                 "newHypothesisProvider(binding, captureRoot)")
    apply_timing_overlay(root)
    if variant == "baseline":
        return
    from variants import apply_variant
    apply_variant(root, variant, replace_once)


def copy_variant_support(native, variant, job):
    """Copy every Go control/helper required by the variant's overlay chain."""
    from tools.experiments.gcsim.search_hypotheses.player_search import PLAYER_VARIANTS

    here = Path(__file__).parent
    player = variant in PLAYER_VARIANTS
    mixed = variant in {"mixed_sparse", "effect_families", "amount_plan"} or player
    shutil.copy2(here / "replay_test.go", native / "cmd/gtt-optimizer/hypothesis_replay_test.go")
    if variant in {"lazy_constants", "linear_freeze", "grouped_constants"}:
        shutil.copy2(here / "lazy_test.go", native / "internal/formula/hypothesis_lazy_test.go")
    if variant == "linear_freeze":
        shutil.copy2(here / "linear_freeze.go", native / "internal/formula/hypothesis_linear_freeze.go")
    if variant == "grouped_constants":
        shutil.copy2(here / "grouped_constants.go", native / "internal/formula/hypothesis_grouped_constants.go")
    if variant in {"region_binding", "region_dense", "combined_preparation"} or mixed:
        for name in ("region_binding.go", "region_binding_test.go"):
            shutil.copy2(here / name, native / "internal/formula" / ("hypothesis_" + name))
        if variant in {"region_dense", "combined_preparation"} or mixed:
            from tools.experiments.gcsim.search_hypotheses.region_dense import apply_dense
            apply_dense(native, replace_once)
    if mixed:
        for name, package in (("mixed_formula.go", "formula"), ("mixed_formula_test.go", "formula"), ("mixed_cache.go", "setcontext")):
            shutil.copy2(here / name, native / "internal" / package / ("hypothesis_" + name))
    if variant in {"effect_families", "amount_plan"} or player:
        for name in ("effect_families.go", "effect_families_test.go"):
            shutil.copy2(here / name, native / "internal/seteffects" / ("hypothesis_" + name))
    if variant == "amount_plan" or player:
        for name in ("amount_plan.go", "amount_plan_test.go"):
            shutil.copy2(here / name, native / "internal/seteffects" / ("hypothesis_" + name))
    if variant in {"inventory_views", "prepared_replay", "combined_preparation"} or mixed:
        fixture_dir = job / "tests/fixtures/gcsim_optimizer_go_v1"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        for name in ("request_v1.json", "compact_ir_v1.json"):
            shutil.copy2(ROOT / "tests/fixtures/gcsim_optimizer_go_v1" / name, fixture_dir / name)
    if player:
        for name in ("player_filter.go", "player_logic_test.go"):
            shutil.copy2(here / name, native / "internal/search" / ("hypothesis_" + name))
    literal = variant == "player_literal"
    if variant.startswith("player_packages") or literal:
        for name in ("bonus_approx.go", "bonus_approx_test.go"):
            shutil.copy2(here / name, native / "internal/seteffects" / ("hypothesis_" + name))
    if variant.startswith("player_packages"):
        shutil.copy2(here / "player_packages.go", native / "internal/allsets/hypothesis_player_packages.go")
    if literal:
        for name in ("literal_fast.go", "literal_fast_test.go"):
            shutil.copy2(here / name, native / "internal/seteffects" / ("hypothesis_" + name))
    if variant.startswith("player_point"):
        for name in ("point_screen.go", "point_screen_test.go"):
            shutil.copy2(here / name, native / "internal/setcontext" / ("hypothesis_" + name))
        shutil.copy2(here / "point_packages.go", native / "internal/allsets/hypothesis_point_packages.go")
        if variant.endswith("_adaptive"):
            replace_once(native, "internal/allsets/hypothesis_point_packages.go", "const hypothesisAdaptivePoint = false", "const hypothesisAdaptivePoint = true")
    approximate = variant in {"player_mean", "player_peak"}
    if approximate:
        for name in ("player_uptime.go", "player_uptime_test.go"):
            shutil.copy2(here / name, native / "internal/seteffects" / ("hypothesis_" + name))
    if approximate or variant.startswith("player_point"):
        shutil.copy2(here / "exact_rescore_test.go", native / "cmd/gtt-optimizer/hypothesis_exact_rescore_test.go")
    if variant in {"inventory_views", "combined_preparation"} or mixed:
        shutil.copy2(here / "vector_views_test.go", native / "internal/domain/hypothesis_vector_views_test.go")
    if variant in {"prepared_replay", "combined_preparation"} or mixed:
        shutil.copy2(here / "replay_plan_test.go", native / "internal/seteffects/hypothesis_replay_plan_test.go")


def fingerprint(rows):
    return [{"group": x["set_group_key"], "rank": x["alternative_rank"],
             "dps": float(x["formula_dps"]),
             "ids": sorted((a["wearer_key"], a["slot"], a["artifact_id"]) for a in x["artifacts"])} for x in rows]


def check(rows, req):
    # The native product path validates assignments; additionally check exported
    # inventory membership, global uniqueness, and single-substitution output.
    groups, identities = {}, set()
    items = {a["artifact_id"]: a for a in req["artifacts"]}
    slots = {"flower", "plume", "sands", "goblet", "circlet"}
    wearers = {w["wearer_key"] for w in req["wearers"]}
    signatures = {}
    for row in rows:
        assignment = tuple(sorted((a["wearer_key"], a["slot"], a["artifact_id"]) for a in row["artifacts"]))
        assert len(assignment) == 20 and len({x[2] for x in assignment}) == 20
        assert assignment not in identities
        assert {(x[0], x[1]) for x in assignment} == {(w, s) for w in wearers for s in slots}
        assert all(x[2] in items and items[x[2]]["slot"] == x[1] for x in assignment)
        signature = []
        for wearer in sorted(wearers):
            counts = Counter(items[x[2]]["set_uid"] for x in assignment if x[0] == wearer)
            signature.append((wearer, tuple(sorted((s, 4 if n >= 4 else 2) for s, n in counts.items() if n >= 2))))
        signature = tuple(signature)
        group = row["set_group_key"]
        assert signatures.setdefault(group, signature) == signature
        assert len(set(signatures.values())) == len(signatures)
        identities.add(assignment)
        groups.setdefault(row["set_group_key"], []).append(dict(((x[0], x[1]), x[2]) for x in assignment))
    for alternatives in groups.values():
        for alt in alternatives[1:]:
            assert sum(alt[k] != alternatives[0][k] for k in alt) == 1


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--saved-run", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", default=["baseline"])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError("Refusing to overwrite retained hypothesis evidence")
    job = owned_job()
    saved = args.saved_run.resolve(strict=True)
    saved.relative_to((ROOT / "data/gcsim/optimizer-go-runs").resolve())
    req = json.loads((saved / "request.json").read_text(encoding="utf-8"))
    engine = Path(req["engine"]["binary_path"]).resolve(strict=True)
    assert sha(engine) == req["engine"]["artifact_sha256"]
    active = json.loads((ROOT / "data/gcsim/engines/active_engine.json").read_text(encoding="utf-8"))
    assert active["active_engine_id"] in engine.parts, "Saved capture is not from the active engine"
    installed = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"
    installed_sha = sha(installed)
    golden = json.loads((saved / "optimizer-output.json").read_text(encoding="utf-8"))
    expected = fingerprint(golden["product_result"]["candidates"])
    source = ROOT / "native/gcsim_optimizer"
    files = sorted(p for p in source.rglob("*") if p.is_file() and (p.suffix == ".go" or p.name in {"go.mod", "go.sum"}))
    source_sha = hashlib.sha256(b"".join(str(p.relative_to(source)).encode() + b"\0" + p.read_bytes() for p in files)).hexdigest()
    receipt = {"schema_version": 1, "scope": ("source-copy controls with active-source envelope; no search, simulation or install" if args.controls_only else "saved-capture CLI-route replay; no new simulation, no install"), "saved_run": saved.name,
               "request_sha256": sha(saved / "request.json"), "source_sha256": source_sha,
               "installed_sha256": installed_sha, "engine_sha256": sha(engine), "variants": []}
    def failed(variant, stage, log):
        receipt["failure"] = {"variant": variant, "stage": stage, "log_tail": log[-12000:]}
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"{stage} failed: {variant}")
    go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
    paired_reference = None
    paired_name = None
    for variant in args.variants:
        from player_search import PLAYER_VARIANTS
        player = variant in PLAYER_VARIANTS
        mixed = variant in {"mixed_sparse", "effect_families", "amount_plan"} or player
        work = job / variant
        native = work / "native"
        for original in files:
            target = native / original.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        overlay(native, variant)
        copy_variant_support(native, variant, job)
        literal = variant == "player_literal"
        approximate = variant in {"player_mean", "player_peak"}
        exact_check = approximate or variant.startswith("player_point")
        env = dict(os.environ, GTT_HYPOTHESIS_SAVED=str(saved), GTT_HYPOTHESIS_WORK=str(work / "result"),
                   GTT_RULE_CACHE_DIR=str(work / "rule-cache"), GTT_RULE_BUNDLED_CACHE_DIR="")
        if args.controls_only or variant.startswith("player_packages") or literal:
            # Existing source-dependent controls opt in explicitly. Do not
            # confuse their skipped default with an active-source test pass.
            env["GTT_RULE_SOURCE_BUNDLE"] = str(saved / "set-sources.json")
        copied_files = sorted(native.rglob("*.go"))
        variant_sha = hashlib.sha256(b"".join(str(p.relative_to(native)).encode() + b"\0" + p.read_bytes() for p in copied_files)).hexdigest()
        started = time.monotonic()
        with (work / "test.log").open("w", encoding="utf-8") as log:
            control = subprocess.run([go, "test", "./internal/formula", "-run=^(TestParametric|TestCompactConstants|TestHypothesis)", "-count=1", "-v", "-timeout=180s"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
            if control.returncode:
                print((work / "test.log").read_text(encoding="utf-8")[-12000:], flush=True)
                failed(variant, "arithmetic_controls", (work / "test.log").read_text(encoding="utf-8"))
            if variant in {"inventory_views", "prepared_replay", "combined_preparation"} or mixed:
                # These hypotheses alter setup ownership, not item scoring.
                # Existing domain/rule tests must pass before the full replay.
                control = subprocess.run([go, "test", "./internal/domain", "./internal/seteffects", "-count=1", "-v", "-timeout=180s"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
                if control.returncode:
                    print((work / "test.log").read_text(encoding="utf-8")[-12000:], flush=True)
                    failed(variant, "preparation_controls", (work / "test.log").read_text(encoding="utf-8"))
            if player:
                control = subprocess.run([go, "test", "./internal/search", "-run=^(TestHypothesis.*|TestCandidatesTinyOracleBudgetAndCancel|TestCandidatesPairedMoveEscapesWorseSingles)$", "-count=1", "-v", "-timeout=180s"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
                if control.returncode:
                    failed(variant, "player_search_controls", (work / "test.log").read_text(encoding="utf-8"))
            if variant.startswith("player_point"):
                control = subprocess.run([go, "test", "./internal/setcontext", "-run=^TestHypothesis", "-count=1", "-v", "-timeout=180s"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
                if control.returncode:
                    failed(variant, "point_controls", (work / "test.log").read_text(encoding="utf-8"))
            if args.controls_only:
                lines = (work / "test.log").read_text(encoding="utf-8").splitlines()
                result = {"variant": variant, "variant_source_sha256": variant_sha,
                          "controls_only": True, "seconds": time.monotonic() - started,
                          "active_source_bundle_sha256": sha(saved / "set-sources.json"),
                          "passed_tests": [x.split(": ", 1)[1].split(" ", 1)[0] for x in lines if x.startswith("--- PASS: ")],
                          "skipped_tests": [x.split(": ", 1)[1].split(" ", 1)[0] for x in lines if x.startswith("--- SKIP: ")]}
                receipt["variants"].append(result)
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
                print("HYPOTHESIS_CONTROLS " + json.dumps(result), flush=True)
                assert sha(installed) == installed_sha and sha(engine) == req["engine"]["artifact_sha256"]
                continue
            if approximate:
                env["GTT_HYPOTHESIS_UPTIME"] = variant.removeprefix("player_")
            proc = subprocess.run([go, "test", "./cmd/gtt-optimizer", "-run=^TestHypothesisReplay$", "-count=1", "-v", "-timeout=15m"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
            if exact_check and proc.returncode == 0:
                env.pop("GTT_HYPOTHESIS_UPTIME", None)
                oracle = subprocess.run([go, "test", "./cmd/gtt-optimizer", "-run=^TestHypothesisExactRescore$", "-count=1", "-v", "-timeout=180s"], cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT)
                if oracle.returncode:
                    failed(variant, "exact_rescore", (work / "test.log").read_text(encoding="utf-8"))
        if proc.returncode:
            print((work / "test.log").read_text(encoding="utf-8")[-12000:], flush=True)
            failed(variant, "replay", (work / "test.log").read_text(encoding="utf-8"))
        output = json.loads((work / "result/all-sets-result.json").read_text(encoding="utf-8"))
        rows = output["product_result"]["candidates"]
        check(rows, req)
        actual = fingerprint(rows)
        leaders = {x["group"]: x["dps"] for x in actual if x["rank"] == 1}
        deltas = [{"group": x["group"], "baseline_dps": x["dps"], "candidate_dps": leaders.get(x["group"]),
                   "delta": leaders.get(x["group"], float("-inf")) - x["dps"]} for x in expected if x["rank"] == 1]
        result = {"variant": variant, "build_and_replay_seconds": time.monotonic() - started,
                  "variant_source_sha256": variant_sha,
                  "exact_rows": actual == expected, "rows": len(rows), "groups": len(leaders), "group_deltas": deltas,
                  "result_fingerprint": hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(),
                  "leaders": [x for x in actual if x["rank"] == 1]}
        if paired_reference is None:
            paired_reference, paired_name = actual, variant
        result["paired_reference_variant"] = paired_name
        result["paired_exact_rows"] = actual == paired_reference
        if exact_check:
            result["exact_rescore"] = json.loads((work / "exact-rescore.json").read_text(encoding="utf-8"))
        diagnostic_lines = (work / "test.log").read_text(encoding="utf-8").splitlines()
        diagnostic_lines += (work / "product-stdout.json").read_text(encoding="utf-8").splitlines()
        result["hypothesis_diagnostics"] = [line for line in diagnostic_lines if "HYPOTHESIS_PACKAGE_SHORTLIST" in line or "HYPOTHESIS_UPTIME" in line or "HYPOTHESIS_POINT_" in line or "literal2p" in line.lower() or "literal two-piece coverage" in line]
        # Compact proof of which newly added controls actually landed before
        # copying. Historical exact_rows still means installed saved output.
        result["passed_hypothesis_controls"] = [line.split(": ", 1)[1].split(" ", 1)[0]
            for line in (work / "test.log").read_text(encoding="utf-8").splitlines()
            if line.startswith("--- PASS: TestHypothesis")]
        memory_path = work / "memory.json"
        if memory_path.exists():
            result["memory"] = json.loads(memory_path.read_text(encoding="utf-8"))
        expected_leaders = sorted((x["dps"] for x in expected if x["rank"] == 1), reverse=True)
        actual_leaders = sorted(leaders.values(), reverse=True)
        result["rank_deltas"] = [a - b for a, b in zip(actual_leaders, expected_leaders)]
        result["alternative_scores"] = {g: [x["dps"] for x in actual if x["group"] == g] for g in leaders}
        result["alternative_deltas"] = {g: [a - b for a, b in zip(
            sorted((x["dps"] for x in actual if x["group"] == g), reverse=True),
            sorted((x["dps"] for x in expected if x["group"] == g), reverse=True))] for g in leaders}
        for key in ["search_seconds", "proposal_seconds", "search_expansions", "search_stop_reason", "total_elapsed_ms", "neutral_model", "neutral_cycles", "neutral_joint_seconds", "neutral_package_joint", "neutral_stabilization"]:
            result[key] = output.get(key)
        result["work_by_lane"] = {}
        for row in output.get("search_work", []):
            lane = row.get("Lane", row.get("lane", row.get("stage", "unknown")))
            summary = result["work_by_lane"].setdefault(lane, {"count": 0, "seconds": 0, "expanded": 0})
            summary["count"] += 1
            summary["seconds"] += row.get("SearchSeconds", 0)
            summary["expanded"] += row.get("Expansions", 0)
        receipt["variants"].append(result)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print("HYPOTHESIS_RESULT " + json.dumps({k: v for k, v in result.items() if k not in {"work_by_lane", "neutral_cycles", "leaders", "neutral_package_joint", "neutral_stabilization"}}), flush=True)
        assert sha(installed) == installed_sha and sha(engine) == req["engine"]["artifact_sha256"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
