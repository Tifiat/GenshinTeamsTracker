# Data Runtime Boundaries

Purpose: compact map of where current project data lives, who writes it, who
reads it at runtime, and what each layer is not allowed to mean. This is a
boundary map, not a full architecture document. Detailed table/source notes live
in the linked handoffs.

## Generated output lifecycle (mandatory)

Every new persistent generated-output root must declare its producer, consumers,
count/byte retention bound, cleanup trigger and exceptions before implementation
is complete. Wire cleanup into the actual producer/operation lifecycle, including
success, failure and cancellation; a callable but unused helper is not coverage.
Add focused tests for deletion, the current run, concurrent active work, pins,
outside-root links and partial cleanup failure. No cleanup may target user data
merely because it is ignored by Git. Expose over-budget protected data honestly.

Current GCSIM ownership:

| Generated path | Lifecycle owner / protection |
| --- | --- |
| `data/gcsim/optimizer-go-runs/` | `optimizer_run_retention.py`, invoked by the shared Selected/All Sets/Theory session finally path;50 completed runs/256MiB ordinary budget; current/OS-leased/manual-pinned runs protected, newest oversized result reported explicitly |
| Older run roots / optimizer cache | `cleanup.py` / `optimizer_cache.py`; legacy callable coverage does not imply an active producer hook |
| `data/gcsim/set-rule-cache/` | Native `seteffects.RuleParseCache`, configured by All Sets adapter; immutable source ASTs only, never team activations or schedules. Source/name/schema/Go-version keys, atomic writes; neutral catalog compilation finally calls cleanup on success/failure. Legacy-only envelopes omit libraries and must not evict this cache. At most512 owned regular entries/64MiB (32MiB per payload); live catalog defines stale keys, oldest live entries may be evicted safely. Recent/active temporary writes protected; abandoned temps expire after24h, protected overflow/cleanup failure is counted, links/ancestors/unowned files untouched. Managed experiments redirect this root into their disposable job. |
| `native/gcsim_optimizer/set-rule-cache/` | Read-only distribution seed; `tools/prepare_optimizer_set_cache.py` warms every active catalog set through the native compiler, with the same512-file/64MiB retention and one replaceable provenance record. Runtime repair/new sources go into the writable cache; shipped files are never edited by optimizer runs. This caches source structure, not a universal bonus or response certificate. |
| `data/gcsim/engines/` | Engine store/update cleanup; active and explicit rollback are protected, but all app consumers use active only |
| `data/gcsim/sources/{archives,expanded}/` | `source_cache_retention.py`, called after acquired-source update preparation on success or controlled failure; two completed versions/512MiB combined target. Current acquisition, newest complete version and all retained engine/diagnostic source references protected. Unknown, incomplete or linked layout fails closed with a report; protected overflow is explicit. Acquisition failure does not authorize guessed cleanup. |
| `.go/build-cache/` | Rebuildable compiler cache; updater cleanup and explicit maintenance, never delete during a build |
| `.codex_tmp/` research outputs | Creating task owns cleanup before closeout; preserve minimal receipts/reproducers, not unlimited source clones or per-experiment Go caches |
| `.codex_tmp/managed-optimizer/job-*` | `tools/managed_optimizer_experiment.py`; one leased job, zero completed jobs retained; cleanup on success/error/cancellation, refusal to allocate if force-kill/cleanup residue remains; no deletion of unknown legacy folders |
| `.codex_tmp/optimizer-retained-evidence-20260917.zip` | One fixed archive, at most512MiB; `archive_optimizer_evidence.py` verifies every member hash/CRC before removal of raw roots. No stacking/overwrite; incomplete owned output is cleaned on failure. N2 boundary/UI and deferred RNG/Theory witness gates own deletion; restore only needed members into managed scratch |
| Five legacy optimizer experiment binaries | One-off exact-file helper `tools/cleanup_optimizer_binaries.ps1`; preview default, explicit `-Apply`, linked/unlisted paths and active builds rejected. These historical files are not product outputs; future reruns belong inside managed scratch |

Parallel linked worktrees are user-owned checkouts, not disposable caches.
Their SQLite DB, settings, engine pointer and output roots are independent;
only Git objects/refs and optionally read-only dependencies are shared. The
runtime seeder stages under one managed job, rejects existing destinations and
linked paths, backs up committed SQLite/WAL state, verifies engine bytes before
publishing, and rolls back only its newly published paths on failure. It leaves
one fixed `.codex_tmp/worker-runtime.json` receipt per worker (16KiB maximum),
not stacked exports. Its lifecycle is the explicitly created worker; removal
requires user-approved worktree retirement, never cache age cleanup. Credentials,
browser profiles, debug dumps, captures, build caches and source downloads are
not copied. Public reference caches use a four-file allowlist, not whole-cache
copying. Synthetic tests cover preservation, WAL backup, publication failure and
available platform link checks.

New disposable research uses the managed runner, including reruns of old scripts.
Pass generated paths under its `{scratch}` argument and export small receipts
before exit. It sets a job-local Go compiler cache and OS/Go temporary directories;
the common build/probe helper respects this cache. Share it across the whole
multi-step command, not across permanently accumulated experiment directories.
Commands must wait for all children; detached work is forbidden. Timeout stops
the child process tree on Windows before cleanup. On force-kill/cleanup failure,
leftovers block another allocation instead of guessing orphan-process safety.
This bounds retained job count, not peak bytes inside one running experiment.
No scheduled wildcard sweeper or deletion of external/legacy outputs is implied.
Research must measure generated bytes before/after expensive work.
`tools/experiments/gcsim/all_sets_efficiency/run_saved_benchmark.py` is the
bounded N1 consumer: it keeps only a small explicit receipt and verified removal
of the managed job; its two current receipts are owned by the optimizer checkpoint.
The isolated `inventory_bound_poc/run.py` likewise refuses unmanaged execution;
its overlay, compact graphs, compiler cache and temp files live in that job.
It keeps one `inventory_bound_poc_lineage5_v1.json` receipt (64KiB hard limit;
currently42,343 bytes), refusing overwrite.
Production arithmetic/legality controls now cover the integration. The fixed
historical real-input receipt/reproducer stays as an independent oracle until
the current single-team integration gate, which owns folding the remaining
controls or pruning duplicate prototype code. No capture archive is retained.
`test_inventory_bound_poc` pins the compact input/legality contract;
`test_managed_optimizer_experiment` covers connected success/error/timeout cleanup,
preservation, links, active leases and cleanup-failure refusal.
The opt-in native `TestParametricActiveEngineWitness` reuses that immutable
receipt, binds the current active engine and writes its two captures only inside
the same managed job. Default suites skip it. No new persistent output root or
capture receipt is created: the Go design retains compact scoped metrics, and
all generated graphs/build files are removed on success/failure by the existing
runner. Unmanaged invocation is rejected before engine calls.
`parametric_effects/check_stat_queries.py` and `check_rules.py` use this same
managed job, not a new output root. The former copies only reviewed patch targets
and preserves both original/generated variants on overlay collisions; the latter
writes one engine-bound source envelope for tiny rule tests. The default gates
run no simulations. Explicit `check_stat_queries.py --capture-fixture` adds the
one saved Flins seed's neutral and original-set response captures, plus strict
native decoding, rule/port binding and residual attribution. Configs, members,
sidecars and source/build copies stay in the SAME managed job; default tests
skip this gate. Only compact measurements are retained in the Go design.
The inventory profile reuses that capture for restricted/full weak-start searches.
The optional `--finish-passes` diagnostic retains the same owned scope/cleaner
and finite external watchdog; it removes only the internal60s search deadline.
Resource observation copies and source controls add no persistent output root.
The optional `--compare-preparation` / `--compare-effects` controls place their two consumer source copies
and Go overlay in that SAME managed job. Both variants reuse the captured inputs;
only compact measurements/work hashes survive in the Go design. Its source-target
and unmanaged-refusal tests live in `test_parametric_effect_gate`. Specialization
reuse is bounded run-local memory (including pinned source graphs), not disk data.
`--two-seeds` explicitly expands the same saved fixture to two neutral and two
independent original-set captures, all inside that SAME job. It requires the
completion profile and excludes paired timing variants; default capture remains
one seed. Strict decoding and same-panel response/recall controls cover both
members. Only compact evidence in the Go design survives; no new output root.
`parametric_effects/verify_candidates.py` checks at most two resulting builds plus
one saved control, each once at n500 through the ACTIVE installed runner. It also
requires a managed job, keeps configs/results there, and emits only a compact
stdout receipt. Gate tests pin unmanaged refusal, candidate count and unique IDs;
the existing managed-runner tests own connected cleanup and preservation.
`parametric_effects/install_neutral.py` is the temporary integration gate. It
replays the old stack against the ACTIVE source identity and uses the same cached
pristine archive in the normal updater/build/manifest pipeline. Staging, native
build, four response captures and disposable consumer backup share ONE managed
job. Explicit `--activate` retains only a validated versioned engine, the normal
consumer and consolidated production `0009-gtt-neutral-event-effects.patch`.
The previous active engine becomes pinned rollback. Injected promotion failure
tests restore the pointer first, consumer and patch, then return the staged tree
to managed cleanup. No account/settings/equipment writes or new cache root.
The2026-09-26 activation gate passed; scoped hashes and measurements live in the
Go design. Historical patch-overlay entrypoints must not reapply their deltas
to the now-consolidated active source. Remove temporary installation/overlay
entrypoints after the Flins product/button gate; retain permanent source/native
controls. Keep compact measured generated/removed bytes in the Go design's neutral
producer section, not expanded sources/envelopes/caches. Existing lifecycle tests
own cleanup/preservation; focused gate tests own path/refusal/selected binding.
`parametric_effects/repair_hit_identity.py` uses that same managed lifecycle for
the user-approved event-hit identity correction. It reconstructs the exact active
source, amends patch0009 in place only at validated promotion, and retains no
second production patch. The tiny finite Song control and real-event consumer
test keep all captures in the owned job; compact evidence belongs to the Go
design. Promotion tests cover restoring an existing patch and failure during the
post-relocation installed capture. Retire this helper/fragment with the neutral
installation helpers; installed source/native regression tests remain.
Its `capture_equivalence.py` companion is a read-only validation helper, not a
second formula evaluator: it verifies original sidecar/member hashes, then
compares ordered expressions and complete effect ownership modulo local node
numbering. It generates no retained files and retires with the deployment helper.
The post-change `all_sets_inventory_regression/run.py` comparison owns
`docs/optimizer-evidence/all-sets-inventory-20260919/`: one byte-identical immutable
`before.json` (2MiB cap), one `after.json` (8MiB,14 teams, at most3 attempts/team),
one compact `install.json` and one generated report (256KiB cap). The user
requested retaining both logs as the next algorithm baseline. No baseline run
is regenerated. Atomic bounded writes preserve failed attempts; excess refuses
new evidence rather than deleting history. Each post-change row/build uses a
separate managed job and connected cleanup. `test_all_sets_inventory_regression`
checks immutable-original, attempt/size refusal and previous-receipt preservation.
These four documents are retained until the user replaces this comparison gate;
raw graphs, disposable binary backups and build caches never survive the job.
The saved-user-run `parametric_effects/check_saved_feather.py` diagnosis also
requires the existing managed scope: four bounded ordinary simulations and an
opt-in native formula replay reading the retained product capture. It writes no
receipt/root outside scratch; compact numbers belong to the Go design's dated
feather receipt. `test_saved_feather_probe` covers unmanaged refusal and exact
single-item substitution; managed-runner lifecycle tests own cleanup. Temporary
Python/Go probes share the existing Flins product acceptance cleanup gate;
ordinary source user-run files remain under the normal product-retention owner.
The scoped `parametric_effects/compare_navia_user_swaps.py` follow-up has at most
sixteen explicit baseline/counterfactual assignments, each changing only one
wearer. It reads owned artifacts without DB initializers and uses the same
active ordinary runner, bounded at2000 iterations per case. Short1/10-iteration
invocations are runtime diagnostics, not ranking evidence. It requires the
managed lifecycle, exports only stdout and retains compact measurements in the
Go design's dated Navia receipt. `test_navia_user_swaps` covers input identity,
isolated changes, physical uniqueness and unmanaged refusal; the existing
managed-runner tests cover deletion/preservation. The helper shares the existing
parametric research cleanup gate; no additional persistent generated root.
The 2026-09-26 search/preparation successor uses
`parametric_effects/recheck_saved_all_sets.py` for exactly one saved-request
product-process replay, not another matrix sweep. It owns the fixed immutable
`flins-user-stabilization-20260926.json` in the existing comparison folder,
at most1MiB; an occupied slot or oversized receipt refuses before overwrite.
It preserves every original matrix attempt. Source/captures/build caches and
the recoverable pre-install consumer backup stay in one managed job and are
removed on exit; a failed product replay restores the previous consumer.
`test_saved_all_sets_recheck` covers the no-overwrite/size/unmanaged guards;
the managed runner owns connected cleanup. The retained successor has the same
user-replacement deletion gate as the comparison, not time-based pruning.
Its temporary probe and `saved_preparation_test.go` share the Flins research
cleanup gate; the latter reads two retained captures without simulator calls.
Deliberately retained evidence needs a named
consumer and deletion gate in the owning manifest; "may be useful" is not a
permanent exception. Keep source patches/reproducers and small receipts instead
of retaining every intermediate engine tree. Do not delete unaccepted unique
evidence or another active task's output.

2026-09-17 audit found38.439GiB total,27.474GiB research scratch and5.861GiB Go
state. The Go-run root was missing from the old retention API and no product
caller remained for its old post-run hook. Shared-session retention is connected.
The initial agent deletion was denied; the user removed the eleven cache and97
research roots (confirmed absent). After renewed authorization, guarded
`cleanup_optimizer_caches.ps1 -Deep -Apply` removed82 further roots, preserving
needed raw witnesses in one verified archive. Preview remains default; `-Apply`
is explicit. It rejects worktrees, protected engines/overlay dependencies and
links. A separate attempted inline deletion of five extra binaries was denied;
the tested exact-file helper was subsequently run by the user and all five are
confirmed absent. User data, profiles, exports and dirty worktree are not cleanup targets.
Receipt: `tests/fixtures/gcsim_optimizer_go_v1/generated_storage_audit_v1.json`.
The checkpoint owns current sizes, the optional blocked tail and witness gates.

Coverage review after the cleanup distinguishes current producers from retired
research residue. Shared Selected/All Sets/Theory runs call lease-aware retention
from their common `finally` path. Successful engine updates prune generated engine
state while preserving active/rollback versions; the engine-update CLI also
deletes its rebuildable Go build cache after successful probe/build unless the
caller explicitly keeps it. Disposable optimizer research must run through the
managed runner, which owns its job-local Go/OS caches and cleans every normal
exit path. The removed old debug trees and five binaries have no product
producer; direct reruns of historical scripts are intentionally not intercepted
and are forbidden unless first adapted to managed scratch. This is lifecycle
coverage for the classes removed in N0, not proof that every generator in the
entire repository has been audited. The full-project size/lifecycle audit is a
separate post-optimizer TODO stage.

## Raw HoYoLAB JSON / Source Cache

Paths:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/account_character_details.json`
- `data/hoyolab/account_language.json`
- `data/hoyolab/crop_manifest.json`

Role:

- source/cache output of the HoYoLAB import pipeline;
- input to account SQLite sync, artifact import, crop/asset generation, and
  explicit debug/source inspection tools;
- test fixture source where a parser/source path is being tested.

Import preparation validates inventory/detail batches and non-empty export
layout/crops before publishing account data. Crops use a temporary path mirror;
account JSON replacement is atomic per file, not across SQLite and all files.
Failure coverage: `docs/handoff/HOYOLAB_IMPORT_RELIABILITY.md`.

The default-OFF HoYoLAB "Change equipment" setting explicitly applies fresh
observations to canonical SQLite equipment after successful account sync.
Runtime UI still reads SQLite; merged historical source inventory is not an
equipment assignment source. Presets remain separate and are never rewritten.

Runtime rule:

- new UI/runtime account code should not read these files directly for account
  character, talent, weapon, or icon state;
- if SQLite account runtime tables are expected but empty, report the empty
  storage/import condition instead of silently falling back to stale raw JSON.

## Account SQLite Runtime State

DB:

- `data/artifacts.db`

Note: this is a legacy filename for the unified local SQLite runtime DB. It is
not artifact-only storage; account, equipment, artifact, and selected static
effect tables can live in the same file.

Runtime account tables:

- `account_characters`
- `account_character_talents`
- `account_weapon_observed_stacks`

Writers:

- normal HoYoLAB import (`python -m hoyolab_export.run_import`) after raw JSON,
  artifacts, and crop manifest are written;
- manual/debug resync (`python -m hoyolab_export.account_storage`), optionally
  with `--download-side-icons`.

Readers:

- runtime/UI account loaders through `hoyolab_export/account_storage.py` read
  adapters;
- `ui/character_assets.py` converts adapter records into legacy visual grid
  asset items;
- `run_workspace/pvp/account_deck_export.py` reads the same adapters to build a
  backend-only Free Draft `DraftDeck` from owned characters and observed weapon
  stacks.

Meaning:

- `account_characters`: authoritative account character state from HoYoLAB
  character list plus clean base/reference fields where available and resolved
  GCSIM character key readiness metadata;
- `account_character_talents`: observed account skill/talent levels from local
  HoYoLAB detail `skills[]`;
- `account_weapon_observed_stacks`: reconstructed observed weapon stacks from
  equipped/detail observations, including resolved GCSIM weapon key readiness
  metadata.

Terminology note: "stack" here means a deduped observed weapon fingerprint with
`known_count`, not a UI tooltip/grouping of different weapon variants.

Important limits:

- `account_characters.name` is localized HoYoLAB display text. Identity-sensitive
  adapters should use stable IDs such as `character_id` plus explicit mapping
  data, not English-name searches or localized display-name matching;
- GCSIM config adapters should consume stored resolved `gcsim_character_key` and
  `gcsim_weapon_key` only when their status is `ready`. The
  `catalog_english_name` fields are local HoYoWiki source context and are not
  valid GCSIM keys by themselves;
- observed weapon stacks are not guaranteed full weapon inventory;
- HoYoLAB weapon id is a weapon type id, not a unique account instance id;
- no fake weapon instance ids;
- current-equipped character -> weapon relation is provenance only, not
  canonical weapon identity;
- TeamBuilder/prototype selected weapons should be explicit observed weapon
  options (stack id/fingerprint or deterministic smoke selector), not inferred
  from current-equipped provenance;
- observed constellation `name`/`effect`/`is_actived` rows are stored in
  `account_character_constellations` for C3/C5 talent normalization. This narrow
  account evidence is not a static talent/constellation catalog, parsed buff
  engine or GCSIM config store.

Detailed contract: `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`.

## PvP Deck Presets / Export Output

Default generated/private write path:

- `data/pvp/decks/`

Role:

- primary local output for AppShell PvP Decks v0 presets:
  `kind = "gtt.pvp_deck_preset"`;
- optional output for `python -m run_workspace.pvp.account_deck_export_smoke
  --write`: backend `kind = "gtt.pvp_deck"` JSON built from current local
  account SQLite runtime data.

Rules:

- default account deck export smoke is dry-run and writes no JSON;
- UI preset JSON stores stable `character_ids` and observed weapon-stack refs;
  it must not store localized display names or image/local machine paths as
  identity;
- backend `DraftDeck` export JSON may contain stable ids, localized display
  names, levels, constellations, weapon refinements, and stack counts;
- PvP deck/preset JSON must not contain artifacts, artifact stats, HoYoLAB
  auth/cookies, raw account dumps, local paths, SQLite row ids, or
  generated/private storage internals;
- AppShell preset loading skips backend `gtt.pvp_deck` files in the same folder;
- `data/pvp/` is ignored and should not be committed.

## PvP Session Bundle Output

Default generated/private write path:

- `data/pvp/sessions/`

Role:

- optional output for `python -m run_workspace.pvp.session_bundle_smoke --write`;
- contains backend/debug PvP session bundle JSON for replay/validation.

Rules:

- default session bundle smoke is dry-run and writes no JSON;
- `--account` is required before the smoke reads local account data;
- bundles may embed account-derived PvP deck data when account mode is explicit;
- bundles must not contain artifacts, artifact stats, HoYoLAB auth/cookies, raw
  account dumps, local paths, SQLite row ids, or huge raw ruleset payloads;
- session bundles are not PvP History persistence;
- `data/pvp/` is ignored and should not be committed.

## Account Character Visual Assets

Sources/paths:

- `account_characters.portrait_path`
- `account_characters.side_icon_url`
- `account_characters.side_icon_path`
- generated/cached files under `assets/hoyolab/characters/...`

Rules:

- portrait/crop paths are local visual assets;
- side icons are cached from already-known HoYoLAB side-icon URLs and reused;
- `side_icon_path` is used for compact overlays such as occupied
  artifact/preset/weapon owner markers and team-bonus member icons;
- side-icon failure is non-fatal and should preserve `side_icon_url`.

Dummy/mannequin placeholders:

- known dummy/mannequin ids from `hoyolab_export/crop_manifest.py` are not
  account runtime visual entries;
- filter them as entities before portrait/side-icon fallback;
- cached side icons must not make non-account placeholders visible.

## Weapon Visual Assets And Hidden Low-Rarity Weapons

Sources/paths:

- `account_weapon_observed_stacks.icon_url`
- `account_weapon_observed_stacks.icon_path`
- generated/cached files under `assets/hoyolab/weapons/...`
- `data/hoyolab/crop_manifest.json` as source/cache asset metadata

Rules:

- weapon icon mapping must use weapon identity/icon source (`icon` URL key first,
  then `weapon_id`), not display order, source row index, or equipped character;
- same weapon type at different levels/refinements normally shares one icon;
- weapon tooltip stat labels must use UI display mappings/localization, not raw
  `P20` / `P23` property ids.

Low rarity:

- 1-2 star weapons may be stored in `account_weapon_observed_stacks`;
- normal weapon visual grids intentionally hide them via
  `IGNORED_WEAPON_RARITIES = {1, 2}` / crop manifest `weaponIgnored` semantics;
- this is stored-but-hidden behavior, not missing icons and not deletion.

## Artifact SQLite Runtime / Storage

DB:

- `data/artifacts.db`

Artifact tables include artifacts, substats, equipment, tags, build presets,
build slots, build targets, artifact sets, set names, set piece icons, and set
bonus descriptions.

Structured static display-stat effects:

- `artifact_set_display_stat_effects` stores only direct always-on artifact set
  display stat effects detected from set bonus descriptions, keyed by
  `(set_uid, pieces_required, stat_key)`;
- `weapon_display_stat_effects` stores only direct always-on weapon passive
  display stat effects, keyed by `(weapon_id, refinement, stat_key)`;
- `weapon_passive_tooltips` stores localized weapon passive/effect tooltip text
  from HoYoWiki weapon `baseInfo` passive fields, keyed by `(weapon_id, lang)`;
- JSON audit/seed files for these effects are source/seed input only and are
  not runtime databases;
- TeamBuilder display stats may apply rows from these SQLite tables, but formula
  effects, conditional effects, talents, constellations, resonances, reaction
  bonuses, enemy debuffs, and combat-state toggles remain out of scope.
- the Right Panel prototype exposes these rows through bonus source display
  items/chips. The current source kinds are `artifact_set_static` and
  `weapon_passive_static`; elemental resonance, `Moonsign` and `Hexerei` also
  use the shared bonus-source shape. Their logic belongs to the team/display
  layer, not these static equipment-effect tables. Future sources should reuse
  the same explanation shape.
- the Right Panel external-bonus toggle disables only external bonus source
  rows such as static artifact set effects and static weapon passive effects.
  It must not disable character base stats, weapon base ATK, weapon secondary
  stat, or artifact main/sub stat totals.
- HoYoLAB account weapon `desc` is flavor/lore reference text from the account
  detail payload. It is not a combat passive/effect description and must not be
  rendered as passive tooltip text.

Role:

- observed equipped artifacts from HoYoLAB are imported into artifact SQLite
  storage;
- existing `artifact_equipment` is an imported HoYoLAB observation table, not
  canonical user-managed current equipment state;
- artifact identity uses content fingerprint/dedupe, not account character
  ownership as identity;
- artifact build presets/slots/targets remain their existing model and are
  separate from account character/weapon runtime tables.
- TeamBuilder/right-panel slot main-stat badges should read actual sands/goblet
  main stats from the selected artifact build snapshot slot data, not build
  target recommendations, character element, HoYoLAB current-final stat rows, or
  selected-detail display stat order.

Do not reset artifact inventory/build preset tables during account-only storage
repairs. See `ARTIFACT_BROWSER.md` for storage identity, content dedupe and
browser/import contracts.

## Persistent Current Equipment State

Design handoff:

- `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md`
- `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`

Implemented role:

- canonical user-managed current weapon per character;
- canonical user-managed current artifact slots per character;
- side-icon owner read models for artifacts, weapons, and presets;
- explicit Artifact Browser equip/apply writes.

Boundaries:

- Stage A schema/service helpers are implemented in
  `hoyolab_export/account_equipment.py` and initialized by `init_db`;
- AppShell reads/writes current weapons through
  `hoyolab_export/account_equipment.py`, including repeated-click unequip;
- AppShell reads current artifact ids through
  `account_character_equipped_artifacts` and converts them into a runtime-only
  current-equipment artifact snapshot for right-panel stats/set bonuses;
- the current-equipment snapshot is not persisted as `artifact_builds` and does
  not mutate saved preset rows;
- AppShell embeds Artifact Browser as a left workspace and reflects the
  operation target/current-equipment UI state through target selection
  highlight and the current-equipment zone. Artifact Browser manual equip,
  repeated-click unequip, and preset apply write persistent equipment through
  the same service helpers. Right-panel target sync initially becomes real
  browser selection for preset browsing; if deselected in the browser, the
  right-panel target remains only as a secondary operation target;
- separate from build preset definitions;
- separate from HoYoLAB observed current-equipped provenance;
- live import applies fresh observations only when the default-OFF Change
  equipment setting is enabled and account SQLite sync succeeds, through one
  validated equipment batch; presets remain unchanged;
- missing HoYoLAB equipment data means "no data", not "clear local equipment";
- OFF preserves user equipment; ON is the explicit snapshot-apply policy in
  `ACCOUNT_EQUIPMENT_STATE_DESIGN.md`.

Artifact Browser / owner-icon boundary:

- the top current-equipment zone is UI presentation over current equipment, not
  an `artifact_build` preset;
- applying a preset copies preset artifacts into current equipment for exactly
  one target character and does not mutate the preset;
- incomplete preset apply clears missing target slots so current equipment
  matches the shown preset;
- artifact owner icons derive from `account_character_equipped_artifacts`;
- preset owner icons derive from the current owners of artifacts in
  `artifact_build_slots`, not from `artifact_build_targets`;
- weapon owner icons derive from `account_character_equipped_weapons` and must
  not create fake weapon instance ids.
- future weapon move/swap UI must select an explicit source owner/copy when a
  `weapon_fingerprint` has no available `known_count`; do not silently steal an
  exhausted assigned weapon by fingerprint.

## Asset / Cache Layer

Generated and cached visual assets live under paths such as:

- `assets/hoyolab/...`
- `assets/artifact_sets/...`
- `data/cache/...`

Rules:

- `crop_manifest.json` is source/cache asset metadata, not the main runtime
  account DB. Version 2 names separate character browser/PvP/History variants,
  raw sources and shared element/rarity layers; existing version-1 manifests
  still supply baked crops as the fallback display path;
- expensive repeatable image work should be cached persistently and not repeated
  in UI hot paths;
- generated local account assets are private/generated state.

Far pre-release note:

- account portrait composition resolution can later become a selectable
  generation quality (`lowres`, `1k`, `2k`, `4k`) with a regenerate action;
- this would change local layer rendering size; normal account import no longer
  uses a HoYoLAB screenshot canvas or crop grid;
- keep this as a late asset-quality pass after the final card/right-panel sizes
  are known.

## Static / Reference Catalogs

Character/weapon detail catalogs are refreshed explicitly with
`python -m hoyolab_export.hoyowiki_catalog_refresh`, default language `en-us`.
Outputs are `data/cache/hoyowiki/character_stats_catalog.json` and
`weapon_stats_catalog.json`. HoYoWiki list menu IDs are 2/4; detail parsing reads
the ascension component. Missing-only refresh retains valid entries; `--force`
refetches after source/parser changes. One failed entry must not discard safe cache.
Mapping/list reports must not implicitly fetch every detail page.

Normal account import best-effort refreshes missing/new artifact sets and small
Moonsign/Hexerei membership data, not every existing icon or character/weapon
detail. Future seed catalogs are sanitized reference data. Empty ascension rows
may mean `future_pending_stats` / `stats_unavailable_yet`, not non-playable junk.
The import owns `data/cache/hoyowiki/artifact_set_list.<language>.json`: public
list responses are reused for six hours, refreshed on expiry, and refreshed
once immediately if an unknown HoYoLAB set cannot be mapped. After each network
fetch, the producer prunes its own list files to eight files / 8 MiB total,
with a 2 MiB per-file admission bound. Other HoYoWiki caches and links are
untouched; partial cleanup failures appear in the import log. The consumer is
the import's artifact catalog/name/bonus refresh only; explicit catalog update
commands still fetch from the source.
Account stat readiness is separate from GCSIM key readiness; Traveler remains
explicitly deferred. Pure helpers live in `account_stat_sheet.py` and
`character_ascension_bonus.py` under `hoyolab_export/`; account ascension uses
`extract_character_ascension_bonus_by_base_stats`, not the legacy level-only
reference helper.


Examples:

- HoYoWiki character stats catalog;
- HoYoWiki weapon stats catalog;
- character region catalog;
- SQLite `character_identity` enrichment table, built from account characters plus
  static/reference region and trait catalogs;
- stat normalization maps;
- current Right Panel team-bonus display/evaluation helpers for elemental
  resonance, `Moonsign`, and `Hexerei`;
- future recommendation or ruleset catalogs.
- refreshable character trait catalog for resonance systems such as `Moonsign`
  (HoYoWiki entry `8782`) and `Hexerei` (HoYoWiki entry `9347`) in
  `hoyolab_export/character_trait_catalog.py`. Raw/source payloads may be
  cached at `data/cache/hoyowiki/character_trait_catalog.json`; normalized
  runtime/reference data lives in SQLite.

Role:

- static/reference data, not account state;
- useful for ascension bonus/reference/fallback, stat normalization, filters,
  and future recommendation/guide features.
- runtime character filters should consume the enriched SQLite/read-adapter
  fields (`region_key`, `traits`, `is_standard_5_star`) rather than each screen
  joining raw HoYoWiki caches independently.
- account-runtime ascension bonus selection uses static HoYoWiki rows only after
  matching the row/phase by factual HoYoLAB base stat anchors from account
  SQLite sync.

Limits:

- character/weapon stat catalogs are not account character/weapon inventory;
- broad static talent/constellation effect catalogs are not stored in account
  SQLite; observed constellation text for talent normalization is the explicit
  narrow exception described in `ACCOUNT_SQLITE_STORAGE.md`;
- `Moonsign`/`Hexerei` are not HoYoLAB account-source fields; they are
  static/reference character traits joined into `character_identity` for
  filters, history, PvP, and resonance calculation;
- normalized trait reference data lives in SQLite tables:
  `character_trait_definitions`, `character_trait_memberships`, and
  `character_trait_tooltip_sections`. `character_identity.traits_json` remains
  the account/runtime join for owned characters, not the full reference catalog.
- HoYoWiki JSON/cache files for traits are source/debug cache only. UI/runtime
  must read normalized SQLite/reference helpers and must not fetch or parse
  HoYoWiki on hover.
- Hexerei tooltip text uses en-us HoYoWiki entry `9347` as canonical source of
  truth. The current HoYoLAB/HoYoWiki content language is a localized override;
  missing localized sections fall back to en-us. Do not machine-translate.
- the Right Panel prototype currently evaluates direct display-stat elemental
  resonance effects in code and exposes them as `RightPanelBonusSourceDisplayItem`
  chips. Implemented stat contributors are Pyro `ATK +25%`, Hydro `HP +25%`,
  Cryo `CR +15%`, Geo selected-character elemental DMG `+15%`, and simplified
  Dendro `EM +50/+80/+100`. Electro/Anemo and non-display-stat resonance
  effects are not modeled in stat rows.
- `Moonsign` is shown as a Lunar Reaction DMG indicator chip only when the team
  has at least 2 `moonsign` characters. With external bonuses enabled, it is
  calculated after direct external stat bonuses (artifact-set static effects,
  weapon-passive static effects, and elemental resonance). If all team members
  are `moonsign`, the chip remains visible but the Lunar value is 0% because a
  non-`moonsign` trigger character is required. The indicator is capped at 36%
  and does not add back into HP/ATK/DEF/EM or normal elemental/physical damage
  rows.
- `Hexerei` is display/tooltip-only for now and does not affect stats. It is
  shown as a team source only when at least 2 current team members have the
  `hexerei` trait. Hexerei source/member tooltips read cached/reference trait
  tooltip sections from SQLite and otherwise show a clear fallback. Member
  tooltips filter sections by account constellation, for example a C4 Mona
  should not show C6 Hexerei text.
- current trait keys are `moonsign` and `hexerei`. The local HoYoWiki trait
  cache carries source entry ids/URLs (`8782` for `Moonsign`, `9347` for
  `Hexerei`) and per-character HoYoWiki entry ids. Tooltip section text belongs
  in `character_trait_tooltip_sections`, not in `character_identity.traits_json`.
- team bonus icons live under `assets/team_bonus/`, including elemental
  resonance icons plus `Moonsign.png` and `Hexerei.png`. Filter icons also
  exist under `assets/filters`. Bonus strip source icons are rendered through a
  cached alpha-trim/scale helper so transparent PNG padding does not shrink the
  visible icon inside the chip. Bonus source chips follow the compact layout
  `[large source icon] [separate effect badge(s)]`; `Hexerei` uses compact
  member icons instead of numeric effect badges. Compact member side icons in
  bonus chips use a separate cached side-icon renderer: fixed scale, centered
  by width, bottom-aligned, clipped at the top if needed, and no nested square
  background.
- bonus source tooltips should be formatted once by the shared Right Panel
  tooltip formatter: title, one `Effects:` section when numeric effects exist,
  then one source/note/breakdown body. Do not repeat the same effect text in
  both the formatter and the source body.
- the Right Panel smoke supports `--team-preset fake|default|moonsign|hexerei|resonance-sanity`
  plus `--summary` for no-GUI validation. `--real-thoma` remains a shortcut for
  the default real smoke. The Moonsign preset includes an all-Moonsign team
  that should show `Lunar +0%` and a Lauma/Ineffa/Nahida/Yelan team for the
  non-Moonsign trigger case. The Hexerei preset has one team with exactly one
  Hexerei member and one team with 2+ Hexerei members. The resonance sanity
  preset covers Geo selected-character elemental damage and Dendro `EM +100`.
- there is currently no elemental resonance definition table/file and no
  resonance formula storage. Future broader structured resonance/team-bonus
  definitions can move to a normalized SQLite/static-reference table, with
  source/cache JSON used only as refresh input. Suggested source keys are
  `elemental_resonance:<element_or_id>`, `moonsign`, and `hexerei`, linked to
  active characters by element or `character_identity.traits_json`.
- standard 5-star membership is a static character trait/filter using
  `assets/filters/standard.png`; UI behavior is tri-state: show all, only
  standard 5-stars, or exclude standard 5-stars;
- account Traveler is force-marked as `standard_5_star` by Traveler character
  id in the identity join; the future dedicated Traveler model must preserve
  that trait even if account display names or elemental variants change;
- if static talent/constellation effects are needed later, create a separate
  static/reference catalog task;
- do not scrape broad HoYoLAB/HoYoWiki sources from account runtime tasks looking
  for talent effect descriptions.

Related handoffs:

- `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`
- `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`
- `docs/handoff/STAT_NORMALIZATION.md`

## Normal Offline Profile Boundary

The normal account profile is separate from PvP `.gttpvp`. Its allowlisted ZIP
includes account characters/weapons/details, `account_language.json`, crop
manifest, allowed assets and a SQLite backup of `data/artifacts.db`. It excludes
browser authorization, cookies/tokens, debug and downloads. A local export-state
marker supports the sign-out unsaved-data warning. Broader History/settings/cache
coverage remains an open task; do not imply the current package already contains it.

## Not Stored Here / Future Boundaries

Not currently stored in account SQLite:

- GCSIM configs/formulas;
- parsed talent/constellation buffs;
- guaranteed full weapon inventory;
- unique weapon instances;
- current-equipped weapon relation as canonical account weapon storage;
- Run Workspace/saved-run immutable snapshot model.

Future saved runs must snapshot actual selected character/weapon/artifact/build
contents instead of relying only on live account/build references.

## Update Rule

When a task changes a persistent data structure, source/cache format, runtime
source boundary, visual filtering rule, or adapter ownership, update this
boundary map or the more specific handoff it points to. Keep root `TODO.md` and
`CODEX.md` as concise entrypoints, not duplicated architecture dumps.

## Optimizer energy experiment lifecycle

`tools/experiments/gcsim/energy_ledger/probe_saved_capture.py` and
`promote_energy_engine.py` run only through `tools/managed_optimizer_experiment.py`.
Their expanded upstream source, temporary patch stack, capture copies and build
outputs belong to that single managed scratch job and are removed on success or
failure. The durable outputs are the consolidated production patch, the active
transactional engine installation and compact documentation/test evidence; the
scripts must not create an additional persistent engine cache or source tree.
