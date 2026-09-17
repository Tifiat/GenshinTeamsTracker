# GOB-11 supplied rotation validation

Started 2026-09-08. User source: `C:/Users/user/Desktop/личные обсидиан/Личные/Конфиги тест.md`.
This is a bounded account-backed validation, not new gameplay implementation.
Do not edit the source note or the saved Chasca rotation. Ignore embedded images.

Historical GP-3 snapshot (2026-09-16, before the dependency audit and2+2
extension; current authority: GCSIM_GOB11_GP3_CHECKPOINT.md): installed after the bounded formula gate
passed. Both Flins captures have zero wholly frozen hits, including59/55 cloud
hits; this is not proof that every subexpression is variable. Saved-vector and
captured-scalar ancestry closes the measured shared-EM/reaction-bonus loss.
All12 controlled stat points now pass, including543 bloom hits at three points.
Two Chasca controls and installed-engine parity pass. No visible UI click.
Both Flins Selected searches passed: n500 winners189400/196748 DPS versus
initial149631/158169 (+26.58%/+24.39%), in119.7s/106.2s. Formula errors2.82% /
0.29%, near-tied ranks remain unresolved under budget; not a global optimum.
See gob11_gp3_production_receipt_v1.json for IDs/timing and GP3 checkpoint.
User decision2026-09-16: Selected2+2 follows completion of core Selected.
Test-only Lauma4p substitution is now authorized: Gilded Dreams, since Nahida
already has Deepwood and Kuki has Silken Moon. Preserve original2+2 evidence.
Read GCSIM_GOB11_GP3_CHECKPOINT.md and gob11_captured_scalar_receipt_v1.json.
Earlier measurements below are historical, not remaining formula blockers.

## Inputs and sequence

### Requested Jahoda variant (2026-09-17; separate syntax smoke)

User requested Flins/Ineffa/Columbina/Jahoda, skill pursuit without Jahoda burst.
Reusable shell: `tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_no_burst_rotation.txt`;
receipt: `tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_no_burst_receipt_v1.json`.
It adapts the first supplied rotation, replacing Sucrose setup with `jahoda skill;`.
In installed2.45 this action automatically remains in pursuit until filling or
expiry; a repeated skill cancels early. No invented `hold`/movement parameter.
One ordinary debug sample, infinite energy, six loops: six filled/zero unfilled
flasks,52 Meowball hits, zero Jahoda bursts,202 frames per Jahoda-to-Flins turn.
Test uses public-note stats for the original three, JahodaC0/test Favonius bowR1
and former Sucrose stats; not account equipment, optimal DPS, formula dependency
or optimizer acceptance. Her burst healing/A4 are deliberately absent. No live
DB/equipment/source-note/saved-rotation changes. Local disposable smoke files:
`.codex_tmp/jahoda-skill-20260917/`; permanent shell/receipt survive their cleanup.
The optimizer's current UI/cleanup next stage is unchanged in GP-3.

Follow-up screenshot exposed a separate real-account preparation bug: Jahoda
was stored as missing using2.42.2 import shortcut data although active2.45
supports her. The import resolver now follows active generated/legacy registry
paths; stale team key/status/method fields cannot override account SQLite.
First active-root repair still used old filenames and failed safely before a
DB write; second handles the observed generated filenames and passed36 unit tests.
Only Jahoda's derived mapping/provenance was refreshed; prior row backup and
one-shot diagnostic live under `.codex_tmp/jahoda-mapping-20260917/`.
`jahoda_mapping_repair_receipt_v1.json` in the same fixture folder records
not-ready -> ready for all four real-account characters, full config preparation
and one ordinary sample with six filled flasks/52 Meowball hits. No equipment,
saved rotation, engine or settings changes; no optimizer/DPS coverage claim.
The user's next All Sets attempt reached the target guard, not a mapping error:
`all_sets-20260917-020735-4a343e12` contains only the action body, with zero target
statements. The assistant's supplied text omitted the header while the earlier
smokes added it privately; those smokes did not prove paste-ready UI input.
The reusable shell now includes the original `swap_delay=12` options and the
same level100/10% resistance DPS target as the UI default/source rotation.
No automatic target injection or weakened one-target guard was added.
Six focused adapter tests pass, including the complete shell regression. Its
verbatim contents also pass `_prepare_inputs` for an All Sets request with the
four real-account characters/current equipment; no simulation/search or account
mutation. Local preparation evidence: `.codex_tmp/jahoda-target-20260917/receipt.json`.
User must prepend the supplied options/target header to the editor text (or use
the complete fixture) and retry. Native Windows tools remain absent; the actual
corrected button path, final DPS and unchanged result/equipment UI are unverified.

### Original supplied-fixture sequence

1. Prepare two Flins/Ineffa/Columbina/Sucrose rotations and one
   Columbina/Kuki/Nahida/Lauma rotation using account characters/weapons and real
   inventory. Strip website character/weapon/artifact-stat declarations from
   the rotation shell; use supplied set choices for fixture equipment only.
   Prefer current equipped weapons. Record any unsupported/missing weapon and
   explicit substitute separately; never claim a substituted context is equal.
   Stage equipment in a SQLite backup, not live equipment. Keep the production
   request/config/materialization path, without patched/mocked scoring.
2. Run bounded ordinary and compact capture checks before full search: loops,
   branches, ability timing, direct/indirect Lunar damage, reaction ownership,
   variable versus wholly frozen channels. Never sum opaque reason shares.
3. Check a small number of controlled stat changes against ordinary engine
   results. Reject invented elemental-bonus dependence on reaction damage;
   inspect real EM/crit/multi-owner dependence. Stop expensive finalist search
   for a mechanic whose principal damage is not modeled sufficiently.
4. Run unchanged Selected only on ready fixtures and report actual IDs, DPS,
   time and limits. A website DPS screenshot is not a minimum for a different
   weapon/constellation/stat/energy context. Distinguish ordinary simulation
   success from correct artifact selection and actual visible UI verification.
5. After findings are fixed and accepted, test further teams/rotations. Only
   after that design automatic GCSIM database config import, separately from
   this user-supplied fixture reader. Energy-aware Selected remains later.

## Initial readiness findings

- Current Selected's production legality is fixed-4p. Lauma's supplied 2+2
  Gilded Dreams/Wanderer's Troupe cannot silently become a 4p fixture. Test its
  engine/formula separately; adding 2+2 search is a distinct product extension.
- Account Sucrose is C1, website fixtures C6. Other equipped weapons also differ.
- Kuki exists under canonical `kukishinobu`; `kuki` is an upstream alias, not a
  missing character. Her equipped weapon 11436 has empty GCSIM mapping. The
  user explicitly approved account Dark Iron Sword level 90 R2 for this test
  copy only. Do not confuse it with the upstream claymore Flame-Forged Insight.

## Measured result (2026-09-08)

GOB-11 is NOT accepted for artifact search. All three supplied rotation bodies
execute in ordinary v2.45.0. Their loops/branches need no syntax workaround.
Account-backed config materialization passes. Full Selected was intentionally
not run after the dependency gap was measured. Website DPS is not a ranking
oracle, and these initial legal builds are not optimizer results.

| Fixture | Ordinary mean DPS, n=64 | Standard error | Compact mean DPS, two seeds | Wholly constant channel damage |
| --- | ---: | ---: | ---: | ---: |
| Flins rotation 1 | 149,163 | 347 | 149,470 | 89.95% |
| Flins rotation 2 | 158,978 | 373 | 159,202 | 89.13-89.42% |
| Columbina/Kuki/Lauma/Nahida | 110,841 | 238 | 110,800 | 69.73% |

Constant-channel percentages sum disjoint channel damage with no response
coordinates. They are NOT summed opaque reason shares, and NOT a complete
measure of uncertainty: a variable channel can contain frozen subexpressions.
Two-seed agreement at the original stats does not prove candidate response.

Controlled diagnostic deltas (not legal complete artifact replacements):

- Flins +187 EM: ordinary team DPS 149,163 -> 153,122 (+3,959; difference SE
  539). Neither captured graph has a Flins EM coordinate, so the offline
  prediction is exactly zero. This is a demonstrated missing dependency, not
  evidence that this stat is useless and not ordinary sampling noise.
- Kuki +187 EM: ordinary team DPS 110,841 -> 113,021 (+2,179; difference SE
  332). Do not claim full offline parity: only part of her reaction damage is
  variable; approximately 68% of her reaction-channel baseline is frozen.

Five ordinary n=64 measurements took 1.63-2.73 seconds each. Capturing and
validating one repaired member took 3.19-4.84 seconds. These are diagnostic
costs, not complete Selected/UI timings. No n=1000 or full search was run.

### Equipment/context limits

The disposable fixture seeder chose five pieces of the requested 4p set, or
Lauma's literal 2+2 bonuses, using actual inventory. It is not a main-stat
optimizer and does not enumerate off-pieces. The current Night set inventory
has DEF%/ATK% sands and one EM goblet, no HP% sands/goblet; hence the initial
Columbina build cannot match the website main stats with five set pieces.
Do not present 110,841 as her best attainable result. Sucrose is account C1,
not website C6; actual weapon/character levels and refinements also apply.

## Bounded trace bug repaired

The original bloom capture failed with `construction arithmetic mismatch` at
hit index 23. Upstream Lauma's `internal/characters/lauma/burst.go` subscribes
to the hit event and adds EM-scaled flat damage after the ordinary reaction
producer computed its number. That is valid upstream behavior, not corrupt
rotation input or a request to implement Lauma gameplay in GTT.

The old validator conflated producer arithmetic with the final modified
attack. The observer had already marked incomplete terminal provenance, yet
the exporter aborted instead of honoring that local boundary.

Generic repair, with no character/reaction-name branch:

- Keep strict producer identity, lineage and internal arithmetic validation.
- A different final flat value is allowed only with the existing explicit
  mismatch diagnostic and incomplete flat-damage provenance.
- The compact compiler freezes that affected reaction channel at observed
  damage and records `reaction_terminal_dependency_not_compiled`; other
  channels continue. Do not mistake this safety repair for Lauma support.
- Regressions reject unmarked drift, false completeness and corrupt producer
  arithmetic, and prove an adjacent ordinary channel remains variable.

Both Go packages pass; six focused application compatibility tests pass.
Fresh official-source patch/build/capability/consumer/ordinary/wave gate passes
in an isolated store. Both Flins fixtures now retain identical channel rows;
the previously failing bloom capture and native validation pass on both seeds.
Both saved current-team/Chasca channel arrays are also unchanged.
Both current-team members have zero wholly frozen channels (383 and 372
channels respectively), using the same coordinate-based metric as above. This
does not assert that every subexpression inside them has proven dependencies.

Production activation passed through the real updater, with identical isolated
and installed SHA256 `76f12ae8c2980a72815b46e46ee14aad1da07fbccec303b05460741ba7b06abf`.
Active `gcsim-v2.45.0-gob11-boundary-20260908`; prior
`gcsim-v2.45.0-compat-20260907` is the rollback target. The consolidated patch
has 96 entries and SHA256
`cef87ba147d78e52c4cb126cf5179f1f15c4385839cd3ed1a5de18928cf7685a`.

## Next decision and sequence

The earlier GP-1/2/3 formula work and response gates are complete within the
bounded source pilot; see GP3 checkpoint rather than replaying old blockers.

1. Use approved test-only Lauma4p Gilded Dreams in a new copied fixture.
   Original2+2 and live equipment remain untouched;2+2 support is deferred
   until core Selected is complete and is the next extension after that.
2. Then run unchanged bounded full search for bloom and report quality/time,
   source boundaries and supported versus unsupported stat responses.
3. Additional teams/rotations follow; automatic database config import later.
   Energy-aware Selected remains a separate scope.

No new search redesign, broad rerun or hidden budget increase is authorized
to claim away formula residuals. The two Flins results are useful measured
improvements, not proof that the formula is complete or globally optimal.

## Evidence and preservation

Permanent compact receipt:
`tests/fixtures/gcsim_optimizer_go_v1/gob11_supplied_rotation_validation_receipt_v1.json`.
It preserves numeric measurements, source block hashes, fixture artifact IDs,
weapons, substitutions, channel coverage and gate results, not the private DB.
Raw captures/configs/SQLite backups are under ignored
`.codex_tmp/gob11-user-rotations-20260908`; the harness and repair helper are
temporary, not a product importer or alternate scoring implementation.

AppShell's Selected signal/worker was followed to its production request,
materializer and capture functions; those backend functions were exercised
directly for fixed4p. The 2+2 fixture used the same materializer and engine
capture but cannot form a valid Selected request. No visible UI click or
new-team full optimizer success is claimed. Live equipment, original note,
and saved Chasca rotation were not written.

## Execution rules

Project venv, sequential work, no subagents, no brute force. Start with at most
two compact seeds and one reduced ordinary sample per fixture; add narrow
stat probes only for a declared question. Reuse saved captures. After three
substantive failed approaches to one blocker, discuss. Preserve unrelated
import changes. No new-team success claim from a one-point formula match.
