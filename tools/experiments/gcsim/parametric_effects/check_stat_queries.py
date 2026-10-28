"""Focused candidate adapter gate, using only the selected active engine source.

Historical pre-install gate: copy only reviewed targets into the existing
managed optimizer job and test through Go overlays. Refuse an active engine
that already contains the consolidated neutral observer.
No account reads, active-source writes or persistent build outputs. The default
gate makes no simulations; --capture-fixture adds two saved-seed response captures.
Owner: the parametric producer section of GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md.
Consolidate the patch/tests into the main engine stack at producer installation;
then remove this temporary gate after the equivalent installed-source checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PATCH_NAMES = ("stat_query_identity.patch", "combat_events.patch", "neutral_inputs.patch", "neutral_world.patch", "neutral_query_metadata.patch", "neutral_query_filters.patch", "neutral_hitlag.patch", "neutral_selected_stats.patch", "neutral_stat_reads.patch", "neutral_character_facts.patch", "neutral_target_facts.patch", "neutral_observer_gating.patch", "neutral_schedule_horizon.patch", "neutral_resources.patch", "neutral_capability.patch")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refuse_consolidated_observer(manifest: dict) -> None:
    capabilities = json.loads(manifest.get("metadata", {}).get("gtt_capabilities", "[]"))
    if "gtt_neutral_inputs_v1" in capabilities:
        raise ValueError("Neutral observer is already consolidated; do not reapply historical deltas")


def patch_paths(text: str) -> list[str]:
    paths = re.findall(r"^diff --git a/(\S+) b/\1$", text, re.MULTILINE)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Missing or duplicate candidate patch targets")
    for name in paths:
        p = Path(name)
        allowed = name.startswith("pkg/") or name == "internal/template/character/character.go"
        if not allowed or p.is_absolute() or ".." in p.parts or "\\" in name:
            raise ValueError("Candidate patch escaped its engine package scope")
    return paths


def bound_overlay_path(raw: str, engine: Path) -> Path:
    """Relocate only this installation's recorded pre-activation build root."""
    path = Path(raw).resolve()
    staging = engine.parents[1] / "staging" / engine.name
    try:
        path = engine / path.relative_to(staging)
    except ValueError:
        pass
    path.relative_to(engine)
    return path


def stage_overlay_variants(engine: Path, job: Path, paths: list[str],
                           overlay: dict, generated: dict[str, Path]) -> list[Path]:
    """Copy reviewed targets; preserve generated instrumentation on collisions."""
    source, generated_source = job / "query-source", job / "query-generated"
    variants = [source, generated_source] if generated else [source]
    for variant in variants:
        variant.mkdir(exist_ok=False)
        for name in paths:
            destination = variant / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            original = generated.get(name, engine / name) if variant == generated_source else engine / name
            if original.is_file():
                shutil.copyfile(original, destination)
    for name in paths:
        overlay["Replace"][str(engine / name)] = str((generated_source if name in generated else source) / name)
    return variants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-fixture", action="store_true",
                        help="neutral plus original-set response captures of one saved Flins seed; source-only, not product acceptance")
    parser.add_argument("--audit-rules", action="store_true",
                        help="diagnose all source packages on that same neutral tape, without per-package simulations")
    parser.add_argument("--inventory-profile", action="store_true",
                        help="60-second source coordinator profile on saved Flins/current inventory; not product acceptance")
    parser.add_argument("--finish-passes", action="store_true",
                        help="diagnostic inventory profile without the 60s search deadline; managed watchdog remains")
    parser.add_argument("--compare-preparation", action="store_true",
                        help="paired exact-reuse/off control on the SAME captures; requires --finish-passes")
    parser.add_argument("--compare-effects", action="store_true",
                        help="paired constant-effect binding/off control on the SAME captures; requires --finish-passes")
    parser.add_argument("--two-seeds", action="store_true",
                        help="use BOTH saved seeds for neutral/control panels; requires --finish-passes, excludes paired timing experiments")
    args = parser.parse_args()
    if args.audit_rules and not args.capture_fixture:
        parser.error("--audit-rules requires --capture-fixture")
    if args.inventory_profile and not args.capture_fixture:
        parser.error("--inventory-profile requires --capture-fixture")
    if args.finish_passes and not args.inventory_profile:
        parser.error("--finish-passes requires --inventory-profile")
    if args.compare_preparation and not args.finish_passes:
        parser.error("--compare-preparation requires --finish-passes")
    if args.compare_effects and (not args.finish_passes or args.compare_preparation):
        parser.error("--compare-effects requires --finish-passes and excludes --compare-preparation")
    if args.two_seeds and (not args.finish_passes or args.compare_preparation or args.compare_effects):
        parser.error("--two-seeds requires --finish-passes and excludes paired timing experiments")
    raw_job = os.environ.get("GTT_SCRATCH_DIR")
    if not raw_job:
        raise RuntimeError("Run inside managed_optimizer_experiment.py")
    job = Path(raw_job).resolve(strict=True)
    managed = (ROOT / ".codex_tmp/managed-optimizer").resolve(strict=True)
    if job.parent != managed or not job.name.startswith("job-"):
        raise ValueError("Not an owned managed optimizer job")
    pointer = ROOT / "data/gcsim/engines/active_engine.json"
    selected = json.loads(pointer.read_text(encoding="utf-8"))["active_engine_id"]
    if not isinstance(selected, str) or Path(selected).name != selected:
        raise ValueError("Invalid active engine identity")
    engine = (ROOT / "data/gcsim/engines/engines" / selected).resolve(strict=True)
    manifest_path = engine / "gtt_engine_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["engine_id"] != selected:
        raise ValueError("Active engine manifest mismatch")
    refuse_consolidated_observer(manifest)
    if args.capture_fixture:
        # Fail cheap source controls before any captures/profile; reuse this
        # managed build cache and the same selected-source identity.
        from check_rules import run_gate
        run_gate(job)
    artifact = engine / manifest["metadata"]["artifact_relative_path"]
    artifact.resolve(strict=True).relative_to(engine)
    if digest(artifact) != manifest["metadata"]["artifact_sha256"]:
        raise ValueError("Active binary no longer matches its source manifest")
    patches = [HERE / name for name in PATCH_NAMES]
    paths = list(dict.fromkeys(name for patch in patches
                             for name in patch_paths(patch.read_text(encoding="utf-8"))))
    originals = [engine / name for name in paths if (engine / name).is_file()]
    overlay = json.loads((engine / "build/gtt-source-overlay.json").read_text(encoding="utf-8"))
    overlay["Replace"] = {
        str(bound_overlay_path(key, engine)): str(bound_overlay_path(value, engine))
        for key, value in overlay["Replace"].items()
    }
    for value in overlay["Replace"].values():
        if not Path(value).is_file():
            raise ValueError(f"Active generated source is missing: {value}")
    generated = {name: Path(overlay["Replace"][str(engine / name)])
                 for name in paths if str(engine / name) in overlay["Replace"]}
    preserved = {p: digest(p) for p in [pointer, manifest_path, artifact, *originals, *generated.values()]}
    # Preserve existing generated instrumentation. Apply the same reviewed
    # source patches to BOTH touched original and generated variants; never
    # replace a generated file with an uninstrumented original on collision.
    variants = stage_overlay_variants(engine, job, paths, overlay, generated)
    try:
        for variant in variants:
            prefix = variant.relative_to(ROOT).as_posix()
            for patch in patches:
                for flags in (["--check"], []):
                    sparse = ["--unidiff-zero"] if patch.name == "neutral_resources.patch" else []
                    subprocess.run(["git", "apply", "--recount", *sparse, *flags, "--directory", prefix, str(patch)], cwd=ROOT, check=True)
        go = shutil.which("go")
        if not go:
            raise RuntimeError("Configured Go toolchain is unavailable")
        overlay_path = job / "query-overlay.json"
        environment = dict(os.environ)
        overlay["Replace"][str(engine / "pkg/gttsourcegen/gtt_neutral_refresh_codegen_test.go")] = str(HERE / "refresh_codegen_test.go")
        if args.capture_fixture:
            # This test is attached only to the selected source's package; it
            # never produces a substitute installed engine or a new registry.
            overlay["Replace"][str(engine / "pkg/optimization/gtt_neutral_capture_fixture_test.go")] = str(HERE / "capture_fixture_test.go")
            environment.update(GTT_NEUTRAL_CAPTURE_DIR=str(job),
                               GTT_NEUTRAL_CAPTURE_FIXTURE=str(ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json"))
            environment["GTT_NEUTRAL_TWO_SEEDS"] = str(int(args.two_seeds))
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        subprocess.run([go, "test", "-overlay", str(overlay_path), "./pkg/gttsourcegen",
                        "-run", "TestNeutralSelected", "-count=1", "-v", "-timeout=90s"],
                       cwd=engine, env=environment, check=True, timeout=110)
        subprocess.run([go, "test", "-overlay", str(overlay_path),
                        "./pkg/gtttrace", "./pkg/core/info", "./pkg/core/event", "./pkg/core/player/character",
                        "./pkg/core", "./pkg/gttcompact", "./pkg/optimization",
                        "-run", "Test(Parametric|Neutral|GTTNonExtra|StatRead|SnapshotStat)",
                        "-count=1", "-v", "-timeout=120s"], cwd=engine, env=environment, check=True, timeout=150)
        if args.capture_fixture:
            from check_rules import run_gate
            extra = {}
            if args.inventory_profile:
                from inventory_profile import prepare_inventory_profile
                extra = prepare_inventory_profile(job)
                if args.finish_passes:
                    extra["GTT_NEUTRAL_FINISH_PASSES"] = "1"
            extra = {"GTT_NEUTRAL_CAPTURE_DIR": str(job),
                     "GTT_NEUTRAL_TWO_SEEDS": str(int(args.two_seeds)),
                     "GTT_RULE_COVERAGE": str(int(args.audit_rules)), **extra}
            if args.compare_preparation or args.compare_effects:
                from compare_preparation import run_comparison
                run_comparison(job, extra, mode="effects" if args.compare_effects else "preparation")
            else:
                run_gate(job, extra_environment=extra)
        print(f"Active source: {selected}; binary unchanged; {(4 if args.two_seeds else 2) * int(args.capture_fixture)} fixture capture(s), zero ordinary finalist simulations.", flush=True)
    finally:
        for path, expected in preserved.items():
            if digest(path) != expected:
                raise RuntimeError(f"Active input changed during gate: {path}")


if __name__ == "__main__":
    main()
