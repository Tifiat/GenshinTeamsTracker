# PvP Seat Profile And Package Handoff

Purpose: canonical contract/status map for the second-player data provider and
portable PvP profile package. The PvP product flow remains in
`PVP_V0_CONTRACT.md`; this file owns the package boundary, independent seat data
and shared neutral visual assets.

## Agreed Implementation Order

1. Finish the two-seat provider/schema so Player 1 and Player 2 can expose
   independent account data, decks, constellations and equipment source data
   without merging either profile into the normal account. Define the minimal
   source schema and explicit artifact/build-preset inclusion rule first;
   character portraits are shared neutral assets keyed by stable game id.
2. Replace the current development `.gttpvp` archive with a validated,
   privacy-safe, portable profile export/import that implements that schema.
3. Only then capture/import the second HoYoLAB account and produce the requested
   three or four deck archive. That workflow must use isolated temporary/output
   paths; its only durable result is the archive selected by the user, not
   additional project or primary-account files.

Do not create a synthetic or second-account archive against the current
development format and then treat it as a stable fixture. That would freeze the
known schema and portability defects into user data.

## Current Reality

<!-- handoff-current: pvp-profile-package -->
2026-10-04: the v3 implementation constructs a new portable SQLite slice from
explicit tables/columns, reads the source without writes, embeds deduplicated
neutral PNGs, and validates its staged export through the importer before an
atomic output replacement. Imported data is checked before a separate managed
runtime database is populated for existing account readers. The normal account
and local Decks directory are never import destinations.

The agreed inventory scope is `all_artifacts_deck_character_builds`: all
artifacts, deck-selected characters/weapon stacks, and saved builds explicitly
targeting those characters or their engine keys. Universal/unrelated builds,
normal equipment ownership, source metadata, paths, history, tags, auth and
debug data are excluded. Selected weapon static display effects and passive
reference text are transported without full catalogs or source metadata.
Nickname/locale metadata remains optional. All transported manifest/deck/ref
text shares SQLite's absolute-local-path rejection; normal public text is
preserved. Main-target privacy and browser compatibility checks are recorded in
the [integration receipt](integration_receipts/2026-10-04_ready_workers.md).
Play requires period metadata to
match current direct HoYoLAB authority; export fills it from validated captured
dates. Local admission, scoped execution and date-precision limits are owned by
`PVP_BUILD_SERVICES.md`. Existing v3 archives with missing/stale period metadata
need re-export; package/schema validation itself does not certify currentness.

One transparent portrait per game id is reused across seats, scopes, Pick/Ban
and result cards. Per-seat stats and fresh runtime equipment remain independent.
The local `portrait` source layer is preferred; the archive fills missing ids
or missing local files, including shared characters. All-shared decks keep
local portraits without switching images between seats.

The v2 foundation's focused verification is retained below as dated evidence.
Current v3/build-service followup verification is in `PVP_BUILD_SERVICES.md`.
Real Decks/Play
acceptance and the second-account 3-4-deck archive remain pending. The user owns
all smoke tests and has forbidden Computer Use; no application smoke was run.

Next: the user's manual sequence below, then an isolated real second-account
source (path requested, not yet provided). Old v1/v2
development archives are rejected and require re-export; v3 remains under
development until real-account acceptance.
<!-- /handoff-current -->

## Target Seat Provider Contract

Each seat has one immutable source provider plus fresh match-local runtime
equipment state. The provider must expose, directly or through typed services:

- profile metadata needed by setup/admission, including optional nickname,
  locale, and Abyss-period identity;
- its own deck preset collection;
- its own SQLite/source-data boundary for characters, observed weapon stacks,
  artifacts, and build presets included by the package contract;
- character and weapon presentation assets keyed by stable game ids; neutral
  character portraits are reusable across seats;
- package/provider lifecycle and cleanup.

Player 1 and Player 2 providers are independent even when both contain the same
`character_id`. Backend draft identity stays one stable game id, while
constellation, level, display metadata, equipment inventory and build presets
remain seat-scoped. Never solve this by rewriting ids or merging the imported
rows into the main account DB.

Draft uses one shared neutral portrait per `character_id`, including pool and
result cards. Local/common assets and packaged assets resolve into that shared
presentation map; no per-seat portrait map or pick/ban image switching is
required. Local paths remain UI/provider data and must not enter `unified_pool`,
session identity, reducer actions or hashes.

## Draft Ownership And Image Rules

Ownership styling is independent of whose turn it is:

PvP uses the transparent `portrait` source layer without a baked background,
element or constellation badge. Existing per-seat constellation badges remain
independent overlays, so shared cards can show each player's C on one portrait.
The same image is valid for both seats; account-browser crops and background
composites are not source portraits. PvP may reuse a local source layer by game
id even when the account-browser crop differs; account-specific History
variants still require a matching browser crop.

- Player-1-only card: full Player 1 frame and Player 1 constellation badge on
  the left;
- Player-2-only card: full Player 2 frame and Player 2 constellation badge on
  the right;
- shared card: outer frame split left Player 1 / right Player 2, with each
  seat's constellation badge on its side;
- active-turn color must not recolor all available cards. Turn/action state is
  already shown by the central turn board, schedule, legal visibility/click
  state, and semantic pick/ban styling.

All pool scopes, Pick/Ban actions and result zones use the same neutral portrait
for the same `character_id`. Ownership and action meaning come from the existing
frames, badges and result-zone styling, not from changing the bitmap.

Prefer an existing local transparent portrait, then the packaged portrait if
the id or local file is missing, then a transparent placeholder. Shared
characters use the local file when present. When all characters are shared and
available locally, no imported character bitmap is selected. Resolve one shared
presentation map independently of the active seat/action. Missing assets never
change ownership or legality.

## Target Portable Package

The v3 package is a versioned ZIP built from an explicit allowlist. Its logical
contents are:

- manifest: format/schema version, creator/app version, optional public profile
  metadata, locale/Abyss-period identity, counts, file hashes, and content map;
- selected deck presets;
- a minimal SQLite profile slice containing only the schema/tables/columns and
  rows required by those decks and the agreed artifact/build-preset scope;
- package-relative asset manifest keyed by stable character/weapon ids;
- required neutral character portraits and weapon bitmap files, deduplicated
  by stable id/content where practical; no per-seat character image variants.

The core members are `manifest.json`, `decks.json`, `account_slice.sqlite` and
`assets.json`; bitmaps use content hashes under `assets/`. The package and SQLite
schema versions are 3; inner deck presets and the asset manifest keep their own
version 1 schemas. Exact SQLite DDL/column allowlists live in
`run_workspace/pvp/profile_schema.py`, not in the application's full schema.

Inventory scope is `all_artifacts_deck_character_builds`, chosen by the user:
export the full artifact inventory and substats, only its referenced set
descriptions/names, and saved builds targeting characters in the selected decks
(by character id or validated engine key). Keep only relevant build targets;
omit universal/unrelated builds. Remap local artifact/build/stack row ids inside
the slice; preserve stable game/catalog ids and observed stack fingerprints.
Normal equipment is not carried into a new PvP match.
Weapon display effects are restricted to exported weapon ID/refinement pairs;
passive references are restricted to exported weapon IDs. Imported runtime
artifact-set effects are rebuilt from the packaged descriptions, without
modifying the immutable portable slice or source account.

The current Decks export action includes the whole saved preset collection;
API callers can pass `deck_ids` to select a subset. Every included deck must be
legal under the supported Free Draft system before the archive is published.

Images are decoded and re-encoded as plain RGBA PNGs to remove metadata and
preserve transparency. Default character export reads the raw `portrait` layer,
not the `pvp` background composite. A missing source image gets a declared
transparent character placeholder (weapons keep a neutral placeholder), so
offline display never requires an old machine's path or a network URL. Explicit
character assets supplied to the exporter must already be source portraits.

Never include cookies, auth tokens, browser profiles/sessions, raw HoYoLAB
responses, debug dumps, unrelated account rows, normal run/history state,
absolute paths, or machine-local SQLite row ids used as cross-file identity.

## Import And Lifetime Rules

Import must validate before Play can select the provider:

- safe member names, duplicate entries, allowed compression/size limits, and
  required files;
- manifest/schema version and per-file hashes;
- SQLite header/integrity, explicit table/column allowlist, and required schema;
- every deck character/weapon reference against the imported source rows;
- every asset-manifest entry against an archive member and stable id;
- deck legality under the selected draft system.

The portable imported slice is immutable source data. A separate compatibility
DB supplies existing readers without altering that slice. The selected provider
lives until replacement, return to the local provider, workspace close or app
exit. Match teardown discards match equipment/context while retaining the
selected profile for another match. Neither its decks nor equipment enter the
normal local account.

An active scoped GCSIM reader retains the imported runtime before dispatch.
Provider close blocks new readers immediately and defers its managed-directory
removal until the final reader releases it after execution/cancellation.

Archive limits are 128 MiB for the file and total unpacked content, 64 MiB per
non-JSON member, 1 MiB per JSON member, 4096 members and a maximum compression
ratio of 200. Only stored/deflate
regular files are accepted. Bitmaps are bounded to 16 MiB and 2048x2048 pixels;
row/type/value bounds and exact schema checks run before runtime hydration.

## Required Regression Coverage

- two providers can contain the same character id with different
  constellations, levels and equipment without overwriting each other's data;
- Player scopes, shared Pick/Ban actions and result zones reuse one neutral
  portrait per id while keeping per-seat constellation overlays correct;
- all-shared decks retain local portraits; the archive supplies missing ids and
  missing local files even for shared characters;
- exported source portraits preserve alpha without using background composites;
- ownership frame/badges do not change when the active seat changes;
- exported package remains usable after the source DB/assets are unavailable;
- exported SQLite contains no table/column/row outside the allowlist and no
  absolute/local paths;
- malformed DBs, broken hashes, missing assets, unknown deck references,
  oversized members, and traversal/duplicate entries are rejected;
- importing/replacing/closing a profile leaves the main account DB, local deck
  directory, normal equipment, and project files unchanged.

## User-Owned Manual Acceptance

1. In Worker4, save valid decks and use Decks → Export to produce a new v3
   `.gttpvp` outside project/account paths.
2. In Play, import it for Player 2. Check the imported deck choices and that the
   local Decks list stays unchanged. If available, use a real profile containing
   different constellations for a shared character and a character absent from
   Player 1.
3. Start Draft, switch Unified/Player scopes and complete Pick/Ban. Check one
   transparent portrait per character, correct per-seat constellation badges, stable owner
   frames and visible imported-only characters. Continue through team/weapon
   assignment and compare each player's weapon inventory.
4. Clear the active draft in Play, replace the profile and choose Local. Check
   that failures preserve a previously valid selection and normal equipment is
   unchanged. Close the app normally; do not delete source account files as part
   of this check (source-independence/cleanup are covered by temp-fixture tests).

This manual sequence is pending user execution, not a passed UI result.

## Focused Verification Receipt

The initial v2 baseline on 2026-10-04 passed 43 backend and 22 headless tests.
The final rerun after the transparent-portrait clarification passed 44 backend
and 25 headless tests, using the main checkout's dependency interpreter
read-only because Worker4 has no local venv. Tests and all fixture databases,
decks, images and packages ran in Worker4-owned temporary paths. No account
capture, smoke module, application launch or rules-source import was run.

| Scope | Tests | Result |
| --- | --- | --- |
| Portable schema/privacy/remapping, selected build/weapon scope and existing runtime readers (`test_profile_schema`) | 6 | PASS |
| Archive export/import, hashes, ZIP/schema/reference/bitmap/size failures, transparent source layers, atomic output and cleanup (`test_profile_package`, `test_profile_package_validation`) | 17 | PASS |
| Existing deck/preset/observed-stack identity (`test_deck`, `test_deck_preset`, `test_weapon_identity`) | 21 | PASS |
| Two-profile integration, all-shared local priority, missing-file archive fallback and lifecycle (`test_pvp_profile_integration`) | 5 | PASS |
| Existing PvP start/owner frames/result zones/self-vs-self/runtime isolation/clear/imported routing/right-panel host cases (`test_pvp_browser`, selected cases) | 8 | PASS |
| Transparent common source/foreign profile/asset helper regressions (`tests/ui/character_assets/test_character_assets.py`) | 12 | PASS |

The malformed-database case initially exposed an open SQLite connection that
blocked managed-directory cleanup on Windows. The read-only connection setup
now closes on failure; the final rejection/cleanup regression passes. Bitmap
checks also decode pixels and reject metadata after pixel chunks, not just image
headers. These checks do not establish a real-account/UI pass or performance
measurement. Handoff/coordination structure checks pass; semantic closeout keeps
the manual and second-account gates open.
