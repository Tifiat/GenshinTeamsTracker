"""GOB-3E: bind and aggregate the existing two real compact members.

This audit never starts GCSIM.  It materializes one real standalone request,
wraps the two GOB-3D members, runs the Go fixed-panel aggregator at zero
artifact delta, and compares it with an independent Python baseline reduction.
All large/private account payloads stay below .codex_tmp; only the small receipt
is intended to be retained.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from time import perf_counter

from run_workspace.gcsim.optimizer_artifact_database import (
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from run_workspace.gcsim.optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
    GCSIM_OPTIMIZER_GO_REQUEST_KIND,
    GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
    GCSIM_OPTIMIZER_GO_STRATEGY_ID,
    canonical_json_bytes,
    canonical_sha256,
    text_sha256,
)
from run_workspace.gcsim.trace_equation.same_context_acceptance import (
    build_current_same_context_acceptance_input,
)
from tools.experiments.gcsim_trace_support_objective_v1_audit import (
    DATABASE_PATH,
    ROOT,
    STORE,
)


STAGING_ROOT = ROOT / ".codex_tmp" / "gob3_staging_source"
STAGING_BUILD = STAGING_ROOT / "build" / "gob3"
STAGING_ENGINE = STAGING_BUILD / "gtt-gcsim-gob3.exe"
GO_ROOT = ROOT / "native" / "gcsim_optimizer"
AUDIT_DIR = ROOT / ".codex_tmp" / "gob3e_real_panel"
RECEIPT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "gcsim_optimizer_go_v1"
    / "gob3e_real_panel_parity_receipt_v1.json"
)
SEEDS = (742031889, 742031890)
SOURCE_MANIFEST_SHA256 = (
    "b3c8b25eeaee4ca7b80f8f422f66703936bc95fb8a379a993d89a08799559977"
)
PATCH_MANIFEST_SHA256 = (
    "fd63f04802d97a2ae49a3546a3039736b1794426f4b064d53327da45a24ccf6a"
)
PARITY_TOLERANCE = 1e-6

_WEAPON_RE = re.compile(
    r'(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+weapon="(?P<weapon>[^"]+)"'
)
_STAT_KEY = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "hp%": "hp_percent",
    "atk%": "atk_percent",
    "def%": "def_percent",
    "em": "em",
    "er": "energy_recharge",
    "cr": "crit_rate",
    "cd": "crit_damage",
    "pyro%": "pyro_damage_bonus",
    "hydro%": "hydro_damage_bonus",
    "electro%": "electro_damage_bonus",
    "cryo%": "cryo_damage_bonus",
    "anemo%": "anemo_damage_bonus",
    "geo%": "geo_damage_bonus",
    "dendro%": "dendro_damage_bonus",
    "phys%": "physical_damage_bonus",
    "heal": "healing_bonus",
}


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    acceptance = build_current_same_context_acceptance_input(
        engine_store_dir=STORE,
        database_path=DATABASE_PATH,
    )
    request = _build_request(acceptance)
    request_sha256 = canonical_sha256(request)
    members = tuple(_load_member(seed) for seed in SEEDS)
    compact = {
        "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
        "schema_kind": GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
        "request_sha256": request_sha256,
        "engine_binding_sha256": request["engine"]["binding_sha256"],
        "context_sha256": request["context"]["trace_context_sha256"],
        "members": list(members),
    }
    request_path = AUDIT_DIR / "request.json"
    compact_path = AUDIT_DIR / "compact.json"
    deltas_path = AUDIT_DIR / "zero-deltas.json"
    binary_path = AUDIT_DIR / "gtt-optimizer-gob3e.exe"
    result_path = AUDIT_DIR / "aggregate-result.json"
    request_path.write_bytes(canonical_json_bytes(request) + b"\n")
    compact_path.write_bytes(canonical_json_bytes(compact) + b"\n")
    deltas_path.write_text("{}\n", encoding="utf-8")

    subprocess.run(
        ("go", "build", "-o", str(binary_path), "./cmd/gtt-optimizer"),
        cwd=GO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    started = perf_counter()
    completed = subprocess.run(
        (
            str(binary_path),
            "aggregate-fixed-panel",
            str(request_path),
            str(compact_path),
            str(deltas_path),
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0
    result_path.write_text(completed.stdout, encoding="utf-8")
    result = json.loads(completed.stdout)
    python = _python_landmarks(members)
    checks = _parity_checks(result, python)
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"GOB-3E parity failed: {failed!r}")

    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_gob3e_real_panel_parity_receipt_v1",
        "status": "PASS",
        "engine_executions": 0,
        "search_executions": 0,
        "n1000_executions": 0,
        "request": {
            "request_sha256": request_sha256,
            "source_context_sha256": request["context"]["context_sha256"],
            "trace_context_sha256": request["context"]["trace_context_sha256"],
            "engine_binding_sha256": request["engine"]["binding_sha256"],
            "artifact_count": len(request["artifacts"]),
            "wearer_count": len(request["wearers"]),
            "incumbent_artifact_count": 20,
        },
        "compact_ir_sha256": canonical_sha256(compact),
        "members": result["members"],
        "aggregate": {
            "mean_dps": _decimal(result["candidate_mean_dps"]),
            "sample_sd_dps": _decimal(
                result["sample_standard_deviation_dps"]
            ),
            "standard_error_dps": _decimal(result["standard_error_dps"]),
            "by_actor": result["candidate_by_actor"],
            "opaque_reason_classes": len(result["opaque_reasons"]),
        },
        "python_reference": python,
        "absolute_tolerance": _decimal(PARITY_TOLERANCE),
        "parity_checks": checks,
        "go_process_elapsed_ms": _decimal(elapsed_ms),
        "large_payloads_retained_only_in_ignored_temp": True,
        "next_stage": "GOB-3F_measure_repeat_runtime_and_memory_without_engine_execution",
    }
    RECEIPT_PATH.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


def _build_request(acceptance) -> dict[str, object]:
    loaded = load_gcsim_optimizer_artifact_database_input(
        DATABASE_PATH,
        engine_context=acceptance.engine_context,
    )
    if not loaded.ready or loaded.database_input is None:
        raise RuntimeError(f"artifact database unavailable: {loaded.issues!r}")
    database = loaded.database_input
    reference_wearer = acceptance.snapshot.wearers[0].wearer
    artifacts = []
    for artifact in database.artifacts:
        if not artifact.default_eligible or not artifact.gcsim_set_key:
            continue
        materialized = materialize_gcsim_optimizer_artifact_stat_vector(
            artifact,
            wearer=reference_wearer,
        )
        if not materialized.ready or materialized.stat_vector is None:
            raise RuntimeError(f"artifact {artifact.artifact_id} did not materialize")
        main = [
            row for row in materialized.stat_vector.contributions
            if row.source_kind == "main"
        ]
        substats = [
            row for row in materialized.stat_vector.contributions
            if row.source_kind == "substat"
        ]
        if len(main) != 1:
            raise RuntimeError(f"artifact {artifact.artifact_id} has invalid main stat")
        artifacts.append(
            {
                "artifact_id": artifact.artifact_id,
                "slot": artifact.position_key,
                "set_uid": artifact.gcsim_set_key.casefold(),
                "rarity": artifact.rarity,
                "level": artifact.level,
                "main_stat": {
                    "key": _stat_key(main[0].gcsim_key),
                    "value": main[0].normalized_value,
                },
                "substats": sorted(
                    (
                        {
                            "key": _stat_key(row.gcsim_key),
                            "value": row.normalized_value,
                        }
                        for row in substats
                    ),
                    key=lambda row: row["key"],
                ),
            }
        )
    weapons = {
        match.group("actor").casefold(): match.group("weapon").casefold()
        for match in _WEAPON_RE.finditer(acceptance.config_text)
    }
    wearers = []
    for wearer in sorted(acceptance.wearers, key=lambda row: row.actor_key):
        selected = [key for key, count in wearer.active_sets if count >= 4]
        if len(selected) != 1:
            raise RuntimeError(f"{wearer.actor_key} has no unique fixed set")
        wearers.append(
            {
                "wearer_key": wearer.actor_key,
                "weapon_key": weapons[wearer.actor_key],
                "selected_set_uid": selected[0],
                "current_artifacts": [
                    {
                        "wearer_key": wearer.actor_key,
                        "slot": slot,
                        "artifact_id": artifact_id,
                    }
                    for slot, artifact_id in wearer.artifact_ids_by_slot
                ],
            }
        )
    rotation_text = Path(acceptance.rotation_shell_path).read_text(encoding="utf-8")
    target_text = acceptance.target_line + "\n"
    context = {
        "prepared_config": _source_text(acceptance.config_text),
        "rotation": _source_text(rotation_text),
        "target": _source_text(target_text),
    }
    context["context_sha256"] = canonical_sha256(
        {
            "prepared_config_sha256": context["prepared_config"]["sha256"],
            "rotation_sha256": context["rotation"]["sha256"],
            "target_sha256": context["target"]["sha256"],
        }
    )
    context["trace_context_sha256"] = acceptance.context_sha256
    artifact_sha256 = _file_sha256(STAGING_ENGINE)
    engine_binding_sha256 = canonical_sha256(
        {
            "kind": "gtt.standalone_engine_binding.v1",
            "artifact_sha256": artifact_sha256,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "patch_manifest_sha256": PATCH_MANIFEST_SHA256,
        }
    )
    return {
        "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
        "schema_kind": GCSIM_OPTIMIZER_GO_REQUEST_KIND,
        "strategy_id": GCSIM_OPTIMIZER_GO_STRATEGY_ID,
        "engine": {
            "binary_path": str(STAGING_ENGINE.resolve()).replace("\\", "/"),
            "artifact_sha256": artifact_sha256,
            "binding_sha256": engine_binding_sha256,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "patch_manifest_sha256": PATCH_MANIFEST_SHA256,
            "capabilities": ["gtt_compact_equation_v1", "gtt_trace_equation_v6"],
        },
        "context": context,
        "wearers": wearers,
        "artifacts": artifacts,
        "legality": {
            "fixed_four_piece": True,
            "max_off_set_pieces_per_wearer": 1,
            "globally_unique_artifact_ids": True,
            "default_minimum_rarity": 5,
            "authorized_lower_rarity_artifact_ids": [],
        },
        "stochastic": {
            "mode": "equal_weight_fixed_panel_v1",
            "seeds": list(SEEDS),
        },
        "budgets": {
            "product_timeout_ms": 190000,
            "development_timeout_ms": 360000,
        },
        "cancellation": {"mode": "process_interrupt_v1"},
    }


def _load_member(seed: int) -> dict[str, object]:
    path = STAGING_BUILD / f"compact-member-{seed}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _python_landmarks(members: tuple[dict[str, object], ...]) -> dict[str, object]:
    member_dps = []
    actor_damage: dict[str, list[float]] = defaultdict(list)
    reasons: dict[str, list[int]] = defaultdict(list)
    actors = ("bennett", "chasca", "furina", "ororon")
    for member in members:
        duration = float(member["duration_ms"]) / 1000.0
        totals: dict[str, list[float]] = defaultdict(list)
        for channel in member["channels"]:
            totals[channel["actor_key"]].append(float(channel["baseline_damage"]))
        damage = math.fsum(math.fsum(totals[actor]) for actor in actors)
        member_dps.append(damage / duration)
        for actor in actors:
            actor_damage[actor].append(math.fsum(totals[actor]))
        for reason in sorted({row["reason_code"] for row in member["opaque_boundaries"]}):
            reasons[reason].append(int(member["seed"]))
    mean_dps = math.fsum(member_dps) / len(member_dps)
    variance = math.fsum((value - mean_dps) ** 2 for value in member_dps) / (
        len(member_dps) - 1
    )
    sd = math.sqrt(variance)
    duration = float(members[0]["duration_ms"]) / 1000.0
    return {
        "member_dps": [_decimal(value) for value in member_dps],
        "mean_dps": _decimal(mean_dps),
        "sample_sd_dps": _decimal(sd),
        "standard_error_dps": _decimal(sd / math.sqrt(len(member_dps))),
        "by_actor": [
            {
                "actor_key": actor,
                "damage": _decimal(math.fsum(actor_damage[actor]) / len(members)),
                "dps": _decimal(
                    (math.fsum(actor_damage[actor]) / len(members)) / duration
                ),
            }
            for actor in actors
        ],
        "opaque_reasons": [
            {"reason_code": reason, "seeds": reasons[reason]}
            for reason in sorted(reasons)
        ],
    }


def _parity_checks(result: dict[str, object], python: dict[str, object]) -> dict[str, bool]:
    close = lambda left, right: abs(float(left) - float(right)) <= PARITY_TOLERANCE
    actor_go = {row["actor_key"]: row for row in result["candidate_by_actor"]}
    actor_py = {row["actor_key"]: row for row in python["by_actor"]}
    return {
        "member_dps": all(
            close(row["dps"], expected)
            for row, expected in zip(result["members"], python["member_dps"], strict=True)
        ),
        "mean_dps": close(result["candidate_mean_dps"], python["mean_dps"]),
        "sample_sd_dps": close(
            result["sample_standard_deviation_dps"], python["sample_sd_dps"]
        ),
        "standard_error_dps": close(
            result["standard_error_dps"], python["standard_error_dps"]
        ),
        "actor_damage_and_dps": actor_go.keys() == actor_py.keys()
        and all(
            close(actor_go[key]["damage"], actor_py[key]["damage"])
            and close(actor_go[key]["dps"], actor_py[key]["dps"])
            for key in actor_py
        ),
        "opaque_reason_seed_coverage": result["opaque_reasons"]
        == python["opaque_reasons"],
        "zero_delta": close(result["delta_mean_damage"], 0)
        and close(result["delta_mean_dps"], 0),
    }


def _source_text(text: str) -> dict[str, str]:
    return {"text": text, "sha256": text_sha256(text)}


def _stat_key(key: str) -> str:
    try:
        return _STAT_KEY[key]
    except KeyError as exc:
        raise RuntimeError(f"unsupported artifact stat key {key!r}") from exc


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal(value: float) -> str:
    return format(Decimal(str(value)), "f")


if __name__ == "__main__":
    main()
