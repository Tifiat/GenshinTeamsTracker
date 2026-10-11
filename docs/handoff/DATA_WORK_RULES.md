# Data and generated-output work rules

Read this for account storage/import, equipment, generated files, caches,
exports and cleanup. Detailed schemas and lifecycles belong to the linked
owners in `README.md` and `DATA_RUNTIME_BOUNDARIES.md`.

- Every new persistent generated/temp output needs an owner, finite retention,
  an actually wired cleaner and focused deletion/preservation tests in the same
  change. `.gitignore` or a cleanup TODO is not a lifecycle. Research copies
  need a deletion gate and only minimal reproducible evidence afterward.
  Measure bytes before/after heavy experiments; do not accumulate cloned
  source trees or build caches.
- `data/artifacts.db` is the unified local runtime SQLite DB despite its name.
  Account-relative paths resolve under the selected profile root; see
  [profiles/defaults](ACCOUNT_PROFILES.md). New preferences and dismissed-hint
  flags must register defaults in `run_workspace/settings_defaults.py` and
  participate in the shared Clear all reset. Saved accounts persist until
  explicit deletion; account-derived caches retain bounded cleanup.
  Raw HoYoLAB JSON is source/import cache. Move remaining catalogs to normalized
  tables only after usage shows frequent runtime joins, filters, mapping or
  stat-calculator needs; retain small rebuildable source JSON where suitable.
- Character, weapon and artifact identity uses stable IDs and stored resolved
  keys rather than translated names or image paths. Observed weapons are
  fingerprinted stacks with non-decreasing `known_count`, not unique instances.
- Current equipment, HoYoLAB observations and saved build presets are separate.
  Removing a team member does not unequip them. Equipment is per character;
  normal team selection is per mode and PvP equipment is scoped. HoYoLAB
  `Change equipment` defaults ON; enabled imports apply fresh observations in
  one validated batch. Missing observations never clear equipment or presets.
- Artifact content twins usually dedupe; simultaneous distinct observed
  wearers can prove additional copies. Reuse IDs on reimport; repeated rows
  alone do not prove copies. Account/source/receipt publication is one SQLite
  transaction; JSON and images are independent recoverable projections.
- Account/API content language differs from UI language. EN service details
  are mapping inputs. Catalog detail refresh is explicit; ordinary import must
  not fetch every character/weapon detail page.
- Shared character/weapon card artwork is shipped application source under the
  [card asset contract](CHARACTER_CARD_ASSETS.md). Imports download unique icons;
  elements/backgrounds have no per-account network fallback or cleanup owner.
- Selected-build display stats use base/reference data and equipment, not
  HoYoLAB final rows. Only explicitly modeled static effects apply; passive
  text is reference. [Traveler variants](TRAVELER_VARIANTS.md) have explicit
  account elements; their calculation/runtime acceptance remains deferred.
- History freezes each occupied slot's display data/assets and reuses an
  isolated read-only Run panel. Factual DPS is HP/time from authoritative Abyss
  cache; missing period/cache/HP means unavailable. PvP has independent source
  providers and scoped runtime state. The `.gttpvp` development boundary and
  pending real-account acceptance are owned by `PVP_PROFILE_PACKAGE.md`.
- Normal offline profile export is an allowlisted ZIP with a SQLite backup,
  account JSON/assets and language metadata. It excludes authentication,
  private debug and browser state. PvP exchange is a separate boundary.
