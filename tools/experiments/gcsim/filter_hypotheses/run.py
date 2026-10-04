"""Isolated fixed-context filter pilots; never installs or modifies settings.

Run under managed_optimizer_experiment.py. One active-engine neutral capture
supplies actual Chasca formulas. Tiny and full two-slot domains are exhaustive
oracles, not an end-to-end/global-optimum gate. Only a compact receipt survives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

# This research runner needs no persistent Python bytecode cache. Go/capture
# outputs are owned by managed scratch; receipts are the only generated evidence.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import assert_unlinked, owned_job
from run_workspace.gcsim.engine_store import GcsimEngineStore

EVIDENCE = ROOT / "docs/optimizer-evidence/2026-10-03-filter-hypotheses"
MAX_RECEIPTS, MAX_RECEIPT_BYTES = 6, 256 * 1024


def receipt_target(raw, *, owner=EVIDENCE):
    """Keep a finite set of immutable, small receipts; never prune failed evidence."""
    candidate = Path(raw).absolute()
    assert_unlinked(candidate)
    receipt = candidate.resolve()
    if receipt.parent != owner.resolve() or receipt.suffix != ".json":
        raise ValueError("Receipt must be a JSON directly in this experiment's evidence folder")
    if receipt.exists():
        raise FileExistsError(receipt)
    existing = list(owner.glob("*.json"))
    for path in existing:
        assert_unlinked(path)
    if len(existing) >= MAX_RECEIPTS or any(path.stat().st_size > MAX_RECEIPT_BYTES for path in existing):
        raise ValueError("Finite receipt budget exhausted; review evidence before another experiment")
    return receipt


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--model-bounds", action="store_true",
                        help="Study fixed arithmetic bounds and early legality, NOT engine-response bounds")
    args = parser.parse_args()
    scratch = owned_job()
    here = Path(__file__).resolve().parent
    native = ROOT / "native/gcsim_optimizer"
    run = Path(args.run).resolve(strict=True)
    if not run.is_relative_to((ROOT / "data/gcsim/optimizer-go-runs").resolve()):
        raise ValueError("Saved input must belong to this checkout's optimizer runs")
    receipt = receipt_target(args.receipt)
    if args.synthetic_only and args.model_bounds:
        raise ValueError("Synthetic-only and actual model-bound scopes are separate")
    request = json.loads((run / "request.json").read_text(encoding="utf-8"))
    active = GcsimEngineStore().get_active_engine()
    binary = Path(request["engine"]["binary_path"]).resolve(strict=True)
    if active is None or binary.parent.parent != active.path.resolve():
        raise ValueError("Saved request does not use the currently active engine")
    expected = request["engine"]["artifact_sha256"]
    if digest(binary) != expected:
        raise ValueError("Saved engine bytes changed")
    protected = {str(p): digest(p) for p in
                 (run / "request.json", run / "set-sources.json", run / "optimizer-output.json",
                  ROOT / "settings.json", native / "gtt-optimizer.exe")}
    replacements = {}
    for source, target in (("box_bounds.go", "internal/formula/filter_hypotheses.go"),
                           ("box_bounds_test.go", "internal/formula/filter_hypotheses_test.go")):
        replacements[str(native / target)] = str(here / source)
    if not args.synthetic_only:
        replacements[str(native / "cmd/gtt-optimizer/filter_hypotheses_test.go")] = str(here / "pilot_test.go")
        replacements[str(native / "internal/seteffects/filter_hypotheses.go")] = str(here / "replay_gate.go")
        patch = json.loads((here / "replay_gate.patch.json").read_text(encoding="utf-8"))
        original = native / "internal/seteffects/rule_replay.go"
        text = original.read_text(encoding="utf-8")
        for edit in patch["replacements"]:
            if text.count(edit["old"]) != 1:
                raise ValueError("Replay overlay no longer matches source")
            text = text.replace(edit["old"], edit["new"], 1)
        changed = scratch / "rule_replay.go"
        changed.write_text(text, encoding="utf-8")  # Generated mechanical overlay.
        replacements[str(original)] = str(changed)
    overlay = scratch / "overlay.json"
    overlay.write_text(json.dumps({"Replace": replacements}), encoding="utf-8")
    env = dict(os.environ, GTT_FILTER_RUN=str(run), GTT_FILTER_OUTPUT=str(scratch / "pilot.json"),
               GTT_FILTER_MODEL_SCOPE="1" if args.model_bounds else "0",
               GTT_RULE_CACHE_DIR=str(scratch / "rule-cache"),
               GTT_RULE_BUNDLED_CACHE_DIR=str(native / "set-rule-cache"))
    packages = ["./internal/formula"] if args.synthetic_only else ["./internal/formula", "./cmd/gtt-optimizer"]
    command = ["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), *packages,
               "-run", "TestHypothesis", "-count=1", "-v", "-timeout", "480s"]
    completed = subprocess.run(command, cwd=native, env=env, check=False)
    after = GcsimEngineStore().get_active_engine()
    unchanged = (after is not None and after.engine_id == active.engine_id and digest(binary) == expected
                 and all(digest(path) == sha for path, sha in protected.items()))
    if not unchanged:
        raise RuntimeError("Protected input/installed state changed during pilot")
    output_path = scratch / "pilot.json"
    output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    output.update(exit_code=completed.returncode, protected_inputs_unchanged=unchanged,
                  engine_id=active.engine_id, engine_sha256=expected,
                  request_sha256=protected[str(run / "request.json")],
                  scope=("synthetic-only" if args.synthetic_only else
                         "compiled arithmetic only, early legality; NOT engine-response bounds or full search" if args.model_bounds else
                         "actual fixed-context two-slot domains; not full search"),
                  prototype_sha256={p.name: digest(p) for p in here.iterdir()
                                    if p.suffix in {".go", ".py", ".json"}})
    payload = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt exceeds 256 KiB")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt = receipt_target(receipt)  # Recheck finite budget after the run.
    with receipt.open("xb") as stream:
        stream.write(payload)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
