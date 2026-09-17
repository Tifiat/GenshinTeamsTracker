# Bloom winner residual: diagnosed, not fixed

Dated diagnostic evidence, 2026-09-16. Current acceptance/resume is owned by
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
Do not interpret this note as completed implementation or formula acceptance.
The production engine, active patch, optimizer, live account and UI were not
changed by the diagnostic run. Shared handoffs were reconciled separately.

## Result

The previously selected bloom winner measures 124224.894 DPS (n1000,
SE 62.689), versus FAST 131479.030: a 5.8395% overestimate.
Two fresh captures of that exact winner, using the saved seeds, each produce
543 hits over 93.65 seconds and 124174.703 expected DPS. Reusing the original
graph with the actual winner artifact deltas produces 131479.030 DPS.
The 7304.326 same-schedule gap is therefore not explained by crit noise or a
different hit sequence. Channel alignment/topology match both seeds; detailed
frame/source/snapshot/ability/element/reaction flags match the first seed.

44 Nahida skill hits account for 7082.560 DPS, or 96.964% of this gap.
Her artifact EM falls from 507 to 37. The graph updates artifact crits/bonus but
retains several benefits of her old EM. This systematically makes that trade
look better than it is. The final simulator reports genuine measured damage;
it cannot recover better candidates already rejected by a biased formula.

## Concrete losses, not new gameplay formulas

1. **Original skill EM term.** Engine `internal/characters/nahida/skill.go`
   reads EM from `snap.Stats` and assigns the talent-scaled term to `ai.FlatDmg`.
   Hit 123 has no terminal source binding. `compileFlatDamage` in
   `pkg/gttcompact/direct.go` falls back to the observed constant. In the
   inspected hit the remaining flat error is exactly 470 * 3.7152 = 1746.144.
   The Spread contribution does respond; do not describe the entire reaction
   or entire hit as frozen.
2. **A4 guarded saved stat vector.** `internal/characters/nahida/asc.go`
   returns a saved vector after attack eligibility guards; another routine
   updates its EM-based capped entries. Current source extraction stops at
   `modifier_nested_control_flow` and the modifier receipt marks dependency
   incompleteness. In hit 123 old CR/DMG contributions 0.24/0.8 remain in the
   candidate graph instead of fresh 0.1012752/0.337584.
3. **Weapon local stat vectors.** `wanderingevenstar.go::updateStats` builds
   local self/team vectors from NonExtraStat(EM), then closures return them.
   These source templates stop at `modifier_output_assignment_count`.
   Hit 123 retains 197.4 extra ATK; the weapon's team transfer also changes by
   59.22 ATK and explains further ordinary-attack discrepancies. Existing
   receiver-field saved-vector support is not proof of local-vector support.
4. **Lunar team bonus stats-container branch.** `setupAscendantGleam` uses
   `SelectStat(true, BaseATK, ATKP, ATK).TotalATK()` on the active Electro
   character. GP3 handles the other branch's captured scalar NonExtraStat(EM),
   not this stats container. Kuki's changed ATK% explains the exact observed
   bonus difference 0.01353188173869. Columbina lunar-bloom hits account for
   another 85.017 DPS of residual. This is a missing upstream bonus response,
   not evidence that the lunar reaction's whole base formula is wrong.

All names/numbers above identify observed witnesses. Future implementation must
recognize typed source shapes and ownership, not match these character/weapon
names or copy their coefficients. Preserve original producer versus later flat
additions, snapshot timing, modifier inclusion and NonExtraStat/Extra semantics.

## Validation lesson

The earlier +187 Nahida EM check already failed; the later search was explicitly
diagnostic, not accepted. Its positive perturbation was also near/above the A4
cap and did not expose the much larger loss when EM decreases below that cap.
Zero wholly frozen hits does not mean zero important frozen dependencies.
Add negative/positive perturbations, cap crossings and combined real artifact
changes to acceptance. Do not hide this mismatch by relaxing tolerance or
increasing per-candidate simulator calls.

Kuki's 68 hyperbloom hits and Lauma's lunar-bloom group match fresh capture in
this winner replay. This fixture does not certify all lunar reactions or teams.

## Proposed repair order (not implemented)

1. Trace typed stats containers at Snapshot/SelectStat reads through to original
   numeric producers. Keep observed timing/owner and Extra exclusion explicit.
   Validate a synthetic source-shape case and the Nahida flat/gleam witnesses.
2. Extend the generic modifier dependency path to guarded saved-vector returns
   and closure-captured local vectors, including their real update producers.
   Validate cap crossings, self/team ownership and no changes to call order.
3. Replay the same winner offline against fresh captures, then run bidirectional
   and combined-stat controls. Only after the response gate passes repeat a
   bounded Selected search and its actual UI path. Do not expand search now.

If tracing a dependency needs a broader design decision, stop with the specific
source shape and evidence. Unknowns must remain visible local boundaries, not
silently treated as proven independent from artifacts.

## Evidence and cost

Durable numerical receipt:
`tests/fixtures/gcsim_optimizer_go_v1/gob11_bloom_winner_residual_diagnosis_v1.json`.
This complements `gob11_bloom4p_diagnostic_receipt_v1.json` and
`gob11_bloom4p_known_boundary_samples_v1.json`; all remain diagnostic evidence.

Raw evidence originally at `.codex_tmp/gob11-bloom-winner-audit-20260916`
is now losslessly stored under that prefix in the N0 evidence archive. The
current checkpoint links its SHA256/CRC receipt and selective restoration rule;
the expanded directory was removed on2026-09-17, not the diagnostic evidence.
Temporary helpers: `.codex_tmp/gob11_bloom_winner_audit.py`,
`.codex_tmp/gob11_bloom_winner_audit_test.go`, and corresponding Go overlay JSON.
The overlay uses production domain.Build, DenseDeltas, AssignmentStats and
EvaluateSeedMember; it does not reimplement game formulas or alter native code.

Only four n1 engine calls were added: two compact winner captures and one
detailed baseline/winner pair. No new search, n500/n1000 run, engine rebuild,
production change or live UI click. Raw detailed captures stay ignored; receipt
contains their hashes and the minimal reproducible facts. This is diagnosis,
not a completed user-facing fix.
