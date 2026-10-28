"""Exercise optimizer product sessions on account teams and export a compact receipt.

The Qt buttons and this probe both instantiate the request/session classes from
``run_workspace.gcsim``. Heavy captures stay inside ``managed_scratch`` and are
deleted on exit; only the explicitly requested compact receipt is retained.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing, contextmanager
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from hoyolab_export.account_storage import list_account_characters
from hoyolab_export.account_equipment import equip_weapon
from hoyolab_export.artifact_db import connect_db
from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest,
    GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
    _prepare_inputs,
)
from run_workspace.gcsim.optimizer_go_theory import (
    GcsimOptimizerGoTheoryRequest,
    GcsimOptimizerGoTheorySession,
)
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualSlotOverride,
    load_active_virtual_roster_catalog,
)
from tools.managed_optimizer_experiment import managed_scratch
from ui.artifact_browser.queries import list_all_artifacts


SESSION_TYPES = {
    "selected": (GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession),
    "all_sets": (GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession),
    "theory": (GcsimOptimizerGoTheoryRequest, GcsimOptimizerGoTheorySession),
}
SLOT_ORDER = {"flower": 0, "plume": 1, "sands": 2, "goblet": 3, "circlet": 4}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _resolve_inside_root(value: str | Path) -> Path:
    path = Path(value)
    path = path if path.is_absolute() else ROOT / path
    resolved = path.resolve()
    resolved.relative_to(ROOT)
    return resolved


def _account_selected_team(db_path: Path, names: list[str]) -> dict[str, Any]:
    with closing(connect_db(db_path)) as conn:
        records = list_account_characters(conn)
    by_name = {
        record.catalog_english_name.casefold(): record
        for record in records
        if record.catalog_english_name
    }
    slots: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        record = by_name.get(str(name).casefold())
        if record is None:
            raise ValueError(f"Account character is missing: {name}")
        slots.append(
            {
                "slot_index": index,
                "character": {
                    "id": record.character_id,
                    "name": record.catalog_english_name,
                },
            }
        )
    return {"slot_count": len(slots), "slots": slots}


def _virtual_selected_team(profiles: list[Mapping[str, Any]]) -> dict[str, Any]:
    catalog = load_active_virtual_roster_catalog()
    characters = {item.gcsim_key.casefold(): item for item in catalog.characters}
    weapons = {item.gcsim_key.casefold(): item for item in catalog.weapons}
    slots: list[dict[str, Any]] = []
    for index, profile in enumerate(profiles):
        character_key = str(profile.get("character_key") or "").casefold()
        weapon_key = str(profile.get("weapon_key") or "").casefold()
        character = characters.get(character_key)
        weapon = weapons.get(weapon_key)
        if character is None:
            raise ValueError(f"Active GCSIM character is missing: {character_key}")
        if weapon is None:
            raise ValueError(f"Active GCSIM weapon is missing: {weapon_key}")
        talents = tuple(int(value) for value in profile.get("talents", (9, 9, 9)))
        if len(talents) != 3:
            raise ValueError(f"Virtual profile talents must contain N/E/Q: {character_key}")
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=index,
            character_key=character.gcsim_key,
            character_name=character.display_name,
            character_weapon_type=character.weapon_type,
            character_icon_path=character.icon_path,
            weapon_key=weapon.gcsim_key,
            weapon_name=weapon.display_name,
            weapon_type=weapon.weapon_type,
            weapon_icon_path=weapon.icon_path,
            constellation=int(profile.get("constellation", 0)),
            refinement=int(profile.get("refinement", 1)),
            character_level=int(profile.get("character_level", 90)),
            talent_normal=talents[0],
            talent_skill=talents[1],
            talent_burst=talents[2],
            weapon_level=int(profile.get("weapon_level", 90)),
            weapon_promote_level=6,
        )
        slots.append(
            {
                "slot_index": index,
                "gcsim_virtual_override": override.to_dict(),
            }
        )
    return {"slot_count": len(slots), "slots": slots}


def _selected_team(db_path: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    profiles = entry.get("virtual_profiles")
    if isinstance(profiles, list) and profiles:
        return _virtual_selected_team(
            [profile for profile in profiles if isinstance(profile, Mapping)]
        )
    return _account_selected_team(db_path, list(entry["characters"]))


def _request(entry: Mapping[str, Any], *, db_path: Path, run_root: Path):
    mode = str(entry["mode"])
    request_type, _ = SESSION_TYPES[mode]
    rotation_path = _resolve_inside_root(str(entry["rotation_file"]))
    return request_type(
        db_path=str(db_path),
        selected_team=_selected_team(db_path, entry),
        team_index=0,
        rotation_shell_text=rotation_path.read_text(encoding="utf-8"),
        infinite_energy_enabled=bool(entry.get("infinite_energy", True)),
        run_root=str(run_root),
    )


def _artifact_catalog(db_path: Path) -> dict[int, Any]:
    return {artifact.id: artifact for artifact in list_all_artifacts(db_path=db_path)}


def _copied_db_with_kuki_dark_iron(source: Path, scratch: Path) -> Path:
    destination = scratch / "account-kuki-dark-iron.db"
    source_uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_conn, closing(
        sqlite3.connect(destination)
    ) as destination_conn:
        source_conn.backup(destination_conn)
        destination_conn.row_factory = sqlite3.Row
        row = destination_conn.execute(
            """
            SELECT weapon_fingerprint
            FROM account_weapon_observed_stacks
            WHERE gcsim_weapon_key = 'darkironsword'
              AND level = 90
              AND refinement = 2
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise ValueError("Approved Dark Iron Sword 90 R2 is missing from account copy")
        equip_weapon(destination_conn, 10000065, str(row[0]))
        destination_conn.commit()
    return destination


def _artifact_summary(artifact_id: int, *, catalog: Mapping[int, Any]) -> dict[str, Any]:
    artifact = catalog.get(int(artifact_id))
    if artifact is None:
        return {"artifact_id": int(artifact_id), "missing_from_display_catalog": True}
    return {
        "artifact_id": artifact.id,
        "set_uid": artifact.set_uid,
        "set_name": artifact.set_name,
        "main": f"{artifact.main_property_name} {artifact.main_property_value}",
    }


def _compact_candidate(candidate: Mapping[str, Any], *, catalog: Mapping[int, Any]) -> dict[str, Any]:
    assignments = candidate.get("artifacts")
    assignments = assignments if isinstance(assignments, list) else []
    by_wearer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            continue
        artifact = _artifact_summary(int(assignment.get("artifact_id") or 0), catalog=catalog)
        artifact["slot"] = str(assignment.get("slot") or "")
        by_wearer[str(assignment.get("wearer_key") or "?")].append(artifact)
    builds: list[dict[str, Any]] = []
    for wearer in sorted(by_wearer):
        artifacts = sorted(by_wearer[wearer], key=lambda row: SLOT_ORDER.get(str(row["slot"]), 99))
        counts = Counter(str(row.get("set_name") or row.get("set_uid") or "?") for row in artifacts)
        builds.append(
            {
                "wearer_key": wearer,
                "sets": [{"name": name, "count": count} for name, count in sorted(counts.items())],
                "main_stats": {
                    str(row["slot"]): row.get("main")
                    for row in artifacts
                    if row["slot"] in {"sands", "goblet", "circlet"}
                },
                "artifact_ids": {
                    str(row["slot"]): int(row["artifact_id"]) for row in artifacts
                },
            }
        )
    return {
        "rank": candidate.get("rank"),
        "measured": dict(candidate.get("measured") or {}),
        "formula_dps": candidate.get("formula_dps"),
        "formula_residual": candidate.get("formula_residual"),
        "builds": builds,
    }


def _compact_product(
    result: Mapping[str, Any], *, mode: str, catalog: Mapping[int, Any]
) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "status": result.get("status"),
        "schema_kind": result.get("schema_kind"),
        "warnings": list(result.get("warnings") or []),
        "coverage": dict(result.get("coverage") or {}),
        "energy": result.get("energy"),
    }
    candidates = result.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    if mode == "theory":
        compact["candidates"] = [
            {
                "rank": row.get("rank"),
                "formula_dps": row.get("formula_dps"),
                "source": row.get("source"),
                "undistinguished_set_slots": list(
                    row.get("undistinguished_set_slots") or []
                ),
                "packages": row.get("packages"),
                "allocations": row.get("allocations"),
                "opaque_reasons": row.get("opaque_reasons"),
            }
            for row in candidates[:5]
            if isinstance(row, Mapping)
        ]
    else:
        compact["candidates"] = [
            _compact_candidate(row, catalog=catalog)
            for row in candidates[:5]
            if isinstance(row, Mapping)
        ]
    return compact


def _saved_result(entry: Mapping[str, Any], *, catalog: Mapping[int, Any]) -> dict[str, Any]:
    source = _resolve_inside_root(str(entry["source_run"]))
    result_path = source / "selected-result.json"
    result = _load_json(result_path)
    adapter_path = source / "adapter-timings.json"
    return {
        "id": entry["id"],
        "mode": entry["mode"],
        "characters": list(entry["characters"]),
        "rotation_file": entry["rotation_file"],
        "infinite_energy": bool(entry.get("infinite_energy", True)),
        "database_variant": str(entry.get("database_variant") or "live_read_only"),
        "execution": "reused_saved_product_run",
        "source_run": source.name,
        "success": result.get("status") == "success",
        "adapter_timings": _load_json(adapter_path) if adapter_path.is_file() else {},
        "product": _compact_product(result, mode=str(entry["mode"]), catalog=catalog),
    }


@contextmanager
def _scratch_environment(scratch: Path):
    temporary = scratch / "temp"
    temporary.mkdir(exist_ok=True)
    keys = ("GTT_SCRATCH_DIR", "TMP", "TEMP")
    before = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        GTT_SCRATCH_DIR=str(scratch), TMP=str(temporary), TEMP=str(temporary)
    )
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_entry(
    entry: Mapping[str, Any], *, db_path: Path, scratch: Path, catalog: Mapping[int, Any]
) -> dict[str, Any]:
    mode = str(entry["mode"])
    _, session_type = SESSION_TYPES[mode]
    request = _request(entry, db_path=db_path, run_root=scratch / "runs")
    run_root = scratch / "runs"
    runs_before = {path.resolve() for path in run_root.glob("*") if path.is_dir()}
    stage = ""

    def progress(payload: dict[str, Any]) -> None:
        nonlocal stage
        current = str(payload.get("stage") or "")
        if current != stage or current in {"completed", "failed"}:
            stage = current
            print(
                f"[{entry['id']}] {current}: "
                f"{payload.get('completed_work')}/{payload.get('total_work')} "
                f"at {float(payload.get('elapsed_ms') or 0) / 1000:.1f}s",
                flush=True,
            )

    started = time.monotonic()
    payload = session_type(request, progress_callback=progress).run()
    output: dict[str, Any] = {
        "id": entry["id"],
        "mode": mode,
        "archetype": entry.get("archetype"),
        "source_url": entry.get("source_url"),
        "expected_mechanics": list(entry.get("expected_mechanics") or []),
        "characters": list(entry["characters"]),
        "rotation_file": entry["rotation_file"],
        "infinite_energy": bool(entry.get("infinite_energy", True)),
        "database_variant": str(entry.get("database_variant") or "live_read_only"),
        "execution": "live_product_session",
        "success": bool(payload.get("success")),
        "status": payload.get("status"),
        "error_code": payload.get("error_code"),
        "error": payload.get("error"),
        "wall_seconds": time.monotonic() - started,
        "elapsed_ms": payload.get("elapsed_ms"),
        "adapter_timings": dict(payload.get("adapter_timings") or {}),
    }
    result = payload.get("result")
    if isinstance(result, Mapping):
        output["product"] = _compact_product(result, mode=mode, catalog=catalog)
    runs_after = {path.resolve() for path in run_root.glob("*") if path.is_dir()}
    created = sorted(runs_after - runs_before, key=lambda path: path.stat().st_mtime_ns)
    if created:
        request_path = created[-1] / "request.json"
        if request_path.is_file():
            engine = _load_json(request_path).get("engine")
            if isinstance(engine, Mapping):
                binary = str(engine.get("binary_path") or "")
                output["engine_identity"] = {
                    "id": Path(binary).parent.parent.name if binary else "",
                    "artifact_sha256": engine.get("artifact_sha256"),
                    "patch_manifest_sha256": engine.get("patch_manifest_sha256"),
                    "source_manifest_sha256": engine.get("source_manifest_sha256"),
                }
        witness = _formula_witness(created[-1])
        if witness:
            output["formula_witness"] = witness
        proposal_witness = _theory_proposal_witness(created[-1])
        if proposal_witness:
            output["theory_proposal_witness"] = proposal_witness
    return output


def _formula_witness(run_dir: Path) -> dict[str, Any]:
    """Keep a compact proof of the actual formula channels before scratch cleanup."""

    members = sorted(run_dir.glob("**/member.json"))
    if not members:
        return {}
    member = _load_json(members[0])
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    all_coordinates: set[str] = set()
    for channel in member.get("channels", []):
        if not isinstance(channel, Mapping):
            continue
        key = (
            str(channel.get("kind") or ""),
            str(channel.get("attack_tag") or ""),
            str(channel.get("damage_type") or ""),
        )
        row = groups.setdefault(
            key,
            {
                "kind": key[0],
                "attack_tag": key[1],
                "damage_type": key[2],
                "channels": 0,
                "hits": 0,
                "baseline_damage": 0.0,
                "response_coordinates": set(),
            },
        )
        row["channels"] += 1
        row["hits"] += int(channel.get("hit_count") or 0)
        row["baseline_damage"] += float(channel.get("baseline_damage") or 0)
        coordinates = {
            str(value)
            for value in channel.get("response_coordinates", [])
            if str(value)
        }
        row["response_coordinates"].update(coordinates)
        all_coordinates.update(coordinates)
    compact_groups = []
    for key in sorted(groups):
        row = groups[key]
        compact_groups.append(
            {
                **row,
                "baseline_damage": round(float(row["baseline_damage"]), 6),
                "response_coordinates": sorted(row["response_coordinates"]),
            }
        )
    boundary_codes = sorted(
        {
            str(boundary.get("code") or boundary.get("reason") or "")
            for boundary in member.get("opaque_boundaries", [])
            if isinstance(boundary, Mapping)
            and str(boundary.get("code") or boundary.get("reason") or "")
        }
    )
    return {
        "member_path": members[0].relative_to(run_dir).as_posix(),
        "topology_sha256": member.get("topology_sha256"),
        "duration_ms": member.get("duration_ms"),
        "formula_coordinates": sorted(all_coordinates),
        "channel_groups": compact_groups,
        "opaque_boundary_codes": boundary_codes,
    }


def _theory_proposal_witness(run_dir: Path) -> dict[str, Any]:
    """Retain the bounded Theory shortlist before managed scratch is removed."""

    report = None
    for path in sorted(run_dir.glob("**/theory-result.json")):
        candidate = _load_json(path).get("proposal_report")
        if isinstance(candidate, Mapping):
            report = candidate
            break
    if report is None:
        return {}
    queue = report.get("queue")
    queue = queue if isinstance(queue, list) else []
    compact_queue: list[dict[str, Any]] = []
    for row in queue:
        if not isinstance(row, Mapping):
            continue
        package = row.get("package")
        package = package if isinstance(package, Mapping) else {}
        compact_queue.append(
            {
                "wearer_index": row.get("wearer"),
                "lane": row.get("lane"),
                "priority_not_candidate_dps": row.get(
                    "priority_not_candidate_dps"
                ),
                "sets": list(package.get("sets") or []),
            }
        )
    return {
        "packages_considered": report.get("packages_considered"),
        "unqueued": report.get("unqueued"),
        "queue": compact_queue,
    }


def _write_receipt(path: Path, manifest: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "date": date.today().isoformat(),
        "status": "measurement_only_pending_user_review",
        "scope": "same_request_and_session_classes_as_optimizer_Qt_buttons",
        "manifest": manifest.get("name"),
        "generated_state_removed_on_exit": True,
        "runs": rows,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _expanded_manifest_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    teams = manifest.get("teams")
    teams = teams if isinstance(teams, Mapping) else {}
    expanded: list[dict[str, Any]] = []
    for raw in manifest.get("runs", []):
        if not isinstance(raw, Mapping):
            continue
        team_id = str(raw.get("team") or "")
        team = teams.get(team_id, {}) if team_id else {}
        if team_id and not isinstance(team, Mapping):
            raise ValueError(f"Unknown or invalid manifest team: {team_id}")
        entry = {**dict(team), **dict(raw)}
        if "characters" not in entry and isinstance(entry.get("virtual_profiles"), list):
            entry["characters"] = [
                str(profile.get("character_key") or "")
                for profile in entry["virtual_profiles"]
                if isinstance(profile, Mapping)
            ]
        expanded.append(entry)
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--include-finite-energy",
        action="store_true",
        help="Include explicitly finite-energy rows; omitted by default while that mode is deferred.",
    )
    args = parser.parse_args()
    manifest_path = _resolve_inside_root(args.manifest)
    receipt = _resolve_inside_root(args.receipt)
    manifest = _load_json(manifest_path)
    db_path = _resolve_inside_root(str(manifest.get("db_path") or "data/artifacts.db"))
    entries = _expanded_manifest_entries(manifest)
    if not args.include_finite_energy:
        entries = [row for row in entries if bool(row.get("infinite_energy", True))]
    wanted = set(args.only)
    if wanted:
        entries = [row for row in entries if str(row.get("id")) in wanted]
        missing = wanted - {str(row.get("id")) for row in entries}
        if missing:
            raise SystemExit("Unknown run ids: " + ", ".join(sorted(missing)))
    catalog = _artifact_catalog(db_path)
    rows: list[dict[str, Any]] = []
    with managed_scratch() as scratch, _scratch_environment(scratch):
        database_variants = {
            "live_read_only": db_path,
            "kuki_dark_iron_test_copy": _copied_db_with_kuki_dark_iron(
                db_path, scratch
            ),
        }
        for entry in entries:
            print(f"Starting {entry['id']}", flush=True)
            entry_db_path = database_variants[
                str(entry.get("database_variant") or "live_read_only")
            ]
            if entry.get("source_run"):
                row = _saved_result(entry, catalog=catalog)
            elif args.preflight:
                try:
                    request = _request(
                        entry, db_path=entry_db_path, run_root=scratch / "runs"
                    )
                    preflight_dir = scratch / f"preflight-{entry['id']}"
                    preflight_dir.mkdir()
                    _, session_type = SESSION_TYPES[str(entry["mode"])]
                    prepared = _prepare_inputs(
                        request,
                        preflight_dir,
                        virtual_artifact_policy=session_type.virtual_artifact_policy,
                    )
                    row = {
                        "id": entry["id"],
                        "mode": entry["mode"],
                        "archetype": entry.get("archetype"),
                        "source_url": entry.get("source_url"),
                        "expected_mechanics": list(
                            entry.get("expected_mechanics") or []
                        ),
                        "success": True,
                        "wearers": [item["wearer_key"] for item in prepared["request"]["wearers"]],
                        "infinite_energy": bool(entry.get("infinite_energy", True)),
                        "database_variant": str(
                            entry.get("database_variant") or "live_read_only"
                        ),
                    }
                except Exception as exc:  # diagnostic boundary; continue the matrix
                    row = {
                        "id": entry["id"],
                        "mode": entry["mode"],
                        "success": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            else:
                row = _run_entry(
                    entry,
                    db_path=entry_db_path,
                    scratch=scratch,
                    catalog=catalog,
                )
            rows.append(row)
            _write_receipt(receipt, manifest, rows)
            print(f"Finished {entry['id']}: success={row.get('success')}", flush=True)
    return 0 if all(bool(row.get("success")) for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
