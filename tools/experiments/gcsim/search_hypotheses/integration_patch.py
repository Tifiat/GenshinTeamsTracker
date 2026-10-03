"""Prepare (never apply/install) the accepted source-copy variant as a patch.

Run under managed_optimizer_experiment.py after matrix review. Expanded sources
belong to the managed job; stdout is an apply_patch proposal for parent review.
The parent applies it only after the gate, then verifies the production build.
Retire this helper with the speed-research overlays after integration acceptance.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
from tools.experiments.gcsim.search_hypotheses.run import (
    apply_timing_overlay, copy_variant_support, replace_once, sha,
)
from tools.experiments.gcsim.search_hypotheses.variants import apply_variant

HELPERS = {
    "internal/formula/hypothesis_region_binding.go": "internal/formula/region_binding.go",
    "internal/formula/hypothesis_region_binding_test.go": "internal/formula/region_binding_test.go",
    "internal/formula/hypothesis_mixed_formula.go": "internal/formula/mixed_effects.go",
    "internal/formula/hypothesis_mixed_formula_test.go": "internal/formula/mixed_effects_test.go",
    "internal/setcontext/hypothesis_mixed_cache.go": "internal/setcontext/neutral_mixed_cache.go",
    "internal/seteffects/hypothesis_effect_families.go": "internal/seteffects/effect_families.go",
    "internal/seteffects/hypothesis_effect_families_test.go": "internal/seteffects/effect_families_test.go",
    "internal/seteffects/hypothesis_amount_plan.go": "internal/seteffects/rule_amount_plan.go",
    "internal/seteffects/hypothesis_amount_plan_test.go": "internal/seteffects/rule_amount_plan_test.go",
    "internal/domain/hypothesis_vector_views_test.go": "internal/domain/vector_cache_test.go",
    "internal/seteffects/hypothesis_replay_plan_test.go": "internal/seteffects/rule_replay_plan_test.go",
    "internal/search/hypothesis_player_logic_test.go": "internal/search/candidate_priority_test.go",
}

# Consistent mechanical names only; algorithm/ordering stays the measured one.
NAMES = {
    "HypothesisRegionStats": "RegionBindingStats",
    "HypothesisRegionsStats": "RegionBindingStats",
    "hypothesisRegionStats": "regionStats",
    "hypothesisRegions": "regions",
    "hypothesisRegionBinder": "regionBinder",
    "hypothesisExportRegions": "exportRegions",
    "hypothesisFamilySerial": "familySerial",
    "hypothesisTwoPieceFamilies": "twoPieceFamilies",
    "hypothesisPayloads": "composedPayloads",
    "hypothesisPayloadOrder": "composedPayloadOrder",
    "hypothesisPayloadValues": "composedPayloadValues",
    "hypothesisPayloadNodes": "composedPayloadNodes",
    "hypothesisIdentity": "effectIdentity",
    "hypothesisIdentify": "identifyComponent",
    "hypothesisRetainPayload": "retainComposedPayload",
    "hypothesisAmountPlanLimit": "amountPlanLimit",
    "hypothesisBuildAmountPlan": "buildAmountPlan",
    "hypothesisAmountPlan": "amountPlan",
    "hypothesisAmountPlans": "amountPlans",
    "hypothesisAmountOrder": "amountPlanOrder",
    "amountScratchLegacy": "inspectAmountScratch",
    "hypothesisDispatch": "contextDispatch",
    "hypothesisView": "contextView",
}


def production_names(text):
    pattern = r"\b(?:" + "|".join(re.escape(x) for x in NAMES) + r")\b"
    text = re.sub(pattern, lambda match: NAMES[match.group()], text)
    return re.sub(r"\b(Test|Benchmark)Hypothesis(?=[A-Z])", r"\1", text)


def production_source(relative, text, variant):
    if variant != "player_safe_wide":
        raise ValueError("Only the reviewed original-width exact-reuse candidate may be proposed")
    if relative == "internal/search/candidates.go":
        # Exact-only promotion must not retain the rejected, uncalled narrowing
        # entry point inherited by the research overlay chain.
        wrapper = """func (engine *Engine) RefineCandidatesHypothesisNarrow(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
\tprevious := engine.config.RecheckFrontierWidth
\tengine.config.RecheckFrontierWidth = 2
\tdefer func() { engine.config.RecheckFrontierWidth = previous }()
\treturn engine.RefineCandidates(ctx, anchor, actor, allowance)
}

"""
        if text.count(wrapper) != 1:
            raise ValueError("Narrowing wrapper changed; review exact-only promotion")
        text = text.replace(wrapper, "", 1)
        if "RefineCandidatesHypothesisNarrow" in text:
            raise ValueError("Unexpected remaining narrowing reference")
    return production_names(text)


def product_relative(relative):
    """None keeps test/replay/heuristic-only helpers out of the proposal."""
    return HELPERS.get(relative) if "/hypothesis_" in relative else relative


def patch_file(relative, before, after):
    target = "native/gcsim_optimizer/" + relative
    if before is None:
        return "*** Add File: " + target + "\n" + "".join("+" + line + "\n" for line in after.splitlines())
    if before == after:
        return ""
    diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), n=3, lineterm=""))[2:]
    return "*** Update File: " + target + "\n" + "\n".join("@@" if line.startswith("@@") else line for line in diff) + "\n"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--variant", choices=("player_safe_wide",), required=True)
    args = parser.parse_args()
    job = owned_job()
    source = ROOT / "native/gcsim_optimizer"
    files = sorted(p for p in source.rglob("*") if p.is_file() and (p.suffix == ".go" or p.name in {"go.mod", "go.sum"}))
    digest = hashlib.sha256(b"".join(str(p.relative_to(source)).encode() + b"\0" + p.read_bytes() for p in files)).hexdigest()
    baseline = json.loads((ROOT / "docs/optimizer-evidence/2026-09-27-search-hypotheses/combined.json").read_text(encoding="utf-8"))
    if digest != baseline["source_sha256"] or sha(source / "gtt-optimizer.exe") != baseline["installed_sha256"]:
        raise ValueError("Source/installed baseline changed: review before generating a promotion patch")
    native = job / "proposal/native"
    for original in files:
        target = native / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    apply_timing_overlay(native)
    apply_variant(native, args.variant, replace_once)
    copy_variant_support(native, args.variant, job)
    changes, chunks = [], []
    for copied in sorted(native.rglob("*.go")):
        relative = copied.relative_to(native).as_posix()
        relative = product_relative(relative)
        if relative is None:
            continue  # Replay/approximation/filter-only helpers are not product code.
        if "/hypothesis_" in copied.relative_to(native).as_posix():
            if (source / relative).exists():
                raise ValueError("Refusing to replace a preexisting helper: " + relative)
        before = (source / relative).read_text(encoding="utf-8") if (source / relative).exists() else None
        after = production_source(relative, copied.read_text(encoding="utf-8"), args.variant)
        chunk = patch_file(relative, before, after)
        if chunk:
            changes.append(relative)
            chunks.append(chunk)
    print(json.dumps({"variant": args.variant, "source_sha256": digest, "files": changes,
                      "patch": "*** Begin Patch\n" + "".join(chunks) + "*** End Patch\n"}))


if __name__ == "__main__":
    main()
