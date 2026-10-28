"""Bounded neutral observer/consumer integration from the ACTIVE engine lineage.

Temporary deployment gate owned by GP-3 / Go design. All staging, captures,
backups and compiler output use one managed job. Only the validated versioned
engine, one consolidated production patch and the normal consumer survive an
explicit --activate. Remove this helper after installed Flins/button acceptance;
retain the scoped hashes/receipt in the existing Go design, not another archive.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.check_stat_queries import PATCH_NAMES, HERE, patch_paths
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job

PATCH_NAME = "0009-gtt-neutral-event-effects.patch"
CONSUMER = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def application_build_report(report, metadata: dict) -> SimpleNamespace:
    """Preserve actual generator evidence; missing flags must fail the gate."""
    return SimpleNamespace(**report.to_dict(),
        source_manifest_required=metadata.get("source_manifest_required") == "true",
        source_manifest_ready=metadata.get("source_manifest_ready") == "true")


def export_delta(active: Path, changed: Path, paths: list[str]) -> str:
    result = []
    for name in sorted(set(paths)):
        before, after = active / name, changed / name
        had_file, has_file = before.is_file(), after.is_file()
        old = before.read_text(encoding="utf-8").splitlines(True) if had_file else []
        new = after.read_text(encoding="utf-8").splitlines(True) if has_file else []
        if old == new and had_file == has_file:
            continue
        result.append(f"diff --git a/{name} b/{name}\n")
        if not had_file:
            result.append("new file mode 100644\n")
        elif not has_file:
            result.append("deleted file mode 100644\n")
        result.extend(difflib.unified_diff(old, new,
            fromfile=f"a/{name}" if had_file else "/dev/null",
            tofile=f"b/{name}" if has_file else "/dev/null"))
    return "".join(result)


def relocate_overlay(engine: Path, old_root: Path) -> None:
    """Only relocate generated build metadata, never source/registry bytes."""
    path = engine / "build/gtt-source-overlay.json"
    rows = json.loads(path.read_bytes())["Replace"]
    out = {}
    for before, after in rows.items():
        pair = []
        for raw in (before, after):
            target = engine / Path(raw).resolve().relative_to(old_root.resolve())
            target.resolve(strict=True).relative_to(engine.resolve())
            pair.append(str(target))
        out[pair[0]] = pair[1]
    path.write_text(json.dumps({"Replace": out}), encoding="utf-8")


def promote(store, candidate: Path, consumer: Path, patch: Path, job: Path, expected: dict, *, verify_installed=None) -> Path:
    """Rollback all visible mutations on failure; never replace another engine."""
    from run_workspace.gcsim.engine_store import load_engine_manifest, _write_manifest
    from run_workspace.gcsim.tree_identity import directory_sha256
    target_patch = ROOT / "run_workspace/gcsim/patch_stack" / PATCH_NAME
    before = store.active_state_path.read_bytes()
    patch_before = target_patch.read_bytes() if target_patch.exists() else None
    patch_hash = hashlib.sha256(patch_before).hexdigest() if patch_before is not None else None
    if sha(store.active_state_path) != expected["pointer"] or sha(CONSUMER) != expected["consumer"] or patch_hash != expected.get("patch"):
        raise ValueError("Active bundle changed before promotion")
    manifest = load_engine_manifest(candidate)
    destination = store.engines_dir / manifest.engine_id
    if destination.parent.resolve() != store.engines_dir.resolve() or destination.exists():
        raise ValueError("Unexpected installation destination")
    backup = job / "previous-optimizer.exe"
    shutil.copy2(CONSUMER, backup)
    moved = patched = False
    try:
        shutil.move(str(candidate), str(destination))
        moved = True
        relocate_overlay(destination, candidate)
        manifest = replace(manifest, engine_tree_hash=directory_sha256(destination, excluded_relative_paths=("gtt_engine_manifest.json",)))
        _write_manifest(destination / "gtt_engine_manifest.json", manifest)
        patched = True
        with target_patch.open("xb" if patch_before is None else "wb") as stream:
            stream.write(patch.read_bytes())
        shutil.copy2(consumer, CONSUMER)
        store.activate_engine(manifest.engine_id)
        from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
        bound = load_active_gcsim_optimizer_engine_context(store_dir=store.root_dir)
        if bound.artifact_sha256 != sha(destination / "build/gtt-gcsim.exe") or sha(CONSUMER) != sha(consumer):
            raise ValueError("Promoted bundle identity changed")
        if verify_installed is not None:
            verify_installed(destination)
        return destination
    except BaseException:
        store.active_state_path.write_bytes(before)
        shutil.copy2(backup, CONSUMER)
        if patched:
            if patch_before is None:
                target_patch.unlink(missing_ok=True)
            else:
                target_patch.write_bytes(patch_before)
        if moved:
            # Restore into owned staging so the normal job cleaner owns it.
            shutil.move(str(destination), str(candidate))
        raise


def capture_controls(engine: Path, job: Path) -> None:
    witness = json.loads((ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json").read_bytes())
    original = witness["inputs"][0]["config"]
    rows, removed = [], 0
    for row in original.split("\n"):
        if "add set=" in row:
            if not re.fullmatch(r'[a-z][a-z0-9_]* add set="[a-z][a-z0-9_]*" count=4;', row):
                raise ValueError("Saved set declaration changed")
            rows.append("")
            removed += 1
        else:
            rows.append(row)
    if removed != 4 or len(witness["seeds"]) != 2:
        raise ValueError("Saved control shape changed")
    for index, seed in enumerate(witness["seeds"]):
        suffix = "" if index == 0 else "-second"
        for kind, text, effects in (("neutral", "\n".join(rows), True), ("control", original, False)):
            config, request = job / f"{kind}.txt", job / "capture-request.json"
            config.write_text(text, encoding="utf-8", newline="\n")
            request.write_text(json.dumps(dict(schema_version=1, context_sha256=sha(config), seed=str(seed),
                iterations=1, workers=1, ignore_burst_energy=True, output_mode="compact_ir_v1", include_effect_inputs=effects)), encoding="utf-8")
            subprocess.run([str(engine / "build/gtt-gcsim.exe"), "-c", str(config), "-out", str(job / f"{kind}-member{suffix}.json"),
                            "-gtt-trace-equation", str(request)], check=True, capture_output=True, timeout=60)
    print("Built binary: two neutral + two independent control captures; no search or ordinary finalists.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    job = owned_job()
    from run_workspace.gcsim.engine_store import GcsimEngineStore, load_engine_manifest, _write_manifest
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.source_acquisition import OfficialGcsimSourceRef, acquire_official_gcsim_source_from_archive
    from run_workspace.gcsim.engine_update import prepare_official_gcsim_engine_update
    from run_workspace.gcsim.patch_backends import GitApplyPatchBackend, ordered_file_stack_identity
    from run_workspace.gcsim.engine_compatibility import verify_engine_application_bundle
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources, NEUTRAL_INPUTS_CAPABILITY
    from run_workspace.gcsim.tree_identity import directory_sha256
    from run_workspace.gcsim.source_manifest_build import compute_patched_source_tree_sha256

    store = GcsimEngineStore()
    bound = load_active_gcsim_optimizer_engine_context()
    active = Path(bound.engine_root)
    old_manifest = load_engine_manifest(active)
    binding = json.loads((active / "build/gtt-source-manifest-input.json").read_bytes())
    production_patches = ROOT / "run_workspace/gcsim/patch_stack"
    old_paths = sorted(production_patches.glob("*.patch"))
    if ordered_file_stack_identity(production_patches, old_paths)[1] != binding["patch_stack_sha256"]:
        raise ValueError("Production patch stack differs from the active build")
    if (production_patches / PATCH_NAME).exists() or NEUTRAL_INPUTS_CAPABILITY in bound.capabilities:
        raise ValueError("Neutral bundle already exists; do not deploy twice")
    expected = dict(pointer=sha(store.active_state_path), consumer=sha(CONSUMER), engine=bound.artifact_sha256)
    go = shutil.which("go")
    if not go:
        raise RuntimeError("Configured Go toolchain unavailable")
    # Only touched original files: the normal source generator is regenerated
    # during the clean updater build, not replaced by stale generated overlays.
    changed = job / "observer-delta"
    paths = list(dict.fromkeys(n for p in PATCH_NAMES for n in patch_paths((HERE / p).read_text(encoding="utf-8"))))
    for name in paths:
        dst = changed / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (active / name).is_file():
            shutil.copy2(active / name, dst)
    for name in PATCH_NAMES:
        subprocess.run(["git", "apply", "--recount", *(["--unidiff-zero"] if name == "neutral_resources.patch" else []),
                        "--directory", changed.relative_to(ROOT).as_posix(), str(HERE / name)], cwd=ROOT, check=True)
    stack = job / "patch-stack"
    stack.mkdir()
    for path in old_paths:
        shutil.copy2(path, stack / path.name)
    delta = stack / PATCH_NAME
    delta.write_text(export_delta(active, changed, paths), encoding="utf-8", newline="\n")
    acquisition = acquire_official_gcsim_source_from_archive(source_ref=OfficialGcsimSourceRef(
        binding["upstream_ref"], binding["upstream_ref"], "", "", "", binding["upstream_repo"]),
        archive_path=old_manifest.metadata["source_archive_path"], cache_dir=job / "upstream")
    if directory_sha256(acquisition.source_dir) != binding["pristine_source_tree_sha256"]:
        raise ValueError("Cached official source is not the active engine's pristine input")
    # Check the old stack against the ACTIVE sources, then build that SAME
    # lineage plus the observer delta through the ordinary updater/generator.
    baseline = job / "baseline-source"
    shutil.copytree(acquisition.source_dir, baseline)
    check = GitApplyPatchBackend().apply(engine_dir=baseline, patch_stack_dir=production_patches)
    if not check.applied or compute_patched_source_tree_sha256(baseline) != compute_patched_source_tree_sha256(active):
        raise ValueError("Clean active-source replay differs; no alternate engine substituted")
    subprocess.run([go, "test", "./...", "-count=1", "-timeout=120s"], cwd=ROOT / "native/gcsim_optimizer", check=True, timeout=180)
    consumer = job / "gtt-optimizer.exe"
    subprocess.run([go, "build", "-trimpath", "-o", str(consumer), "./cmd/gtt-optimizer"], cwd=ROOT / "native/gcsim_optimizer", check=True, timeout=90)
    report = prepare_official_gcsim_engine_update(release=binding["upstream_ref"], store_dir=job / "engine-store",
        patch_stack_dir=stack, source_acquirer=lambda **_: acquisition, patch_backend=GitApplyPatchBackend(),
        build_artifact=True, activate=False, prune_engine_store=False, clean_go_build_cache=False,
        go_executable=go, runtime_probe_timeout_seconds=300)
    if not report.success:
        raise RuntimeError(report.error)
    engine = Path(report.engine_path)
    relocate_overlay(engine, engine.parent.parent / "staging" / engine.name)
    manifest = load_engine_manifest(engine)
    error = verify_engine_application_bundle(engine, application_build_report(report, manifest.metadata), optimizer_binary=consumer)
    if error:
        raise RuntimeError(error)
    if NEUTRAL_INPUTS_CAPABILITY not in report.gtt_capabilities:
        raise ValueError("Built neutral observer capability absent")
    manifest = replace(manifest, metadata={**manifest.metadata, "application_compatibility_status": "passed"},
        engine_tree_hash=directory_sha256(engine, excluded_relative_paths=("gtt_engine_manifest.json",)))
    _write_manifest(engine / "gtt_engine_manifest.json", manifest)
    source_binding = {"binary_path": report.artifact_path, "artifact_sha256": report.artifact_sha256,
        "source_manifest_sha256": manifest.metadata["source_manifest_body_sha256"], "capabilities": report.gtt_capabilities}
    source = prepare_all_set_effect_sources(engine, source_binding, include_neutral_rules=True)
    source_path = job / "rule-sources.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    capture_controls(engine, job)
    environment = dict(os.environ, GTT_RULE_SOURCE_BUNDLE=str(source_path), GTT_NEUTRAL_CAPTURE_DIR=str(job), GTT_NEUTRAL_TWO_SEEDS="1")
    subprocess.run([go, "test", "./internal/seteffects", "./internal/engineclient", "./internal/setcontext", "./internal/allsets",
        "-run", "Test(Rule|Neutral)", "-count=1", "-v", "-timeout=120s"], cwd=ROOT / "native/gcsim_optimizer", env=environment, check=True, timeout=150)
    if sha(store.active_state_path) != expected["pointer"] or sha(CONSUMER) != expected["consumer"] or sha(Path(bound.artifact_path)) != expected["engine"]:
        raise ValueError("Active bundle changed during preparation")
    if ordered_file_stack_identity(production_patches, sorted(production_patches.glob("*.patch")))[1] != binding["patch_stack_sha256"]:
        raise ValueError("Production patches changed during preparation")
    target = promote(store, engine, consumer, delta, job, expected) if args.activate else engine
    print("NEUTRAL_INSTALL " + json.dumps(dict(activated=args.activate, engine_id=report.engine_id,
        engine_sha256=report.artifact_sha256, consumer_sha256=sha(consumer), source_manifest_sha256=source_binding["source_manifest_sha256"],
        patch_sha256=sha(delta), stack_sha256=ordered_file_stack_identity(stack, sorted(stack.glob("*.patch")))[1],
        installed_path=str(target), previous_engine_id=bound.engine_id, previous_consumer_sha256=expected["consumer"],
        source_captures=4, ordinary_compatibility_smokes=2, compact_compatibility_smokes=1, ui_verified=False)), flush=True)


if __name__ == "__main__":
    main()
