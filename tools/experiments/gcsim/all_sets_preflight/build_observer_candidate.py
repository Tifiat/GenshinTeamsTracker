"""Export reviewed source deltas and build through the normal manifest generator.

No activation, updater store mutation, simulation or live patch overwrite.
"""
import argparse
from dataclasses import asdict
import difflib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from run_workspace.gcsim.artifact_build import build_gcsim_artifact  # noqa: E402
from run_workspace.gcsim.engine_update import _source_manifest_binding_input  # noqa: E402
from run_workspace.gcsim.patch_backends import GitApplyPatchBackend  # noqa: E402
from run_workspace.gcsim.source_acquisition import OfficialGcsimSourceAcquisition, OfficialGcsimSourceRef  # noqa: E402

CHANGED = (
    "pkg/core/player/character/mods.go", "pkg/enemy/damage.go", "pkg/gtt/info.go",
    *("pkg/gttcompact/"+n for n in ("builder.go", "compile.go", "contributor_group.go", "direct.go", "effect_input.go", "model.go", "numeric_recipe.go", "resistance_input.go", "effect_input_test.go")),
    "pkg/gtttrace/effect_read.go", "pkg/gtttrace/effect_read_test.go",
    "pkg/gttsourcegen/numeric_recipe_test.go", "pkg/optimization/gtt_trace_equation.go",
    "pkg/optimization/gtt_effect_inputs.go", "pkg/optimization/gtt_effect_inputs_test.go",
)


def export(base, source, paths):
    output = []
    for name in sorted(set(paths)):
        before, after = base / name, source / name
        old = before.read_text(encoding="utf-8").splitlines(True) if before.exists() else []
        new = after.read_text(encoding="utf-8").splitlines(True) if after.exists() else []
        if old == new:
            continue
        output.append(f"diff --git a/{name} b/{name}\n")
        if not old:
            output.append("new file mode 100644\n")
        output.extend(difflib.unified_diff(old, new, fromfile=f"a/{name}" if old else "/dev/null", tofile=f"b/{name}"))
    return "".join(output)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--installed", type=Path, required=True)
    args = parser.parse_args()
    candidate, installed = args.candidate.resolve(), args.installed.resolve()
    candidate.relative_to(ROOT / ".codex_tmp")
    source = candidate / "source"
    patch_dir = candidate / "patch_stack"
    patch_dir.mkdir(exist_ok=True)
    current = ROOT / "run_workspace/gcsim/patch_stack/0001-gtt-engine-adapter-v245.patch"
    paths = re.findall(r"^diff --git a/(.+?) b/", current.read_text(encoding="utf-8"), re.M)
    pristine = candidate / "upstream/expanded/v2.45.0"
    (patch_dir / current.name).write_text(export(pristine, source, [*paths, *CHANGED]), encoding="utf-8", newline="\n")
    Path(__file__).with_name("observer_source.patch").write_text(export(installed, source, CHANGED), encoding="utf-8", newline="\n")
    acquisition = OfficialGcsimSourceAcquisition(
        OfficialGcsimSourceRef("v2.45.0", "v2.45.0", "cached-official-archive", "", ""),
        ROOT / "data/gcsim/sources/archives/v2.45.0.zip", pristine, candidate / "upstream")
    binding = _source_manifest_binding_input(acquisition=acquisition, patch_stack=patch_dir, patch_backend=GitApplyPatchBackend())
    result = build_gcsim_artifact(source, go_executable="C:/Program Files/Go/bin/go.exe",
                                 timeout_seconds=300, require_gtt_marker=True, source_manifest_binding_input=binding)
    summary = asdict(result)
    (candidate / "build-summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status":result.status, "ready":result.artifact_ready, "error":result.error,
                      "stderr":result.build_stderr[-4000:]}, ensure_ascii=False))
    if not result.artifact_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
