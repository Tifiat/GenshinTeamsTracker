"""A minimal common-H adapter, applied only inside an owned managed copy."""
from pathlib import Path
import hashlib
import shutil

HERE = Path(__file__).resolve().parent
LEGACY_H_SHA = "6ee3177e74bf5e70fdf265c7f88ef9cec08b82392f5f245e3c8f0bfcdd7b8080"
LEGACY_DEPENDENCY_SHA = "9b0a7b7b7845e2ff05c45ef3a28353c6ad06e186cda33de5762903ee3bfd43cf"


def once(code, before, after):
    if code.count(before) != 1:
        raise RuntimeError("Common H anchor changed: " + before[:100])
    return code.replace(before, after, 1)


def prepare(native, bounds, case):
    original = bounds.HERE / "hybrid_test.go"
    if hashlib.sha256(original.read_bytes()).hexdigest() != LEGACY_H_SHA:
        raise RuntimeError("The measured v2 hybrid source changed")
    if bounds.identity()["sha256"] != LEGACY_DEPENDENCY_SHA:
        raise RuntimeError("The measured v2 hybrid dependencies changed")
    bounds.prepare_copy(native)
    bounds.prepare_harness(native, case)
    path = native / "cmd/gtt-optimizer/hybrid_test.go"
    source = path.read_text(encoding="utf-8")
    edits = [
        ("type hybridRun struct {\n", "type hybridRun struct {\n researchH *commonHConfig\n"),
        ("func (h *hybridRun) alive() bool { return time.Now().Before(h.deadline) }",
         "func (h *hybridRun) alive() bool { return time.Now().Before(h.deadline) && commonHWithinWork(h) }"),
        ("for pass := 0; pass < 2; pass++ {", "for pass := 0; pass < commonHPasses(h); pass++ {"),
    ]
    adapted = source
    for before, after in edits:
        adapted = once(adapted, before, after)
    restored = adapted
    for before, after in reversed(edits):
        restored = once(restored, after, before)
    if restored != source:
        raise RuntimeError("Common H inverse transformation differs")
    path.write_text(adapted, encoding="utf-8", newline="\n")
    harness = native / "cmd/gtt-optimizer/theory_feasible_experiment_test.go"
    code = harness.read_text(encoding="utf-8")
    code = once(code, "func TestTheoryFeasibleExperiment(t *testing.T) {\n",
                "func TestTheoryFeasibleExperiment(t *testing.T) {\n researchTestStarted := time.Now()\n")
    code = once(code, "\tstart := time.Now()\n\th, err := session.Resolve(context.Background(), base, nil, nil)",
                "\tresearchNativeInputSeconds := time.Since(researchTestStarted).Seconds()\n\tstart := time.Now()\n\th, err := session.Resolve(context.Background(), base, nil, nil)")
    code = once(code, "\tmodelSeconds := time.Since(start).Seconds()\n",
                "\tmodelSeconds := time.Since(start).Seconds()\n researchCatalogStarted := time.Now()\n")
    code = once(code, 'emitFeasible(map[string]any{"kind": "preparation",',
                'emitFeasible(map[string]any{"kind": "preparation", "native_input_seconds": researchNativeInputSeconds, "catalog_setup_seconds": time.Since(researchCatalogStarted).Seconds(),')
    marker = '\tif strings.HasPrefix(os.Getenv("GTT_FEASIBLE_PHASE"), "r2_") {'
    code = once(code, marker,
                '\tif os.Getenv("GTT_FEASIBLE_PHASE") == "common_h" {\n'
                '\t\trunCommonHStudy(t, factory, req, base, original, options, initial)\n\t\treturn\n\t}\n' + marker)
    harness.write_text(code, encoding="utf-8", newline="\n")
    for name in ("policy_test.go", "contract_test.go"):
        shutil.copyfile(HERE / name, native / "cmd/gtt-optimizer" / ("common_h_" + name))
    return {"legacy_source_sha256": LEGACY_H_SHA, "legacy_dependency_sha256": LEGACY_DEPENDENCY_SHA,
            "inverse_transformation_exact": True, "edits": [p[0] for p in edits],
            "full_pass_count": 2, "first_pass_count": 1,
            "numerical_core": "unchanged v2; only explicit pass limit and nonbinding work watchdogs"}
