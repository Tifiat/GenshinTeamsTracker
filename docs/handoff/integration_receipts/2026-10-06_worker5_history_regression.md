# Worker5 transparent History pipeline regression — 6 October 2026

Owner: Worker5. Scope: close the reviewed test gap between imported asset
selection, team-card data and frozen History. No product behavior changed.
The orchestrator authorized this narrow regression/receipt stage and an own
verified local commit under the direct human integration request, source turn
`01a11037-7237-7682-8ad4-2d978a591e38` in chat
`01a0b9e5-7078-7160-ad7b-ba6255012de1`. No master update, other checkout/ref
write, app/import/engine run or push belongs to this stage.

## Source and transfer boundary

Before this stage, Worker5 was clean on `codex/history-review` at
`5512bad51f3b76f70352a4026b8b2fdcc0bf27a3`, tree
`18471db7ee391fefa902c3b8bb6f6c9707099b83`. The reviewed History candidate is
the net delta against exact ancestor `9b2a167180033625914dfb4ceeed9b651f26f351`,
restricted to the 17 paths below: 291 additions/53 deletions plus six PNGs.
This regression stage leaves every one of those files unchanged.

```text
hoyolab_export/account_storage.py
hoyolab_export/team_card_data.py
run_workspace/history_snapshot_builder.py
ui/character_assets.py
ui/right_panel/common/history_card.py
tests/run_workspace/history/test_history_snapshot_builder.py
tests/ui/character_assets/test_character_assets.py
tests/ui/right_panel/history/test_history_cards.py
docs/handoff/ACCOUNT_SQLITE_STORAGE.md
docs/handoff/HISTORY_BROWSER.md
docs/design/history/README.md
docs/design/history/implementation-transparent-aligned/compact-1004-150pct.png
docs/design/history/implementation-transparent-aligned/compact-704-150pct.png
docs/design/history/implementation-transparent-aligned/export.png
docs/design/history/implementation-transparent-layers/compact-704.png
docs/design/history/implementation-transparent-layers/compact.png
docs/design/history/implementation-transparent-layers/export.png
```

Add this stage's new
`tests/run_workspace/history/test_history_transparent_pipeline.py`, this receipt,
and only its new catalog row. Do not replace the target catalog with Worker5's
whole file. Actual new commit hash, parent, tree and time are recorded in
Worker5's shared status/event log, avoiding a follow-up self-hash commit.

Original feature source is `e7de1a4f6cddbba387be396220ad682c1a2278e0`, parent
`bde62f972ac77c50bffcf6f54cd08beeb0558457`. Its 30-file mixed feature/routing
commit must not be replayed blindly. Prerequisite import/profile source
`a085d3526e22a8862243ab40f3532b9be877ea72` and
`3df2629f34b6d46cd54a5a805fc896d8cc5d2928` were already accepted in master
`ad0ea8c06a48a83c6edfe0aee22b36e68f2b31ff` and inherited through 9b2a167.
In particular, master supplies raw-layer lookup, account-root containment,
low-rarity download filtering and PvP privacy/portable-asset behavior. Preserve
5512bad's joint raw/composed priority and corrected account-root fixture.

Exclude Worker5 AGENTS/CODEX policy, the old reverse-sync receipt and its
catalog row, and the redundant import-reliability low-rarity note. No older
optimizer/Theory lineage, live data or isolated importer worktree is included.
Root reports its next target as `5da96c7383913afb7908c90673dcbd9f2157e414`
after PvP docs `7b576df43d0b5b95775064071ef135ece3cf2a6b`. This source check
does not certify that target; root owns exact integration and target validation.

## Gap and regression

Earlier checks tested image selection and separately injected raw paths into
snapshot-builder inputs. They could miss removal of `portrait_history_path`
or `icon_transparent_path` from the team-card adapter's output.

The new test calls the real manifest resolvers via
`account_character_asset_item` and `AccountWeaponObservedStack`, then calls
`build_character_details_data`, attaches its result to a synthetic RunSession,
builds the snapshot and materializes it through `HistorySnapshotBundleStore`.
It never injects either History path into the team-data output. The live panel
still supplies baked images, so the snapshot must use the correctly propagated
optional layer. Assertions independently check the intermediate paths and final
copied bytes, unchanged input mappings/live state, and saved constellation.
After source images are removed, saved reads must use bundle-local assets and
must not query the live manifest.

Four cases:

| Case | Expected saved image choice |
| --- | --- |
| Active imported crop, raw and composed portraits both present | Raw portrait and raw weapon; both paths survive team data |
| Different active-account bitmaps with the same game IDs | Their own displayed character/weapon fallbacks; no borrowed raw layers |
| Foreign packaged neutral bitmaps with the same IDs | That package's own fallbacks; no active-import layer reuse |
| Matching crop with raw files absent | Matching composed History portrait and original weapon fallback |

The foreign case represents an external temporary package, not permission to
read another managed account. Existing account-root guards remain unchanged.
Distinct synthetic byte files test layer identity/copying; image decoding and
physical appearance are outside this regression. No behavior fork or concrete
product defect was found, so no product code was edited.

## Verification on Worker5

One focused run on 2026-10-06: **13 PASS**, no skips/failures, 0.698 seconds.
Four new cases and nine directly related existing cases:

- `TransparentHistoryPipelineTest`: all four methods in the new module.
- `CharacterAssetRuntimeItemsTest`: matching raw History/weapon lookup, foreign
  neutral PvP portrait reuse, and missing-neutral baked-fallback rejection.
- `HistorySnapshotBuilderTests`: transparent layers frozen without live-state
  changes; supplied team/slot/build/stat/bonus data preserved.
- `HistorySnapshotAssetTests`: both copying/reference-rewrite/source-removal
  and missing-required-asset publication rejection.
- `TeamCardDataTest`: basic character/weapon/build details and the no-build
  character/weapon case.

The runner used Python `-B -X utf8`, explicit language, temporary account roots
before imports and no QApplication/window construction. Its audit hook rejected
process launch, network/DNS, any SQLite open, and access to live checkout
runtime/account/settings paths: **zero violations**. Each new test additionally
rejects Popen/system, socket calls, SQLite, QProcess launches and profile
bootstrap, with mock call counts checked even if a failure were swallowed.
Manifest/profile roots and all fixture writes are temporary; cleanup is wired
through TemporaryDirectory/ExitStack. No app, real account/import or engine ran.

Handoff/diff checks and the exact committed scope belong to the final own-status
entry. Oct3 painter/asset and Oct4 reverse-sync counts remain dated evidence in
[design history](../../design/history/README.md) and the
[reverse-sync event record](../../../../GTT%20coordination/archive/GIT_EVENTS_20261004_REVERSE_SYNC.md), not new runs.

Target integration still needs bounded renderer/tooltip/profile compatibility
checks under isolated roots. Physical History Save/reopen/collapse/hover,
artwork upload/reset, native PNG export/restart and display scaling remain open.
This regression closes the team-data propagation gap only.
