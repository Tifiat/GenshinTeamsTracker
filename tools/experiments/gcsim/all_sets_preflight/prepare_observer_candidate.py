"""Prepare isolated clean source from cached upstream + reviewed patch, no install.

The initial bootstrap copies already tested observer deltas. Subsequent runs use
the retained source delta, including the ORIGINAL source marker (never generated
overlay edits). The updater's normal generator/build path remains authoritative.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from run_workspace.gcsim.source_acquisition import (  # noqa: E402
    OfficialGcsimSourceRef, acquire_official_gcsim_source_from_archive,
)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap-from", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / ".codex_tmp")
    output.mkdir(exist_ok=False)
    ref = OfficialGcsimSourceRef("v2.45.0", "v2.45.0", "https://api.github.com/repos/genshinsim/gcsim/zipball/v2.45.0", "", "")
    acquired = acquire_official_gcsim_source_from_archive(
        source_ref=ref, archive_path=ROOT / "data/gcsim/sources/archives/v2.45.0.zip",
        cache_dir=output / "upstream")
    source = output / "source"
    shutil.copytree(acquired.source_dir, source)
    patch = ROOT / "run_workspace/gcsim/patch_stack/0001-gtt-engine-adapter-v245.patch"
    prefix = source.relative_to(ROOT).as_posix()
    for flag in (["--check"], []):
        subprocess.run(["git", "apply", *flag, "--directory", prefix, str(patch)], cwd=ROOT, check=True)
    if args.bootstrap_from:
        reviewed = args.bootstrap_from.resolve()
        reviewed.relative_to(ROOT / ".codex_tmp")
        paths = {"mods.go": "pkg/core/player/character/mods.go"}
        paths.update({n: "pkg/gttcompact/"+n for n in (
            "model.go", "compile.go", "builder.go", "direct.go", "numeric_recipe.go", "contributor_group.go")})
        for name, destination in paths.items():
            shutil.copyfile(reviewed / name, source / destination)
        here = Path(__file__).resolve().parent
        for folder, names in {"gttcompact": ["effect_input.go", "resistance_input.go"],
                              "gtttrace": ["effect_read.go", "effect_read_test.go"]}.items():
            for name in names:
                shutil.copyfile(here / name, source / "pkg" / folder / name)
    else:
        delta = Path(__file__).with_name("observer_source.patch")
        for flag in (["--check"], []):
            subprocess.run(["git", "apply", *flag, "--directory", prefix, str(delta)], cwd=ROOT, check=True)
    print(source)


if __name__ == "__main__":
    main()
