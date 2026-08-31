"""GOB-4 real indexed-domain and compiled-evaluator parity audit.

Uses only the ignored request/compact payload produced by GOB-3E. GCSIM is not
started. Python independently reduces the same numeric IR for incumbent, one
broad stat profile, and one legal real replacement per wearer/slot.
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import subprocess

from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from tools.experiments.gcsim_trace_support_objective_v1_audit import ROOT


AUDIT_DIR = ROOT / ".codex_tmp" / "gob3e_real_panel"
REQUEST_PATH = AUDIT_DIR / "request.json"
COMPACT_PATH = AUDIT_DIR / "compact.json"
BINARY_PATH = AUDIT_DIR / "gtt-optimizer-gob4.exe"
RECEIPT_PATH = (
    ROOT / "tests" / "fixtures" / "gcsim_optimizer_go_v1"
    / "gob4_indexed_evaluator_receipt_v1.json"
)
TOLERANCE = 1e-6


def main() -> None:
    completed = subprocess.run(
        (
            str(BINARY_PATH), "audit-indexed-panel", str(REQUEST_PATH),
            str(COMPACT_PATH), "100",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    go = json.loads(completed.stdout)
    request = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    compact = json.loads(COMPACT_PATH.read_text(encoding="utf-8"))
    coordinates = sorted(
        {
            node["coordinate"]
            for member in compact["members"]
            for node in member["nodes"]
            if node["operation"] == "artifact_stat"
        }
    )
    incumbent = [
        [row["artifact_id"] for row in wearer["current_artifacts"]]
        for wearer in request["wearers"]
    ]
    incumbent_delta = _assignment_deltas(request, coordinates, incumbent)
    python_incumbent = _evaluate_panel(compact, coordinates, incumbent_delta)
    broad = [0.01] * len(coordinates)
    python_broad = _evaluate_panel(compact, coordinates, broad)
    swap_rows = []
    for row in go["single_swaps"]:
        python_dps = _evaluate_panel(
            compact,
            coordinates,
            _assignment_deltas(request, coordinates, row["assignment"]),
        )
        swap_rows.append(
            {
                "assignment_sha256": canonical_sha256(row["assignment"]),
                "go_dps": str(row["mean_dps"]),
                "python_dps": str(python_dps),
                "absolute_error": str(abs(row["mean_dps"] - python_dps)),
            }
        )
    checks = {
        "incumbent": abs(go["incumbent_dps"] - python_incumbent) <= TOLERANCE,
        "broad_profile": abs(go["broad_profile_dps"] - python_broad) <= TOLERANCE,
        "all_real_single_swaps": all(
            float(row["absolute_error"]) <= TOLERANCE for row in swap_rows
        ),
        "twenty_slot_controls_present": len(swap_rows) == 20,
        "hot_evaluator_has_search_margin": go["mean_hot_evaluation_ms"] < 2.0,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"GOB-4 parity failed: {failed!r}")
    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_gob4_indexed_evaluator_receipt_v1",
        "status": "PASS",
        "engine_executions": 0,
        "search_executions": 0,
        "artifact_count": go["artifact_count"],
        "coordinate_count": go["coordinate_count"],
        "single_swap_count": len(swap_rows),
        "compile_elapsed_ms": str(go["compile_elapsed_ms"]),
        "mean_hot_evaluation_ms": str(go["mean_hot_evaluation_ms"]),
        "incumbent": {
            "go_dps": str(go["incumbent_dps"]),
            "python_dps": str(python_incumbent),
        },
        "broad_profile": {
            "go_dps": str(go["broad_profile_dps"]),
            "python_dps": str(python_broad),
        },
        "single_swaps": swap_rows,
        "absolute_tolerance": str(TOLERANCE),
        "checks": checks,
        "interpretation": (
            "The real request is indexed once, physical assignments enforce slot/"
            "four-piece/global-ID legality, and the compiled Go formula matches an "
            "independent Python reduction for incumbent, broad deltas, and 20 real "
            "legal single replacements. Candidate arithmetic starts no engine."
        ),
        "next_stage": "GOB-5_clean_Go_FGBS_to_current_accepted_Python_capability",
    }
    RECEIPT_PATH.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


def _assignment_deltas(request, coordinates, assignment):
    artifacts = {row["artifact_id"]: row for row in request["artifacts"]}
    coordinate_index = {value: index for index, value in enumerate(coordinates)}
    output = [0.0] * len(coordinates)
    for wearer_index, wearer in enumerate(request["wearers"]):
        incumbent = _stats(
            artifacts[row["artifact_id"]] for row in wearer["current_artifacts"]
        )
        candidate = _stats(artifacts[value] for value in assignment[wearer_index])
        for key in incumbent.keys() | candidate.keys():
            coordinate = f"{wearer['wearer_key']}.{key}"
            if coordinate in coordinate_index:
                output[coordinate_index[coordinate]] = (
                    candidate.get(key, 0.0) - incumbent.get(key, 0.0)
                )
    return output


def _stats(artifacts):
    output = defaultdict(float)
    for artifact in artifacts:
        output[artifact["main_stat"]["key"]] += float(
            artifact["main_stat"]["value"]
        )
        for row in artifact["substats"]:
            output[row["key"]] += float(row["value"])
    return output


def _evaluate_panel(compact, coordinates, deltas):
    delta_by_coordinate = dict(zip(coordinates, deltas, strict=True))
    member_dps = []
    for member in compact["members"]:
        values = [0.0] * (len(member["nodes"]) + 1)
        for node in member["nodes"]:
            operation = node["operation"]
            inputs = [values[row["node_id"]] for row in node["inputs"]]
            if operation in {"constant", "opaque_frozen"}:
                value = float(node["value"])
            elif operation == "artifact_stat":
                value = delta_by_coordinate.get(node["coordinate"], 0.0)
            elif operation == "add":
                value = math.fsum(inputs)
            elif operation == "multiply":
                value = math.prod(inputs)
            elif operation == "min":
                value = min(inputs)
            elif operation == "max":
                value = max(inputs)
            elif operation == "power":
                value = inputs[0] ** inputs[1]
            else:
                raise RuntimeError(f"unsupported operation {operation!r}")
            if not math.isfinite(value):
                raise RuntimeError(f"node {node['node_id']} is non-finite")
            values[node["node_id"]] = value
        damage = math.fsum(values[row["root_node_id"]] for row in member["channels"])
        member_dps.append(damage / (float(member["duration_ms"]) / 1000.0))
    return math.fsum(member_dps) / len(member_dps)


if __name__ == "__main__":
    main()
