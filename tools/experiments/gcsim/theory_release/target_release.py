"""Stage14: hash-bound main snapshot + existing dirty overlays + Theory hunks.

This tool only prepares frozen patches in Worker2 or a leased disposable
assembly. It never applies changes to main, switches refs, or runs an engine.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

if __package__:
    from . import package_io as io
    from . import release as source
    from .target_hunks import relocate_hunks
else:
    # Resolve this declared bootstrap as a package, never from the target main.
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from tools.experiments.gcsim.theory_release import package_io as io
    from tools.experiments.gcsim.theory_release import release as source
    from tools.experiments.gcsim.theory_release.target_hunks import relocate_hunks

EVIDENCE = "docs/optimizer-evidence/2026-10-11-theory-target"
SOURCE_EVIDENCE = "docs/optimizer-evidence/2026-10-11-theory-output-package"
SOURCE_MANIFEST_SHA = "8d28cc7f87a22503dc6dbfd301c081152c084fd93e3f7aae08402b4500730b99"
TOOLS = "tools/experiments/gcsim/theory_release/"
OWN_NEW = (
    TOOLS + "target_hunks.py", TOOLS + "target_release.py",
    "tests/tools/test_theory_target_hunks.py",
    "native/gcsim_optimizer/internal/seteffects/theory_target_guard_test.go",
)
REVIEW_PATHS = (
    "localization/locales/en.json", "localization/locales/pt-br.json", "localization/locales/ru.json",
    "ui/app_shell.py", "ui/gcsim_browser/run_worker.py", "ui/gcsim_browser/window.py",
)
ADJACENT_MODULES = (
    "tests.run_workspace.gcsim.test_optimizer_go_selected",
    "tests.run_workspace.gcsim.test_rotation_import",
    "tests.run_workspace.gcsim.test_rotation_team",
    "tests.run_workspace.gcsim.test_rotation_import_optimizer",
    "tests.ui.gcsim_browser.test_rotation_import_ui",
    "tests.ui.gcsim_browser.test_rotation_import_optimizer_ui",
    "tests.tools.test_theory_target_hunks",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def current_pins(repo: Path, main: Path, initial: dict) -> dict:
    actual_head = source.git(main, "rev-parse", "HEAD").decode().strip()
    if actual_head != initial["target_head"]:
        raise ValueError("main HEAD changed; an explicit snapshot rebind is required")
    target = {path: io.sha_bytes((main / path).read_bytes()) for path in initial["target_relevant_live_raw_sha256"]}
    if target != initial["target_relevant_live_raw_sha256"]:
        raise ValueError("relevant main dirty source changed; rebind the affected snapshot explicitly")
    worker = {path: io.sha_bytes((repo / path).read_bytes()) for path in initial["worker_runtime_account_raw_sha256"]}
    if worker != initial["worker_runtime_account_raw_sha256"]:
        raise ValueError("Worker2 runtime/account pins changed")
    return {"target_head": actual_head, "target_live_raw_sha256": target, "worker_runtime_account_raw_sha256": worker}


def _guard_context(patch: str) -> dict[int, tuple[str, str]]:
    sections = re.split(r"(?m)(?=^@@ )", patch)[1:]
    overrides = {}
    anchor = "    def _request_optimizer_mode(self, mode: str) -> None:\n"
    retained = "        if self._restricted_build:\n            return\n"
    for index, block in enumerate(sections, 1):
        lines = block.splitlines(keepends=True)[1:]
        old = "".join(line[1:] for line in lines if line.startswith((" ", "-")))
        new = "".join(line[1:] for line in lines if line.startswith((" ", "+")))
        if anchor in old:
            if old.count(anchor) != 1 or new.count(anchor) != 1:
                raise ValueError("optimizer request guard resolution became ambiguous")
            overrides[index] = (old.replace(anchor, anchor + retained), new.replace(anchor, anchor + retained))
    if len(overrides) != 1:
        raise ValueError("the one reviewed restricted-build overlap was not found")
    return overrides


def _emit_patch(repo: Path, files: dict[str, str]) -> str:
    rows = ["*** Begin Patch"]
    for name, content in sorted(files.items()):
        target = repo / name
        if target.exists():
            old = target.read_text(encoding="utf-8")
            if old == content:
                continue
            rows.append("*** Update File: " + str(target))
            rows.extend("@@" if line.startswith("@@") else line for line in
                        list(difflib.unified_diff(old.splitlines(), content.splitlines(), n=3, lineterm=""))[2:])
        else:
            rows.append("*** Add File: " + str(target))
            rows.extend("+" + line for line in content.splitlines())
    rows.append("*** End Patch")
    return "\n".join(rows) + "\n"


def freeze(repo: Path, main: Path) -> str:
    initial = read_json(repo / EVIDENCE / "initial.json")
    current_pins(repo, main, initial)
    original_raw = (repo / SOURCE_EVIDENCE / "package/manifest.json").read_bytes()
    if io.sha_bytes(original_raw) != SOURCE_MANIFEST_SHA:
        raise ValueError("reviewed Theory source package changed")
    original = json.loads(original_raw)
    base = initial["target_head"]
    entries = source.tree(main, base)
    old_entries = source.tree(repo, original["base_head"])
    source_blobs = source.blobs(repo, [old_entries[row["path"]] for row in original["patches"] if row["path"] in old_entries])
    target_paths = set(initial["target_relevant_live_raw_sha256"]) | {row["path"] for row in original["patches"]} | set(OWN_NEW)
    prefixes = ("ui/", "hoyolab_export/", "run_workspace/", "localization/", "tests/")
    paths = sorted(path for path in entries if (
        (path.startswith("native/gcsim_optimizer/") and (path.endswith(".go") or path.endswith(("go.mod", "go.sum"))))
        or (path.endswith(".py") and ("/" not in path or path.startswith(prefixes)))
        or path.startswith("tests/fixtures/gcsim_optimizer_go_v1/")
        or path in target_paths or (path.startswith("ui/") and path.endswith(".qss"))
    ))
    contents = source.blobs(main, [entries[path] for path in paths])
    base_files = [{"path": path, "git_blob": entries[path], "sha256": io.sha_bytes(contents[entries[path]]), "bytes": len(contents[entries[path]])} for path in paths]
    base_bodies = {path: contents[entries[path]] for path in paths}
    final = {path: base_bodies.get(path, b"") for path in target_paths}
    files, layers, reviews = {}, {}, []
    # Each existing dirty body is a declared exact overlay, retained separately.
    for path, digest in initial["target_relevant_live_raw_sha256"].items():
        live = (main / path).read_bytes()
        if io.sha_bytes(live) != digest:
            raise ValueError("target changed while freezing")
        normalized = source.normalized(live)
        before = base_bodies.get(path, b"")
        if normalized != before:
            payload = "overlays/" + path + ".patch"
            patch = io.make_patch(path, before, normalized)
            files[EVIDENCE + "/package/" + payload] = patch
            layers[path] = {"payload": payload, "payload_sha256": io.sha_bytes(patch.encode()), "raw_sha256": digest,
                            "before_sha256": io.sha_bytes(before), "after_sha256": io.sha_bytes(normalized),
                            "authorship": "existing target dirty source, retained without claiming implementation"}
        final[path] = normalized
    for row in original["patches"]:
        path = row["path"]
        payload = (repo / SOURCE_EVIDENCE / "package/patches" / row["payload"]).read_bytes()
        if io.sha_bytes(payload) != row["payload_sha256"]:
            raise ValueError("original frozen patch identity mismatch")
        before = source_blobs[old_entries[path]] if path in old_entries else b""
        current = final.get(path, b"")
        override = _guard_context(payload.decode()) if path == "ui/gcsim_browser/window.py" else None
        after, hunks = relocate_hunks(path, before, current, payload.decode(), override)
        final[path] = after
        theory_payload = "theory/" + path + ".patch"
        resolved = io.make_patch(path, current, after) if current != after else None
        if resolved:
            files[EVIDENCE + "/package/" + theory_payload] = resolved
        reviews.append({"path": path, "source_payload_sha256": row["payload_sha256"],
                        "target_before_sha256": io.sha_bytes(current), "target_after_sha256": io.sha_bytes(after),
                        "resolved_payload": theory_payload if resolved else None,
                        "resolved_payload_sha256": io.sha_bytes(resolved.encode()) if resolved else None,
                        "role": row["role"], "hunks": hunks,
                        "resolution": "retain restricted-build early return before Theory reset" if override else "unique exact full context; preserve every other target byte"})
    # New isolated test/tool implementation belongs to Worker2, not main.
    for path in OWN_NEW:
        final[path] = source.normalized((repo / path).read_bytes())
    patches = []
    for path, after in sorted(final.items()):
        before = base_bodies.get(path, b"")
        if before == after:
            continue
        payload = "combined/" + path + ".patch"
        patch = io.make_patch(path, before, after)
        files[EVIDENCE + "/package/" + payload] = patch
        patches.append({"path": path, "payload": path + ".patch", "payload_sha256": io.sha_bytes(patch.encode()),
                        "before_sha256": io.sha_bytes(before), "after_sha256": io.sha_bytes(after),
                        "existing_dirty_overlay": layers.get(path),
                        "role": "external_prerequisite" if path == source.EXTERNAL else "target_existing_dirty_only" if path in layers and not any(r["path"] == path for r in original["patches"]) else "reviewed_theory_on_target"})
    # JSON additions must retain all target-only keys and their exact values.
    locale_review = {}
    for path in REVIEW_PATHS[:3]:
        target = json.loads((main / path).read_text(encoding="utf-8"))
        merged = json.loads(final[path])
        if any(merged.get(key) != value for key, value in target.items()):
            raise ValueError("target locale key/value was replaced")
        locale_review[path] = {"retained_keys": len(target), "added_keys": sorted(set(merged) - set(target)), "retained_values_unchanged": True}
    manifest = {"schema_kind": "gtt_theory_target_package_v1", "date": "2026-10-11", "base_head": base,
                "source_stage_head": initial["worker_head"], "source_manifest_sha256": SOURCE_MANIFEST_SHA,
                "base_files": base_files, "patches": patches, "target_dirty_layers": layers,
                "hunk_review": reviews, "locale_review": locale_review,
                "capture_budget": 0, "engine_calls": 0, "installed": False,
                "bootstrap": {path: io.sha_bytes(source.normalized((repo / path).read_bytes())) for path in
                              (TOOLS + "target_release.py", TOOLS + "target_hunks.py", TOOLS + "package_io.py", TOOLS + "release.py")},
                "dependency_runtime": original["dependency_runtime"], "go_build_environment": original["go_build_environment"],
                "python_test_modules": list(original["python_test_modules"]) + list(ADJACENT_MODULES)}
    files[EVIDENCE + "/package/manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    current_pins(repo, main, initial)
    return _emit_patch(repo, files)


def _assert_layers(repo: Path, main: Path, manifest: dict, assembly: Path) -> None:
    base = manifest["base_head"]
    entries = source.tree(main, base)
    bodies = source.blobs(main, [entries[row["path"]] for row in manifest["patches"] if row["path"] in entries])
    reviews = {row["path"]: row for row in manifest["hunk_review"]}
    for row in manifest["patches"]:
        path = row["path"]
        before = bodies[entries[path]] if path in entries else b""
        layer = manifest["target_dirty_layers"].get(path)
        if layer:
            patch = (repo / EVIDENCE / "package" / layer["payload"]).read_bytes()
            if io.sha_bytes(patch) != layer["payload_sha256"]:
                raise ValueError("existing target dirty overlay drift")
            before = io.apply_file_patch(path, before, patch.decode())
            if io.sha_bytes(before) != layer["after_sha256"]:
                raise ValueError("target dirty overlay after identity differs")
        review = reviews.get(path)
        if review and review["resolved_payload"]:
            patch = (repo / EVIDENCE / "package" / review["resolved_payload"]).read_bytes()
            if io.sha_bytes(patch) != review["resolved_payload_sha256"]:
                raise ValueError("reviewed Theory hunk drift")
            before = io.apply_file_patch(path, before, patch.decode())
        if path not in OWN_NEW and before != (assembly / path).read_bytes():
            raise ValueError("combined target body differs from its declared dirty/Theory layers")


def verify(repo: Path, main: Path, python: Path, go: Path) -> dict:
    initial = read_json(repo / EVIDENCE / "initial.json")
    pins = current_pins(repo, main, initial)
    manifest_raw = (repo / EVIDENCE / "package/manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest["base_head"] != pins["target_head"] or manifest["capture_budget"] != 0:
        raise ValueError("target manifest authorization/base differs")
    for path, digest in manifest["bootstrap"].items():
        if io.sha_bytes(source.normalized((repo / path).read_bytes())) != digest:
            raise ValueError("target bootstrap not frozen")
    if manifest["dependency_runtime"] != {"go_sha256": io.sha_bytes(go.read_bytes()), "python_sha256": io.sha_bytes(python.read_bytes())}:
        raise ValueError("target dependency runtime changed")
    source_initial = read_json(repo / SOURCE_EVIDENCE / "initial.json")
    before_drafts = {p: io.sha_bytes((repo / p).read_bytes()) for p in initial["worker_prior147_raw_sha256"]}
    receipt = {"schema_kind": "gtt_theory_target_validation_v1", "date": "2026-10-11", "status": "FAIL",
               "target_head": pins["target_head"], "manifest_sha256": io.sha_bytes(manifest_raw),
               "source_stage_head": initial["worker_head"], "checks": [], "capture_budget": 0, "engine_calls": 0,
               "installed": False, "before_pins": pins, "toolchain": manifest["dependency_runtime"]}
    lifecycle = None
    try:
        with source.optimizer_slot(repo / ".codex_tmp/managed-optimizer"), io.managed_job(repo / ".codex_tmp/theory-target-assembly") as lifecycle:
            job = lifecycle["path"]
            assembly = job / "assembly"
            records = io.materialize_from_manifest(main, manifest, repo / EVIDENCE / "package/combined", assembly)
            _assert_layers(repo, main, manifest, assembly)
            receipt["assembly_files"] = len(records)
            receipt["assembly_sha256"] = io.sha_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())
            receipt["numerical_preservation"] = source.numerical_preservation(repo, source_initial, assembly)
            receipt["all_dirty_layers_and_reviewed_hunks_match"] = True
            for name in ("temp", "go-cache", "go-mod", "rule-cache", "bundled-cache"):
                (job / name).mkdir()
            env = dict(os.environ)
            for key in ("PYTHONPATH", "PYTHONHOME", "GTT_RULE_SOURCE_BUNDLE", "GTT_THEORY_OUTPUT_EXPORT", "GTT_ENGINE_ROOT", "GTT_RUN_ROOT"):
                env.pop(key, None)
            env.update(manifest["go_build_environment"], GOROOT=str(go.parent.parent), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
                       QT_QPA_PLATFORM="offscreen", TEMP=str(job / "temp"), TMP=str(job / "temp"),
                       GOCACHE=str(job / "go-cache"), GOMODCACHE=str(job / "go-mod"), GOTMPDIR=str(job / "temp"),
                       GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOWORK="off",
                       GTT_RULE_CACHE_DIR=str(job / "rule-cache"), GTT_BUNDLED_CACHE_DIR=str(job / "bundled-cache"),
                       GTT_THEORY_OUTPUT_EXPORT=str(job / "native-public-output.json"))
            receipt["toolchain"]["go_version"] = source.run([str(go), "version"], assembly, env, 30)["stdout"].strip()
            native = assembly / "native/gcsim_optimizer"
            # Active engine sources are read/hash-verified only, never executed.
            engine = repo / "data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932"
            engine_manifest = read_json(engine / "gtt_engine_manifest.json")
            metadata = engine_manifest["metadata"]
            receipt["source_fixture_provenance"] = {"engine_id": engine_manifest["engine_id"],
                "engine_manifest_raw_sha256": io.sha_bytes((engine / "gtt_engine_manifest.json").read_bytes()),
                "artifact_sha256": metadata["artifact_sha256"], "source_manifest_body_sha256": metadata["source_manifest_body_sha256"],
                "patched_source_tree_sha256": metadata["source_manifest_patched_tree_sha256"],
                "upstream_version": metadata["gtt_upstream_version"], "executed": False}
            binding = {"binary_path": str(engine / metadata["artifact_relative_path"]), "artifact_sha256": metadata["artifact_sha256"],
                       "source_manifest_sha256": metadata["source_manifest_body_sha256"], "capabilities": json.loads(metadata["gtt_capabilities"])}
            fixture_code = "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources;b=prepare_all_set_effect_sources(sys.argv[2],json.loads(sys.argv[3]),include_neutral_rules=True);b['items']=[x for x in b['items'] if x['key'] in ('marechausseehunter','songofdayspast')];assert len(b['items'])==2;Path(sys.argv[4]).write_text(json.dumps(b,sort_keys=True),encoding='utf-8')"
            fixture = job / "active-two-set-sources.json"
            prep = source.run([str(python), "-I", "-B", "-c", fixture_code, str(assembly), str(engine), json.dumps(binding), str(fixture)], assembly, env, 180)
            receipt["source_fixture_preparation"] = prep
            if prep["exit_code"]:
                raise RuntimeError("identified active source fixture provenance/preparation failed")
            receipt["source_fixture_sha256"] = io.sha_bytes(fixture.read_bytes())
            env["GTT_RULE_SOURCE_BUNDLE"] = str(fixture)
            groups = (
                ["./internal/theoryalloc", "./internal/theorysearch", "./internal/theorypackages"],
                ["-run", "Theory|Finish|Selected|AllSetsNeutralRoute|SeedFull45|Publication|ValidationRejectsIllegalSlot|RuleAccessors|RuleEmit|RuleActiveHealGuard|RuleTargetHeal|Linear",
                 "./internal/contracts", "./internal/formula", "./internal/seteffects", "./internal/setcontext", "./cmd/gtt-optimizer"],
            )
            for group in groups:
                raw = source.run([str(go), "test", "-json", "-count=1", "-p=2", *group], native, env)
                result = source.go_receipt(raw)
                result["passed_tests"] = sorted({event["Test"] for line in raw["stdout"].splitlines() if line.startswith("{")
                                                 for event in (json.loads(line),)
                                                 if event.get("Action") == "pass" and event.get("Test")})
                receipt["checks"].append(result)
                print(json.dumps({"step": "target native", "passes": result["top_level_passes"], "failures": result["failures"]}), flush=True)
                if result["exit_code"]:
                    raise RuntimeError("target native contract gate failed")
                if "-run" in group:
                    required = {"TestRuleEmitUsesOwnedHealArgumentsAcrossSubscriptions", "TestRuleEmitRejectsObservedHealPayloadMutation",
                                "TestRuleActiveHealGuardOrdinaryAndSymbolicContracts", "TestRuleTargetHealOperandsRequireBinding"}
                    if not required.issubset(result["passed_tests"]) or result["skips"]:
                        raise RuntimeError("new callback isolation/source guard controls did not all execute successfully")
            for name in ("target", "repeat"):
                result = source.run([str(go), "build", "-trimpath", "-o", str(job / (name + ".exe")), "./cmd/gtt-optimizer"], native, env)
                receipt["checks"].append(result)
                if result["exit_code"]:
                    raise RuntimeError("target clean build failed")
            receipt["binary_sha256"] = io.sha_bytes((job / "target.exe").read_bytes())
            receipt["repeat_binary_sha256"] = io.sha_bytes((job / "repeat.exe").read_bytes())
            if receipt["binary_sha256"] != receipt["repeat_binary_sha256"]:
                raise RuntimeError("target binary is not reproducible")
            # Retain incompatible old precise symbolic expectations as failures.
            legacy = source.go_receipt(source.run([str(go), "test", "-json", "-count=1", "-p=2", "-run",
                "^(TestRuleActiveMarechausseeHealingBranch|TestRuleActiveSongRejectsMissingHitIdentity)$", "./internal/seteffects"], native, env))
            receipt["legacy_precise_source_expectations"] = legacy
            top_failures = {name for name in legacy["failures"] if "/" not in name}
            if legacy["skips"] or top_failures != {"TestRuleActiveMarechausseeHealingBranch", "TestRuleActiveSongRejectsMissingHitIdentity"}:
                raise RuntimeError("identified source controls did not exercise the reviewed guard boundary")
            diagnostics = [line.strip() for line in legacy["failure_output"] if re.search(r"\.go:\d+:", line)]
            if not diagnostics or any("neutral heal amount has no bound health-operation expression" not in line for line in diagnostics):
                raise RuntimeError("legacy controls failed outside the reviewed unbound-heal boundary")
            legacy["boundary_diagnostics"] = diagnostics
            legacy["status"] = "EXPECTED_LEGACY_PRECISE_SYMBOLIC_ASSERTIONS_FAIL_WITH_UNBOUND_HEAL_GUARD"
            receipt["native_export_sha256"] = io.sha_bytes((job / "native-public-output.json").read_bytes())
            code = "import sys,unittest;sys.path.insert(0,sys.argv[1]);suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]);r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not r.wasSuccessful())"
            result = source.run([str(python), "-I", "-B", "-c", code, str(assembly), *manifest["python_test_modules"]], assembly, env, 240)
            receipt["checks"].append(result)
            if result["exit_code"]:
                raise RuntimeError("target Python/offscreen/preserved-rotation gate failed")
            receipt["status"] = "PASS_REVIEWED_TARGET_READY_FOR_TRANSFER"
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["failure_traceback"] = traceback.format_exc()
    finally:
        receipt["cleanup"] = {key: str(value) if isinstance(value, Path) else value for key, value in (lifecycle or {}).items()}
        receipt["worker_drafts_unchanged_by_check"] = all(io.sha_bytes((repo / path).read_bytes()) == digest for path, digest in before_drafts.items())
        try:
            receipt["after_pins"] = current_pins(repo, main, initial)
        except ValueError as exc:
            receipt["pin_error"] = str(exc)
            receipt["status"] = "FAIL"
        if not receipt["worker_drafts_unchanged_by_check"] or not receipt["cleanup"].get("cleaned"):
            receipt["status"] = "FAIL"
    return receipt


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("freeze", "verify"))
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--python", type=Path)
    p.add_argument("--go", type=Path)
    args = p.parse_args()
    repo, target = args.repo.resolve(strict=True), args.main.resolve(strict=True)
    if args.mode == "freeze":
        sys.stdout.write(freeze(repo, target))
        return 0
    if not args.python or not args.go:
        p.error("verification requires explicit read-only dependency executable paths")
    result = verify(repo, target, args.python.resolve(strict=True), args.go.resolve(strict=True))
    print("RECEIPT_JSON=" + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
