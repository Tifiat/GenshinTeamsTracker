"""Compare installed and source-built Selected consumers on one captured input.

Source-only gate harness: prepare one real Selected request and compact IR,
then feed byte-identical copies to the installed and candidate consumers. Run
only through tools/managed_optimizer_experiment.py; all raw files stay in that
owned job and are removed by its outer cleanup. This is not product acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
CASES = ("flins_jahoda_selected_infinite", "bloom_selected_infinite")
SLOT_ORDER = {"flower": 0, "plume": 1, "sands": 2, "goblet": 3, "circlet": 4}


def _owned_job() -> Path:
    raw = os.environ.get("GTT_SCRATCH_DIR")
    if not raw:
        raise RuntimeError("Run inside tools/managed_optimizer_experiment.py")
    job = Path(raw).resolve(strict=True)
    managed_root = (ROOT / ".codex_tmp/managed-optimizer").resolve(strict=True)
    if job.parent != managed_root or not job.name.startswith("job-"):
        raise ValueError("GTT_SCRATCH_DIR is not an owned managed job")
    return job


@contextmanager
def _scratch_environment(job: Path):
    temporary = job / "temp"
    temporary.mkdir(exist_ok=True)
    keys = ("GTT_SCRATCH_DIR", "TMP", "TEMP")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(GTT_SCRATCH_DIR=str(job), TMP=str(temporary), TEMP=str(temporary))
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _inside_root(value: str | Path) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    resolved.relative_to(ROOT)
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_sha256(path: Path) -> str:
    """Hash a read-only SQLite backup, including committed WAL state."""
    source_uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True, timeout=5.0)) as source, closing(
        sqlite3.connect(":memory:")
    ) as snapshot:
        source.execute("PRAGMA query_only = ON")
        source.backup(snapshot)
        digest = hashlib.sha256()
        for statement in snapshot.iterdump():
            digest.update(statement.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()


def _account_team_readonly(db_path: Path, names: list[str]) -> dict[str, Any]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT character_id, catalog_english_name FROM account_characters "
            "WHERE catalog_english_name IS NOT NULL ORDER BY character_id"
        ).fetchall()
    by_name: dict[str, sqlite3.Row] = {}
    for row in rows:
        by_name.setdefault(str(row["catalog_english_name"]).casefold(), row)
    slots = []
    for index, name in enumerate(names):
        record = by_name.get(str(name).casefold())
        if record is None:
            raise ValueError(f"Account character is missing: {name}")
        slots.append({
            "slot_index": index,
            "character": {
                "id": int(record["character_id"]),
                "name": str(record["catalog_english_name"]),
            },
        })
    if len(slots) != 4 or len({row["character"]["id"] for row in slots}) != 4:
        raise ValueError("Selected case must resolve to four distinct account characters")
    return {"slot_count": 4, "slots": slots}


def _copy_account_database(source: Path, destination: Path) -> Path:
    source_uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True, timeout=5.0)) as source_conn, closing(
        sqlite3.connect(destination)
    ) as destination_conn:
        source_conn.execute("PRAGMA query_only = ON")
        source_conn.backup(destination_conn)
    return destination


def _copy_bloom_database(source: Path, job: Path) -> Path:
    from hoyolab_export.account_equipment import equip_weapon

    destination = _copy_account_database(source, job / "account-kuki-dark-iron.db")
    with closing(sqlite3.connect(destination)) as destination_conn:
        destination_conn.row_factory = sqlite3.Row
        row = destination_conn.execute(
            """SELECT weapon_fingerprint FROM account_weapon_observed_stacks
               WHERE gcsim_weapon_key = 'darkironsword' AND level = 90 AND refinement = 2
               ORDER BY id LIMIT 1"""
        ).fetchone()
        if row is None:
            raise ValueError("Approved Dark Iron Sword 90 R2 is missing from account copy")
        equip_weapon(destination_conn, 10000065, str(row[0]))
        destination_conn.commit()
    return destination


def _matrix_equipment_fixture(database: Path, job: Path, case: str) -> dict[str, Any]:
    """Use a recorded legal full team only on the disposable account copy.

    This does not restore old inventory or claim the current equipped team is
    unchanged from that matrix. Both consumers see today's inventory and the
    same explicit fixed-package test setup.
    """
    from hoyolab_export.account_equipment import equip_artifact

    database.resolve(strict=True).relative_to(job.resolve(strict=True))
    matrix_case = {
        "flins_jahoda_selected_infinite": "lunar_charged_all_sets",
        "bloom_selected_infinite": "lunar_bloom_all_sets",
    }[case]
    path = ROOT / "docs/optimizer-evidence/all-sets-inventory-20260919/after.json"
    matrix = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for row in matrix["runs"] if row.get("id") == matrix_case and row.get("success")]
    row = max(rows, key=lambda item: int(item["attempt"]))
    top = next(item for item in row["product"]["candidates"] if item["rank"] == 1)
    builds = {item["wearer_key"]: item["artifact_ids"] for item in top["builds"]}
    ids = [int(value) for slots in builds.values() for value in slots.values()]
    if len(builds) != 4 or len(ids) != 20 or len(set(ids)) != 20 or any(set(slots) != set(SLOT_ORDER) for slots in builds.values()):
        raise ValueError("Saved matrix winner is not a legal twenty-ID fixture")
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        characters = {str(item["gcsim_character_key"]): int(item["character_id"]) for item in connection.execute(
            "SELECT character_id, gcsim_character_key FROM account_characters"
        )}
        for wearer, slots in builds.items():
            for artifact_id in slots.values():
                equip_artifact(connection, characters[wearer], int(artifact_id))
        connection.commit()
    return {
        "source": path.relative_to(ROOT).as_posix(), "matrix_case": matrix_case,
        "attempt": row["attempt"], "rank": 1, "artifact_ids": builds,
        "source_row_sha256": hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "scope": "scratch_equipment_only_current_inventory_and_account_character_profiles",
    }


def _engine_identity(loader) -> dict[str, str]:
    context = loader()
    return {
        "engine_id": context.engine_id,
        "artifact_sha256": context.artifact_sha256,
        "engine_tree_sha256": context.engine_tree_sha256,
        "binding_sha256": context.binding_sha256,
    }


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flat_ints(value: Any) -> list[int]:
    if isinstance(value, list):
        output: list[int] = []
        for item in value:
            output.extend(_flat_ints(item))
        return output
    if type(value) is int:
        return [value]
    return []


def _initial_measurement(wrapper: Mapping[str, Any], current_ids: list[int]) -> dict[str, Any] | None:
    for stage in (wrapper.get("verification"), wrapper.get("screening")):
        candidates = stage.get("candidates") if isinstance(stage, Mapping) else None
        for row in (candidates if isinstance(candidates, list) else ()):
            if sorted(_flat_ints(row.get("assignment"))) != current_ids:
                continue
            return {
                "dps": _float(row.get("measured_dps")),
                "standard_error": _float(row.get("standard_error")),
                "iterations": row.get("iterations"),
            }
    return None


def _top_three(product: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = product.get("candidates")
    output = []
    for row in (rows[:3] if isinstance(rows, list) else ()):
        assignments: dict[str, dict[str, int]] = {}
        for item in row.get("artifacts") or ():
            if not isinstance(item, Mapping):
                continue
            wearer = str(item.get("wearer_key") or "?")
            slot = str(item.get("slot") or "?")
            assignments.setdefault(wearer, {})[slot] = int(item.get("artifact_id") or 0)
        output.append({
            "rank": row.get("rank"),
            "measured": {
                "dps": _float((row.get("measured") or {}).get("dps")),
                "standard_error": _float((row.get("measured") or {}).get("standard_error")),
                "iterations": (row.get("measured") or {}).get("iterations"),
            },
            "artifact_ids": {
                wearer: dict(sorted(slots.items(), key=lambda pair: SLOT_ORDER.get(pair[0], 99)))
                for wearer, slots in sorted(assignments.items())
            },
        })
    return output


def _work_summary(wrapper: Mapping[str, Any]) -> dict[str, Any]:
    search = wrapper.get("search") if isinstance(wrapper.get("search"), Mapping) else {}
    fixed = wrapper.get("fixed_search") if isinstance(wrapper.get("fixed_search"), Mapping) else {}
    stages: dict[str, dict[str, Any]] = {}
    for row in (fixed.get("candidate_work") or ()):
        if not isinstance(row, Mapping):
            continue
        item = stages.setdefault(str(row.get("stage") or "?"), {"records": 0, "expanded": 0, "stops": {}})
        item["records"] += 1
        item["expanded"] += int(row.get("expanded") or 0)
        stop = str(row.get("stop") or "not_reported")
        item["stops"][stop] = item["stops"].get(stop, 0) + 1
    stabilization = []
    for row in (fixed.get("stabilization") or ()):
        if isinstance(row, Mapping):
            stabilization.append({
                "stop": row.get("stop"),
                "evaluations": row.get("evaluations"),
                "accepted": row.get("accepted"),
                "single_stationary": row.get("single_stationary"),
            })
    steps = search.get("steps") if isinstance(search.get("steps"), list) else []
    return {
        "algorithm": fixed.get("algorithm") or "legacy_fgb_s",
        "stop": search.get("stop_reason") or "not_reported",
        "evaluations": fixed.get("evaluations"),
        "work_limit": fixed.get("work_limit"),
        "candidate_work": stages,
        "legacy_step_expanded": sum(int(row.get("expanded") or 0) for row in steps if isinstance(row, Mapping)),
        "pair_evaluated": search.get("pair_evaluated"),
        "stabilization": stabilization,
    }


def _ordinary_work(wrapper: Mapping[str, Any]) -> dict[str, int]:
    screening = wrapper.get("screening") if isinstance(wrapper.get("screening"), Mapping) else {}
    verification = wrapper.get("verification") if isinstance(wrapper.get("verification"), Mapping) else {}
    screened = screening.get("candidates") if isinstance(screening.get("candidates"), list) else []
    checked = verification.get("candidates") if isinstance(verification.get("candidates"), list) else []
    adaptive = verification.get("adaptive") if isinstance(verification.get("adaptive"), Mapping) else {}
    extension_ids = adaptive.get("extended_assignment_sha256")
    extension_count = len(extension_ids) if isinstance(extension_ids, list) else 0
    rows = screened + checked
    return {
        "calls": len(screened) + len(checked) + extension_count,
        "iterations": (
            sum(int(row.get("iterations") or 0) for row in rows if isinstance(row, Mapping))
            + extension_count * int(adaptive.get("base_iterations") or 0)
        ),
    }


def _consumer_receipt(label: str, wrapper: Mapping[str, Any], *, current_ids: list[int], wall_ms: int, preflight_ms: int) -> dict[str, Any]:
    product = wrapper.get("product_result") if isinstance(wrapper.get("product_result"), Mapping) else {}
    verification = wrapper.get("verification") if isinstance(wrapper.get("verification"), Mapping) else {}
    measured = product.get("measured") if isinstance(product.get("measured"), Mapping) else {}
    initial = _initial_measurement(wrapper, current_ids)
    return {
        "consumer": label,
        "timing_ms": {
            "preflight": preflight_ms,
            "optimizer_process": wall_ms,
            "compile": wrapper.get("compile_elapsed_ms"),
            "search": wrapper.get("search_elapsed_ms"),
            "screening": (wrapper.get("screening") or {}).get("total_elapsed_ms") if isinstance(wrapper.get("screening"), Mapping) else None,
            "verification": verification.get("total_elapsed_ms"),
            "reported_total": wrapper.get("total_elapsed_ms"),
        },
        "initial": initial,
        "winner": {
            "dps": _float(measured.get("dps")),
            "standard_error": _float(measured.get("standard_error")),
            "iterations": measured.get("iterations"),
        },
        "top3": _top_three(product),
        "algorithm": _work_summary(wrapper),
        "verification_policy": wrapper.get("verification_policy") or "not_reported",
        "ordinary": _ordinary_work(wrapper),
    }


def _validate_all_wrapper(wrapper: Mapping[str, Any], request_sha: str, label: str) -> None:
    product = wrapper.get("product_result")
    if (wrapper.get("mode") != "all" or not isinstance(product, Mapping)
            or product.get("request_sha256") != request_sha):
        raise RuntimeError(f"{label} output identity does not match the common verify-fgbs all request")


def installed_smoke(case: str = CASES[0]) -> int:
    """One complete application session using the default installed path.

    Final install gate, not another paired comparison or matrix attempt. Raw
    captures and the explicit fixture copy remain in the outer managed job.
    """
    job = _owned_job()
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_selected import (
        DEFAULT_OPTIMIZER_BINARY, GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession,
    )

    manifest = json.loads((ROOT / "tools/experiments/gcsim/mode_matrix/manifest_v1.json").read_text(encoding="utf-8"))
    entry = next(row for row in manifest["runs"] if row["id"] == case and row["mode"] == "selected")
    source = _inside_root(manifest["db_path"])
    live_before = _database_sha256(source)
    copy = (_copy_bloom_database(source, job) if entry.get("database_variant") == "kuki_dark_iron_test_copy"
            else _copy_account_database(source, job / "account-selected-smoke.db"))
    fixture = _matrix_equipment_fixture(copy, job, case)
    copy_before = _database_sha256(copy)
    engine = _engine_identity(load_active_gcsim_optimizer_engine_context)
    binary = Path(DEFAULT_OPTIMIZER_BINARY)
    binary_sha = _sha256_file(binary)
    rotation = _inside_root(entry["rotation_file"])
    rotation_sha = _sha256_file(rotation)
    request = GcsimOptimizerGoSelectedRequest(
        db_path=str(copy), selected_team=_account_team_readonly(copy, list(entry["characters"])),
        team_index=0, rotation_shell_text=rotation.read_text(encoding="utf-8"),
        infinite_energy_enabled=True, expected_engine_id=engine["engine_id"],
        run_root=str(job / "installed-product-runs"),
        # Deliberately no optimizer_binary_path override: the button's default.
    )
    with _scratch_environment(job):
        outcome = GcsimOptimizerGoSelectedSession(request).run()
    if (live_before != _database_sha256(source) or copy_before != _database_sha256(copy)
            or engine != _engine_identity(load_active_gcsim_optimizer_engine_context)
            or binary_sha != _sha256_file(binary) or rotation_sha != _sha256_file(rotation)):
        raise RuntimeError("Installed Selected smoke changed an input or installed identity")
    if not outcome.get("success"):
        print(json.dumps({key: outcome.get(key) for key in ("success", "error_code", "error", "adapter_timings")}), flush=True)
        return 1
    run_dir = Path(outcome["run_dir"])
    run_dir.resolve().relative_to(job)
    wrapper = json.loads((run_dir / "optimizer-output.json").read_text(encoding="utf-8"))
    prepared = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    _validate_all_wrapper(wrapper, outcome["request_sha256"], "installed")
    if wrapper.get("verification_policy") != "single_n500" or wrapper.get("screening") is not None:
        raise RuntimeError("Installed Selected did not use the new single-stage route")
    current_ids = sorted(int(a["artifact_id"]) for wearer in prepared["wearers"] for a in wearer["current_artifacts"])
    timings = outcome["adapter_timings"]
    print(json.dumps({
        "schema_kind": "gtt_selected_installed_session_gate_v1", "case": case,
        "success": True, "default_installed_path": str(binary), "optimizer_sha256": binary_sha,
        "engine": engine, "equipment_fixture": fixture, "request_sha256": outcome["request_sha256"],
        "adapter_timings": timings, "elapsed_ms": outcome["elapsed_ms"],
        "inputs_and_installed_identities_unchanged": True,
        "consumer": _consumer_receipt("installed", wrapper, current_ids=current_ids,
            wall_ms=int(timings["optimizer_process_ms"]), preflight_ms=int(timings["request_preflight_ms"])),
    }, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


def main() -> int:
    job = _owned_job()  # fail before importing account or engine modules
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-binary", type=Path, required=True)
    parser.add_argument("--case", choices=CASES, default=CASES[0])
    parser.add_argument("--matrix-equipment", action="store_true",
                        help="Equip the recorded matrix winner on a disposable DB copy only")
    args = parser.parse_args()
    candidate_binary = args.candidate_binary.resolve(strict=True)
    candidate_binary.relative_to(job)
    if not candidate_binary.is_file():
        raise ValueError("Candidate optimizer binary is not a file")

    sys.dont_write_bytecode = True
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_selected import (
        DEFAULT_OPTIMIZER_BINARY,
        GcsimOptimizerGoSelectedRequest,
        GcsimOptimizerGoSelectedSession,
        _prepare_inputs,
    )
    from run_workspace.gcsim.optimizer_artifact_database import load_gcsim_optimizer_artifact_database_input
    from run_workspace.gcsim.optimizer_go_selected_inputs import load_selected_equipped_team_snapshot

    manifest_path = ROOT / "tools/experiments/gcsim/mode_matrix/manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((row for row in manifest.get("runs", ()) if row.get("id") == args.case), None)
    if not isinstance(entry, Mapping) or entry.get("mode") != "selected":
        raise ValueError(f"Selected case is absent from the mode manifest: {args.case}")
    if not bool(entry.get("infinite_energy", True)):
        raise ValueError("This comparison harness is limited to infinite-energy Selected")
    source_db = _inside_root(str(manifest.get("db_path") or "data/artifacts.db"))
    source_db_before = _database_sha256(source_db)
    entry_db = _copy_bloom_database(source_db, job) if entry.get("database_variant") == "kuki_dark_iron_test_copy" else source_db
    equipment_fixture = None
    if args.matrix_equipment:
        if entry_db == source_db:
            entry_db = _copy_account_database(source_db, job / "account-matrix-equipment.db")
        equipment_fixture = _matrix_equipment_fixture(entry_db, job, args.case)
    case_db_before = _database_sha256(entry_db)
    engine_before = _engine_identity(load_active_gcsim_optimizer_engine_context)

    installed_binary = Path(DEFAULT_OPTIMIZER_BINARY).resolve(strict=True)
    if installed_binary == candidate_binary:
        raise ValueError("Candidate must be source-built in this job, not the installed executable")
    binaries_before = {
        "installed": _sha256_file(installed_binary),
        "candidate": _sha256_file(candidate_binary),
    }
    selected_team = _account_team_readonly(entry_db, list(entry["characters"]))
    rotation_path = _inside_root(str(entry["rotation_file"]))
    rotation_source_sha256 = _sha256_file(rotation_path)
    request = GcsimOptimizerGoSelectedRequest(
        db_path=str(entry_db),
        selected_team=selected_team,
        team_index=0,
        rotation_shell_text=rotation_path.read_text(encoding="utf-8"),
        infinite_energy_enabled=True,
        expected_engine_id=engine_before["engine_id"],
        optimizer_binary_path=str(installed_binary),
        run_root=str(job / "product-runs"),
    )
    candidate_request = replace(request, optimizer_binary_path=str(candidate_binary))
    installed_session = GcsimOptimizerGoSelectedSession(request)
    candidate_session = GcsimOptimizerGoSelectedSession(candidate_request)

    with _scratch_environment(job):
        capture_dir = job / "shared-capture"
        capture_dir.mkdir()
        started = time.monotonic()
        prepared = _prepare_inputs(
            request,
            capture_dir,
            virtual_artifact_policy=installed_session.virtual_artifact_policy,
        )
        prepare_ms = int((time.monotonic() - started) * 1000)
        if prepared["request"]["engine"]["artifact_sha256"] != engine_before["artifact_sha256"]:
            raise RuntimeError("Active GCSIM engine changed during request preparation")
        current_ids = sorted(
            int(item["artifact_id"])
            for wearer in prepared["request"]["wearers"]
            for item in wearer["current_artifacts"]
        )
        if len(current_ids) != 20 or len(set(current_ids)) != 20:
            raise ValueError("Prepared Selected input does not contain twenty unique current artifacts")
        actual_2p2 = None
        if args.case == "bloom_selected_infinite":
            lauma = next((row for row in prepared["request"]["wearers"] if row.get("wearer_key") == "lauma"), None)
            packages = lauma.get("selected_sets") if isinstance(lauma, Mapping) else None
            if not isinstance(packages, list) or len(packages) != 2 or sorted(int(row.get("count") or 0) for row in packages) != [2, 2]:
                raise ValueError("Current Selected request does not contain Lauma's actual two distinct 2-piece packages")
            if len({str(row.get("set_uid") or "") for row in packages}) != 2:
                raise ValueError("Lauma's prepared 2+2 packages are not distinct")
            actual_2p2 = {
                "wearer": "lauma",
                "sets": sorted(
                    [
                        {"set_uid": str(row["set_uid"]), "count": int(row["count"])}
                        for row in packages
                    ],
                    key=lambda row: row["set_uid"],
                ),
                "current_artifact_ids": sorted(int(row["artifact_id"]) for row in lauma["current_artifacts"]),
            }

        request_bytes = (capture_dir / "request.json").read_bytes()
        request_sha = prepared["request_sha256"]
        contexts = prepared["request"]["context"]
        guard = {
            "request_sha256": request_sha,
            "prepared_config_sha256": contexts["prepared_config"]["sha256"],
            "rotation_sha256": contexts["rotation"]["sha256"],
            "target_sha256": contexts["target"]["sha256"],
            "trace_context_sha256": contexts["trace_context_sha256"],
            "snapshot_sha256": prepared["snapshot"].snapshot_sha256,
            "equipment_rows_sha256": prepared["snapshot"].equipment_rows_sha256,
            "artifact_inventory_sha256": prepared["snapshot"].artifact_database_input_sha256,
        }

        consumers = (
            ("installed", installed_session),
            ("candidate", candidate_session),
        )
        run_dirs = {label: job / f"consumer-{label}" for label, _ in consumers}
        for label, run_dir in run_dirs.items():
            run_dir.mkdir()
            (run_dir / "request.json").write_bytes(request_bytes)
        preflight_ms: dict[str, int] = {}
        for label, session in consumers:
            started = time.monotonic()
            session._validate_optimizer_request(run_dir=run_dirs[label], started=started)
            preflight_ms[label] = int((time.monotonic() - started) * 1000)

        started = time.monotonic()
        compact = installed_session._prepare_formula_inputs(
            prepared=prepared,
            run_dir=capture_dir,
            started=started,
        )
        capture_ms = int((time.monotonic() - started) * 1000)
        compact_bytes = (capture_dir / "compact.json").read_bytes()
        compact_sha = hashlib.sha256(compact_bytes).hexdigest()
        if compact.get("request_sha256") != request_sha:
            raise RuntimeError("Compact IR is not bound to the prepared request")
        for run_dir in run_dirs.values():
            (run_dir / "compact.json").write_bytes(compact_bytes)

        outputs: dict[str, dict[str, Any]] = {}
        consumer_times: dict[str, int] = {}
        for label, session in consumers:
            started = time.monotonic()
            session._run_go_optimizer(
                prepared=prepared,
                compact=compact,
                run_dir=run_dirs[label],
                started=started,
            )
            consumer_times[label] = int((time.monotonic() - started) * 1000)
            wrapper = json.loads((run_dirs[label] / "optimizer-output.json").read_text(encoding="utf-8"))
            _validate_all_wrapper(wrapper, request_sha, label)
            outputs[label] = _consumer_receipt(
                label, wrapper, current_ids=current_ids,
                wall_ms=consumer_times[label], preflight_ms=preflight_ms[label],
            )
            outputs[label]["_wrapper"] = wrapper

        candidate_wrapper = outputs["candidate"].pop("_wrapper")
        outputs["installed"].pop("_wrapper")
        if (candidate_wrapper.get("fixed_search") is None
                or candidate_wrapper.get("verification_policy") != "single_n500"
                or candidate_wrapper.get("screening") is not None):
            raise RuntimeError("Candidate did not exercise the expected fixed Selected single_n500 route")
        if (capture_dir / "request.json").read_bytes() != request_bytes or (capture_dir / "compact.json").read_bytes() != compact_bytes:
            raise RuntimeError("Shared request or compact IR changed during comparison")
        for run_dir in run_dirs.values():
            if (run_dir / "request.json").read_bytes() != request_bytes or (run_dir / "compact.json").read_bytes() != compact_bytes:
                raise RuntimeError("A consumer did not retain byte-identical request and compact IR")

    # Recheck all live inputs and executable identities after the consumers exit.
    engine_after = _engine_identity(load_active_gcsim_optimizer_engine_context)
    loaded_after = load_gcsim_optimizer_artifact_database_input(entry_db, engine_context=load_active_gcsim_optimizer_engine_context())
    if not loaded_after.ready or loaded_after.database_input is None:
        raise RuntimeError(f"Post-run artifact inventory is not ready: {loaded_after.issues!r}")
    snapshot_after = load_selected_equipped_team_snapshot(
        entry_db,
        artifact_database=loaded_after.database_input,
        character_keys=tuple(prepared["snapshot"].character_keys),
    )
    binaries_after = {
        "installed": _sha256_file(installed_binary),
        "candidate": _sha256_file(candidate_binary),
    }
    source_db_after = _database_sha256(source_db)
    case_db_after = _database_sha256(entry_db)
    rotation_source_after = _sha256_file(rotation_path)
    if engine_after != engine_before:
        raise RuntimeError("Active GCSIM engine identity changed during comparison")
    if binaries_after != binaries_before:
        raise RuntimeError("An optimizer executable changed during comparison")
    if source_db_after != source_db_before or case_db_after != case_db_before:
        raise RuntimeError("Live database or scratch input copy changed during comparison")
    if rotation_source_after != rotation_source_sha256:
        raise RuntimeError("Selected rotation source changed during comparison")
    if loaded_after.database_input.artifact_database_input_sha256 != prepared["snapshot"].artifact_database_input_sha256:
        raise RuntimeError("Artifact inventory changed during comparison")
    if (snapshot_after.snapshot_sha256 != prepared["snapshot"].snapshot_sha256
            or snapshot_after.equipment_rows_sha256 != prepared["snapshot"].equipment_rows_sha256):
        raise RuntimeError("Current equipped artifact snapshot changed during comparison")

    old_winner = outputs["installed"]["winner"]
    new_winner = outputs["candidate"]["winner"]
    if any(outputs[label]["initial"] is None for label in ("installed", "candidate")):
        raise RuntimeError("A consumer did not report measured DPS and SE for the current assignment")
    old_dps, new_dps = old_winner["dps"], new_winner["dps"]
    old_se, new_se = old_winner["standard_error"], new_winner["standard_error"]
    if None in (old_dps, new_dps, old_se, new_se):
        raise RuntimeError("Cannot compare consumers without measured winner DPS and standard errors")
    regression_limit = max(3.0 * math.hypot(old_se, new_se), 0.001 * abs(old_dps))
    material_regression = new_dps < old_dps - regression_limit
    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_selected_consumer_comparison_v1",
        "case": args.case,
        "comparison": "same_prepared_request_and_compact_ir",
        "identity": {
            **guard,
            "compact_sha256": compact_sha,
            "engine": engine_before,
            "installed_optimizer_sha256": binaries_before["installed"],
            "candidate_optimizer_sha256": binaries_before["candidate"],
            "database_sha256": source_db_before,
        },
        "input_checks": {
            "engine_unchanged": True,
            "inventory_unchanged": True,
            "equipment_unchanged": True,
            "database_unchanged": True,
            "optimizer_binaries_unchanged": True,
            "request_and_compact_identical": True,
            "rotation_source_unchanged": True,
        },
        "prepare_capture_ms": {"prepare_request": prepare_ms, "capture_compact_ir": capture_ms},
        "actual_2plus2": actual_2p2,
        "equipment_fixture": equipment_fixture,
        "consumers": outputs,
        "regression_check": {
            "candidate_below_installed_by": round(old_dps - new_dps, 6),
            "material_threshold": round(regression_limit, 6),
            "rule": "max(3*hypot(installed_SE,candidate_SE),0.001*abs(installed_DPS))",
            "material_regression": material_regression,
            "install_approved": False,
        },
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")), flush=True)
    return 2 if material_regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
