# Account Traveler variants

<!-- handoff-current: traveler-variants -->
2026-10-11, Worker4 scoped executor; source ready for review and local profile
migration complete. This file owns
the requirements, source acceptance and progress for this independent package.
The shared TODO remains the only active queue; the canonical Worker4 shared
status reached through [coordination](COORDINATION.md) belongs to the PvP owner
and is not edited by this executor.

Read-only inspection of the imported Worker4 profile found one female Traveler
(`10000007`, Cryo, level 90, C4), seven stored skill rows, six constellation rows,
one assigned weapon and five assigned artifacts. Saved source confirms Cryo;
no inference about another element replaces it. Existing character upsert uses
the game ID alone, so another element would overwrite this row. Separate
variant identity and element-specific talent replacement are required.

Seven variants now persist with independent observations and standard-star
membership. Missing variants copy character/talent/constellation data only.
Later element imports replace copied active talents, preserve incomplete source
groups, and reuse existing gear under the usual revision/capacity/replay checks.
AppShell/PvP use a neutral portrait and the selected element layer. All seven
fallback element icons are tracked; a missing import cache does not hide variants.

Worker4's imported profile was expanded 78→84 characters, inside its supervisor,
operation and registry leases and one SQLite transaction. Six copies were added;
original skills/constellations, every non-Traveler row and 29 other tables were
verified unchanged. Exact original character/identity rows remain recoverable
inside the anchor metadata. An earlier in-memory backup exercise passed the
same checks and found seven distinct grid identities with usable element layers.

Source tests cover imports, rollback/replay, equipment, missing cache, filters,
PvP costs/Pyro requirement and profile exchange. No authenticated import, native
UI or engine/search ran. Runtime calculation remains explicitly deferred for
all Traveler variants; local registry has six elements but no Cryo key. Legacy
image-only UI and cross-account shared-draft identity remain separate limitations
below. Next: user AppShell smoke; no transfer or push is authorized here.
<!-- /handoff-current -->

## Original user requirements (verbatim)

нужно поручить новому чату в воркер 4(там импортирован профиль)реализовать путешественника как персонажа

путешественник в приложении должен отображаться как 7 разных персонажей разных элементов, однако мы импортируем за раз лишь одного.

поскольку мы сейчас отображение иконок персонажей собираем по кусочкам, делаем так 
импортированного собираем  как обычно - в том числе все его данные идут как обычно
если других путешественников нет - собираем копии путешественника, но с разными элементами. то есть копируем все данные самого персонажа, кроме снаряжения(чтобы не клонировать снаряжение - оружие и артефакты). таким образом на первом импорте у нас появляется в приложении 7 путешественников, один из которых реальный перенесенный из приложения, остальные просто его клоны, у которых мы поменяли в базе элементы на все остальные и при отображении в приложении - значок элемента тоже заменяется на соответствующий(здесь аккуратно - когда мы первый раз импортируем  я не знаю точно, будут у нас значки или нет - это надо определить. раньше у нас были значки скачанные, теперь мы скачиваем отдельно значки напрямую запросами во время импорта, по идее эти значки нужно будет потом поставлять изначально и иметь в базе - в общем если возникнет конфликт здесь - нужно будет пометить в хэндоффах-туду чтобы этот вопрос решили перед мвп как именно поставляем иконки).
теперь логика такая - если произойдет обновление, то путешественник другого элемента обновит собой уже существующего - это вроде как сейчас должно происходить без дополнительных действий, просто нужно проверить, что в коде так и будет работать - то есть уровни талантов и созвездие, скопированные у первого импорта, подхватятся и станут актуальными. Путешественник пускай находится под фильтром стандартных персонажей - то есть реагирует на него.

чат создавай на соответствующем усилии - но от тебя требуется сказать ему какой хэндофф читать, конкретно мои требования пришли в неизменном виде, но если я что-то ошибся или надо уточнить - свои комментарии добавь после моего текста 

## Integration boundaries

Account storage/import and equipment contracts remain in
[storage](ACCOUNT_SQLITE_STORAGE.md), [import](HOYOLAB_IMPORT_RELIABILITY.md),
and [equipment](ACCOUNT_EQUIPMENT_STATE_DESIGN.md). This package owns the
Traveler exception to ordinary game-ID identity and its acceptance. Preserve
base game ID/gender, existing IDs and equipment references; private data stays
outside Git. Native consumer/engine and Theory/search are outside scope.

## Storage and migration contract

- The first observed element retains `10000005` (Aether) or `10000007` (Lumine),
  preserving existing gear, builds and deck references. Other variants use local
  negative IDs `-(source_id * 10 + ordinal)`, with the fixed order Anemo, Geo,
  Electro, Dendro, Hydro, Pyro, Cryo. These are internal IDs, never official game
  IDs. Runtime refs expose `source_character_id` and `traveler_variant` separately.
- `traveler.py` owns that finite namespace and canonical `Traveler (Element)`
  names. `traveler_variants.py` fills missing rows only. Startup account-schema
  initialization runs a guarded, idempotent backfill; ordinary import also fills
  variants inside source publication. Existing other variants are not refreshed
  from a newly imported element. Missing/unknown elements never pick a default.
- Original legacy character and identity rows are saved once in
  `source_metadata.traveler_variant.legacy_original` on the positive anchor;
  future imports retain this record. At most one original pair per source
  Traveler is kept as saved account data until explicit profile deletion/reset.
  No new backup files or independent cleanup root are introduced. Imported
  observations and equipment retain their existing owners and lifecycles.
- Skills copied into variants carry `traveler_initial_copy`. Three distinct
  observed active talents (`skill_type=1`) replace copied active IDs. Missing or
  shorter passive groups preserve marked copies; observed same-element skills
  are never pruned by a partial source. Constellation positions upsert normally.
  No copied item, observed wearer, assignment, applied-build marker or preset is
  created. Raw artifact/weapon observations keep source IDs; only application of
  current equipment maps an observed element to its account variant.
- Every variant has `standard_5_star` in `character_identity`. The account key
  and resolution metadata are explicitly `unsupported_traveler`, with no GCSIM
  key and no element substitution. Generic catalog refresh cannot override this.

## Icons and UI

`asset_layers.py` still downloads shared layers for observed elements only.
`assets/filters/element_{anemo,geo,electro,dendro,hydro,pyro,cryo}.png` are all
tracked source assets and already feed the shared card-layer fallback. There
is no discovered missing-icon distribution conflict requiring a new shared TODO.
The normal release must continue including these existing assets; downloaded
profile cache files are not claimed as release content.

`ui/character_assets.py` looks up the source's neutral portrait, then side icon,
then the selected element glyph. It never reuses another element's baked crop.
AppShell and PvP overlay element, rarity and constellation from the chosen row;
include/exclude standard filters and element filters use each variant's metadata.
Missing optional images do not affect core publication. This acceptance covers
the AppShell grids (`python -m ui.app_shell_smoke`); legacy `main.py` still uses
image-only `DraggableIcon` widgets and has no dynamic element overlay. No launcher
was changed or launched by this task.

## PvP and runtime limits

Explicit valid variants are selectable in account export, deck validation and
Free Draft cards. Abyss prices/assigned-weapon overrides use the source game ID
and exact element, including the opposite-gender source ID only for that same
element. Only the matched Pyro source row satisfies a Pyro requirement. Ambiguous
or contradictory variants do not acquire a price or satisfy requirements.
Profile/package exchange accepts only the finite negative namespace and verifies
its element, retaining exact account references without exporting raw metadata.

The original game-ID anchor is account-local. The existing shared-draft reducer
still intersects local character IDs across opponents: equal logical variants
with different anchors/genders may not appear as shared candidates. Different
elements sharing an anchor are excluded from shared immunity. Full cross-account
draft canonicalization/acceptance remains outside this minimal rules seam; do not
claim a complete playable Traveler match from price or requirement tests.
The legacy tournament ruleset format/applicability path is unchanged and remains
conservative about Traveler. No tournament-system redesign was performed.

Read-only inspection of the installed `gcsim-v2.45.0-20260927011932` registry found
Aether/Lumine keys for Anemo, Geo, Electro, Dendro, Hydro and Pyro, plus the Lumine
`traveler*` aliases; no Cryo key exists. All seven account variants deliberately
remain calculation-not-ready until elemental talent/stat/runtime acceptance.
Neither native consumer/engine nor Theory/search code was changed.

## Verification and handoff

- The isolated regression suite includes first 1→7 import for either gender,
  each element update, same-element repeat, receipt replay, rollback, empty/partial
  talents, recovery/backfill idempotence, gear OFF/concurrent edit preservation,
  no inventory/count duplication and stale GCSIM metadata rejection.
- Automated UI checks cover seven distinct cards/layers, element filtering,
  standard include/exclude and missing portrait/shared cache. PvP fixtures cover
  prices, Pyro requirement, board selectability, profile/package round trips,
  invalid negative IDs and mismatched elements.
- Local profile migration used only its existing saved account database. Source
  receipt, raw JSON, images, equipment, presets, other characters and the draft
  profile remain unchanged; foreign-key check passed. Original rows are retained
  as above; migration required no reimport or authentication.
- User smoke remains: open AppShell character browser; confirm seven variants,
  standard include/exclude and element filters; inspect original Cryo gear and
  empty clone gear; select Pyro in Decks and inspect price/required status.
  Native visual acceptance, authenticated repeated import, cross-account match
  and GCSIM execution are unverified. Propose shared queue closure only for the
  implemented source/import/AppShell/PvP-price scope, retaining these limits.

Final automated receipt: **246 tests passed** in this checkout: one combined
227-test run (41.618 seconds) across the Traveler, storage/import/equipment,
layered-assets/stat-snapshot, character-assets, deck UI and seven PvP suites;
then 19 profile-package validation tests (20.476 seconds). These are isolated
fixtures and offscreen Qt checks, not native clicks. Existing test-harness SQLite
ResourceWarnings and one asyncio slow-callback diagnostic did not fail tests.
Handoff structure/budgets/current-projection check passed; semantic review
reconciled the storage, data rules, stat normalization and PvP entrypoints.
Staged whitespace review found only the two trailing spaces in the verbatim
human assignment above; those are intentionally retained. Source/test diffs
have no whitespace errors.

Changed source paths: `hoyolab_export/traveler.py`,
`hoyolab_export/traveler_variants.py`, `hoyolab_export/account_storage.py`,
`hoyolab_export/import_store.py`, `hoyolab_export/character_identity.py`,
`hoyolab_export/character_stat_snapshot.py`, `ui/character_assets.py`,
`ui/pvp_browser/deck_rules.py`, and `run_workspace/pvp/abyss_rules.py`,
`run_workspace/pvp/abyss_match_rules.py`,
`run_workspace/pvp/account_deck_export.py`, `run_workspace/pvp/validation.py`,
`run_workspace/pvp/free_draft_board.py`, `run_workspace/pvp/profile_schema.py`,
`run_workspace/pvp/profile_package.py`. Corresponding focused tests accompany
the package, including new
`tests/hoyolab_export/account/test_traveler_variants.py`. Handoff edits are this
owner plus CATALOG, README, ACCOUNT_SQLITE_STORAGE, DATA_WORK_RULES,
STAT_NORMALIZATION and PVP_DECK_RULES.

## Local Git receipt

Intent 2026-10-11 12:50 +03:00: scoped Traveler executor, local source commit on
`codex/pvp-providers`, source `c0a8850296f2a7e6d21383225ab0ad47e1baa2c3`.
Standing own-stage commit authorization applies. Initial tree/index were clean;
only this task's reviewed source/tests/handoffs are selected. No merge/rebase/
cherry-pick/revert operation or index lock is present. No transfer, branch move,
push, runtime binary change or canonical Worker4 status write is included.
The shared queue owner receives results through this chat's final snapshot.

Result 2026-10-11 12:52:48 +03:00: source commit
`34de29b9ea2ffb6115020a69e713a7a9630a5893`, parent
`c0a8850296f2a7e6d21383225ab0ad47e1baa2c3`, on `codex/pvp-providers`.
All 33 selected source/test/handoff paths committed successfully; working tree
and index were clean afterward. The 246-test and handoff receipts above apply;
native UI, authenticated import, cross-account draft and engine limits remain.

Receipt-only follow-up intent 2026-10-11 12:55 +03:00: the same scoped executor
will commit only this Git receipt on the same branch, from source commit
`34de29b9ea2ffb6115020a69e713a7a9630a5893`, under the same own-stage authority.
The resulting hash and final clean-tree check are reported in the final chat
snapshot for the queue owner; no additional product or shared-status edit.
