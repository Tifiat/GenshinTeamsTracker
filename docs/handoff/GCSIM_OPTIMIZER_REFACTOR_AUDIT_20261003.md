# Optimizer refactor and Git-baseline audit — 2026-10-03

This is dated source/worktree evidence, not a new numerical acceptance claim.
[GP-3](GCSIM_GOB11_GP3_CHECKPOINT.md) owns installed acceptance and limits;
[TODO](../../TODO.md) owns execution order. The initial audit and structural
slice made no Git changes; the later explicitly authorized baseline is recorded
separately in section9. Historical observations below retain their original scope.

## Conclusion and scope

Selected/All Sets have accepted **bounded backend behavior**, not a declaration
that all optimizer code is clean, the search is globally optimal, or every
energy/schedule/UI case is complete. The 2026-09-28 matrix/install receipts
remain valid within their recorded scope. This audit does not rerun them.

Reviewed the active Go CLI, domain/search/finalists, both All Sets coordinators,
set effects/context/formula/cache boundaries, Python adapters/input builders,
UI call sites, legacy imports/exports, tests, research installers, source patch
stack, distribution cache and Git tracking. Three bounded Sol agents supplied
read-only call-site audits; the parent reviewed their findings. A serialized
Luna job owns verification. No Computer Use, app restart, account writes,
ordinary simulations, new captures or optimizer searches were requested here.

Installed consumer SHA256 is still
`e0bf5d64d6d6341fc434bf81f095e67e3e6a3d3ac43abf4fd7475a293bad6cf4`.
The 2026-09-28 build's source aggregate
`9251adeaf231e26d55e8a61b00f86c41ad2ca4b8c9c3a32648913dbe674918c8`
is dated: that aggregate includes test files, and this audit fixes one test.
The implementation follow-up below also restructures source boundaries; it is
not the source identity of a newly built executable. No Go production arithmetic
or installed executable was changed.

## 1. Git baseline is incomplete

On `master`, HEAD is `d75a1d1`. In `native/gcsim_optimizer` the review found
119 tracked files, 233 untracked files (135 Go files, 97 cache entries and one
provenance file), and 26 modified tracked Go files after the test-only repair.
Examples of untracked **live** implementation include `selected_search.go`,
`grouped_result.go` and `internal/allsets/neutral_coordinator.go`.
`run_workspace/gcsim/patch_stack/0009-gtt-neutral-event-effects.patch` is also
untracked; patches0001–0008 are tracked. The optimizer evidence directory has
82 untracked files at the time of inspection.

A clean checkout from HEAD therefore does not reproduce the installed new
implementation. This is not a claim that the older HEAD fails to compile.
Creating a branch in the current dirty checkout carries changes but is not a
reproducible checkpoint.

Before feature branches, prepare a reviewed baseline containing the complete
optimizer sources/tests, Python integration, required UI/shared-helper hunks,
engine patch stack, portable fixtures and minimal permanent receipts. Shared
files such as `ui/app_shell.py`, settings, locales and artifact catalogs also
contain unrelated work; review dependencies/hunks rather than using `git add .`.
Do not discard, stash or commit unrelated edits automatically. Committing needs
the user's explicit request under CODEX.

The executable and account/runtime data are correctly ignored and must remain
generated/private. The bounded bundled `set-rule-cache` is intentionally not
ignored. Keep its provenance as the historical generation identity, not proof
of the current consumer. Retain it as a reviewed distribution input or make its
rebuild reproducible before removing it. No `.gitattributes` exists; a future
line-ending decision must not trigger an unrelated whole-project rewrite.

## 2. Confirmed obsolete Go paths

These are cleanup candidates, **not current ranking bugs**. Current product
routes do not call them; tests/research references must be migrated first.

| Component | Observed callers / issue | Safe disposition |
| --- | --- | --- |
| `cmd/gtt-optimizer/main.go`: `buildProductResult`, `buildMeasuredProductResult` | Old top-five projection; live route uses grouped results | Removed; warning/energy/identity assertions moved to `grouped_result_test.go` |
| Same file: `boundedN1000Finalists` | Test-only n128/n1000 ladder with `mandatory_current` | Removed with obsolete tests; separate development controls retained |
| Same file: `maxProductCandidates`, `uniqueCandidates` | Initial audit misclassified these: `theory.go` still uses the limit and `selected_search.go` uses deduplication | **Retained live** after implementation-time caller recheck |
| `internal/finalists/adaptive.go`: `VerifyAdaptive*` | No production caller; old tests and historical preflight overlay | Retire after migrating useful resource/error checks; reconcile the retained `Adaptive` result/warning compatibility field |
| `internal/engineclient/ordinary.go`: package-level `RunOrdinary` | Repository-wide Go search found no caller; the bound client method is live | Unused wrapper removed; bound engine client and hash gates retained |
| `seteffects.NewSignalProbe`, `Description.OwnerStatSignals` and associated response signals | Only tests/historical research, no product scoring consumer | Retire the old-context proposal chain after preserving useful source oracles |
| `setcontext.constantEffectKey` | Test/research wrapper; live cache uses `projectedConstantEffectKey` | Move oracle-only support to tests or remove superseded research |
| `chooseFinalists(pool, initial, selected, limit)` | `initial` and `selected` were unused; old comment promised their preservation | Now `chooseFinalists(pool, limit)`; ranking unchanged |

The `main.go` header incorrectly described staged finite Selected measurement;
it is corrected. Both product Selected energy modes use the final n500 path.
Old n128/n1000/current-reservation code is not evidence that those rules still
affect the button. The two live-symbol corrections above supersede the initial
audit classification; they are not new dead-code discoveries.

Do **not** blanket-delete the full-context coordinator, source discovery,
portable map/compact composition oracles, or development controls. Finite
All Sets, Theory, source audits and strict parity tests still use parts of them.
Synthetic static replacement certificates have no production producer: isolate
or retire their pilot machinery only after preserving capture identity checks.
`NewEngineProvider` itself is live through `NewEffectEngineProvider`.

## 3. Live routes and structural refactor

`ui/app_shell.py` → `ui/gcsim_browser/run_worker.py` → the three Go sessions:

| Mode | Native command / route |
| --- | --- |
| Selected | `verify-fgbs ... all`; fixed chosen package, common item search |
| All Sets | `optimize-all-sets`; `RunNeutral` only for infinite energy with required neutral capability/rules, otherwise `Run` |
| Theory | `optimize-theory`; separate theoretical allocation |

All Sets builds a canonical inventory reference before either coordinator.
The account's equipped build is not a reserved ranking candidate. There is no
Python numerical fallback on these button paths.

At audit start `optimizer_go_selected.py` was about1500 physical lines. Its
shared `_prepare_inputs` served all three modes while inferring Theory from
`virtual_artifact_policy`; All/Theory imported Selected private helpers.
The follow-up extracts common requests, input preparation, process lifecycle
and result text into `optimizer_go_requests`, `optimizer_go_inputs`,
`optimizer_go_session` and `optimizer_go_result_text`. Canonical/diagnostic
writers live in `optimizer_go_contracts`. Preparation takes an explicit mode.
Selected is now a small capture/command facade; All no longer inherits its
compact-capture implementation. Theory keeps All's verified source transport,
its own command and its unchanged finite-mode rejection.

The old `_prepare_inputs` policy facade and public Selected request/error names
remain compatibility aliases for research/import consumers, not a numerical
fallback. Shared error-code/wire-identity spellings containing Selected are
retained intentionally. Tests patch the new owning modules. No new UI widget
coupling was introduced.

Preserve immutable snapshots, source validation, exact engine binding, cleanup,
Finish/Cancel distinction, Selected fixed packages, All canonical inventory,
Theory's zero-inventory wire form and finite-mode rejection. UI should request a
mode and display DTOs, not reach into a private session mode field. Deduplicate
progress/finish labels without tying numerical code to present widgets.

The large live coordinators/search files can be split by responsibilities after
these boundaries are stable. File length alone does not justify replacing the
accepted numerical algorithm.

## 4. Legacy Python, exports and wire contracts

`optimizer_product_contracts.py` is about3896 physical lines and combines live
artifact/wearer/materialization types with legacy farming/result adaptation.
The actual Go wire boundary is `optimizer_go_contracts.py`; these are not a
second Go request schema. Materializer/input callers are live, so deleting the
large mixed file would break the product. Separate its live shared types first.

The old `optimizer_backend`/`optimizer_runner`/`optimizer_candidate` chain is
reachable through farming helpers and lazy package exports, but no current UI
caller for its advisor/automatic/optimized entrypoints was found. Repository
non-test/non-research callers are absent; exported APIs can still have external
consumers. Explicitly retire those exports, then remove the disconnected closure
and obsolete tests rather than keeping a second optimizer fallback. Shared
configuration, materialization, two-piece signatures and optimizer cleanup are
live and must remain.

`source_manifest_build.py` previously imported strict codecs from
`trace_equation.source_dependencies`, loading a deeper trace closure.
The manifest round-trip gate remains live, but codecs now belong to standalone
`source_manifest_codec.py` and the shared error to `trace_contract_error.py`.
Old trace modules re-export the same objects; binding/replay logic remains
there. A fresh-process test proves strict source validation does not load
`trace_equation`. Legacy result-shape fallbacks in the UI are compatibility
readers, not proven dead code; version or explicitly retire them.

The request schema validates `FinalistPolicy`, `DevelopmentTimeoutMS` and
`Cancellation.Mode`, but those values do not control the current product
measurement/work flow. The real product uses fixed n500, output options and
cooperative Finish/context cancellation. Mark these old fields as deprecated
compatibility input and make ignored semantics explicit, or retire them through
a versioned schema/fixture migration. Do not silently reinterpret v1 fixtures.

## 5. Cache and research tools

`warm-set-cache` previously ran full unfiltered legacy discovery just to prepare
source syntax/schedule metadata. It now uses
`CompileSourceBundleForCacheWarming`: all source entries, no inventory filtering,
`LegacyPrepared=false`. Full compilation remains unchanged for finite All Sets,
Theory and audits. New tests cover rules, source identity and schedule metadata
against the full compiler. Cache identity/eviction/repair/library boundaries
and the distinct AST parser options remain unchanged. No bundle was regenerated
and no new speed gain was measured.

Research includes historical source overlays and installers as well as useful
portable evidence. `install_search_schedule.py` still has a mutation-capable
main; later gates import its source-oracle helper. `install_neutral.py` also
exports helpers used elsewhere. Move reusable verification/hash utilities to
non-mutating helpers before disabling/removing obsolete installer entrypoints.
Do not delete whole files solely because their main is historical.

Accepted native implementation must be the sole product path. After the
baseline is reproducible, remove redundant source overlays/installers and their
orphan tests under the existing cleanup gates. Retain compact failed/success
receipts, portable regression fixtures, current source inputs and required
active/rollback engines. No product import from `tools.experiments` or `tests`
was found. No raw managed jobs are retained by this audit.

## 6. Local maintenance and verification

- Removed the unused `gcsim.optimizer.all_estimate` locale key that still
  described time-limited18-minute search; no UI caller was found.
- Corrected the Portuguese infinite-energy explanation and the native README's
  obsolete pilot/staged-measurement descriptions.
- First managed job `.codex_tmp/managed-optimizer/job-dp6pv7zc` failed
  `go vet ./...`: `guide_test.go:147` copied a `SourceCatalog` containing a mutex.
  **No test suite was launched in that job.** Cleanup removed72,463,167 bytes
  and restored the1-byte managed-root baseline.
- The test-only repair constructs a fresh source identity and checks the
  identity-boundary error explicitly instead of copying the catalog/lock.
  Full source-arithmetic/search behavior and installed binary remain unchanged.
- Repaired managed job `.codex_tmp/managed-optimizer/job-i5qepi2t` passes
  `go vet ./...` and `go test -json -count=1 ./...`: all15 packages pass,
  no failures. Of34 runtime skips,32 are explicitly cleared live/saved/source
  GTT gates and2 are Windows symlink/junction limits. These skips do not certify
  an active-engine source oracle or schedule response. Cleanup removed96,174,712
  bytes; job directories are absent and the managed root is back to1 byte.
- All three edited locale files parse as JSON; the deprecated key has no
  remaining locale/UI/runtime/test occurrence. Handoff structure/budgets/current
  projections pass. Scoped whitespace checks pass with CRLF treated as line
  endings; no whole-file line-ending normalization was performed.

## 7. Proposed cleanup sequence and acceptance

1. Review the complete optimizer baseline and shared dependencies; preserve a
   reproducible Git checkpoint before deleting experimental implementations.
   No blanket staging of other project work.
2. Retire confirmed dead Go product helpers and migrate useful tests to live
   grouped-result/finalist paths. Remove stale comments/unused parameters.
3. Separate live Python transport/input/DTO/manifest-codec boundaries, explicitly
   retire disconnected farming/pilot exports and remove their dead closure.
   Keep small compatibility readers only with a documented owner/retirement gate.
4. Separate source-cache compilation intent and pure test tools from historical
   installers; remove superseded research after the baseline/retention gates.
5. For each production refactor, require vet/unit gates, focused mocked
   adapter/UI gates, frozen request/capture output parity, legal assignments,
   identical ranking/groups/trial accounting, Finish/Cancel and finite routing.
   Production changes require proportional same-engine numerical checks; passing
   unit tests is not a replacement for them. Rebuild/install only through the
   normal identity/parity gate. Then establish reviewed cleanup commits and
   start feature branches from that baseline.

This is a staged structural cleanup, not a reason to rewrite the search math or
repeat the full matrix before removing test-only code. The remaining Theory,
finite-neutral, changed-item schedule-response and global-search limitations
are not erased by a clean tree.

## 8. Authorized implementation follow-up — same date

The user approved proceeding without another architecture choice. Removed the
confirmed dead projection/n1000 helpers and the unused ordinary-run wrapper;
kept the two rechecked live helpers, both All Sets energy routes and historical
development controls. The shared adapter and manifest-codec extraction above
is implemented. Input preparation after explicit mode selection and all ten
moved input helpers match the pre-refactor text after only the shared
error/request/canonical-writer symbol renames. This is a source-extraction
check, not an engine response or numerical matrix run.

| Managed attempt | Scope and actual outcome | Cleanup |
| --- | --- | --- |
| `job-uwmrgpp5` | vet PASS; 15 native packages PASS; first Python check reports82 tests/6 errors, no assertion failures. Selected facade missed `_request_wearers`; a source-serialization mock had an empty character payload. |96,117,739 bytes removed |
| `job-zckffa3o` | Restored compatibility alias and a valid four-character fixture without weakening runtime validation. vet PASS; 15 native packages PASS; 11 Python modules94 tests plus2 offscreen UI modules25 tests: **119 PASS**, no failures/errors/skips. |96,171,389 bytes removed |
| `job-lyg1pnb5` | After the unused ordinary wrapper removal only: vet PASS and all15 native packages PASS. Python/UI files unchanged; no repeat Python phase. |96,159,118 bytes removed |

Each native pass has34 explicit skips:32 disabled live/source/saved/capture
gates and2 Windows symlink/junction limitations. Every job was absent after
cleanup; no `job-*` residue and the managed root returned to its1-byte baseline.
One low-context Luna agent ran these serialized checks. Source review/coding
used bounded Sol tasks. No build/install, capture, ordinary simulation, search,
matrix, Computer Use, app restart, equipment/DB write or Git mutation occurred.
The first Python failure remains FAILED evidence, not retrospectively PASS.

### Baseline and remaining retirement gates

The baseline needs the complete current native module/tests; six new Python
runtime modules above plus boundary/codec tests; the verified patch stack,
portable fixtures/receipts and reviewed source-cache provenance. Do not omit
untracked live files simply because the current executable already exists.
`hoyolab_export/asset_paths.py` is a required untracked import of the result UI.
`ui/app_shell.py`, `ui/gcsim_browser/run_worker.py`, `optimizer_result.py`,
`ui/right_panel/settings/account_data.py` and the three locale files mix
optimizer changes with assets/import/History/ordinary-run work. They need hunk
and dependency review, not whole-file blanket staging. The bounded bundled
cache is a reviewed distribution input, not disposable account cache.

The bounded read-only hunk review found no architecture choice required:

| Shared file | Optimizer anchors to retain | Work not automatically included |
| --- | --- | --- |
| `ui/app_shell.py` | effective optimizer settings, request options/engine ID, Finish signal/handler, formula/partial result handling | character/weapon assets, virtual catalog refresh, ordinary-run binding, Artifact Browser synchronization changes |
| `ui/gcsim_browser/run_worker.py` | `GcsimBrowserSelectedOptimizerWorker.request_finish` | other hunks are ordinary-run binding/partial/report-identity changes, coupled to ordinary AppShell hunks |
| `ui/gcsim_browser/optimizer_result.py` | grouped/formula results and single-item replacement data/UI | source-of-icon refresh is independent; if retained, include its `asset_paths.py` import dependency |
| `ui/right_panel/settings/account_data.py` | optimizer controls/handlers and checkbox/spinbox imports; scrolling layout needed for the current controls | HoYoLAB image refresh/import progress |
| three locale JSON files | optimizer settings/progress/elapsed/ranking keys | History and HoYoLAB/import keys |

`asset_paths.py` directly imports only stdlib and existing
`HOYOLAB_DATA_DIR`/`PROJECT_ROOT` in tracked `hoyolab_export/paths.py`; its chain
does not require untracked `asset_layers.py` or the added shared-assets constant.
The dependency/hunk map is reviewed, but no temporary index/commit was assembled
and no clean-checkout gate ran. A future baseline must check that selected hunks
are internally complete; ordinary-run changes cannot be half-selected.

Still gated, not silently deleted: old adaptive verification and its compatible
metadata; signal-probe/static-proof research; detached farming exports and
mixed product-contract adapters; old schema-v1 policy fields and UI compatibility
readers; mutation-capable research installers/overlays. Removing these requires
a reproducible baseline and/or their documented compatibility/reference gates.
Future Theory math references remain retained until that scope is accepted or
abandoned. No fresh-checkout reproducibility or installed post-refactor parity
has been claimed. No file was staged and no branch/commit was created.

## 9. Authorized whole-project baseline and isolated worker preparation

The user explicitly requested committing the complete mixed working state on
`master`, then separating Selected/All Sets polish and Theory into linked
worktrees. This supersedes the earlier optimizer-only shared-hunk staging plan,
not the credential/runtime exclusions or unfinished acceptance gates. No push,
new chat, app launch or additional numerical matrix was requested.

The low-context safety audit found no recognized credential/authentication/raw
browser/API material in the reviewed nonignored candidate files. The97 source
AST cache entries and34 design PNGs are intentional tracked inputs. The6.44MiB
`all-sets-inventory-20260919/after.json` is reproducible optimizer work evidence,
not a raw account/API dump: preserve it and the original receipts, including
failures and historical engine paths. This is a scoped pattern/schema review,
not a universal secret-free certification.

Metadata-only storage walk:5,721,652,536 bytes,109,320 files,16,199 directories,
no links/reparse entries or traversal errors. Main contributors: data2.01GB,
research scratch1.17GB, dependencies811MB, browser profile484MB, exports440MB.
These are not all trash. Historical worktrees, evidence archives, protected
captures and user exports keep their existing deletion gates; do not clone them
into the second worker.

Two concrete maintenance defects were addressed: completed source downloads
previously had no updater retention hook; old pinned optimizer runs were counted
after newer ordinary runs and could incorrectly exceed the ordinary byte budget.
The source cleaner is conservative (two versions/512MiB, retained references and
unsafe-state protection). Run cleanup now charges all protected runs before
selection and rechecks late pins/leases/links before deletion.

`tools/bootstrap_optimizer_worker.py` seeds only a fresh registered linked
worktree through managed scratch. Its SQLite backup includes committed WAL;
active/rollback engine manifests use the existing directory-hash protocol.
Copied settings, account data, public references and assets are local worker
copies; credentials, browser state, old runs/source/build caches are excluded.
One16KiB-max local receipt owns seeding identity, not a new shared database.

| Managed attempt | Actual focused result | Cleanup |
| --- | --- | --- |
| `job-oxwq0iuw` |58 tests:46 PASS,9 errors,1 failure,2 platform skips. Bootstrap held SQLite connections after transaction context exit; Windows refused DB rename/cleanup. No live database touched. |124,074 bytes removed; no job residue |
| `job-iui3v1kg` | Explicitly close source/destination and test SQLite connections. Same six lifecycle/store/context modules plus retention regressions:61 tests,58 PASS,3 platform link skips,0 failures/errors. |0 residual file bytes; job removed, root remains its1-byte lease |

Initial run-retention preview exposed95,942,345 over-budget bytes despite the
protected data fitting the budget. Corrected preview identifies four ordinary
completed run directories totaling95,992,687 bytes. Applied only those four
validated targets: protected evidence136,975,926 bytes and ordinary retained
results131,409,188 bytes fit the256MiB budget; no errors. Unknown historical
directories and permanent receipts are preserved. Raw removed files are not
recoverable from Trash; rerun to regenerate them. Source-cache preview retains
both completed versions (272,547,904 bytes), protects v2.45.0 and needs no
deletion. Clean-checkout proof and branch creation are pending below.

Git staging initially hit a stale empty `index.lock` dated2026-09-19. No Git
process was present and an exclusive handle check succeeded; only that empty
lock was removed, never the index. Staging then succeeded. Whitespace diagnostics
were confined to literal unified-diff context inside `.patch` files; all other
staged files passed. The narrow `.gitattributes` rule keeps patch payloads LF on
Windows and excludes context-space false positives, without changing production
patch bytes or normalizing other source files.

The whole mixed working state, 637 reviewed staged files, was committed as
`dc08ce343ffc38922c0cec5b2a7c29f7e06de7c8` on `master` with a clean index.
A linked checkout at `C:/Users/user/Desktop/worker2 GTT` starts at that commit
on `codex/optimizer-theory`; the production patch0009 bytes match the primary
checkout. The managed seeder copied406,176,639 bytes of runtime input and
removed its job `job-3w32p_4t`. The resulting checkout is520,157,845 bytes
(13,552 files), versus5,721,652,536 bytes in the primary pre-cleanup walk;
that comparison excludes the primary's later95,992,687-byte run cleanup.
No primary `.venv`, browser profile, old run logs, build/source caches, exports
or research scratch was copied. Worker imports, settings, run root, optimizer
binary and engine store resolve inside the worker checkout. The active engine
context is trusted, with the same engine ID and binding hash as primary; the
copied consumer hash matches the seed receipt. The worker database is a separate
file, matches the seed receipt and passes SQLite `quick_check`. This is backend
path/identity validation, not a button or numerical optimizer acceptance run.

Fresh linked-checkout gate used the primary Python dependencies read-only, with
the worker as current directory and its own managed scratch. All four inspected
module origins resolved inside `worker2 GTT`. Selected, All Sets, Theory,
transport/codec, engine, retention, bootstrap and offscreen result UI tests:
82 total,79 PASS,3 Windows link skips,0 errors/failures. Its job was removed.
No simulator search, account mutation or physical button was run. Branch
separation is source/runtime readiness; numerical and user-path gates stay open.

## 10. Bounded polish closeout — 2026-10-04

The user authorized one changed-item numerical case, guarded cleanup and own
verified local commits, not another matrix or cross-branch transfer. The current
checkpoint owns the resulting acceptance boundary; the new closeout receipt
records the response evidence separately from the dated matrix.

Rechecked the old-code callers before deletion. Removed only the unexported
`constantEffectKey` forwarding alias. Its five native test calls and the
historical effects-comparison overlay now call the existing
`projectedConstantEffectKey(keys, keys, effects)` directly. Full-vector identity,
signed-zero/rejection and eviction controls remain; live projection, formula
arithmetic, cache limits and effect evaluation are unchanged.

Retain adaptive metadata/warnings and historical verification controls;
signal/discovery oracles; Python farming exports/mixed contracts; schema-v1
compatibility readers; source overlays and guarded research promoters. These
still have useful reference or compatibility obligations. No Theory/finite
coordinator, engine/patch stack or gameplay implementation was removed.

The compact-adapter smoke test initially counted two patches because an
unchanged context line in patch0009 mentions the capability defined by patch0001.
It now counts added definitions and tests definition/context/removal/duplicate
cases. This is a test repair, not an adapter or engine fix. The failed initial
check remains evidence; the focused rerun passes.

[Closeout evidence](../optimizer-evidence/2026-10-04-optimizer-closeout/README.md)
records123 distinct Python/offscreen checks with no skips, four native package
vet/unit checks and the injected config predicate PASS. The initial numerical
harness failed to compile before any engine capture; its immutable failure is
retained. One local harness-only repair enabled the bounded retry: exactly10
trace seed members, no ordinary n500 stage or full All Sets search.

Numerical acceptance FAILED. Chasca top1 reused150008.566 versus fresh
151488.295 DPS; plume/goblet alternatives remain worse in both estimates.
The three fresh cases have identical topology to each other, but differ from
the incumbent/neutral panel in both seeds. Neutral fixed-package predictions
equal Selected predictions. This does not establish an arithmetic error or
exact response; frozen dependencies and changed-schedule attribution remain.
The pinned Selected case was mislabeled Navia in earlier prose: its input is
Chasca, unchanged SHA25611532ecb. Older All Sets Navia evidence remains dated.

Both managed jobs were removed (79,926,578 and183,394,212 bytes), with no residue;
active engine and default consumer hashes were preserved. Only one regenerable
11,994-byte research bytecode file was removed separately. UI geometry/help and
mocked save payload pass; actual visible UI/preset persistence are unverified.
No cross-branch transfer, push or other worker's source modification occurred.
