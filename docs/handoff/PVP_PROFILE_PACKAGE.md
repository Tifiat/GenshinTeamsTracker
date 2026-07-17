# PvP Seat Profile And Package Handoff

Purpose: canonical contract/status map for the second-player data provider and
portable PvP profile package. The PvP product flow remains in
`PVP_V0_CONTRACT.md`; this file owns the package boundary and the per-seat visual
data rules.

## Agreed Implementation Order

1. Finish the two-seat provider/schema so Player 1 and Player 2 can expose
   independent account data, decks, constellations, equipment source data, and
   visual assets without merging either profile into the normal account.
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

`run_workspace/pvp/profile_package.py` and the Decks/Play buttons are a
development prototype, not a completed profile exchange feature.

The current `version = 1` ZIP contains only:

- `manifest.json`;
- `decks.json`;
- `account_slice.sqlite`.

Useful behavior that already exists:

- archive member names are allowlisted and traversal names are rejected;
- imported SQLite is materialized under a managed temporary directory;
- an imported provider is seat-scoped and is not restored into the main app DB;
- deck presets are selected from the imported provider in Play rather than
  copied into the local Decks directory.

Known blockers before the format is share-safe:

- export starts by copying the whole local `artifacts.db` and deletes rows only
  from a small account-table subset; unrelated tables, presets/catalog rows,
  source metadata, and local-path fields can remain;
- bitmap assets and a package-relative asset manifest are absent, so a package
  is not visually autonomous on another machine;
- import validates the ZIP/JSON envelope but does not validate the SQLite
  schema, required rows, deck-to-DB references, asset references, integrity, or
  privacy allowlist;
- the Draft workspace still resolves all portraits through one host
  `character_assets` map, so imported per-seat images are ignored during
  pick/ban;
- the internal version number is not a promise of public compatibility. It may
  be replaced or migrated while the feature remains development-only.

## Target Seat Provider Contract

Each seat has one immutable source provider plus fresh match-local runtime
equipment state. The provider must expose, directly or through typed services:

- profile metadata needed by setup/admission, including optional nickname,
  locale, and Abyss-period identity;
- its own deck preset collection;
- its own SQLite/source-data boundary for characters, observed weapon stacks,
  artifacts, and build presets included by the package contract;
- character and weapon presentation assets keyed by stable game ids;
- package/provider lifecycle and cleanup.

Player 1 and Player 2 providers are independent even when both contain the same
`character_id`. Backend draft identity stays one stable game id, while
constellation, level, display metadata, image, equipment inventory, and build
presets remain seat-scoped. Never solve this by rewriting ids or merging the
imported rows into the main account DB.

The Draft UI should receive maps shaped conceptually as
`assets_by_seat[seat][character_id]`; local and imported providers use the same
interface. Local paths remain UI/provider data and must not enter
`unified_pool`, session identity, reducer actions, or hashes.

## Draft Ownership And Image Rules

Ownership styling is independent of whose turn it is:

- Player-1-only card: full Player 1 frame and Player 1 constellation badge on
  the left;
- Player-2-only card: full Player 2 frame and Player 2 constellation badge on
  the right;
- shared card: outer frame split left Player 1 / right Player 2, with each
  seat's constellation badge on its side;
- active-turn color must not recolor all available cards. Turn/action state is
  already shown by the central turn board, schedule, legal visibility/click
  state, and semantic pick/ban styling.

Seat-specific image selection is deterministic:

- `Player 1` and `Player 2` pool scopes always show that seat's image;
- a single-owner card always shows its owner's image;
- a shared card during `pick_character` shows the acting player's image;
- a shared card during `ban_character` shows the opponent's image;
- when no actionable turn exists, use the backend `base_seat` only as a stable
  presentation fallback;
- result zones preserve the action meaning: a shared pick uses the picker image
  and a shared ban uses the opponent image selected for that ban.

Missing assets fall back by stable `character_id` to a bundled/common icon or a
neutral placeholder. They never change ownership or legality.

## Target Portable Package

The finalized package remains a versioned ZIP, but it must be built from an
explicit allowlist rather than from a copied full application DB. Its logical
contents are:

- manifest: format/schema version, creator/app version, optional public profile
  metadata, locale/Abyss-period identity, counts, file hashes, and content map;
- selected deck presets;
- a minimal SQLite profile slice containing only the schema/tables/columns and
  rows required by those decks and the agreed artifact/build-preset scope;
- package-relative asset manifest keyed by stable character/weapon ids;
- the required bitmap files, deduplicated by content where practical.

The exact artifact/build-preset inclusion rule must be decided with the schema
implementation. It must be explicit (for example selected presets only, or all
presets for exported deck characters), testable, and reflected in the manifest;
silently copying every artifact/preset table is not acceptable.

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

The imported profile is read-only source data. It lives in a managed temporary
provider, gets a new seat-local PvP equipment state for each match, is closed on
replacement/match teardown/app exit, and never appears in the normal local deck
list unless a separate future user-authorized copy action is designed.

## Required Regression Coverage

- two providers can contain the same character id with different
  constellations and different images without overwriting each other;
- Player scopes and shared Pick/Ban image selection follow the rules above;
- ownership frame/badges do not change when the active seat changes;
- exported package remains usable after the source DB/assets are unavailable;
- exported SQLite contains no table/column/row outside the allowlist and no
  absolute/local paths;
- malformed DBs, broken hashes, missing assets, unknown deck references,
  oversized members, and traversal/duplicate entries are rejected;
- importing/replacing/closing a profile leaves the main account DB, local deck
  directory, normal equipment, and project files unchanged.
