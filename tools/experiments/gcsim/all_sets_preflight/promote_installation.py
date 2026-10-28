"""Promote only the prepared All Sets bundle; keep exact local rollback copies.

One-shot deployment receipt for this accepted experiment, not a new updater.
No simulations, account writes, pruning or recursive deletion.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.optimizer_go_all import all_sets_available

out = root / ".codex_tmp/all-sets-install-20260917"
receipt = json.loads((out / "prepare-receipt.json").read_bytes())
if receipt["status"] != "prepared_crlf_equivalent_bundle_and_winner_pass_not_activated":
    raise SystemExit("preparation gate missing")
store = GcsimEngineStore()
before = json.loads((out / "active-before.json").read_bytes())
if json.loads(store.active_state_path.read_bytes()) != before:
    raise SystemExit("active state changed")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
patch = root / "run_workspace/gcsim/patch_stack/0001-gtt-engine-adapter-v245.patch"
consumer = root / "native/gcsim_optimizer/gtt-optimizer.exe"
candidate_patch = root / ".codex_tmp/all-sets-observer-candidate-20260916/patch_stack" / patch.name
candidate_consumer = out / consumer.name
engine = store.engines_dir / receipt["engine_id"] / "build/gtt-gcsim.exe"
for path, key in ((engine, "engine_sha256"), (candidate_patch, "patch_sha256"), (candidate_consumer, "consumer_sha256")):
    if sha(path) != receipt[key]:
        raise SystemExit("validated bytes changed: " + str(path))
backup = out / "rollback"
backup.mkdir(exist_ok=False)
shutil.copy2(patch, backup / patch.name)
shutil.copy2(consumer, backup / consumer.name)
shutil.copy2(store.active_state_path, backup / store.active_state_path.name)
try:
    for source, target in ((candidate_patch, patch), (candidate_consumer, consumer)):
        staged = target.with_name(target.name + ".allsets-pending")
        if staged.exists():
            raise RuntimeError("unexpected pending deployment file")
        shutil.copy2(source, staged)
        staged.replace(target)
    installed = store.activate_engine(receipt["engine_id"])
    if not all_sets_available():
        raise RuntimeError("installed All Sets display capability unavailable")
    if sha(patch) != receipt["patch_sha256"] or sha(consumer) != receipt["consumer_sha256"]:
        raise RuntimeError("promoted bytes differ")
except BaseException:
    shutil.copy2(backup / patch.name, patch)
    shutil.copy2(backup / consumer.name, consumer)
    shutil.copy2(backup / store.active_state_path.name, store.active_state_path)
    raise
result = {**receipt, "status": "installed_backend_pass_ui_pending",
          "rollback_engine_id": before["active_engine_id"], "ui_click_verified": False,
          "ui_blocker": "native_windows_computer_use_tools_unavailable",
          "rollback_patch_sha256": sha(backup / patch.name),
          "rollback_consumer_sha256": sha(backup / consumer.name)}
(out / "installation-receipt.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
