"""Temporary paired preparation control; owner: Go optimizer design.

Disable ONLY the two exact-reuse optimizations in a managed Go overlay, never
edit installed/workspace source. Reuse the same captured graphs and inventory
for both modes. Remove this helper after the single-team production acceptance.
All generated copies/results die with the existing managed job; no new root.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]


def without_reuse(model: str, candidates: str) -> tuple[str, str]:
    line = "\tmodel.specializations = formula.NewSpecializationCache(neutralProgramEntries, neutralProgramNodes)"
    if model.count(line) != 1:
        raise ValueError("Specialization control target changed")
    begin = "\tplan, err := r.engine.domain.PreparePackageLinear("
    end = "\tids, ok, err := linear()"
    if candidates.count(begin) != 1 or candidates.count(end) != 1:
        raise ValueError("Linear-plan control target changed")
    start, stop = candidates.index(begin), candidates.index(end)
    if stop <= start:
        raise ValueError("Invalid linear-plan control span")
    replacement = "\tlinear := func(excluded ...int64) ([5]int64, bool, error) { return r.linear(w, excluded...) }\n"
    return model.replace(line, "\t// Paired control: no specialization reuse."), candidates[:start] + replacement + candidates[stop:]


def without_constant_binding(cache: str, expression: str) -> tuple[str, str]:
    key = "\tkey, constant := projectedConstantEffectKey(m.effectKeys, m.constantKeys, effects)"
    fast = "\tif bound, constant, err := p.bindConstantEffects(effects); constant {\n\t\treturn bound, err\n\t}\n"
    if cache.count(key) != 1 or expression.count(fast) != 1:
        raise ValueError("Constant binding control target changed")
    return cache.replace(key, "\tkey, constant := constantEffectKey(m.effectKeys, effects)"), expression.replace(fast, "")


def semantic_profile(row: dict, *, effect_cache: bool = False) -> dict:
    row = json.loads(json.dumps(row))
    for key in ("Seconds", "ProposalSeconds", "SeedSeconds", "PotentialSeconds", "JointSeconds", "SlowFrontiers"):
        row.pop(key)
    for key in ("RuleSeconds", "BindSeconds", "ViewSeconds", "Specialization"):
        row["Model"].pop(key)
    if effect_cache:
        for key in ("ProgramHits", "ProgramMisses"):
            row["Model"].pop(key)
    return row


def run_comparison(job: Path, extra: dict[str, str], *, mode: str = "preparation") -> None:
    if job != Path(os.environ.get("GTT_SCRATCH_DIR", "")).resolve() or job.parent != (ROOT / ".codex_tmp/managed-optimizer").resolve() or not job.name.startswith("job-"):
        raise ValueError("Paired preparation requires an owned managed job")
    if extra.get("GTT_NEUTRAL_FINISH_PASSES") != "1":
        raise ValueError("Paired preparation requires completed passes")
    native = ROOT / "native/gcsim_optimizer"
    if mode == "preparation":
        paths = [native / "internal/setcontext/neutral.go", native / "internal/search/candidates.go"]
        transform = without_reuse
    elif mode == "effects":
        paths = [native / "internal/setcontext/neutral_program_cache.go", native / "internal/formula/effect_expression.go"]
        transform = without_constant_binding
    else:
        raise ValueError("Unknown paired control mode")
    originals = [p.read_bytes() for p in paths]
    texts = transform(*(b.decode("utf-8").replace("\r\n", "\n") for b in originals))
    overlay = {"Replace": {}}
    for index, (path, text) in enumerate(zip(paths, texts, strict=True)):
        destination = job / f"preparation-control-{index}.go"
        destination.write_text(text, encoding="utf-8")
        overlay["Replace"][str(path)] = str(destination)
    overlay_path = job / "preparation-control-overlay.json"
    overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
    environment = dict(os.environ, GTT_RULE_SOURCE_BUNDLE=str(job / "rule-sources.json"), **extra)
    go = shutil.which("go")
    if not go:
        raise RuntimeError("Configured Go toolchain is unavailable")
    compared = []
    try:
        # The refactored family matcher is also used by existing inventory
        # callers. Run their complete cheap arithmetic/legality suites before
        # the paired measurements, serially in this same owned compiler cache.
        subprocess.run([go, "test", "./internal/domain", "./internal/formula", "./internal/search", "-count=1", "-timeout=90s"],
                       cwd=native, env=environment, check=True, timeout=110)
        prefix = "reuse" if mode == "preparation" else "effects"
        for name, flags in ((prefix + "_off", ["-overlay", str(overlay_path)]), (prefix + "_on", [])):
            print(f"Paired preparation {name}: same capture, seed, inventory and completed-pass limits.", flush=True)
            result = subprocess.run([go, "test", *flags, "./internal/allsets", "-run", "^TestNeutralCoordinatorSavedInventoryProfile$", "-count=1", "-v", "-timeout=600s"],
                                    cwd=native, env=environment, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=620)
            if result.returncode:
                print(result.stdout[-24000:], result.stderr[-8000:], flush=True)
                raise RuntimeError(f"Paired preparation {name} failed")
            rows = [json.loads(line.split("INVENTORY_PROFILE ", 1)[1]) for line in result.stdout.splitlines() if "INVENTORY_PROFILE " in line]
            if len(rows) != 2 or [r["Restricted"] for r in rows] != [True, False] or any(r["Stop"] != "neutral_cycle_budget" for r in rows):
                raise RuntimeError("Paired preparation did not finish both inventory profiles")
            compared.append(rows)
            for row in rows:
                print("PREPARATION_PROFILE " + json.dumps({"Mode": name, **row}), flush=True)
        if [semantic_profile(row, effect_cache=mode == "effects") for row in compared[0]] != [semantic_profile(row, effect_cache=mode == "effects") for row in compared[1]]:
            raise RuntimeError("Preparation reuse changed search coverage, recorded work or finalists")
        print("Paired preparation PASS: identical work hashes, coverage, finalists, DPS and physical IDs; zero additional captures/ordinary simulations.", flush=True)
    finally:
        for path, content in zip(paths, originals, strict=True):
            if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
                raise RuntimeError(f"Workspace source changed during comparison: {path}")
