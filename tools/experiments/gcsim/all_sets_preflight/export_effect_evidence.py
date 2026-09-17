"""Sanitized source-discovery/neutral-input receipt; no simulations or DB reads.

Also retain the reviewed three-file observer delta for reproducible isolation.
It is NOT a production patch stack and must be removed after consolidation.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--engine-root", type=Path, required=True)
    a = p.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    discovery = json.loads((a.catalog / "effect-discovery-receipt.json").read_text())
    response = json.loads((a.inputs / "response-receipt.json").read_text())
    captures = json.loads((a.inputs / "capture-receipt.json").read_text())
    if len(captures) != 4 or len(response) != 2 or any(row["relative_residual"] > 1e-9 for row in response):
        raise ValueError("controlled response did not pass")
    patches = []
    sources = []
    for name, relative in {
        "mods.go": "pkg/core/player/character/mods.go",
        "model.go": "pkg/gttcompact/model.go",
        "compile.go": "pkg/gttcompact/compile.go",
    }.items():
        before = (a.engine_root / relative).read_text(encoding="utf-8")
        after = (a.inputs / name).read_text(encoding="utf-8")
        patches.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                          fromfile="a/" + name, tofile="b/" + name))
        sources.append(dict(path=relative, parent_sha256=hashlib.sha256(before.encode()).hexdigest(),
                            overlay_sha256=hashlib.sha256(after.encode()).hexdigest()))
    delta = here / "effect_inputs_experiment.patch"
    delta.write_text("".join(patches), encoding="utf-8", newline="\n")
    out = dict(schema_version=1, date="2026-09-16",
               owner="docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md",
               status="source_discovery_and_isolated_reaction_input_response_pass_not_all_sets_product",
               discovery=discovery, neutral_input_controls=response, capture_timings=captures,
               new_engine_calls=4, installed_binary_ui_energy_changed=False,
               parent_engine_sha256=discovery["engine_sha256"],
               observer_source_changes=sources,
               experimental_delta_sha256=hashlib.sha256(delta.read_bytes()).hexdigest(),
               limits=[
                   "93 source effect sites are not a fraction of complete gameplay coverage.",
                   "Possible amount alternatives are not additive totals or activation/uptime proofs.",
                   "Raw-stat proxy and contextual increment keep old effects; neither is changed-set DPS.",
                   "Two fixed-seed artificial +0.1 reaction-bonus controls are not real-set replacement acceptance.",
                   "No resistance-input recipe, automatic proposal queue, real static proof producer or All Sets UI enabled.",
                   "Source observer remains isolated; no installed compatibility/update or UI claim.",
               ])
    out["capture_sha256"] = {name: hashlib.sha256((a.inputs / name).read_bytes()).hexdigest()
                             for name in ("bloom-baseline.json", "bloom-offset.json", "cloud-baseline.json", "cloud-offset.json")}
    target = root / "tests/fixtures/gcsim_optimizer_go_v1/all_sets_effect_discovery_receipt_v1.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
