"""One-off profile/build control for the user's 188k Flins UI run.

The saved UI request is the authority for rotation, talents, weapons and active
engine. This temporary diagnostic reuses the exact raw-artifact renderer from
the dated Flins cross-check, keeping all non-artifact config lines identical.
Generated configs/results live only in managed scratch; the compact receipt is
retained until the All Sets ranking-quality gate is resolved.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.artifact_runner import run_active_gcsim_artifact
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_go_selected import _bound_artifact_registry_source
from run_workspace.gcsim.optimizer_go_selected_inputs import (
    enforce_gcsim_optimizer_mvp_energy_policy,
)
from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
    SLOTS, _build_config, _non_artifact_hash, _ordinary_budget, _top_builds,
)
from tools.experiments.gcsim.mode_matrix.run_product_matrix import (
    _scratch_environment, _virtual_selected_team,
)
from tools.managed_optimizer_experiment import managed_scratch


APP_RUN = ROOT / "data/gcsim/optimizer-go-runs/all_sets-20260919-152727-f767b4b8"
ACCOUNT_RECEIPT = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_all_sets_lineage5_exact_recheck_v1.json"
MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
RECEIPT = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/flins_ui_188_cross_assignment_lineage5_v1.json"
CHAR_LINE = re.compile(r"(?m)^([a-z0-9_]+) char lvl=(\d+)/(\d+) cons=(\d+) talent=(\d+),(\d+),(\d+);$")
WEAPON_LINE = re.compile(r'(?m)^([a-z0-9_]+) add weapon="([a-z0-9_]+)" refine=(\d+) lvl=(\d+)/(\d+);$')


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _profiles(config: str, manifest: dict) -> list[dict]:
    chars = {match[0]: match for match in CHAR_LINE.findall(config)}
    weapons = {match[0]: match for match in WEAPON_LINE.findall(config)}
    result = []
    for original in manifest["teams"]["lunar_charged"]["virtual_profiles"]:
        key = original["character_key"]
        char, weapon = chars[key], weapons[key]
        if int(char[1]) != 90 or int(char[2]) != 90 or int(weapon[3]) != 90 or int(weapon[4]) != 90:
            raise ValueError("This one-off comparison expects level 90/90 profiles")
        result.append({
            "character_key": key,
            "constellation": int(char[3]),
            "talents": [int(value) for value in char[4:7]],
            "weapon_key": weapon[1],
            "refinement": int(weapon[2]),
            "character_level": 90,
            "weapon_level": 90,
        })
    if set(chars) != {row["character_key"] for row in result} or set(weapons) != set(chars):
        raise ValueError("UI team members differ from the virtual control team")
    return result


def _ui_top1(result: dict) -> dict[str, dict[str, int]]:
    assignments = result["candidates"][0]["artifacts"]
    output: dict[str, dict[str, int]] = {}
    for row in assignments:
        output.setdefault(row["wearer_key"], {})[row["slot"]] = int(row["artifact_id"])
    if set(output) != {"flins", "ineffa", "columbina", "jahoda"}:
        raise ValueError("UI winner has a different roster")
    if any(set(build) != set(SLOTS) for build in output.values()):
        raise ValueError("UI winner does not provide five artifacts per wearer")
    if len({item for build in output.values() for item in build.values()}) != 20:
        raise ValueError("UI winner shares a physical artifact")
    return output


def main() -> None:
    if RECEIPT.exists():
        raise FileExistsError(RECEIPT)
    request, result = _read(APP_RUN / "request.json"), _read(APP_RUN / "selected-result.json")
    manifest = _read(MANIFEST)
    account = _read(ACCOUNT_RECEIPT)
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.artifact_sha256 != request["engine"]["artifact_sha256"]:
        raise ValueError("The saved UI request is not bound to the active executable")
    source_config = request["context"]["prepared_config"]["text"]
    profiles = _profiles(source_config, manifest)
    selected_team = _virtual_selected_team(profiles)
    source_config = _ordinary_budget(
        enforce_gcsim_optimizer_mvp_energy_policy(source_config, ignore_burst_energy=True),
        iterations=1000, workers=4,
    )
    base_non_artifact = _non_artifact_hash(source_config)
    rotation_text = (APP_RUN / "rotation.from-ui.txt").read_text(encoding="utf-8")
    if rotation_text != (ROOT / manifest["teams"]["lunar_charged"]["rotation_file"]).read_text(encoding="utf-8"):
        raise ValueError("UI rotation differs from the 108k virtual fixture")
    cases = (
        ("ui_top1", _ui_top1(result)),
        ("account_191k_top1", _top_builds(account)),
    )
    rows = []
    with managed_scratch() as scratch, _scratch_environment(scratch):
        rotation_path = scratch / "rotation.txt"
        rotation_path.write_text(rotation_text, encoding="utf-8")
        for name, ids in cases:
            root = scratch / name
            config = _build_config(
                db_path=(ROOT / manifest["db_path"]).resolve(strict=True),
                profiles=profiles,
                selected_team=selected_team,
                rotation_path=rotation_path,
                registry_path=_bound_artifact_registry_source(Path(engine.engine_root)),
                ids_by_wearer=ids,
                case_root=root,
                iterations=1000,
            )
            if _non_artifact_hash(config) != base_non_artifact:
                raise ValueError(f"{name}: non-artifact config differs from UI request")
            output = run_active_gcsim_artifact(
                config, run_dir=root / "ordinary", timeout_seconds=240,
                expected_engine_id=engine.engine_id,
            )
            if not output.success or output.summary.iterations != 1000:
                raise RuntimeError(f"{name}: {output.status}: {output.error}")
            row = {
                "name": name,
                "artifact_ids": ids,
                "config_sha256": hashlib.sha256(config.encode("utf-8")).hexdigest(),
                "non_artifact_sha256": _non_artifact_hash(config),
                "dps": output.summary.dps_mean,
                "standard_error": output.summary.dps_se,
                "duration_mean": output.summary.duration_mean,
                "iterations": output.summary.iterations,
            }
            rows.append(row)
            print(f"{name}: {row['dps']:.3f} +/- {row['standard_error']:.3f}", flush=True)
        after = load_active_gcsim_optimizer_engine_context()
        if (after.engine_id, after.artifact_sha256) != (engine.engine_id, engine.artifact_sha256):
            raise ValueError("Active executable changed during comparison")
        receipt = {
            "schema_version": 1,
            "scope": "same_saved_ui_profile_rotation_active_engine_artifacts_only",
            "app_run": APP_RUN.name,
            "app_reported_top1_dps": result["candidates"][0]["measured"]["dps"],
            "profiles_from_ui_request": profiles,
            "engine_id": engine.engine_id,
            "engine_artifact_sha256": engine.artifact_sha256,
            "non_artifact_sha256": base_non_artifact,
            "cases": rows,
            "account_minus_ui_dps": rows[1]["dps"] - rows[0]["dps"],
            "status": "backend_control_not_ui_click",
        }
        RECEIPT.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"Receipt: {RECEIPT}", flush=True)


if __name__ == "__main__":
    main()
