# Worker5 reverse synchronization on 4 October 2026

Owner: Worker5. This records the reviewed merge of accepted master into the
existing History branch. Root review is complete and completion is authorized.
The review snapshot below is historical; actual merge hash, tree, time and
checks belong to Worker5's shared status and the shared event log. Unfinished
History remains on this branch.

## Authorization and Git boundary

The human request was verified in source chat
`01a0b9e5-7078-7160-ad7b-ba6255012de1`, user message
`01a10622-82b3-7f20-afc8-7e64146974af`: synchronize completed Workers1/3/4/5
with master, excluding Worker2. New orchestrator
`01a10629-02cd-7842-a44b-5b2367dadaf5` delegated the concrete preservation
commit and real `--no-commit` merge, initially reserving the merge commit until
review. Root completed that review and explicitly authorized completion with
only this receipt's temporary wording updated; no second approval is required.
Shared intent and collected events are in
`C:/Users/user/Desktop/GTT coordination/archive/GIT_EVENTS_20261004_REVERSE_SYNC.md`.
Only this checkout and Worker5's own shared status were edited. No other
checkout/ref, shared queue, fetch or push is part of this operation.

Starting branch: `codex/history-review`, HEAD
`a085d3526e22a8862243ab40f3532b9be877ea72`. The index was empty; exactly
`CODEX.md` and `docs/handoff/COORDINATION.md` contained own policy edits.
Those two files were preserved in local commit
`14a49f88500973577c7497a036b9fe7e3e045dee` at
`2026-10-04T13:19:18+03:00`, parent the starting HEAD above. Scope: 17
additions/four deletions; no temporary instrumentation or product source.
The index/tree were clean after that commit. Original raw bytes matched
before/after commit, including LF-only endings:

| File | Raw SHA-256 | LF count |
| --- | --- | --- |
| `CODEX.md` | `b0268f9b179b8a7bc7bb2b76b4ae0156ae4c04567a642b1e39ae9b0af9484ae2` | 104 |
| `docs/handoff/COORDINATION.md` | `9e8977026835a7895e53770c87b736d44a8de982c8cb2eb54d5387e734d7b380` | 57 |

The real merge used exact master
`9b2a167180033625914dfb4ceeed9b651f26f351` with `--no-commit --no-ff`.
The approved parents are `14a49f88500973577c7497a036b9fe7e3e045dee` first and
`9b2a167180033625914dfb4ceeed9b651f26f351` second. At the historical review
snapshot, `HEAD` was the policy commit, `MERGE_HEAD` was that exact master and
the staged tree was `34696aa5b87001598afe93b9bb979cefce230951`. Those pins
were independently checked by root and rechecked before completion. Only this
receipt changes relative to the approved tree; product/test content is fixed.

## Conflict review

The real merge reported 31 content/add-add conflicts, all resolved explicitly:

```text
AGENTS.md
CODEX.md
TODO.md
docs/handoff/ABYSS_ENEMY_DATA.md
docs/handoff/ACCOUNT_PROFILES.md
docs/handoff/CATALOG.md
docs/handoff/COORDINATION.md
docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md
docs/handoff/HANDOFF_MAINTENANCE.md
docs/handoff/HOYOLAB_IMPORT_RELIABILITY.md
docs/handoff/README.md
docs/handoff/TOOLTIP_CONTRACTS.md
docs/handoff/WORKER5_TRANSFER_PACKAGE.md
docs/handoff/WORK_BACKLOG.md
docs/optimizer-evidence/2026-10-03-filter-hypotheses/README.md
localization/locales/en.json
localization/locales/pt-br.json
localization/locales/ru.json
run_workspace/gcsim/optimizer_artifact_database.py
run_workspace/settings_defaults.py
tests/run_workspace/gcsim/test_gcsim_mixed_source_collisions.py
tests/run_workspace/test_settings_defaults.py
tests/ui/tooltips/test_inventory.py
tests/ui/tooltips/test_presentation_contracts.py
tools/experiments/gcsim/filter_hypotheses/neighborhood_gate.go
tools/experiments/gcsim/filter_hypotheses/neighborhood_gate_test.go
tools/experiments/gcsim/filter_hypotheses/search_gate.patch.json
tools/experiments/gcsim/filter_hypotheses/search_hook.go
ui/artifact_browser/queries.py
ui/character_assets.py
ui/right_panel/settings/account_data.py
```

Decisions:

- Coordination and area receipts retain accepted master's shared routing and
  target evidence. AGENTS retains the explicit Worker5 status route. CODEX
  retains the fuller own local-commit rule, including the prohibition on
  temporary instrumentation and other workers' unfinished stages. The obsolete
  main-checker fallback was removed because this merge brings the local checker.
  The dated low-rarity download regression remains in import reliability.
- All three locale dictionaries match master. Incoming keys add 15 PvP/display
  strings per locale; no own-only key or conflicting translation was lost.
- Browser queries retain `initialize`/`read_only`, batched child reads and
  account-relative assets. Settings retain `DisplaySettingsBlock` and the
  central `ui_use_system_scaling: false` default. Their conflict resolutions
  and corresponding tests match master.
- Mixed-source artifact admission matches master: preserve one valid canonical
  representative of an ambiguous group, exclude aliases, allow separately
  observed copies, and include the observation proof in the digest. The tests
  use temporary SQLite and a synthetic catalog; no optimizer was executed.
- Tooltip inventory and presentation match master, including the two custom
  PvP run-admission bindings and their block/update/clear contract.
- Character assets combine master's neutral PvP portrait reuse by game ID
  with Worker5's transparent History preference. History still requires an
  exact matching imported crop; raw portrait wins when raw and composed
  variants both exist. PvP still clears baked portrait fallbacks when the
  neutral layer is missing. The History test now supplies both variants.
- The History weapon fixture was adapted to account-root isolation and actual
  portable `assets/hoyolab/weapons/...` manifest paths; a foreign displayed
  bitmap must still receive no transparent replacement. Production account
  isolation was not weakened to accommodate the old fixture.
- Research gate/hook/patch/test conflicts match master's consistent context
  cancellation contract. The experiment README retains dated failed cleanup
  evidence and distinguishes the old isolated study from later accepted H4
  source. No Go tests, engine installation or numerical acceptance is claimed.

The merged source was compared against exact master. Browser queries/store,
artifact DB, settings/display, canonical artifact admission, selected-team
config, profile context/control, PvP package/assets/UI, gcsim UI, import runner,
Abyss source runtime, tooltip inventory/presentation, repaired startup fixture
and coordination checkers retain accepted master content. These comparisons
are source evidence, not new product execution.

The residual delta against master preserves only Worker5 policy and older
History source/tests/receipts/illustrations, plus this merge receipt/catalog
entry and the strengthened History fixture. In particular, History transparent
weapon capture, immutable snapshot storage, team art, larger weapons and common
bottom alignment remain on this branch. Their older physical acceptance gates
are not closed by reverse synchronization. See [History](../HISTORY_BROWSER.md)
and the [target integration receipt](2026-10-04_ready_workers.md).

## Focused verification and isolation

Fixture review preceded execution. Python ran with `-B -X utf8`, offscreen Qt
and explicit language. Default account roots/settings were redirected into a
temporary directory before UI/domain imports. An audit guard rejected process
launch, network connection/DNS, access to this checkout's runtime/account files,
and SQLite outside temporary fixtures. The corrected single-test rerun rejected
all SQLite access. Both runs recorded zero guard violations. No GTT launcher,
real profile/import, engine, optimizer or broad test suite was run.

Twenty-one distinct focused checks now pass. The first run had 20 PASS and one
History fixture FAIL in 3.751 seconds: its bare `weapon.png` manifest reference
used the superseded project-root assumption. After changing only that fixture
to real account-relative paths, the failed test passed alone in 0.030 seconds.
The other 20 tests were not needlessly repeated. This failure is retained as
fixture evidence, not rewritten into a clean first run.

Exact selected tests (module prefix `tests.`):

| Class/module | Methods or bounded class |
| --- | --- |
| `run_workspace.gcsim.test_gcsim_mixed_source_collisions.MixedSourceCollisionTests` | `test_later_mapping_does_not_admit_scanner_and_hoyolab_as_two_copies`; `test_ambiguous_group_keeps_one_deterministic_canonical_copy_without_db_write`; `test_invalid_lower_canonical_id_does_not_hide_valid_copy`; `test_observation_proof_changes_digest_and_copy_admission` |
| `run_workspace.test_settings_defaults.SettingsDefaultsTest` | `test_defaults_include_known_preferences_and_are_copied`; `test_system_scaling_first_read_persisted_choice_and_reset_share_defaults` |
| `ui.character_assets.test_character_assets.CharacterAssetRuntimeItemsTest` | `test_foreign_profile_keeps_packaged_portrait_when_no_neutral_variant_exists`; `test_foreign_profile_reuses_neutral_variant_by_game_id`; `test_pvp_does_not_reuse_baked_browser_when_transparent_layer_is_missing`; `test_history_uses_raw_portrait_and_weapon_only_for_matching_import` |
| `ui.artifact_browser.test_readonly_queries.ReadOnlyArtifactQueriesTest` | All four temporary-database methods |
| `ui.artifact_browser.test_inventory_bulk_queries.InventoryBulkQueriesTest` | All three in-memory database methods |
| `ui.tooltips.test_inventory.TooltipInventoryTest` | All three source/AST inventory methods |
| `ui.tooltips.test_presentation_contracts.TooltipPresentationContracts` | `test_pvp_run_admission_hints_update_and_clear_without_changing_run_guards` |

Static review parsed 81 changed Python and 10 JSON files. The historical review
snapshot had no conflict markers, unmerged entries, unstaged or untracked files.
Its scope and structural/diff checks are retained in Worker5's shared status
alongside the actual merge result. No inherited 67/83/269-test result is claimed
as a new run here.

The repaired startup fixture was inspected and retained from master, not run:
its child path explicitly uses `--profile-child` and forbids a real supervisor;
its public-boundary test mocks the supervisor and rejects bootstrap/UI entry.
The prior target fixture escape and actual migration remain documented in the
target receipt. Real multiaccount/avatar/import/loader/hover/display acceptance,
the old PvP timer-header issue and numerical response gates remain open.

Root independently checked the review tree/parents, eleven key files against
accepted master, policy/doc differences and the raw-portrait/account-root
fixture. A separate read-only audit of six History files found no loss of
master guards or profile routing: five files matched the first parent, while
team_card_data also retained master's helper. Root checked this receipt's
initial fixture failure, 21 passing checks and evidence limits; the explicit
Worker5-root handoff check passed.

The authorized closeout creates the merge with the two approved parents and
checks ancestry, clean state and handoff structure. It adds no product changes,
app/import/engine run or new product tests. Actual commit/tree/time and checks
are recorded in Worker5's own shared status for collection in the shared event
log. This completion grants no transfer of older History to master or push.
