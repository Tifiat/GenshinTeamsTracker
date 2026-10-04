# Worker5 source transfer inventory

<!-- handoff-current: worker5-transfer-inventory -->
2026-10-04. The user's later instruction in the orchestrator, "ты синхронизировал?
если нет - доделывай", explicitly followed the question about committing and
transferring Worker5. The human message was verified read-only in thread
`01a0b9e5-7078-7160-ad7b-ba6255012de1`, turn
`01a10523-9367-72f0-b0d4-b31dfdf32dd8`. It authorizes a local commit of the
verified import/profile/icon/tooltip source and orchestrator-owned transfer.
Visible tooltip/account acceptance and real multiaccount imports stay open;
push remains unauthorized. The pre-stage HEAD is
`3df2629f34b6d46cd54a5a805fc896d8cc5d2928`; the resulting full commit ID and
timestamp belong to Worker5's status and the Git commit record.

The combined stage includes profiles, so its tooltip tests retain their profile
dependencies. Packets A/B/C below preserve the earlier decomposition for review,
not a claim that the final suite works without profiles. Whole-branch integration
would carry unrelated earlier History/optimizer changes and is excluded. No
network, import or app launch is authorized for packaging. Current-target
integration and compatibility checks remain Worker1's responsibility.
<!-- /handoff-current -->

## Pre-stage source identity and existing commits

| Source | Exact location / identity |
| --- | --- |
| Worker5 additions below | `C:/Users/user/Desktop/worker5 GTT`, branch `codex/history-review`, HEAD `3df2629f34b6d46cd54a5a805fc896d8cc5d2928`, dirty working tree |
| Isolated importer candidate | `C:/Users/user/.codex/worktrees/hoyolab-import-repair/worker5 GTT`, detached `bde62f972ac77c50bffcf6f54cd08beeb0558457`, dirty working tree |
| Target checked during commit preparation | `dbae9d1eec845108db91fb2792e2b842a6a04a42`; an observation, not a freeze or integration result |

`3df2629f34b6d46cd54a5a805fc896d8cc5d2928` is the earlier independent partial-import
hotfix. It is superseded in behavior by the combined pipeline implementation.
The historical isolated Packet A is consolidated against
`bde62f9`; the old hotfix is not a required preceding cherry-pick for that packet.
Neither `e7de1a4f6cddbba387be396220ad682c1a2278e0` nor
`4ee99d27bab70ce50d3dd3d78630f01ba316817f` is an import-transfer dependency:
those checkpoints contain History/pre-existing optimizer work.

Review target changes before extracting hunks. At the observed main revision,
Artifact Browser queries/window and the account settings page have changed
since `bde62f9`. The mini-set description cache and Fact DPS local-image URI
adaptations were not present in the inspected main versions. Do not replace
Worker3's accepted files wholesale with Worker5's older copies.

## Prerequisites for the combined commit on the checked target

The new commit has parent `3df2629f34b6d46cd54a5a805fc896d8cc5d2928`, so its
diff does not repeat retained hotfix code already present in that parent.
The checked target lacks these prerequisite hunks from that exact commit:

| Source path at `3df2629` | Required retained behavior |
| --- | --- |
| `hoyolab_export/artifact_set_catalog.py` | `UnmappedArtifactSetError`; `ensure_hoyolab_set_mapping(..., allow_unmapped=False)` and its `unmapped` result; `resolve_hoyolab_set_uid` raises the specific error for missing canonical mapping; `ensure_artifact_set_catalog` closes the seed transaction before refresh and continues requested refresh after seeding |
| `ui/right_panel/settings/account_data.py` | `HOYOLAB_IMPORT_WARNING_KEYS`, warning-list initialization/reset, `[IMPORT_WARNING]` parsing via `_record_hoyolab_import_warning`, `_hoyolab_import_warning_details`, and success-path warning display; the combined stage narrows the map to artifact/account/equipment failures |
| `localization/locales/en.json`, `localization/locales/ru.json`, `localization/locales/pt-br.json` | `hoyolab.import_warning.title`, `.artifacts`, `.account`, `.equipment`, `.set_names`; preserve each language's values |
| `tests/hoyolab_export/artifacts/test_artifact_set_catalog.py` | The hotfix's seed-refresh/closed-connection and mapping fixtures/regressions; current changes to two existing test bodies assume those fixtures already exist |

Use those source hunks while adapting, keeping the **new commit's final source**
as authority. The old skip-unknown-relic behavior in `3df2629`'s importer is
superseded; current import keeps unresolved source identities and equipment.
The obsolete unknown-set warning mapping/message is not a current requirement.
Do not transfer whole older History/optimizer checkpoints merely to obtain
this parent. At the checked target, the History hover tests, optimizer help
surface and account/view-model APIs used by the tooltip runner already exist.

Static preparation verified that all 139 staged paths exist as expected and
no directly imported local Python module is missing from target plus packet.
The profile modules absent from target are included in the same stage. This
does not prove conflict-free cherry-pick or target behavior; Worker1 must
reconcile accepted Browser/PvP/default-setting code and run the focused tests.

## Packet A: isolated importer candidate

Use the isolated candidate root above, not the similarly named files in the
current Worker5 checkout. This packet predates saved profiles and the final
icon/tooltip work. It contains atomic source-first publication, unresolved-set
identity preservation, bounded parallel enrichment, progress and default
equipment application, plus the consumer changes needed for raw set identities.
The three GCSIM consumers listed here are that import compatibility work; they
do not authorize moving other optimizer changes.

Exact inventory: 47 code/test/locale files and seven handoff files. Paths are
relative to the isolated candidate root. Added files are included.

```text
hoyolab_export/abyss_source_refresh.py
hoyolab_export/account_equipment.py
hoyolab_export/account_storage.py
hoyolab_export/artifact_build_snapshot.py
hoyolab_export/artifact_db.py
hoyolab_export/artifact_fingerprint.py
hoyolab_export/artifact_importer.py
hoyolab_export/artifact_set_catalog.py
hoyolab_export/asset_layers.py
hoyolab_export/character_detail.py
hoyolab_export/character_stat_snapshot.py
hoyolab_export/hoyowiki_catalog_refresh.py
hoyolab_export/import_pipeline.py
hoyolab_export/import_progress.py
hoyolab_export/import_store.py
hoyolab_export/offline_profile.py
hoyolab_export/run_import.py
localization/locales/en.json
localization/locales/pt-br.json
localization/locales/ru.json
run_workspace/abyss/fandom_enemy_hp_fallback.py
run_workspace/abyss/source_data_cache.py
run_workspace/abyss/source_data_update.py
run_workspace/gcsim/account_prepared_config.py
run_workspace/gcsim/optimizer_artifact_database.py
run_workspace/gcsim/selected_team_config.py
tests/hoyolab_export/abyss/test_hoyolab_abyss_source_refresh.py
tests/hoyolab_export/account/test_account_equipment.py
tests/hoyolab_export/account/test_asset_layers.py
tests/hoyolab_export/account/test_import_asset_publication_async.py
tests/hoyolab_export/account/test_import_progress.py
tests/hoyolab_export/account/test_import_reliability.py
tests/hoyolab_export/account/test_import_settings.py
tests/hoyolab_export/account/test_import_store.py
tests/hoyolab_export/account/test_profile_import_projection.py
tests/hoyolab_export/account/test_run_import_cli.py
tests/hoyolab_export/artifacts/test_artifact_set_catalog.py
tests/hoyolab_export/artifacts/test_artifact_source_identity.py
tests/hoyolab_export/artifacts/test_catalog_parallel_refresh.py
tests/hoyolab_export/artifacts/test_unresolved_source_sets.py
tests/run_workspace/abyss/test_fandom_enemy_hp_fallback.py
tests/run_workspace/abyss/test_source_data_cache.py
tests/run_workspace/abyss/test_source_data_update.py
tests/run_workspace/gcsim/test_gcsim_mixed_source_collisions.py
tests/ui/right_panel/test_hoyolab_import_lifecycle.py
ui/right_panel/settings/account_data.py
ui/widgets/loader.py
```

The candidate's accompanying documents are:

```text
docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md
docs/handoff/ACCOUNT_SQLITE_STORAGE.md
docs/handoff/APP_SHELL_WORKSPACE_PLAN.md
docs/handoff/ARTIFACT_BROWSER.md
docs/handoff/DATA_RUNTIME_BOUNDARIES.md
docs/handoff/DATA_WORK_RULES.md
docs/handoff/HOYOLAB_IMPORT_RELIABILITY.md
```

Reconcile their applicable contract/evidence hunks into target owners; do not
restore old current-status blocks over newer accepted work. The dated 337-case
candidate run and its Windows symlink skip are owned by
[the reliability receipt](HOYOLAB_IMPORT_RELIABILITY.md#loaderdefaultthroughput-review-2026-10-04-worker5).
That run does not cover Packets B/C or later profiles.

## Packet B: later Abyss icon recovery

Use the current Worker5 root. These nine source files build on Packet A's
shared HP/icon worker pool and progress plumbing:

```text
run_workspace/abyss/browser_image_fetcher.py
run_workspace/abyss/monster_icon_catalog.py
run_workspace/abyss/source_data_cache.py
run_workspace/abyss/source_data_update.py
tests/run_workspace/abyss/test_browser_image_fetcher.py
tests/run_workspace/abyss/test_icon_browser_fallback.py
tests/run_workspace/abyss/test_monster_icon_catalog.py
tests/run_workspace/abyss/test_source_data_cache.py
tests/run_workspace/abyss/test_source_data_update.py
```

The browser helper and monster catalog are new modules; the matching three
test modules are new. For shared cache/update files, extract the delta from
Packet A to these Worker5 versions. A transfer directly onto a target without
Packet A must also carry/adapt its worker-pool, progress and HP-fallback seam.
`hoyolab_export/abyss_source_refresh.py` and its test remain Packet A dependencies
and are part of the 83-case verification command below.

`browser_image_fetcher.py` uses the existing `find_browser_exe` function,
Playwright and Pillow. It does not need the newer managed-login implementation
in Worker5's `hoyolab_export/auth.py`. Do not transfer those unrelated auth
hunks. Likewise, the current `source_data_runtime.py` change routes an account's
period path through `ACCOUNT_ROOT`; it belongs to profiles, not this icon fix.

The source/image behavior, exact real download results, partial first attempt
and subsequent cache-only repeat are owned by
[Abyss enemy data](ABYSS_ENEMY_DATA.md#2026-10-04-browser-recovery-receipt).
No downloaded image, cache JSON, browser profile or account data is in this
source packet.

## Packet C: tooltip repairs and semantic contracts

Use the current Worker5 root. This is the exact 19-file source inventory, not
permission to copy every listed production file wholesale:

```text
tests/ui/right_panel/live_run/test_fact_dps_tooltip_icons.py
tests/ui/right_panel/live_run/test_mini_set_tooltips.py
tests/ui/tooltips/__init__.py
tests/ui/tooltips/known_sets.py
tests/ui/tooltips/test_catalog_tooltips.py
tests/ui/tooltips/test_content_contracts.py
tests/ui/tooltips/test_inventory.py
tests/ui/tooltips/test_presentation_contracts.py
tools/check_tooltips.py
ui/artifact_browser/filter_popup.py
ui/artifact_browser/queries.py
ui/artifact_browser/window.py
ui/main_window.py
ui/right_panel/common/run_summary.py
ui/right_panel/common/slot_parts.py
ui/right_panel/live_run/panel.py
ui/right_panel/settings/account_data.py
ui/right_panel/settings/account_profiles.py
ui/utils/tooltips.py
```

Hunk boundaries and dependencies:

| File / area | Carry with tooltip work | Keep with profile work |
| --- | --- | --- |
| `ui/utils/tooltips.py` | Reuse one owner controller, update visible text, clear/hide | None |
| `ui/right_panel/common/slot_parts.py` | Independent tooltip refresh key; read-only descriptions cached by DB/WAL/language signature; recover transient misses | Uses the target's existing account DB/content-language path constants |
| `ui/right_panel/live_run/panel.py` | Local image `resolve().as_uri()` in `_fact_dps_tooltip_html` | None |
| `ui/artifact_browser/queries.py` | Read-only description lookup and empty-HTML language fallback in both readers | `account_asset_path` import and asset path routing |
| `ui/artifact_browser/window.py` | Custom action/slot hints and stale `_install_set_bonus_tooltip` clearing | `account_asset_path` import and asset path routing; preserve target's other Browser changes |
| `ui/artifact_browser/filter_popup.py`, `ui/right_panel/common/run_summary.py` | Shared custom hints | None |
| `ui/main_window.py` | Controller initialization/import and running/cleanup/clear hint updates | `ACCOUNT_ROOT`, state/history path routing |
| `ui/right_panel/settings/account_data.py` | Existing energy/import hints, locale refresh and clear | Saved-account controls, new login/import/lifecycle dependencies and other non-tooltip hunks |
| `ui/right_panel/settings/account_profiles.py` | Profile deletion hint, when that widget is transferred | Entire new widget depends on the saved-profile package |

The nine new test/runner files include two previously adapted Worker3
regressions. Check for equivalent target implementations before adding them.

The full runner is **not yet a standalone packet on a target without profiles**:
`test_catalog_tooltips.py` imports `active_profile`/`profile_root`,
`test_presentation_contracts.py` imports `AccountProfilesWidget`, and the binding
inventory registers that widget. Either transfer the separately accepted
profile implementation first, or adapt the account locator to the target's
existing read-only account path and retain the profile-specific assertions
with the profile packet. Do not remove the first-present-set failure rule or
turn missing modules into a blanket successful skip. Reconcile the binding
inventory with accepted target UI changes while retaining semantic tests for
every registered family.

The tooltip owner is [TOOLTIP_CONTRACTS.md](TOOLTIP_CONTRACTS.md). Transfer its
contract plus the relevant mandatory-regression rule in `UI_WORK_RULES.md`,
description behavior in `ARTIFACT_BROWSER.md`, focused command in `TESTS.md`,
and links in `README.md`/`CATALOG.md`. These are selective documentation hunks,
not a request to overwrite current target handoffs.

## Combined profile stage and scope boundaries

The newly authorized local stage uses the **current Worker5** versions of the
importer, icon and tooltip files, including their saved-profile dependencies.
It also includes registry/locks/supervisor/migration, game-account metadata,
isolated ZIP restore, centralized defaults, account controls, profile path
routing and their tests/contracts. `git show --name-status <resulting commit>`
is the exact committed inventory; the resulting ID is recorded in Worker5's
shared status for the orchestrator. The isolated Packet A is kept intact as
dated comparison evidence and is not changed or committed by this operation.

Changes in History/PvP/run/cache consumers carry only account-root routing.
The required GCSIM import seams retain source-set IDs, refuse unresolved active
canonical bonuses, and guard against treating scanner/source records as extra
physical copies after late canonical enrichment. Their collision fixtures are
part of the earlier import suite. `gcsim/settings.py` delegates unchanged 3/3
and 5/21 defaults to the user's required central registry. These seams are
included; no earlier optimizer search/theory or History presentation work is
added by the new commit. Main's newer implementations need hunk-level adaptation.

## Verification and remaining gates

These are existing dated results, not new runs during inventory preparation:

| Scope | Recorded evidence | Boundary |
| --- | --- | --- |
| Isolated importer candidate | 336 PASS, one declared Windows symlink skip | Older Packet A; [receipt](HOYOLAB_IMPORT_RELIABILITY.md#loaderdefaultthroughput-review-2026-10-04-worker5) |
| Worker5 tooltip runner | 67 PASS, including the active account's Emblem 2p/4p on both tooltip surfaces | Controlled/offscreen plus read-only catalog witness; [owner](TOOLTIP_CONTRACTS.md) |
| Worker5 Abyss/source/cache/refresh suite | 83 PASS | Includes browser fallback, failure, bounds, ordering and cache reuse; [owner](ABYSS_ENEMY_DATA.md) |
| Real public icon repair | All eight validated images eventually cached; first pass 7/8, follow-up 8/8; warm run made no image HTTP/browser calls | One observed cache/period, not a universal first-attempt guarantee; [receipt](ABYSS_ENEMY_DATA.md#2026-10-04-browser-recovery-receipt) |

Focused commands after an authorized target adaptation:

```text
python -X utf8 tools/check_tooltips.py
python -X utf8 -m unittest tests.run_workspace.abyss.test_monster_icon_catalog tests.run_workspace.abyss.test_source_data_cache tests.run_workspace.abyss.test_source_data_update tests.hoyolab_export.abyss.test_hoyolab_abyss_source_refresh tests.run_workspace.abyss.test_browser_image_fetcher tests.run_workspace.abyss.test_icon_browser_fallback -q
```

Visible AppShell hover acceptance, multiple authenticated account imports and
game-avatar acceptance remain open. The saved-profile implementation has its
own [owner and controlled checks](ACCOUNT_PROFILES.md); the local source commit
does not declare those physical gates accepted. The previous 53.656s
full import is dated evidence, not a new performance limit or a new timing for
the final icon implementation.

Main's accepted system-scaling preference must be added to the central
`settings_defaults.py` registry when profiles/defaults are integrated. Preserve
an explicit existing setting and verify first-start/reset semantics; this
inventory did not modify either defaults implementation or target UI.

Exclude runtime/account assets, SQLite databases, credentials, browser profiles,
temporary measurement timers, unrelated History/optimizer edits, and dirty
`CODEX.md`/`COORDINATION.md`. No clean-current-target apply result, merge or push
is claimed. The orchestrator's transfer action is selective adaptation against
the destination's actual current code followed by its focused checks. Physical
acceptance remains a separately open gate after the authorized source commit.

## Source-byte fingerprints

These fingerprints identify the inspected local bytes, not a portable Git
patch. For each packet, sort the listed relative code/test/locale paths
lexicographically, compute SHA-256 of each file's raw bytes, concatenate UTF-8
lines of `<lowercase file sha256><two spaces><relative POSIX path>\n`, then hash
that stream with SHA-256. Packet A excludes its seven handoff files. Packets
B/C include the full listed files even where transfer must select hunks.

| Packet | File count | Aggregate SHA-256 |
| --- | --- | --- |
| A, isolated candidate | 47 | `b278f6efd0b57969a619ffc96e2d07af8e5f475fda9b7dbfe7ed033c276287d6` |
| B, Worker5 icons | 9 | `30b0f7b142c92487619560c3c59369989cbcb3abdcda59cb323dc83c1126a14b` |
| C, Worker5 tooltips | 19 | `9973adf700d6a2f937342e41bfb36beb276b79b7d163b200a5b978d4f607d5d8` |
