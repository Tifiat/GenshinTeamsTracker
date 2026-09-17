"""Source-only effect discovery audit over one engine-bound artifact catalog.

No simulations, DB or installed engine changes. Output is discovery evidence,
not a replacement certificate, uptime claim or product ranking acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    sys.path.insert(0, str(root))
    from run_workspace.gcsim.artifact_set_catalog import load_gcsim_artifact_set_catalog
    output = args.output.resolve()
    output.relative_to(root / ".codex_tmp")
    output.mkdir(exist_ok=False)
    request = json.loads((args.source_run / "request.json").read_text(encoding="utf-8"))
    binary = Path(request["engine"]["binary_path"]).resolve()
    if binary.parent.parent != args.engine_root.resolve():
        raise ValueError("source root must be the bound engine root")
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != request["engine"]["artifact_sha256"]:
        raise ValueError("engine binary changed")
    catalog = load_gcsim_artifact_set_catalog(args.engine_root)
    items = []
    for capability in catalog.sets:
        if capability.max_rarity != 5 or not capability.two_piece_modeled:
            continue
        sources = {}
        for name in capability.source_files:
            if not name.endswith(".go"):
                continue
            source = (args.engine_root / name).resolve()
            source.relative_to(args.engine_root.resolve())
            sources[name] = source.read_bytes().decode("utf-8")
        items.append(dict(key=capability.key, sources=sources, four_piece_modeled=capability.four_piece_modeled))
    manifest = output / "manifest.json"
    stat_source = (args.engine_root / "pkg/core/attributes/stats.go").read_text(encoding="utf-8")
    attack_source = (args.engine_root / "pkg/core/attacks/attack.go").read_text(encoding="utf-8")
    context_source = (args.engine_root / "pkg/enemy/damage.go").read_text(encoding="utf-8")
    element_source = (args.engine_root / "pkg/core/attributes/element.go").read_text(encoding="utf-8")
    manifest.write_text(json.dumps(dict(engine_sha256=actual, catalog_sha256=catalog.source_fingerprint,
                                       stat_source=stat_source, attack_source=attack_source, context_source=context_source, element_source=element_source,
                                       source_run=str(args.source_run.resolve()), items=items)), encoding="utf-8")
    overlay = output / "overlay.json"
    overlay.write_text(json.dumps({"Replace": {
        str(root / "native/gcsim_optimizer/internal/seteffects/gtt_catalog_audit_test.go"):
        str(here / "effect_catalog_test.go"),
    }}), encoding="utf-8")
    env = dict(os.environ, GTT_EFFECT_MANIFEST=str(manifest), GTT_EFFECT_OUTPUT=str(output))
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                    "./internal/seteffects", "-run", "TestAllSetEffectCatalog", "-count=1", "-v"],
                   cwd=root / "native/gcsim_optimizer", env=env, check=True, timeout=60)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != actual:
        raise ValueError("engine binary changed during audit")


if __name__ == "__main__":
    main()
