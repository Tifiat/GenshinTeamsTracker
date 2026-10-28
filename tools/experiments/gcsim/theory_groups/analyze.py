"""Receipt-only practical-group analysis; never imports or invokes an engine."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BANDS = (0.02, 0.03)
INPUTS = (
    ("chasca", "2026-10-09-theory-hybrid/chasca-01.json", "442b4385e298eb78a8bc19f062ab8d72c94ec58196e6db5c8214aedf5874838a", "H_transfer"),
    ("chiori", "2026-10-09-theory-hybrid/chiori-01.json", "8a8116c036a2ff84893087aa548873e663b3a86ee096c1a13232ecfae8de7d02", "H_transfer"),
    ("bountiful", "2026-10-09-theory-common-h/bountiful-01.json", "d8f6cb1fdd8c9bfebb2777d40146d2607611369c116b7db431d23aa9500d6b8b", "H_common_full"),
)


def membership(lower, reference, fraction):
    """A witnessed lower bound can prove inclusion, never exclusion."""
    if not math.isfinite(reference) or reference <= 0 or not 0 < fraction < 1:
        raise ValueError("A positive frozen reference and a fraction in (0, 1) are required")
    if lower is None:
        return "unknown"
    if not math.isfinite(lower):
        raise ValueError("Nonfinite score is not a witnessed lower bound")
    return "demonstrated_in_band" if lower >= reference * (1 - fraction) else "below_band_lower_bound_only"


def package_key(packages):
    return "|".join("+".join(f"{s['set_uid']}:{s['count']}" for s in sorted(p.get("sets") or [], key=lambda s: s["set_uid"])) or "none" for p in packages)


def policy_band(policy, reference, fraction):
    members = []
    for row in policy["ranking"]:
        if membership(row["formula_dps"], reference, fraction) == "demonstrated_in_band":
            members.append({"family": row["family"], "representative_package_key": row["package_key"],
                            "lower": row["formula_dps"], "deficit_fraction_of_reference": 1-row["formula_dps"]/reference,
                            "exact_alias_count": len(policy["aliases_by_family"][row["family"]])})
    members.sort(key=lambda row: (row["representative_package_key"], row["family"]))
    keys = [key for row in members for key in policy["aliases_by_family"][row["family"]]]
    if len(keys) != len(set(keys)):
        raise ValueError("A package key cannot belong to multiple exact families in one frozen world")
    return {"fraction": fraction, "threshold": reference*(1-fraction), "members": members,
            "family_count": len(members), "exact_alias_count": len(set(keys)),
            "alias_bearing_family_count": sum(row["exact_alias_count"] > 1 for row in members),
            "below_band_lower_bound_family_count": len(policy["ranking"])-len(members)}


def observation(record, index, full, reference):
    candidate = record.get("candidate")
    if candidate is None:
        return None
    family, score = candidate["formula_family"], candidate["formula_dps"]
    baseline = next((row for row in full["ranking"] if row["family"] == family), None)
    lower = baseline["formula_dps"] if baseline else None
    key = package_key(candidate["packages"])
    states = []
    for fraction in BANDS:
        before, after = membership(lower, reference, fraction), membership(score, reference, fraction)
        states.append({"fraction": fraction, "policy_membership": before, "point_membership": after,
                       "new_demonstrated_member": before != "demonstrated_in_band" and after == "demonstrated_in_band"})
    return {"record_index": index, "kind": record["kind"], "role": record.get("role"), "label": record.get("label", record.get("known_label")),
            "family": family, "package_key": key, "lower": score, "policy_family_lower": lower,
            "gain_fraction_of_reference": None if lower is None else (score-lower)/reference,
            "completed_stages": record.get("completed_stages"), "bands": states,
            "package_alias_seen_in_policy": key in full["aliases_by_family"].get(family, []),
            "credited_to_policy": False}


def analyze_case(name, relative, digest, full_label):
    path = ROOT / "docs/optimizer-evidence" / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Frozen receipt changed: " + relative)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["status"] != "pass":
        raise ValueError("Only passing receipts are admitted")
    policies = {r["variant"]: r for r in data["records"] if r.get("kind") == "hybrid_policy"}
    full = policies[full_label]
    first = policies[full_label.removesuffix("_full") + "_first_pass"]
    reference = full["best"]["formula_dps"]
    bands = []
    for fraction in BANDS:
        early, late = policy_band(first, reference, fraction), policy_band(full, reference, fraction)
        first_members = {r["family"] for r in early["members"]}
        full_members = {r["family"] for r in late["members"]}
        first_seen = {r["family"] for r in first["ranking"]}
        first_keys = {key for family in first_members for key in first["aliases_by_family"][family]}
        full_keys = {key for family in full_members for key in full["aliases_by_family"][family]}
        retained_family_keys = {key for family in first_members & full_members for key in full["aliases_by_family"][family]}
        bands.append({"fraction": fraction, "first": early, "full": late,
                      "new_in_full_not_seen_in_first": sorted(full_members-first_seen),
                      "crossed_into_band_after_first": sorted((full_members-first_members) & first_seen),
                      "first_members_missing_in_full": sorted(first_members-full_members),
                      "new_demonstrated_package_tuple_count": len(full_keys-first_keys),
                      "new_alias_tuples_on_first_band_families": len(retained_family_keys-first_keys),
                      "first_band_package_tuples_missing_in_full": len(first_keys-full_keys)})
    channels = {"independent_audit": [], "post_selection_on_policy": [], "historical_tuple_points": []}
    missing = {channel: [] for channel in channels}
    for index, record in enumerate(data["records"]):
        kind = record.get("kind")
        channel = ("independent_audit" if kind in ("hybrid_reference_attempt", "common_h_audit_attempt")
                   else "post_selection_on_policy" if kind == "progressive_known_on_leader"
                   else "historical_tuple_points" if kind == "progressive_known_control" else None)
        if channel:
            point = observation(record, index, full, reference)
            if point is not None:
                channels[channel].append(point)
            else:
                missing[channel].append(index)
    audit = next(r for r in data["records"] if r.get("kind") in ("hybrid_reference_summary", "common_h_audit_summary"))
    return {"case": name, "receipt": relative, "receipt_sha256": digest,
            "reference": {"origin": full_label + " frozen leader", "value": reference, "rebased_after_audit": False},
            "bands": bands, "observations": channels, "unavailable_or_missing_witness_records": missing,
            "audit_accounting": {key: audit.get(key) for key in ("planned_attempts", "completed_attempts", "pending_attempts")},
            "audit_baseline_scope": "Compared here with frozen full H; stage6 B actually followed P and does not update H",
            "policy_unknown": {"unique_unavailable_tuples": len({key for keys in full["unavailable_by_reason"].values() for key in keys}),
                               "reason_groups": len(full["unavailable_by_reason"]), "unvisited_outer_upper": "unbounded"},
            "timing": {"first_seconds": first["seconds"], "full_seconds": full["seconds"], "full_stages": full["stages_seconds"]}}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to((ROOT / "docs/optimizer-evidence/2026-10-09-theory-groups").resolve())
    if output.exists():
        raise FileExistsError(output)
    result = {"kind": "theory_practical_groups_posthoc_v1", "new_engine_calls": 0, "new_capture_members": 0,
              "new_finalist_calls": 0, "policy_modified": False, "bands": BANDS,
              "scope": "Frozen-receipt observed lower-bound inclusion; no exclusion, statistical equivalence, or upper-bound proof",
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.glob("*.py"))},
              "cases": [analyze_case(*row) for row in INPUTS]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "pass", "output": str(output), "new_capture_members": 0}))


if __name__ == "__main__":
    main()
