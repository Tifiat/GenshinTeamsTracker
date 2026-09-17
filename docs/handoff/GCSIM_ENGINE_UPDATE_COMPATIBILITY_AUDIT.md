# Engine update compatibility audit and repair

Date: 2026-09-07. Scope: post-GOB-11A, before GOB-11 cross-team tests.
The read-only audit was followed by an authorized bounded repair. Current
status below supersedes the former "not fixed yet" audit, but not cross-team
acceptance or the mandatory pre-MVP all-patches re-audit.

This is the historical 2026-09-07 repair receipt. Current installed engine,
rollback and acceptance are owned by `GCSIM_GOB11_GP3_CHECKPOINT.md`;
`GCSIM_GOB11_ROTATION_VALIDATION.md` retains the supplied-fixture chronology.
IDs and acceptance below describe this repair, not today's active installation.
Its disjoint wholly constant channel measure is not the conservative
opaque-reason exposure criticized below.

## Result and acceptance boundary

Narrow defects and automatic activation/rollback gaps are repaired. General
reaction-dependency completeness and unconditional future-update safety are NOT
proved. Do not announce a measured known/opaque damage fraction from current
conservative diagnostics.

At this historical repair: `gcsim-v2.45.0-compat-20260907`; pinned rollback:
`gcsim-v2.45.0-gob11a-20260907`. Actual rollback/restoration and trusted application
source/catalog/executable binding passed. Patch SHA-256:
`22f097feee2514c03a441536175d7352c516bc3deadca9cc9de09f1533e2a04b`.
Formula registry is now `gtt_trace_formula_v3`; compact schema remains v1.
Permanent receipt:
`tests/fixtures/gcsim_optimizer_go_v1/engine_compatibility_repair_receipt_v1.json`.

Paths under `pkg/` below refer to files inside the consolidated versioned
engine patch, not another production source checkout.

## Implemented repair

- UC-1: isolated reaction snapshots no longer inherit unproven owner artifact
  CR/CD/DMG%. Own EM, fixed special crit and proven modifier-event crit edges
  remain. Tests compare EM changes with the real upstream reaction producer.
  Supporting EM and reaction-bonus dependencies are not fully replayed: observed
  parts explicitly freeze with `reaction_em_external_dependencies_frozen` and,
  where applicable, `reaction_bonus_dependencies_frozen`. The EM warning is
  conservative even if a particular hit has no external EM buff. It does not
  mean reaction damage is wholly frozen or that support has zero effect.
- UC-2: each compiled hit is checked against its independent engine terminal
  value, undoing observed crit and applying expected crit. Incomplete/mismatched
  channels freeze locally; neighboring valid formulas remain variable. This
  verifies the captured point, not every candidate derivative or random schedule.
  The static foreign `max_hp` risk is also guarded: an unproven provider base HP
  freezes with `flat_damage_external_base_hp_unproven` instead of borrowing the
  hit actor's base. No live account occurrence of that case was reproduced.
- UC-3: native ordinary-result parsing rejects missing/null mean or SD, while
  explicit valid zero and unrelated future fields remain accepted. The deployed
  standalone optimizer executable was rebuilt.
- UC-4: official source-only/probe/`--prepare-only` preparation never activates
  or prunes previous installations. Built-engine activation requires existing
  patch/build/manifest checks plus all required capabilities, a nonempty matching
  artifact catalog, an ordinary/compact independent DPS smoke, variable formula
  inputs, validation by the ACTUAL standalone consumer, a two-wave smoke, and
  unchanged engine/consumer bytes during checks. Failure reports
  `application_compatibility_failed` and retains the active engine. Implemented
  in `engine_compatibility.py` and `engine_update.py`; tiny fixture characters
  are compatibility tests, not runtime gameplay heuristics. Generic store APIs
  still allow explicit manual/development activation. Optional feature groups
  are not implemented: the current required application bundle is atomic.
- UC-5: `rollback_engine_id` explicitly pins the prior active engine, independent
  of mtime or newer unused builds. Re-selecting the same engine preserves it;
  manual rollback swaps it. Legacy state without a pin conservatively retains
  existing successful installs until a subsequent activation records one.
- The real gate additionally found a wave-adapter bug: `dummy` construction
  passed an uninitialized resistance map to upstream and panicked. The adapter
  now initializes it; a permanent test checks default and overridden resists.
  The initial new smoke also omitted mandatory target type; its fixture was
  corrected, without relaxing engine input validation.
- UC-6 remains a version-sensitive integration boundary. A permanent test shows
  an unknown health API is not claimed supported. The bounded activation smoke
  does NOT prove all heal/buff API renames are detected by that tiny rotation.
  Keep diagnostics and expand representative controls with accepted mechanisms.
  Current patch: 94 entries, 52 new files and 42 upstream-file edits.
- UC-7 remains open: reason shares are overlapping conservative warnings, not
  measured per-channel/per-dependency attribution. Never sum them or label a
  partly variable reaction wholly frozen because external EM is fixed.

## Original findings (pre-repair behavior, retained for rationale)

### UC-1: unsupported artifact dependencies on transformative reaction damage

Confirmed implementation defect, not just a future-update risk.
`pkg/gttcompact/direct.go:compileTransformative` unconditionally adds the owner's
artifact CR/CD and generic DMG% deltas to a separately constructed reaction
snapshot. That snapshot does not necessarily inherit those character stats.
The upstream producer `pkg/core/combat/reaction.go:CalcReactionDmg` initializes
its own snapshot; the standard enemy calculation skips DMG% for non-stat hits.

Synthetic probe calls the real reaction producer, then the compact compiler:
zero-delta damage is 5098.436142857143 in both. Adding artifact CR=0.2/CD=1
produces a false +20%; generic DMG%=0.4 produces a false +40%. The latter is an
IR-coordinate probe, not a claim that an ordinary artifact has that main stat.
The crit probe is directly relevant to artifact selection. Zero-delta equality
and old/new graph parity cannot catch incorrect derivatives already present in
both versions. Final simulation measures selected builds correctly but cannot
recover a candidate discarded by an incorrect formula ranking.

Repair must follow proven snapshot/producer dependency ownership. Do not use a
reaction-name blacklist or globally forbid reaction crit: fixed/special crit
providers can exist. Also check the reverse loss in this compiler: it uses
frozen reaction bonus and observed EM plus own artifact delta, without the
direct compiler's supporting-stat event replay. Cross-owner support must either
have a proven edge or an explicit local freeze, not an implicit zero effect.

### UC-2: terminal formula consistency is not independent engine parity

Confirmed missing guard. `pkg/gttcompact/direct.go:compileChannels` sets channel
baseline from its own compiled expression. A synthetic standard, no-crit hit
reports 200 damage but has inputs compiling to 100; `CompileSeedMember` exports
100 without error or an opaque diagnostic. This simulates an unhandled terminal
multiplier/semantic change, not an observed 50% error on the user's team.
Internal zero-delta checks compare against that same generated baseline.

Add an independent same-trace terminal check and controlled stat perturbations.
Account for sampled versus expected crit; do not blindly equate one rolled hit
with its mathematical expectation. Unknown dependencies still freeze locally;
the check must not disable the entire scorer for an unrelated opaque branch.

### UC-3: missing ordinary-result fields silently become valid zero values

Confirmed in `native/gcsim_optimizer/internal/engineclient/ordinary.go`,
`ParseOrdinaryResult`. With correct `statistics.iterations`, absent DPS, absent
SD, or null numeric fields decode into zero-valued Go floats and are accepted.
Probes: `{iterations:500}` -> DPS=0/SE=0; `{iterations:500,dps:{mean:100}}` ->
DPS=100/SE=0. Null mean/SD also pass. An upstream output-format change can thus
look like real zero damage or zero uncertainty and affect adaptive verification.
Reject missing/null required numbers; allow an explicitly supplied valid zero.

### UC-4: updater activation checks do not cover the application contract

Confirmed narrow-gate gap in `engine_update.py:_make_engine_update_smoke_check`
and `artifact_build.py:_parse_gtt_info`. Build/version/GTT marker and generated
source identity checks are present. Required Selected capabilities, application
artifact catalog loading, compact consumer compatibility and real semantic
smokes are not all checked before automatic activation.

A probe with only marker/source-manifest capabilities, no trace/compact
capability and waves=false passes the info checker. Missing generator command
returns `not_required` from `source_manifest_build.py`; absence alone does not
fail a Selected-required bundle. The application rejects missing Selected
capabilities later, so this is premature activation, not silent successful use.
Source-only development preparation also intentionally activates without a
built executable; future production UI must not use those optional defaults.

Make preparation versus activation explicit; validate the full required bundle
and independent semantic fixtures before replacing a working engine. The last
stage's manual validation covered the installed build, not future automation.

### UC-5: cleanup does not pin the previous known-good engine

Confirmed selection defect in `engine_store.py:_kept_successful_engine_ids`.
Default retention is active + newest remaining by directory mtime. Given an
older known-good engine, a newer unused build and a new active engine, the
known-good one is omitted from the keep list. The probe did not delete engines.
Pin previous active/last semantically accepted explicitly; do not infer rollback
identity from modification time. Production rollback was not altered here.

### UC-6: runtime API discovery remains version-sensitive

Confirmed structural limit, not hardcoded new gameplay. The patch has 91 file
entries: 49 new files and 42 modifications of upstream files, including one
existing test. Most added implementation is isolated, but upstream damage,
reaction construction, snapshots, events, health, scheduling and aggregation
remain integration seams. A single patch is not a single upstream seam.

`pkg/gttsourcegen/scan.go:describeSeamCall` recognizes API shapes/names such as
Heal/Drain, QueueAttack*, Add*Mod, event Subscribe; `ir.go` recognizes MaxHP,
TotalATK and TotalDEF. A synthetic rename Heal -> RestoreHealth changes source
root discovery from true to false. This alone does not prove a silent live DPS
error: runtime hooks may diagnose the missing source or a build may fail first.
But successful compilation cannot guarantee discovery coverage after a refactor.
Keep API-shape/renaming/unknown-path tests and coverage diagnostics. Do not
replace this with character or reaction display-name matching.

### UC-7: opaque damage shares are conservative, not measured attribution

Existing documented limit in `pkg/gttcompact/compile.go`: each deduplicated
reason receives whole baseline damage and share=1 for nonzero damage. These are
overlapping conservative warnings, not distinct additive chunks or measured
unknown damage. Unsupported direct reaction channels retain observed damage;
reason records are not yet precise channel/dependency attribution. Before
GOB-11 claims an unknown fraction, distinguish a whole frozen hit from a frozen
multiplier in a partly variable hit and do not sum overlapping reason shares.

Additional static risk for targeted follow-up: `compileFlatDamage` uses the hit
actor's `base_hp` to expand a `max_hp` parameter even if `parameterActor` differs.
No live occurrence was reproduced here; prove the provider actor before using
that base, or freeze. Do not classify this as a measured account regression.

## Validation and next work

- 84 focused Python tests pass: 39 bundle/update/store and 45 manifest/catalog/
  contracts/Selected integration. Engine compact/enemy/GTT tests, the narrow
  source-API regression, and native engineclient/finalists/CLI tests pass.
- Clean v2.45 apply/build passes in isolation and production. Both executables
  hash to `47e47cdcd6873e486548bcf5e0b166f82b107b9c71092ee137e2781a6e7fbaae`.
- Existing current-team seeds retain 383/372 channels and identical baseline
  damage. The 84/73 reaction channels change candidate coordinates as intended;
  no new terminal mismatch/incomplete reasons appear. The actual consumer
  accepts both members. This does not re-prove finalist quality.
- Successful final acceptance uses 3 short smokes per installation plus those
  2 current-team captures. Earlier failed wave-gate diagnostics are additional,
  not included in that eight-run acceptance count. No full optimizer search,
  new-team rotation, full repository suite or production pruning ran.

Next is GOB-11: controlled stat probes on fixed rotations, including Lunar/
multi-owner and bloom-family cases. Report UC-1/6/7 limitations honestly. Do not
start with a broad account sweep. Unsupported direct-reaction dependencies
remain frozen; ER-aware search and pre-MVP all-patches cleanup stay later.

## Historical reproduction evidence and disposition

One Python probe and four isolated Go diagnostic tests reproduced the findings;
these tests assert current defective behavior, so their PASS is not a product
acceptance result. Full test suite was not run. Engine simulation calls: 0.

Original temporary probes (not current acceptance tests):

- `.codex_tmp/update_risk_audit_20260907.py`: gate, absent generator, rollback
  keep-list, patch seam inventory; imported production Python modules.
- `.codex_tmp/gob11a-source-20260902/pkg/gttcompact/update_risk_audit_test.go`:
  real reaction producer + compact dependency probe and terminal mismatch.
- `.codex_tmp/gob11a-source-20260902/pkg/gttsourcegen/update_risk_audit_test.go`:
  source seam discovery rename.
- `.codex_tmp/update_risk_ordinary_test.go` plus
  `.codex_tmp/update-risk-overlay.json`: compile a diagnostic test into the
  standalone engineclient package via Go overlay, without editing that package.

Corrected assertions were promoted into permanent engine
`gttcompact/dependency_validation_test.go`, `gttsourcegen/api_boundary_test.go`,
native ordinary-result tests, and Python bundle/update/store tests. The two
engine `update_risk_audit_test.go` files were renamed/corrected before patch
regeneration; faulty-behavior assertions are not in the current patch. Ignored
local residue is now disposable under the cleanup manifest. Never rerun a stale
audit overlay to claim that a repaired bug still exists.
