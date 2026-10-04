"""One bounded Selected/neutral changed-item response gate.

Run only through tools/managed_optimizer_experiment.py. The frozen request,
fresh engine captures, copied Go source, build cache and raw output stay in its
owned job. Only one compact immutable receipt survives.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import assert_unlinked, owned_job
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest,
    GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256, write_canonical
from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
)
from run_workspace.gcsim.source_manifest_build import canonical_json as canonical_source_manifest_json
from run_workspace.gcsim.engine_store import load_engine_manifest


FROZEN_REQUEST = (
    ROOT
    / "data/gcsim/optimizer-go-runs/selected-20260928-122336-1a5e659e/request.json"
)
FROZEN_REQUEST_SHA256 = "11532ecbe8925315e3f675c5b5680c72a7d32c2e1083a95d45af6e00927ab2ef"
EXPECTED_SEEDS = (742_031_889, 742_031_890)
EXPECTED_ARTIFACT_COUNT = 597
EXPECTED_BUILDS_PER_GROUP = 7
RECEIPT_DIR = ROOT / "docs/optimizer-evidence/2026-10-04-optimizer-closeout"
MAX_RECEIPTS = 3
MAX_RECEIPT_BYTES = 128 * 1024
SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
PACKAGES = (
    "./internal/domain",
    "./internal/search",
    "./internal/setcontext",
    "./internal/finalists",
)
GO_TEST_SOURCE = Path(__file__).with_name("closeout_response_test.go")
NATIVE_FIXTURE_ROOT = ROOT / "tests/fixtures/gcsim_optimizer_go_v1"
NATIVE_FIXTURE_NAMES = ("request_v1.json", "compact_ir_v1.json")
SOURCE_DIGEST_ALGORITHM = (
    "sha256 over sorted relative .go, go.mod, and go.sum files when present; "
    "each record is uint32be path length + path bytes + uint64be content length + content bytes; "
    "distinct from the H4 NUL-delimited aggregate"
)


class CloseoutError(RuntimeError):
    pass


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def immutable_receipt_target(raw: str | Path, *, owner: Path = RECEIPT_DIR) -> Path:
    """Validate one direct-child JSON receipt without replacing any evidence."""
    owner = Path(owner).absolute()
    target = Path(raw).absolute()
    if target.parent != owner or target.suffix.casefold() != ".json":
        raise ValueError("Receipt must be a JSON directly in the closeout evidence folder")
    assert_unlinked(owner)
    owner.mkdir(parents=True, exist_ok=True)
    assert_unlinked(target)
    resolved_owner = owner.resolve(strict=True)
    resolved_target = target.resolve(strict=False)
    if resolved_target.parent != resolved_owner:
        raise ValueError("Receipt path escapes the closeout evidence folder")
    if target.exists():
        raise FileExistsError(target)
    existing = list(owner.glob("*.json"))
    for path in existing:
        assert_unlinked(path)
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("An existing receipt exceeds the per-file byte budget")
    if len(existing) >= MAX_RECEIPTS:
        raise ValueError("Closeout receipt count budget is exhausted")
    return target


def write_receipt(
    raw: str | Path,
    payload: Mapping[str, Any],
    *,
    owner: Path = RECEIPT_DIR,
) -> Path:
    target = immutable_receipt_target(raw, owner=owner)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise ValueError("Closeout receipt exceeds the 128 KiB budget")
    # Recheck the shared count immediately before the exclusive creation.
    target = immutable_receipt_target(target, owner=owner)
    with target.open("xb") as handle:
        handle.write(encoded)
    return target


def load_frozen_request(path: str | Path = FROZEN_REQUEST) -> dict[str, Any]:
    source = Path(path)
    actual = digest_file(source)
    if actual != FROZEN_REQUEST_SHA256:
        raise ValueError("Pinned Selected request changed")
    request = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ValueError("Pinned Selected request must be a JSON object")
    if request.get("schema_kind") != "gtt_gcsim_optimizer_request_v1":
        raise ValueError("Pinned input is not a Selected optimizer request")
    seeds = tuple(request.get("stochastic", {}).get("seeds", ()))
    if seeds != EXPECTED_SEEDS:
        raise ValueError("Pinned Selected seed order changed")
    if len(request.get("artifacts", ())) != EXPECTED_ARTIFACT_COUNT:
        raise ValueError("Pinned Selected inventory count changed")
    _validate_request_inventory(request)
    return request


def request_for_fast_selection(request: Mapping[str, Any]) -> dict[str, Any]:
    """Clone the frozen contract and change only the explicit fast flag."""
    clone = deepcopy(dict(request))
    options = clone.get("result_options")
    if not isinstance(options, dict):
        raise ValueError("Selected result options are required")
    if options.get("builds_per_group") != EXPECTED_BUILDS_PER_GROUP:
        raise ValueError("Inherited builds_per_group must remain seven")
    options["fast_mode"] = True
    changed = _differing_paths(request, clone)
    if changed != ["result_options.fast_mode"]:
        raise ValueError(f"Fast request changed unexpected fields: {changed}")
    return clone


def _differing_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        keys = set(before) | set(after)
        result: list[str] = []
        for key in sorted(keys):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                result.append(path)
            else:
                result.extend(_differing_paths(before[key], after[key], path))
        return result
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [prefix]
        result = []
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            result.extend(_differing_paths(left, right, f"{prefix}[{index}]"))
        return result
    return [] if before == after else [prefix]


def _validate_request_inventory(request: Mapping[str, Any]) -> None:
    artifacts = request.get("artifacts")
    wearers = request.get("wearers")
    if not isinstance(artifacts, list) or not isinstance(wearers, list) or len(wearers) != 4:
        raise ValueError("Selected request has an invalid fixed team or artifact pool")
    by_id: dict[int, Mapping[str, Any]] = {}
    for row in artifacts:
        if not isinstance(row, Mapping):
            raise ValueError("Artifact rows must be objects")
        ident = row.get("artifact_id")
        if type(ident) is not int or ident <= 0 or ident in by_id:
            raise ValueError("Artifact IDs must be positive and unique")
        by_id[ident] = row
    actor_keys = [str(row.get("wearer_key", "")) for row in wearers]
    if actor_keys != sorted(set(actor_keys)) or len(actor_keys) != 4:
        raise ValueError("Wearers must be four distinct canonical actor keys")
    assigned: list[int] = []
    for wearer in wearers:
        rows = wearer.get("current_artifacts")
        if not isinstance(rows, list) or len(rows) != len(SLOTS):
            raise ValueError("Each wearer must have five reference artifacts")
        for slot, assignment in zip(SLOTS, rows, strict=True):
            if assignment.get("wearer_key") != wearer["wearer_key"] or assignment.get("slot") != slot:
                raise ValueError("Reference items must preserve canonical owner/slot order")
            ident = assignment.get("artifact_id")
            artifact = by_id.get(ident)
            if artifact is None or artifact.get("slot") != slot:
                raise ValueError("Reference assignment does not match the inventory")
            assigned.append(ident)
    if len(set(assigned)) != 20:
        raise ValueError("Selected reference must contain twenty globally unique IDs")


def _assignment_rows(candidate: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = candidate.get("artifacts")
    if not isinstance(raw, list) or len(raw) != 20:
        raise ValueError("Production top1 must contain twenty assigned artifacts")
    rows = [dict(row) for row in raw if isinstance(row, Mapping)]
    if len(rows) != 20:
        raise ValueError("Production top1 assignment is malformed")
    expected = [(w["wearer_key"], slot) for w in request["wearers"] for slot in SLOTS]
    actual = [(row.get("wearer_key"), row.get("slot")) for row in rows]
    if actual != expected:
        raise ValueError("Production top1 does not preserve canonical owner/slot order")
    _require_legal_assignment(request, rows)
    return rows


def _requirements(wearer: Mapping[str, Any]) -> list[tuple[str, int]]:
    rows = wearer.get("selected_sets")
    if isinstance(rows, list) and rows:
        return [(str(row["set_uid"]), int(row["count"])) for row in rows]
    uid = wearer.get("selected_set_uid")
    if uid:
        return [(str(uid), 4)]
    return []


def _require_legal_assignment(request: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    inventory = {row["artifact_id"]: row for row in request["artifacts"]}
    expected = [(w["wearer_key"], slot) for w in request["wearers"] for slot in SLOTS]
    if [(row.get("wearer_key"), row.get("slot")) for row in rows] != expected:
        raise ValueError("Assignment must contain the fixed four-by-five slot grid")
    ids = [row.get("artifact_id") for row in rows]
    if len(ids) != 20 or len(set(ids)) != 20:
        raise ValueError("Assignment must use twenty globally unique artifact IDs")
    authorized = set(request.get("legality", {}).get("authorized_lower_rarity_artifact_ids", ()))
    minimum = int(request.get("legality", {}).get("default_minimum_rarity", 5))
    by_actor: dict[str, list[int]] = {str(row["wearer_key"]): [] for row in request["wearers"]}
    for row in rows:
        artifact = inventory.get(row.get("artifact_id"))
        if artifact is None or artifact.get("slot") != row.get("slot"):
            raise ValueError("Assignment references an unknown item or wrong slot")
        if int(artifact.get("rarity", 0)) < minimum and artifact["artifact_id"] not in authorized:
            raise ValueError("Assignment violates the request rarity floor")
        by_actor[str(row["wearer_key"])].append(int(artifact["artifact_id"]))
    for wearer in request["wearers"]:
        actor = str(wearer["wearer_key"])
        counts: dict[str, int] = {}
        for ident in by_actor[actor]:
            uid = str(inventory[ident]["set_uid"])
            counts[uid] = counts.get(uid, 0) + 1
        for uid, required in _requirements(wearer):
            if counts.get(uid, 0) < required:
                raise ValueError(f"Assignment violates fixed set package for {actor}")


def _stat_totals(artifact: Mapping[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    main = artifact.get("main_stat")
    if not isinstance(main, Mapping):
        raise ValueError("Artifact main stat is missing")
    for stat in [main, *(artifact.get("substats") or ())]:
        key = str(stat.get("key") or "")
        value = float(stat.get("value"))
        if not key or not math.isfinite(value):
            raise ValueError("Artifact stat is malformed")
        output[key] = output.get(key, 0.0) + value
    return output


def crit_mass(artifact: Mapping[str, Any]) -> float:
    """Normalized crit mass used for challenger ordering: 2*CR + CD."""
    stats = _stat_totals(artifact)
    return 2.0 * stats.get("crit_rate", 0.0) + stats.get("crit_damage", 0.0)


def _slot_index(rows: Sequence[Mapping[str, Any]], actor: str, slot: str) -> int:
    for index, row in enumerate(rows):
        if row.get("wearer_key") == actor and row.get("slot") == slot:
            return index
    raise ValueError(f"Assignment lacks {actor} {slot}")


def _isolated_swap(
    base: Sequence[Mapping[str, Any]],
    *,
    actor: str,
    slot: str,
    replacement_id: int,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in base]
    target = rows[_slot_index(rows, actor, slot)]
    target["artifact_id"] = replacement_id
    assert_isolated_swap(base, rows, actor=actor, slot=slot)
    return rows


def assert_isolated_swap(
    base: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    actor: str,
    slot: str,
) -> None:
    if len(base) != 20 or len(candidate) != 20:
        raise ValueError("Changed-item comparison requires two complete assignments")
    changed = [index for index, (left, right) in enumerate(zip(base, candidate, strict=True)) if left != right]
    target = _slot_index(base, actor, slot)
    if changed != [target]:
        raise ValueError("A changed-item candidate must alter exactly its authorized slot")
    if candidate[target].get("artifact_id") == base[target].get("artifact_id"):
        raise ValueError("Changed-item candidate must use a distinct artifact")


def choose_changed_item_cases(
    request: Mapping[str, Any],
    top1: Mapping[str, Any],
    *,
    actor: str = "chasca",
) -> list[dict[str, Any]]:
    """Choose a legal high-crit plume and goblet challenger against top1."""
    base = _assignment_rows(top1, request)
    inventory = {row["artifact_id"]: row for row in request["artifacts"]}
    used = {row["artifact_id"] for row in base}
    wearer = next((row for row in request["wearers"] if row["wearer_key"] == actor), None)
    if wearer is None:
        raise ValueError(f"Frozen request has no {actor} wearer")

    def legal_for(slot: str) -> list[Mapping[str, Any]]:
        output = []
        for item in request["artifacts"]:
            if item.get("slot") != slot or item["artifact_id"] in used:
                continue
            trial = _isolated_swap(base, actor=actor, slot=slot, replacement_id=item["artifact_id"])
            try:
                _require_legal_assignment(request, trial)
            except ValueError:
                continue
            output.append(item)
        return output

    plume_candidates = legal_for("plume")
    if not plume_candidates:
        raise ValueError("No legal unused Chasca plume alternative in frozen inventory")
    plume = max(plume_candidates, key=lambda item: (crit_mass(item), -int(item["artifact_id"])))
    plume_rows = _isolated_swap(base, actor=actor, slot="plume", replacement_id=int(plume["artifact_id"]))

    goblet_candidates = legal_for("goblet")
    atk_goblets = [row for row in goblet_candidates if row.get("main_stat", {}).get("key") == "atk_percent"]
    base_goblet_id = base[_slot_index(base, actor, "goblet")]["artifact_id"]
    base_goblet_main = inventory[base_goblet_id]["main_stat"]["key"]
    if atk_goblets:
        goblet = max(atk_goblets, key=lambda item: (crit_mass(item), -int(item["artifact_id"])))
        goblet_criterion = "highest_normalized_crit_mass_legal_atk_percent_main"
    else:
        distinct = [row for row in goblet_candidates if row.get("main_stat", {}).get("key") != base_goblet_main]
        if not distinct:
            raise CloseoutError("No legal distinct-main-stat Chasca goblet challenger exists")
        else:
            goblet = max(distinct, key=lambda item: (crit_mass(item), -int(item["artifact_id"])))
            goblet_criterion = "highest_normalized_crit_mass_legal_distinct_main_stat_fallback"

    base_stats = _assignment_actor_stats(request, base, actor)
    cases: list[dict[str, Any]] = [{
        "name": "top1",
        "assignment": base,
        "selection": {"kind": "fresh_production_formula_top1"},
    }, {
        "name": "chasca_plume",
        "assignment": plume_rows,
        "selection": {
            "kind": "single_item_swap",
            "slot": "plume",
            "criterion": "highest_normalized_crit_mass_legal_unused_same_slot",
            "artifact_id": int(plume["artifact_id"]),
            "normalized_crit_mass_2cr_plus_cd": crit_mass(plume),
        },
        "stat_delta_vs_top1": _map_delta(base_stats, _assignment_actor_stats(request, plume_rows, actor)),
    }]
    goblet_rows = _isolated_swap(base, actor=actor, slot="goblet", replacement_id=int(goblet["artifact_id"]))
    _require_legal_assignment(request, goblet_rows)
    cases.append({
        "name": "chasca_goblet",
        "assignment": goblet_rows,
        "selection": {
            "kind": "single_item_swap",
            "slot": "goblet",
            "criterion": goblet_criterion,
            "baseline_main_stat": base_goblet_main,
            "selected_main_stat": goblet["main_stat"]["key"],
            "artifact_id": int(goblet["artifact_id"]),
            "normalized_crit_mass_2cr_plus_cd": crit_mass(goblet),
        },
        "stat_delta_vs_top1": _map_delta(base_stats, _assignment_actor_stats(request, goblet_rows, actor)),
    })
    return cases


def _assignment_actor_stats(
    request: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], actor: str
) -> dict[str, float]:
    inventory = {row["artifact_id"]: row for row in request["artifacts"]}
    totals: dict[str, float] = {}
    for row in rows:
        if row["wearer_key"] != actor:
            continue
        for key, value in _stat_totals(inventory[row["artifact_id"]]).items():
            totals[key] = totals.get(key, 0.0) + value
    return totals


def _map_delta(before: Mapping[str, float], after: Mapping[str, float]) -> dict[str, float]:
    keys = sorted(set(before) | set(after))
    return {key: after.get(key, 0.0) - before.get(key, 0.0) for key in keys
            if after.get(key, 0.0) != before.get(key, 0.0)}


def _selected_case_request(request: Mapping[str, Any], job: Path) -> GcsimOptimizerGoSelectedRequest:
    options = request["result_options"]
    return GcsimOptimizerGoSelectedRequest(
        db_path=str(job / "unused-account-db-path"),
        selected_team={},
        team_index=0,
        rotation_shell_text="",
        infinite_energy_enabled=True,
        set_group_limit=int(options["set_group_limit"]),
        builds_per_group=int(options["builds_per_group"]),
        expanded_limits=bool(options.get("expanded_limits", False)),
        fast_mode=True,
        expected_engine_id="",
        optimizer_binary_path=str(DEFAULT_OPTIMIZER_BINARY),
        run_root=str(job / "unused-session-run-root"),
        seeds=tuple(request["stochastic"]["seeds"]),
        product_timeout_ms=int(request["budgets"]["product_timeout_ms"]),
    )


def _selected_production_top1(request: dict[str, Any], job: Path) -> tuple[dict[str, Any], Path]:
    run_dir = job / "selected-reference"
    run_dir.mkdir()
    request_path = run_dir / "request.json"
    write_canonical(request_path, request)
    prepared = {"request": request, "request_sha256": canonical_sha256(request), "adapter_warnings": ()}
    session = GcsimOptimizerGoSelectedSession(_selected_case_request(request, job))
    session._optimizer_environment = lambda: _managed_go_environment(job, include_scratch=True)
    started = time.monotonic()
    session._validate_optimizer_request(run_dir=run_dir, started=started)
    compact = session._prepare_formula_inputs(prepared=prepared, run_dir=run_dir, started=started)
    result = session._run_go_optimizer(
        prepared=prepared, compact=compact, run_dir=run_dir, started=started
    )
    product = result
    if product.get("ranking_basis") != "formula" or "formula_only_unverified" not in product.get("warnings", ()):
        raise CloseoutError("Fresh Selected adapter did not return formula-only ranked output")
    if product.get("measured") is not None or not product.get("candidates"):
        raise CloseoutError("Fresh Selected adapter returned no unmeasured formula finalists")
    return product["candidates"][0], run_dir


def _all_sets_sources(request: dict[str, Any], job: Path) -> Path:
    source_dir = job / "all-sets-sources"
    source_dir.mkdir()
    request_path = job / "selected-reference" / "request.json"
    # All Sets preparation reads the prepared request and the currently active
    # engine source tree. It does not open an account DB or run a search.
    options = request["result_options"]
    adapter_request = GcsimOptimizerGoAllSetsRequest(
        db_path=str(job / "unused-account-db-path"), selected_team={}, team_index=0,
        rotation_shell_text="", infinite_energy_enabled=True,
        set_group_limit=int(options["set_group_limit"]),
        builds_per_group=int(options["builds_per_group"]),
        expanded_limits=bool(options.get("expanded_limits", False)), fast_mode=True,
        optimizer_binary_path=str(DEFAULT_OPTIMIZER_BINARY),
        run_root=str(job / "unused-all-sets-run-root"),
        seeds=tuple(request["stochastic"]["seeds"]),
        product_timeout_ms=int(request["budgets"]["product_timeout_ms"]),
    )
    # Source preparation consumes this in-memory clone only.
    prepared = {"request": request, "request_sha256": canonical_sha256(request)}
    session = GcsimOptimizerGoAllSetsSession(adapter_request)
    session._prepare_formula_inputs(prepared=prepared, run_dir=source_dir, started=time.monotonic())
    result = source_dir / "set-sources.json"
    if not result.is_file():
        raise CloseoutError("Current All Sets source adapter did not write its bundle")
    return result


def _engine_binding(request: Mapping[str, Any]) -> dict[str, Any]:
    context = load_active_gcsim_optimizer_engine_context()
    if not context.trusted:
        raise CloseoutError("Active GCSIM engine context is not trusted")
    engine = request["engine"]
    artifact_path = Path(context.artifact_path).resolve(strict=True)
    request_engine_path = Path(str(engine["binary_path"])).resolve(strict=True)
    if request_engine_path != artifact_path:
        raise CloseoutError("Frozen request does not name the active engine artifact path")
    if engine.get("artifact_sha256") != context.artifact_sha256:
        raise CloseoutError("Frozen request and active engine artifact digests differ")
    root = Path(context.engine_root)
    source_body_path = root / "build" / "gtt-source-manifest-body.json"
    source_body = json.loads(source_body_path.read_bytes())
    source_manifest_sha = digest_bytes(canonical_source_manifest_json(source_body).encode("utf-8"))
    manifest = load_engine_manifest(root)
    patch_sha = str(manifest.patch_metadata.get("patch_stack_sha256", "") or "").casefold()
    if engine.get("source_manifest_sha256") != source_manifest_sha:
        raise CloseoutError("Frozen request and active engine source manifest differ")
    if engine.get("patch_manifest_sha256") != patch_sha:
        raise CloseoutError("Frozen request and active engine patch manifest differ")
    if set(engine.get("capabilities", ())) != set(context.capabilities):
        raise CloseoutError("Frozen request and active engine capabilities differ")
    consumer_path = Path(DEFAULT_OPTIMIZER_BINARY).resolve(strict=True)
    return {
        "engine_id": context.engine_id,
        "engine_root": str(root),
        "binary_path": str(artifact_path),
        "artifact_sha256": context.artifact_sha256,
        "source_manifest_sha256": source_manifest_sha,
        "patch_manifest_sha256": patch_sha,
        "engine_tree_sha256": context.engine_tree_sha256,
        "catalog_fingerprint": context.catalog.source_fingerprint,
        "binding_sha256": context.binding_sha256,
        "capabilities": list(context.capabilities),
        "consumer_default_path": str(consumer_path),
        "consumer_default_sha256": digest_file(consumer_path),
    }


def _active_identity_unchanged(before: Mapping[str, Any]) -> bool:
    try:
        current = load_active_gcsim_optimizer_engine_context()
        consumer_path = Path(DEFAULT_OPTIMIZER_BINARY).resolve(strict=True)
        return bool(
            current.trusted
            and current.engine_id == before["engine_id"]
            and Path(current.engine_root).resolve() == Path(before["engine_root"]).resolve()
            and Path(current.artifact_path).resolve() == Path(before["binary_path"]).resolve()
            and current.artifact_sha256 == before["artifact_sha256"]
            and current.engine_tree_sha256 == before["engine_tree_sha256"]
            and current.catalog.source_fingerprint == before["catalog_fingerprint"]
            and current.binding_sha256 == before["binding_sha256"]
            and consumer_path == Path(before["consumer_default_path"]).resolve()
            and digest_file(consumer_path) == before["consumer_default_sha256"]
        )
    except (OSError, ValueError, RuntimeError):
        return False


def _source_digest(native: Path) -> str:
    digest = hashlib.sha256()
    paths = sorted([
        *native.rglob("*.go"),
        *(path for path in (native / "go.mod", native / "go.sum") if path.is_file()),
    ])
    for path in paths:
        rel = path.relative_to(native).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _copy_native_source(native: Path, target: Path, job: Path) -> int:
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name.casefold().endswith((".exe", ".test", ".out"))}
        for name in names:
            if name in {"set-rule-cache", ".git", ".codex_tmp"}:
                ignored.add(name)
        return ignored

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(native, target, ignore=ignore)
    fixtures = job / "repo" / "tests" / "fixtures" / "gcsim_optimizer_go_v1"
    fixtures.mkdir(parents=True)
    for name in NATIVE_FIXTURE_NAMES:
        shutil.copy2(NATIVE_FIXTURE_ROOT / name, fixtures / name)
    return sum(path.stat().st_size for root in (target, fixtures) for path in root.rglob("*") if path.is_file())


def _managed_go_environment(
    job: Path,
    *,
    base: Mapping[str, str] | None = None,
    closeout: Mapping[str, str] | None = None,
    include_scratch: bool = False,
) -> dict[str, str]:
    """Build a clean Go env; inherited GTT_* values cannot enable live hooks."""
    inherited = os.environ if base is None else base
    env = {key: value for key, value in inherited.items() if not key.startswith("GTT_")}
    extras = dict(closeout or {})
    if any(not key.startswith("GTT_CLOSEOUT_") for key in extras):
        raise ValueError("Only explicit GTT_CLOSEOUT_* inputs may enter the Go environment")
    env.update(extras)
    rule_cache = job / "rule-cache"
    go_cache = job / "go-build-cache"
    go_temp = job / "go-temp"
    for directory in (rule_cache, go_cache, go_temp):
        directory.mkdir(parents=True, exist_ok=True)
    env.update({
        "GTT_RULE_CACHE_DIR": str(rule_cache),
        "GTT_RULE_BUNDLED_CACHE_DIR": "",
        "GOCACHE": str(go_cache),
        "GOTMPDIR": str(go_temp),
        "GOWORK": "off",
        "GOTOOLCHAIN": "local",
        "TMP": str(go_temp),
        "TEMP": str(go_temp),
    })
    if include_scratch:
        env["GTT_SCRATCH_DIR"] = str(job)
    return env


def _run_go_checks(native_copy: Path, job: Path) -> dict[str, Any]:
    env = _managed_go_environment(job)
    rows: dict[str, Any] = {}
    for label, arguments in (
        ("vet", ["go", "vet", *PACKAGES]),
        ("unit", ["go", "test", *PACKAGES, "-count=1"]),
    ):
        completed = subprocess.run(
            arguments,
            cwd=native_copy,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        rows[label] = {"exit_code": completed.returncode, "packages": list(PACKAGES)}
        if completed.returncode != 0:
            detail = completed.stdout[-1800:].strip()
            raise CloseoutError(f"Native {label} checks failed ({completed.returncode}): {detail}")
    return rows


def _tree_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def _write_cases(
    path: Path,
    cases: Sequence[Mapping[str, Any]],
    *,
    production_top1_formula_dps: float,
) -> None:
    payload = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_closeout_cases_v1",
        "production_top1_formula_dps": production_top1_formula_dps,
        "cases": [
            {
                "name": row["name"],
                "assignment": row["assignment"],
                "selection": row["selection"],
                "stat_delta_vs_top1": row.get("stat_delta_vs_top1", {}),
            }
            for row in cases
        ],
    }
    write_canonical(path, payload)


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise CloseoutError(f"{label} is not a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CloseoutError(f"{label} is not a finite number") from exc
    if not math.isfinite(parsed):
        raise CloseoutError(f"{label} is not a finite number")
    return parsed


def _run_injected_native_gate(
    *,
    native_copy: Path,
    job: Path,
    request_path: Path,
    compact_path: Path,
    source_path: Path,
    cases_path: Path,
    go_test_digest: str,
) -> dict[str, Any]:
    capture_root = job / "fresh-captures"
    neutral_root = job / "neutral-captures"
    capture_root.mkdir()
    neutral_root.mkdir()
    output_path = job / "go-evidence.json"
    delta_path = job / "zero-deltas.json"
    delta_path.write_text("{}\n", encoding="utf-8")
    env = _managed_go_environment(job, closeout={
        "GTT_CLOSEOUT_REQUEST": str(request_path),
        "GTT_CLOSEOUT_REFERENCE_COMPACT": str(compact_path),
        "GTT_CLOSEOUT_ZERO_DELTAS": str(delta_path),
        "GTT_CLOSEOUT_SOURCES": str(source_path),
        "GTT_CLOSEOUT_CASES": str(cases_path),
        "GTT_CLOSEOUT_CAPTURE_ROOT": str(capture_root),
        "GTT_CLOSEOUT_NEUTRAL_ROOT": str(neutral_root),
        "GTT_CLOSEOUT_OUTPUT": str(output_path),
        "GTT_CLOSEOUT_TEST_SOURCE_SHA256": go_test_digest,
    })
    completed = subprocess.run(
        ["go", "test", "./cmd/gtt-optimizer", "-run", "^TestCloseoutResponse$", "-count=1"],
        cwd=native_copy,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout[-1800:].strip()
        raise CloseoutError(f"Managed-copy numerical gate failed ({completed.returncode}): {detail}")
    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    if evidence.get("go_test_source_sha256") != go_test_digest:
        raise CloseoutError("Managed-copy test source identity mismatch")
    expected_go_captures = len(EXPECTED_SEEDS) * (1 + len(json.loads(cases_path.read_text(encoding="utf-8"))["cases"]))
    if evidence.get("trace_seed_capture_members_inside_go") != expected_go_captures:
        raise CloseoutError("Go seed-capture count differs from the bounded gate plan")
    return evidence


def _compile_injected_test(native_copy: Path, job: Path) -> dict[str, Any]:
    """Compile the experiment test before any runtime GCSIM capture."""
    cmd_dir = native_copy / "cmd" / "gtt-optimizer"
    injected = cmd_dir / "closeout_response_experiment_test.go"
    if injected.exists():
        raise CloseoutError("Managed-copy Go test path already exists")
    shutil.copy2(GO_TEST_SOURCE, injected)
    completed = subprocess.run(
        ["go", "test", "./cmd/gtt-optimizer", "-run", "^TestCloseoutConfigPredicates$", "-count=1"],
        cwd=native_copy,
        env=_managed_go_environment(job),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout[-1800:].strip()
        raise CloseoutError(f"Managed-copy config predicate test failed ({completed.returncode}): {detail}")
    return {
        "test": "TestCloseoutConfigPredicates",
        "status": "passed",
        "exit_code": 0,
        "source_sha256": digest_file(GO_TEST_SOURCE),
    }


def _preflight_then_selected_top1(
    native_copy: Path,
    job: Path,
    request: dict[str, Any],
    *,
    progress: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    """Run native checks and the config-only Go predicate before Selected can capture."""
    checks = _run_go_checks(native_copy, job)
    predicate_check = _compile_injected_test(native_copy, job)
    checks["injected_config_predicates"] = predicate_check
    if predicate_check.get("source_sha256") != digest_file(GO_TEST_SOURCE):
        raise CloseoutError("Injected Go test source changed before config predicate execution")
    if progress is not None:
        progress.update({
            "stage": "selected_reference_in_progress",
            "actual_capture_members": None,
            "capture_count_status": "unknown_until_adapter_returns",
        })
    top1, selected_dir = _selected_production_top1(request, job)
    return checks, predicate_check, top1, selected_dir


def run_gate(
    job: Path,
    *,
    request_path: Path,
    receipt_path: Path,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if progress is None:
        progress = {}
    progress.update({
        "stage": "frozen_request_validation",
        "actual_capture_members": 0,
        "capture_count_status": "known",
    })
    original = load_frozen_request(request_path)
    modified = request_for_fast_selection(original)
    before = _engine_binding(modified)
    native = ROOT / "native/gcsim_optimizer"
    source_digest = _source_digest(native)
    go_test_digest = digest_file(GO_TEST_SOURCE)
    native_copy = job / "repo" / "native" / "gcsim_optimizer"
    progress.update({
        "stage": "native_preflight",
        "actual_capture_members": 0,
        "capture_count_status": "known",
    })
    copied_bytes = _copy_native_source(native, native_copy, job)
    check_results, predicate_check, top1, selected_dir = _preflight_then_selected_top1(
        native_copy, job, modified, progress=progress
    )
    if predicate_check["source_sha256"] != go_test_digest:
        raise CloseoutError("Injected Go test source changed before config predicate execution")
    formula_dps = _finite_number(top1.get("formula_dps"), label="Fresh Selected top1 formula DPS")
    compact_payload = json.loads((selected_dir / "compact.json").read_text(encoding="utf-8"))
    if [row.get("seed") for row in compact_payload.get("members", ())] != list(EXPECTED_SEEDS):
        raise CloseoutError("Fresh Selected reference capture changed seed count or declaration order")
    progress.update({
        "stage": "selected_reference_complete",
        "actual_capture_members": len(EXPECTED_SEEDS),
        "capture_count_status": "known",
    })
    cases = choose_changed_item_cases(modified, top1)
    _write_cases(job / "cases.json", cases, production_top1_formula_dps=formula_dps)
    sources_path = _all_sets_sources(modified, job)
    if sorted(path.name for path in (job / "all-sets-sources").iterdir()) != ["set-sources.json"]:
        raise CloseoutError("All Sets source preparation produced unexpected capture or output files")
    selected_request_path = selected_dir / "request.json"
    compact_path = selected_dir / "compact.json"
    progress.update({
        "stage": "neutral_and_candidate_captures_in_progress",
        "actual_capture_members": None,
        "capture_count_status": "unknown_until_native_gate_returns",
    })
    evidence = _run_injected_native_gate(
        native_copy=native_copy,
        job=job,
        request_path=selected_request_path,
        compact_path=compact_path,
        source_path=sources_path,
        cases_path=job / "cases.json",
        go_test_digest=go_test_digest,
    )
    progress.update({
        "stage": "all_captures_complete",
        "actual_capture_members": len(EXPECTED_SEEDS)
        + int(evidence["trace_seed_capture_members_inside_go"]),
        "capture_count_status": "known",
    })
    unchanged = _active_identity_unchanged(before)
    if not unchanged:
        raise CloseoutError("Active engine or installed consumer changed during the gate")
    if evidence.get("case_count") != len(cases):
        raise CloseoutError("Native gate returned a different case count")
    selected_item_ids = {
        case["name"]: {
            "slot": case["selection"]["slot"],
            "artifact_id": case["selection"]["artifact_id"],
        }
        for case in cases if case["name"] != "top1"
    }
    top1_assignment_digest = canonical_sha256(top1["artifacts"])
    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_closeout_response_receipt_v1",
        "status": "complete",
        "scope": "one Chasca Selected fixed-package changed-item response gate; not a full All Sets search",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frozen_request_sha256": FROZEN_REQUEST_SHA256,
        "selection_request_sha256": canonical_sha256(modified),
        "selection_input_changes": ["result_options.fast_mode=true"],
        "builds_per_group": EXPECTED_BUILDS_PER_GROUP,
        "artifact_pool_size": EXPECTED_ARTIFACT_COUNT,
        "selected_reference_ids": [
            row["artifact_id"] for row in top1["artifacts"] if row["wearer_key"] == "chasca"
        ],
        "top1_assignment_sha256": top1_assignment_digest,
        "changed_item_ids": selected_item_ids,
        "seeds_in_declaration_order": list(EXPECTED_SEEDS),
        "trace_seed_capture_budget": {
            "selected_reference": len(EXPECTED_SEEDS),
            "neutral_no_set_panel": len(EXPECTED_SEEDS),
            "fresh_top1_and_two_swaps": len(EXPECTED_SEEDS) * len(cases),
            "total": len(EXPECTED_SEEDS) * (2 + len(cases)),
            "maximum": 10,
        },
        "engine": before,
        "consumer": {
            "default_optimizer_binary": before["consumer_default_path"],
            "sha256": before["consumer_default_sha256"],
        },
        "native_source": {
            "go_source_sha256": source_digest,
            "go_source_sha256_algorithm": SOURCE_DIGEST_ALGORITHM,
            "managed_copy_bytes": copied_bytes,
            "injected_test_sha256": predicate_check["source_sha256"],
            "checks": check_results,
        },
        "production_top1": {
            "rank": top1.get("rank"),
            "formula_dps": top1.get("formula_dps"),
            "ranking_basis": evidence.get("production_ranking_basis", "formula"),
            "warning": "formula_only_unverified",
        },
        "candidate_selection": [
            {key: value for key, value in case.items() if key not in {"assignment"}}
            for case in cases
        ],
        "response": evidence,
        "engine_and_consumer_unchanged": unchanged,
        "ephemeral_cleanup": {
            "owner": "tools.managed_optimizer_experiment.managed_scratch",
            "job_bytes_before_cleanup": _tree_bytes(job),
        },
    }
    target = write_receipt(receipt_path, receipt)
    print(json.dumps({
        "status": receipt["status"],
        "receipt": str(target),
        "cases": [row["name"] for row in cases],
        "trace_seed_capture_members": receipt["trace_seed_capture_budget"]["total"],
        "gate_status": evidence.get("gate_status"),
        "neutral_status": evidence.get("neutral_model_status"),
    }, separators=(",", ":")), flush=True)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=FROZEN_REQUEST)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    job = owned_job()
    receipt_path = immutable_receipt_target(args.receipt)
    try:
        progress: dict[str, Any] = {
            "stage": "runner_started",
            "actual_capture_members": 0,
            "capture_count_status": "known",
        }
        run_gate(job, request_path=args.request, receipt_path=receipt_path, progress=progress)
    except Exception as exc:  # Keep one small immutable failure receipt too.
        failed = {
            "schema_version": 1,
            "schema_kind": "gtt_optimizer_closeout_response_receipt_v1",
            "status": "failed",
            "scope": "one Chasca Selected fixed-package changed-item response gate",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": progress.get("stage", "unknown"),
            "actual_capture_members": progress.get("actual_capture_members"),
            "capture_count_status": progress.get("capture_count_status", "unknown"),
            "frozen_request_sha256": FROZEN_REQUEST_SHA256,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1600],
            "ephemeral_cleanup": {
                "owner": "tools.managed_optimizer_experiment.managed_scratch",
                "job_bytes_before_cleanup": _tree_bytes(job),
            },
        }
        try:
            write_receipt(receipt_path, failed)
        except Exception:
            pass
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
