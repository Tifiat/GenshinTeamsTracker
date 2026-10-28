"""Stage11 managed-copy clock and observation overlay; Stage10 stays frozen."""
from pathlib import Path
import hashlib
import shutil

from tools.experiments.gcsim.theory_light import adapter as light_adapter
from tools.experiments.gcsim.theory_light import run as light
from tools.experiments.gcsim.theory_hybrid.adapter import once

HERE = Path(__file__).resolve().parent
LIGHT_SHA = "fd9a6a3367694a978cd77b8ed61111d1ab51d296467ad95ff8e4bed2c675eb2d"
STAGE10_COMMIT = "47e13fa8c2bc79284b177978605a38570c841ac7"


def transform(source, edits):
    adapted = source
    for before, after in edits:
        adapted = once(adapted, before, after)
    restored = adapted
    for before, after in reversed(edits):
        restored = once(restored, after, before)
    if restored != source:
        raise RuntimeError("Stage11 inverse transformation differs")
    return adapted, {
        "original_text_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "adapted_text_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
        "inverse_transformation_exact": True,
        "edits": [before for before, _ in edits],
    }


def prepare(native, bounds, case):
    if light.identity()["sha256"] != LIGHT_SHA:
        raise RuntimeError("Frozen Stage10 dependency changed")
    evidence = light_adapter.prepare(native, bounds, case)
    edits = {
        "light_policy_test.go": [
            ("const lightOverallSeconds = 360", "const lightOverallSeconds = 240"),
            ("overall_offline_360s_guard", "overall_offline_240s_guard"),
            ("research overall offline 360s guard", "research overall offline 240s guard"),
            ("\tbaseline := runLightPolicy(t, factory, req, base, original, options, initial, false, global)",
             "\tcontrastBeforeBaseline(t)\n\tbaseline := runLightPolicy(t, factory, req, base, original, options, initial, false, global)"),
        ],
        "light_contract_test.go": [
            ("if 135+180+lightAuditSeconds+lightChecksSeconds >= lightOverallSeconds {\n\t\tt.Fatal(\"no overall slack\")",
             "if lightOverallSeconds != 240 || lightAuditSeconds != 29 || lightChecksSeconds != 12 {\n\t\tt.Fatal(\"shared offline censoring clock or evidence reservations changed\")"),
        ],
    }
    transformed = {}
    for name, changes in edits.items():
        path = native / "cmd/gtt-optimizer" / name
        adapted, proof = transform(path.read_text(encoding="utf-8"), changes)
        path.write_text(adapted, encoding="utf-8", newline="\n")
        transformed[name] = proof
    shutil.copyfile(HERE / "contract_test.go", native / "cmd/gtt-optimizer/contrast_contract_test.go")
    return {
        "stage10": evidence,
        "stage10_commit": STAGE10_COMMIT,
        "light_identity_sha256": LIGHT_SHA,
        "inverse_transformation_exact": True,
        "transformed_files": transformed,
        "numerical_search_unchanged": True,
        "scope": "shared offline watchdog and pre-baseline receipt ACK only; no search, seed, cache or work-quota edits",
    }
