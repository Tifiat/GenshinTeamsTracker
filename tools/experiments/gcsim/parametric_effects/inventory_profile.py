"""Temporary source-only full-inventory preparation for the saved Flins gate.

No new capture or account mutation here. Reuse the managed neutral/control pair,
check its twenty baseline vectors against current inventory, and time the source
coordinator for 60 seconds. This is preparation profiling, not installed product
or quality acceptance. All files live in the existing managed job and are removed
with it; replace this entrypoint after the real single-team product gate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
SLOTS = ("flower", "plume", "sands", "goblet", "circlet")


def bind_saved_reference(request: dict, saved: dict, stat_keys: dict) -> dict:
    """Fail before scoring when a saved physical witness no longer matches."""
    out = deepcopy(request)
    items = {a["artifact_id"]: a for a in out["artifacts"]}
    config = saved["config"]
    used = set()
    for wearer in out["wearers"]:
        actor = wearer["wearer_key"]
        ids = saved["reference_ids"][actor]
        stats, counts = defaultdict(float), Counter()
        wearer["current_artifacts"] = []
        for slot in SLOTS:
            artifact_id = ids[slot]
            item = items[artifact_id]
            if item["slot"] != slot or artifact_id in used:
                raise ValueError("Saved reference is not a legal twenty-ID assignment")
            used.add(artifact_id)
            counts[item["set_uid"]] += 1
            for stat in [item["main_stat"], *item["substats"]]:
                stats[stat["key"]] += float(stat["value"])
            wearer["current_artifacts"].append(dict(wearer_key=actor, slot=slot, artifact_id=artifact_id))
        rows = re.findall(rf"(?m)^{re.escape(actor)} add stats ([^;]+);$", config)
        if len(rows) != 1:
            raise ValueError("Reference config needs exactly one artifact stat row")
        expected = {stat_keys[k]: float(v) for k, v in (x.split("=", 1) for x in rows[0].split())}
        if any(not math.isclose(stats.get(k, 0), expected.get(k, 0), rel_tol=0, abs_tol=1e-8)
               for k in stats.keys() | expected.keys()):
            raise ValueError(f"Saved artifact vector changed: {actor}")
        packages = [(key, min(4, n // 2 * 2)) for key, n in counts.items() if n >= 2]
        declared = [(k, min(4, int(n) // 2 * 2)) for k, n in re.findall(
            rf'(?m)^{re.escape(actor)} add set="([a-z0-9]+)" count=([2-5]);$', config)]
        if sorted(packages) != sorted(declared) or len(packages) != 1 or packages[0][1] != 4:
            raise ValueError("Saved initial 4p package differs from physical inventory")
        wearer.pop("selected_sets", None)
        wearer["selected_set_uid"] = packages[0][0]
    out["legality"]["fixed_four_piece"] = True
    out["legality"]["fixed_set_packages"] = False
    from run_workspace.gcsim.source_manifest_build import canonical_json
    sha = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    context = out["context"]
    context["prepared_config"] = {"text": config, "sha256": sha(config)}
    context["trace_context_sha256"] = sha(config)
    context["context_sha256"] = sha(canonical_json({
        "prepared_config_sha256": sha(config),
        "rotation_sha256": context["rotation"]["sha256"],
        "target_sha256": context["target"]["sha256"],
    }))
    return out


def prepare_inventory_profile(job: Path) -> dict[str, str]:
    if str(job) != os.environ.get("GTT_SCRATCH_DIR") or job.parent != ROOT / ".codex_tmp/managed-optimizer":
        raise ValueError("Inventory profile requires the existing managed job")
    from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs, _STAT_KEY
    from run_workspace.gcsim.selected_team_config import VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE
    from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request
    manifest = json.loads((ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json").read_bytes())
    saved = json.loads((ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json").read_bytes())
    prepared_dir = job / "inventory-prepared"
    prepared_dir.mkdir()
    entry = dict(manifest["teams"]["lunar_charged"], mode="all_sets")
    prepared = _prepare_inputs(_request(entry, db_path=ROOT / manifest["db_path"], run_root=job), prepared_dir,
                               virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE)
    request = prepared["request"]
    if any(request["engine"][k] != saved["engine"][k] for k in ("artifact_sha256", "source_manifest_sha256")):
        raise ValueError("Selected engine differs from the dated source profile")
    request = bind_saved_reference(request, saved["inputs"][0], _STAT_KEY)
    path = job / "inventory-request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    print(f"Inventory profile: {len(request['artifacts'])} physical artifacts; saved twenty-ID vectors verified; one seed, no ordinary verification.", flush=True)
    return {"GTT_NEUTRAL_INVENTORY_REQUEST": str(path)}
