"""Prepare/verify the accepted All Sets engine+consumer without activation.

Uses the normal clean-source updater with the consolidated candidate patch.
Three tiny bundle smokes plus two saved-winner controls after source verification. No pruning,
live equipment/setting writes or activation. A separate explicit step promotes.
"""
from dataclasses import replace
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
from run_workspace.gcsim.engine_update import prepare_official_gcsim_engine_update
from run_workspace.gcsim.engine_store import GcsimEngineStore, load_engine_manifest, _write_manifest
from run_workspace.gcsim.engine_compatibility import verify_engine_application_bundle
from run_workspace.gcsim.patch_backends import GitApplyPatchBackend
from run_workspace.gcsim.source_acquisition import OfficialGcsimSourceAcquisition, OfficialGcsimSourceRef
from run_workspace.gcsim.tree_identity import directory_sha256
from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources

candidate = root / ".codex_tmp/all-sets-observer-candidate-20260916"
out = root / ".codex_tmp/all-sets-install-20260917"
parser = argparse.ArgumentParser(__doc__)
parser.add_argument("--resume", action="store_true")
args = parser.parse_args()
out.mkdir(exist_ok=args.resume)
gate = json.loads((root / ".codex_tmp/all-sets-cli-20260917-run2/cli-receipt.json").read_bytes())
if gate["exit_code"] != 0:
    raise SystemExit("cold CLI gate did not pass")
build = json.loads((candidate / "build-summary.json").read_bytes())
store = GcsimEngineStore()
before = json.loads((out / "active-before.json").read_bytes()) if args.resume else json.loads(store.active_state_path.read_bytes())
if not args.resume:
    (out / "active-before.json").write_text(json.dumps(before), encoding="utf-8")
if json.loads(store.active_state_path.read_bytes()) != before:
    raise SystemExit("active engine changed; re-evaluate before resuming")
binary = out / "gtt-optimizer.exe"
if not args.resume:
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "build", "-o", str(binary), "./cmd/gtt-optimizer"], cwd=root / "native/gcsim_optimizer", check=True)
acquisition = OfficialGcsimSourceAcquisition(
    OfficialGcsimSourceRef("v2.45.0", "v2.45.0", "cached-official-archive", "", ""),
    root / "data/gcsim/sources/archives/v2.45.0.zip",
    candidate / "upstream/expanded/v2.45.0", candidate / "upstream")
engine_id = "gcsim-v2.45.0-allsets-20260917"
report = None if args.resume else prepare_official_gcsim_engine_update(
    release="v2.45.0", engine_id=engine_id, patch_stack_dir=candidate / "patch_stack",
    source_acquirer=lambda **kwargs: acquisition, patch_backend=GitApplyPatchBackend(),
    build_artifact=True, go_executable="C:/Program Files/Go/bin/go.exe",
    runtime_probe_timeout_seconds=300, activate=False, prune_engine_store=False,
    clean_go_build_cache=False)
if report is not None:
    (out / "prepare-report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
prepared_report = json.loads((out / "prepare-report.json").read_bytes())
if not prepared_report["success"]:
    raise SystemExit(prepared_report["error"])
installed = store.engines_dir / engine_id
manifest = load_engine_manifest(installed)
meta = dict(manifest.metadata)
engine_binary = installed / meta["artifact_relative_path"]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if sha(engine_binary) != prepared_report["artifact_sha256"]:
    raise SystemExit("prepared engine bytes changed")

def module_files(folder):
    result = {}
    for current, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in {"build", ".git"}]
        for name in files:
            path = Path(current) / name
            relative = path.relative_to(folder).as_posix()
            if relative not in {"pkg/gttsource/generated_manifest.go", "gtt_engine_manifest.json"}:
                result[relative] = path.read_bytes()
    return result

old_files, new_files = module_files(candidate / "source"), module_files(installed)
if old_files.keys() != new_files.keys():
    raise SystemExit("prepared module file inventory differs")
eol_only = []
for name, original in old_files.items():
    actual = new_files[name]
    if original != actual:
        if original.replace(b"\r\n", b"\n") != actual.replace(b"\r\n", b"\n"):
            raise SystemExit("prepared module content differs: " + name)
        eol_only.append(name)
old_body = json.loads((candidate / "source/build/gtt-source-manifest-body.json").read_bytes())
new_body = json.loads((installed / "build/gtt-source-manifest-body.json").read_bytes())
if {k: v for k, v in old_body.items() if k != "patched_source_tree_sha256"} != {k: v for k, v in new_body.items() if k != "patched_source_tree_sha256"}:
    raise SystemExit("generated source semantics differ beyond exact tree identity")
(out / "source-equivalence.json").write_text(json.dumps({"status": "crlf_only", "files": sorted(eol_only), "file_count": len(old_files)}, indent=2), encoding="utf-8")

# Build-only absolute overlay locations must follow the updater's staging move.
# Arithmetic/source bytes and the compiled binary remain unchanged. Both sides
# are checked inside their explicit roots before replacing generated metadata.
overlay_path = installed / meta["source_manifest_overlay_relative_path"]
overlay = json.loads(overlay_path.read_bytes())
staged = (store.staging_dir / engine_id).resolve()
relocated = {}
for original, replacement in overlay["Replace"].items():
    base = installed.resolve() if Path(original).resolve().is_relative_to(installed.resolve()) else staged
    old_relative = Path(original).resolve().relative_to(base)
    new_relative = Path(replacement).resolve().relative_to(base)
    src, dst = (installed / old_relative).resolve(), (installed / new_relative).resolve()
    src.relative_to(installed.resolve()); dst.relative_to(installed.resolve())
    if not src.is_file() or not dst.is_file():
        raise SystemExit("relocated overlay points outside prepared files")
    relocated[str(src)] = str(dst)
overlay_path.write_text(json.dumps({"Replace": relocated}), encoding="utf-8")
probe = SimpleNamespace(**{**build, "artifact_path": str(engine_binary), "artifact_sha256": sha(engine_binary)})
error = verify_engine_application_bundle(installed, probe, optimizer_binary=binary)
if error:
    raise SystemExit(error)
# Validate the same installed-root source adapter used by the actual UI worker.
binding = {"binary_path": str(engine_binary), "artifact_sha256": sha(engine_binary),
           "source_manifest_sha256": meta["source_manifest_body_sha256"],
           "capabilities": json.loads(meta["gtt_capabilities"])}
sources = prepare_all_set_effect_sources(installed, binding)

# Preserve the exact accepted configs/seeds, comparing fresh installed output
# with the earlier candidate's response receipt; never rewrite prior evidence.
control_root = root / ".codex_tmp/all-sets-transfer-winner-20260917-run2"
expected = json.loads((control_root / "winner-response-receipt.json").read_bytes())
actual_dps = []
for index, prior in enumerate(sorted(control_root.glob("winner-*"))):
    if not prior.is_dir():
        continue
    target = out / prior.name
    target.mkdir(exist_ok=False)
    output = target / "member.json"
    subprocess.run([str(engine_binary), "-c", str(prior / "config.txt"), "-out", str(output),
                    "-gtt-trace-equation", str(prior / "capture-request.json")],
                   capture_output=True, check=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    subprocess.run([str(binary), "validate-seed-member", str(output)], capture_output=True, check=True, timeout=30)
    member = json.loads(output.read_bytes())
    dps = sum(float(ch["baseline_damage"]) for ch in member["channels"]) * 1000 / member["duration_ms"]
    if not math.isclose(dps, expected["per_seed_expected_dps"][len(actual_dps)], rel_tol=1e-9):
        raise SystemExit("installed winner differs from candidate")
    actual_dps.append(dps)
if len(actual_dps) != 2:
    raise SystemExit("unexpected control count")
meta["application_compatibility_status"] = "passed"
manifest = replace(manifest, metadata=meta, engine_tree_hash=directory_sha256(installed, excluded_relative_paths=("gtt_engine_manifest.json",)))
_write_manifest(installed / "gtt_engine_manifest.json", manifest)
if json.loads(store.active_state_path.read_bytes()) != before:
    raise SystemExit("active engine changed during preparation")
receipt = {"status": "prepared_crlf_equivalent_bundle_and_winner_pass_not_activated", "engine_id": engine_id,
           "engine_sha256": sha(engine_binary), "consumer_sha256": sha(binary),
           "patch_sha256": sha(candidate / "patch_stack/0001-gtt-engine-adapter-v245.patch"),
           "source_manifest_sha256": meta["source_manifest_body_sha256"], "compact_n1_calls": 3,
           "ordinary_n1_calls": 2, "eol_only_file_count": len(eol_only),
           "installed_source_packages": len(sources["items"]), "winner_per_seed_dps": actual_dps}
(out / "prepare-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt))
