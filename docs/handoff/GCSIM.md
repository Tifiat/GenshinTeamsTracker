# GCSIM Integration Research

Research date: 2026-05-17

Scope: research handoff only. No app code, TODO, CODEX, account data, cache data, HoYoLAB import, or UI behavior was touched for this research.

Implementation direction note: authoritative current backend/UI/release status for the GTT-modified GCSIM engine lives in `docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md`. Keep this file as the historical upstream/source research reference; do not use its original MVP ordering as the current task queue.

Label meanings used below:

- Confirmed: verified from GCSIM docs, release metadata, or source inspection.
- Unconfirmed: plausible but not verified enough to design against.
- Needs follow-up: concrete next research item.
- Risk: implementation or product risk.
- MVP recommendation: preferred first implementation direction for GenshinTeamsTracker.

## 1. Overview

Confirmed:

- GCSIM is an open-source Monte Carlo combat simulator for Genshin Impact.
- Primary user-facing usage is the web app at `https://gcsim.app`, but the project also ships a downloadable CLI/core binary and source-build path.
- For this app, the useful integration target is the local engine/CLI binary, not the browser site.
- The downloadable core is the important integration surface for GenshinTeamsTracker because it exposes local config execution, local JSON result files, sample outputs, optimizer flags, version reporting, and engine update/version control. The browser/viewer path is useful later for attribution or optional result viewing, but it should not be the calculation dependency.
- The current project direction fits GCSIM best through the future Run Workspace:
  - DPS Dummy first.
  - Abyss later, starting with simplified target models.
  - Compare factual DPS from in-game HP/time data with sim DPS from GCSIM.

MVP recommendation:

- Treat GCSIM first as a simulator engine invoked locally.
- Keep HoYoWiki as the current local source for character/weapon stat catalogs in GenshinTeamsTracker until a deliberate data-source decision says otherwise.
- Use GCSIM's internal data for simulation correctness and maybe as reference data, but do not silently replace the existing HoYoWiki catalog path.

Useful sources:

- Repo: https://github.com/genshinsim/gcsim
- Docs: https://docs.gcsim.app/
- Web app: https://gcsim.app/

## 2. Invocation / Engine

Confirmed:

- Official docs list two CLI acquisition paths:
  - download `gcsim.exe` from GitHub releases;
  - build from source with Go under `cmd/gcsim`.
- Current release metadata checked through GitHub API on 2026-05-17:
  - latest stable tag: `v2.42.2`;
  - published: `2026-05-11T17:27:33Z`;
  - assets include `gcsim_windows_amd64.exe`, `gcsim_darwin_amd64`, `gcsim_darwin_arm64`, `gcsim_linux_amd64`, and `LICENSE`.
- Source release/build paths:
  - `cmd/gcsim/main.go` is the CLI entrypoint.
  - `scripts/build.sh` cross-builds `gcsim_windows_amd64.exe`, macOS binaries, and Linux binary.
  - `.github/actions/deploy-binary/action.yml` uploads those binaries to releases.
- Runtime commands from docs/source:
  - `./gcsim.exe -c test.txt`
  - `./gcsim.exe -c test.txt -out result.json`
  - `./gcsim.exe -c test.txt -out result.json -gz`
  - `./gcsim.exe -c test.txt -s -nb`
  - `./gcsim.exe -version`
- CLI flags confirmed in `cmd/gcsim/main.go` and docs:
  - `-c`: config path.
  - `-out`: result JSON output path.
  - `-sample`, `-sampleMinDps`, `-sampleMaxDps`: sample frame-log outputs.
  - `-gz`: compressed output.
  - `-s`: serve local result/sample to the GCSIM web viewer.
  - `-nb`: do not open browser when serving.
  - `-ks`: keep serving.
  - `-nr`: do not run sim, useful with sample generation.
  - `-substatOptim`, `-substatOptimFull`, `-options`, `-v`: substat optimizer.
  - `-update`: self-update from GitHub release.
  - `-version`: print binary version.
- `pkg/simulator` exposes Go functions such as `Run(context.Context, Options)` and `RunWithConfig(...)`.

MVP recommendation:

- Integrate by subprocess around the downloaded or bundled `gcsim_windows_amd64.exe`.
- Do not depend on the browser viewer for core calculation.
- Treat `gcsim_windows_amd64.exe` as the engine package to manage: download/verify/store version, generate a config, execute it, parse output, and keep the UI responsive with cancellation/timeouts.
- Store the engine binary path/version in app settings or a future engine manager.
- Include GCSIM version/hash in result cache keys and saved sim-result metadata.
- App-controlled update/download is safer than calling `gcsim.exe -update` silently.

Risk:

- Python/PySide cannot directly import Go packages. Library-style integration would need a separate Go wrapper, local RPC process, WASM bridge, or CGO/shared library work. Subprocess is the smallest stable bridge.
- GCSIM is volunteer-driven and live-service; new game versions may lag or change behavior.
- The CLI can consume significant CPU, especially optimizer modes and high iteration counts. Runner needs timeout/cancel.

Useful source paths:

- `cmd/gcsim/main.go`
- `cmd/gcsim/serve.go`
- `pkg/simulator/simulator.go`
- `pkg/model/save.go`
- `scripts/build.sh`
- `.github/actions/deploy-binary/action.yml`

## 3. License / Attribution

Confirmed:

- GCSIM uses the MIT License.
- Repo license path: `LICENSE`.
- MIT terms allow use, copy, modification, distribution, sublicensing, and sale, as long as the copyright and permission notice are included in copies/substantial portions.

MVP recommendation:

- If bundling or downloading a GCSIM binary, ship/display the GCSIM MIT license notice in an app "About / Third-party licenses" place.
- UI should label results as `sim DPS` or `GCSIM sim DPS`, separate from factual DPS.
- A GCSIM logo/link button can open `https://gcsim.app/`, but show a small "Open GCSIM website?" dialog before opening the browser.

Needs follow-up:

- Confirm whether the GCSIM logo/image asset has separate usage guidance. MIT covers the repository code, but logo/trademark expectations should still be checked before bundling a logo.

Useful source:

- License raw URL: https://raw.githubusercontent.com/genshinsim/gcsim/main/LICENSE

## 4. Config Format

Confirmed:

- GCSIM config is a text DSL, not JSON.
- Docs call the scripting part `gcsl`.
- A config contains:
  - simulator options;
  - character settings;
  - enemy/energy/starting-character settings;
  - action script/rotation.
- Config parser/source paths:
  - `pkg/gcs/parser/parseOptions.go`
  - `pkg/gcs/parser/parseCharacter.go`
  - `pkg/gcs/parser/parseTarget.go`
  - `pkg/gcs/parser/parseEnergy.go`
  - `pkg/gcs/parser/parseHurt.go`
  - `pkg/gcs/parser/parse_test.go`
- Important syntax:
  - `options iteration=1000 duration=90 swap_delay=12;`
  - `<char> char lvl=90/90 cons=0 talent=9,9,9;`
  - `<char> add weapon="<weapon_key>" refine=1 lvl=90/90;`
  - `<char> add set="<set_key>" count=4;`
  - `<char> add stats hp=4780 atk=311 er=0.518 cr=0.311;`
  - `target lvl=100 resist=0.1;`
  - `target lvl=100 type=dummy radius=2 pos=0,2.4;`
  - `active <char>;`
  - rotations use actions like `<char> skill, burst;`, loops, conditions, functions, and fields.
- GCSIM expects character/weapon/set names in its own key/shortcut space, not localized display names.
- Character `lvl` uses current/max level, for example `70/80` or `90/90`.
- Artifact `add stats` should be artifact stats only. Docs explicitly say not to add character/weapon base stats or set bonuses to `add stats`.
- Artifact main/sub stats can be split into multiple `add stats` lines. This is useful for preserving our `ArtifactBuildSnapshot` slot breakdown later.
- Optional params exist on character/weapon/set config lines through `+params=[key=value,...]`. Some mechanics require these params.

Minimal illustrative DPS Dummy-style config skeleton:

```txt
options iteration=1000 duration=90 swap_delay=12;
target lvl=100 type=dummy radius=2 pos=0,2.4;
energy every interval=480,720 amount=1;

bennett char lvl=90/90 cons=6 talent=9,9,9;
bennett add weapon="thealleyflash" refine=1 lvl=90/90;
bennett add set="noblesseoblige" count=4;
bennett add stats hp=4780 atk=311 er=0.518 pyro%=0.466 cr=0.311; # artifact mains
bennett add stats def%=0.124 def=39.36 hp=507.88 hp%=0.0992 atk=33.08 atk%=0.1984 er=0.1102 em=39.64 cr=0.331 cd=0.7944; # artifact subs

active bennett;
while 1 {
  bennett skill, burst;
}
```

Needs follow-up:

- Build a local mapping table from GenshinTeamsTracker stat keys to GCSIM stat keys:
  - likely direct-ish: `hp`, `hp%`, `atk`, `atk%`, `def`, `def%`, `er`, `em`, `cr`, `cd`, element damage keys like `pyro%`.
  - must verify every key used by Artifact Browser.
- Build a mapping table from our character/weapon/artifact set ids to GCSIM keys:
  - GCSIM key sources include `pkg/core/keys/*`, `pkg/shortcut/*`, and generated `*_gen.go`.
  - Do not feed localized names directly to config generator.

Useful docs:

- Config guide: https://docs.gcsim.app/guides/understanding_config_files/
- Config reference: https://docs.gcsim.app/reference/config/

## 5. Character / Weapon / Artifact Data

Confirmed:

- GCSIM includes internal character, weapon, artifact, enemy, and curve data.
- Source paths:
  - `internal/characters/<char>/...`
  - `internal/weapons/<class>/<weapon>/...`
  - `internal/artifacts/<set>/...`
  - `pipeline/pkg/data/avatar/*`
  - `pipeline/pkg/data/weapon/*`
  - `pipeline/pkg/data/artifact/*`
  - `pipeline/pkg/data/enemy/*`
  - `protos/model/data.proto`
- Base stat calculation is implemented in:
  - `pkg/core/player/character/basestat.go`
  - functions `AvatarBaseStat(...)`, `WeaponBaseStat(...)`, `AvatarAsc(...)`.
- GCSIM generated result contains character details and snapshot stats:
  - `protos/model/sim.proto`
  - `protos/model/result.proto`
  - `pkg/simulation/details.go`.
- `SimulationResult.incomplete_characters` exists in result schema. This can warn if a sim uses incomplete character implementations.
- Source snapshot inspected from cloned repo contained approximately:
  - 103 top-level character dirs under `internal/characters`;
  - 225 weapon configs under `internal/weapons`;
  - 50 artifact dirs under `internal/artifacts`.
  These are source-tree counts only, not a product promise.
- `ui/packages/data/src/latest_chars.json` exists and can indicate newly added characters for a GCSIM docs/data package version.

MVP recommendation:

- Generate GCSIM config from our `CharacterStatSnapshot` and `ArtifactBuildSnapshot`, but let GCSIM calculate its own runtime base stats/effects for the simulation.
- Use our HoYoWiki catalogs for app UI/stat display until a deliberate replacement/merge is designed.
- Capture GCSIM result `character_details`, `target_details`, `incomplete_characters`, and `sim_version` for traceability.

Risk:

- GCSIM and HoYoWiki may disagree temporarily after game updates.
- GCSIM mechanics may be incomplete for new characters/weapons or special systems.
- GCSIM applies weapon/artifact effects internally when modeled; our UI stat snapshot deliberately does not yet apply passive/set/resonance formulas. The two values should be shown as different concepts.

## 6. Default / Standard Builds

Confirmed:

- GCSIM has a CLI-only substat optimizer.
- Docs say the substat optimizer defaults to KQM Standard assumptions.
- CLI flags:
  - `-substatOptim`
  - `-substatOptimFull`
  - `-options`
  - `-v`
- Optimizer source:
  - `pkg/optimization/substatoptimizer.go`
  - `pkg/optimization/substats.go`
  - `pkg/optimization/opt_energy.go`
  - `pkg/optimization/opt_damage.go`
  - `pkg/optimization/opt_allstats.go`
  - `pkg/optimization/optstats/*`
- Optimizer options from CLI/docs:
  - `total_liquid_substats`
  - `indiv_liquid_cap`
  - `fixed_substats_count`
  - `fine_tune`
  - `show_substat_scalars`
- GCSIM also has a Config Database ecosystem (`simpact.app` / DB-related code) with config entries, tags, team summaries, and descriptions.

Unconfirmed:

- There is no confirmed reusable "KQM standard full build catalog" found in this pass.
- The substat optimizer is not the same thing as a full account artifact optimizer.
- Config Database entries are examples/community sims, not necessarily canonical standard builds.

MVP recommendation:

- Do not depend on GCSIM default/standard builds for first integration.
- First generate configs from the user's selected account/build data.
- Treat `-substatOptimFull` as a later research feature for account-independent estimates or bot heuristics.

Risk:

- The optimizer is documented as experimental and may use high CPU.
- It assumes specific config shape, especially separate main-stat/substat lines.

Useful docs:

- Substat optimizer guide: https://docs.gcsim.app/guides/substat_optimizer/

## 7. Enemy / Target Modeling

Confirmed:

- Config target syntax supports:
  - `lvl`
  - `resist` for all elements
  - per-element resist keys such as `pyro`, `hydro`, `physical`
  - `pos`
  - `radius`
  - `freeze_resist`
  - `hp`
  - `particle_threshold`
  - `particle_drop_count`
  - `particle_element`
  - `type=<monster_key>`
- Multiple targets are represented by repeating `target` lines.
- `type=dummy` is implemented in `pkg/enemy/types.go`:
  - huge HP;
  - 10 percent resist for supported damage types;
  - no particle generation.
- For named monster targets, GCSIM can derive monster HP/resist data from internal enemy data and applies a default Spiral Abyss multiplier of 2.5 unless `hp_mult` is provided.
- If target `hp` is set, docs say simulation duration is ignored and the sim runs until enemies die.
- `protos/model/sim.proto` result target fields include level, HP, resist map, position, particle drop data, name, and modified flag.

MVP recommendation:

- DPS Dummy MVP:
  - one `type=dummy` target, or one custom high-HP target with fixed resist;
  - fixed duration mode is simpler for comparing rotations;
  - factual dummy DPS remains app-owned, separate from sim DPS.
- Simplified Abyss later:
  - one or more static targets with known HP/resists/positions;
  - no promise of exact wave/phase/invulnerability modeling.

Risk:

- Full Abyss modeling is not just target HP. Waves, delayed spawns, shields, immunity, invulnerability, enemy movement, and phase logic are not obviously solved by basic target lines.
- Multiple targets exist simultaneously; this is not automatically a wave scheduler.

Needs follow-up:

- Investigate whether GCSIM scripts can approximate waves by target HP/death conditions, spawned enemies, or custom target behavior. No clean full-Abyss solution was confirmed in this pass.
- Verify current monster key coverage against any future Abyss data updater.

## 8. Optimizer / Build Search

Confirmed:

- GCSIM has substat optimizer functionality.
- It can run simulations repeatedly with custom stat allocation logic.
- It is available via CLI, not web, according to docs.
- It can output an optimized config, not a selected list of account artifact ids.

Unconfirmed:

- No complete account artifact inventory optimizer was confirmed.
- No direct GOOD/Artiscan artifact inventory search API was confirmed in this pass.

MVP recommendation:

- Do not use optimizer in the first GCSIM integration.
- Later, test optimizer only in DPS Dummy workspace with explicit warnings:
  - "best found / simulated estimate", not "absolute optimum".
  - Separate from the user's real selected artifact build.

Risk:

- Full artifact search across an account is combinatorially large.
- Substat optimizer can be CPU-heavy and may not correspond to real account artifacts.

Needs follow-up:

- Inspect `pkg/optimization` more deeply when optimizer becomes a concrete feature.
- Determine whether Genshin Optimizer export/import paths in the web UI can help bridge real artifact inventories, but do not assume it.

## 9. Output / Result Parsing

Confirmed:

- CLI prints a short human-readable summary through `SimulationResult.PrettyPrint()`.
- CLI can save full result JSON through `-out`.
- Source output paths:
  - `cmd/gcsim/main.go`
  - `pkg/model/save.go`
  - `pkg/model/marshal.go`
  - `protos/model/result.proto`
- Result JSON uses protobuf JSON via `protojson.MarshalOptions`:
  - `UseEnumNumbers: true`;
  - `EmitUnpopulated: false`.
- Important result fields:
  - `schema_version`
  - `sim_version`
  - `modified`
  - `build_date`
  - `sample_seed`
  - `config_file`
  - `simulator_settings`
  - `energy_settings`
  - `initial_character`
  - `character_details`
  - `target_details`
  - `incomplete_characters`
  - `statistics`
- Important `statistics` fields:
  - `iterations`
  - `duration`
  - `dps`
  - `rps`
  - `eps`
  - `hps`
  - `shp`
  - `total_damage`
  - `warnings`
  - `failed_actions`
  - `element_dps`
  - `target_dps`
  - `character_dps`
  - `dps_by_element`
  - `dps_by_target`
  - `source_dps`
  - `source_damage_instances`
  - `field_time`
  - `end_stats`
- DPS extraction path for MVP:
  - `statistics.dps.mean`;
  - optionally `statistics.dps.min`, `max`, `sd`, `q1`, `q2`, `q3`;
  - also capture `statistics.total_damage.mean` and `statistics.duration.mean`.
- `-sample` outputs detailed per-frame logs with schema in `protos/model/sample.proto`.

Risk:

- Compressed `-gz` output is saved with `.gz` suffix, but source uses `compress/zlib` and serves it with `Content-Encoding: deflate`. Do not assume Python `gzip` will read it; verify and likely use zlib/deflate handling.
- Proto3 JSON omits default zero values. Result parser must treat missing numeric fields carefully.
- `character_dps` is an array aligned with character order, not self-labeled in the proto. Pair it with `character_details` order.

MVP recommendation:

- Use uncompressed `-out result.json` first to reduce parser ambiguity.
- Later support compressed output only after a tiny zlib/gzip compatibility test.

## 10. Integration Architecture Notes

MVP recommendation:

- Future modules can be shaped like:
  - `GcsimEngineManager`
  - `GcsimConfigGenerator`
  - `GcsimRunner`
  - `GcsimResultParser`
  - `GcsimRotationModel`
  - `GcsimResultCache`
  - simulator UI panel/window
- Engine manager responsibilities:
  - locate bundled/downloaded binary;
  - verify version via `-version`;
  - keep MIT license text available;
  - explicit update/download action;
  - cache binary path/version/hash.
- Config generator responsibilities:
  - accept explicit `TeamSnapshot` / `CharacterStatSnapshot` / `ArtifactBuildSnapshot`;
  - map our ids/names/stats to GCSIM keys;
  - emit deterministic config text;
  - never read UI widgets directly.
- Runner responsibilities:
  - create temp working directory;
  - write config text;
  - call `gcsim_windows_amd64.exe -c config.txt -out result.json`;
  - capture stdout/stderr;
  - support cancel/timeout;
  - never block UI thread.
- Result parser responsibilities:
  - parse result JSON;
  - extract sim DPS and metadata;
  - preserve warnings, failed actions, incomplete characters;
  - keep raw config/result path only in debug/dev mode, not in public exports by default.
- Result cache key should include:
  - GCSIM binary version/hash;
  - config text hash;
  - team/build snapshot hash;
  - target setup;
  - rotation text;
  - iteration count;
  - simulator options.

Connections to current/future project data:

- `CharacterStatSnapshot`: source of character level, constellation, weapon, artifact contribution references, but GCSIM config still needs GCSIM keys and artifact stat values.
- `ArtifactBuildSnapshot`: should produce `add stats` lines and `add set` lines.
- `TeamCard` / `RunCard`: should display factual DPS and sim DPS separately.
- DPS Dummy mode: first consumer.
- Abyss mode: later consumer with explicit simplified target assumptions.

## 11. Recommended MVP

MVP recommendation:

1. DPS Dummy only.
2. One team.
3. One target:
   - default: `type=dummy`;
   - optional custom resist/level later.
4. Manual rotation text:
   - start with a text editor field;
   - later build rotation helper UI.
5. Use local/downloaded GCSIM binary:
   - not the browser as engine.
6. Generate config from selected team/build snapshots.
7. Run CLI in background worker with cancel/timeout.
8. Parse uncompressed JSON result.
9. Display:
   - `sim DPS`;
   - iterations;
   - duration;
   - total damage;
   - warnings/failed actions;
   - GCSIM version.
10. Keep factual dummy DPS separate from sim DPS.

Not MVP:

- Full Abyss simulation.
- Account artifact optimization inside the GCSIM integration itself. A separate
  real-account backend now exists in `run_workspace/artifact_optimizer/`; see
  `docs/handoff/ARTIFACT_OPTIMIZER.md`. GCSIM may later rerank its bounded top-M
  candidates, but its theoretical substat optimizer does not select real ids.
- Automatic rotation generation.
- KQM/default build guessing.
- Weapon/artifact recommendation scraping.
- Direct Go library embedding.

## 12. Risks / Blockers

Risk:

- Mapping our localized/account data to GCSIM keys is correctness-critical.
- GCSIM config must not receive localized display names.
- Some characters/weapons/mechanics can be incomplete or lag current game version.
- Our current `CharacterStatSnapshot` is deliberately not a full final stat calculator; GCSIM may include effects our UI does not.
- GCSIM output schema can change; result parser should validate `schema_version`.
- CLI execution can be CPU-heavy; isolate from UI thread and add cancel/timeout.
- `-gz` format uses zlib/deflate despite `.gz` suffix.
- Full Abyss wave/phase/immunity modeling is likely hard.
- Substat optimizer is experimental and not equal to real account artifact search.
- License is permissive, but logo/trademark presentation still needs care.

## 13. Open Questions / Needs Deeper Research

Needs follow-up:

- GCSIM key mapping:
  - where best to extract char/weapon/artifact key aliases from `pkg/shortcut/*` and generated key files;
  - how to maintain mapping in our app without importing Go.
- Binary update policy:
  - bundle one tested binary vs app-managed download from GitHub release;
  - how to verify checksum/signature for downloaded binary.
- Result parser:
  - build tiny parser fixture from a real result JSON;
  - verify compressed `-gz` with Python zlib vs gzip.
- Rotation editor:
  - decide whether first UI is free text, structured action list, or hybrid.
- GCSIM logo:
  - find official logo file/license/usage expectation before bundling.
- Config Database:
  - whether `simpact.app` / GCSIM DB can be queried safely/legal for examples;
  - whether tags/descriptions can help draft bot heuristics.
- Abyss:
  - whether GCSIM supports practical wave modeling beyond simultaneous targets;
  - how to express invulnerability/phases/shields if possible.
- Optimizer:
  - whether `pkg/optimization` can be used in subprocess mode for limited DPS Dummy build search;
  - whether it can accept real account artifact constraints without major new code.
- Data source:
  - whether GCSIM generated `protos/model/data.proto` data could eventually complement HoYoWiki catalogs;
  - do not switch sources until a separate mapping/freshness audit is done.

## 14. Useful Source Pointers

Official links:

- Repo: https://github.com/genshinsim/gcsim
- Releases: https://github.com/genshinsim/gcsim/releases
- Latest release page checked: https://github.com/genshinsim/gcsim/releases/tag/v2.42.2
- Docs root: https://docs.gcsim.app/
- CLI install docs: https://docs.gcsim.app/guides/installation/
- CLI reference: https://docs.gcsim.app/reference/cli/
- Config guide: https://docs.gcsim.app/guides/understanding_config_files/
- Config reference: https://docs.gcsim.app/reference/config/
- Substat optimizer docs: https://docs.gcsim.app/guides/substat_optimizer/
- License: https://raw.githubusercontent.com/genshinsim/gcsim/main/LICENSE

Repo/source paths inspected in a temporary clone:

- `README.md`: overview, web app, CLI release link, live-service status.
- `LICENSE`: MIT license.
- `go.mod`: module path `github.com/genshinsim/gcsim`, Go version.
- `cmd/gcsim/main.go`: CLI flags, run flow, optimizer flags, output/sample handling, self-update.
- `cmd/gcsim/serve.go`: local result/sample server for web viewer.
- `scripts/build.sh`: release binary targets, including Windows AMD64.
- `.github/actions/deploy-binary/action.yml`: release assets uploaded.
- `.github/workflows/deploy.yml`: tagged release flow.
- `.github/workflows/nightly.yml`: nightly release flow.
- `pkg/simulator/simulator.go`: config reading, parsing, simulation run, result generation.
- `pkg/model/save.go`: JSON and compressed output save.
- `pkg/model/marshal.go`: protojson marshal behavior.
- `pkg/model/print.go`: stdout summary fields.
- `protos/model/result.proto`: result JSON schema.
- `protos/model/sample.proto`: sample/frame-log schema.
- `protos/model/sim.proto`: character/weapon/enemy result schemas.
- `protos/model/data.proto`: internal data schema for avatars/weapons/artifacts/monsters.
- `pkg/gcs/parser/parseOptions.go`: option names.
- `pkg/gcs/parser/parseCharacter.go`: char/weapon/set/stat syntax.
- `pkg/gcs/parser/parseTarget.go`: target syntax.
- `pkg/gcs/parser/parse_test.go`: compact config examples.
- `ui/packages/docs/docs/guides/installation.md`: CLI install/build docs.
- `ui/packages/docs/docs/reference/cli.md`: CLI option docs.
- `ui/packages/docs/docs/guides/understanding_config_files.md`: config structure and examples.
- `ui/packages/docs/docs/reference/config.md`: options/enemy/reference syntax.
- `ui/packages/docs/docs/guides/substat_optimizer.md`: KQM Standard substat optimizer docs.
- `pkg/core/player/character/basestat.go`: character/weapon base stat calculation.
- `pkg/simulation/setup.go`: target/team setup and resonance implementation.
- `pkg/simulation/details.go`: character details and final snapshot stats in output.
- `pkg/enemy/types.go`: dummy target, named monster target, Abyss HP multiplier.
- `pkg/optimization/*`: substat optimizer implementation.
- `backend/pkg/services/db.proto`: GCSIM DB entry/summary schema.
- `ui/packages/storybook/src/stories/samples/sampleResult.json`: example result JSON shape.
- `ui/packages/components/src/stories/samples/sampleDBEntries.json`: example DB entries/configs.
