"""Gate a source-built All Sets consumer through the real application adapter.

Run only under managed_optimizer_experiment.py after an accepted matrix pair.
The request is retained evidence, not rebuilt from an account. No binary is
installed unless both explicit install and parent-approval switches are given.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.engine_store import GcsimEngineStoreError, load_engine_manifest
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.source_manifest_build import (
    SOURCE_MANIFEST_BODY_KIND, SOURCE_MANIFEST_BODY_SCHEMA_VERSION,
    canonical_json as canonical_source_manifest_json,
)
from tools.experiments.gcsim.parametric_effects.capture_equivalence import capture_comparison_kind
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _expanded_manifest_entries
from tools.experiments.gcsim.search_hypotheses.matrix_pair import (
    EVIDENCE_ROOT, MANIFEST, captures, compare, prepare_reused_input, summarize,
    validated_evidence_dir,
)
from tools.experiments.gcsim.search_hypotheses.run import sha
from tools.managed_optimizer_experiment import owned_job

SOURCE = ROOT / "native/gcsim_optimizer"
INSTALLED = SOURCE / "gtt-optimizer.exe"
POINTER = ROOT / "data/gcsim/engines/active_engine.json"
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
PASS_STATUSES = frozenset(("paired_formula_gate_pass", "reference_baseline_reused_gate_pass"))


class CandidateSession(GcsimOptimizerGoAllSetsSession):
    """The real adapter with only its disposable rule cache pinned to this job."""

    def __init__(self, request, *, cache_dir: Path):
        super().__init__(request)
        self._candidate_cache_dir = cache_dir

    def _optimizer_environment(self):
        env = super()._optimizer_environment()
        env["GTT_RULE_CACHE_DIR"] = str(self._candidate_cache_dir)
        return env


def source_sha256(source: Path = SOURCE) -> str:
    files = sorted(p for p in source.rglob("*") if p.is_file() and
                   (p.suffix == ".go" or p.name in {"go.mod", "go.sum"}))
    return hashlib.sha256(b"".join(str(p.relative_to(source)).encode() + b"\0" + p.read_bytes()
                                   for p in files)).hexdigest()


def receipt_path(raw: Path) -> Path:
    raw = Path(raw)
    path = (raw if raw.is_absolute() else ROOT / raw).resolve()
    validated_evidence_dir(path.parent)
    if path.suffix != ".json" or path.exists():
        raise ValueError("Promotion receipt must be a new .json optimizer-evidence file")
    return path


def accepted_reference(raw: Path, variant: str):
    path = Path(raw).resolve(strict=True)
    if not path.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("Reference must be retained optimizer evidence")
    reference = json.loads(path.read_text(encoding="utf-8"))
    if reference.get("status") not in PASS_STATUSES or reference.get("variant") != variant:
        raise ValueError("Reference variant is not an accepted matrix pass")
    if not all(reference.get(k) is True for k in
               ("installed_unchanged", "active_pointer_unchanged", "engine_unchanged",
                "common_captures_equal")):
        raise ValueError("Reference failed identity or capture checks")
    if reference.get("comparison", {}).get("regressions") or any(
        reference.get("capture_key_difference", {}).get(k) for k in ("baseline_only", "candidate_only")
    ):
        raise ValueError("Reference has a quality or capture regression")
    for key in ("case", "request_sha256", "sources_sha256", "engine_sha256",
                "installed_sha256", "manifest_sha256", "source_sha256"):
        if not reference.get(key):
            raise ValueError(f"Reference lacks {key}")
    request = reference.get("request")
    runs = [r for r in reference.get("runs", ()) if r.get("name") == variant]
    if (not isinstance(request, dict) or len(runs) != 1 or
            runs[0].get("legal_output_checked") is not True or
            len(runs[0].get("rows", ())) != 49 or not runs[0].get("captures") or
            not isinstance(runs[0].get("warnings"), list)):
        raise ValueError("Reference lacks a complete 49-row accepted candidate")
    return path, reference, runs[0]


def assert_engine(reference, active) -> None:
    """Recompute the request's standalone binding, not the legacy context hash."""
    bound = reference["request"]["engine"]
    if (Path(bound["binary_path"]).resolve() != Path(active.artifact_path).resolve() or
            bound["artifact_sha256"] != active.artifact_sha256 or
            reference["engine_sha256"] != active.artifact_sha256 or
            sha(active.artifact_path) != active.artifact_sha256):
        raise ValueError("Retained request is not bound to the current active engine")
    root = Path(active.engine_root).resolve()
    source_path = root / "build" / "gtt-source-manifest-body.json"
    try:
        body = json.loads(source_path.read_bytes())
        manifest = load_engine_manifest(root)
        patch_sha = str(manifest.patch_metadata.get("patch_stack_sha256", "") or "").casefold()
        if (not isinstance(body, dict) or
                type(body.get("schema_version")) is not int or
                body["schema_version"] != SOURCE_MANIFEST_BODY_SCHEMA_VERSION or
                body.get("kind") != SOURCE_MANIFEST_BODY_KIND or
                body.get("patch_stack_sha256") != patch_sha or
                len(patch_sha) != 64 or any(c not in "0123456789abcdef" for c in patch_sha)):
            raise ValueError("Malformed active source or patch manifest")
        source_sha = hashlib.sha256(canonical_source_manifest_json(body).encode("utf-8")).hexdigest()
    except (OSError, ValueError, TypeError, KeyError, GcsimEngineStoreError) as exc:
        raise ValueError("Active engine source manifest is invalid") from exc
    standalone = canonical_sha256({
        "kind": "gtt.standalone_engine_binding.v1",
        "artifact_sha256": active.artifact_sha256,
        "source_manifest_sha256": source_sha,
        "patch_manifest_sha256": patch_sha,
    })
    if (bound.get("source_manifest_sha256") != source_sha or
            bound.get("patch_manifest_sha256") != patch_sha or
            bound.get("binding_sha256") != standalone):
        raise ValueError("Retained request standalone source/patch binding differs from active engine")


def adapter_request(job: Path, reference, candidate: Path | None):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if sha(MANIFEST) != reference["manifest_sha256"]:
        raise ValueError("Matrix manifest changed since the accepted reference")
    entries = {e["id"]: e for e in _expanded_manifest_entries(manifest) if e["mode"] == "all_sets"}
    entry = entries[reference["case"]]
    request = GcsimOptimizerGoAllSetsRequest(
        db_path=str(job / "unused-account.db"), selected_team={}, team_index=0,
        rotation_shell_text="", infinite_energy_enabled=bool(entry.get("infinite_energy", True)),
        run_root=str(job / "unused-runs"), fast_mode=True, set_group_limit=7,
        builds_per_group=7, product_timeout_ms=0,
    )
    if Path(request.optimizer_binary_path).resolve() != INSTALLED.resolve():
        raise ValueError("Default application consumer no longer resolves to installed optimizer")
    return replace(request, optimizer_binary_path=str(candidate)) if candidate is not None else request


def adapter_prepared(reference):
    """The adapter hashes canonical JSON without the on-disk trailing newline."""
    return {"request": reference["request"],
            "request_sha256": canonical_sha256(reference["request"])}


def parity(reference_run, candidate_run):
    # Retained JSON turns fingerprint ID tuples into arrays. Normalize both
    # sides before comparing exact rows, without changing their numeric bits.
    normalized_reference = json.loads(json.dumps(reference_run))
    normalized_candidate = json.loads(json.dumps(candidate_run))
    comparison = compare(normalized_reference, normalized_candidate)
    comparison.pop("search_speedup", None)  # Separate runs are not a paired speed proof.
    old_captures, new_captures = reference_run["captures"], candidate_run["captures"]
    old_keys, new_keys = set(old_captures), set(new_captures)
    exact_49 = (comparison["exact_rows"] and len(reference_run["rows"]) == 49 and
                len(candidate_run["rows"]) == 49)
    capture_kinds = {key: capture_comparison_kind(old_captures[key], new_captures[key],
                                                  allow_algebraic=exact_49)
                     for key in sorted(old_keys & new_keys)}
    canonical_equal = old_keys == new_keys and bool(old_keys) and all(
        kind != "unmatched" for kind in capture_kinds.values())
    reasons = []
    if not comparison["exact_rows"] or len(candidate_run["rows"]) != 49:
        reasons.append("candidate_rows_differ_from_accepted_49")
    if reference_run["warnings"] != candidate_run["warnings"]:
        reasons.append("warnings_differ")
    if not canonical_equal:
        reasons.append("canonical_capture_keys_or_hashes_differ")
    return {"passed": not reasons, "reasons": reasons, "comparison": comparison,
            "capture_keys_equal": old_keys == new_keys,
            "canonical_captures_equal": canonical_equal,
            "capture_comparison_kinds": capture_kinds,
            "algebraic_capture_gate_exact_49": exact_49,
            "raw_captures_equal": old_captures == new_captures}


def postinstall_default_run(job: Path, reference, preinstall_run, source_work: Path):
    """Exercise the application's default executable on copied immutable inputs.

    No account, new capture preparation, Finish marker, or candidate output is
    copied. The installed optimizer creates its own verification in a new dir.
    """
    request = adapter_request(job, reference, None)
    if Path(request.optimizer_binary_path).resolve() != INSTALLED.resolve():
        raise ValueError("Post-install adapter did not select the default optimizer path")
    work = job / "installed-default-adapter"
    work.mkdir()
    for name, digest in (("request.json", reference["request_sha256"]),
                         ("set-sources.json", reference["sources_sha256"])):
        original = source_work / name
        if sha(original) != digest:
            raise ValueError(f"Pre-install {name} changed before default-path gate")
        shutil.copy2(original, work / name)
        if sha(work / name) != digest:
            raise ValueError(f"Post-install {name} differs from frozen input")
    session = CandidateSession(request, cache_dir=job / "installed-default-rule-cache")
    started = time.monotonic()
    session._validate_optimizer_request(run_dir=work, started=started)
    preflight_seconds = time.monotonic() - started
    session._run_go_optimizer(prepared=adapter_prepared(reference), compact={},
                              run_dir=work, started=started)
    process_seconds = time.monotonic() - started - preflight_seconds
    wrapper = json.loads((work / "optimizer-output.json").read_text(encoding="utf-8"))
    run = summarize(wrapper, reference["request"])
    run["captures"] = captures(work / "verification")
    for name, digest in (("request.json", reference["request_sha256"]),
                         ("set-sources.json", reference["sources_sha256"])):
        if sha(work / name) != digest or sha(source_work / name) != digest:
            raise ValueError(f"Default-path optimizer changed {name}")
    return {"optimizer_binary_path": str(Path(request.optimizer_binary_path).resolve()),
            "optimizer_sha256": sha(INSTALLED),
            "trace": {"preflight_seconds": preflight_seconds,
                      "process_seconds": process_seconds,
                      "search_seconds": run.get("search_seconds"),
                      "search_stop_reason": run.get("search_stop_reason")},
            "summary": {k: run[k] for k in
                        ("rows", "leaders", "warnings", "captures", "legal_output_checked")},
            "parity_to_preinstall": parity(preinstall_run, run)}


def require_postinstall_parity(evidence) -> None:
    verdict = evidence["parity_to_preinstall"]
    if not verdict["passed"]:
        raise ValueError("Installed default-path run differs from pre-install candidate: " +
                         ", ".join(verdict["reasons"]))


def require_install_approval(*, install: bool, parent_approved: bool) -> None:
    if install and not parent_approved:
        raise ValueError("--install also requires prior parent approval and --parent-approved")
    if parent_approved and not install:
        raise ValueError("--parent-approved is meaningful only with --install")


def install_candidate(candidate: Path, installed: Path, job: Path,
                      *, old_sha: str, candidate_sha: str, verify_after=None) -> None:
    """Exact-file replacement with a job-owned rollback copy; never called by default."""
    if sha(installed) != old_sha or sha(candidate) != candidate_sha:
        raise ValueError("Consumer changed before installation")
    backup = job / "previous-optimizer.exe"
    if job.stat().st_dev != installed.parent.stat().st_dev:
        raise ValueError("Managed scratch and optimizer must share a volume for atomic replacement")
    stage = job / "optimizer-promotion-stage.exe"
    if stage.exists():
        raise ValueError("A prior optimizer promotion stage exists")
    shutil.copy2(installed, backup)
    if sha(backup) != old_sha:
        raise ValueError("Optimizer backup is not byte-identical")
    replaced = False
    try:
        shutil.copy2(candidate, stage)
        if sha(stage) != candidate_sha or sha(installed) != old_sha:
            raise ValueError("Optimizer staging identity mismatch")
        os.replace(stage, installed)
        replaced = True
        if sha(installed) != candidate_sha:
            raise ValueError("Installed optimizer hash differs from candidate")
        if verify_after is not None:
            verify_after()
    except BaseException:
        if replaced:
            shutil.copy2(backup, stage)
            os.replace(stage, installed)
            if sha(installed) != old_sha:
                raise RuntimeError("Optimizer rollback identity mismatch")
        raise
    finally:
        if stage.exists():
            stage.unlink()


def save_receipt(path: Path, job: Path, receipt: dict, *, first: bool = False) -> None:
    data = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("Promotion receipt exceeds 2 MiB")
    if first:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    else:
        pending = job / "promotion-receipt.pending.json"
        pending.write_bytes(data)
        pending.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--parent-approved", action="store_true",
                        help="Assert explicit parent approval before optional installation")
    args = parser.parse_args()
    require_install_approval(install=args.install, parent_approved=args.parent_approved)
    job = owned_job()
    path = receipt_path(args.receipt)
    receipt = {"schema_version": 1, "status": "preparing", "variant": args.variant,
               "scope": "source-built real All Sets adapter; exact retained request; no account DB",
               "install_requested": args.install, "parent_approval_asserted": args.parent_approved}
    save_receipt(path, job, receipt, first=True)
    stage = "reference"
    try:
        reference_path, reference, accepted = accepted_reference(args.reference, args.variant)
        receipt.update(reference=str(reference_path.relative_to(ROOT)).replace("\\", "/"),
                       reference_sha256=sha(reference_path), case=reference["case"],
                       request_sha256=reference["request_sha256"], sources_sha256=reference["sources_sha256"],
                       old_installed_sha256=sha(INSTALLED), engine_sha256=reference["engine_sha256"])
        if receipt["old_installed_sha256"] != reference["installed_sha256"]:
            raise ValueError("Installed optimizer differs from accepted matrix baseline")
        active = load_active_gcsim_optimizer_engine_context()
        assert_engine(reference, active)
        pointer_sha, production_sha = sha(POINTER), source_sha256()
        receipt.update(active_pointer_sha256=pointer_sha, production_source_sha256=production_sha,
                       engine_binding_sha256=active.binding_sha256)
        stage = "build"
        candidate = job / "promotion-candidate.exe"
        go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
        started = time.monotonic()
        with (job / "promotion-build.log").open("w", encoding="utf-8") as log:
            built = subprocess.run([go, "build", "-mod=readonly", "-trimpath", "-o", str(candidate),
                                    "./cmd/gtt-optimizer"], cwd=SOURCE, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=300, check=False)
        receipt["build_seconds"] = time.monotonic() - started
        if built.returncode:
            receipt["compiler_log_tail"] = (job / "promotion-build.log").read_text(
                encoding="utf-8", errors="replace")[-3000:]
            raise RuntimeError(f"Go build failed with exit {built.returncode}")
        receipt["candidate_sha256"] = sha(candidate)
        if sha(INSTALLED) != receipt["old_installed_sha256"] or source_sha256() != production_sha:
            raise ValueError("Production source or installed optimizer changed during build")
        stage = "adapter"
        request = adapter_request(job, reference, candidate)
        session = CandidateSession(request, cache_dir=job / "rule-cache")
        work = job / "adapter"
        work.mkdir()
        started = time.monotonic()
        prepare_reused_input(work, reference["request"], session,
                             request_sha=reference["request_sha256"],
                             sources_sha=reference["sources_sha256"])
        source_seconds = time.monotonic() - started
        session._validate_optimizer_request(run_dir=work, started=started)
        preflight_seconds = time.monotonic() - started - source_seconds
        prepared = adapter_prepared(reference)
        receipt["adapter_request_sha256"] = prepared["request_sha256"]
        session._run_go_optimizer(prepared=prepared, compact={}, run_dir=work, started=started)
        process_seconds = time.monotonic() - started - source_seconds - preflight_seconds
        wrapper = json.loads((work / "optimizer-output.json").read_text(encoding="utf-8"))
        candidate_run = summarize(wrapper, reference["request"])
        candidate_run["captures"] = captures(work / "verification")
        receipt.update(adapter_trace={"source_seconds": source_seconds,
                                      "preflight_seconds": preflight_seconds,
                                      "process_seconds": process_seconds,
                                      "search_seconds": candidate_run.get("search_seconds"),
                                      "search_stop_reason": candidate_run.get("search_stop_reason")},
                       candidate_summary={k: candidate_run[k] for k in
                                          ("rows", "leaders", "warnings", "captures", "legal_output_checked")})
        stage = "parity"
        verdict = parity(accepted, candidate_run)
        receipt["parity"] = verdict
        if not verdict["passed"]:
            raise ValueError("Source-built candidate differs from accepted source-copy reference: " +
                             ", ".join(verdict["reasons"]))
        if (sha(work / "request.json") != reference["request_sha256"] or
                sha(work / "set-sources.json") != reference["sources_sha256"] or
                sha(INSTALLED) != receipt["old_installed_sha256"] or
                sha(POINTER) != pointer_sha or source_sha256() != production_sha):
            raise ValueError("Request, source, installed optimizer, or active pointer changed during gate")
        final_active = load_active_gcsim_optimizer_engine_context()
        assert_engine(reference, final_active)
        if final_active.engine_tree_sha256 != active.engine_tree_sha256:
            raise ValueError("Active engine source tree changed during gate")
        receipt["status"] = "validated_not_installed"
        save_receipt(path, job, receipt)
        if args.install:
            stage = "install"
            def verify_installed() -> None:
                current_active = load_active_gcsim_optimizer_engine_context()
                assert_engine(reference, current_active)
                if (sha(POINTER) != pointer_sha or source_sha256() != production_sha or
                        current_active.engine_tree_sha256 != active.engine_tree_sha256):
                    raise ValueError("Active engine or source changed after optimizer installation")
                postinstall = postinstall_default_run(job, reference, candidate_run, work)
                receipt["postinstall_default_adapter"] = postinstall
                save_receipt(path, job, receipt)
                require_postinstall_parity(postinstall)
                final_post_active = load_active_gcsim_optimizer_engine_context()
                assert_engine(reference, final_post_active)
                if (postinstall["optimizer_sha256"] != receipt["candidate_sha256"] or
                        sha(POINTER) != pointer_sha or source_sha256() != production_sha or
                        final_post_active.engine_tree_sha256 != active.engine_tree_sha256):
                    raise ValueError("Installed optimizer, active engine, or source changed during default-path run")
                receipt["status"] = "validated_and_installed"
                save_receipt(path, job, receipt)
            install_candidate(candidate, INSTALLED, job,
                              old_sha=receipt["old_installed_sha256"],
                              candidate_sha=receipt["candidate_sha256"],
                              verify_after=verify_installed)
        print("PROMOTION_GATE " + json.dumps({
            "status": receipt["status"], "variant": args.variant,
            "receipt": str(path.relative_to(ROOT)).replace("\\", "/"),
            "candidate_sha256": receipt["candidate_sha256"],
            "old_installed_sha256": receipt["old_installed_sha256"],
            "installed": receipt["status"] == "validated_and_installed",
        }), flush=True)
        return 0
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["failure"] = {"stage": stage, "type": type(exc).__name__,
                              "message": str(exc)[:512]}
        raise
    finally:
        if receipt["status"] != "validated_and_installed":
            save_receipt(path, job, receipt)


if __name__ == "__main__":
    raise SystemExit(main())
