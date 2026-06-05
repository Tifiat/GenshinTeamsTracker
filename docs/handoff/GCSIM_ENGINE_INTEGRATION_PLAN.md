# GCSIM Engine Integration Plan

Planning date: 2026-06-04

Scope: implementation-direction handoff for GTT-modified GCSIM engine integration. This is not a final Codex implementation task and not a rigid architecture freeze. It records the current product/engineering vector, open questions, and contracts that future Codex tasks must respect unless a later handoff explicitly supersedes them.

Related references:

- `docs/handoff/GCSIM.md` - original GCSIM research notes and upstream source pointers.
- `docs/handoff/STAT_NORMALIZATION.md` - project stat normalization and GCSIM stat-key mapping notes.
- `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md` - Run Workspace boundary, factual DPS vs sim DPS split, and snapshot/session state rules.
- `docs/handoff/ABYSS_ENEMY_DATA.md` - Abyss source-data pipeline and enemy rows.

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

The intended update model is official GCSIM source plus GTT patches embedded in the application:

```text
official genshinsim/gcsim source release or commit
+ local GTT patch stack shipped with the app
= local GTT-GCSIM engine folder
```

The app-level `Update GCSIM` action should be transactional:

1. Download/select official GCSIM source for a chosen release/commit/PR source.
2. Create a new local engine folder.
3. Apply the GTT patch stack shipped with the app.
4. Build/prepare the engine runtime.
5. Run compatibility smoke checks.
6. Activate the new engine only if patch/build/smoke all pass.
7. If anything fails, keep the previous active engine and report incompatibility.

Guarantee target:

- If upstream GCSIM areas touched by GTT patches remain compatible, patches should apply and the new local GTT engine should become usable automatically.
- If upstream changes conflict with GTT patches or break smoke checks, the app must not activate the new engine.
- Older working engine folders must remain selectable/rollback-capable.

A small local engine stack is acceptable, for example two or three known-good engine folders plus optional failed/debug folders. Engine folder size is not currently considered a blocker.

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

## 3. Patch Stack Direction

GTT features should be implemented as a minimal patch stack over GCSIM, not as broad rewrites scattered across the engine.

Preferred shape:

- Keep most GTT logic isolated in GTT-specific packages/modules inside the patched source tree, such as scenario, wave scheduler, engine API, and result metadata modules.
- Touch upstream GCSIM core/parser/setup/combat code only at narrow integration points.
- Keep patches small enough that upstream updates adding characters, weapons, artifacts, or ordinary mechanics usually merge cleanly.
- Treat conflict with target/combat/event/setup internals as an expected compatibility failure requiring a newer app/patch-stack version.

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

Key mapping is a separate required task before reliable config/scenario generation.

Contracts:

- Do not feed localized display names to GCSIM.
- Map project/account character, weapon, artifact set, and enemy identifiers to GCSIM keys using stable IDs or generated mapping data.
- Traveler is explicitly deferred for initial GCSIM integration; do not silently guess a Traveler element/variant.
- Missing or ambiguous mappings should make a slot/scenario not ready for GCSIM rather than producing a misleading config.

## 7. Character Level Helper

GCSIM character config needs current/max level style values such as `80/90` or `90/90`.

Current account/runtime data may not always expose character ascension/max level directly. A helper is required before full config generation:

```text
resolve_gcsim_character_level(account_character, character_catalog_entry) -> current/max level + warnings
```

The helper may use account level plus catalog/base-stat evidence where available. It must report uncertainty instead of silently inventing max level.

## 8. Talent Levels

GCSIM config should use account-observed displayed talent levels, including constellation-increased levels.

Example: if the account/UI-observed levels are `9/11/8`, emit those levels for the GCSIM talent line rather than trying to subtract constellation bonuses.

A later implementation task must verify the project account talent order and GCSIM expected order, then provide a deterministic helper for normal/skill/burst ordering.

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

The UI should show a confirmation/warning before heavy batch simulation, explaining that it may load the CPU heavily and recommending not interacting with the PC until it finishes.

## 11. Result Handling / JSON Boundary

A practical first result boundary can use GCSIM JSON result files/objects as the interchange format. This is acceptable because saved run history will need durable result metadata anyway.

Result parsing should extract at least:

- sim DPS statistics;
- duration / clear-time statistics;
- total damage;
- warnings and failed actions;
- target/character/element breakdowns where useful;
- engine version/hash;
- GTT patch/capability metadata;
- scenario/team/build/enemy hashes.

The parser must tolerate missing default/zero fields because GCSIM results are protobuf JSON where default values may be omitted.

If a later Go API/shared-library/native result object is designed, it should still preserve a JSON/history-friendly result representation.

## 12. Suggested Implementation Phases

This is a direction, not a mandatory Codex task split. Codex may propose safer boundaries after inspecting the current repo.

1. Documentation/preflight:
   - keep this handoff updated;
   - identify current repo entrypoints for engine storage/settings and Run Workspace integration.
2. Local engine update/patch manager experiment:
   - official source folder -> new local engine folder;
   - dummy GTT patch application;
   - manifest creation;
   - active/rollback behavior;
   - no real wave scheduler yet.
3. Build artifact / shipped fallback preparation:
   - build a local runtime artifact from patched source;
   - record artifact path/hash in the manifest;
   - keep the release-shipped known-good engine as a non-deletable trusted fallback;
   - do not require ordinary users to have Go/Git for out-of-box calculations.
4. Dependency-aware update UX:
   - detect Go/Git readiness;
   - expose automatic install/manual install/already-installed/cancel paths;
   - treat `winget` as optional and always keep the current engine active on dependency failure.
5. GTT engine API skeleton:
   - engine info/capabilities;
   - validate scenario;
   - run scenario;
   - result metadata.
6. Key mapping and config/scenario generation foundation:
   - character/weapon/artifact/enemy key mapping;
   - Traveler deferred;
   - character max-level helper;
   - talent order helper.
7. Vanilla-compatible GCSIM run through the GTT boundary:
   - one team/scenario;
   - single target and simultaneous multi-target target models;
   - parse result into a backend object;
   - no right-panel integration yet unless explicitly scoped.
8. Sequential wave scheduler patch:
   - spawn queue;
   - group-clear and rolling-replacement experiments;
   - scenario metadata;
   - smoke configs.
9. Abyss scenario integration:
   - consume existing Abyss cache/enemy rows;
   - generate chamber/side scenarios;
   - run batch simulations with resource budgeting;
   - produce sim DPS and sim timer objects.
10. Right-panel/UI integration:
    - fill prepared Sim DPS cells;
    - show stale-result warnings;
    - expose engine/scenario metadata compactly;
    - keep detailed controls outside cramped TeamCard/right-dock cells.

## 13. First Codex Task Direction

The first Codex task after this handoff should not implement full GCSIM or UI integration. It should inspect the repo and propose/prepare the smallest safe experiment for the local engine update/patch manager boundary.

The first task should verify where engine folders/settings/manifests can live, how to keep the experiment isolated from production UI, and how to test transactional active/rollback behavior without requiring network/app-wide runs.

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
  It runs `go version`, requires `windows/amd64`, runs `go build -o build/gtt-gcsim.exe ./cmd/gcsim` inside the staged engine source, then verifies the built executable with `build/gtt-gcsim.exe -version`. The new engine activates only when build and artifact runtime check pass.
- First real GTT patch content exists at `run_workspace/gcsim/patch_stack/0001-gtt-engine-marker.patch`. It adds a minimal `pkg/gtt` package and a `-gtt-info` CLI flag to `cmd/gcsim/main.go`.
- Sequential-wave prototype patch exists at `run_workspace/gcsim/patch_stack/0002-gtt-sequential-wave-prototype.patch`. It is opt-in through a vanilla-ignored config comment directive:
  `# gtt_wave_prototype duplicate_first_target=1`.
  The prototype reads that directive before simulation run, duplicates/reuses the first configured finite-HP target as the next wave, hooks damage-mode `stopCheck()` so a pending GTT wave can spawn before vanilla all-dead termination, and keeps the new target visible to the dynamic status/damage result paths needed by this smoke. This proves a next target can be spawned inside one simulation iteration after the current finite-HP target/group dies, preserving the run rather than ending immediately. It does not model real Abyss waves, groups, spawn positions, enemy identities, target key mapping, or final 3+3+3 policy.
- Structured wave scenario payload patch exists at `run_workspace/gcsim/patch_stack/0003-gtt-wave-scenario-payload.patch`. It adds a `-gtt-wave-scenario scenario.json` CLI flag and `simulator.Options.GTTWaveScenarioPath`. Empty path is a no-op so vanilla runs remain unchanged. Explicit payload errors are fatal and must not silently fall back to vanilla.
- Payload schema v1 is intentionally minimal and app-owned: `schema_version=1`, `spawn_policy="group_clear"`, and `waves[].targets[]` with required `level`, `type`, and explicit `hp`. The patch builds each enemy through GCSIM's target type/profile path (`enemy.ConfigureTarget`), so `type` owns monster stats/resists and the payload HP is applied as an explicit override after the profile is configured. Optional `pos`/`radius` remain explicit overrides only; normal Abyss bridge output does not write them. The first payload wave replaces parsed config targets; remaining waves are stored on `ActionList` and deep-copied per simulation iteration. When the current group is dead, the scheduler spawns the next payload group inside the same iteration. This still does not implement key mapping, real Abyss 3+3+3 policy, rolling replacement, or UI integration.
- Current `-gtt-info` for a built patched artifact should report `gtt_engine=true`, `gtt_patch_version=gtt-wave-scenario-v1`, `capabilities=["gtt_engine_marker","gtt_wave_scheduler_prototype","gtt_wave_scenario_payload"]`, `sequential_waves=true`, `wave_scheduler_stage="scenario_payload_prototype"`, and the upstream version when available. This is a prototype capability signal, not a final Abyss-correctness claim.
- Built artifact metadata is recorded in the manifest/report: artifact path, filename, sha256, build status, artifact runtime check status, Go version/OS/arch, build command/stdout/stderr, artifact version command/stdout/stderr, GTT marker status/version/capabilities/stdout/stderr, `artifact_kind=local_build`, and `shipped_fallback_status=resolver_available_not_bundled`. `runtime_ready=true` means either the legacy no-build `--probe-runtime` passed or, when `--build-artifact` is requested, the built executable passed the artifact checks. If `--build-artifact` is used with a non-empty `.patch` stack, the built executable must also pass `build/gtt-gcsim.exe -gtt-info`; missing, nonzero, invalid JSON, missing patch version, or missing `gtt_engine_marker` capability keeps the previous active engine.
- Minimal artifact runner exists in `run_workspace/gcsim/artifact_runner.py`, with a dev CLI at:
  `python -m run_workspace.gcsim.run_smoke --config path --gtt-wave-scenario scenario.json --format text`.
  It resolves the active engine from `GcsimEngineStore`, locates the built artifact recorded in the manifest, writes caller-provided config text to a run directory, executes `gtt-gcsim.exe -gtt-wave-scenario scenario.json -c config.txt -out result.json` when a scenario is supplied, captures stdout/stderr/return code, enforces a timeout, and parses only a tolerant summary from uncompressed JSON results: schema version, sim version, `statistics.dps.mean`, `statistics.duration.mean`, `statistics.total_damage.mean`, warnings, failed actions, and incomplete characters. It intentionally does not generate account/team configs, map keys, final Abyss wave policies, or integrate with UI.
- Shipped fallback artifact resolver exists in `run_workspace/gcsim/shipped_artifact.py`. The default candidate path is `run_workspace/gcsim/shipped/gtt-gcsim.exe`, but no production binary is bundled yet. The resolver reports explicit statuses (`disabled`, `candidate_missing`, `candidate_ready`, `candidate_not_file`, `candidate_invalid_path`) and requires an actual file for `candidate_ready`. `run_active_gcsim_artifact(...)` has explicit opt-in fallback support: the active built artifact remains first priority, and a ready shipped fallback is used only when the active artifact is unavailable. Run results now include `artifact_source`, `active_artifact_status`, and `shipped_fallback_status` diagnostics. Shipped binary marker/capability validation is not implemented yet and remains release-process work.
- A narrow backend Abyss-to-GTT-wave bridge now exists in `run_workspace/gcsim/abyss_wave_scenario.py`. It consumes typed `AbyssFloorSourceData`, selects one chamber/side, audits rows grouped by source waves, expands `enemy_count` into individual schema-v1 targets, and can produce a `group_clear` payload dict plus a separate audit/result object. Payload generation is ready only when required source HP/level fields are present and an explicit Abyss enemy source identity -> GCSIM enemy type mapping is provided. Nanoka monster id is the preferred strong identity when present, but it is not the only allowed identity: Fandom enemy page URL/page title/name candidates must remain valid fallback identities, and enemy-type fallback must be independent from HP source fallback. HP may come from Nanoka while GCSIM type resolves through Fandom identity, or HP may come from Fandom fallback while type resolves through Nanoka id. A last-resort debug-only identity source may come from Snap metadata if normal Nanoka/Fandom matching breaks: tower schedule floor id -> tower floor `LevelGroupId` -> tower level monsters -> monster `DescribeId` -> monster `Name`/`Title`. Snap metadata is only a fallback name source for enemy type mapping; it must not be used as HP truth or gameplay stat truth, and it lacks source wave splits, so ordering/group matching is only diagnostic/provisional. Missing Nanoka id alone is not a blocker; the blocker is missing explicit mapping for all available source identities. The bridge must not infer production-ready GCSIM type keys from arbitrary display/localized names.
- Dev CLI `python -m run_workspace.gcsim.abyss_wave_scenario_smoke` loads either the current cached Abyss period or an explicit cached period/floor, builds the provisional schema-v1 scenario JSON for a selected chamber/side, and can optionally pass that scenario to the existing active artifact runner with a caller-provided config. Missing cache/source fields or missing enemy type mapping prints the audit and exits nonzero without writing/running a misleading scenario. This remains backend/dev-only and still does not generate account/team configs, broad key mappings, final Abyss wave policy, or UI state.
- Enemy type mapping JSON supports explicit records with `source_kind`, `source_id`, `gcsim_type`, diagnostic `source_name`, and optional notes/warnings. The previous `enemy_types_by_nanoka_monster_id` shape still loads for dev compatibility, but new mapping sources should prefer the records format so Fandom page URL/title and future debug-only Snap identities can be represented without overloading Nanoka ids. Duplicate records for the same identity are reported as ambiguous and are not silently chosen.
- Dev coverage checker `python -m run_workspace.gcsim.abyss_enemy_type_mapping_report --enemy-type-map path --cache-file path --format text` verifies cached Abyss source-data against an enemy type mapping without network fetches, cache mutation, GCSIM runs, or UI imports. It reports total rows, resolution counts by identity kind, missing/ambiguous mappings, HP-present/type-missing rows, type-present/HP-missing rows, and unresolved rows with all available identities. Use it for both normal Nanoka-backed caches and forced Fandom fallback/Fandom-only caches. Full production enemy type mapping coverage remains future work.
- Backend config readiness audit now exists in `run_workspace/gcsim/config_readiness.py`. It is adapter-free and accepts lightweight prepared team inputs instead of UI widgets or SQLite rows directly. It audits explicit GCSIM mapping refs for characters, weapons, and artifact sets; current/max character level; equipped weapon level/refinement; artifact completeness and normalized artifact add-stats via the existing stat-normalization layer; and account-observed talent levels only when normal/skill/burst order is confirmed. Missing or display-name-only mappings report `missing_mapping`, ambiguous mappings report `ambiguous_mapping`, Traveler remains `unsupported_traveler`, and missing source fields such as level/weapon/artifacts/talents report controlled readiness statuses. This still does not generate config text, create real project-id-to-GCSIM mapping data/reports, query account/equipment storage, run artifacts, or wire UI.
- Backend GCSIM key-mapping report foundation now exists in `run_workspace/gcsim/key_mapping.py`. It defines explicit character, weapon, and artifact-set mapping records with project id/set uid, diagnostic canonical name, `gcsim_key`, source kind/name, readiness status, warnings, and optional ambiguous candidates. It converts ready records into `config_readiness.GcsimMappingRef` values and reports counts/missing/ambiguous entries by entity type. The current boundary is seed/fixture-oriented (`curated`, `curated_test_fixture`, `dev_fixture`, `test_fixture`) because no reliable committed production `project id -> GCSIM key` source has been identified. Display-name, localized-name, and normalized-name-guess sources are rejected as not ready; Traveler remains explicitly unsupported/deferred. This still does not create production mapping data, generate config text, query account/equipment storage, run artifacts, or wire UI.
- Tiny committed GCSIM key-mapping dev seed now exists at `run_workspace/gcsim/mapping_seeds/gcsim_key_mapping_seed_v1.json`, with a report CLI at `python -m run_workspace.gcsim.key_mapping_report --format text|json`. The default report keeps `production_mapping_data_missing` because the seed is intentionally tiny and not production-complete. Current records cover only explicit dev/fixture-backed Mona, Favonius Codex, and Noblesse Oblige keys; do not extrapolate from these names or slugs, and do not treat this as full character/weapon/artifact-set mapping coverage. Full mapping source generation/curation remains future work.
- Tests in `tests/test_gcsim_engine_store.py` pin success activation, patch failure rollback, smoke failure rollback, manifest metadata, and old-active availability.
- Official GitHub source acquisition exists in `run_workspace/gcsim/source_acquisition.py`. It resolves official `genshinsim/gcsim` releases through the GitHub API, downloads the release source zip, extracts the single top-level source tree into `data/gcsim/sources/`, and rejects unsafe/corrupt archives.
- Backend/dev update command exists at `python -m run_workspace.gcsim.engine_update --release latest`. It downloads official source, calls `GcsimEngineStore.prepare_engine_update(...)`, applies the selected replaceable patch backend, runs a source-layout smoke check for `go.mod`, `cmd/gcsim/main.go`, `pkg/simulator`, and `pkg/model`, writes source/patch/check metadata into the manifest, and activates only on success.
- Optional runtime probe flag exists: `python -m run_workspace.gcsim.engine_update --release latest --probe-runtime`. It first checks `go version`, requires `windows/amd64`, then runs `go run ./cmd/gcsim -version` from the prepared source tree with a timeout. If Go is missing, wrong-arch, times out, or exits nonzero, the staged engine is not activated and the previous active engine remains active.
- Go subprocesses launched by this backend use project-local cache/bin directories under `.go/` via `GOMODCACHE`, `GOCACHE`, and `GOBIN`; `.go/` is ignored.
- Engine/source runtime data is local/generated and ignored under `data/gcsim/`.
- Default check status remains source-layout only and records `runtime_ready=false` / `runtime_check_status=not_requested`. With `--probe-runtime`, a successful no-build probe records `runtime_ready=true`, `runtime_check_status=runtime_probe_passed`, `go_version`, `go_os`, `go_arch`, and truncated probe stdout/stderr metadata. With `--build-artifact`, the preferred runtime check is the built executable, not `go run`.
- Tests in `tests/test_gcsim_patch_backends.py` pin git backend ordered patch success, parent-repo discovery isolation, missing git, patch check failure, patch apply failure, empty patch stack success, and previous-active preservation. Tests in `tests/test_gcsim_engine_update.py` pin fake official-source acquisition, download failure, corrupt archive failure, layout-smoke failure, manifest metadata, old-active preservation, Go-missing, wrong-arch, nonzero probe, timeout, default no-probe behavior, successful fake runtime-ready activation, git patch backend plus runtime probe together, successful fake build artifact activation, Go missing/wrong arch/build failure/artifact version failure rollback, artifact sha256 metadata, GTT marker success activation, and GTT marker failure rollback.
- A real local validation command succeeded on 2026-06-04:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git --probe-runtime --build-artifact --format text`.
  After the structured payload patch, it built official upstream `v2.42.2`, activated engine `gcsim-v2.42.2-20260604175430`, produced `build/gtt-gcsim.exe` with sha256 `c06aa07af8924b3bafb7ad9097bc3e5e39f9570e99958dd43cd20c3a760b6921`, and `-gtt-info` returned `gtt_patch_version=gtt-wave-scenario-v1` plus `gtt_wave_scheduler_prototype` and `gtt_wave_scenario_payload` with `sequential_waves=true`.
- A real local sequential-wave prototype smoke also succeeded on 2026-06-04 through `run_smoke`. The smoke used `iteration=1`, `duration=10`, a single finite-HP target, Bennett, and `kill_target(...)` sysfunc calls so the observable is duration rather than damage. Without the GTT directive, the sim ended after the first killed target with `duration_mean=0.0333333`. With `# gtt_wave_prototype duplicate_first_target=1`, the patched engine spawned one more copy of the first target and continued to `duration_mean=1.03333`. This proves continuation/spawn inside one iteration, but not real Abyss wave modeling.
- A real local structured payload smoke also succeeded on 2026-06-04 through `run_smoke --gtt-wave-scenario scenario.json`. With the same simple config and a two-wave `group_clear` payload, no-payload duration remained `0.0333333`, while payload duration was `1.03333`. A bad payload with `spawn_policy="rolling"` failed clearly with `unsupported spawn_policy "rolling"; expected "group_clear"` instead of silently falling back to vanilla.
- Next real-engine tasks should add real shipped binary packaging/validation, config generation, stronger simulation smoke configs, and app-side scenario payload generation from typed run/enemy data. Do not wire this into UI until engine preparation, config generation, and result boundaries are validated.
