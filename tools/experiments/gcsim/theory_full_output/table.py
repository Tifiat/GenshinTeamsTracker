"""Lossless public projections for terminal Theory v2 snapshots.

This module only transforms an already captured result. It does not run an
optimizer, select candidates, write files, or infer game/source mechanics.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from run_workspace.gcsim.optimizer_go_theory_session import copy_theory_snapshot


SCHEMA_KIND = "gtt_gcsim_optimizer_theory_full_output_v1"
STAT_KEYS = (
    "atk", "atk_percent", "crit_damage", "crit_rate", "def",
    "def_percent", "em", "energy_recharge", "hp", "hp_percent",
)
CRIT_STATS = frozenset({"crit_rate", "crit_damage"})
SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
TABLE_SLOTS = ("sands", "goblet", "circlet")


def _json_copy(value: Any) -> Any:
    """Return a JSON-compatible deep copy and reject non-finite values."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _units(value: float) -> float:
    """Normalize a quarter-grid unit count to an exact quarter value."""
    quarter_units = round(float(value) * 4)
    return quarter_units / 4


def _combo_id(request_sha256: str, tuple_key: str, context_sha256: str) -> str:
    return _sha256_id(
        "combo",
        {
            "request_sha256": request_sha256,
            "tuple_key": tuple_key,
            "context_sha256": context_sha256,
        },
    )


def _wearer_label(wearer_key: str, wearer_names: Mapping[str, str]) -> str:
    return wearer_names.get(wearer_key, wearer_key)


def _set_rows(package: Mapping[str, Any], set_names: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "set_uid": row["set_uid"],
            "name": set_names.get(row["set_uid"], row["set_uid"]),
            "count": row["count"],
        }
        for row in package["sets"]
    ]


def _packages_by_wearer(packages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {package["wearer_key"]: package for package in packages}


def _actor_projection(
    allocation: Mapping[str, Any],
    witness: Mapping[str, Any],
    actor_index: int,
    package: Mapping[str, Any],
    wearer_names: Mapping[str, str],
    set_names: Mapping[str, str],
) -> dict[str, Any]:
    wearer_key = allocation["wearer_key"]
    substats = allocation["substats"]
    stat_keys = tuple(stat["stat_key"] for stat in substats)
    if stat_keys != STAT_KEYS:
        raise ValueError("Theory full45 substat coordinates do not match theoryalloc.StatKeys")

    noncrit_quarters: dict[str, int] = {}
    total_upgrade_quarters = 0
    initial_line_units = 0
    for slot_index, slot in enumerate(SLOTS):
        lines = witness["Lines"][actor_index][slot_index]
        upgrades = witness["Upgrades"][actor_index][slot_index]
        initial_line_units += len(lines)
        for stat_index, upgrade in zip(lines, upgrades):
            quarter_units = round(float(upgrade) * 4)
            total_upgrade_quarters += quarter_units
            stat_key = stat_keys[stat_index]
            if stat_key not in CRIT_STATS:
                noncrit_quarters[stat_key] = noncrit_quarters.get(stat_key, 0) + quarter_units

    noncrit_by_stat = {
        stat_key: quarter_units / 4
        for stat_key, quarter_units in sorted(noncrit_quarters.items())
        if quarter_units
    }
    mains = {
        slot: witness["Mains"][actor_index][slot_index]
        for slot_index, slot in enumerate(SLOTS)
    }
    raw_package = _json_copy(dict(package))
    return {
        "wearer_key": wearer_key,
        "wearer_name": _wearer_label(wearer_key, wearer_names),
        "package": raw_package,
        "sets": _set_rows(package, set_names),
        "main_stats": mains,
        "table_mains": {slot: mains[slot] for slot in TABLE_SLOTS},
        "initial_line_units": initial_line_units,
        "total_upgrade_units": total_upgrade_quarters / 4,
        "total_roll_units": initial_line_units + total_upgrade_quarters / 4,
        "noncrit_upgrade_units": sum(noncrit_quarters.values()) / 4,
        "noncrit_upgrade_by_stat": noncrit_by_stat,
    }


def _option_signature(actor: Mapping[str, Any]) -> dict[str, Any]:
    package = actor["package"]
    sets = sorted(
        ({"set_uid": row["set_uid"], "count": row["count"]} for row in package["sets"]),
        key=lambda row: (row["set_uid"], row["count"]),
    )
    return {
        "wearer_key": actor["wearer_key"],
        "sets": sets,
        "table_mains": actor["table_mains"],
        "noncrit_upgrade_units": actor["noncrit_upgrade_units"],
        "noncrit_upgrade_by_stat": actor["noncrit_upgrade_by_stat"],
    }


def _actor_rows(combination: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    packages_json = _canonical_json(combination["packages"])
    uncertainty_json = _canonical_json(combination["uncertainty"])
    for actor in combination["actors"]:
        rows.append({
            "publication_state": combination["publication_state"],
            "co_leader_band": combination["co_leader_band"],
            "combination_id": combination["combination_id"],
            "tuple_key": combination["tuple_key"],
            "family_id": combination["family_id"],
            "family_formula_dps": combination["family_formula_dps"],
            "family_deficit_percent": combination["family_deficit_percent"],
            "family_refinement_level": combination["family_refinement_level"],
            "family_reason": combination["family_reason"],
            "witness_id": combination["witness_id"],
            "context_sha256": combination["context_sha256"],
            "uncertainty_json": uncertainty_json,
            "packages_json": packages_json,
            "wearer_key": actor["wearer_key"],
            "wearer_name": actor["wearer_name"],
            "sets_json": _canonical_json(actor["sets"]),
            "sands": actor["table_mains"]["sands"],
            "goblet": actor["table_mains"]["goblet"],
            "circlet": actor["table_mains"]["circlet"],
            "initial_line_units": actor["initial_line_units"],
            "total_upgrade_units": actor["total_upgrade_units"],
            "total_roll_units": actor["total_roll_units"],
            "noncrit_upgrade_units": actor["noncrit_upgrade_units"],
            "noncrit_upgrade_by_stat_json": _canonical_json(actor["noncrit_upgrade_by_stat"]),
        })
    return rows


def _unavailable_actor_rows(
    row: Mapping[str, Any],
    request_sha256: str,
    wearer_names: Mapping[str, str],
    set_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    packages = row["packages"]
    packages_json = _canonical_json(packages)
    reasons_json = _canonical_json(row["reasons"])
    by_wearer = _packages_by_wearer(packages)
    rows = []
    for package in packages:
        wearer_key = package["wearer_key"]
        rows.append({
            "publication_state": "unavailable",
            "co_leader_band": None,
            "combination_id": _combo_id(request_sha256, row["tuple_key"], ""),
            "tuple_key": row["tuple_key"],
            "family_id": "",
            "family_formula_dps": "",
            "family_deficit_percent": "",
            "family_refinement_level": "",
            "family_reason": reasons_json,
            "witness_id": "",
            "context_sha256": "",
            "uncertainty_json": reasons_json,
            "packages_json": packages_json,
            "wearer_key": wearer_key,
            "wearer_name": _wearer_label(wearer_key, wearer_names),
            "sets_json": _canonical_json(_set_rows(package, set_names)),
            "sands": "",
            "goblet": "",
            "circlet": "",
            "initial_line_units": "",
            "total_upgrade_units": "",
            "total_roll_units": "",
            "noncrit_upgrade_units": "",
            "noncrit_upgrade_by_stat_json": "",
        })
    return rows


def _build_grouped_options(
    combinations: list[dict[str, Any]],
    request_sha256: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for combination in combinations:
        for actor in combination["actors"]:
            signature = _option_signature(actor)
            signature_key = _canonical_json(signature)
            option = grouped.get(signature_key)
            if option is None:
                option = {
                    "option_id": _sha256_id(
                        "option",
                        {"request_sha256": request_sha256, "signature": signature},
                    ),
                    **signature,
                    "wearer_name": actor["wearer_name"],
                    "set_names": actor["sets"],
                    "combination_ids": [],
                    "publication_states": [],
                }
                grouped[signature_key] = option
            option["combination_ids"].append(combination["combination_id"])
            option["publication_states"].append(combination["publication_state"])
    output = list(grouped.values())
    for option in output:
        option["combination_ids"] = sorted(set(option["combination_ids"]))
        option["publication_states"] = sorted(set(option["publication_states"]))
    return sorted(output, key=lambda option: (option["wearer_key"], option["option_id"]))


def _roundtrip_counts(report: Mapping[str, Any]) -> dict[str, int]:
    combinations = report["combinations"]
    families = report["families"]
    witness_ids = {row["witness_id"] for row in combinations}
    return {
        "co_leader_families": sum(row["publication_state"] == "co_leader" for row in families),
        "pending_families": sum(row["publication_state"] == "pending" for row in families),
        "co_leader_combinations": sum(row["publication_state"] == "co_leader" for row in combinations),
        "pending_combinations": sum(row["publication_state"] == "pending" for row in combinations),
        "unavailable_combinations": len(report["unavailable"]),
        "actor_rows": len(report["actor_rows"]),
        "unavailable_actor_rows": len(report["unavailable_actor_rows"]),
        "unique_witnesses": len(witness_ids),
        "grouped_options": len(report["grouped_options"]),
    }


def _summary_ru(summary: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    energy_mode = context.get("energy_mode")
    energy_text = str(energy_mode) if energy_mode is not None else "не указан во входном контексте"
    prediction = context.get("prediction_status", "unverified")
    proc_facts = context.get("proc_facts")
    if proc_facts is None or proc_facts == [] or proc_facts == {}:
        proc_text = "неизвестны: связанные подтверждённые факты не переданы"
    elif isinstance(proc_facts, Mapping) and proc_facts.get("status") == "unknown":
        proc_text = f"неизвестны по переданному контексту: {_canonical_json(proc_facts)}"
    else:
        proc_text = _canonical_json(proc_facts)
    return "\n".join((
        f"Команда: {summary['team_key']}",
        f"Фаза: {summary['phase']}; найдено полных co-leader комбинаций: {summary['co_leader_combinations']}; семейств: {summary['co_leader_families']}.",
        f"Ширина группы: {summary['practical_band_percent']}%; чувствительность {summary['sensitivity_band_percent']}%: {summary['sensitivity_group_families']} семейств / {summary['sensitivity_group_tuples']} комбинаций.",
        f"Ожидают уточнения: {summary['pending_families']} семейств / {summary['pending_combinations']} комбинаций; недоступны: {summary['unavailable_combinations']}; невидимые: {summary['unseen_tuples']} из {summary['domain_tuples']}.",
        f"Покрытие всего домена: {summary['full_cartesian_covered']}; режим энергии: {energy_text}; проверка прогнозного score: {prediction}; формульный score не является подтверждённым DPS GCSim.",
        f"Групп вариантов персонажа: {summary['grouped_options']} (по персонажам: {_canonical_json(summary['grouped_options_by_wearer'])}); proc-факты: {proc_text}.",
        "Roll units — условные четвертные единицы модели; физические вероятности роллов не моделируются.",
    ))


def build_theory_full_output(
    snapshot: Mapping[str, Any],
    *,
    team_key: str,
    wearer_names: Mapping[str, str],
    set_names: Mapping[str, str] | None = None,
    public_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build complete aliases, exact wearer rows and explicit option memberships.

    ``wearer_names`` and ``set_names`` are caller-supplied display catalogs.
    Missing entries retain the exact wire key/UID. ``public_context`` is copied
    through verbatim for bound energy, prediction and sourced proc facts.
    """
    if not isinstance(team_key, str) or not team_key:
        raise ValueError("team_key must be a nonempty string")
    if not isinstance(wearer_names, Mapping):
        raise TypeError("wearer_names must be a mapping")
    wearer_names = _json_copy(dict(wearer_names))
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in wearer_names.items()):
        raise TypeError("wearer_names keys and labels must be strings")
    if set_names is None:
        set_names = {}
    elif not isinstance(set_names, Mapping):
        raise TypeError("set_names must be a mapping")
    set_names = _json_copy(dict(set_names))
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in set_names.items()):
        raise TypeError("set_names keys and labels must be strings")
    if not isinstance(public_context, Mapping):
        if public_context is not None:
            raise TypeError("public_context must be a mapping")
        public_context = {}
    context = _json_copy(dict(public_context))

    # The existing transport validator owns v2 schema, tuple ownership and
    # full45 witness validation. Keep this projection downstream of that seam.
    source = copy_theory_snapshot(snapshot)
    request_sha256 = source["request_sha256"]
    source_snapshot_sha256 = hashlib.sha256(_canonical_json(source).encode("utf-8")).hexdigest()
    combinations: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    actor_rows: list[dict[str, Any]] = []

    for section in ("co_leaders", "pending"):
        publication_state = "co_leader" if section == "co_leaders" else "pending"
        for source_family in source[section]:
            witness_payload = {
                "allocations": source_family["allocations"],
                "witness45": source_family["witness45"],
            }
            witness_id = _sha256_id("witness", witness_payload)
            family_combo_ids: list[str] = []
            for source_alias in source_family["aliases"]:
                packages = _json_copy(source_alias["packages"])
                package_by_wearer = _packages_by_wearer(packages)
                combo_id = _combo_id(
                    request_sha256,
                    source_alias["tuple_key"],
                    source_alias["context_sha256"],
                )
                actors = [
                    _actor_projection(
                        allocation,
                        source_family["witness45"],
                        actor_index,
                        package_by_wearer[allocation["wearer_key"]],
                        wearer_names,
                        set_names,
                    )
                    for actor_index, allocation in enumerate(source_family["allocations"])
                ]
                combination = {
                    "publication_state": publication_state,
                    "co_leader_band": True if publication_state == "co_leader" else None,
                    "combination_id": combo_id,
                    "tuple_key": source_alias["tuple_key"],
                    "family_id": source_family["family"],
                    "family_formula_dps": source_family["formula_dps"],
                    "family_deficit_percent": source_family["deficit_percent"],
                    "family_refinement_level": source_family["refinement_level"],
                    "family_reason": source_family.get("reason"),
                    "witness_id": witness_id,
                    "context_sha256": source_alias["context_sha256"],
                    "uncertainty": _json_copy(source_alias["uncertainty"]),
                    "packages": packages,
                    "source_alias": _json_copy(source_alias),
                    "actors": actors,
                }
                combinations.append(combination)
                family_combo_ids.append(combo_id)
                actor_rows.extend(_actor_rows(combination))
            families.append({
                "publication_state": publication_state,
                "co_leader_band": True if publication_state == "co_leader" else None,
                "family_id": source_family["family"],
                "formula_dps": source_family["formula_dps"],
                "deficit_percent": source_family["deficit_percent"],
                "refinement_level": source_family["refinement_level"],
                "reason": source_family.get("reason"),
                "witness_id": witness_id,
                "combination_ids": family_combo_ids,
                "source_family": _json_copy(source_family),
            })

    unavailable = _json_copy(source["unavailable"])
    unavailable_actor_rows: list[dict[str, Any]] = []
    for row in unavailable:
        unavailable_actor_rows.extend(
            _unavailable_actor_rows(row, request_sha256, wearer_names, set_names)
        )

    grouped_options = _build_grouped_options(combinations, request_sha256)
    grouped_options_by_wearer: dict[str, int] = {}
    for option in grouped_options:
        wearer = option["wearer_key"]
        grouped_options_by_wearer[wearer] = grouped_options_by_wearer.get(wearer, 0) + 1

    summary = {
        "team_key": team_key,
        "phase": source["phase"],
        "snapshot_version": source["snapshot_version"],
        "reference_score": source["reference_score"],
        "practical_band_percent": source["practical_band_percent"],
        "sensitivity_band_percent": source["sensitivity_band_percent"],
        "total_found_families": source["total_found_families"],
        "total_found_tuples": source["total_found_tuples"],
        "co_leader_families": source["found_group_families"],
        "co_leader_combinations": source["found_group_tuples"],
        "sensitivity_group_families": source["sensitivity_group_families"],
        "sensitivity_group_tuples": source["sensitivity_group_tuples"],
        "pending_families": len(source["pending"]),
        "pending_combinations": sum(len(row["aliases"]) for row in source["pending"]),
        "unavailable_combinations": len(unavailable),
        "domain_tuples": source["domain_tuples"],
        "unseen_tuples": source["unseen_tuples"],
        "full_cartesian_covered": source["full_cartesian_covered"],
        "grouped_options": len(grouped_options),
        "grouped_options_by_wearer": grouped_options_by_wearer,
        "energy_mode": context.get("energy_mode"),
        "prediction_status": context.get("prediction_status", "unverified"),
        "proc_facts": context.get("proc_facts"),
    }
    report = {
        "schema_version": 1,
        "schema_kind": SCHEMA_KIND,
        "team_key": team_key,
        "identity": {
            key: source[key]
            for key in (
                "request_sha256", "session_id", "snapshot_version", "phase",
                "schema_version", "schema_kind", "status",
            )
        },
        "source_snapshot_sha256": source_snapshot_sha256,
        "source_snapshot": source,
        "public_context": context,
        "summary": summary,
        "summary_ru": _summary_ru(summary, context),
        "families": families,
        "combinations": combinations,
        "unavailable": unavailable,
        "actor_rows": actor_rows,
        "unavailable_actor_rows": unavailable_actor_rows,
        "grouped_options": grouped_options,
        "roundtrip_counts": {},
    }
    report["roundtrip_counts"] = _roundtrip_counts(report)
    return report


CSV_FIELDS = (
    "publication_state", "co_leader_band", "combination_id", "tuple_key",
    "family_id", "family_formula_dps", "family_deficit_percent",
    "family_refinement_level", "family_reason", "witness_id",
    "context_sha256", "uncertainty_json", "packages_json", "wearer_key",
    "wearer_name", "sets_json", "sands", "goblet", "circlet",
    "initial_line_units", "total_upgrade_units", "total_roll_units", "noncrit_upgrade_units",
    "noncrit_upgrade_by_stat_json",
)

GROUPED_OPTION_TSV_FIELDS = (
    "option_id", "wearer_key", "wearer_name", "sets_json", "sands",
    "goblet", "circlet", "noncrit_upgrade_units",
    "noncrit_upgrade_by_stat_json", "combination_ids_json",
    "publication_states_json",
)


def _render_delimited(rows: list[Mapping[str, Any]], fields: tuple[str, ...], delimiter: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def render_theory_full_output(report: Mapping[str, Any]) -> dict[str, str]:
    """Return deterministic JSON, long-form CSV, grouped TSV and Russian summary."""
    payload = _json_copy(dict(report))
    expected_counts = _roundtrip_counts(payload)
    payload["roundtrip_counts"] = expected_counts
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    parsed = json.loads(json_text)
    actual_counts = _roundtrip_counts(parsed)
    if actual_counts != expected_counts:
        raise ValueError("Theory full-output JSON round trip changed row counts")

    csv_rows = payload["actor_rows"] + payload["unavailable_actor_rows"]
    grouped_rows = [
        {
            "option_id": row["option_id"],
            "wearer_key": row["wearer_key"],
            "wearer_name": row["wearer_name"],
            "sets_json": _canonical_json(row["set_names"]),
            "sands": row["table_mains"]["sands"],
            "goblet": row["table_mains"]["goblet"],
            "circlet": row["table_mains"]["circlet"],
            "noncrit_upgrade_units": row["noncrit_upgrade_units"],
            "noncrit_upgrade_by_stat_json": _canonical_json(row["noncrit_upgrade_by_stat"]),
            "combination_ids_json": _canonical_json(row["combination_ids"]),
            "publication_states_json": _canonical_json(row["publication_states"]),
        }
        for row in payload["grouped_options"]
    ]
    return {
        "json": json_text,
        "csv": _render_delimited(csv_rows, CSV_FIELDS, ","),
        "grouped_options_tsv": _render_delimited(grouped_rows, GROUPED_OPTION_TSV_FIELDS, "\t"),
        "summary_ru": payload["summary_ru"],
    }


__all__ = [
    "SCHEMA_KIND",
    "STAT_KEYS",
    "build_theory_full_output",
    "render_theory_full_output",
]
