"""Regenerate the consolidated v2.45 patch with the reviewed energy ledger.

The cached official archive is the pristine base. The normal transactional
engine updater remains the only activation path; managed scratch owns both
temporary source copies and removes them after success or failure.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.engine_update import prepare_official_gcsim_engine_update
from run_workspace.gcsim.patch_backends import GitApplyPatchBackend
from run_workspace.gcsim.source_acquisition import (
    OfficialGcsimSourceRef,
    acquire_official_gcsim_source_from_archive,
)
from tools.managed_optimizer_experiment import managed_scratch


PATCH_NAME = "0001-gtt-engine-adapter-v245.patch"
ENERGY_PATHS = (
    "pkg/gtttrace/energy.go",
    "pkg/optimization/optstats/trace_equation.go",
    "pkg/gttcompact/model.go",
    "pkg/gttcompact/compile.go",
    "pkg/optimization/gtt_trace_equation.go",
    "pkg/gtt/info.go",
    "pkg/gtt/info_test.go",
)


def _export_patch(pristine: Path, patched: Path, paths: list[str]) -> str:
    output: list[str] = []
    for name in sorted(set(paths)):
        before = pristine / name
        after = patched / name
        old = before.read_text(encoding="utf-8").splitlines(True) if before.exists() else []
        new = after.read_text(encoding="utf-8").splitlines(True) if after.exists() else []
        if old == new:
            continue
        output.append(f"diff --git a/{name} b/{name}\n")
        if not old:
            output.append("new file mode 100644\n")
        output.extend(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"a/{name}" if old else "/dev/null",
                tofile=f"b/{name}",
            )
        )
    return "".join(output)


def main() -> int:
    patch_path = ROOT / "run_workspace/gcsim/patch_stack" / PATCH_NAME
    installed = ROOT / "data/gcsim/engines/engines/gcsim-v2.45.0-allsets-20260917"
    archive = ROOT / "data/gcsim/sources/archives/v2.45.0.zip"
    if not patch_path.is_file() or not installed.is_dir() or not archive.is_file():
        raise SystemExit("required patch, installed source, or cached archive is missing")

    with managed_scratch() as scratch:
        acquisition = acquire_official_gcsim_source_from_archive(
            source_ref=OfficialGcsimSourceRef(
                "v2.45.0", "v2.45.0",
                "https://api.github.com/repos/genshinsim/gcsim/zipball/v2.45.0", "", "",
            ),
            archive_path=archive,
            cache_dir=scratch / "upstream",
        )
        pristine = acquisition.source_dir
        patched = scratch / "patched"
        shutil.copytree(pristine, patched)
        applied = GitApplyPatchBackend().apply(
            engine_dir=patched, patch_stack_dir=patch_path.parent
        )
        if not applied.applied:
            raise RuntimeError(applied.error)
        for relative in ENERGY_PATHS:
            source = installed / relative
            if not source.is_file():
                raise RuntimeError(f"reviewed energy source missing: {relative}")
            destination = patched / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

        old_paths = re.findall(
            r"^diff --git a/(.+?) b/", patch_path.read_text(encoding="utf-8"), re.M
        )
        candidate_stack = scratch / "patch_stack"
        candidate_stack.mkdir()
        candidate_patch = candidate_stack / PATCH_NAME
        candidate_patch.write_text(
            _export_patch(pristine, patched, [*old_paths, *ENERGY_PATHS]),
            encoding="utf-8", newline="\n",
        )

        prefix = pristine.relative_to(ROOT).as_posix()
        checked = subprocess.run(
            ["git", "apply", "--check", "--directory", prefix, str(candidate_patch)],
            cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if checked.returncode != 0:
            raise RuntimeError("candidate patch clean check failed: " + checked.stderr[-4000:])

        report = prepare_official_gcsim_engine_update(
            release="v2.45.0",
            patch_stack_dir=candidate_stack,
            patch_backend=GitApplyPatchBackend(),
            engine_id="gcsim-v2.45.0-energy-20260917",
            source_acquirer=lambda **_: acquisition,
            build_artifact=True,
            probe_runtime=False,
            activate=True,
            prune_engine_store=True,
        )
        if not report.success or not report.activated:
            raise RuntimeError(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))

        # This is a generated consolidated patch, not a hand-authored source
        # edit; byte identity with the activated manifest is required.
        shutil.copyfile(candidate_patch, patch_path)
        print(json.dumps({
            "active_engine_id": report.active_engine_id,
            "artifact_sha256": report.artifact_sha256,
            "patch_files": list(report.patch_files),
            "gtt_capabilities": list(report.gtt_capabilities),
            "application_compatibility_status": report.application_compatibility_status,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
