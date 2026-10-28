"""Frozen receipt gates and practical groups. No engine imports or execution."""
from __future__ import annotations

import math

LIGHT_SHA = "fd9a6a3367694a978cd77b8ed61111d1ab51d296467ad95ff8e4bed2c675eb2d"
NATIVE_SHA = "04aa6940e15e93512f38e821007d0ff7d4c1ec03b9aeee514fd0068793d51369"
CONSUMER_SHA = "e0bf5d64d6d6341fc434bf81f095e67e3e6a3d3ac43abf4fd7475a293bad6cf4"
ARTIFACT_SHA = "7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c"
BINDING_SHA = "8d143c742ac9501df45be2a6832cadb1ac337ccb2253069f51fe9a67978e4c4d"
VARIANTS = ("H_light", "H_baseline")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def rows_of(records, kind):
    return [r for r in records if r.get("kind") == kind]


def one(records, kind):
    rows = rows_of(records, kind)
    if len(rows) != 1:
        raise ValueError(f"Expected one {kind}, received {len(rows)}")
    return rows[0]


def _key(row):
    key = row["package_key"]
    if len(key.split("|")) != 4:
        raise ValueError("Package tuple must name four ordered wearers")
    return key


def ranking(policy, reference, fraction):
    rows = policy["ranking"]
    if len({r["family"] for r in rows}) != len(rows):
        raise ValueError("Duplicate numerical family")
    for row in rows:
        _key(row)
        if not finite(row["formula_dps"]):
            raise ValueError("Nonfinite numerical family lower bound")
    return sorted((r for r in rows if r["formula_dps"] >= reference * (1 - fraction)),
                  key=lambda r: (-r["formula_dps"], _key(r), r["family"]))


def shortlist(policy, reference, fraction, limit=5):
    """Actual numeric representatives, greedy maximum minimum wearer distance."""
    remaining = ranking(policy, reference, fraction)
    selected, keys = [], set()
    while remaining and len(selected) < limit:
        if not selected:
            chosen = remaining[0]
        else:
            def priority(row):
                distance = min(sum(a != b for a, b in zip(_key(row).split("|"), _key(s).split("|"))) for s in selected)
                return (-distance, -row["formula_dps"], _key(row), row["family"])
            chosen = min(remaining, key=priority)
        selected.append(chosen)
        keys.add(_key(chosen))
        remaining = [r for r in remaining if _key(r) not in keys]
    return [{"family": r["family"], "package_key": _key(r), "lower": r["formula_dps"],
             "deficit_percent": 100 * (1 - r["formula_dps"] / reference)} for r in selected]


def band(policy, reference, fraction):
    members = ranking(policy, reference, fraction)
    keys = []
    for row in members:
        aliases = policy["aliases_by_family"][row["family"]]
        if _key(row) not in aliases or any(len(k.split("|")) != 4 for k in aliases):
            raise ValueError("Representative/alias identity inconsistent")
        keys.extend(aliases)
    if len(keys) != len(set(keys)):
        raise ValueError("Alias assigned to multiple families")
    choices = [sorted({k.split("|")[actor] for k in keys}) for actor in range(4)]
    return {"family_count": len(members), "alias_tuple_count": len(keys),
            "per_wearer_packages": choices, "shortlist": shortlist(policy, reference, fraction),
            "below_band_families_remain_unknown": len(policy["ranking"]) - len(members)}


def quality(records):
    policies = {r["variant"]: r for r in rows_of(records, "hybrid_policy")}
    results = {r["variant"]: r for r in rows_of(records, "light_policy_result")}
    reference = max(results[v]["best"]["formula_dps"] for v in VARIANTS)
    if not finite(reference) or reference <= 0:
        raise ValueError("Invalid shared reference")
    groups = {}
    for variant in VARIANTS:
        groups[variant] = {}
        for suffix, label in (("_first_pass", "first"), ("", "full")):
            policy = policies[variant + suffix]
            groups[variant][label] = {str(int(f * 100)): band(policy, reference, f) for f in (0.02, 0.03)}
        groups[variant]["unknown"] = {
            "unavailable_tuples": len({k for keys in policies[variant]["unavailable_by_reason"].values() for k in keys}),
            "reason_groups": len(policies[variant]["unavailable_by_reason"]),
            "source_upper": "unbounded", "outer_upper": "unbounded",
        }
    light3, baseline3 = (groups[v]["full"]["3"] for v in VARIANTS)
    baseline2 = groups["H_baseline"]["full"]["2"]["shortlist"]
    anchor = _key(ranking(policies["H_baseline"], reference, 1.0)[0]).split("|")
    missing = set()
    for row in baseline2:
        for actor, package in enumerate(row["package_key"].split("|")):
            if package != anchor[actor] and package not in light3["per_wearer_packages"][actor]:
                missing.add((actor, package))
    deficit = 1 - results["H_light"]["best"]["formula_dps"] / reference
    light_time, baseline_time = (results[v]["seconds"] for v in VARIANTS)
    runtime_excess = light_time - baseline_time
    audit_values = [r["candidate"]["formula_dps"] for r in rows_of(records, "light_audit_attempt") if r.get("candidate")]
    best_audit = max(audit_values, default=None)
    failures = []
    if deficit > 0.01:
        failures.append("light_leader_deficit_over_1_percent")
    required = min(3, len(baseline3["shortlist"]))
    if len(light3["shortlist"]) < required:
        failures.append("insufficient_demonstrated_diverse_choices")
    if missing:
        failures.append("baseline_2_percent_shortlist_direction_missing_from_light_3_percent")
    if runtime_excess > max(10.0, 0.25 * baseline_time):
        failures.append("light_runtime_regression_over_max_10s_25percent")
    if best_audit is not None and best_audit > 1.01 * reference:
        failures.append("legal_independent_audit_point_over_1_percent_above_reference")
    return {"pass": not failures, "failures": failures, "frozen_reference": reference,
            "reference_rebased_after_audit": False, "leader_deficit_percent": 100 * deficit,
            "light_policy_seconds": light_time, "baseline_policy_seconds": baseline_time,
            "runtime_reduction_percent": 100 * (1 - light_time / baseline_time),
            "required_diverse_choices": required, "missing_directions": sorted(missing),
            "best_partial_or_complete_audit_lower": best_audit, "groups": groups,
            "scope": "demonstrated inclusion only; aliases do not add shortlist slots; low or unseen lower bounds never exclude"}


def check_policy_contract(records):
    prep = one(records, "preparation")
    result_rows = rows_of(records, "light_policy_result")
    if [r["variant"] for r in result_rows] != list(VARIANTS):
        raise ValueError("Cold policy results missing, duplicated or out of order")
    for result, limit, deep in zip(result_rows, (135, 180), (0, 2)):
        name = result["variant"]
        if result.get("complete") is not True or result.get("stop_reason") != "" or result.get("wall_guard_hit") is not False:
            raise ValueError(name + " incomplete or guarded")
        if not finite(result["seconds"]) or not 0 < result["seconds"] < limit or result["policy_guard_seconds"] != limit:
            raise ValueError(name + " wall limit or post-operation time invalid")
        for key, expected in (("completed_catalog_passes", 2), ("completed_deep_passes", deep), ("planned_sweeps", 16), ("completed_sweeps", 16), ("observation_count", 3)):
            if result[key] != expected:
                raise ValueError(name + " counter differs: " + key)
        snapshot_rows = [r for r in rows_of(records, "hybrid_policy") if r["variant"] == name]
        if len(snapshot_rows) != 1:
            raise ValueError(name + " missing/duplicate full snapshot")
        snapshot = snapshot_rows[0]
        for key, expected in (("completed_catalog_passes", 2), ("completed_refined_passes", deep), ("full_sweeps", 16), ("attempted_sweeps", 16), ("complete_outer_plan", True)):
            if snapshot[key] != expected:
                raise ValueError(name + " inconsistent final snapshot: " + key)
        for actual, cap in ((snapshot["work"]["Formula"], 400000), (snapshot["work"]["Gradient"], 100000), (snapshot["reuse"]["Requests"], 9 + 16 * prep["packages_per_wearer"] + 64)):
            if not isinstance(actual, int) or not 0 <= actual < cap:
                raise ValueError(name + " post-operation work guard binding")
        if snapshot["reuse"]["NumericHits"] or snapshot["final_solution_cache_enabled"] or snapshot["additional_audit_included"]:
            raise ValueError(name + " forbidden numeric reuse or audit rescue")
        if snapshot["best"] != result["best"]:
            raise ValueError(name + " final witness changed after snapshot")
        if not snapshot["ranking"] or max(r["formula_dps"] for r in snapshot["ranking"]) != result["best"]["formula_dps"]:
            raise ValueError(name + " ranking/leader lower bound differs")
        config = [r for r in rows_of(records, "light_policy_configuration") if r["variant"] == name]
        expected = {"Depth": "full", "CatalogPasses": 2, "PolicySeconds": 180, "FormulaLimit": 400000,
                    "GradientLimit": 100000, "ResolveLimit": 9 + 16 * prep["packages_per_wearer"] + 64}
        if len(config) != 1 or config[0]["common_configuration"] != expected or config[0]["numeric_solution_cache"] is not False or config[0]["cold_model_and_context_caches"] is not True or config[0]["skip_pass_deep_bundles"] != (deep == 0):
            raise ValueError(name + " frozen configuration changed")
    expected_snapshots = [v + suffix for v in VARIANTS for suffix in ("_pre_deep_pass0", "_first_pass", "_pre_deep_pass1", "")]
    if [r["variant"] for r in rows_of(records, "hybrid_policy")] != expected_snapshots:
        raise ValueError("First/full observation sequence incomplete")


def evaluate(result):
    failures, evidence, quality_gate = [], {}, {"pass": False, "failures": ["completeness_not_established"]}
    if result.get("phase") != "study":
        return {"acceptance_complete": False, "acceptance_failures": ["unit_phase_has_no_pair"], "quality_gate": quality_gate, "next_case_allowed": False}
    try:
        if result["status"] != "pass":
            raise ValueError("Managed process/setup/cleanup failed")
        for key in ("inputs_stable", "engine_stable", "protocol_stable", "historical_controls_removed"):
            if result.get(key) is not True:
                raise ValueError(key + " not established")
        if result["native_source_sha256"] != NATIVE_SHA or result["installed_consumer_sha256"] != CONSUMER_SHA or result["engine"]["artifact_sha256"] != ARTIFACT_SHA or result["engine"]["binding_sha256"] != BINDING_SHA:
            raise ValueError("Pinned source/consumer/engine identity differs")
        proof = result["adapter_equivalence"]
        if proof["light_identity_sha256"] != LIGHT_SHA or proof["inverse_transformation_exact"] is not True or proof["numerical_search_unchanged"] is not True or not all(p["inverse_transformation_exact"] is True for p in proof["transformed_files"].values()):
            raise ValueError("Stage10 equivalence missing")
        if result["prototype"]["light_identity_sha256"] != LIGHT_SHA:
            raise ValueError("Prototype Stage10 pin differs")
        if result["cleanup"]["job_absent"] is not True or result["cleanup"]["remaining_jobs"]:
            raise ValueError("Scratch cleanup incomplete")
        for key in ("compile", "contracts", "python_contracts", "study"):
            if result[key]["returncode"] != 0:
                raise ValueError(key + " failed")
        tests = result["contracts"]["passed_tests"]
        if len(tests) != 20 or len(set(tests)) != 20:
            raise ValueError("Expected 20 distinct retained/new Go contracts")
        if result["capture_members_actual"] != 2 or result["capture_reservation_spent"] != 2 or result["study_invocations"] != 1 or result["ordinary_finalists"] != 0 or result["installed_changes"] is not False:
            raise ValueError("Capture/finalist/invocation/mutation budget differs")
        records = result["records"]
        check_policy_contract(records)
        summary, audit, plan = (one(records, kind) for kind in ("light_study_summary", "light_audit_summary", "light_audit_plan"))
        if summary["offline_guard_seconds"] != 240 or not 0 < summary["seconds"] < 240 or summary["checks_guard_hit"] or not 0 <= summary["checks_seconds"] < 12:
            raise ValueError("Post-operation offline/checks guard binding")
        if not summary["policy_unchanged_after_audit"] or summary["leader_replays_completed"] != 2 or summary["fresh_capture_calls_inside_study"] or summary["ordinary_finalists"]:
            raise ValueError("Frozen comparison/replay/capture contract failed")
        pair_seconds = result.get("paired_offline_seconds", summary["seconds"])
        if not finite(pair_seconds) or not summary["seconds"] <= pair_seconds <= 480:
            raise ValueError("Aggregate two-case offline guard exceeded")
        if not finite(audit["seconds"]) or not 0 <= audit["seconds"] < 29 or audit["wall_guard_hit"] or audit["policy_rescue"] or audit["is_oracle"] or audit["complete_exclusion_proof"]:
            raise ValueError("Audit scope or overall clock invalid")
        measured_components = sum(r["seconds"] for r in rows_of(records, "light_policy_result")) + audit["seconds"] + summary["checks_seconds"]
        if measured_components > summary["seconds"] + 0.001:
            raise ValueError("Offline wall time shorter than sequential measured components")
        if plan["both_nonleader_coverage"] != "reserved_first_target" or len(plan["targets"]) != 4 or plan["no_quota_transfer"] is not True:
            raise ValueError("Reserved independent audit plan missing")
        if plan["per_tuple_seconds"] != 7 or plan["per_start_seconds"] != 3 or plan["per_tuple_formula"] != 30000 or plan["per_tuple_gradient"] != 7500 or plan["audit_seconds"] != 29:
            raise ValueError("Audit quotas changed")
        for target in rows_of(records, "light_audit_target_result"):
            if target["formula"] > 30000 or target["gradient"] > 7500:
                raise ValueError("Post-operation audit work exceeded tuple quota")
        for attempt in rows_of(records, "light_audit_attempt"):
            if attempt["formula"] > 15000 or attempt["gradient"] > 3750:
                raise ValueError("Post-operation audit work exceeded start quota")
            if attempt["completed_stages"] == 3 and not attempt["stop_reason"] and attempt["seconds"] > 3:
                raise ValueError("Audit attempt completeness hides wall guard")
        if audit["complete"] and (audit["completed_attempts"] != 8 or audit["target_wall_guard_hits"] or audit["pending_targets"] or audit["unavailable_targets"]):
            raise ValueError("Audit completeness inconsistent")
        replay = rows_of(records, "light_leader_replay")
        if [r["variant"] for r in replay] != list(VARIANTS):
            raise ValueError("Two cold leader replays missing")
        for row in replay:
            if not math.isclose(row["replayed_dps"], row["candidate"]["formula_dps"], rel_tol=1e-9, abs_tol=1e-9) or len(row["gradient"]) != 4 or any(len(a) != 10 or not all(finite(v) for v in a) for a in row["gradient"]):
                raise ValueError("Replay value or finite gradient failed")
        ready, ack = (one(records, k) for k in ("contrast_light_ready", "contrast_prefix_ack"))
        ri, ai = records.index(ready), records.index(ack)
        light_i = next(i for i, r in enumerate(records) if r.get("kind") == "light_policy_result" and r["variant"] == "H_light")
        base_i = next(i for i, r in enumerate(records) if r.get("kind") == "light_policy_configuration" and r["variant"] == "H_baseline")
        prefix = result["direct_prefix"]
        if not light_i < ri < ai < base_i or ready["baseline_started"] is not False or prefix["ready_count"] != 1 or prefix["ack_sent_count"] != 1 or prefix["baseline_excluded_by_ack"] is not True or not finite(prefix["seconds"]) or prefix["seconds"] <= 0:
            raise ValueError("Direct parent prefix barrier invalid")
        from .witness_audit import audit_records
        evidence["witness_audit"] = audit_records(records)
        quality_gate = quality(records)
        if summary["frozen_reference"] != quality_gate["frozen_reference"] or audit["frozen_reference"] != summary["frozen_reference"] or plan["frozen_reference"] != summary["frozen_reference"]:
            raise ValueError("Shared reference changed after policy freeze")
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
        failures.append(str(exc))
    return {"acceptance_complete": not failures, "acceptance_failures": failures,
            "acceptance_evidence": evidence, "quality_gate": quality_gate,
            "next_case_allowed": not failures and quality_gate["pass"]}


def validate_prerequisite(result, prototype_sha, protocol_sha):
    if result.get("case") != "chasca" or result.get("prototype", {}).get("sha256") != prototype_sha or result.get("protocol_sha256") != protocol_sha:
        raise ValueError("Nilou requires this frozen prototype/protocol's Chasca receipt")
    checked = evaluate(result)
    if result.get("acceptance_complete") is not True or result.get("next_case_allowed") is not True or not checked["next_case_allowed"]:
        raise ValueError("Chasca completeness/quality gate did not pass; no next capture")
    return one(result["records"], "light_study_summary")["seconds"]
