# Rotation editor working window — 9 October 2026

Current owner: [READABLE_ROTATION_EDITOR.md](../handoff/READABLE_ROTATION_EDITOR.md).
The human authorized implementation with «приступай» after the separate-window
proposal. This is a working interaction prototype; final product layout and
native AppShell acceptance remain open.

## Delivered behavior

- A button beside existing GCSIM Browser Code opens a separate maximizable
  editor. It has a nested readable document, Code, command navigation with Back,
  one selected-block properties panel and optional simulation settings.
- The same source tree owns all projections. Character windows are ranges of
  statements, not a second persisted model. Clicking selects; crosses delete
  an action/command/window; actions can move within their source sequence.
  Insertion after a middle action splits a multi-action line at the correct
  place. Wrapping an action or complete window retains neighboring commands.
- Buttons create actions, waits, counted/infinite cycles, if/else, conditional
  repetition and rotation schedules. Conditions have nested all/any/not;
  thresholds, full energy, readiness, onfield, timers, constellations and the
  audited personal states are properties. Bennett/Chasca/Furina variants use
  the existing explicit preparation/guard API. Inspecting an import does not
  insert preparation. Chasca's partial-bullet restriction remains visible.
- Holes are highlighted. Incomplete structural drafts have no generated Code
  and cannot apply. Invalid raw Code is retained and must be corrected before
  structural editing. Pending text is flushed before actions/details; stale
  property callbacks are rejected. Code and blocks share bounded undo/redo.
- Apply validates and signals the existing browser field only if its initial
  text and engine binding still match. A conflict retains both documents.
  Close/reopen in the living browser retains draft/history. Explicit Reload
  replaces the draft; a replacement is constructed before discarding the old
  window, so failed construction preserves it. No account persistence added.

## Admission and limits

Local aliases and docs come from the active source installation. Special
interpretations require repo `genshinsim/gcsim`, ref `v2.45.0`, and fingerprint
`c9e00c1820dd5844e0e7833f7cdd5d3fb15bed5329f4036691ad3d967e3f7bd9` over
the 75 Go files enumerated in `integration.AUDITED_GROUPS`. Digest input is
sorted forward-slash relative path, NUL, bytes, NUL. This binds the current
audited slice to earlier evidence; it does not independently prove the whole
engine commit, executable, all dependencies or runtime mechanics. No revision
is guessed for metadata network fetches. Unknown source keeps ordinary commands
and detailed Code, without enabling audited condition/variant constructors.
The edit/apply identity additionally covers aliases, docs, profile and the
manifest's declared tree hash; it changes even if engine ID stays the same.

Public-fixture names Furina/Chasca/Bennett/Ororon have explicit app translations.
Other names use prepared engine display labels or stable keys. No translated
name is used to infer engine identity. General localized character-name resolver,
first-selection network/cache fallback, loader integration and new personal
mechanics remain future work. Existing versioned option service is unchanged.
The input limit is 2 MiB; the document pane explicitly shows at most 400 blocks,
retaining full Code. UI does not simulate cooldowns or prove battle readiness.
Character-window movement and arbitrary detailed expressions use Code for now.

## Verification

Focused Python/Qt tests cover independent expected ordering, projected-window
deletion including hidden swaps/nested conditions, middle-line insertion,
wrapping, last-action removal, holes, undo/redo, cycle property changes, character
navigation, raw Code editing, compound predicates, large schedule values,
explicit Chasca preparation, else filling, unknown-engine admission, changed
metadata, browser apply conflicts, engine change, failed flush retention,
pending Details and stale property callbacks. Offscreen Qt checks supplement
the backend and browser regression suite. Final combined run: **154 tests PASS**,
including 17 focused Qt/admission checks and 9 structural editing checks.

The real selected Go parser matched the previous 25 public source pairs,
19 generated block pairs, 90 schedule truth checks, 23 condition/variant pairs
and 34 condition truth checks. Added **7 structural-edit pairs** compare to
independently written expected GCSL, rather than the editor's own canonical
output. This is parser/config evidence only, without evaluation or simulation.

Independent bounded source review found pending-Code loss during Details and
stale-property invocation, plus ignored flush failure during engine re-open.
These were fixed and given regressions; the reviewer rechecked the paths and
found no remaining issue in its bounded scope. No broader safety verdict claimed.

The standalone public-fixture preview was launched through project Python,
without AppShell/account bootstrap or simulation. Computer Use displayed its
native document and properties; helper input encountered changed bounds/user
input, so further native inputs were stopped and the window left to the human.
No successful automated native click sequence or main-browser acceptance is
claimed. One oversized Qt input test stalled during text layout; only its
verified owned offscreen processes were stopped. Its regression now injects
the parser-limit failure into a small draft, keeping the retained-text assertion.
The human's interactive preview process was preserved.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:GTT_LANGUAGE='ru'
.venv/Scripts/python.exe -B -X utf8 -m unittest tests.run_workspace.gcsim.test_rotation_editor tests.run_workspace.gcsim.test_rotation_options tests.run_workspace.gcsim.test_rotation_validation tests.run_workspace.gcsim.test_rotation_source tests.run_workspace.gcsim.test_rotation_semantics tests.run_workspace.gcsim.test_rotation_conditions tests.run_workspace.gcsim.test_rotation_variants tests.run_workspace.gcsim.test_rotation_editing tests.ui.gcsim_browser.test_rotation_editor_ui tests.ui.gcsim_browser.test_gcsim_optimizer_ui
.venv/Scripts/python.exe -B -X utf8 tools/check_rotation_editor.py --engine-root data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932
```

## Human smoke route

On a restarted AppShell: GCSIM Browser → «Открыть редактор ротации». Select
the cycle and change count; select an action and inspect/change repeat or
personal variant; select a body placeholder and add an action; test Back,
cross/Undo/Redo, Code and Details. Apply should update the browser Code. If
that field is edited while the window is open, Apply should retain the draft
and report a conflict. Final convenience decisions are grouped after this trial.
Do not switch `main.py` to AppShell as part of this stage.

The account-free public example is also runnable independently:

```powershell
.venv/Scripts/python.exe -B -X utf8 tools/preview_rotation_editor_ui.py --engine-root data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932
```

That preview only keeps edits in memory and displays validated Code. It never
writes the application rotation or account. Close ends the standalone draft.

## Local closeout

Own package on `master` over clean `7374af19340fb9e176680d6e17a9794ff32c42b9`.
The direct user instruction and CODEX authorize its verified local commit.
Scope: editor core additions, editor UI/browser entry, three locales, focused
tests/check helper, public preview launcher and owning handoff/receipt/catalog.
No account, engine installation, optimizer behavior, persistent cache, push or
peer transfer. Hub/status/journal remain owned by the orchestrator and were not
edited by this execution chat. This fixed receipt is versioned; no screenshot
files, private data, second queue or accumulating generated logs are retained.
Final resulting commit hash is reported to the human after the local operation.
