"""Stage10 overlay: observe pass boundaries and optionally omit deep bundles."""
from pathlib import Path
import hashlib
import shutil

from tools.experiments.gcsim.theory_hybrid import adapter as common_adapter
from tools.experiments.gcsim.theory_hybrid import run as common

HERE = Path(__file__).resolve().parent
COMMON_SHA = "f8740ff8ab9d0ea8c928138e9cfb995c027cbe56495209fea9f6a87c09820eb0"


def prepare(native, bounds, case):
    if common.identity()["sha256"] != COMMON_SHA:
        raise RuntimeError("Frozen common-H dependency changed")
    evidence = common_adapter.prepare(native, bounds, case)
    path = native / "cmd/gtt-optimizer/hybrid_test.go"
    source = path.read_text(encoding="utf-8")
    edits = [
        ("type hybridRun struct {\n", "type hybridRun struct {\n researchLight *lightObservation\n"),
        ('h.finalRefinement(fmt.Sprintf("pass%d", pass))',
         'lightPassRefinement(h, fmt.Sprintf("pass%d", pass))'),
        ("\t\th.refinedPasses = pass + 1",
         "\t\tif lightDeepEnabled(h) { h.refinedPasses = pass + 1 }"),
    ]
    adapted = source
    for before, after in edits:
        adapted = common_adapter.once(adapted, before, after)
    restored = adapted
    for before, after in reversed(edits):
        restored = common_adapter.once(restored, after, before)
    if restored != source:
        raise RuntimeError("Stage10 inverse transformation differs")
    path.write_text(adapted, encoding="utf-8", newline="\n")
    harness = native / "cmd/gtt-optimizer/theory_feasible_experiment_test.go"
    code = harness.read_text(encoding="utf-8")
    marker = '\tif os.Getenv("GTT_FEASIBLE_PHASE") == "common_h" {'
    code = common_adapter.once(code, marker,
        '\tif os.Getenv("GTT_FEASIBLE_PHASE") == "light_study" {\n'
        '\t\trunLightStudy(t, factory, req, base, original, options, initial)\n\t\treturn\n\t}\n' + marker)
    harness.write_text(code, encoding="utf-8", newline="\n")
    for name in ("policy_test.go", "contract_test.go"):
        shutil.copyfile(HERE / name, native / "cmd/gtt-optimizer" / ("light_" + name))
    return {"common": evidence, "common_identity_sha256": COMMON_SHA,
            "inverse_transformation_exact": True, "edits": [p[0] for p in edits],
            "adapted_hybrid_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
            "baseline": "unchanged numerical search plus pure pre-deep observations",
            "light": "only mandatory per-pass deep bundles omitted; shallow starts and sweep winners unchanged"}
