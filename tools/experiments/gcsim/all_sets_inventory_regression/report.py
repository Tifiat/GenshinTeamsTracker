"""Render the retained before/after data, without running any simulator."""
from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

SLOT_ORDER = ("flower", "plume", "sands", "goblet", "circlet")
SLOT_LABELS = {
    "flower": "Цветок",
    "plume": "Перо",
    "sands": "Часы",
    "goblet": "Кубок",
    "circlet": "Корона",
}
STAT_LABELS = {
    "hp": "HP",
    "hp_percent": "HP",
    "atk": "АТК",
    "atk_percent": "АТК",
    "def": "ЗЩТ",
    "def_percent": "ЗЩТ",
    "em": "МС",
    "energy_recharge": "ВЭ",
    "crit_rate": "КШ",
    "crit_damage": "КУ",
    "pyro_damage_bonus": "Пиро",
    "hydro_damage_bonus": "Гидро",
    "electro_damage_bonus": "Электро",
    "cryo_damage_bonus": "Крио",
    "anemo_damage_bonus": "Анемо",
    "geo_damage_bonus": "Гео",
    "dendro_damage_bonus": "Дендро",
    "physical_damage_bonus": "Физ.",
    "healing_bonus": "Лечение",
}
PERCENT_STATS = frozenset({
    "hp_percent", "atk_percent", "def_percent", "energy_recharge",
    "crit_rate", "crit_damage", "pyro_damage_bonus", "hydro_damage_bonus",
    "electro_damage_bonus", "cryo_damage_bonus", "anemo_damage_bonus",
    "geo_damage_bonus", "dendro_damage_bonus", "physical_damage_bonus",
    "healing_bonus",
})
GAMING_CASE = "gaming_melt_all_sets"
PRIOR_ACCEPTED_CASES = {
    "lunar_crystallize_all_sets",  # Navia
    "lunar_charged_all_sets",      # Flins
    "lunar_bloom_all_sets",
    "bountiful_core_all_sets",
}


def top(row):
    candidates = row.get("product", {}).get("candidates", [])
    return candidates[0] if candidates else {}


def text(value):
    return str(value).replace("|", "/").replace("\n", " ")


def _candidate_artifact_ids(candidate):
    result = {}
    for build in candidate.get("builds", []) or []:
        if not isinstance(build, dict):
            continue
        wearer = text(build.get("wearer_key") or "?")
        artifact_ids = build.get("artifact_ids")
        if not isinstance(artifact_ids, dict):
            continue
        for slot in SLOT_ORDER:
            try:
                artifact_id = int(artifact_ids[slot])
            except (KeyError, TypeError, ValueError):
                continue
            result[(wearer, slot)] = artifact_id
    return result


def _format_stat(stat):
    if not isinstance(stat, dict):
        return "—"
    key = str(stat.get("key") or "")
    label = STAT_LABELS.get(key, key or "?")
    value = stat.get("value")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return f"{label} {text(value)}"
    if not number.is_finite():
        return f"{label} {text(value)}"
    if key in PERCENT_STATS:
        rendered = f"{number * Decimal(100):.1f}".replace(".", ",") + "%"
    else:
        rendered = format(number.normalize(), "f").replace(".", ",")
    return f"{label} {rendered}"


def _format_dps(value):
    try:
        return f"{Decimal(str(value)):.1f}".replace(".", ",")
    except (InvalidOperation, TypeError, ValueError):
        return text(value or "?")


def _request_artifact_lookup(rows):
    lookup = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            artifact_id = int(row["artifact_id"])
        except (KeyError, TypeError, ValueError):
            continue
        lookup[artifact_id] = row
    return lookup


def _artifact_description(artifact_id, artifacts):
    artifact = artifacts.get(artifact_id)
    if artifact is None:
        return f"#{artifact_id} (строка запроса отсутствует)"
    main = _format_stat(artifact.get("main_stat"))
    substats = artifact.get("substats")
    substats = substats if isinstance(substats, list) else []
    rendered_substats = ", ".join(_format_stat(row) for row in substats) or "—"
    return f"#{artifact_id} ({main}; {rendered_substats})"


def render_top_three_builds(row):
    work = row.get("inventory_search", {})
    frozen_rows = work.get("finalist_artifact_rows")
    if not isinstance(frozen_rows, list) or not frozen_rows:
        return []
    candidates = row.get("product", {}).get("candidates", [])
    candidates = candidates[:3] if isinstance(candidates, list) else []
    if not candidates:
        return []

    artifacts = _request_artifact_lookup(frozen_rows)
    top_one = _candidate_artifact_ids(candidates[0])
    if not top_one:
        return []
    top_one_dps = _format_dps((candidates[0].get("measured") or {}).get("dps"))
    lines = [
        "",
        "### Топ-3 сборки (точные статы из строк запроса)",
        "",
        f"Топ-1 — {top_one_dps} DPS",
        "",
        "| Персонаж | Слот | ID | Главный стат | Сабстаты |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for (wearer, slot), artifact_id in sorted(
        top_one.items(), key=lambda item: (item[0][0], SLOT_ORDER.index(item[0][1]))
    ):
        artifact = artifacts.get(artifact_id)
        main_stat = _format_stat(artifact.get("main_stat")) if artifact else "строка запроса отсутствует"
        substats = artifact.get("substats") if artifact else []
        substats = substats if isinstance(substats, list) else []
        rendered_substats = ", ".join(_format_stat(stat) for stat in substats) or "—"
        lines.append(
            f"| {wearer} | {SLOT_LABELS[slot]} | {artifact_id} | {main_stat} | {rendered_substats} |"
        )

    for rank, candidate in enumerate(candidates[1:3], start=2):
        current = _candidate_artifact_ids(candidate)
        dps = _format_dps((candidate.get("measured") or {}).get("dps"))
        lines += ["", f"Топ-{rank} — {dps} DPS"]
        changed = [
            ((wearer, slot), top_one.get((wearer, slot)), current.get((wearer, slot)))
            for wearer, slot in sorted(
                set(top_one) | set(current),
                key=lambda item: (item[0], SLOT_ORDER.index(item[1]) if item[1] in SLOT_ORDER else 99),
            )
            if top_one.get((wearer, slot)) != current.get((wearer, slot))
        ]
        if not changed:
            lines.append("Изменений относительно топ-1 нет.")
            continue
        lines += [
            "",
            "| Персонаж | Слот | Замена относительно топ-1 |",
            "| --- | --- | --- |",
        ]
        for (wearer, slot), old_id, new_id in changed:
            old_description = _artifact_description(old_id, artifacts) if old_id is not None else "—"
            new_description = _artifact_description(new_id, artifacts) if new_id is not None else "—"
            slot_label = SLOT_LABELS.get(slot, slot)
            lines.append(f"| {wearer} | {slot_label} | {old_description} → {new_description} |")
    return lines


def build_text(build):
    sets = "+".join(f"{s['count']} {s['name']}" for s in build.get("sets", []) if s["count"] >= 2) or "no bonus"
    slots = ("flower", "plume", "sands", "goblet", "circlet")
    ids = ",".join(str(build.get("artifact_ids", {}).get(s, "?")) for s in slots)
    mains = "; ".join(str(build.get("main_stats", {}).get(s, "?")) for s in slots[2:])
    return f"{sets}; IDs {ids}; {mains}"


def render_report(before, after, lunar_control=None):
    old = {r["id"]: r for r in before["runs"] if r["mode"] == "all_sets"}
    new = {r["id"]: r for r in after["runs"]}
    non_gaming_total = sum(key != GAMING_CASE for key in old)
    non_gaming = {key: row for key, row in new.items() if key != GAMING_CASE}
    completed = sum(bool(r.get("success") and top(r).get("measured")) for r in non_gaming.values())
    interrupted = sum(bool(r.get("interrupted_by_user")) for r in non_gaming.values())
    latest_consumer_sha = next(
        (
            str(row["optimizer_sha256"])
            for row in reversed(after.get("runs", []))
            if row.get("optimizer_sha256")
        ),
        None,
    )
    latest_consumer_rows = sum(
        row.get("optimizer_sha256") == latest_consumer_sha
        for row in non_gaming.values()
    ) if latest_consumer_sha else 0
    engine_match = bool(new) and all(
        row.get("engine_identity") and row["engine_identity"] == old[key].get("engine_identity")
        for key, row in new.items()
    )
    lines = ["# All Sets comparison — original 2026-09-19 matrix and later attempts", "",
             "Current acceptance owner: [GP-3](../../handoff/GCSIM_GOB11_GP3_CHECKPOINT.md).", "",
             f"Successful retained non-Gaming rows: {completed}/{non_gaming_total}; "
             f"user-interrupted: {interrupted}. Latest consumer SHA `{text(latest_consumer_sha or 'unavailable')}` "
             f"appears on {latest_consumer_rows}/{non_gaming_total} non-Gaming row receipts "
             "(consumer provenance only, not a same-input or accuracy certificate). "
             "Gaming is historical/deferred, not accepted by this continuation. "
             "Earlier Navia/Flins/Lunar/Bountiful matrix receipts keep their recorded SHAs and were not rerun "
             "in this continuation; later saved-user repair gates are separate evidence, not replacement matrix rows. "
             "Retained success is receipt status, not acceptance; GP-3 owns acceptance. "
             "Original log: [before.json](before.json); "
             "all post-change attempts, including failures: [after.json](after.json). "
             "The original matrix was copied byte-for-byte, not rerun.", "",
             f"Receipt status at capture: {text(after.get('matrix_status', 'in_progress'))}. "
             f"{text(after.get('stop_reason', ''))}", "",
             "Scope: the same 14 saved virtual profiles, rotation files and infinite-energy "
             "product request/session classes behind All Sets. No Theory rerun. The baseline "
             "does not retain an inventory hash; exact historical inventory identity cannot "
             "be independently proved. New rows retain inventory/config/rotation/optimizer "
             "identities. Backend completion is not a physical button check or a global-optimum proof.", "",
             "Inputs: [unchanged archetype manifest](../../../tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json). "
             f"Every compared row matches its original engine identity: **{engine_match}** "
             "(False also means unavailable). Each run records its actual engine and optimizer "
             "identities. [install.json](install.json) is the original inventory-search deployment "
             "receipt; later neutral-observer deployment is documented in GP-3 and the Go design.", "",
             "DPS are ordinary simulator means, not proposal hints. Differences within three "
             "combined standard errors are marked noise-scale (descriptive, not a paired test). "
             "Physical set counts do not by themselves prove a bonus activated.", "",
             "Product warnings are printed verbatim. An opaque-formula warning may reflect "
             "ParametricView opacity uncertainty aggregated across finalists, not only a current witness.", "",
             "Historical inventory-search attempts changed both the algorithm and exploration "
             "budgets; their gains do not isolate those factors. Neutral attempts are identified "
             "below and use a different capture/search pipeline. A partial "
             "matrix cannot establish quality for untested teams or a global optimum.", "",
             "| Team | Before DPS | After DPS | Change | Noise scale | Before/after seconds | Captured formula contexts | Stop |",
             "| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |"]
    for key, original in old.items():
        row = new.get(key)
        baseline = top(original)
        baseline_dps = float(baseline["measured"]["dps"])
        if key == GAMING_CASE:
            lines.append(
                f"| {key} | {baseline_dps:.1f} | historical/deferred | | | | | "
                "not accepted by this continuation |"
            )
            continue
        if not row:
            lines.append(f"| {key} | {baseline_dps:.1f} | not run | | | | | |")
            continue
        candidate, baseline = top(row), top(original)
        work = row.get("inventory_search", {})
        if row.get("interrupted_by_user"):
            lines.append(f"| {key} | {baseline_dps:.1f} | interrupted | | | {row.get('wall_seconds',0):.1f} | | user request; not a quality result |")
            continue
        if not row.get("success") or not candidate.get("measured"):
            lines.append(f"| {key} | {baseline_dps:.1f} | FAILED | | | {row.get('wall_seconds',0):.1f} | | {text(row.get('error'))} |")
            continue
        a, b = baseline_dps, float(candidate["measured"]["dps"])
        se = math.hypot(float(baseline["measured"]["standard_error"]), float(candidate["measured"]["standard_error"]))
        noise = "noise-scale" if abs(b-a) <= 3*se else "above 3 combined SE"
        contexts = (work.get("capture_members") or 0) // 2
        if key in PRIOR_ACCEPTED_CASES:
            status = "earlier matrix receipt; not rerun in this continuation"
        elif row.get("optimizer_sha256") != latest_consumer_sha:
            status = "historical receipt; not rerun with latest consumer"
        else:
            status = text(work.get("search_stop_reason"))
        lines.append(f"| {key} | {a:.1f} | {b:.1f} | {(b/a-1)*100:+.2f}% | {noise} | {original.get('wall_seconds',0):.1f} / {row.get('wall_seconds',0):.1f} | {contexts} | {status} |")
    for key, row in new.items():
        lines += ["", f"## {key}", "", f"Attempt {row.get('attempt')}; optimizer `{row.get('optimizer_sha256')}`."]
        if key == GAMING_CASE:
            lines += ["", "Gaming is historical/deferred, not accepted by this continuation."]
        elif key in PRIOR_ACCEPTED_CASES:
            lines += ["", "Earlier matrix receipt, not rerun in this continuation; recorded SHA is retained above. Consult GP-3 and separate saved-user repairs for current acceptance."]
        elif row.get("optimizer_sha256") != latest_consumer_sha:
            lines += ["", "Historical receipt; not rerun with the latest consumer in this continuation."]
        warnings = row.get("product", {}).get("warnings", [])
        if warnings:
            lines += ["", "Product warnings (verbatim): " + ", ".join(text(warning) for warning in warnings) + "."]
        if not row.get("success"):
            if row.get("interrupted_by_user"):
                lines += ["", row["interruption_note"], "", f"Original process status retained: {row.get('error')}"]
            else:
                lines += ["", f"Failure retained: {row.get('error')}"]
            continue
        previous = {b["wearer_key"]: b for b in top(old[key]).get("builds", [])}
        for build in top(row).get("builds", []):
            prior = previous[build["wearer_key"]]
            if build == prior:
                lines += ["", f"- {build['wearer_key']}: unchanged."]
            else:
                lines += ["", f"- {build['wearer_key']}: {build_text(prior)} → {build_text(build)}."]
        lines += render_top_three_builds(row)
        work = row.get("inventory_search", {})
        if work.get("search_algorithm") == "neutral_event_effects":
            cycles = work.get("neutral_cycles") or []
            lines += ["", "Pipeline: neutral event/effect model; ordinary final measurements are n500 once per finalist. "
                      f"Cycles: {len(cycles)}; prepared {sum(c.get('Prepared',0) for c in cycles)}/"
                      f"{sum(c.get('Total',0) for c in cycles)}; "
                      f"heuristically deferred {sum(c.get('HeuristicSkipped',0) for c in cycles)}. "
                      "Completed cycles are not an exhaustive/global-optimum proof."]
        contexts = work.get("search_work") or []
        if work.get("search_algorithm") == "neutral_event_effects":
            model = work.get("neutral_model") or {}
            lines += ["", f"Coverage markers: {work.get('pending')} non-exhaustive regions; "
                      "these are NOT an unfinished preparation queue or a timeout. "
                      f"Unavailable packages: {model.get('Unavailable',0)}. "
                      f"Evaluations: {work.get('search_expansions')}. "
                      f"Winner formula residual: {top(row).get('formula_residual')}.", "",
                      f"Search total: {float(work.get('search_seconds') or 0):.2f}s; "
                      f"package preparation: {float(work.get('proposal_seconds') or 0):.2f}s; "
                      f"rules: {model.get('RuleSeconds',0):.2f}s; binding: {model.get('BindSeconds',0):.2f}s. "
                      "Nested counters overlap; do not sum these phases. "
                      f"Joint refinement: {float(work.get('neutral_joint_seconds') or 0):.2f}s. "
                      "The whole-session wall time above includes Python preparation and final measurements."]
            joint = work.get('neutral_package_joint') or []
            if joint:
                lines += ["", "Joint package replacement: "
                          f"{sum(bool(lane.get('Finished')) for lane in joint)}/{len(joint)} bounded lanes completed; "
                          f"{sum(lane.get('Proposals', 0) for lane in joint)} pair proposals, "
                          f"{sum(lane.get('Scored', 0) for lane in joint)} complete seeds scored, "
                          f"{sum(lane.get('Refined', 0) for lane in joint)} distinct-tuple refinements; "
                          f"{sum(lane.get('Seconds', 0) for lane in joint):.2f}s within search time. "
                          "This is a bounded heuristic frontier, NOT an exhaustive joint optimum. "
                          f"Allocation deferrals {sum(lane.get('AllocationDeferred', 0) for lane in joint)}; "
                          f"unavailable seed bindings {sum(lane.get('Unavailable', 0) for lane in joint)}."]
            continue
        lines += ["", f"Search queue records: {work.get('queued')} queued; {work.get('pending')} pending; "
                  f"{work.get('unqueued_across_guides')} unmodeled/unqueued proposals; "
                  f"{work.get('reservation_deferred','not recorded')} unresolved joint reservations. "
                  f"Bounds: {sum(c.get('bound_evaluations',0) for c in contexts)} evaluations; "
                  f"{sum(c.get('bound_pruned_builds',0) for c in contexts)} region leaves pruned "
                  "(sum over searches, not unique full-team builds). "
                  f"{sum(c.get('budget_unexpanded',0) for c in contexts)} region leaves left by work limits "
                  "(also overlapping between searches). "
                  f"Winner formula residual: {top(row).get('formula_residual')}.", "",
                  f"Work timing: {sum(c.get('CaptureSeconds',0) for c in contexts):.2f}s fresh captures; "
                  f"{sum(c.get('SearchSeconds',0) for c in contexts):.2f}s artifact refinement; "
                  f"{float(work.get('proposal_seconds') or 0):.2f}s proposals. "
                  "Queue totals span refreshed anchors, not an exhaustive four-wearer set Cartesian domain."]
    if after.get("review_notes"):
        lines += ["", "## Historical analysis at the first user-requested stop", "",
                  "The notes below describe the earlier inventory-bound attempts, not later neutral runs. "
                  "They are retained as failed evidence; the current owner is GP-3.", ""]
        for note in after["review_notes"]:
            lines += [f"- {note}", ""]
    if lunar_control is not None and "lunar_charged_all_sets" in new:
        from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
            _non_artifact_hash, _ordinary_budget,
        )
        row = new["lunar_charged_all_sets"]
        prepared = row.get("inventory_search", {}).get("prepared_config")
        if prepared:
            digest = _non_artifact_hash(_ordinary_budget(prepared, iterations=1000, workers=4))
            same = digest == lunar_control["non_artifact_sha256"]
            measured = top(row).get("measured", {})
            lines += ["", "## Known 108k / 144.7k control", "",
                      "Reference: [artifact-only cross-check](../../../tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_artifact_crosscheck_lineage5_v1.json). "
                      "This retained Flins result is a prior accepted receipt, not a rerun in this continuation. "
                      f"The stronger legal build measured {lunar_control['dps']:.3f} DPS "
                      f"(SE {lunar_control['standard_error']:.3f}, n={lunar_control['iterations']}). "
                      f"Non-artifact config identity matches the post-change input: **{same}**, "
                      "after normalizing iteration/worker counts only. "
                      f"SHA256 `{digest}`."]
            if measured:
                gap = float(measured["dps"]) - lunar_control["dps"]
                conclusion = ("This specific known-control gap is exceeded by the measured mean; "
                              "global search quality, performance and visible UI acceptance remain separate gates."
                              if gap >= 0 else "An improvement over the old matrix is not a recall pass while a "
                              "stronger known legal control remains missed.")
                lines += ["", f"Retained search result minus that control: {gap:+.3f} DPS "
                          f"({gap/lunar_control['dps']*100:+.2f}%). {conclusion}"]
    return "\n".join(lines) + "\n"


def write_report(directory: Path):
    before = json.loads((directory / "before.json").read_text(encoding="utf-8"))
    after = json.loads((directory / "after.json").read_text(encoding="utf-8"))
    control_path = Path(__file__).resolve().parents[4] / "tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_artifact_crosscheck_lineage5_v1.json"
    control = next(row for row in json.loads(control_path.read_text(encoding="utf-8"))["cases"] if row["name"] == "account_top1")
    report = render_report(before, after, control)
    successor = directory / "flins-user-stabilization-20260926.json"
    if successor.is_file():
        report += render_saved_repair(json.loads(successor.read_text(encoding="utf-8")))
    data = report.encode("utf-8")
    if len(data) > 256 * 1024:
        raise ValueError("Comparison report exceeds 256 KiB")
    (directory / "report.md").write_bytes(data)


def render_saved_repair(receipt):
    lines = ["", "## 2026-09-26: exact user request — stabilization and preparation repair", "",
        "Separate successor, NOT a fourth matrix retry or a replacement for the three retained attempts. "
        "[Immutable old/new receipt](flins-user-stabilization-20260926.json). "
        f"Source: `{receipt['source_run']}`; request `{receipt['canonical_request_sha256']}`. "
        "Talents10/10/10, unchanged587-item inventory, rotation, two fixed capture seeds and active engine. "
        "Uses the button's installed executable through its actual Python preflight/source/process methods, "
        "skipping account request rebuilding to preserve the exact input. No physical UI click.", ""]
    if not receipt.get('success'):
        return '\n'.join(lines + [f"Failed replay retained: {text(receipt.get('error'))}.", ""])
    a, b = receipt['before'], receipt['after']
    lines += ["| Same measured boundary | Before | After |", "| --- | ---: | ---: |",
        f"| Complete Go backend, seconds | {a['total_elapsed_ms']/1000:.3f} | {b['total_elapsed_ms']/1000:.3f} |",
        f"| Capture/model/search, seconds | {a['search_seconds']:.3f} | {b['search_seconds']:.3f} |",
        f"| Effect preparation, seconds (nested) | {a['neutral_model']['RuleSeconds']:.3f} | {b['neutral_model']['RuleSeconds']:.3f} |",
        f"| Formula evaluations | {a['search_expansions']} | {b['search_expansions']} |", "",
        f"Backend speedup {a['total_elapsed_ms']/b['total_elapsed_ms']:.2f}x; "
        f"new adapter replay {receipt['replay_wall_seconds']:.3f}s (not whole fresh UI time). "
        f"Search configuration unchanged: **{a['search_config'] == b['search_config']}**. "
        "Both cycles still prepare2096/2096 packages; identical586 sampled refinements and3606 "
        "heuristic deferrals. This is not a smaller candidate shortlist or increased time budget.", "",
        "All six non-baseline finalists complete single-neighborhood stabilization; "
        "18 accepted changes/27145 extra evaluations. Every returned representative improves its "
        "own old formula score. The top1 changes only Flins plume1534->1535; other19 IDs and sets stay fixed. "
        f"Formula {a['verification']['winner']['formula_dps']:.3f}->{b['verification']['winner']['formula_dps']:.3f}. "
        f"New ordinary n500 {b['verification']['winner']['measured_dps']:.3f} "
        f"(SE {b['verification']['winner']['standard_error']:.3f}). "
        "Do not infer a measured improvement or regression from independent n500 means: "
        "the prior dedicated n4000 feather comparison establishes the item's advantage.", "",
        "Stop remains `neutral_cycle_budget`, NOT a timeout or an exhaustive optimum. "
        "The complete final single-item neighborhood and sampled-pair stability are proved only "
        "for this formula/these finalists; broader set combinations and heuristic deferrals remain open. "
        "Two neutral captures, seven ordinary n500 evaluations; no n128 ladder, other team or Gaming. "
        f"Consumer `{receipt['optimizer_sha256']}`; active engine unchanged `{receipt['engine_id']}`.", ""]
    return '\n'.join(lines)
