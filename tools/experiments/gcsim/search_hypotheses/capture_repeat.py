"""Bounded same-input capture identity diagnostic; managed scratch only.

Two two-seed captures, no search/install. Keep one <=128KiB diagnostic receipt
through the paired matrix gate. Expanded graph data is removed by the runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
from tools.experiments.gcsim.parametric_effects.capture_equivalence import canonical_capture, encoded
from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
from run_workspace.gcsim.optimizer_go_selected import _write_canonical


def differences(a, b, path="$", output=None):
    output = [] if output is None else output
    if len(output) >= 24 or a == b:
        return output
    if type(a) is not type(b):
        output.append({"path": path, "types": [type(a).__name__, type(b).__name__]})
    elif isinstance(a, dict):
        if a.keys() != b.keys():
            output.append({"path": path, "keys_only_a": sorted(a.keys()-b.keys()), "keys_only_b": sorted(b.keys()-a.keys())})
        for key in sorted(a.keys() & b.keys()):
            differences(a[key], b[key], path+"."+key, output)
    elif isinstance(a, list):
        if len(a) != len(b):
            output.append({"path": path, "lengths": [len(a), len(b)]})
        for i, (x, y) in enumerate(zip(a, b)):
            differences(x, y, path+f"[{i}]", output)
            if len(output) >= 24: break
    else:
        output.append({"path": path, "a": str(a)[:240], "b": str(b)[:240]})
    return output


def canonical_field_equality(a, b):
    """Top-level canonical fields, excluding the sidecar's member-byte binding."""
    return {part: {key: a[part].get(key) == b[part].get(key)
                   for key in sorted((a[part].keys() | b[part].keys()) -
                                     ({"member_content_sha256"} if part == "effects" else set()))}
            for part in ("member", "effects")}


def capture_guards(effects):
    neutral = effects.get("neutral") or {}
    return {"reads_complete": neutral.get("reads_complete") is True,
            "world_complete": (neutral.get("world") or {}).get("complete") is True,
            "ledger_not_truncated": (neutral.get("ledger") or {}).get("truncated") is False}


def diagnostic_path(pair: Path, attempt: int) -> Path:
    if attempt not in (1, 2, 3):
        raise ValueError("Capture diagnostic attempt must be 1..3")
    suffix = "" if attempt == 1 else f"-attempt{attempt}"
    return pair.with_name(pair.stem + "-capture-diagnostic" + suffix + ".json")


def _compact(value):
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:500] + "…[truncated]"
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _annotations(effects):
    neutral = effects.get("neutral") or {}
    result = {}
    for kind, rows in (("effect_inputs", effects.get("effect_inputs", [])),
                       ("resistance_inputs", effects.get("resistance_inputs", [])),
                       ("neutral.stats", neutral.get("stats", [])),
                       ("neutral.reads", neutral.get("reads", []))):
        for row in rows:
            result.setdefault(row["node_id"], []).append({
                "kind": kind, "binding": {key: value for key, value in row.items() if key != "node_id"}})
    return {key: sorted(value, key=encoded) for key, value in result.items()}


def compare_root_dags(a_member, a_effects, b_member, b_effects, a_root, b_root,
                      *, mismatch_limit=16, preview_limit=80):
    """Walk aligned raw DAGs in input order; node IDs only identify local nodes."""
    a_nodes = {node["node_id"]: node for node in a_member["nodes"]}
    b_nodes = {node["node_id"]: node for node in b_member["nodes"]}
    a_annotations, b_annotations = _annotations(a_effects), _annotations(b_effects)
    visited, preview, mismatches = set(), [], []
    stack = [(a_root, b_root, "root")]
    while stack and len(mismatches) < mismatch_limit:
        a_id, b_id, path = stack.pop()
        if (a_id, b_id) in visited:
            continue
        visited.add((a_id, b_id))
        a_node, b_node = a_nodes.get(a_id), b_nodes.get(b_id)
        if len(preview) < preview_limit:
            preview.append({"path": _compact(path), "depth": path.count(".input["),
                            "a_id": a_id, "b_id": b_id})
        a_meta = ({key: value for key, value in a_node.items() if key not in ("node_id", "inputs")}
                  if a_node is not None else None)
        b_meta = ({key: value for key, value in b_node.items() if key not in ("node_id", "inputs")}
                  if b_node is not None else None)
        a_anno, b_anno = a_annotations.get(a_id, []), b_annotations.get(b_id, [])

        def record(kind, location, left, right):
            if len(mismatches) < mismatch_limit:
                mismatches.append({"kind": kind, "path": _compact(location),
                                   "depth": location.count(".input["),
                                   "a": _compact(left), "b": _compact(right),
                                   "a_node": _compact(a_meta), "b_node": _compact(b_meta),
                                   "a_annotations": _compact(a_anno),
                                   "b_annotations": _compact(b_anno)})

        if a_node is None or b_node is None:
            record("missing_node", path, a_id if a_node is not None else None,
                   b_id if b_node is not None else None)
            continue
        if a_meta != b_meta:
            record("node_metadata", path, a_meta, b_meta)
        if a_anno != b_anno:
            record("annotations", path, a_anno, b_anno)
        a_inputs, b_inputs = a_node.get("inputs", []), b_node.get("inputs", [])
        if len(a_inputs) != len(b_inputs):
            record("input_count", path, len(a_inputs), len(b_inputs))
        children = []
        for index, (a_edge, b_edge) in enumerate(zip(a_inputs, b_inputs)):
            child_path = path + f".input[{index}]"
            a_edge_meta = {key: value for key, value in a_edge.items() if key != "node_id"}
            b_edge_meta = {key: value for key, value in b_edge.items() if key != "node_id"}
            if a_edge_meta != b_edge_meta:
                record("edge_metadata", child_path, a_edge_meta, b_edge_meta)
            children.append((a_edge["node_id"], b_edge["node_id"], child_path))
        stack.extend(reversed(children))
    return {"raw_roots": [a_root, b_root], "structural_equal": not mismatches and not stack,
            "visited_pairs": len(visited), "first_visited": preview,
            "mismatches": mismatches, "mismatch_limit_reached": bool(stack)}


def channel_root_diagnostics(a_member, a_effects, b_member, b_effects, a_canonical, b_canonical):
    a_raw, b_raw = a_member["channels"], b_member["channels"]
    a_can, b_can = a_canonical["member"]["channels"], b_canonical["member"]["channels"]
    rows = []
    for index in range(min(len(a_raw), len(b_raw))):
        a_root, b_root = a_raw[index]["root_node_id"], b_raw[index]["root_node_id"]
        canonical_changed = a_can[index]["root_node_id"] != b_can[index]["root_node_id"]
        raw_changed = a_root != b_root
        if canonical_changed or raw_changed:
            rows.append({"channel": index, "canonical_root_changed": canonical_changed,
                         "raw_root_ids_changed": raw_changed, "a_root_id": a_root, "b_root_id": b_root})
    selected = sorted(rows, key=lambda row: not row["canonical_root_changed"])[:3]
    for row in selected:
        row["dag"] = compare_root_dags(a_member, a_effects, b_member, b_effects,
                                       row["a_root_id"], row["b_root_id"])
    missing = abs(len(a_raw) - len(b_raw))
    return {"channel_counts": [len(a_raw), len(b_raw)],
            "canonical_root_differences": missing + sum(r["canonical_root_changed"] for r in rows),
            "raw_root_id_differences": missing + sum(r["raw_root_ids_changed"] for r in rows),
            "first_differing_roots": selected}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--attempt", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    job = owned_job()
    pair = json.loads(args.pair.read_text(encoding="utf-8"))
    out = diagnostic_path(args.pair, args.attempt)
    if out.exists(): raise ValueError("Diagnostic evidence already exists")
    req = pair["request"]
    engine = Path(req["engine"]["binary_path"])
    installed = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(installed) != pair["installed_sha256"] or digest(engine) != pair["engine_sha256"]:
        raise ValueError("Engine or installed optimizer changed")
    _write_canonical(job / "request.json", req)
    sources = prepare_all_set_effect_sources(engine.parent.parent, req["engine"], include_neutral_rules=True)
    _write_canonical(job / "set-sources.json", sources)
    if digest(job / "request.json") != pair["request_sha256"] or digest(job / "set-sources.json") != pair["sources_sha256"]:
        raise ValueError("Retained request/source reconstruction differs")
    native = job / "native"
    source = ROOT / "native/gcsim_optimizer"
    for original in source.rglob("*"):
        if original.is_file() and (original.suffix == ".go" or original.name in {"go.mod", "go.sum"}):
            target = native / original.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    shutil.copy2(Path(__file__).with_name("capture_repeat_test.go"), native / "cmd/gtt-optimizer/hypothesis_capture_repeat_test.go")
    contexts = {key.split("/")[0].removeprefix("context-") for key in pair["runs"][0]["captures"]}
    if len(contexts) != 1: raise ValueError("Diagnostic expects one neutral context")
    env = dict(os.environ, GTT_CAPTURE_REPEAT=str(job), GTT_CAPTURE_CONTEXT=next(iter(contexts)),
               GTT_RULE_CACHE_DIR=str(job / "rule-cache"), GTT_RULE_BUNDLED_CACHE_DIR="")
    go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
    subprocess.run([go,"test","./cmd/gtt-optimizer","-run=^TestHypothesisCaptureRepeat$","-count=1","-v","-timeout=180s"], cwd=native, env=env, check=True)
    result = {"scope": "two repeated active-engine captures of the retained canonical request, no search", "seeds": []}
    for first in sorted((job / "first").glob("context-*/seed-*/member.json")):
        second = job / "second" / first.relative_to(job / "first")
        a, b = first.read_bytes(), second.read_bytes()
        ae, be = first.with_name("member.json.effects.json").read_bytes(), second.with_name("member.json.effects.json").read_bytes()
        a_member, b_member = json.loads(a), json.loads(b)
        a_effects, b_effects = json.loads(ae), json.loads(be)
        ca, cb = canonical_capture(a, ae), canonical_capture(b, be)
        folded = {}
        diagnostic_a, diagnostic_b = ca, cb
        if args.attempt == 3:
            diagnostic_a = canonical_capture(a, ae, independent_status_adds=True, fold_unbound_constants=True)
            diagnostic_b = canonical_capture(b, be, independent_status_adds=True, fold_unbound_constants=True)
            folded = {"equal": diagnostic_a == diagnostic_b,
                      "first": hashlib.sha256(encoded(diagnostic_a)).hexdigest(),
                      "second": hashlib.sha256(encoded(diagnostic_b)).hexdigest(),
                      "top_level_equal": canonical_field_equality(diagnostic_a, diagnostic_b),
                      "differences": differences(diagnostic_a, diagnostic_b)}
        result["seeds"].append({"seed": first.parent.name, "raw_equal": a == b and ae == be,
            "raw_first": digest(first), "raw_second": digest(second),
            "canonical_equal": ca == cb,
            "canonical_first": hashlib.sha256(encoded(ca)).hexdigest(),
            "canonical_second": hashlib.sha256(encoded(cb)).hexdigest(),
            "guards": {"a": capture_guards(a_effects), "b": capture_guards(b_effects)},
            "canonical_top_level_equal": canonical_field_equality(ca, cb),
            "channels": channel_root_diagnostics(a_member, a_effects, b_member, b_effects, diagnostic_a, diagnostic_b),
            "channel_comparison_basis": "constant_fold" if args.attempt == 3 else "strict",
            "constant_fold": folded,
            "canonical_differences": differences(ca, cb),
            "raw_differences": differences({"member":a_member,"effects":a_effects}, {"member":b_member,"effects":b_effects})})
    result["installed_unchanged"] = digest(installed) == pair["installed_sha256"]
    result["engine_unchanged"] = digest(engine) == pair["engine_sha256"]
    data = encoded(result)
    if len(data) > 128*1024: raise ValueError("Diagnostic receipt cap")
    with out.open("xb") as stream:
        stream.write(data)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
