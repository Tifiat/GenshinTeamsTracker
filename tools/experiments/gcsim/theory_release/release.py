"""Freeze/verify the authorized capture-free Theory source package.

Freeze reads a closed source whitelist. Verify imports only this hash-bound
bootstrap, Git objects at the declared base, and the frozen patch directory.
It never copies the dirty checkout into its assembly or calls the optimizer.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import difflib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import traceback

if __package__:
    from .package_io import apply_file_patch, make_patch, managed_job, materialize_from_manifest, safe_relative, sha_bytes
else:
    from package_io import apply_file_patch, make_patch, managed_job, materialize_from_manifest, safe_relative, sha_bytes

EVIDENCE = "docs/optimizer-evidence/2026-10-11-theory-output-package"
BASE = "1698b695de15785be7ab3f39c50c9f407a10474b"
BOOTSTRAP = "tools/experiments/gcsim/theory_release/"
ADDITIONAL = (
    "native/gcsim_optimizer/cmd/gtt-optimizer/theory_session_domains.go",
    "native/gcsim_optimizer/cmd/gtt-optimizer/theory_session_domains_test.go",
    "native/gcsim_optimizer/internal/theorypackages/catalog.go",
    "native/gcsim_optimizer/internal/theorypackages/catalog_test.go",
    "native/gcsim_optimizer/internal/theorysearch/output_contract_test.go",
    "native/gcsim_optimizer/internal/seteffects/theory_heal_prerequisite_test.go",
    "tests/run_workspace/gcsim/theory_output_fixture.py",
    BOOTSTRAP + "package_io.py", BOOTSTRAP + "release.py",
    "tests/tools/test_theory_release_package_io.py",
)
PREREQUISITES = (
    "native/gcsim_optimizer/internal/contracts/schemas.go",
    "native/gcsim_optimizer/internal/contracts/theory_options.go",
    "native/gcsim_optimizer/internal/contracts/theory_options_test.go",
    "native/gcsim_optimizer/internal/contracts/validate_request.go",
    "native/gcsim_optimizer/internal/contracts/result_options_test.go",
    "native/gcsim_optimizer/cmd/gtt-optimizer/all_sets.go",
    "native/gcsim_optimizer/internal/seteffects/source_bundle.go",
    "run_workspace/gcsim/optimizer_go_all.py",
    "run_workspace/gcsim/optimizer_go_inputs.py",
    "run_workspace/gcsim/optimizer_go_theory.py",
    "tests/run_workspace/gcsim/test_optimizer_go_theory.py",
    "tests/run_workspace/gcsim/test_optimizer_go_all.py",
)
EXTERNAL = "native/gcsim_optimizer/internal/seteffects/rule_resources.go"
EXCLUDED_DIRTY = (
    "native/gcsim_optimizer/cmd/gtt-optimizer/theory.go",
    "native/gcsim_optimizer/cmd/gtt-optimizer/theory_test.go",
    "native/gcsim_optimizer/internal/theory/solver.go",
    "native/gcsim_optimizer/internal/theory/solver_test.go",
)
PYTHON_MODULES = (
    "tests.run_workspace.gcsim.test_optimizer_go_theory_session",
    "tests.ui.gcsim_browser.test_theory_session_ui",
    "tests.ui.gcsim_browser.test_gcsim_optimizer_ui",
    "tests.run_workspace.gcsim.test_optimizer_go_theory",
    "tests.run_workspace.gcsim.test_optimizer_go_all",
    "tests.tools.test_theory_release_package_io",
)


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def normalized(data: bytes) -> bytes:
    text = data.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text or "\x00" in text:
        raise ValueError("noncanonical source text")
    return text.encode("utf-8")


def blobs(repo: Path, identities: list[str]) -> dict[str, bytes]:
    identities = sorted(set(identities))
    if not identities:
        return {}
    data = subprocess.check_output(["git", "-C", str(repo), "cat-file", "--batch"],
                                   input="".join(blob + "\n" for blob in identities).encode("ascii"),
                                   stderr=subprocess.PIPE)
    result, offset = {}, 0
    for blob in identities:
        end = data.index(b"\n", offset)
        actual, kind, size = data[offset:end].decode("ascii").split()
        if actual != blob or kind != "blob" or not size.isdecimal():
            raise ValueError("unexpected Git batch header")
        offset, size = end + 1, int(size)
        result[blob] = data[offset:offset + size]
        if len(result[blob]) != size or data[offset + size:offset + size + 1] != b"\n":
            raise ValueError("truncated Git blob")
        offset += size + 1
    if offset != len(data):
        raise ValueError("extra Git batch data")
    return result


def tree(repo: Path, base: str) -> dict[str, str]:
    rows = {}
    for raw in git(repo, "ls-tree", "-r", "-z", base).split(b"\x00"):
        if not raw:
            continue
        meta, name = raw.split(b"\t", 1)
        mode, kind, blob = meta.decode("ascii").split()
        path = name.decode("utf-8")
        safe_relative(path)
        if mode == "100644" and kind == "blob":
            rows[path] = blob
    return rows


def projection(path: str, before: bytes, current: bytes) -> bytes:
    """Retain only the required request/test seam in the older v1 adapter."""
    if path == "run_workspace/gcsim/optimizer_go_theory.py":
        old = b"    product_timeout_ms: int = 360_000\n"
        new = b"    product_timeout_ms: int = 0\n    theory_options: Mapping[str, Any] | None = None\n"
        if before.count(old) != 1 or current.count(new) != 1:
            raise ValueError("Theory request projection changed")
        return before.replace(old, new)
    if path == "tests/run_workspace/gcsim/test_optimizer_go_theory.py":
        old = b"self.assertEqual(request.product_timeout_ms, 360_000)"
        new = b"self.assertEqual(request.product_timeout_ms, 0)"
        if before.count(old) != 1:
            raise ValueError("Theory timeout test projection changed")
        text = current.decode("utf-8")
        module = ast.parse(text)
        names = {
            "test_neutral_engine_is_required_before_source_preparation",
            "test_constraint_transport_preserves_fixed_zero_and_rejects_unknown_options",
            "test_default_theory_options_keep_new_backend_compatibility_fence",
        }
        lines = text.splitlines(keepends=True)
        selected = [node for node in ast.walk(module)
                    if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in selected} != names:
            raise ValueError("missing prerequisite regression")
        methods = "".join("".join(lines[n.lineno - 1:n.end_lineno]) + "\n"
                          for n in sorted(selected, key=lambda n: n.lineno))
        anchor = b"class TheoryAdapterTests(unittest.TestCase):\n"
        if before.count(anchor) != 1:
            raise ValueError("Theory test class projection changed")
        return before.replace(old, new).replace(anchor, anchor + methods.encode("utf-8"))
    return current


def numerical_preservation(repo: Path, initial: dict, source: Path) -> dict:
    """Bind zero-capture assembly to the already validated production bodies."""
    head = initial["worker_head"]
    entries = tree(repo, head)
    paths = sorted(path for path in initial["original_stage12_source_raw_sha256"]
                   if path.startswith("native/") and path.endswith(".go") and not path.endswith("_test.go"))
    contents = blobs(repo, [entries[path] for path in paths])
    proof = {}
    for path in paths:
        before = contents[entries[path]]
        expected = before
        if path in ("native/gcsim_optimizer/internal/theorysearch/search.go",
                    "native/gcsim_optimizer/internal/theorysearch/formula_world.go",
                    "native/gcsim_optimizer/cmd/gtt-optimizer/theory_session.go"):
            expected = expected.replace(b"/internal/theoryteams\"", b"/internal/theorypackages\"").replace(b"theoryteams.", b"theorypackages.")
        if path == "native/gcsim_optimizer/cmd/gtt-optimizer/theory_session.go":
            expected = expected.replace(
                b'\t"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"\n\t"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"',
                b'\t"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"\n\t"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"')
            old = b"domains, _, _, _, err := theoryOptions(req, packages)"
            new = b"domains, err := theorySessionAllowedDomains(req, packages)"
            if expected.count(old) != 1:
                raise ValueError("domain extraction baseline changed")
            expected = expected.replace(old, new)
        actual = normalized((source / path).read_bytes())
        if actual != expected:
            raise ValueError(f"unapproved numerical production change needs a new justified packet: {path}")
        proof[path] = {"baseline_git_blob": entries[path], "baseline_sha256": sha_bytes(before),
                       "after_sha256": sha_bytes(actual), "change": "namespace/domain projection extraction only" if before != actual else "unchanged"}
    return {"baseline_head": head, "files": proof, "fresh_capture_required": False,
            "extraction_review": "Packages/Key copied unchanged; allowed-domain order unchanged for valid inputs, invalid duplicates/empty/unknown owners rejected earlier"}


def freeze(repo: Path) -> str:
    initial = json.loads((repo / EVIDENCE / "initial.json").read_text(encoding="utf-8"))
    if initial["base_head"] != BASE or initial["capture_budget"] != 0:
        raise ValueError("base or authorization mismatch")
    entries = tree(repo, BASE)
    numerical = numerical_preservation(repo, initial, repo)
    own = sorted(set(initial["original_stage12_source_raw_sha256"]) | set(ADDITIONAL) | set(PREREQUISITES))
    sources = sorted(set(own) | {EXTERNAL})
    # Public source only: no account, engine, profile, image, dump or live data.
    prefixes = ("ui/", "hoyolab_export/", "run_workspace/", "localization/", "tests/")
    base_paths = sorted(path for path in entries if (
        (path.startswith("native/gcsim_optimizer/") and (path.endswith(".go") or path.endswith(("go.mod", "go.sum"))))
        or (path.endswith(".py") and ("/" not in path or path.startswith(prefixes)))
        or path.startswith("tests/fixtures/gcsim_optimizer_go_v1/")
        or path in sources or (path.startswith("ui/") and path.endswith(".qss"))
    ))
    contents = blobs(repo, [entries[path] for path in base_paths])
    base_rows = []
    for path in base_paths:
        data = contents[entries[path]]
        base_rows.append({"path": path, "git_blob": entries[path], "sha256": sha_bytes(data), "bytes": len(data)})
    patches, files = [], {}
    for path in sources:
        before = contents[entries[path]] if path in entries else b""
        current = normalized((repo / path).read_bytes())
        after = projection(path, before, current)
        if before == after:
            continue
        role = "external_prerequisite" if path == EXTERNAL else "own_source"
        payload = ("external/" if path == EXTERNAL else "own/") + path + ".patch"
        patch = make_patch(path, before, after)
        if apply_file_patch(path, before, patch) != after:
            raise ValueError("freezer roundtrip mismatch")
        files[EVIDENCE + "/package/patches/" + payload] = patch
        row = {"path": path, "payload": payload, "role": role,
               "payload_sha256": sha_bytes(patch.encode("utf-8")),
               "before_sha256": sha_bytes(before), "after_sha256": sha_bytes(after),
               "current_raw_sha256": sha_bytes((repo / path).read_bytes()),
               "projection": "required request/timeout/options only" if after != current else "declared current source"}
        if path == EXTERNAL:
            row["provenance"] = {
                "authorship": "unresolved shared-source prerequisite; not claimed as Worker2 implementation",
                "base_git_blob": entries[path],
                "reason": "preserve observed-build symbolic heal fail-closed boundary used by prior parity study",
                "legacy_compatibility_controls": ["TestRuleActiveMarechausseeHealingBranch", "TestRuleActiveSongRejectsMissingHitIdentity"],
                "integration": "separate explicit shared prerequisite review before installation; this assembly freezes it unchanged",
            }
        patches.append(row)
    manifest = {
        "schema_kind": "gtt_theory_frozen_source_package_v1", "date": "2026-10-11",
        "base_head": BASE, "source_head_at_freeze": git(repo, "rev-parse", "HEAD").decode().strip(),
        "base_files": base_rows, "patches": patches,
        "capture_budget": 0, "engine_calls": 0, "installed": False,
        "numerical_preservation": numerical,
        "excluded_dirty_legacy": list(EXCLUDED_DIRTY),
        "prerequisite_selection": "five native symbols/hunks plus Theory options/timeout request/test transport; no dirty legacy solver/search closure",
        "bootstrap": {path: sha_bytes(normalized((repo / path).read_bytes()))
                      for path in (BOOTSTRAP + "release.py", BOOTSTRAP + "package_io.py")},
        "dependency_runtime": {
            "go_sha256": sha_bytes(Path("C:/Program Files/Go/bin/go.exe").read_bytes()),
            "python_sha256": sha_bytes(Path("C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe").read_bytes()),
        },
        "go_build_environment": {"GOFLAGS": "-buildvcs=false", "GOENV": "off", "CGO_ENABLED": "0",
                                 "GOOS": "windows", "GOARCH": "amd64", "GOAMD64": "v1"},
        "python_test_modules": list(PYTHON_MODULES),
    }
    files[EVIDENCE + "/package/manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    output = ["*** Begin Patch"]
    for path, content in sorted(files.items()):
        destination = repo / path
        if destination.exists():
            old = destination.read_text(encoding="utf-8").replace("\r\n", "\n")
            if old == content:
                continue
            output.append("*** Update File: " + str(destination))
            output.extend("@@" if line.startswith("@@") else line for line in
                          list(difflib.unified_diff(old.splitlines(), content.splitlines(), n=3, lineterm=""))[2:])
        else:
            output.append("*** Add File: " + str(destination))
            output.extend("+" + line for line in content.splitlines())
    output.append("*** End Patch")
    return "\n".join(output) + "\n"


def run(args: list[str], cwd: Path, env: dict[str, str], timeout: int = 600) -> dict:
    started = time.monotonic()
    proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        raise
    return {"argv": args, "exit_code": proc.returncode, "seconds": round(time.monotonic() - started, 6),
            "stdout": out.decode("utf-8", errors="replace"), "stderr": err.decode("utf-8", errors="replace")}


def go_receipt(result: dict) -> dict:
    events = [json.loads(line) for line in result["stdout"].splitlines() if line.startswith("{")]
    terminal = [e for e in events if e.get("Test") and e.get("Action") in ("pass", "fail", "skip")]
    return {**{k: v for k, v in result.items() if k != "stdout"},
            "top_level_passes": sum(e["Action"] == "pass" and "/" not in e["Test"] for e in terminal),
            "pass_events": sum(e["Action"] == "pass" for e in terminal),
            "failures": sorted(e["Test"] for e in terminal if e["Action"] == "fail"),
            "skips": sorted(e["Test"] for e in terminal if e["Action"] == "skip"),
            "failure_output": [e.get("Output", "") for e in events if e.get("Action") == "output"
                               and (e.get("Test") in {f["Test"] for f in terminal if f["Action"] == "fail"})]}


@contextmanager
def optimizer_slot(root: Path):
    """Share the legacy runner's nonblocking OS lease; preserve its lock file."""
    if not root.is_absolute():
        raise ValueError("absolute optimizer scratch root required")
    for path in (*reversed(root.parents), root):
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("linked optimizer scratch path")
    if not root.exists():
        yield
        return
    lock = root / ".gtt-active.lock"
    if set(root.iterdir()) != {lock}:
        raise ValueError("an existing optimizer scratch job blocks release validation")
    info = lock.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size != 1:
        raise ValueError("invalid optimizer scratch lease")
    with lock.open("r+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        acquire()
        try:
            if set(root.iterdir()) != {lock}:
                raise ValueError("optimizer scratch changed under lease")
            yield
        finally:
            handle.seek(0)
            release()


def compatibility(repo: Path, main: Path, manifest: dict, bundle: Path) -> dict:
    head = git(main, "rev-parse", "HEAD").decode().strip()
    entries = tree(main, head)
    contents = blobs(main, [entries[row["path"]] for row in manifest["patches"] if row["path"] in entries])
    rows = []
    for patch in manifest["patches"]:
        path = patch["path"]
        target = contents[entries[path]] if path in entries else b""
        current_path = main / path
        live = current_path.read_bytes() if current_path.is_file() else b""
        status = "exact_before" if sha_bytes(target) == patch["before_sha256"] else "already_after" if sha_bytes(target) == patch["after_sha256"] else "review_required"
        if status == "review_required":
            try:
                apply_file_patch(path, target, (bundle / patch["payload"]).read_text(encoding="utf-8"))
                status = "patch_context_compatible"
            except ValueError:
                pass
        rows.append({"path": path, "role": patch["role"], "main_head_sha256": sha_bytes(target),
                     "main_live_raw_sha256": sha_bytes(live), "live_differs_from_head": normalized(live) != target,
                     "head_compatibility": status})
    return {"main_head": head, "applied": False, "rows": rows,
            "next_step": "integrator reviews frozen external guard and main conflicts, preserves main dirty hunks, then verifies a separately authorized clean target; no live source replacement"}


def verify(repo: Path, main: Path, python: Path, go: Path) -> dict:
    manifest_path = repo / EVIDENCE / "package/manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest["base_head"] != BASE or manifest["capture_budget"] != 0:
        raise ValueError("unauthorized manifest")
    for path, digest in manifest["bootstrap"].items():
        if sha_bytes(normalized((repo / path).read_bytes())) != digest:
            raise ValueError("bootstrap differs from frozen package")
    if not go.is_file() or not python.is_file():
        raise ValueError("declared read-only dependency runtime unavailable")
    if manifest["dependency_runtime"] != {"go_sha256": sha_bytes(go.read_bytes()), "python_sha256": sha_bytes(python.read_bytes())}:
        raise ValueError("dependency runtime differs from frozen pins")
    old_scratch = repo / ".codex_tmp/managed-optimizer"
    initial = json.loads((repo / EVIDENCE / "initial.json").read_text(encoding="utf-8"))
    # Hash every old draft at entry/exit; verification has no permission to edit it.
    live_before = {path: sha_bytes((repo / path).read_bytes()) for path in initial["prior_draft_raw_sha256"]}
    pins = {**initial["runtime_raw_sha256"], **initial["account_initial_raw_sha256"]}
    if any(sha_bytes((repo / path).read_bytes()) != digest for path, digest in pins.items()):
        raise ValueError("runtime/account changed before release checks")
    bundle = repo / EVIDENCE / "package/patches"
    receipt = {"schema_kind": "gtt_theory_clean_package_validation_v1", "date": "2026-10-11",
               "manifest_sha256": sha_bytes(raw), "base_head": BASE, "capture_budget": 0,
               "engine_calls": 0, "installed": False, "checks": [],
               "toolchain": {"go_path": str(go), "go_sha256": sha_bytes(go.read_bytes()),
                             "python_path": str(python), "python_sha256": sha_bytes(python.read_bytes())},
               "compatibility": compatibility(repo, main, manifest, bundle)}
    lifecycle = None
    try:
        with optimizer_slot(old_scratch), managed_job(repo / ".codex_tmp/theory-clean-assembly") as lifecycle:
            job = lifecycle["path"]
            assembly = job / "assembly"
            records = materialize_from_manifest(repo, manifest, bundle, assembly)
            receipt["assembly_files"] = len(records)
            receipt["assembly_sha256"] = sha_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())
            receipt["excluded_dirty_legacy_verified"] = all(records[path]["after_sha256"] == records[path]["base_sha256"] for path in EXCLUDED_DIRTY)
            if not receipt["excluded_dirty_legacy_verified"]:
                raise ValueError("excluded dirty legacy sources entered the assembly")
            receipt["numerical_preservation"] = numerical_preservation(repo, initial, assembly)
            if receipt["numerical_preservation"] != manifest["numerical_preservation"]:
                raise ValueError("frozen numerical preservation proof differs from assembly")
            for name in ("temp", "go-cache", "go-mod", "rule-cache", "bundled-cache"):
                (job / name).mkdir()
            env = dict(os.environ)
            for name in ("PYTHONPATH", "PYTHONHOME", "GTT_THEORY_OUTPUT_EXPORT", "GTT_ENGINE_ROOT", "GTT_RUN_ROOT"):
                env.pop(name, None)
            env.update(PYTHONDONTWRITEBYTECODE="1", QT_QPA_PLATFORM="offscreen",
                       TEMP=str(job / "temp"), TMP=str(job / "temp"),
                       GOCACHE=str(job / "go-cache"), GOMODCACHE=str(job / "go-mod"), GOTMPDIR=str(job / "temp"),
                       GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOWORK="off",
                       GTT_RULE_CACHE_DIR=str(job / "rule-cache"), GTT_BUNDLED_CACHE_DIR=str(job / "bundled-cache"),
                       GTT_THEORY_OUTPUT_EXPORT=str(job / "native-public-output.json"))
            env.update(manifest["go_build_environment"], GOROOT=str(go.parent.parent))
            version = run([str(go), "version"], assembly, env, 30)
            receipt["toolchain"]["go_version"] = version["stdout"].strip()
            native = assembly / "native/gcsim_optimizer"
            core = ["./internal/theoryalloc", "./internal/theorysearch", "./internal/theorypackages"]
            route = ["-run", "Theory|Finish|Selected|AllSetsNeutralRoute|SeedFull45|Publication|ValidationRejectsIllegalSlot|RuleAccessors|Linear",
                     "./internal/contracts", "./internal/formula", "./internal/seteffects", "./internal/setcontext", "./cmd/gtt-optimizer"]
            for group in (core, route):
                result = go_receipt(run([str(go), "test", "-json", "-count=1", "-p=2", *group], native, env))
                receipt["checks"].append(result)
                print(json.dumps({"step": "go tests", "exit": result["exit_code"], "passed": result["top_level_passes"], "failures": result["failures"]}), flush=True)
                if result["exit_code"]:
                    raise RuntimeError("clean native gate failed")
            build = run([str(go), "build", "-trimpath", "-o", str(job / "gtt-optimizer-clean.exe"), "./cmd/gtt-optimizer"], native, env)
            receipt["checks"].append(build)
            if build["exit_code"]:
                raise RuntimeError("clean build failed")
            receipt["built_binary_sha256"] = sha_bytes((job / "gtt-optimizer-clean.exe").read_bytes())
            repeat = run([str(go), "build", "-trimpath", "-o", str(job / "gtt-optimizer-repeat.exe"), "./cmd/gtt-optimizer"], native, env)
            receipt["reproducible_build_check"] = repeat
            receipt["reproducible_build_verified"] = repeat["exit_code"] == 0 and sha_bytes((job / "gtt-optimizer-repeat.exe").read_bytes()) == receipt["built_binary_sha256"]
            if not receipt["reproducible_build_verified"]:
                raise RuntimeError("same frozen assembly produced a different native binary")
            # These engine-source-dependent controls are explicitly outside the
            # frozen public source packet. Record skips, never infer a PASS.
            boundary = go_receipt(run([str(go), "test", "-json", "-count=1", "-p=2", "-run",
                                      "^(TestRuleActiveMarechausseeHealingBranch|TestRuleActiveSongRejectsMissingHitIdentity)$", "./internal/seteffects"], native, env))
            receipt["external_guard_legacy_controls"] = boundary
            expected = {"TestRuleActiveMarechausseeHealingBranch", "TestRuleActiveSongRejectsMissingHitIdentity"}
            if boundary["failures"] or set(boundary["skips"]) != expected or boundary["top_level_passes"] != 0:
                raise RuntimeError("external guard compatibility boundary changed")
            boundary["status"] = "SKIPPED_EXTERNAL_ENGINE_SOURCE_NOT_DECLARED"
            export = job / "native-public-output.json"
            if not export.is_file():
                raise RuntimeError("independently verified native output was not exported")
            receipt["native_export_sha256"] = sha_bytes(export.read_bytes())
            code = "import sys,unittest;sys.path.insert(0,sys.argv[1]);suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]);r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not r.wasSuccessful())"
            py = run([str(python), "-I", "-B", "-c", code, str(assembly), *manifest["python_test_modules"]], assembly, env, 180)
            receipt["checks"].append(py)
            print(json.dumps({"step": "python offscreen/tests", "exit": py["exit_code"]}), flush=True)
            if py["exit_code"]:
                raise RuntimeError("clean Python/offscreen gate failed")
            receipt["status"] = "PASS_OWN_PACKAGE_WITH_DECLARED_EXTERNAL_PREREQUISITE"
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["failure_traceback"] = traceback.format_exc()
    finally:
        receipt["cleanup"] = {k: str(v) if isinstance(v, Path) else v for k, v in (lifecycle or {}).items()}
        receipt["prior_drafts_unchanged_by_verification"] = all(sha_bytes((repo / path).read_bytes()) == digest for path, digest in live_before.items())
        receipt["runtime_account_pins_unchanged"] = all(sha_bytes((repo / path).read_bytes()) == digest for path, digest in pins.items())
        if not receipt["prior_drafts_unchanged_by_verification"] or not receipt["runtime_account_pins_unchanged"] or not receipt["cleanup"].get("cleaned"):
            receipt["status"] = "FAIL"
    return receipt


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "verify"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--main", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--go", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    if args.mode == "freeze":
        sys.stdout.write(freeze(repo))  # Apply this reviewable patch with apply_patch.
        return 0
    if not args.main or not args.python or not args.go:
        parser.error("verify requires explicit read-only main, Python and Go paths")
    result = verify(repo, args.main.resolve(strict=True), args.python.resolve(strict=True), args.go.resolve(strict=True))
    print("RECEIPT_JSON=" + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
