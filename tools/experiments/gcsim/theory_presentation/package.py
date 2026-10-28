"""Stage17: fresh main identity/overlays + reviewed Theory + presentation hunks.

Only Worker2 packet files and leased scratch are written. Previous patches are
reused by exact content hash after fresh hunk replay, never as an implicit target.
"""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import stat
from typing import Any

from tools.experiments.gcsim.theory_release import package_io as io, release as source, target_release as prior
from tools.experiments.gcsim.theory_release.target_hunks import relocate_hunks

EVIDENCE = "docs/optimizer-evidence/2026-10-11-theory-presentation"
HERE = "tools/experiments/gcsim/theory_presentation/package.py"
SOURCE = prior.SOURCE_EVIDENCE
PREVIOUS = prior.EVIDENCE
SOURCE_MANIFEST_SHA = prior.SOURCE_MANIFEST_SHA
CHANGED = (
    "localization/locales/en.json", "localization/locales/pt-br.json", "localization/locales/ru.json",
    "ui/utils/ui_palette.py", "ui/gcsim_browser/optimizer_result.py",
    "ui/gcsim_browser/window.py", "ui/app_shell.py",
    "run_workspace/gcsim/optimizer_go_theory_session.py",
    "tests/ui/gcsim_browser/test_theory_session_ui.py",
)
NEW = (
    "run_workspace/gcsim/optimizer_theory_presentation.py",
    "tests/run_workspace/gcsim/test_optimizer_theory_presentation.py",
    "ui/gcsim_browser/theory_result.py", "tests/ui/gcsim_browser/test_theory_presentation.py",
    HERE, "tests/tools/test_theory_presentation_package.py",
)
LEGACY = (
    "run_workspace/gcsim/optimizer_go_theory.py",
    "tests/run_workspace/gcsim/test_optimizer_go_theory.py",
)
RETIRED_TESTS = frozenset({
    "test_partial_result_is_not_labeled_complete",
    "test_formatter_explains_non_owned_result_and_allocations",
    "test_formatter_keeps_the_backend_top_five",
})


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pins(repo: Path, main: Path, initial: dict) -> dict:
    head = source.git(main, "rev-parse", "HEAD").decode().strip()
    if head != initial["main_head"]:
        raise ValueError("main Git identity changed; a fresh provenance rebind is required")
    actual = {}
    for path, record in initial["main_relevant_live"].items():
        target = main / path
        if target.exists() != record["exists"]:
            raise ValueError("main existence changed: " + path)
        digest = io.sha_bytes(target.read_bytes()) if target.exists() else None
        if digest != record["raw_sha256"]:
            raise ValueError("main relevant body changed: " + path)
        actual[path] = digest
    runtime = {p: io.sha_bytes((repo / p).read_bytes()) for p in initial["worker_runtime_account_raw_sha256"]}
    if runtime != initial["worker_runtime_account_raw_sha256"]:
        raise ValueError("Worker2 runtime/account changed")
    return {"target_head": head, "target_live_raw_sha256": actual, "worker_runtime_account_raw_sha256": runtime}


def _without_functions(body: bytes, names: set[str]) -> bytes:
    text = body.decode()
    lines = text.splitlines(keepends=True)
    nodes = [n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        start = min([node.lineno] + [x.lineno for x in node.decorator_list]) - 1
        end = node.end_lineno
        while end < len(lines) and not lines[end].strip():
            end += 1
        del lines[start:end]
    return "".join(lines).encode()


def _retire_legacy(path: str, body: bytes, repo: Path) -> bytes:
    if path == LEGACY[0]:
        result = _without_functions(body, {"format_gcsim_optimizer_go_theory_result"})
        result = result.replace(b"from .optimizer_go_result_text import format_optimizer_warning\n", b"")
        result = result.replace(b'    "format_gcsim_optimizer_go_theory_result",\n', b"")
    else:
        result = _without_functions(body, set(RETIRED_TESTS))
        result = result.replace(b"    format_gcsim_optimizer_go_theory_result,\n", b"")
        # Keep the finite-energy guard test; retire only its old-text assertion.
        text = result.decode(); lines = text.splitlines(keepends=True)
        current = source.normalized((repo / path).read_bytes()).decode()
        latest_lines = current.splitlines(keepends=True)
        latest = next(n for n in ast.walk(ast.parse(current)) if isinstance(n, ast.FunctionDef) and n.name == "test_finite_energy_theory_fails_before_formula_search")
        old = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == latest.name)
        lines[old.lineno - 1:old.end_lineno] = latest_lines[latest.lineno - 1:latest.end_lineno]
        result = "".join(lines).encode()
    if b"format_gcsim_optimizer_go_theory_result" in result:
        raise ValueError("retired v1 formatter remains in target: " + path)
    ast.parse(result.decode())
    return result


def _widget_context_rebase(before: bytes, after: bytes) -> tuple[bytes, bytes, list[dict]]:
    """Keep the main owner's geometry while preserving every Stage17 edit."""
    from tools.experiments.gcsim.theory_release.target_hunks import _parse_hunks
    def intent(left, right):
        _, hunks = _parse_hunks(io.make_patch("ui/gcsim_browser/optimizer_result.py", left, right))
        return [(prefix, line) for hunk in hunks for prefix, line in hunk["events"] if prefix != " "]
    original = intent(before, after)
    resolutions = []
    pairs = (
        (b"                    self.grid.addWidget(missing, row_index, column)\n",
         b"                    self.grid.addWidget(missing, row_index, column, alignment=Qt.AlignmentFlag.AlignTop)\n"),
        (b"                        column,\n                    )\n",
         b"                        column,\n                        alignment=Qt.AlignmentFlag.AlignTop,\n                    )\n"),
        (b"            action_layout.setContentsMargins(2, 0, 0, 0)\n",
         b"            action_layout.setContentsMargins(0, 0, 0, 0)\n"),
        (b'            button = QPushButton(_translated("artifact.build.save", "Save"))\n',
         b'            button = QPushButton(_translated("artifact.build.save", "Save"))\n            button.setMinimumHeight(28)\n'),
        (b"        root.setContentsMargins(3, 3, 3, 3)\n",
         b"        root.setContentsMargins(6, 6, 6, 6)\n"),
    )
    for old, new in pairs:
        if before.count(old) != 1 or after.count(old) != 1:
            raise ValueError("the reviewed widget context resolution is no longer unique")
        before, after = before.replace(old,new), after.replace(old,new)
        resolutions.append({"old_context":old.decode(),"retained_target_context":new.decode()})
    if intent(before,after) != original:
        raise ValueError("widget context resolution changed Stage17 edit intent")
    return before,after,resolutions


def freeze_files(repo: Path, main: Path) -> dict[str, str]:
    initial = read(repo / EVIDENCE / "initial.json")
    pins(repo, main, initial)
    raw = (repo / SOURCE / "package/manifest.json").read_bytes()
    if io.sha_bytes(raw) != SOURCE_MANIFEST_SHA:
        raise ValueError("reviewed source dependency changed")
    original = json.loads(raw)
    entries = source.tree(main, initial["main_head"])
    old_entries = source.tree(repo, original["base_head"])
    old_blobs = source.blobs(repo, [old_entries[r["path"]] for r in original["patches"] if r["path"] in old_entries])
    worker_entries = source.tree(repo, initial["worker_head"])
    worker_blobs = source.blobs(repo, [worker_entries[p] for p in CHANGED])
    target_paths = set(initial["main_relevant_live"]) | {r["path"] for r in original["patches"]} | set(prior.OWN_NEW) | set(CHANGED) | set(NEW) | set(LEGACY)
    paths = sorted(p for p in entries if (
        (p.startswith("native/gcsim_optimizer/") and p.endswith((".go", "go.mod", "go.sum")))
        or (p.endswith(".py") and ("/" not in p or p.startswith(("ui/", "hoyolab_export/", "run_workspace/", "localization/", "tests/"))))
        or p.startswith("tests/fixtures/gcsim_optimizer_go_v1/")
        or p in target_paths or (p.startswith("ui/") and p.endswith(".qss"))
    ))
    base_blobs = source.blobs(main, [entries[p] for p in paths])
    base = {p: base_blobs[entries[p]] for p in paths}
    final = {p: base.get(p, b"") for p in target_paths}
    files: dict[str, str] = {}
    payload_sources: dict[str, dict] = {}
    dirty: dict[str, dict] = {}
    reviews: dict[str, dict] = {}
    changes_before: dict[str, bytes] = {}

    def payload(group: str, path: str, patch: str) -> str:
        logical = group + "/" + path + ".patch"
        body = patch.encode(); digest = io.sha_bytes(body)
        old_path = PREVIOUS + "/package/" + logical
        old_file = repo / old_path
        if old_file.is_file() and old_file.read_bytes() == body:
            physical, reused = old_path, True
        else:
            physical, reused = EVIDENCE + "/package/payloads/" + digest + ".patch", False
            files[physical] = patch
        payload_sources[logical] = {"repository_path": physical, "sha256": digest, "bytes": len(body), "reused_exact_prior_payload_after_fresh_replay": reused}
        return logical

    for p, record in initial["main_relevant_live"].items():
        if not record["exists"]:
            continue
        live = source.normalized((main / p).read_bytes())
        before = base.get(p, b"")
        if before != live:
            logical = payload("overlays", p, io.make_patch(p, before, live))
            dirty[p] = {"payload": logical, "payload_sha256": payload_sources[logical]["sha256"],
                        "raw_sha256": record["raw_sha256"], "before_sha256": io.sha_bytes(before),
                        "after_sha256": io.sha_bytes(live), "authorship": "current target-owned live overlay; preserved, not claimed"}
        final[p] = live

    for r in original["patches"]:
        p = r["path"]
        raw_patch = (repo / SOURCE / "package/patches" / r["payload"]).read_bytes()
        if io.sha_bytes(raw_patch) != r["payload_sha256"]:
            raise ValueError("source patch changed: " + p)
        original_before = old_blobs[old_entries[p]] if p in old_entries else b""
        current = final.get(p, b"")
        override = prior._guard_context(raw_patch.decode()) if p == "ui/gcsim_browser/window.py" else None
        after, hunks = relocate_hunks(p, original_before, current, raw_patch.decode(), override)
        changes_before[p] = current
        final[p] = after
        reviews[p] = {"path": p, "role": r["role"], "source_payload_sha256": r["payload_sha256"],
                      "prior_source_hunks": hunks, "target_before_sha256": io.sha_bytes(current)}

    for p in prior.OWN_NEW:
        changes_before.setdefault(p, final.get(p, b""))
        final[p] = source.normalized((repo / p).read_bytes())
        reviews.setdefault(p, {"path": p, "role": "owned_validation_helper"})
    for p in CHANGED:
        before = worker_blobs[worker_entries[p]]
        after = source.normalized((repo / p).read_bytes())
        if io.sha_bytes(source.normalized((repo / p).read_bytes())) == io.sha_bytes(before):
            continue
        if io.sha_bytes(source.normalized(source.git(repo, "show", initial["worker_head"] + ":" + p))) != io.sha_bytes(before):
            raise ValueError("worker baseline identity mismatch")
        widget_resolution = []
        if p == "ui/gcsim_browser/optimizer_result.py":
            before, after, widget_resolution = _widget_context_rebase(before, after)
        patch = io.make_patch(p, before, after)
        overrides = None
        if p == "ui/gcsim_browser/window.py" and "    def _request_optimizer_mode(self, mode: str) -> None:\n" in patch:
            overrides = prior._guard_context(patch)
        current = final.get(p, base.get(p, b""))
        changes_before.setdefault(p, current)
        try:
            final[p], hunks = relocate_hunks(p, before, current, patch, overrides)
        except ValueError as exc:
            raise ValueError("Stage17 presentation hunk " + p + ": " + str(exc)) from exc
        review = reviews.setdefault(p, {"path": p, "role": "owned_presentation"})
        review["presentation_hunks"] = hunks
        review["worker_baseline_git_blob"] = worker_entries[p]
        review["worker_source_raw_sha256"] = io.sha_bytes((repo / p).read_bytes())
        if widget_resolution:
            review["shared_context_resolution_preserving_exact_edit_intent"] = widget_resolution
    for p in LEGACY:
        current = final[p]
        changes_before.setdefault(p, current)
        final[p] = _retire_legacy(p, current, repo)
        reviews.setdefault(p, {"path": p, "role": "own_source"})["legacy_retirement"] = "named dead formatter/tests only; request/lifecycle/finite guard/availability retained"
    for p in NEW:
        if (main / p).exists():
            raise ValueError("new own path collides with target-owned file: " + p)
        changes_before.setdefault(p, b"")
        final[p] = source.normalized((repo / p).read_bytes())
        reviews[p] = {"path": p, "role": "owned_presentation_or_validation", "worker_source_raw_sha256": io.sha_bytes((repo / p).read_bytes())}

    patches, transfer = [], []
    for p, after in sorted(final.items()):
        before = base.get(p, b"")
        if before == after:
            continue
        combined = payload("combined", p, io.make_patch(p, before, after))
        patches.append({"path": p, "payload": p + ".patch", "payload_sha256": payload_sources[combined]["sha256"],
                        "before_sha256": io.sha_bytes(before), "after_sha256": io.sha_bytes(after), "existing_dirty_overlay": dirty.get(p)})
        if p in reviews:
            target_before = changes_before.get(p, source.normalized((main / p).read_bytes()) if (main / p).is_file() else b"")
            logical = payload("theory", p, io.make_patch(p, target_before, after))
            review = reviews[p]
            review.update(resolved_payload=logical, resolved_payload_sha256=payload_sources[logical]["sha256"],
                          target_before_sha256=io.sha_bytes(target_before), target_after_sha256=io.sha_bytes(after))
            transfer.append({"path": p, "role": review["role"], "payload": logical,
                             "payload_source": payload_sources[logical],
                             "before_normalized_sha256": io.sha_bytes(target_before), "after_normalized_sha256": io.sha_bytes(after)})
    locales = {}
    for p in CHANGED[:3]:
        current = json.loads((main / p).read_text(encoding="utf-8")); merged = json.loads(final[p])
        if any(merged.get(key) != value for key, value in current.items()):
            raise ValueError("target-owned locale value was replaced")
        locales[p] = {"retained_keys": len(current), "added_keys": sorted(set(merged)-set(current)), "retained_values_unchanged": True}
    bootstrap = {p: io.sha_bytes(source.normalized((repo / p).read_bytes())) for p in (HERE, prior.TOOLS+"target_release.py", prior.TOOLS+"target_hunks.py", prior.TOOLS+"package_io.py", prior.TOOLS+"release.py")}
    manifest = {"schema_kind": "gtt_theory_presentation_target_package_v1", "date": "2026-10-11", "base_head": initial["main_head"],
                "source_parent": initial["worker_head"], "source_manifest_sha256": SOURCE_MANIFEST_SHA,
                "base_files": [{"path": p, "git_blob": entries[p], "sha256": io.sha_bytes(base[p]), "bytes": len(base[p])} for p in paths],
                "patches": patches, "target_dirty_layers": dirty, "hunk_review": list(reviews.values()), "locale_review": locales,
                "payload_sources": payload_sources, "capture_budget": 0, "engine_calls": 0, "installed": False,
                "bootstrap": bootstrap, "dependency_runtime": original["dependency_runtime"], "go_build_environment": original["go_build_environment"],
                "python_test_modules": list(dict.fromkeys(list(read(repo/PREVIOUS/"package/manifest.json")["python_test_modules"]) + [
                    "tests.run_workspace.gcsim.test_optimizer_theory_presentation", "tests.ui.gcsim_browser.test_theory_presentation",
                    "tests.ui.gcsim_browser.test_gcsim_optimizer_result_basis", "tests.tools.test_theory_presentation_package"])),
                "owned_payload_retention": "until explicit human acceptance or authorized consolidation; gated exact-hash cleaner"}
    files[EVIDENCE + "/package/manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    recipe = {"schema_kind": "gtt_theory_presentation_transfer_v1", "source_parent": initial["worker_head"], "target_head": initial["main_head"],
              "target_manifest_sha256": io.sha_bytes(files[EVIDENCE+"/package/manifest.json"].encode()),
              "target_dirty_raw_sha256": {p:r["raw_sha256"] for p,r in initial["main_relevant_live"].items() if p in dirty},
              "transfer_paths": transfer, "assembly_only_preserved_target_paths": sorted(p for p in dirty if p not in reviews),
              "capture_budget": 0, "engine_calls": 0, "main_writes": 0, "installed": False,
              "external_guard_authorship": "unresolved; unchanged external prerequisite, not Worker2 UI implementation",
              "release_boundary": "root reviews exact packet; main owner integrates only after release; active-engine gate budget and physical UI acceptance remain separate"}
    files[EVIDENCE+"/transfer-recipe.json"] = json.dumps(recipe, indent=2, sort_keys=True) + "\n"
    pins(repo, main, initial)
    return files


def freeze(repo: Path, main: Path) -> str:
    return prior._emit_patch(repo, freeze_files(repo, main))


def _read_payload(repo: Path, record: dict) -> bytes:
    relative = str(io.safe_relative(record["repository_path"]))
    data = io._read(repo, relative)
    if len(data) != record["bytes"] or io.sha_bytes(data) != record["sha256"]:
        raise ValueError("frozen referenced payload changed: " + relative)
    return data


def verify(repo: Path, main: Path, python: Path, go: Path) -> dict:
    initial = read(repo/EVIDENCE/"initial.json"); pins(repo,main,initial)
    manifest = read(repo/EVIDENCE/"package/manifest.json")
    # The established checker gets a temporary physical view of the new packet.
    # It replays current dirty/Theory layers, numerical-body proof, source guards,
    # standard builds and declared Python/offscreen tests; it executes no engine.
    with io.managed_job(repo/".codex_tmp/theory-presentation-packet") as packet_job:
        mirror = packet_job["path"]/"packet"; (mirror/"package").mkdir(parents=True)
        translated = dict(initial, target_head=initial["main_head"],
                          worker_prior147_raw_sha256=initial["prior147_current_raw_sha256"])
        (mirror/"initial.json").write_text(json.dumps(translated),encoding="utf-8")
        for logical, record in manifest["payload_sources"].items():
            path = mirror/"package"/io.safe_relative(logical)
            path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(_read_payload(repo,record))
        (mirror/"package/manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        previous_evidence, previous_pins, previous_new = prior.EVIDENCE, prior.current_pins, prior.OWN_NEW
        try:
            prior.EVIDENCE = str(mirror)
            prior.current_pins = lambda r,m,i:pins(r,m,initial)
            prior.OWN_NEW = (*previous_new,*NEW)
            result = prior.verify(repo,main,python,go)
        finally:
            prior.EVIDENCE,prior.current_pins,prior.OWN_NEW = previous_evidence,previous_pins,previous_new
        result["schema_kind"]="gtt_theory_presentation_target_validation_v1"
        result["manifest_sha256"]=io.sha_bytes((repo/EVIDENCE/"package/manifest.json").read_bytes())
        result["staged_packet_manifest_sha256"]=io.sha_bytes((mirror/"package/manifest.json").read_bytes())
    result["packet_cleanup"]={k:str(v) if isinstance(v,Path) else v for k,v in packet_job.items()}
    if not result["packet_cleanup"].get("cleaned"):result["status"]="FAIL"
    pins(repo,main,initial)
    return result


def cleanup_packet(repo: Path, *, accepted_or_consolidated: bool=False) -> dict:
    if not accepted_or_consolidated:
        raise ValueError("explicit human acceptance or authorized consolidation is required")
    manifest = read(repo/EVIDENCE/"package/manifest.json")
    records = {r["repository_path"]:r for r in manifest["payload_sources"].values()
               if not r["reused_exact_prior_payload_after_fresh_replay"]}
    prefix=EVIDENCE+"/package/payloads/"
    for path, record in records.items():
        if not path.startswith(prefix) or not path.endswith(".patch") or "/" in path[len(prefix):]:
            raise ValueError("cleanup path is outside exact owned payload scope")
        _read_payload(repo,record)
    count=total=0
    for path,record in records.items():
        io._child(repo,path).unlink(); count+=1;total+=record["bytes"]
    return {"removed_files":count,"removed_bytes":total,"prior_payloads_receipts_manifest_protocol_and_reports_preserved":True}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("freeze","verify","cleanup"))
    parser.add_argument("--repo",type=Path,required=True)
    parser.add_argument("--main",type=Path)
    parser.add_argument("--python",type=Path)
    parser.add_argument("--go",type=Path)
    parser.add_argument("--accepted-or-authorized-consolidation",action="store_true")
    args=parser.parse_args()
    repo=args.repo.resolve()
    if args.action=="freeze":
        print(freeze(repo,args.main.resolve()),end="")
    elif args.action=="verify":
        print(json.dumps(verify(repo,args.main.resolve(),args.python.resolve(),args.go.resolve()),ensure_ascii=True))
    else:
        print(json.dumps(cleanup_packet(repo,accepted_or_consolidated=args.accepted_or_authorized_consolidation)))
    return 0

if __name__=="__main__":raise SystemExit(main())
