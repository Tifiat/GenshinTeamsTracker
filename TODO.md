# TODO: GenshinTeamsTracker

This file is for future agents. Keep it current, English, and mostly ASCII. Completed history should stay compact unless it changes future architecture or implementation choices.

## Workflow Rules

- Read `CODEX.md` first.
- Keep tool usage narrow and cheap.
- Do not run tests, app startup, imports, DB scans, or broad validation unless the user asks or the change needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- Avoid scanning generated/private state:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - large JSON/image folders
- Expensive repeatable UI work should use both in-memory cache and persistent cache under `data/cache/...`; do not leave image processing/parsing in hot UI paths.
- Update this file only with active tasks and useful follow-ups.
- Do not bring Known Bugs into planning/discussion unless the user explicitly asks about bugs or the affected area.

## Known Bugs

- [ ] Changing app language can change the window size, narrowing the character selector area; the artifact grid is not recalculated afterward.
- [ ] Editing the timer for one room does not adjust overlapping room timers, so impossible totals can appear, for example room 1 ends at 9:50 (10s), room 2 ends at 9:56 (-6s), total 4s.
- [ ] After dragging a character into a team slot, the same character remains available in the character grid; characters already placed in slots cannot be moved to another slot or another team's slot.

## Current Artifact Browser State

- Artifact Browser is stable enough to stop treating it as a pure prototype, but direct main-UI integration should wait for the Run Workspace architecture below.
- Completed manual smoke passes: Build Target Selector, target persistence, build/target preview, JSON import/clear, build preset lifecycle, and custom sets.
- Compact preset rows show set-bonus metadata, sands/goblet main-stat badge, and cached set-bonus icons.
- Build target preview strip is a baked pixmap strip with persistent caches; it is not many child widgets and intentionally has no tooltips.
- Build preview set bonus cells and compact preset-row set bonus icons use stored 2p/4p set bonus descriptions and custom tooltips.
- Region filters are implemented through `assets/filters/Statue.png`; character regions come from HoYoWiki character list `menu_id=2` and are cached at `data/cache/hoyowiki/character_region_catalog.json`.
- Region filters are multi-select: OR inside the region group, AND with element/weapon/rarity.
- Artifact Browser has fixed bottom-row `Import JSON` / `Clear JSON` buttons; JSON clear deletes only `json_imported=1` + `import_source='artiscan'` artifacts and clears affected build preset slots.
- Sort and Sets popups toggle closed on repeated button click and order game/custom sets by owned piece count descending.
- Region joins are isolated around normalized localized character names; stable game ids are not available from the current HoYoWiki path.

## 1. Pre-Integration Architecture

- Do not keep developing the current main-window right panel as the final structure. It is legacy/prototype UI and should be replaced by a shared Run Workspace.
- Do not blindly discard useful legacy behavior. Extract reusable logic into modules/helpers when it fits the new model, for example timer editing that reacts to mouse wheel and updates values.
- Separate these domains clearly:
  - Account / Inventory: imported characters, weapons, artifacts, build presets, local catalogs.
  - Team Builder: current team composition, selected characters/weapons, selected artifact builds, calculated stats, resonances.
  - Scenario / Run: Abyss run, DPS Dummy run, future PvP match, enemy/room/rules metadata, timers, results.
  - Presentation / Export: shared TeamCard/RunCard components, history UI, PNG/XLSX export, simulator result presentation, PvP result export.
- Saved run history must store immutable snapshots, not live references to current account/build state. If artifacts, levels, weapons, or presets change later, old saved runs must not silently change.
- Snapshots must preserve structured information, not only images: characters, weapons, constellations/refinements when available, artifacts, set bonuses, stats, timers, run metadata, and enough data for useful later tooltips/details.

## 2. Main Run Workspace

- Replace the legacy right panel with a Run Workspace that has at least two modes/tabs: Abyss and DPS Dummy.
- Active mode controls team layout, visible inputs, which history tab opens from "open history", and which run type is saved.
- If the panel is on DPS Dummy, history opens DPS Dummy history. If it is on Abyss, history opens Abyss history.
- Abyss mode:
  - two teams;
  - rooms/chambers;
  - timers per team per chamber;
  - total timer;
  - factual DPS based on enemy HP and clear time when enemy data exists;
  - save run snapshot into the current Abyss season.
- DPS Dummy mode:
  - one team;
  - one DPS result / target setup;
  - same TeamCard logic;
  - saved into DPS Dummy history;
  - later connected to simulator UI.
- Prefer UI wording "DPS" or "factual DPS" for HP/time calculation. Keep simulator output separate as "sim DPS" with explicit GCSIM label/logo where applicable.

## 3. Shared TeamCard / RunCard

- Create reusable TeamCard / RunCard concepts shared by main Run Workspace, Abyss history, DPS Dummy history, export, simulator window, and most PvP post-draft flows.
- PvP may use different visuals where needed, but the underlying team composition logic should remain reusable.
- A team contains four characters. Each character tile/card should eventually show portrait, element, constellation, weapon, refinement when available, compact artifact set bonus info, useful current stats, and tooltip/details with full snapshot information.
- Reuse the compact artifact set bonus rendering/tooltips already implemented in Artifact Browser where possible. Do not create a second incompatible set-bonus representation unless there is a concrete reason.
- Visual design problem: weapon and artifact bonus info must stay readable without covering the portrait too much. Explore small attached badges/strips rather than fully overlaying the portrait.
- Pre-release visual pass: round/crop normal character preview portraits only after all card-like windows and slots are present, so final card treatment is consistent.

## 4. Team Selection and Snapshot Model

- New team builder should support drag from available list into slots, drag between slots, drag between teams, swap characters, clear slot, and disabled/hidden used characters in the available list.
- Used weapons should disappear if unique. Weapon duplicates are first-day/future patch unless current data can distinguish instances safely; do not overcomplicate MVP.
- Artifacts are not consumed by PvP deck rules unless a future ruleset explicitly says so. For normal team building, selected builds/artifacts should be shown and snapshotted.
- Snapshot actual selected artifact/build data, active set bonuses, and relevant stats when saving a run. Do not rely only on a live build preset id.

## 5. Artifact Browser Integration Into Main UI

- Do not integrate Artifact Browser as a disconnected button. It should feed artifact builds/build presets into Team Builder and TeamCard.
- The current Artifact Browser can still open as its own window, but main UI needs a clean path to select/use builds in teams.
- Preserve build presets as shared ownership categories, not "one build = one character".
- A preset can belong to Universal and/or multiple character targets; selected target filters use intersection semantics and should not auto-include Universal unless Universal is selected.
- Keep build data separate from visual skin/delegate rendering.

## 6. Abyss History / Seasons

- Redesign history around shared RunCard/TeamCard components. The old history grid is not final and will not scale once weapons, set bonuses, simulator values, filters, and metadata are added.
- Abyss history structure:
  - top-level tab: Abyss;
  - inside: seasons/periods;
  - each season page shows period/timestamp, floors/chambers/enemies when known, total HP when known, saved runs, filters/sorting, and export.
- Previous seasons can be read-only or mostly read-only.
- New saved Abyss runs go into the current season.
- Saved run history must be immutable snapshots, not live references to current account/build state.

## 7. DPS Dummy History

- DPS Dummy history should use the same visual language as Abyss history but simpler.
- One team per result.
- Store dummy/target setup if available, factual DPS, sim DPS later, filters/sorting, and export.
- The DPS Dummy history button should open when the Run Workspace is in DPS Dummy mode.

## 8. Abyss Data Updater and Enemy Model

- Need future AbyssSeason / room / chamber / wave / enemy model.
- For each Abyss chamber/side, data should ideally support enemies, waves, enemy HP, total HP, resistances, immunities, special states, invulnerability/phases where available, and icons.
- Do not require this data for the app to function.
- Investigate current Abyss enemy data sources. The user has seen this information on third-party leak/info sites, so at least one source likely exists.
- Do not rely on only one source if multiple are available. Design fallback logic so one unavailable source does not break the feature.
- Do not download a huge historical database initially. Update current Abyss info at the relevant time and create a new season/page if current Abyss data changed.
- No network / no data fallback:
  - still create/use an Abyss period based on the system date;
  - use the 16th day of month as the split point;
  - use a localized period label such as `16.05 - 16.06.26`;
  - show "no data" / localized equivalent where enemy data/HP is needed;
  - factual DPS from enemy HP is unavailable when HP data is missing.
- Keep in mind HP/time DPS is not exact damage dealt because waves, immunity, phases, shields, invulnerability, movement, and similar mechanics can distort it.

## 9. Stats / Resonance / Static Catalogs

- Team selection UI should eventually display current stats for each character.
- Stats may need character base stats by level/ascension, weapon base stats/substats, weapon level/refinement, artifact main/sub stats, static artifact set bonuses, and resonances.
- Investigate whether GCSIM data can be reused for character/weapon base stats. If not, create/update a local auto-updatable static catalog.
- Do not fully parse arbitrary set bonus text into formulas for MVP.
- Reasonable stats MVP:
  - calculate from known structured data;
  - include static bonuses only when explicitly modeled;
  - skip conditional bonuses or mark them as condition-required/not automatically included;
  - add manual toggles later if needed.
- Need data-driven resonance model for elemental resonances, lunar resonance, witchcraft/sabbath resonance, and future resonance-like systems.
- Elemental resonances can usually be inferred from character elements. Other systems may require character traits/tags from another source or a local auto-updatable/seeded table.
- UI should show active resonances, why each resonance is active/inactive, description tooltip, and involved characters.
- For lunar resonance, first implementation can show total bonus, contribution by character when known, and clear explanation when activation is impossible.
- Refactor future catalog/update code into a common location instead of scattering it in UI modules. Use bundled seed/static data, downloaded cache, schema version, source, timestamp, language, and updater modules.
- App should work offline with last known or bundled data.
- Data categories likely needing common catalog/updater support: artifact set catalog/icons, character base stats, weapon base stats, resonance definitions, current Abyss enemies/HP, monster stats, standard build profiles, tournament rulesets.

## 10. Export

- Abyss history and DPS Dummy history need export.
- Target formats: PNG/image for visual sharing and XLSX for analysis/comparison. CSV/HTML can be optional fallback later.
- PNG export should reuse the same visual components/cards as history where practical.
- XLSX should be data-oriented and include season/period, date, run type, chamber/side, team, characters, weapons, artifact set bonuses, timers, factual DPS if available, sim DPS if available, notes/warnings.
- Do not prioritize import of history as a separate feature. Later full offline profile import/export can include history.

## 11. GCSIM Integration

- GCSIM is a major future feature and should influence architecture now, but implementation comes later.
- Each team/run card should eventually have simulator action, GCSIM logo/label, and result area for sim DPS.
- Clicking the GCSIM logo should show a dialog like "Open GCSIM website?" before opening the official GCSIM site, for useful attribution and license/credit clarity.
- Before bundling or modifying GCSIM, verify current license/attribution requirements. It is believed to be MIT-compatible, but do not rely on memory.
- Simulator window should receive team data from TeamCard/TeamSnapshot: characters, constellations, weapons, refinements, artifacts, stats, set bonuses, talents if available, rotation, target/enemy setup.
- Implement GCSIM for DPS Dummy first:
  - one team;
  - one target;
  - configurable HP/resistance or supported target setup;
  - rotation editor;
  - sim DPS result;
  - comparison with factual dummy DPS if available.
- GCSIM for Abyss later should start with simplified modes: single target, multi-target, simplified room, manual target. Do not promise perfect full-Abyss simulation.
- For Abyss, compare factual DPS from HP/time with sim DPS from simplified/current selected target.
- Later GCSIM research/tasks:
  - CLI/binary/library options;
  - config format;
  - enemies/targets;
  - rotation representation;
  - output format;
  - cancellation/timeouts;
  - result parser;
  - optimizer functionality;
  - whether local GCSIM data can provide character/weapon base stats;
  - where standard/KQM-style builds come from.
- Possible architecture names: `GcsimEngineManager`, `GcsimConfigGenerator`, `GcsimRunner`, `GcsimResultParser`, rotation editor, result cache keyed by team/build/rotation/target/gcsim version.

## 12. KQM / Standard Builds Research

- Investigate where GCSIM gets default/standard character builds.
- Do not hardcode "KQM standards" until source, license, and data format are verified.
- Research whether this data is actually KQM standards, where it is stored, whether it can be used legally/technically, and what it contains: artifacts, talents, weapons, rotations, assumptions.
- Future uses: simulator fallback, draft bot, account-independent team estimates, comparing user builds to standard baseline.

## 13. Artifact Optimizer

- Future advanced feature: find the strongest build on the account for a selected team and rotation.
- Target DPS Dummy / simulator workspace first. Do not attempt full Abyss optimization initially.
- Full optimization across four characters, thousands of artifacts, set bonuses, off-pieces, and multiple rooms is combinatorially huge. Use heuristics, not full brute force.
- Potential staged approach:
  - use current or standard build;
  - run simulation;
  - estimate damage share;
  - choose candidate set templates;
  - select top-N artifacts per slot/stat weighting;
  - generate limited candidate builds;
  - simulate top-M candidates;
  - cache results;
  - show "best found", not "absolute optimum".
- Investigate whether current GCSIM already has usable optimizer-like functionality.
- Keep the user's simplified idea for research: use default standards, test set templates quickly, identify promising configurations, apply filters, then search best artifacts matching the configuration.

## 14. Offline Profile

- Current profile import/export should eventually become full offline profile import/export, not partial character/profile data.
- Future full profile should include, where safe: account characters, weapons, artifacts DB, build presets, run history, settings/local state needed for offline use, and relevant local catalog/cache data if appropriate.
- It must not include cookies, auth tokens, browser profile/session data, or private debug dumps.
- Use versioned profile format and safe restore/backup semantics.
- When improving offline profile export/import, include `data/hoyolab/account_language.json` alongside account details, characters, weapons, and crop manifest.

## 15. Tournament / PvP

- PvP is experimental and important long-term, but do not mix it into MVP before normal run/history/simulator features work well.
- General PvP flow:
  - select/import tournament ruleset;
  - build deck according to rules;
  - enter lobby;
  - picks/bans draft;
  - after draft, move to team composition;
  - compose teams only from picked characters;
  - select weapons only from deck weapons;
  - account artifacts are unrestricted by default;
  - enter timers/results;
  - confirm results;
  - export verified result image.
- Future custom tournament system idea: balance not only by character cost/tier but also by account artifact strength. Keep this as design/research, not immediate implementation.
- Investigate existing tournament systems/sites. Known possible source: `https://gentor.vercel.app/planilhas`. Also investigate similar sites, spreadsheets, Discord-provided XLSX, CSV, or JSON data.
- Start with manual XLSX/CSV/JSON ruleset import before website scraping/import.
- Ruleset model should be data-driven and may include character costs, constellation costs, tiers, tier counts, deck limits, pick/ban order, room/team rules, timer rules, weapon/artifact restrictions, special bans, and tournament-specific changes.
- Deck builder should evaluate total cost, tier constraints, invalid choices, and why a deck is invalid.
- Lobby/networking stages should be realistic:
  - local/hotseat lobby;
  - LAN/direct IP or manual connection;
  - import/export lobby state fallback;
  - investigate P2P with connection code;
  - investigate STUN/signaling/relay;
  - optional user-hosted relay or future server only if resources/donations justify it.
- Do not promise fully reliable serverless P2P; NAT, CG-NAT, firewalls, routers, and provider restrictions can break direct connections.
- PvP roles: player 1, player 2, spectator, moderator/judge, host.
- Draft engine must be generic/data-driven and support ban order, pick order, timers, locked picks, unavailable characters after pick/ban, rule validation, and action log.
- PvP result confirmation should bind confirmations to a state hash. Any result change after one player confirms clears that confirmation. Final means both players confirmed the same unchanged state inside the app.
- Do not claim the app guarantees real-world truth of entered timers. It can guarantee only that both players confirmed the same unchanged in-app result state.
- Export result image should include players, rooms, teams, timers per room/run, total timers, winner, confirmation status, statement like "confirmed by both players in GenshinTeamsTracker", and maybe session id/hash.
- PvP multi-run timer logic should support cumulative totals across games.

## 16. Draft Bots

- Future bots should let the user practice drafts when no one is available.
- Start with a rule-based bot, not global self-learning.
- Bot should consider current Abyss, tournament rules, cost/tier limits, enemy features, elements, immunities/counter-picks, team archetypes, synergy/anti-synergy, and rough character strength.
- Possible later stages: local imitation bot trained from user draft history, opt-in global draft data only with privacy policy/infrastructure, anonymization, and explicit consent.
- Bot logic should use metrics/tags, not only memorized character names, so new characters are not ignored.
- Useful tags/metrics: role, element, archetype, pick/ban priority, synergy, anti-synergy, Abyss suitability, historical pick/ban rate when available.
- After draft, bot should assign picked characters into teams/rooms using Abyss enemy features, similar GCSIM team/rotation data, KQM/default standards, assumed fallback talents, reasonable weapon fallback, and other available structured data.

## 17. Donation / Support Page

- Future non-core task: add a support/donation page/dialog.
- It should say users can support development and can potentially donate toward a specific major feature, but specific feature requests should be discussed with the developer first for feasibility.
- Mention that some features may depend on external APIs, licenses, servers, infrastructure, or third-party data, so not every requested feature is guaranteed feasible.
- Do not clutter core UI with donation content.

## Other Future / Maintenance Items

- Add color highlighting for build summary Crit Value and Proc Count later; choose thresholds/colors first.
- Later unify reset controls in target selector, sort popup, and sets popup.
- Future polish: make Sort popup and Sets popup selection behavior visually consistent with artifacts/targets/presets.
- First-day/future patch: automatic proc counting for imported Artiscan artifacts.
- Check other export/import services and compatibility.
- Do not do final cleanup of old DB physical schema until the new browser path is stable.
- Later migration: recreate/drop old `artifacts.icon_id` and `artifact_icons` physical leftovers if they still exist in local DBs.
- Keep `artifact_set_piece_icons` as the browser icon source by `(set_uid, pos)`.
- Do not reintroduce per-artifact icon cache or `artifact_icons` fallback.
- Keep `ru`, `en`, and `pt-br` locale files in sync when adding UI strings.
- Commit seeded artifact catalog resources when ready: `data/static/artifact_set_catalog.json` and `assets/artifact_sets`.
- Keep local account/generated state ignored: `data/hoyolab`, `data/artifacts.db`, `assets/hoyolab`, browser profile/session/debug/download outputs.
- Keep Artiscan sample files under `samples/artiscan/` unless a future import task needs another layout.
- Retry normal `git push` for local commit `1ae2de6` after previous GitHub Internal Server Error; do not force-push.
