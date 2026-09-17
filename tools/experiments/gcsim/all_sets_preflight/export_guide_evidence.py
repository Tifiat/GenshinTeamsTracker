"""Retain sanitized guide/resistance evidence and a reproducible isolated delta."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

p = argparse.ArgumentParser(__doc__)
for key in ("engine-root", "reaction", "resistance", "catalog", "guide", "queue", "automatic", "winner"):
    p.add_argument("--"+key, type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
def load(path):
    return json.loads(path.read_text())
rows = load(a.resistance / "resistance-response-receipt.json")
if len(rows) != 2 or any(r["relative_residual"] > 1e-9 for r in rows):
    raise ValueError("resistance response gate did not pass")
changes = []
digests = []
for name, before_path in {
    "model.go": a.reaction / "model.go", "compile.go": a.reaction / "compile.go",
    **{n: a.engine_root / "pkg/gttcompact" / n for n in ("builder.go", "direct.go", "numeric_recipe.go", "contributor_group.go")},
    "damage.go": a.engine_root / "build/gtt-source-overlay/pkg/enemy/damage.go",
}.items():
    before = before_path.read_text()
    after = (a.resistance / name).read_text()
    changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="a/"+name, tofile="b/"+name))
    digests.append(dict(name=name, before_sha256=hashlib.sha256(before.encode()).hexdigest(), after_sha256=hashlib.sha256(after.encode()).hexdigest()))
delta = here / "resistance_inputs_experiment.patch"
delta.write_text("".join(changes), encoding="utf-8", newline="\n")
queue = load(a.queue / "proposal-queue.json")
# No private artifact IDs in permanent receipt; full queue remains local.
sanitized = []
for row in queue["queue"]["queue"]:
    sanitized.append({k: v for k, v in row.items() if k != "seed"})
result = dict(schema_version=1, date="2026-09-16", owner="docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md",
              status="isolated_source_resistance_and_bounded_queue_not_search_or_product_acceptance",
              resistance_controls=rows, resistance_capture_timings=load(a.resistance / "capture-receipt.json"),
              source_curves=load(a.catalog / "context-curves.json"),
              joined_guide=load(a.guide / "joined-guide-receipt.json"),
              proposal_queue=dict(elapsed_seconds=queue["elapsed_seconds"], limit=queue["limit"],
                                  feasible_by_wearer=queue["queue"]["feasible_by_wearer"],
                                  raw_formula_evaluations=queue["queue"]["raw_formula_evaluations"],
                                  slope_evaluations=queue["queue"]["slope_evaluations"],
                                  unqueued=queue["queue"]["unqueued"], proposals=sanitized),
              source_changes=digests, experimental_delta_sha256=hashlib.sha256(delta.read_bytes()).hexdigest(),
              new_engine_calls=4, cumulative_effect_stage_engine_calls=8,
              installed_source_binary_ui_energy_changed=False,
              limitations=["guide uses one fixed seed; raw package seed guide uses saved two-seed panel",
                           "source alternatives and raw counterfactuals are not whole-set DPS or activation proof",
                           "literal shared keys group proposal hints only, not certified removal or stacking semantics",
                           "16 is an isolated queue experiment, not the released product budget",
                           "no product capture budget, provider-transfer acceptance, ordinary finalist panel or All Sets UI"])
automatic = load(a.automatic / "automatic-capture-receipt.json")
winner = load(a.winner / "winner-response-receipt.json")
if automatic["new_engine_calls"] != 8 or winner["new_engine_calls"] != 2 or winner["relative_residual"] > 1e-9:
    raise ValueError("automatic queue / winner response gate incomplete")
automatic["rows"] = [{k: v for k, v in row.items() if k != "winner"} for row in automatic["rows"]]
result.update(automatic_four_proposal_capture=automatic, automatic_winner_response=winner,
              new_engine_calls=14, cumulative_effect_stage_engine_calls=18,
              status="isolated_effect_inputs_automatic_queue_and_winner_response_pass_not_product_acceptance")
target = root / "tests/fixtures/gcsim_optimizer_go_v1/all_sets_effect_guide_receipt_v1.json"
target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(target)
