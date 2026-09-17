# GCSIM Engine Integration Plan

Planning date: 2026-06-04

Status reviewed: 2026-09-16

Scope: implementation-direction handoff for GTT-modified GCSIM engine integration. This is not a final Codex implementation task and not a rigid architecture freeze. It records the current product/engineering vector, open questions, and contracts that future Codex tasks must respect unless a later handoff explicitly supersedes them.

Related references:

- `docs/handoff/GCSIM.md` - original GCSIM research notes and upstream source pointers.
- `docs/handoff/GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md` - sole current
  optimizer architecture, engine provenance/guard contract, three product
  scopes, exact fallback and cutover requirements.
- `docs/handoff/STAT_NORMALIZATION.md` - project stat normalization and GCSIM stat-key mapping notes.
- `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md` - Run Workspace boundary, factual DPS vs sim DPS split, and snapshot/session state rules.
- `docs/handoff/ABYSS_ENEMY_DATA.md` - Abyss source-data pipeline and enemy rows.

## Current Authoritative Status

Current engine identity, pinned rollback, active patch, hashes, acceptance and
immediate optimizer work are owned by
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
This document owns engine/update/Browser contracts, not a second optimizer
status log.

Typed AttackEvent numeric fields/getters are version-sensitive integration
seams; arithmetic/conditions are read from source. New internal observations
retain strict validation, and unsupported writes/operands retain diagnosed
freezes. The earlier scalar/callback receipts are historical install checkpoints.
The additive pilot extends the existing core/reactable calculation seams with
scalar observation markers and optional capture plumbing. It does not copy
reaction formulas into the consumer: nested source recipes reuse its arithmetic
compiler. Source tests follow changed upstream coefficients. These named engine
seams remain version-sensitive and must pass apply/build/semantic gates after
an update; unsupported source expressions remain local freezes, not guaranteed
future coverage. The internal live field ledger includes non-callback writes.
The needless upstream reaction-to-lunar comment change was removed. No new
gameplay mechanics were added. Earlier compatibility acceptance remains
recorded in GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md.
Full cross-team reaction coverage and pre-MVP patch cleanup remain open.

The functional backend for the current selected-team Abyss Browser path is
implemented. Do not start another broad "finish the GCSIM backend" task without
a concrete failing scenario. The working path already covers:

- transactional engine acquisition/update, ordered GTT patches, build/runtime
  validation, active/rollback metadata, and bounded generated-engine cleanup;
- a patched `gtt-gcsim.exe` contract with `-gtt-info`, structured
  `gtt-wave-scenario-v1` payloads, sequential `group_clear` waves, artifact
  preflight, execution, and result parsing;
- selected runtime TeamBuilder state -> stable account/equipment ids -> full
  generated GCSIM config, with controlled readiness failures and no localized
  display-name identity guesses;
- current cached Abyss chamber/side data -> enemy type resolution -> explicit
  wave/HP payload, selected-chamber and sequential C1-C3 Browser runs;
- runtime Sim DPS results in typed `RunSessionState`, compact right-panel rows,
  stale-input clearing, and immutable Abyss History Snapshot serialization when
  the user saves the run;
- a diagnostic DPS Dummy execution path, boosted-energy settings, retention,
  and backend/dev coverage reports.

The remaining GCSIM work is primarily product UI, orchestration, and release
engineering, not missing config/run backend fundamentals:

- finish the Browser presentation, readable/no-code rotation UX, result detail
  navigation, readiness wording, and settings polish;
- replace the stale `History persistence: disabled` runtime wording. Abyss
  Browser results are not auto-saved per simulation, but current session results
  are included when the user invokes normal Run Save;
- add progress/cancellation and, only after measurement, optional bounded
  parallel batch scheduling; the safe current C1-C3 worker is sequential;
- attach DPS Dummy simulation results to typed DPS Dummy session/snapshot state;
- produce and release-validate the known-good bundled executable and build the
  dependency-aware advanced update UI;
- keep Traveler and entities genuinely absent from the active upstream GCSIM
  registry as controlled unavailable cases rather than app mapping bugs.

The tiny committed `gcsim_key_mapping_seed_v1.json` remains a dev/audit fixture,
not the production Browser mapping owner. Normal Browser runs use account SQLite
character/weapon keys resolved during import, active-registry artifact-set
resolution, and the enemy registry/Snap fallback pipeline. Coverage reports
should find real exceptions and upstream gaps; they are not a requirement to
hand-curate every automatically resolvable entity into one global mapping file.

Historical verification on 2026-07-17 (not rerun in this reconciliation):

- all 233 `tests/run_workspace/gcsim/` tests passed;
- all 18 `tests/ui/gcsim_browser/` worker/report tests passed;
- the focused History builder test confirmed typed GCSIM runtime results become
  immutable `sim_dps` summaries separate from factual DPS;
- the local entity coverage report inspected 414 catalog entities: characters
  102 ready / 15 missing / 7 deferred Traveler, weapons 225 ready / 6 missing,
  artifact sets 58 ready / 1 missing, with no ambiguous rows. Missing rows are
  current active-registry/upstream gaps unless a concrete identity bug proves
  otherwise.

Shared ownership boundary (not a claim that another task is currently running):
coordinate PvP/AppShell changes. Do not refactor
`ui/app_shell.py` or introduce scoped PvP GCSIM as part of the normal GCSIM UI
pass. Until the later AppShell refactor, keep GCSIM work inside the existing
hooks and prefer `ui/gcsim_browser/`, `ui/right_panel/live_run/gcsim/`, and
`run_workspace/gcsim/`. PvP-scoped simulation remains owned by the PvP handoff.

## Artifact Optimizer Engine/Browser Boundary

Detailed mechanics and delivery order live only in
`GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md`.

Do not grow a second optimizer roadmap here.

### Product boundary

Product scopes are:

1. Selected Sets: account search preserving currently equipped4p or2+2 packages;
2. All Sets: account search across every feasible modeled concrete set in the
   frozen shared artifact database;
3. Theory: inventory-independent equal-investment set comparison, fixed `4p`
   before `2p+2p`.

Selected derives its baseline and required set tiers from current equipment,
then verifies they match the prepared config. It does not have a separate set
picker. Future All Sets/package controls (including optional2+2 scope) and Theory
remain design work, not implemented switches. FAST is the working search
evaluator; no legacy Python strategy or STANDARD user speed mode is restored.

Underlying theoretical `4p`, theoretical `2p+2p`, and account operations may
retain separate typed/cache identities.

### Existing engine/config reuse

The optimizer reuses:

- the already ready selected-team/rotation/config context;
- trusted active engine/source/executable/catalog binding;
- exact selected-chamber wave-scenario or explicit DPS-Dummy target validation;
- GCSIM ordinary process/result primitives;
- pure stat normalization and set/stat rendering primitives.

For every candidate, all four source artifact stat/set blocks are replaced.
Every character, weapon, talent, option, rotation, target, and engine semantic
stays frozen. Selected preserves observed set-effect initialization order and
required bonus tiers. Current equipment is a comparison/candidate seed, not an
exclusive filter over the account's available artifact rows.

The frozen Python evidence was observed from concrete incumbent artifact
states. A second seed changed hit/reaction topology, proving that one full trace
is not expected-DPS truth. The accepted repair is not another Python trace-tree
stage: GOB-2 defines a compact engine-neutral adapter output and GOB-3 aggregates
the bounded stochastic panel natively in Go. The incumbent-delta Python form is
a parity oracle only; artifact stats and set state are explicit Go candidate
variables over the frozen non-artifact context.

Selected preparation reads current equipment to establish its legal seed and
chosen packages. Presets/History are not search-domain filters; the existing
explicit result Save action reuses preset services and does not auto-equip.

The account artifact domain is every `artifacts` row and matching
`artifact_substats`, frozen from a true read-only SQLite transaction.
Eligibility then defaults to valid 5-star rows, with explicit selected-set/ID
authorization for 4-star pieces. Malformed rows are reported and excluded
without failing unrelated legal builds.

### Upstream optimizer boundary

Upstream `-substatOptim` optimizes abstract substats after sets and main stats
are fixed. It does not choose real artifacts, main stats, set packages, or
cross-character ownership.

GTT must own:

- provenance trace capture and a versioned executable numeric IR;
- guard-aware rotation-conditioned replay and targeted exact fallback;
- main-stat, absolute-stat/cap, set and reaction-safe candidate discovery;
- lazy real five-piece generation and physical opportunity cost;
- global all-different assignment;
- recipient/channel-aware team-set allocation;
- common-fidelity finalist validation.

Ordinary GCSIM simulation verifies retained physical finalists. Upstream
`-substatOptim -out optimized.txt` may be reused only by an explicit Theory
operation after its equal-investment contract exists. `substatOptimFull` is a
disposable compatibility smoke only.

Optimizer comparisons use the same explicit target context chosen for the run:
the selected-chamber GTT wave scenario or the explicit DPS-Dummy target. There is
no hidden static-target fallback, because that would rank builds against a
different fight. A new Go patch is justified only by a concrete measured
capability/performance blocker.

### Optimizer engine status

The former M/S/New/Selected V2 search services and their optimizer UI wiring are
not active architecture. Lower-level engine lifecycle, artifact database,
materialization, legality, transport, cancellation and cache primitives may be
reused only through the current trace-equation contract.

The current bound development engine exposes trace/provenance/source/state and
support capabilities accumulated through every patch currently present. It
supplies the observed hits, snapshots, reaction formulas, attack tags, raw
damage types and bounded source programs consumed by the temporary Python
reference. Do not use a historical numeric patch endpoint as the active
contract; discovery and identity always cover the complete present stack.

The accepted optimizer evaluator roles are:

- FAST - production search evaluator; response-signature channels rank directly
  into a bounded GCSIM finalist batch;
- STANDARD - bounded development/regression control only;
- detailed per-candidate traversal - narrow parity fixture only.

Do not add a hidden STANDARD pass or fall back to an older optimizer when trace
binding fails. A binding/schema/source mismatch disables the affected optimizer
context fail-closed and reports readiness.

The active application optimizer engine/UI has not been cut over. Current
measurements use the bound saved development trace and prove offline arithmetic,
not a working product button or cold product runtime. The sole current
implementation sequence is in
`GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md`.

The runtime source of truth remains `data/gcsim/engines/active_engine.json`;
handoffs must not pin a generated engine directory. Machine patch/tree/binary
identities and historical schema receipts belong in the cleanup manifest, not
in this human task queue.

Before product cutover, audit every patch that exists at that time, discard
obsolete deltas, consolidate all required modifications into one versioned
patch, and prove automatic update plus atomic rollback. Patch discovery must
cover the complete stack present at execution time; no numbered subset may be
hard-coded into that task.

### Stable correctness rules

- Exactly four wearers, five real slots each, and twenty distinct IDs in every
  account success.
- Canonical real-build identity is ordered `slot -> artifact_id`; `5p` and
  `3+2` are not duplicated by free-slot labels.
- Concrete DB set identity is `set_uid`; renderer identity is a registry-
  validated GCSIM key.
- Missing set parameters use pinned GCSIM default/automatic behavior and do not
  blanket-block the set.
- Default product search is 5-star only.
- Original source artifact stats never combine with candidate stats.
- Low fidelity is screening only; displayed rows share a common minimum final
  fidelity and close leaders rerace.
- Every account proposal is rechecked fail closed against its package-specific
  hard floors before scorer or GCSIM submission.
- Simulation-cache identity is compiled config/execution; assignment provenance
  separately binds the request, DB input, and twenty IDs.
- Normal search keeps bounded audit/provenance evidence. Trace persistence is
  retention-bounded but the trace itself is a production scoring input, not an
  accepted candidate or an optional debug oracle.
- Search never equips or saves.

### Future UI/save boundary

The optimizer is a dedicated GCSIM Browser view. Backend milestones do not touch
UI/AppShell. A later UI milestone may use narrow existing hooks, but it does not
authorize a global AppShell refactor.

Search results are ephemeral and not History. Planned explicit save flow:

- generic per-wearer account `stat >= X` controls;
- energy/ER optimization follows the shared energy-mode and ledger contract in
  the authoritative optimizer handoff; current FAST must not infer it from
  damage-only evidence;

- save an individual wearer to an Artifact Browser preset;
- default name `best_found_<other three team members>`, user-editable;
- `Save team` reuses already saved rows and creates missing ones;
- store one GCSIM-only multi-preset referencing those four preset IDs;
- later explicit apply can equip all four atomically.

There is no generic manual multi-preset constructor and saving never auto-equips.

### Shared energy-mode UI boundary

Account/Settings -> GCSIM and the inline optimizer control beside the optimizer
action are two synchronized views of the existing settings-owned
`gcsim_boosted_energy_enabled` value. Changing either updates the other,
invalidates stale simulation results and affects subsequent runs only. Infinite
mode keeps Browser boosted-energy injection and makes Selected write/pass
`ignore_burst_energy=true`; the other mode keeps normal Browser energy and makes
Selected write/pass `ignore_burst_energy=false` instead of overriding it.

The energy-requirements position is intentionally visible as a diagnostic
boundary at the user's request, but its inline warning is authoritative: the
current search does not yet optimize ER and the rotation may fail. Do not call
that position energy-aware optimization until the ledger, search constraint and
finalist schedule verification below pass. A later explicit `EnergyMode` type
may wrap the stored boolean, but must not create a second optimizer-only value.

CPU limits, cancellation, progress, cache retention, reduced exhaustive oracles,
adversarial account-floor (including ER), theoretical no-auto-ER,
EM/HP/DEF/crit/support fixtures, and measured recall/regret remain release
requirements. FAST remains the sole product search evaluator; STANDARD is not a
user-facing speed mode.

## 1. Product Direction

The application should expose GCSIM-backed calculations inside the GenshinTeamsTracker UI, especially in the Run Workspace/right dock where Factual DPS and prepared Sim DPS result cells live.

The UI-level contract is:

- User selects/equips teams, weapons, artifact builds, and an Abyss chamber/side scenario.
- The app sends a structured scenario to a local GTT-modified GCSIM engine boundary.
- The engine returns sim DPS, simulated clear time/timer data, warnings, and engine/scenario metadata.
- Right-panel Sim DPS cells show compact results; deeper config/result/debug UI can live in a separate workspace/window/overlay.
- If team/build/enemy scenario/target mode/engine version changes after a sim result was produced, keep the result visible but mark it stale instead of silently treating it as current.

Factual DPS remains app-owned HP/time math. GCSIM results are `sim DPS` and must not be mixed into factual DPS calculations.

## 2. Engine Update / Patch Model

The intended update model is official GCSIM source plus the versioned GTT engine
delta embedded in the application:

```text
official genshinsim/gcsim source release or commit
+ versioned consolidated GTT patch shipped with the app
= local GTT-GCSIM engine folder
```

The app-level `Update GCSIM` action should be transactional:

1. Download/select official GCSIM source for a chosen release/commit/PR source.
2. Create a new local engine folder.
3. Apply the versioned consolidated GTT patch shipped with the app.
4. Generate and validate any source/dependency manifest required by the patch,
   bound to the exact upstream source and complete patch identity.
5. Build/prepare the engine runtime.
6. Run capability, manifest and compatibility smoke checks.
7. Activate the new engine only if patch/build/manifest/smoke all pass.
8. If anything fails, keep the previous active engine and report incompatibility.

Implemented official-update gate: source-only/development probes and
`--prepare-only` never activate or prune installed engines. Activation of a
built engine requires the complete source/trace/compact/wave/effect-input capability bundle,
matching artifact catalog, independent ordinary/compact DPS agreement, actual
standalone-consumer validation and a two-wave smoke. Engine/consumer bytes are
checked for stability during validation. The required bundle is currently
atomic; optional patch groups remain future work. Explicit low-level manual
activation is separate from this official-update workflow.

All Sets requires `gtt_effect_inputs_v1`. Installed source verification excludes
only generated build material and the exact root `gtt_engine_manifest.json`
written after compilation; module/source changes remain identity failures.
The2026-09-17 clean install exposed CRLF-only differences from its research tree:
the exact hashes were retained, semantic source equivalence was checked and the
new executable received separate bundle/winner controls. This does not relax
ordinary updater hash validation. Generated absolute build overlays also need
rebasing after staging is moved; the current installation did this explicitly.
Normal updater relocation remains in the pre-MVP safety TODO, not a claimed
generic repair. Current identities and acceptance live in GP-3.

`active_engine.json` records `rollback_engine_id` as well as `active_engine_id`.
Retention always protects that pin, not merely the newest directory. Legacy
state without a pin conservatively preserves existing successful engines until
an activation supplies one. Re-selecting the same engine must not lose the pin.

Guarantee target:

- If upstream GCSIM areas touched by GTT patches remain compatible, patches should apply and the new local GTT engine should become usable automatically.
- If upstream changes conflict with GTT patches or break smoke checks, the app must not activate the new engine.
- Older working engine folders must remain selectable/rollback-capable through the bounded local engine-store retention policy.

A small retained local engine stack is acceptable, for example active plus one previous known-good engine and one latest failed/debug engine. Generated engine folders should stay bounded by retention; unbounded accumulated full source/engine copies are a size problem, not a desired cache.

### Shipped engine and dependency UX contract

The app should ship with a known-good, prebuilt GTT-GCSIM engine artifact that was produced and validated by the project release process. This bundled engine is the out-of-box calculation engine and must work for normal users without requiring Go, Git, Python, or any build tool on their PC.

The shipped engine must not be deleted by ordinary user-triggered GCSIM updates. It should remain available as the trusted fallback even if the local update stack keeps only a small number of downloaded/generated engines. Rationale: a locally rebuilt engine may appear to work at first but later reveal a subtle issue; the release-shipped engine should remain recoverable as the last project-validated baseline.

The `Update GCSIM` UI must not assume the user's Windows installation has build dependencies. The update flow should explicitly detect dependency readiness and present choices before trying a source rebuild:

- automatic dependency install path, preferably using `winget` when available;
- manual dependency path, with links/instructions for official Go and Git downloads;
- already-installed dependency path, where Go/Git are detected and the update proceeds;
- cancel/keep-current-engine path.

The app may later help install dependencies automatically, but it must not silently install Go/Git. Any dependency installation must be explicit, user-confirmed, and recoverable. `winget` must be treated as optional, not guaranteed. If `winget` is unavailable or dependency installation fails, the built-in shipped engine remains active and calculations remain usable.

The final UX should communicate that GCSIM source updates are an advanced/local rebuild path. Normal calculations should continue through the shipped engine even when local update dependencies are missing.

### Future Settings -> GCSIM update failure and compatibility UX

The user-facing `Update GCSIM` action belongs in `Settings -> GCSIM`. It must
call the existing transactional update backend; UI code must not replace the
active engine pointer or build an engine independently.

An unsuccessful update must be a clear, recoverable product result rather than
a generic error. The UI must state all of the following:

- the requested upstream release and the stage that failed (`download`, patch
  compatibility, build, capability smoke, or semantic/runtime smoke);
- that the application is still using the last verified working engine, with
  both its GTT build identity and its upstream GCSIM version;
- where expandable technical details/debug evidence were saved;
- whether a compatible release search was attempted and which release, if any,
  was selected instead.

The compatible-release search must be bounded and fail closed. It must never
force-apply a patch, silently downgrade, scan an unlimited release history, or
activate a merely compiling binary. Start with the requested release, then use
versioned compatibility metadata for this GTT patch/schema to try the newest
known-compatible release (normally including the currently active upstream
release) and only a small explicitly bounded candidate list. A candidate may
activate only after patch check, build, `-gtt-info` capability validation,
compact semantic parity, and ordinary-simulation smoke all pass in staging.
The UI must explain any fallback before activation and show the final active
version. If no candidate passes, keep the previous verified engine active and
say that the application patch must be adapted for the new upstream version.

Compatibility metadata must distinguish upstream GCSIM release/commit, GTT
patch identity/schema, and produced engine build identity. This cannot prevent
upstream from changing an integration seam, but it must prevent such a change
from breaking the installed application or leaving the user unsure which
engine is actually running.

## 3. Engine Patch Direction

Post-GOB-11A update-risk audit (2026-09-07):
[GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md](GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md)
records the findings and completed bounded repair. False transformative
artifact dependencies, missing terminal/result guards, incomplete automatic
activation gates and unpinned rollback retention are repaired. The real gate
also caught and led to fixing an uninitialized resistance map for wave dummies.
External reaction-support dependencies, API drift and precise opaque attribution
remain bounded limitations, not claims of general reaction-team validation.

GTT features should remain a minimal, isolated delta over GCSIM, not broad
rewrites scattered across the engine. The current ordered development patches
are valid reconstruction/forensic inputs, but before product cutover the task
must audit every patch that exists at that time, remove superseded changes and
produce one versioned consolidated patch as the only active update input. Do
not consolidate only a historical numbered subset: audit and classify every
patch file present when the consolidation stage begins.

The optimizer itself is not part of this patch. The accepted boundary is a
standalone `native/gcsim_optimizer` Go binary which depends only on versioned
GTT request/result/compact-IR contracts. The consolidated engine patch contains
the smallest adapter that converts unavoidable GCSIM runtime internals into that
IR and exposes ordinary finalist simulation. It must not contain artifact
enumeration, FGBS, stochastic panel policy or UI behavior. Upstream symbol use is
confined to the adapter so patch/build/smoke fails before activation if those
seams change.

Preferred shape:

- Keep most GTT logic isolated in GTT-specific packages/modules inside the patched source tree, such as scenario, wave scheduler, engine API, and result metadata modules.
- Touch upstream GCSIM core/parser/setup/combat code only at narrow integration points.
- Keep patches small enough that upstream updates adding characters, weapons, artifacts, or ordinary mechanics usually merge cleanly.
- Treat conflict with target/combat/event/setup internals as an expected compatibility failure requiring a newer app/patch-stack version.

Patch packaging may become physically modular at the pre-MVP re-audit, but
feature activation must remain capability-atomic. Optional groups such as the
wave scheduler may fail compatibility and be disabled without discarding a
separately valid optimizer adapter. Required pieces of one feature must never be
partially activated: Selected may activate only when its whole adapter/manifest/
trace capability bundle passes. The updater keeps the previous verified engine
whenever a required bundle fails and reports which patch group was incompatible.

### Upstream ownership of Lunar and Stellar mechanics

Official GCSIM v2.45 already implements Lunar Charged, Lunar Bloom, Lunar
Crystallize and Stellar Conduct damage. GTT did not add those game formulas. The
current adapter observes the upstream direct-reaction calculation and uses its
executed path plus producer receipts/structural flags to classify damage, without
a duplicated list of Lunar or ordinary reaction tags. Stellar Conduct exposed a generic source-generator
case; the GTT response was to stage declarations safely and freeze unsupported
live conditional boundaries, not to implement Stellar damage.

The duplicated reaction classifier was removed in GOB-11A before cross-team
validation. The pre-MVP patch re-audit remains mandatory. No character,
region or future-reaction gameplay formula may be hardcoded into GTT merely to
make a trace test pass.

### GOB-11A: observed-path reaction classification

Status: PASS 2026-09-07. Receipt:
`tests/fixtures/gcsim_optimizer_go_v1/gob11a_reaction_classification_receipt_v1.json`.
All three bounded gates below are complete. This is the historical GOB-11A
checkpoint; the later compatibility repair below supersedes its active identity.

Implemented result in `0001-gtt-engine-adapter-v245.patch`:

- `gttTraceReactionOperatorID` no longer contains reaction tags, names or numeric
  tag ranges. Amplified/catalyzed flags retain their operator meaning; separate
  reaction damage uses the generic producer's formula identity/operator receipt.
- Actual terminal calculation branches set `standard`/`direct_reaction`.
  The existing upstream decision to apply ordinary damage bonuses is recorded
  at that branch; a non-stat hit lacking a producer receipt becomes explicitly
  unknown. GCSIM's own gameplay dispatch remains untouched.
- The post-calculation guard now sees the executed branch. Unknown paths remain
  trace hits and diagnostics; unused code creates no additional hit roots.
- The flattened formula registry is `gtt_trace_formula_v2`; manifest generation
  binds it. Compact IR remains v1. Go and retained Python reference consumers
  accept `direct_reaction`; old `direct_lunar` evidence keeps its spelling/hash
  and remains non-exact. Engine/source/patch identities prevent cache mixing.
- A synthetic regression exposed an existing terminal compiler error: a
  direct-reaction receipt with observed damage 1850 became standard damage 250
  and gained unproven ATK/DMG% coordinates. Unsupported direct reactions now
  retain observed damage with `direct_reaction_dependency_formula_not_compiled`
  rather than claiming that ordinary talent arithmetic is valid for them.
  This freezes the whole unsupported hit, not a newly implemented Lunar formula;
  multi-owner/EM/conditional dependence is still a required GOB-11 control.
- 58 focused Python update/manifest/contracts checks and 15 catalog/Selected
  checks pass. Engine tests pass in enemy, compact, combat, optimization, event,
  GTT packages and the reaction lineage fixture. Unknown tag/name, trace-off,
  ordinary flags, legacy spelling and an unaffected neighboring hit are covered.
- Two fixed seeds (742031889/742031890) retain 383/372 channels, exact channel
  records, opaque boundaries and topology. Expression hashes match after sorting
  commutative operands; raw node arrays can differ because pre-existing map
  iteration changes constant order. No stat-dependency/formula change was found.
  The standalone Go consumer validates both new members.
- Ordinary trace-off damage parity and a real two-wave smoke pass. Seven short
  simulation invocations total (four compact old/new, two ordinary old/new,
  one wave); no formula search, finalist screening or full optimizer rerun.
- Clean pinned v2.45 patch apply/build, capability checks, production binary
  parity, trusted application engine/catalog binding and rollback/restore pass.
  At that checkpoint, active: `gcsim-v2.45.0-gob11a-20260907`; rollback:
  `gcsim-v2.45.0-clean-adapter-20260901`. Executable SHA-256:
  `ecbeb14af152c25e67bafb567912aebc1a8ceb3d8fb6e0a6a6cfc1529d4087c1`;
  manifest body: `1c3e36cd059388a6c5a727d95dd50f19d5a8c3242b6357360c2955eb41f9743e`.
- Two incidental integration fixes were needed: resolve the engine directory
  before forming build/probe paths; read v2.45 `Issues/artifact.dm.json` and
  canonical pipeline artifact `name` instead of requiring legacy `key`.
  Old catalog layouts remain supported; missing issue metadata is still an error.

Required boundary:

- Start per-rotation runtime exploration from actual damage hits and follow
  their source/callback/task/modifier/reaction edges, including supporting
  healing and buff actions that explain those hits. Use source identity bound
  to the engine manifest and concrete event occurrences, not displayed words.
- Generic hooks in damage, reaction, event, snapshot, modifier and health paths
  stay: source text alone cannot reveal the actual inputs, selected branch or
  temporary buff state. An unexecuted hook emits no runtime evidence. A full
  build-time source manifest remains valid; this is not a demand to rediscover
  or regenerate the engine source per rotation.
- Prefer classification by the executed calculation path and recorded
  arithmetic/operator provenance. Stable upstream structural flags/traits are
  acceptable where their meaning is verified; do not replace a named whitelist
  with an unverified numeric tag range. Do not infer formula completeness merely
  from a known reaction name or from the fact that GCSIM produced damage.
- Use generalized direct-reaction naming (`direct_reaction`) and remove
  reaction-name dispatch where generic evidence supplies the same semantics.
  If evidence is missing, freeze the local dependency with diagnostics; do not
  erase a supported formula or silently turn every reaction opaque to claim
  that hardcoding has been removed.
- GCSIM keeps ownership of gameplay formulas, coefficients and execution.
  Recognizing a generic arithmetic operation is not a promise that arbitrary
  future Go code can be fully decomposed. No character/region lookup tables,
  gameplay additions, runtime keyword search, search rewrite or ER work here.

Completed gate sequence (retain as regression scope):

1. Map trace producers, compact conversion, validators and retained consumers.
   Prove which existing fields/edges can distinguish supported operators; list
   any missing evidence before editing. Check schema/hash/cache identity and
   choose explicit compatibility handling for old `direct_lunar` evidence.
2. Implement the narrow generic classification in the adapter and necessary
   consumers. Add focused checks for ordinary and direct-reaction paths, a
   renamed/unknown tag using a known generic path, and an unsupported path that
   freezes without failing the other formulas. No full account run.
3. Rebuild the consolidated patch against pristine pinned upstream; validate
   capabilities and compact output. Reuse the fixed current-team seeds for
   parity (same damage/dependencies, aside from intentional metadata changes),
   verify unused reactions do not become runtime hit roots, and run bounded
   ordinary/trace-off and transactional-update checks. Preserve rollback;
   activate only after all required checks pass. Full Lunar/multi-contributor
   stat-direction and ownership tests remain GOB-11, not a claimed result here.

Stop and discuss if supporting a generic path requires new dependency
semantics, damage ownership rules or broad source-compiler work. Follow the
three-substantive-failed-attempt rule. Do not hide the blocker behind category
renaming, broader exact simulations or silent loss of formula coverage. The
pre-MVP all-patches audit still remains mandatory after this correction.

### Post-GOB-11A compatibility repair — PASS in bounded scope

Receipt: `tests/fixtures/gcsim_optimizer_go_v1/engine_compatibility_repair_receipt_v1.json`.
Installed binary SHA-256:
`47e47cdcd6873e486548bcf5e0b166f82b107b9c71092ee137e2781a6e7fbaae`.
Source manifest body:
`96cd34877825b93e296179c8007d5b6babcc2cfb8a4a7d91171276b72c2497c0`.
Formula registry `gtt_trace_formula_v3`, compact schema v1. Both current-team
seeds retain baseline damage and 383/372 channels, with corrected dependencies
on their 84/73 reaction channels and no new terminal mismatch. This is an
intentional candidate-coordinate correction, not identical expression graphs.
No full optimizer or new-team search was run. Read the compatibility audit for
implemented guards and remaining external-support/API/opaque limits.

### Formula source/dependency manifest

Optimizer source analysis is part of engine preparation, not a repeated button
or candidate-ranking operation. The prepared engine now carries a deterministic
manifest that maps stable, module-relative source IDs to modifier functions,
event callbacks, scheduled tasks and attack/heal/drain construction roots needed
by trace analysis. The semantic body binds upstream source, complete applied
patch, patched tree, trace schema, source-compiler and toolchain inputs; the
outer engine manifest separately binds that body to the executable.

Runtime instrumentation stays at narrow central seams and emits those IDs with
provider/value/frame lineage. A cached Go AST/type/SSA analyzer follows only the
roots actually executed by the frozen trace. Supported arithmetic and state/event
edges become the optimizer's small numeric IR; unsupported code terminates at an
explicit `OPAQUE_FROZEN` boundary. A manifest mismatch or unknown required
semantic keeps the previous engine/result path available for ordinary GCSIM but
marks optimizer dependency replay unavailable. It must not activate a partially
compatible optimizer engine or invoke an old search backend.

The earlier `1774113`-byte body with SHA-256
`3101329b13280508cfe76feda58f93ace860cbab8d5d51949b6ec2011496d486`
and tree SHA-256
`a38eba55c8dcf1a42a36bf6684aa0cadffd368d333f2aaf45dda686336faabb4`
used `patches=[]`, `upstream_ref=accepted-0011` and a synthetic pristine hash.
It is cross-language smoke evidence only, never the production update-chain
passport above.

Future automatic-update hardening, not a blocker for the current ordered-state
dependency slice, must add: body-to-overlay semantic coverage or a mandatory
tiny latest-schema trace smoke; construction of `SourceManifestBinding` only from a verified
`GcsimOptimizerEngineContext` with artifact/tree/binding comparison before
product use; and a post-build staged-source re-hash to close concurrent staging
mutation. These are product-cutover/update-activation gates.

Planned/possible patches include:

- GTT engine API/capabilities.
- GTT scenario metadata.
- Sequential Abyss wave scheduler.
- GTT result metadata and scenario hash reporting.
- Future GTT-specific target models or debug hooks.

## 4. Sequential Waves / Abyss Target Modeling

Vanilla GCSIM supports simultaneous multi-target scenarios. GTT needs additional sequential wave behavior for Abyss-like scenarios.

Required conceptual feature:

```text
enemy/group dies -> spawn next enemy/group
next dies -> spawn next enemy/group
all scheduled enemies/groups are exhausted -> simulation ends
```

This must happen inside one simulation iteration/run so that buffs, cooldowns, energy, auras, summons, snapshots, active character, and other combat state are preserved across waves.

Important clarification:

- GCSIM `iterations` should be used as repeated Monte Carlo runs of the whole scenario.
- One iteration should represent one simulated Abyss pass/side/chamber scenario.
- Inside each iteration, GTT wave logic handles the sequence of enemies/groups.
- After one full wave scenario ends, the next GCSIM iteration repeats the same full scenario with a different seed as usual.

Open target model options to research/compare:

- `simultaneous_multitarget`: all targets exist at once; vanilla-like multi-target behavior.
- `single_big_target`: one combined HP target; simple but loses AoE/multi-target behavior.
- `representative_multiplier`: simulate representative target(s) and scale by count/HP; useful approximation for some multi-target rooms.
- `sequential_group_clear`: spawn the next group only after the whole current group is dead.
- `sequential_rolling_replacement`: when one target dies, spawn the next queued target into its slot while other current targets remain alive.
- Hybrid Abyss policy: identical enemy stacks may use rolling replacement, while transition to a different enemy/boss may require clearing the remaining current group first.

The exact model for rooms like `3 + 3 + 3` must be researched against actual Abyss behavior and GCSIM mechanics before being treated as product-correct. The handoff intentionally records this as a design area, not as a locked algorithm.

## 5. Abyss Sim Timer

GCSIM Abyss results should eventually produce a simulated clear time and corresponding simulated Abyss timer/remaining time.

Possible sources:

- If the GTT/GCSIM scenario is kill-mode with finite target HP, prefer the simulation result duration statistics, for example mean duration.
- If using fixed-duration sim DPS mode, derive clear time with the same HP/time relationship used by factual DPS: `sim_clear_time = abyss_side_hp / sim_dps`.

The UI should label this separately from factual timer values and carry engine/scenario metadata.

## 6. Key Mapping

### Deferred update-path/UI audit (user decision2026-09-17)

The updater must be reviewed end-to-end through application consumers, not just
patch/build success. Cover import character/weapon resolution, persisted mapping
refresh/invalidation after an engine change WITHOUT requiring reimport, active
artifact/enemy registry paths, selected-team snapshots, prepared normal/optimizer
configs, source caches, UI readiness, rollback and restart. Include newly added
entities and generated registry filename/layout changes in regression scenarios.
The Jahoda incident used old2.42.2 import registries while2.45 supported her;
the current narrow fix is not evidence that all other paths are aligned.
Artifact/enemy report/preparation defaults also need explicit audit rather than
assuming they follow the corrected account resolver.

Settings/GCSIM should later display the actual active release and local modified
build identity. A future picker may offer already retained compatible patched/
built installations through the existing bounded store and activation/rollback
gate; merely downloaded/unvalidated sources must not be shown as ready engines.
These are documented future tasks, not UI changes authorized in this repair.
TODO owns scheduling; no second independent engine selection setting.

Key mapping is a separate required task before reliable config/scenario generation.

Contracts:

- Do not feed localized display names to GCSIM.
- Map project/account character, weapon, artifact set, and enemy identifiers to GCSIM keys using stable IDs or generated mapping data. For account characters and observed weapon stacks, `name` is localized display text; future config adapters should use stored resolved `gcsim_character_key` / `gcsim_weapon_key` fields only when their status is `ready`, rather than searching localized names.
- Traveler is explicitly deferred for initial GCSIM integration; do not silently guess a Traveler element/variant.
- Missing or ambiguous mappings should make a slot/scenario not ready for GCSIM rather than producing a misleading config.
- A backend/dev entity registry report has been added in `run_workspace/gcsim/entity_key_readiness_report.py`. It parses local prepared GCSIM shortcut sources for accepted character, weapon, and artifact set config keys, prefers explicit seed overrides, then reports exact normalized project-name candidates, and then applies a conservative contiguous-name-span fallback. The span fallback matches whole normalized tokens/spans only, not random substrings: `Yumemizuki Mizuki -> mizuki` and `Rainbow Serpent's Rain Bow -> rainbowserpent` are accepted as audit candidates, while `The Daybreak Chronicles -> ak` is rejected. Exact/span candidates are readiness evidence only and are reported with `auto_exact_candidate_not_curated_mapping` or `contiguous_name_span_candidate_not_curated_mapping`; they must not be silently promoted into committed curated production mappings.
- The default report CLI is `python -m run_workspace.gcsim.entity_key_readiness_report --format text|json`. Without an explicit entity fixture, it reads only existing local HoYoWiki character/weapon stats caches plus `data/static/artifact_set_catalog.json`; character/weapon cache identities are HoYoWiki `entry_page_id` values and are warned as diagnostic identities, not the missing production game-id mapping owner. Names such as Mizuki in this report come from the local HoYoWiki cache/catalog and the local prepared GCSIM registry, not from account SQLite localized names and not from network at report runtime. Full production project-id-to-GCSIM-key coverage is still future work.
- Account SQLite sync now materializes a narrower account-owned result for
  current account characters and observed weapon stacks: `catalog_english_name`,
  resolved `gcsim_character_key` / `gcsim_weapon_key`, status, and method. This
  uses the same local registry matching logic once per sync and stores only
  ready keys as config-ready values. It does not solve artifact-set mapping,
  Traveler variant selection, selected-team/current-build ownership, or global
  production mapping coverage.

## 7. Character Level Helper

GCSIM character config needs current/max level style values such as `80/90` or `90/90`.

Current account/runtime data may not always expose character ascension/max level directly. A pure helper has been added before full config generation:

```text
run_workspace.gcsim.config_level.resolve_gcsim_level_text(level, promote_level) -> current/max level + warnings
```

The helper mirrors the project breakpoint assumption: `80,5 -> 80/80`, `80,6 -> 80/90`, `70,4 -> 70/70`, and `70,5 -> 70/80`. If `promote_level` is missing on breakpoint levels 20/40/50/60/70/80, the character is assumed after ascension and the result carries `promote_level_missing_assumed_after_ascension`. Level 90 is `90/90`, and special/final caps 95 and 100 are accepted as `95/95` and `100/100`. Missing level returns controlled `missing_level`. This helper is still formatting/readiness support only; it does not generate config text.

A backend character config block builder has been added in `run_workspace/gcsim/config_blocks.py`. It accepts already-prepared mapping refs, level/promote data or ready level helper results, constellation, confirmed normal/skill/burst talents, weapon mapping/refinement/level, artifact set counts, and artifact build snapshot stat totals. Ready input renders only the character/equipment block lines (`char`, `add weapon`, `add set`, `add stats`). Missing mappings, unsupported Traveler, unconfirmed talent order, missing levels/refinement, ambiguous set mappings, or no mappable artifact snapshot stats return a controlled not-ready result with no partial config text. `add stats` is restricted to artifact snapshot totals normalized through `hoyolab_export/stat_normalization.py`; character base stats, weapon base stats/passives, final/right-panel totals, and artifact set bonuses must not be injected here. This is still not full GCSIM config generation, account/team adapter wiring, artifact execution, or UI integration.

A backend/dev full-config assembly boundary has been added in `run_workspace/gcsim/config_assembly.py`. It combines ready generated character blocks with a rotation/options shell and refuses to emit partial full config if any block is not ready. The Chasca/Ororon/Furina/Bennett shell fixture lives at `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt` and contains only options, energy, a placeholder target line, active character, and rotation script. That shell is not account truth: it must not contain manual `char`, `add weapon`, `add set`, or `add stats` lines, and the assembler rejects shells that do. The target line remains parser/website-style placeholder text; enemy waves, HP, and target types remain the generated schema-v1 `-gtt-wave-scenario` payload. A narrow prepared-input adapter boundary exists in `run_workspace/gcsim/prepared_config_adapter.py`; it accepts explicit backend/dev dict/JSON input and converts it to `GcsimCharacterConfigInput` without UI access, storage queries, network, or final/right-panel stat totals.

Prepared full-config bridge support has been added to the same adapter module. CLI: `python -m run_workspace.gcsim.prepared_config_adapter --fixture path --rotation-shell path --format text|json`. Default dev fixture `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json` is marked `synthetic_dev_fixture`: it is not account truth, not UI state, and not production mapping data. It uses registry-checked GCSIM keys for Chasca, Ororon, Furina, Bennett, their synthetic weapons/sets, confirmed talent order, and artifact-snapshot-only synthetic stat totals. The bridge writes a generated full config only when all prepared characters and the shell audit are ready; missing required characters, missing/ambiguous mappings, unsupported Traveler, missing weapons, missing talents, or missing artifact stats produce a not-ready report with no config output.

Account-backed backend/dev prepared config bridge now exists in `run_workspace/gcsim/account_prepared_config.py`. CLI: `python -m run_workspace.gcsim.account_prepared_config --format text|json`; optional cached-Abyss smoke: add `--run-abyss-smoke`. It reads real `data/artifacts.db` account rows for Chasca/Ororon/Furina/Bennett, consumes stored ready `account_characters.gcsim_character_key` and `account_weapon_observed_stacks.gcsim_weapon_key`, and never uses localized `name` fields as GCSIM identity. Current-equipped weapon rows are used when present; otherwise a deterministic ready observed weapon stack of the matching weapon type is selected and reported with `dev_weapon_candidate_not_account_truth`. Current-equipped artifact rows are consumed when available: `account_character_equipped_artifacts` joins `artifacts` and `artifact_substats`, `add stats` is built only from equipped artifact main/sub stat totals, and `add set` is built from equipped set counts. Final account/right-panel stat sheets and manual set bonuses are not injected. Missing or incomplete current artifacts produce a controlled not-ready report instead of a silent synthetic fallback. Artifact set keys are exact registry-checked `set_uid` candidates in this backend/dev bridge and are reported as not curated production mapping. The adapter writes no partial config when any character block is not ready. It does not query UI, persist right-panel state, run network refreshes, rebuild GCSIM, or change the patch stack. It uses account SQLite constellation rows only for the narrow talent-level normalization described below. Local no-network diagnostic on 2026-06-06 generated an account-backed Chasca/Ororon/Furina/Bennett full config from current-equipped artifacts and passed cached `2026-02-16` F12 C1 S1 through the active artifact as a backend compatibility smoke only; do not treat the smoke summary as DPS correctness. This bridge remains useful as a dev CLI/smoke path, not the Browser production team source.

The account-backed CLI also supports a backend end-to-end compatibility smoke: `python -m run_workspace.gcsim.account_prepared_config --run-abyss-smoke --dev-energy-override --format text`. It assembles account-prepared team blocks with the manual Chasca rotation shell, writes a temporary dev-only boosted-energy shell copy in the run dir, generates cached Abyss waves for the configured chamber/side, and runs the existing patched artifact runner with `-gtt-wave-scenario`. The boosted energy line is dev-only and must not be treated as product rotation truth. Future GCSIM browser/editor work needs direct rotation code input/editing, not only committed shell fixtures.

Production Browser config wiring now uses `run_workspace/gcsim/selected_team_config.py`. It consumes the current selected `TeamBuilderTeamState`/AppShell slot state and resolves account-owned data by stable ids such as `character_id` and selected/current weapon fingerprint. It must not infer GCSIM identity from localized names, and unlike the dev CLI bridge it must not choose deterministic fallback weapon candidates. Missing selected/current weapon, character/weapon/artifact-set GCSIM key, current artifact data/stats, talent/level/refinement data, unsupported Traveler, or rotation-shell issues produce structured not-ready reports. `run_workspace/gcsim/readiness_summary.py` turns those reports into grouped UI-independent text for Browser prepare/run failures. Normal Browser output is readiness-first and compact; the first compact UI pass shows a context bar, reserved rotation tabs, a run summary, and hidden-by-default Advanced/Debug raw details instead of a dominant issue/log wall. Browser `Check readiness` exposes the prepare/preflight path, while actual run attempts remain the product path for readiness blockers. `run_workspace/gcsim/settings.py` owns product energy mode: boosted energy is disabled by default and only injects/replaces `energy every interval=480,720 amount=100;` when `gcsim_boosted_energy_enabled` is true. The setting is exposed in the Account page under a compact GCSIM block and clears runtime Sim DPS results when changed. The dev CLI `--dev-energy-override` remains separate in `account_prepared_config.py`.

### First GCSIM Browser MVP UI contract

The first GCSIM UI should be a browser tab/page near the existing character/weapon and artifact browser areas, not an isolated popup and not a small TeamCard-only panel. The right panel remains the compact Run Workspace summary that receives Sim DPS / clear-time results.

Contracts:

- Consume the current runtime team composition from Run Workspace/right panel through `selected_team_config.py`; do not use localized display names or the old dev `team_names` bridge as Browser identity. Runtime results belong to typed Run Session state; widgets only display/command that state.
- Abyss mode has Team 1 / Team 2 tabs. Team 1 maps to first-half Abyss enemies, Team 2 maps to second-half Abyss enemies. DPS Dummy mode has one team tab.
- Show compact team readiness cards with character, weapon, artifact set summary, and ready/issues. Full build editing stays in the existing account/artifact UI.
- Provide GCSIM total-stats tooltip/report per character so users can compare GCSIM-computed totals with the app/right-panel totals.
- Show an Abyss target browser below the team: C1/C2/C3, side by active team, waves, enemy names, levels, HP, and resolved GCSIM target types.
- The existing solo/multi target toggle must control which targets are sent to GCSIM. Current generated wave policy remains `group_clear`; stack/rolling replacement is future work.
- Show temporary run defaults in the browser, for example iterations and boosted-energy status. Boosted energy is settings-controlled from Account -> GCSIM and disabled unless explicitly enabled; later these defaults can move to a fuller GCSIM settings section/control.
- Raw GCSIM rotation-code input is required in the MVP. A visual/button-based rotation builder can be added later, but must not replace direct code input.
- Current implemented Abyss run action is `Run selected chamber`: the active Team 1/Team 2 tab maps to Abyss side 1/2, the selected C1/C2/C3 button maps to `abyss_chamber`, the rotation editor text is used as the shell, and a Qt worker under `ui/gcsim_browser/run_worker.py` runs selected-runtime-team config generation plus generated wave backend path asynchronously. AppShell passes the current cached Abyss source-data identity already used by the Browser/right-panel preview (`period_start`, `floor`); the run worker must not fall back to backend smoke defaults such as `2026-02-16` when current UI source-data exists. Results include config/scenario paths, source identity, scenario waves/targets/total HP, observed duration, DPS summary, average total damage per sim run, warnings, failed action buckets, incomplete characters, grouped readiness summaries, and controlled error category in the GCSIM Browser Results panel. A selected-chamber result is converted into `RightPanelGcsimChamberResult`, stored in typed Run Session state, and replaces only the matching team/chamber/side row; compatible existing rows for other chambers on the same team/side are retained, and unrelated team/side rows are not overwritten. Diagnostic warning `abyss_preview_scenario_source_mismatch` is reserved for preview/run source identity drift.
- Current implemented DPS Dummy action reuses the selected Team 1 state and manual rotation shell, assembles config through the same selected-runtime-team adapter, and runs the active artifact without Abyss source identity or generated wave scenario. The report includes diagnostic energy mode, dummy target HP/resist/source when parseable from the shell/config, and average total damage per sim run wording. It deliberately does not create history, no-code rotation, right-panel persistence, or enemy/source defaults, and damage correctness remains unclaimed.
- Current implemented batch action is `Run 3 chambers`: it maps the active Team 1/Team 2 tab to side 1/2, uses the same current cached Abyss source identity and rotation editor text, then runs C1/C2/C3 sequentially in the same Qt worker. Do not parallelize those three GCSIM processes yet. The browser shows a compact batch report with per-chamber status, observed duration, DPS summary, average total damage per sim run, scenario total HP/waves/targets, warnings, and error category. The same batch result is converted into typed-session `RightPanelGcsimChamberResult` rows; the active team's right-panel Sim DPS cells show compact `clear time / DPS` text, the other team remains `not run`, and results are cleared on obvious input changes such as team/equipment/source/target-mode/rotation/energy-mode changes. Normal Run Save serializes these current Abyss session results into immutable History Snapshot `sim_dps` summaries. There is no separate auto-save after every simulation and no SQLite GCSIM archive. The current tooltip/report text that says `History persistence: disabled` is stale and should be replaced during the UI pass with wording that explains save-with-run-snapshot behavior.
- Future GCSIM run scheduler should treat the current sequential `Run 3 chambers` behavior as the safe MVP, then support bounded parallel chamber runs when the user's machine can handle them. It needs `max_workers`/auto mode, isolated `run_dir`/config/scenario/stdout/stderr per chamber, ordered C1/C2/C3 result aggregation, and cancellation/progress handling.
- Later GCSIM Browser/right-panel work should polish sim result tooltip visuals/details, expose the existing save-with-run-snapshot policy clearly, move temporary defaults into fuller settings when needed, and improve navigation between right-panel Sim DPS cells and Browser result details.
- First UI work should prioritize readiness/report/config/result visibility over visual polish.

Manual smoke checklist for the current backend-MVP:

- Ready selected team -> `Check readiness` produces a ready config/preflight report.
- Not-ready selected team -> run attempt shows readable readiness blockers.
- `Run selected chamber` -> the matching right-panel Sim DPS cell updates.
- `Run 3 chambers` -> all three matching right-panel Sim DPS cells update.
- Hover Sim DPS -> tooltip shows status, config/scenario paths, target identity, no-correctness wording, and correct save-with-run-snapshot behavior.
- Toggle Account/Data -> GCSIM boosted energy -> previous Sim DPS clears and the next run reports the new energy mode.
- DPS Dummy -> runs without Abyss source-data and shows energy/dummy target diagnostics.

## 8. Talent Levels

The original GCSIM v2.42.2 source inspection established the base-talent contract: it validates config talent levels as parser/base values in the inclusive range `1..10` (`pkg/core/player/character/character.go`). Account/HoYoLAB observed talent rows may include constellation-boosted displayed levels above 10, so displayed levels are not GCSIM-ready.

Pure helper `run_workspace/gcsim/config_talents.py` now prepares parser-safe levels before config output. It consumes the three active `skill_type=1` talents plus active constellation rows, considers only active C3/C5 (`pos in 3,5` and `is_actived=true`), extracts text inside HoYoLAB `<color=...>...</color>` markup, normalizes both colored references and talent names, and subtracts the +3 bonus only when a colored reference matches exactly one active talent. Unresolved active C3/C5 rows warn with `constellation_talent_bonus_not_resolved`; any level that remains above 10 after normalization is capped with `post_normalization_talent_level_capped_to_gcsim_range`. GCSIM output must never receive a talent level above 10, and unresolved/special cases are not silently treated as exact.

The account storage layer now persists minimal constellation source rows in `account_character_constellations` (`character_id`, `pos`, `name`, `effect`, `is_actived`) only so the talent helper can remove C3/C5 display bonuses. This is not a buff engine and not a static constellation-effect catalog. Production selected-team generation already uses deterministic `skill_id` ordering with a controlled warning; richer semantic talent-slot validation remains correctness polish, not a missing production wiring prerequisite.

## 9. Artifact / Weapon / Set Double-Counting Boundary

Artifact `add stats` for GCSIM should contain artifact main/sub stats only, normalized to GCSIM units.

Do not manually inject weapon passive effects, artifact set effects, resonance, or other conditional bonuses into `add stats` when GCSIM is expected to model those through its own character/weapon/set systems.

Project display effects/tooltips are UI/reference data and must not be used as GCSIM stat injection unless a later explicit design says otherwise.

## 10. Resource Budget / Multiple Simulations

The app may need to run up to six simulations for Abyss-related calculations. This can be CPU-heavy.

Before launching a batch, the app should estimate a safe resource budget:

- CPU logical/core count.
- Current CPU load if available.
- Reserved threads for system/UI responsiveness.
- Number of requested concurrent sims.
- Workers per sim.

The app should avoid launching multiple GCSIM jobs each with an aggressive default worker count. If resources are limited, queue simulations or reduce per-sim worker count.

Normal Auto mode must remain interactive through its reserved logical processor,
below-normal process priority, progress, and cancellation. Show an explicit
heavy-load warning only when the user selects an aggressive/max CPU budget that
removes the normal responsiveness reserve.

## 11. Result Handling / JSON Boundary

The implemented result boundary uses GCSIM JSON result files/objects as the
interchange format. `artifact_runner.py` tolerates omitted protobuf-default
fields and converts the output into a compact backend summary. Browser workers
add selection/scenario/readiness/error metadata, and successful Abyss rows are
converted into typed Run Session results. Normal Run Save then maps those rows
to immutable History Snapshot `sim_dps` summaries.

Current parsing/reporting extracts:

- sim DPS statistics;
- duration / clear-time statistics;
- total damage;
- warnings and failed actions;
- scenario identity, target mode, generated paths, and compact readiness/error
  diagnostics;
- rotation hash and enough team/chamber/side identity to invalidate or replace
  the correct runtime result.

Deeper target/character/element breakdowns, complete release engine hashes in
saved snapshots, and a dedicated result-details UI remain optional product
extensions rather than backend-MVP blockers.

The parser must tolerate missing default/zero fields because GCSIM results are protobuf JSON where default values may be omitted.

If a later Go API/shared-library/native result object is designed, it should still preserve a JSON/history-friendly result representation.

## 12. Suggested Implementation Phases

Historical phases 1-10 are complete for the current Abyss Browser MVP: engine
store/update, build artifact, GTT capability marker, config generation, selected
runtime-team adapter, `group_clear` waves, current Abyss scenarios, JSON result
parsing, typed session writeback, right-panel summaries, and save-with-run-
snapshot History attachment all exist.

Current implementation sequence:

1. GCSIM Browser UI pass inside `ui/gcsim_browser/`: replace placeholders,
   improve team/target/readiness/result presentation, and correct stale History
   wording without refactoring AppShell ownership.
2. Rotation product pass: retain raw code, add readable parsing/presets, and
   investigate published gcsim.app config discovery by exact stable
   four-character roster. Collect/cache/parse every matching rotation and let
   the user choose; source/API, attribution, freshness, parser safety, and
   duplicates require their own task. Then decide whether a constrained no-code
   builder is worth maintaining.
3. Run orchestration pass: progress, cancellation, run-artifact/debug retention
   controls, and measured optional bounded parallelism.
4. DPS Dummy state pass: attach successful results to typed DPS Dummy session
   and immutable snapshot data, separate from factual DPS.
5. Release pass: build and validate the bundled known-good executable, package
   it outside user-writable engine retention, and add dependency-aware advanced
   update UI.
6. Correctness/coverage pass: maintain real rotation smokes, audit current
   registry gaps, and add explicit mapping overrides only for proven exceptions.

Independent backend-only optimizer track while PvP/AppShell work continues:

- Production identity is `gtt_gcsim_optimizer_go_v1`, implemented as a
  standalone `native/gcsim_optimizer` module plus the smallest versioned engine
  adapter needed for compact formula/support evidence and ordinary simulation.
- GOB-1 through GOB-7 pass. GOB-8 transactionally activated
  `gcsim-v2.42.2-gob8-20260830b` with compact-IR capability while retaining the
  previous engine for rollback. Existing real
  captures produced exact stochastic parity, a compiled 483-artifact evaluator
  and a clean Go FGBS real-account result in 64.39 s, with zero engine/n=1000/UI
  calls during GOB-3E through GOB-5.
- GOB-6 migration cleanup passes: replaced Python Selected/FGBS/stochastic and
  superseded strategies were removed after a fresh reachability scan. No Python
  fallback remains.
- GOB-7 staged the 24 formula candidates plus Current through common n=128,
  retained at most seven mandatory/measured finalists, and completed common
  n=1000 in 170.67 seconds. GOB-8 UI/adapter is functionally accepted: after
  fixing per-seed duration aggregation, the actual restarted AppShell Selected
  button returned 148910.10 DPS and twenty unique IDs. Full UI progress took
  about 191.15 seconds, so the 190-second performance target remains narrowly
  missed and the temporary working kill is 360 seconds.
- GOB-9 final cleanup passed: one Selected Go backend and one consolidated
  engine patch remain, with transactional update and rollback proof.
- Keep UI/AppShell changes narrow. A global AppShell refactor remains out of
  scope for optimizer work.
- Follow `GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md` for sequencing and
  `GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json` for every deletion
  candidate.

## 13. Historical Backend Implementation Record

The original first-task direction was completed. The detailed record below is
kept for engine/patch debugging and release validation; it is not the current
task queue. Use the authoritative status and current implementation sequence at
the top of this file for new work.

Current implementation state:

- Initial isolated backend prototype exists in `run_workspace/gcsim/engine_store.py`.
- It models a local engine store with `engines/`, `staging/`, `failed/`, an `active_engine.json` pointer, and per-engine `gtt_engine_manifest.json`.
- `GcsimEngineStore.prepare_engine_update(...)` copies a source-like tree into staging, applies a replaceable `PatchBackend`, runs an optional smoke-check callable, writes the manifest, then activates the new engine only after all steps pass.
- The default `OverlayPatchBackend` is test-only/prototype-friendly: it copies files from a patch-stack directory over the staged source. It proves transaction boundaries without requiring real GCSIM source, network, Go, or `git apply`.
- Production-oriented patch backend exists in `run_workspace/gcsim/patch_backends.py` as `GitApplyPatchBackend`. It discovers ordered `.patch` files from the patch stack, runs `git apply --check`, then runs `git apply`. Git subprocesses set `GIT_CEILING_DIRECTORIES` so prepared engine trees under generated `data/gcsim/...` paths are patched as isolated source folders instead of being interpreted through the parent GTT repository. Missing git, check failure, and apply failure are controlled patch failures; the engine store preserves the failed staging folder and keeps the previous active engine.
- Backend/dev update command supports explicit patch backend selection:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git`.
  Overlay remains the conservative default. If the default `run_workspace/gcsim/patch_stack/` directory is absent or a selected patch stack has no `.patch` files, the git backend reports a no-patch success and does not invoke git.
- Optional build artifact flag exists:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git --build-artifact`.
  It requires `windows/amd64`, builds the staged source with its generated
  manifest, and checks the executable version/marker. Activation additionally
  requires the full application compatibility gate described above; a build or
  development runtime probe alone is insufficient.
- The active patch stack contains exactly one file:
  `run_workspace/gcsim/patch_stack/0001-gtt-engine-adapter-v245.patch`, SHA-256
  `22f097feee2514c03a441536175d7352c516bc3deadca9cc9de09f1533e2a04b`.
  It contains only the current engine-owned boundary: `-gtt-info`, trace and
  compact equation/source provenance used by FAST, and structured
  `-gtt-wave-scenario` group-clear scheduling. Artifact enumeration, search,
  stochastic policy and UI remain outside the engine patch.
- The consolidated patch reproduced the accepted 4,314-file source tree after
  clean check/apply. Transactional update built and activated
  `gcsim-v2.42.2-gob9-consolidated-20260831`; rollback to
  `gcsim-v2.42.2-gob8-20260830b` and restoration both passed. Its executable
  SHA-256 is `bce061db71f2ebc7171ba19d192a6c0522358edb68e821b25a7649406f86fe03`.
- GOB-10's v2.42.2 engine remains installed as the rollback target:
  `gcsim-v2.42.2-gob10-perf-20260901`, executable SHA-256
  `00834023d64f3853723ee2ca28af6b9bd5fbaacb1cbda4cf7e11dd44a45ff99a`.
- The 2026-09-01 patch audit removed four obsolete areas before adapting to
  v2.45.0: the old stat-response/effect-observation modes, the unrelated
  upstream `substatOptim` ER behavior change, the config-comment
  `gtt_wave_prototype`, and the generated source-manifest snapshot that pinned
  thousands of source rows to one release. The manifest is now regenerated
  from the exact target source during the transactional build. Patch size fell
  from about 3.10 MB to about 0.67 MB. Legacy response/effect/prototype
  capabilities are absent from the built artifact.
- A clean application of the reduced v2.42.2 patch to pristine v2.45.0 exposed
  six changed upstream seams. Three were harmless context/import drift; three
  required explicit preservation of new upstream behavior: character model
  removal, cooldown/reaction-bonus logging changes, and generalized direct
  Lunar Reaction damage. Three-way application was used only to diagnose the
  differences, never as activation proof. The final v2.45 patch itself passes a
  clean `git apply --check` and apply.
- v2.45.0 also exposed a generic source-generator defect: when a modifier began
  with replayable frozen inputs and later reached a live conditional input, the
  correct opaque fallback left unused generated declarations. The generator now
  stages declarations and emits them only after the whole expression is proven
  replayable; a synthetic regression pins this fail-closed behavior. This is
  generic boundary handling, not Stellar Conduct hardcoding.
- Transactional production activation passed for
  `gcsim-v2.45.0-clean-adapter-20260901`. Executable SHA-256 is
  `4ce399e8fd0fae48ac8812fbe8e3fcd746b5e74c84554228fa660ef944cfb857`;
  source-manifest body SHA-256 is
  `40b6b0d5d789d9b8f7481c03360fbaca75fa90d40f8babe6c2208d4910685029`.
  The production executable is byte-identical to the isolated validated build.
  Current-team one-seed compact output retained the exact v2.42.2 topology
  (duration 66950 ms, 42512 nodes, 377 channels, 25 opaque boundaries, topology
  SHA-256 `0d670be4f6edaf75a9137da778d8bf8236ae3b19d4e406224839a0416e8ff15b`),
  and ordinary simulation plus a real two-wave structured scenario passed.
- That parity fixture does not exercise Lunar Crystallize or Stellar Conduct.
  The v2.45 build proves that new/unknown conditional source mechanics stop at
  a declared opaque boundary instead of breaking generation, but a team that
  materially uses either new mechanic still needs its own semantic fixture
  before formula completeness may be claimed for that team.
- The removed config-comment wave prototype is historical evidence only and is
  not accepted runtime. Sequential waves are available solely through the
  explicit structured `-gtt-wave-scenario` payload below.
- The historical structured-wave patch introduced the now-consolidated
  `-gtt-wave-scenario scenario.json` flag and
  `simulator.Options.GTTWaveScenarioPath`. Empty path is a no-op so vanilla
  runs remain unchanged. Explicit payload errors are fatal and must not
  silently fall back to vanilla.
- Payload schema v1 is intentionally minimal and app-owned: `schema_version=1`, `spawn_policy="group_clear"`, and `waves[].targets[]` with required `level`, `type`, and explicit `hp`. The patch builds each enemy through GCSIM's target type/profile path (`enemy.ConfigureTarget`), so `type` owns monster stats/resists and the payload HP is applied as an explicit override after the profile is configured. Optional `pos`/`radius` remain explicit overrides only; normal Abyss bridge output does not write them. The first payload wave replaces parsed config targets; remaining waves are stored on `ActionList` and deep-copied per simulation iteration. Current implemented `group_clear` behavior is sequential groups: when all enemies in the current group are dead, the scheduler spawns the next payload group inside the same iteration. If a wave contains multiple targets, killing one target does not spawn the next wave; the whole current group must be cleared first, and then the next wave spawns as a whole group. This still does not implement key mapping, real Abyss 3+3+3 policy, rolling replacement, stack replacement, or UI integration.
- Future DPS mode contract: single-target DPS should use the selected single target and then the next single target. This should later be tied to the existing fact-DPS single-target/multi-target setting so fact DPS and GCSIM DPS describe the same target model. Multi-target DPS should eventually expose settings-backed modes: `sequential waves` (current implemented group-clear behavior) and `stack/rolling replacement` (future, not implemented), where enemies from the next wave may be added to replace dead enemies from the current group. Do not implement stack mode until the in-game behavior/policy is confirmed.
- Current `-gtt-info` for a built patched artifact should report
  `gtt_engine=true`, capability `gtt_wave_scenario_payload`,
  `sequential_waves=true`, and the upstream version when available. The
  `gtt_patch_version` string is cumulative diagnostic metadata and may advance
  when later optimizer patches are applied; consumers must not require the old
  exact value `gtt-wave-scenario-v1`. This is a capability signal, not a final
  Abyss-correctness claim.
- Built artifact metadata is recorded in the manifest/report: artifact path, filename, sha256, build status, artifact runtime check status, Go version/OS/arch, build command/stdout/stderr, artifact version command/stdout/stderr, GTT marker status/version/capabilities/stdout/stderr, `artifact_kind=local_build`, and `shipped_fallback_status=resolver_available_not_bundled`. `runtime_ready=true` means either the legacy no-build `--probe-runtime` passed or, when `--build-artifact` is requested, the built executable passed the artifact checks. If `--build-artifact` is used with a non-empty `.patch` stack, the built executable must also pass `build/gtt-gcsim.exe -gtt-info`; missing, nonzero, invalid JSON, missing patch version, or missing `gtt_engine_marker` capability keeps the previous active engine.
- Minimal artifact runner exists in `run_workspace/gcsim/artifact_runner.py`, with a dev CLI at:
  `python -m run_workspace.gcsim.run_smoke --config path --gtt-wave-scenario scenario.json --format text`.
  It resolves the active engine from `GcsimEngineStore`, locates the built artifact recorded in the manifest, writes caller-provided config text to a run directory, executes `gtt-gcsim.exe -gtt-wave-scenario scenario.json -c config.txt -out result.json` when a scenario is supplied, captures stdout/stderr/return code, enforces a timeout, and parses only a tolerant summary from uncompressed JSON results: schema version, sim version, `statistics.dps.mean`, `statistics.duration.mean`, `statistics.total_damage.mean`, warnings, failed actions, and incomplete characters. It intentionally does not generate account/team configs, map keys, final Abyss wave policies, or integrate with UI.
- Shipped fallback artifact resolver exists in `run_workspace/gcsim/shipped_artifact.py`. The default candidate path is `run_workspace/gcsim/shipped/gtt-gcsim.exe`, but no production binary is bundled yet. The resolver reports explicit statuses (`disabled`, `candidate_missing`, `candidate_ready`, `candidate_not_file`, `candidate_invalid_path`) and requires an actual file for `candidate_ready`. `run_active_gcsim_artifact(...)` has explicit opt-in fallback support: the active built artifact remains first priority, and a ready shipped fallback is used only when the active artifact is unavailable. Run results now include `artifact_source`, `active_artifact_status`, and `shipped_fallback_status` diagnostics. Shipped binary marker/capability validation is not implemented yet and remains release-process work.
- A narrow backend Abyss-to-GTT-wave bridge now exists in `run_workspace/gcsim/abyss_wave_scenario.py`. It consumes typed `AbyssFloorSourceData`, selects one chamber/side, audits rows grouped by source waves, expands `enemy_count` into individual schema-v1 targets, and can produce a `group_clear` payload dict plus a separate audit/result object. Payload generation is ready only when required source HP/level fields are present and each enemy resolves to a compatible valid GCSIM target type. GTT writes explicit Abyss HP into the payload, so exact GCSIM HP/variant identity is not required at this stage; for example, `Grounded Geoshroom -> groundedgeoshroom` is acceptable when it avoids `unknown target type` and preserves usable GCSIM enemy stats/resists. Nanoka monster id is the preferred strong identity for manual overrides when present, but it is not the only allowed identity: Fandom enemy page URL/page title/name candidates must remain valid fallback identities, and enemy-type fallback must be independent from HP source fallback. HP may come from Nanoka while GCSIM type resolves through Fandom/name identity, or HP may come from Fandom fallback while type resolves through Nanoka/name identity. Managed Snap Monster title cache support exists in `run_workspace/gcsim/snap_monster_titles.py` as a last-resort enemy `Name -> Title` fallback after manual overrides, normal registry exact/base matching, and small aliases fail. The normal app-style contract is cache-first: primary matching runs without Snap; if rows remain unresolved, GTT may check the managed cached `data/cache/gcsim/snap_metadata/Monster.json`; if cached `Name -> Title` matching and cached title-containing-target matching are still insufficient, the cache may be refreshed from the official online Snap.Metadata file `https://github.com/wangdage12/Snap.Metadata/blob/main/Genshin/EN/Monster.json` and then rechecked. No Git install or Snap.Metadata repository checkout is required. The refresh step reads the single online `Monster.json` over HTTPS and persists only the managed cache file plus a small sidecar metadata file. A local file path or direct URL remains supported only as an explicit dev/offline/debug input, not as the normal app contract. Only `Name` and `Title` are read; Snap metadata must not be used as HP/stat/resist/wave/count truth or source-data replacement. Duplicate normalized Snap `Name` records with different `Title` values are ambiguous instead of silently chosen. If the Snap `Title` still does not exact/base-match the registry, the final last-resort matcher may resolve a unique GCSIM target whose key contains the full normalized Snap title (`snap_title_contains_target`); multiple containing targets remain ambiguous. This covers cases such as `Tenebrous Papilla: Type II -> Tenebrous Papilla -> tenebrouspapillatypei` without turning arbitrary display-name fuzziness into production truth. Missing Nanoka id alone is not a blocker; the blocker is missing any safe explicit or automatic compatible GCSIM target type. The bridge must not infer production-ready GCSIM type keys from arbitrary fuzzy/display-name similarity.
- Dev CLI `python -m run_workspace.gcsim.abyss_wave_scenario_smoke` loads either the current cached Abyss period or an explicit cached period/floor, builds the provisional schema-v1 scenario JSON for a selected chamber/side, and can optionally pass that scenario to the existing active artifact runner with a caller-provided config. It accepts explicit override mapping JSON, `--gcsim-enemy-registry-source path` for automatic known-target matching, managed Snap cache flags `--use-cached-snap-monster-json`, `--refresh-snap-monster-json-if-needed`, and optional `--snap-monster-cache-path`. Direct `--snap-monster-json PATH_OR_URL` and `--use-default-remote-snap-monster-json` remain dev/debug overrides and are mutually exclusive with the managed flow. Remote Snap refresh failures, invalid JSON, and invalid shape are controlled input errors. Missing cache/source fields or missing/ambiguous enemy type resolution prints the audit and exits nonzero without writing/running a misleading scenario. Backend reports expose progress steps such as `matching_enemy_names_primary`, `checking_cached_snap_titles`, `refreshing_snap_metadata`, `rechecking_snap_titles_after_refresh`, `building_abyss_wave_scenario`, and `running_gcsim_artifact`. Coverage reports also include `timing_seconds` diagnostics for primary matching, cached Snap loading/matching, remote refresh/indexing when it happens, refreshed matching, and total report time. The first forced Snap fallback can be noticeably slower because it refreshes the managed runtime cache from the online `Monster.json`; later runs should use the cached file and avoid network. Artifact runs that supply `gtt_wave_scenario` now preflight-check the selected artifact with `-gtt-info` before sim execution. The selected active or shipped fallback artifact must report capability `gtt_wave_scenario_payload`; `gtt_patch_version` is cumulative diagnostic metadata and is not an exact compatibility gate. Stale artifacts fail with `artifact_wave_scenario_contract_mismatch`, observed/required capability diagnostics, and a rebuild-required message before sim execution. Runs without a wave scenario keep the previous behavior. Stable backend/dev smoke case catalog exists at `run_workspace/gcsim/smoke_cases.py`, with committed manual config fixture `run_workspace/gcsim/smoke_fixtures/manual_config_minimal.txt`. Named case `abyss_2026_04_16_f12_c3_s2_manual_config` proves manual GCSIM config plus generated cached Abyss wave scenario, managed cache-first Snap matching, and artifact preflight/run parsing without depending on an ad-hoc runtime run directory config. Latest manual case run passed through the active artifact: scenario generation used managed Snap cache hit (`remote_not_needed`), resolved `Tenebrous Papilla: Type II` by `snap_title_contains_target` to `tenebrouspapillatypei`, built one wave / one target, and artifact preflight observed `gtt-wave-scenario-v1` with `gtt_wave_scenario_payload`. Parsed run summary stayed smoke-only: duration_mean `0.03333333333333333`, dps_mean `0.0`, total_damage_mean `0.0`; do not treat this as DPS correctness. Future UI loader messages should surface these backend steps so enemy matching, Snap refresh, scenario build, and optional artifact run do not look frozen. This remains backend/dev-only and still does not generate account/team configs, broad key mappings, final Abyss wave policy, or UI state.
- Additional manual/dev fixture `run_workspace/gcsim/smoke_fixtures/manual_config_neuv_furina_lauma_xiangling.txt` stores a hand-written Neuvillette/Furina/Lauma/Xiangling config for backend compatibility diagnostics only. It is not generated account config and not benchmark truth. Its manual `target` lines are placeholders; when used through `abyss_wave_scenario_smoke`, generated `-gtt-wave-scenario` JSON remains the enemy/wave/HP/type source of truth. A real local run on 2026-06-05 for cached period `2026-05-16` F12 C2 S1 built three exact-name scenario waves (`fatuielectrocicinmage`, `ruindrakeearthguard`, `primogeovishap`) and passed artifact preflight. This smoke exposed a patched GCSIM runtime panic in `pkg/stats/damage/damage.go`: dynamically spawned wave enemies can receive sparse target keys after gadgets, while cumulative damage buckets were sized by current enemy count and indexed by `targetKey-1`. Patch-stack fix `0004-gtt-dynamic-wave-stats.patch` makes damage cumulative buckets grow by resolved enemy index and lets aura aggregation grow for dynamic `result.Enemies`. After rebuilding the active artifact in-place on 2026-06-05, the same 3-wave smoke passed with artifact preflight intact. The same config also still passes without `-gtt-wave-scenario`. No DPS correctness claim.
- Enemy type mapping JSON supports explicit records with `source_kind`, `source_id`, `gcsim_type`, diagnostic `source_name`, and optional notes/warnings. The previous `enemy_types_by_nanoka_monster_id` shape still loads for dev compatibility, but explicit records are now the first-priority override/exception layer, not a full production enemy database. Duplicate records for the same identity are reported as ambiguous and are not silently chosen.
- Backend/dev GCSIM enemy type registry matcher exists in `run_workspace/gcsim/enemy_type_registry.py`. It parses known target type keys from local prepared GCSIM `pkg/shortcut/enemies_gen.go` and can resolve Abyss Nanoka/Fandom name candidates by exact normalized name, compatible/base-name rules that strip controlled variant tokens, and small explicit aliases for known exceptions. Automatic matching runs only after manual overrides fail. Missing or ambiguous compatible matches are reported instead of guessed, and fuzzy/display-name similarity is not production truth. Full production validation still depends on using a current prepared GCSIM source registry and later real-engine checks.
- Dev coverage checker `python -m run_workspace.gcsim.abyss_enemy_type_mapping_report --gcsim-enemy-registry-source path --scan-cache-dir data/cache/abyss/source_data --format text` verifies cached Abyss source-data against optional overrides plus the GCSIM enemy type registry without Abyss network refresh, GCSIM runs, or UI imports. It accepts repeated `--cache-file`, single `--cache-dir --period-start --floor`, or bulk `--scan-cache-dir` over `**/floor_*.json`; `--period-start` and `--floor` filter bulk scans. It accepts the same managed Snap cache flags as the smoke CLI. Network is not used when primary registry matching resolves all rows, and is not used when cached Snap title fallback resolves the remaining rows. The online Snap `Monster.json` refresh is a last step only when explicitly enabled and cache results are missing, invalid, or insufficient. The report records `snap_cache`, refresh/cache status, source kind, progress `steps`, and Snap fallback counts. Direct `--snap-monster-json PATH_OR_URL` and `--use-default-remote-snap-monster-json` remain dev/debug overrides. Snap fallback resolutions are counted separately as `snap_title_fallback`, and final containing-target resolutions as `snap_title_contains_target`, so exact/base/alias coverage remains visible. It reports cache file count, total rows, resolution counts by method (`manual_mapping`, `exact_normalized_name`, `compatible_base_name`, `manual_alias`, optional `snap_title_fallback`/`snap_title_contains_target`), counts by identity/name source, missing/ambiguous mappings, HP-present/type-missing rows, type-present/HP-missing rows, compact unresolved/ambiguous text rows, JSON resolved rows with selected type/method, and unresolved rows with all available identities. Current real-code-path diagnostic over the 8 cached source files / 96 rows resolved 88 exact, 7 `snap_title_fallback`, 1 `snap_title_contains_target`, 0 missing, and 0 ambiguous after Snap title fallback. Use it to validate matcher behavior on existing caches for both normal Nanoka-backed data and forced Fandom fallback/Fandom-only caches. Missing/ambiguous rows should drive small matcher or alias fixes, not a full hand-written enemy mapping table. Full production enemy type coverage remains future work.
- Backend config readiness audit now exists in `run_workspace/gcsim/config_readiness.py`. It is adapter-free and accepts lightweight prepared team inputs instead of UI widgets or SQLite rows directly. It audits explicit GCSIM mapping refs for characters, weapons, and artifact sets; current/max character level; equipped weapon level/refinement; artifact completeness and normalized artifact add-stats via the existing stat-normalization layer; and account-observed talent levels only when normal/skill/burst order is confirmed. Missing or display-name-only mappings report `missing_mapping`, ambiguous mappings report `ambiguous_mapping`, Traveler remains `unsupported_traveler`, and missing source fields such as level/weapon/artifacts/talents report controlled readiness statuses. This still does not generate config text, create real project-id-to-GCSIM mapping data/reports, query account/equipment storage, run artifacts, or wire UI.
- Backend GCSIM key-mapping report foundation now exists in `run_workspace/gcsim/key_mapping.py`. It defines explicit character, weapon, and artifact-set mapping records with project id/set uid, diagnostic canonical name, `gcsim_key`, source kind/name, readiness status, warnings, and optional ambiguous candidates. It converts ready records into `config_readiness.GcsimMappingRef` values and reports counts/missing/ambiguous entries by entity type. The current boundary is seed/fixture-oriented (`curated`, `curated_test_fixture`, `dev_fixture`, `test_fixture`) because no reliable committed production `project id -> GCSIM key` source has been identified. Display-name, localized-name, and normalized-name-guess sources are rejected as not ready; Traveler remains explicitly unsupported/deferred. This still does not create production mapping data, generate config text, query account/equipment storage, run artifacts, or wire UI.
- Tiny committed GCSIM key-mapping dev seed now exists at `run_workspace/gcsim/mapping_seeds/gcsim_key_mapping_seed_v1.json`, with a report CLI at `python -m run_workspace.gcsim.key_mapping_report --format text|json`. The default report keeps `production_mapping_data_missing` because the seed is intentionally tiny and not production-complete. Current records cover only explicit dev/fixture-backed Mona, Favonius Codex, and Noblesse Oblige keys; do not extrapolate from these names or slugs, and do not treat this as full character/weapon/artifact-set mapping coverage. Full mapping source generation/curation remains future work.
- Backend/dev entity registry coverage report has been added in `run_workspace/gcsim/entity_key_readiness_report.py`, with CLI `python -m run_workspace.gcsim.entity_key_readiness_report --format text|json`. It parses local prepared GCSIM shortcut sources for accepted character, weapon, and artifact set keys, prefers explicit seed overrides, then reports exact normalized candidates, conservative contiguous-name-span candidates, missing rows, ambiguous rows, and unsupported Traveler/Traveler variants. Default local diagnostics read existing HoYoWiki character/weapon stats caches plus the artifact set static seed; HoYoWiki `entry_page_id` identities are flagged as diagnostic and are not treated as the missing production game-id mapping owner. This report is not an account SQLite mapper: its character names are local HoYoWiki cache/catalog names, not localized `account_characters.name` values. Exact and contiguous-span candidates are not committed curated production mappings. Local diagnostic on 2026-06-05 over available caches after span fallback reported 414 entities total: characters 102 ready / 15 missing / 7 unsupported Traveler / 0 ambiguous, weapons 225 ready / 6 missing / 0 ambiguous, artifact sets 58 ready / 1 missing / 0 ambiguous. Match methods were 382 `exact_normalized_name`, 2 `contiguous_name_span`, 1 `explicit_seed`, 22 missing, and 7 unsupported Traveler. Current-registry gaps remain controlled missing and should later surface as user-facing warnings such as "GCSIM implementation is missing for this character/weapon/set; replace it or update GCSIM source." This still does not generate config text, query account/equipment storage, run artifacts, or wire UI.
- Account SQLite sync stores account-owned GCSIM key enrichment for
  `account_characters` and `account_weapon_observed_stacks`: English HoYoWiki
  `catalog_english_name`, resolved key, status, and method. The resolver loads
  local GCSIM character/weapon shortcut keys once per sync and then does
  in-memory matching. Local backfill on 2026-06-05 updated `data/artifacts.db` in
  about 1.1s: 65 account characters and 64 observed weapon stacks were `ready`,
  7 characters and 2 weapon stacks were current-registry `missing`, and account
  Traveler stayed `unsupported_traveler`. Known current-GCSIM-registry missing
  account rows are expected gaps, not account mapper failures: characters
  `10000100` Kachina, `10000110` Iansan, `10000113` Ifa, `10000123` Durin,
  `10000124` Jahoda, `10000127` Illuga, and `10000130` Linnea; weapon stacks
  `12432` Flame-Forged Insight and `15516` Golden Frostbound Oath. Account
  Traveler `10000007` remains `unsupported_traveler` because variant selection is
  still deferred. These counts are local-account diagnostics, not global
  coverage. This still does not generate configs or solve artifact-set
  mapping/current-build selection.
- GCSIM level text helper has been added in `run_workspace/gcsim/config_level.py`. It formats future config levels from account `level` plus optional `promote_level`: `80,5 -> 80/80`, `80,6 -> 80/90`, `70,4 -> 70/70`, `70,5 -> 70/80`, missing promote on breakpoint levels assumes after ascension with a warning, and final/special caps use `90/90`, `95/95`, and `100/100`. Missing level returns controlled `missing_level`.
- Backend character config block builder has been added in `run_workspace/gcsim/config_blocks.py`. It renders a single prepared character/equipment block from explicit mapping refs, level helper data, constellation/talents, weapon data, artifact set counts, and artifact-snapshot-only normalized `add stats`. Not-ready inputs return issues and no partial config text. This still does not generate full configs, create mappings, query account/UI storage, run artifacts, or wire UI.
- Backend/dev full-config assembler has been added in `run_workspace/gcsim/config_assembly.py`, with shell-only rotation fixture `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt`. The fixture preserves Chasca/Ororon/Furina/Bennett options/energy/active/script plus a placeholder target, while generated character blocks and generated `-gtt-wave-scenario` remain the account/team and enemy truth sources. Explicit prepared-input adapter and CLI bridge have been added in `run_workspace/gcsim/prepared_config_adapter.py`; default synthetic fixture `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json` can generate four ready blocks and assemble a full config only when all prepared data is ready. Account SQLite backend/dev bridge has been added in `run_workspace/gcsim/account_prepared_config.py`; it reads real account character rows and ready stored character/weapon GCSIM keys, uses current-equipped weapons when available, reports deterministic dev weapon candidates when not, normalizes displayed talent levels through `run_workspace/gcsim/config_talents.py`, uses current-equipped artifact owner rows plus artifact main/sub stat totals when available, and can run an end-to-end account-prepared + manual shell + generated Abyss wave compatibility smoke with dev-only boosted energy. Missing/incomplete current artifacts stay controlled not-ready, not silent synthetic fallback. Browser production wiring now uses `run_workspace/gcsim/selected_team_config.py`: it consumes selected TeamBuilder/AppShell state, resolves account data by stable ids, never chooses dev fallback weapons, uses Account/GCSIM settings-controlled boosted energy, feeds grouped readiness summaries through `run_workspace/gcsim/readiness_summary.py`, writes typed-session right-panel Sim DPS rows for Abyss selected-chamber and 3-chamber Browser runs, includes current Abyss results in normal Run Save snapshots, and reports DPS Dummy target/energy diagnostics without claiming damage correctness. `account_prepared_config.py` remains a dev CLI/smoke bridge.
- Tests in `tests/run_workspace/gcsim/test_gcsim_engine_store.py` pin success activation, patch failure rollback, smoke failure rollback, manifest metadata, and old-active availability.
- Official GitHub source acquisition exists in `run_workspace/gcsim/source_acquisition.py`. It resolves official `genshinsim/gcsim` releases through the GitHub API, downloads the release source zip, extracts the single top-level source tree into `data/gcsim/sources/`, and rejects unsafe/corrupt archives.
- Backend/dev update command exists at `python -m run_workspace.gcsim.engine_update --release latest`. It downloads official source, calls `GcsimEngineStore.prepare_engine_update(...)`, applies the selected replaceable patch backend, runs a source-layout smoke check for `go.mod`, `cmd/gcsim/main.go`, `pkg/simulator`, and `pkg/model`, writes source/patch/check metadata into the manifest, and activates only on success.
- Optional runtime probe flag exists: `python -m run_workspace.gcsim.engine_update --release latest --probe-runtime`. It first checks `go version`, requires `windows/amd64`, then runs `go run ./cmd/gcsim -version` from the prepared source tree with a timeout. If Go is missing, wrong-arch, times out, or exits nonzero, the staged engine is not activated and the previous active engine remains active.
- Go subprocesses launched by this backend use project-local cache/bin directories under `.go/` via `GOMODCACHE`, `GOCACHE`, and `GOBIN`; `.go/` is ignored. Investigation on 2026-06-11 found `.go/build-cache` can grow to about `4.94 GB` after repeated GCSIM builds/probes, while `.go/pkg/mod` was only about `53 MB`. `engine_update` now deletes rebuildable `.go/build-cache` after a successful `--probe-runtime` or `--build-artifact` unless `--keep-go-build-cache` is passed; module cache stays.
- Engine/source runtime data is local/generated and ignored under `data/gcsim/`. Investigation on 2026-06-11 found repeated successful/failed full engine copies were the main `data/gcsim` growth source: `data/gcsim/engines` was about `1.71 GB`, while `data/gcsim/runs` was only about `6.6 MB`. Generated engine-store retention now keeps active + one previous successful engine plus one latest failed engine and prunes older generated/staging folders. Manual cleanup/dry-run command: `python -m run_workspace.gcsim.cleanup`; pass `--apply` to delete. The command bounds `runs`, optimizer ordinary-screen `farming-runs`, and two-stage `optimizer-runs` independently, keeping at most 50 recent directories and 256 MB in each root by default. Successful optimizer screens remove their default-owned run directory after typed summary extraction, and two-stage optimizer sessions remove their reproducible private executable copy after process completion. Persistent optimizer evidence under `data/cache/gcsim_optimizer` is separately auto-bounded to 20,000 JSON entries and 256 MiB, with a full retention scan at most once per five minutes and stale atomic `.tmp` cleanup after one hour; the cleanup CLI reports and applies this same policy.
- Default check status remains source-layout only and records `runtime_ready=false` / `runtime_check_status=not_requested`. With `--probe-runtime`, a successful no-build probe records `runtime_ready=true`, `runtime_check_status=runtime_probe_passed`, `go_version`, `go_os`, `go_arch`, and truncated probe stdout/stderr metadata. With `--build-artifact`, the preferred runtime check is the built executable, not `go run`.
- Tests in `tests/run_workspace/gcsim/test_gcsim_patch_backends.py` pin git backend ordered patch success, parent-repo discovery isolation, missing git, patch check failure, patch apply failure, empty patch stack success, and previous-active preservation. Tests in `tests/run_workspace/gcsim/test_gcsim_engine_update.py` pin fake official-source acquisition, download failure, corrupt archive failure, layout-smoke failure, manifest metadata, old-active preservation, Go-missing, wrong-arch, nonzero probe, timeout, default no-probe behavior, successful fake runtime-ready activation, git patch backend plus runtime probe together, successful fake build artifact activation, Go missing/wrong arch/build failure/artifact version failure rollback, artifact sha256 metadata, GTT marker success activation, and GTT marker failure rollback.
- A real local validation command succeeded on 2026-06-04:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git --probe-runtime --build-artifact --format text`.
  After the structured payload patch, it built official upstream `v2.42.2`, activated engine `gcsim-v2.42.2-20260604175430`, produced `build/gtt-gcsim.exe` with sha256 `c06aa07af8924b3bafb7ad9097bc3e5e39f9570e99958dd43cd20c3a760b6921`, and `-gtt-info` returned `gtt_patch_version=gtt-wave-scenario-v1` plus `gtt_wave_scheduler_prototype` and `gtt_wave_scenario_payload` with `sequential_waves=true`.
- The current verified activation is resolved from
  `data/gcsim/engines/active_engine.json`, rather than a handoff-pinned generated
  directory. The 2026-07-29 activation had `patch_count=7`: patch 0005 adds
  explicit `optimize_er`, patch 0006 adds paired stat-response v2, and patch 0007
  adds paired set-response v1. GTT theoretical requests pin
  `optimize_er=0;fine_tune=0` while retaining fixed KQM-standard rolls.
- A real local sequential-wave prototype smoke also succeeded on 2026-06-04 through `run_smoke`. The smoke used `iteration=1`, `duration=10`, a single finite-HP target, Bennett, and `kill_target(...)` sysfunc calls so the observable is duration rather than damage. Without the GTT directive, the sim ended after the first killed target with `duration_mean=0.0333333`. With `# gtt_wave_prototype duplicate_first_target=1`, the patched engine spawned one more copy of the first target and continued to `duration_mean=1.03333`. This proves continuation/spawn inside one iteration, but not real Abyss wave modeling.
- A real local structured payload smoke also succeeded on 2026-06-04 through `run_smoke --gtt-wave-scenario scenario.json`. With the same simple config and a two-wave `group_clear` payload, no-payload duration remained `0.0333333`, while payload duration was `1.03333`. A bad payload with `spawn_policy="rolling"` failed clearly with `unsupported spawn_policy "rolling"; expected "group_clear"` instead of silently falling back to vanilla.
- Engine/config/scenario/result backend preparation is complete for the current
  Abyss Browser MVP. Remaining engine-side work is release packaging/validation
  of the shipped binary plus targeted patch maintenance when a real regression
  or new wave policy requires it. Do not reopen completed config generation or
  app-side scenario generation as generic tasks.
