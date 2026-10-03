"""One-off controlled physical-build comparison for the Flins/Jahoda audit.

The two candidate ID maps come from the dated lineage5 compact receipts. This
temporary research harness keeps the *virtual* 9/9/9 profiles, rotation and
active engine fixed, varies only four five-piece artifact assignments, and
simulates both at one ordinary iteration budget. Replace it with a generic
bounded candidate-comparison utility only if the ranking-quality gate needs
further cases. The dated audit and compact receipt pin this temporary scope.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from hoyolab_export.artifact_db import calculate_raw_build_summary
from run_workspace.gcsim.artifact_runner import run_active_gcsim_artifact
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_go_selected import (
    _bound_artifact_registry_source,
)
from run_workspace.gcsim.optimizer_go_selected_inputs import (
    enforce_gcsim_optimizer_mvp_energy_policy,
)
from run_workspace.gcsim.optimizer_rotation_policy import (
    normalize_optimizer_rotation_shell,
)
from run_workspace.gcsim.selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    build_selected_team_full_config_report,
)
from run_workspace.gcsim.settings import GcsimRunSettings
from tools.experiments.gcsim.mode_matrix.run_product_matrix import (
    _scratch_environment,
    _virtual_selected_team,
)
from tools.managed_optimizer_experiment import managed_scratch


SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
OPTION_LINE = re.compile(r"(?m)^[ \t]*options[ \t]+([^;\r\n]*);[ \t]*\r?$")
ARTIFACT_LINE = re.compile(
    r"(?m)^[ \t]*[a-z0-9_]+[ \t]+add[ \t]+(?:set|stats)\b[^\r\n]*;[ \t]*\r?$"
)


def _json(relative: str) -> dict[str, Any]:
    path = (ROOT / relative).resolve(strict=True)
    path.relative_to(ROOT)
    return json.loads(path.read_text(encoding="utf-8"))


def _top_builds(receipt: dict[str, Any]) -> dict[str, dict[str, int]]:
    run = receipt["runs"][0]
    assert run["id"] in {
        "lunar_charged_all_sets", "flins_jahoda_all_sets_lineage5_exact_input"
    }
    assert run["success"] and run["mode"] == "all_sets"
    builds = run["product"]["candidates"][0]["builds"]
    output = {
        row["wearer_key"]: {slot: int(row["artifact_ids"][slot]) for slot in SLOTS}
        for row in builds
    }
    assert set(output) == {"flins", "ineffa", "columbina", "jahoda"}
    ids = [value for build in output.values() for value in build.values()]
    assert len(ids) == len(set(ids)) == 20
    return output


def _ordinary_budget(text: str, *, iterations: int, workers: int) -> str:
    matches = list(OPTION_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"Expected one options line, found {len(matches)}")
    match = matches[0]
    tokens = [
        token for token in match.group(1).split()
        if not token.startswith(("iteration=", "workers="))
    ]
    replacement = "options " + " ".join(
        [*tokens, f"iteration={iterations}", f"workers={workers}"]
    ) + ";"
    return text[:match.start()] + replacement + text[match.end():]


def _non_artifact_hash(text: str) -> str:
    neutral = ARTIFACT_LINE.sub("", text)
    return hashlib.sha256(neutral.encode("utf-8")).hexdigest()


def _build_config(
    *,
    db_path: Path,
    profiles: list[dict[str, Any]],
    selected_team: dict[str, Any],
    rotation_path: Path,
    registry_path: Path,
    ids_by_wearer: dict[str, dict[str, int]],
    case_root: Path,
    iterations: int,
) -> str:
    case_root.mkdir()
    baselines: dict[int, dict[str, Any]] = {}
    database_uri = db_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(database_uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        for slot_index, profile in enumerate(profiles):
            wearer = profile["character_key"].casefold()
            ids = ids_by_wearer[wearer]
            baselines[slot_index] = calculate_raw_build_summary(
                conn,
                slots={index: ids[slot] for index, slot in enumerate(SLOTS, 1)},
            )
            assert baselines[slot_index]["artifact_ids_by_pos"] == {
                index: ids[slot] for index, slot in enumerate(SLOTS, 1)
            }
        conn.rollback()
    report = build_selected_team_full_config_report(
        db_path=db_path,
        selected_team=selected_team,
        team_index=0,
        rotation_shell_path=rotation_path,
        run_dir=case_root,
        write_config=False,
        artifact_set_registry_source=registry_path,
        run_settings=GcsimRunSettings(boosted_energy_enabled=False),
        virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
        virtual_artifact_baselines=baselines,
    )
    if not report.ready or report.issues:
        raise RuntimeError(f"Virtual config failed preparation: {report.issues!r}")
    text = enforce_gcsim_optimizer_mvp_energy_policy(
        report.full_config.assembly.config_text, ignore_burst_energy=True
    )
    return _ordinary_budget(text, iterations=iterations, workers=4)


def main() -> None:
    virtual_source = "tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_lunar_charged_lineage5_recheck_v1.json"
    account_source = "tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_all_sets_lineage5_exact_recheck_v1.json"
    manifest_source = "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
    receipt_path = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_artifact_crosscheck_lineage5_v1.json"
    if receipt_path.exists():
        raise FileExistsError(f"Comparison receipt already exists: {receipt_path}")
    virtual_receipt = _json(virtual_source)
    account_receipt = _json(account_source)
    manifest = _json(manifest_source)
    team = manifest["teams"]["lunar_charged"]
    profiles = team["virtual_profiles"]
    selected_team = _virtual_selected_team(profiles)
    db_path = (ROOT / manifest["db_path"]).resolve(strict=True)
    rotation_source = (ROOT / team["rotation_file"]).resolve(strict=True)
    rotation_policy = normalize_optimizer_rotation_shell(
        rotation_source.read_text(encoding="utf-8")
    )
    engine = load_active_gcsim_optimizer_engine_context()
    assert engine.engine_id == "gcsim-v2.45.0-observed-modifier-lineage5-20260919"
    for source in (virtual_receipt, account_receipt):
        expected = source["runs"][0]["engine_identity"]
        if engine.artifact_sha256 != expected["artifact_sha256"]:
            raise ValueError("Active executable differs from source receipt")
    registry = _bound_artifact_registry_source(Path(engine.engine_root))
    iterations = 1000
    rows = []
    with managed_scratch() as scratch, _scratch_environment(scratch):
        effective_rotation = scratch / "rotation.optimizer.txt"
        effective_rotation.write_text(rotation_policy.optimizer_text, encoding="utf-8")
        for name, source, source_path in (
            ("virtual_top1", virtual_receipt, virtual_source),
            ("account_top1", account_receipt, account_source),
        ):
            case_root = scratch / name
            ids = _top_builds(source)
            config = _build_config(
                db_path=db_path,
                profiles=profiles,
                selected_team=selected_team,
                rotation_path=effective_rotation,
                registry_path=registry,
                ids_by_wearer=ids,
                case_root=case_root,
                iterations=iterations,
            )
            outcome = run_active_gcsim_artifact(
                config,
                run_dir=case_root / "ordinary",
                timeout_seconds=240,
                expected_engine_id=engine.engine_id,
            )
            if not outcome.success or outcome.summary.iterations != iterations:
                raise RuntimeError(
                    f"{name} ordinary simulation failed: {outcome.status}: {outcome.error}"
                )
            row = {
                "name": name,
                "source_receipt": source_path,
                "artifact_ids": ids,
                "config_sha256": hashlib.sha256(config.encode("utf-8")).hexdigest(),
                "non_artifact_sha256": _non_artifact_hash(config),
                "iterations": outcome.summary.iterations,
                "dps": outcome.summary.dps_mean,
                "standard_error": outcome.summary.dps_se,
                "duration_mean": outcome.summary.duration_mean,
                "failed_actions": list(outcome.summary.failed_actions),
            }
            rows.append(row)
            print(f"{name}: {row['dps']:.3f} ± {row['standard_error']:.3f} DPS", flush=True)
        if rows[0]["non_artifact_sha256"] != rows[1]["non_artifact_sha256"]:
            raise AssertionError("Character, weapon, target or rotation changed")
        after = load_active_gcsim_optimizer_engine_context()
        if (after.engine_id, after.artifact_sha256) != (
            engine.engine_id, engine.artifact_sha256
        ):
            raise AssertionError("Active engine changed during comparison")
        output = {
            "schema_version": 1,
            "scope": "virtual_lunar_charged_same_profiles_rotation_engine_change_artifacts_only",
            "manifest": manifest_source,
            "rotation_file": team["rotation_file"],
            "rotation_normalized": rotation_policy.changed,
            "database_variant": "live_read_only",
            "energy_mode": "infinite",
            "engine_id": engine.engine_id,
            "engine_artifact_sha256": engine.artifact_sha256,
            "iterations_per_case": iterations,
            "cases": rows,
            "account_minus_virtual_dps": rows[1]["dps"] - rows[0]["dps"],
            "status": "complete_backend_control_not_ui_click",
        }
        receipt_path.write_text(
            json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Receipt: {receipt_path}", flush=True)


if __name__ == "__main__":
    main()
