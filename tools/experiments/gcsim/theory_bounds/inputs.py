"""Fresh, receipt-bound virtual Theory inputs for two managed contrasts.

The old Theory receipt supplies identity checks and an explicitly named package
control only. Its allocations, formula scores, and selected layouts never enter
the prepared request.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

# The managed runner starts with -B; set this before importing project modules too.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
OWNER = ROOT / "docs/optimizer-evidence/2026-10-03-theory-current-matrix"
MANAGED = (ROOT / ".codex_tmp/managed-optimizer").resolve()
CASES = frozenset({"chiori_lunar_crystallize", "bountiful_core"})
# These two saved rank-one packages are declared comparison controls, not seeds.
SAVED_PACKAGE_CONTROLS = CASES
SOURCE_FILES = (
    "tools/experiments/gcsim/theory_bounds/inputs.py",
    "tools/experiments/gcsim/mode_matrix/run_product_matrix.py",
    "run_workspace/gcsim/optimizer_go_inputs.py",
    "run_workspace/gcsim/optimizer_go_requests.py",
    "run_workspace/gcsim/optimizer_go_theory.py",
    "run_workspace/gcsim/optimizer_go_all.py",
    "run_workspace/gcsim/selected_team_config.py",
    "run_workspace/gcsim/virtual_roster.py",
    "run_workspace/gcsim/optimizer_engine_context.py",
)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite input number: {value}")


def _object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(f"Input JSON too large: {path}")
    result = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def _source(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {name: _hash(path) for name, path in paths.items()}


def _saved_control(receipt: dict[str, Any], case: str, wearers: set[str]) -> dict[str, Any] | None:
    if case not in SAVED_PACKAGE_CONTROLS:
        return None
    candidates = receipt.get("product", {}).get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Saved package control has no result candidate")
    chosen = candidates[0]
    if not isinstance(chosen, dict) or chosen.get("rank") != 1:
        raise ValueError("Saved package control is not rank one")
    packages = chosen.get("packages")
    if not isinstance(packages, list) or len(packages) != 4:
        raise ValueError("Saved package control requires four wearer packages")
    if (any(not isinstance(row, dict) or not isinstance(row.get("sets"), list)
            or not isinstance(row.get("wearer_key"), str) for row in packages)
            or {row["wearer_key"] for row in packages} != wearers):
        raise ValueError("Saved package control is malformed")
    # Extract only fixed set keys; no saved mains, rolls, layout, score, or objective.
    return {
        "role": "comparison_only_not_seed",
        "source": "current_matrix_theory_rank_one_result",
        "packages_by_wearer": {
            row["wearer_key"]: [
                {"set_uid": item["set_uid"], "count": item["count"]}
                for item in row["sets"]
            ]
            for row in packages
        },
    }


@contextmanager
def _owned_environment(job: Path):
    """Direct preparation's transient caches and subprocesses into this job."""
    temporary = job / "input-temp"
    temporary.mkdir(exist_ok=True)
    paths = {
        "GTT_SCRATCH_DIR": job,
        "TMP": temporary,
        "TEMP": temporary,
        "GTT_RULE_CACHE_DIR": job / "set-rule-cache",
        "GTT_RULE_BUNDLED_CACHE_DIR": job / "bundled-rule-cache",
    }
    saved = {name: os.environ.get(name) for name in (*paths, "PYTHONDONTWRITEBYTECODE")}
    try:
        for name, path in paths.items():
            os.environ[name] = str(path)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def load_contrast(case: str, job: str | Path, engine: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prepare one fresh four-profile, infinite-energy, two-seed Theory request.

    ``job`` must be an existing owned managed job. Only its copied SQLite DB and
    preparation directory are written. The caller chooses whether to compare
    against the optional saved package control in the returned provenance.
    """
    if case not in CASES:
        raise ValueError(f"Unsupported Theory contrast: {case}")
    job = Path(job).resolve()
    if not job.is_dir() or job.parent != MANAGED or not job.name.startswith("job-"):
        raise ValueError("Contrast preparation requires an owned managed job")
    if not engine.trusted:
        raise ValueError("Current GCSIM engine is not trusted")

    # These imports are read-only. The managed runner and this module disable
    # bytecode generation before importing any repository modules.
    from run_workspace.gcsim.optimizer_go_inputs import prepare_optimizer_inputs
    from tools.experiments.gcsim.mode_matrix import run_product_matrix as matrix

    receipt_path = OWNER / f"{case}_theory.json"
    manifest = _object(MANIFEST)
    receipt = _object(receipt_path)
    entries = [row for row in matrix._expanded_manifest_entries(manifest)
               if row.get("team") == case and row.get("mode") == "theory"]
    if len(entries) != 1 or entries[0].get("id") != f"{case}_theory":
        raise ValueError("The manifest does not identify one current Theory entry")
    entry = entries[0]
    profiles = entry.get("virtual_profiles")
    if (not isinstance(profiles, list) or len(profiles) != 4
            or any(not isinstance(row, dict) or not row.get("character_key")
                   or not row.get("weapon_key") for row in profiles)
            or len({row["character_key"] for row in profiles}) != 4):
        raise ValueError("Contrast requires four distinct virtual profiles")
    if entry.get("infinite_energy") is not True:
        raise ValueError("Contrast requires explicit infinite energy")

    rotation_path = _source(str(entry["rotation_file"]))
    source_db = _source(str(manifest["db_path"]))
    source_paths = {name: _source(name) for name in SOURCE_FILES}
    source_paths.update({
        MANIFEST.relative_to(ROOT).as_posix(): MANIFEST,
        rotation_path.relative_to(ROOT).as_posix(): rotation_path,
        receipt_path.relative_to(ROOT).as_posix(): receipt_path,
        source_db.relative_to(ROOT).as_posix(): source_db,
    })
    # WAL state, if present, participates in the frozen database identity.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source_db) + suffix)
        if sidecar.exists():
            source_paths[sidecar.relative_to(ROOT).as_posix()] = sidecar
    before = _hashes(source_paths)
    input_row = receipt.get("input", {})
    binding = receipt.get("binding", {})
    if (receipt.get("schema_version") != 1
            or receipt.get("execution", {}).get("success") is not True
            or binding.get("engine_trusted") is not True
            or input_row.get("team") != case
            or input_row.get("run_id") != f"{case}_theory"
            or input_row.get("manifest_sha256") != before[MANIFEST.relative_to(ROOT).as_posix()]
            or input_row.get("rotation_path") != rotation_path.relative_to(ROOT).as_posix()
            or input_row.get("rotation_sha256") != before[rotation_path.relative_to(ROOT).as_posix()]
            or input_row.get("profiles_sha256") != _canonical_hash(profiles)):
        raise ValueError("Current matrix manifest, rotation, or profiles differ from receipt")
    simple_profiles = [
        {"character_key": row["character_key"], "weapon_key": row["weapon_key"]}
        for row in profiles
    ]
    if input_row.get("profiles") != simple_profiles:
        raise ValueError("Current matrix virtual identities differ from receipt")
    binary = Path(engine.artifact_path).resolve()
    engine_root = Path(engine.engine_root).resolve()
    binary.relative_to(ROOT.resolve())
    engine_root.relative_to(ROOT.resolve())
    if (engine.engine_id != binding.get("engine_id")
            or engine.artifact_sha256 != binding.get("engine_artifact_sha256")
            or engine.binding_sha256 != binding.get("engine_binding_sha256")
            or binary.relative_to(ROOT).as_posix() != binding.get("engine_binary")
            or engine_root.relative_to(ROOT).as_posix() != binding.get("engine_root")
            or _hash(binary) != engine.artifact_sha256):
        raise ValueError("Current engine differs from current matrix receipt")
    control = _saved_control(receipt, case, {row["character_key"] for row in profiles})

    base = job / "contrasts" / case
    base.mkdir(parents=True, exist_ok=False)
    copied_db = base / "artifacts.db"
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source_conn, \
            closing(sqlite3.connect(copied_db)) as destination_conn:
        source_conn.backup(destination_conn)
    with _owned_environment(job):
        request = matrix._request(entry, db_path=copied_db, run_root=base / "runs")
        request = replace(request, expected_engine_id=engine.engine_id)
        if (tuple(request.seeds) != (742_031_889, 742_031_890)
                or not request.infinite_energy_enabled
                or request.db_path != str(copied_db)):
            raise ValueError("Prepared product request changed its two-seed or energy policy")
        prep = base / "preparation"
        prep.mkdir()
        prepared = prepare_optimizer_inputs(request, prep, mode="theory")
    wire = prepared["request"]
    wire_engine = wire["engine"]
    expected_engine = binding.get("request_engine", {})
    expected_request_binding = _canonical_hash({
        "kind": "gtt.standalone_engine_binding.v1",
        **{key: expected_engine.get(key) for key in
           ("artifact_sha256", "source_manifest_sha256", "patch_manifest_sha256")},
    })
    if (wire["stochastic"]["seeds"] != [742_031_889, 742_031_890]
            or wire_engine.get("artifact_sha256") != engine.artifact_sha256
            or wire_engine.get("binding_sha256") != expected_request_binding
            or any(wire_engine.get(key) != expected_engine.get(key)
                   for key in ("artifact_sha256", "source_manifest_sha256", "patch_manifest_sha256"))
            or wire.get("legality", {}).get("theory_search") is not True):
        raise ValueError("Fresh Theory preparation differs from receipt engine or seed binding")
    if _hashes(source_paths) != before or _hash(binary) != engine.artifact_sha256:
        raise ValueError("Source files or engine changed during Theory preparation")
    if any(Path(str(source_db) + suffix).exists() !=
           (Path(str(source_db) + suffix).relative_to(ROOT).as_posix() in before)
           for suffix in ("-wal", "-shm")):
        raise ValueError("Source database sidecar state changed during preparation")

    provenance = {
        "kind": "fresh_virtual_theory_contrast_input_v1",
        "case": case,
        "mode": "theory",
        "energy": "infinite",
        "seeds": list(request.seeds),
        "profiles_sha256": _canonical_hash(profiles),
        "source_sha256": before,
        "engine": {
            "id": engine.engine_id,
            "artifact_sha256": engine.artifact_sha256,
            "binding_sha256": engine.binding_sha256,
            "request_binding_sha256": wire_engine["binding_sha256"],
        },
        "receipt": {"path": receipt_path.relative_to(ROOT).as_posix(),
                    "sha256": before[receipt_path.relative_to(ROOT).as_posix()]},
        "database_copy": copied_db.relative_to(job).as_posix(),
        "request_sha256": prepared["request_sha256"],
        "saved_package_control": control,
        "saved_solution_reuse": False,
    }
    return wire, provenance
