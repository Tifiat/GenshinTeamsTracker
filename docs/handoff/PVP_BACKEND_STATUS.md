# PvP Backend Status

Last updated: 2026-06-12.

Purpose: implementation-oriented status for the backend-only PvP v0 foundation.
The stable product contract lives in `PVP_V0_CONTRACT.md`. Ruleset/source
mapping boundaries live in `PVP_RULESET_SOURCE_MATRIX.md` and are paused until
real usable tournament files are provided.

## Active Direction

The active backend direction is no-rules Free Draft v0:

- local hot-seat / ghost-deck sessions;
- two `DraftDeck` payloads;
- registered `free_draft_v0` draft system;
- reducer/action log/replay;
- controller plus board/read-model projection API for a future simple UI;
- post-draft team/weapon/timer/result summaries;
- session bundle snapshot/verifier.

Ruleset/balance modules remain report-only research support. They are not the
active implementation direction until real tournament Excel/Sheets/Discord docs
or JSON examples exist.

## AppShell UI Status

The first AppShell integration exists only as a placeholder workspace/policy:

- `LEFT_WORKSPACE_PVP = "pvp"` is registered beside Characters/Weapons,
  Artifacts, and GCSIM.
- When PvP is active, the right operations dock keeps Account/Data visible but
  replaces Abyss/DPS Dummy controls with a `PvP Control` placeholder page.
- Leaving PvP for a normal workspace restores the normal run right dock and the
  previously selected Abyss/DPS Dummy mode.
- The placeholder does not wire `FreeDraftController`, does not render a real
  draft board, and does not mutate normal TeamBuilder/Run state.

## Backend Modules

- `run_workspace/pvp/deck.py`: v0 `DraftDeck` JSON dataclasses, strict
  root/schema/kind loading, stable `to_dict()` roundtrip.
- `run_workspace/pvp/validation.py`: `DeckValidationReport`, Free Draft v0
  deck validation, conservative Traveler rejection, weapon stack/count checks.
- `run_workspace/pvp/schedule.py`: default Free Draft v0 config and explicit
  schedule: 14 steps, 22 actions, 3 bans and 8 picks per seat.
- `run_workspace/pvp/draft_system.py`: executable draft-system registry.
  `free_draft_v0` is registered as version `1`; imported ruleset/balance data
  is separate.
- `run_workspace/pvp/session.py`: deterministic reducer, action rejection
  codes, accepted action log, replay, state hash, team/weapon validators.
- `run_workspace/pvp/free_draft_controller.py`: local manual controller and
  JSON-friendly projection API for future UI. It creates sessions from decks,
  deck files/mappings, explicit account export, or session bundles; computes
  legal targets by probing the existing reducer; applies manual actions through
  `apply_draft_action`; stores post-draft assignments/timers; and builds
  verifiable session bundles. It exposes the UI-facing board projection through
  `to_board_projection(debug=False)` / `to_board_dict(debug=False)` while
  keeping the older compact `to_projection()` contract available.
- `run_workspace/pvp/free_draft_board.py`: backend-only Free Draft board/read
  model. It derives per-seat card statuses and legal target markers from the
  controller/reducer state, plus global pools, action-log rows, schedule
  timeline rows, and compact assignment/result summaries. Compact mode is the
  default; debug mode can add reducer excluded-target reason codes. It also
  owns stable card/timeline status enums and
  `validate_free_draft_board_projection_dict(...)` for UI-contract sample
  validation and private-field smoke checks.
- `run_workspace/pvp/free_draft_board_sample.py`: synthetic UI-contract sample
  builder for the board/read-model projection. The committed sample fixture is
  `samples/pvp/ui_contract/free_draft_board_projection_sample.json` and covers
  initial, after-two-actions, and final/result states.
- `run_workspace/pvp/free_draft_planner.py`: deterministic smoke/dev helper
  that chooses first reducer-accepted actions and simple team/weapon
  assignments. It is not a product bot or optimizer.
- `run_workspace/pvp/match_result.py`: chamber timer totals, lower-time winner,
  draw state, and technical-loss state.
- `run_workspace/pvp/account_deck_export.py`: backend-only Free Draft deck
  exporter from local account SQLite runtime adapters. It excludes artifacts,
  auth/cookies, raw dumps, local paths, SQLite row ids, and fake weapon
  instance ids.
- `run_workspace/pvp/account_deck_copy.py`: small backend helper for creating an
  independent Player 2 copy of an account-derived deck. Stable backend modules
  should import this helper, not the CLI smoke module.
- `run_workspace/pvp/account_full_loop_smoke.py`: account export plus copied
  independent player 2 deck, deterministic draft, assignments, replay, timers.
- `run_workspace/pvp/session_bundle.py`: `gtt.pvp_session_bundle` schema v1,
  embedded deck/session snapshot, replay verifier, assignment/result checks.
- `run_workspace/pvp/ruleset_applicability.py`: report-only capabilities and
  blockers for parsed `TournamentRulesetV1` source data.
- `run_workspace/pvp/ruleset_costs.py`: report-only character/weapon cost
  preview by ids first, with display-name fallback warnings and assignment
  override previews.
- `run_workspace/pvp/ruleset_balance.py`: report-only ruleset/balance
  application summary for decks/bundles. It reports mapping, costs,
  unsupported features, and not-enforced restrictions; it does not execute
  schedules or source scripts.

## Smoke Commands

Default commands write no files unless a command explicitly documents `--write`.

```powershell
python -m run_workspace.pvp.full_loop_smoke
python -m run_workspace.pvp.free_draft_controller_smoke
python -m run_workspace.pvp.free_draft_controller_smoke --json
python -m run_workspace.pvp.free_draft_controller_smoke --step-demo
python -m run_workspace.pvp.free_draft_controller_smoke --account
python -m run_workspace.pvp.account_deck_export_smoke
python -m run_workspace.pvp.account_full_loop_smoke
python -m run_workspace.pvp.session_bundle_smoke
python -m run_workspace.pvp.ruleset_applicability_smoke
python -m run_workspace.pvp.ruleset_balance_smoke
```

`free_draft_controller_smoke` now prints a board/controller summary: draft
system, current requirement, legal target count, first card statuses, status
after two actions, final pools, assignment/result summary, and action-log row
count. `--json` prints compact projection/board reports instead of full card
lists; direct controller callers should use `to_board_dict()` for the complete
board read model.

Stable UI-contract sample:

- `samples/pvp/ui_contract/free_draft_board_projection_sample.json`

Validation helper:

- `run_workspace.pvp.free_draft_board.validate_free_draft_board_projection_dict`

Commands with local account access:

- `account_deck_export_smoke`
- `account_full_loop_smoke`
- `session_bundle_smoke --account`
- `free_draft_controller_smoke --account`
- `ruleset_balance_smoke --account`

## Generated / Private Paths

- `data/pvp/decks/`: optional account deck export output when
  `account_deck_export_smoke --write` is used.
- `data/pvp/sessions/`: optional session bundle output when
  `session_bundle_smoke --write` is used.
- `data/pvp/` is ignored and should not be committed.

Default controller smoke writes no files. Session bundles are backend/debug
artifacts, not PvP History persistence.

## Tests

Focused PvP backend tests live under `tests/run_workspace/pvp/`, including the
Free Draft board/read-model projection, validator, compact JSON smoke shape, and
committed UI-contract sample tests in `test_free_draft_board.py`.

Recommended local checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\pvp -t .
.\.venv\Scripts\python.exe -m unittest discover -s tests\hoyolab_export\tournament -t .
.\.venv\Scripts\python.exe -m run_workspace.pvp.full_loop_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --json
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --step-demo
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --account
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_applicability_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_balance_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_deck_export_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_full_loop_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.session_bundle_smoke
```

## Current Backend Gaps

Still out of scope / not implemented:

- real PvP draft board UI and controller wiring beyond the AppShell placeholder;
- online/P2P/relay transport;
- PvP History persistence;
- deck builder/exporter UI;
- real Gentor/Abyss importer;
- XLSX/Google Sheets/Discord importer;
- ruleset identity mapping / alias layer;
- automatic draft schedule derivation;
- third-party script execution;
- richer ruleset enforcement;
- full localized Traveler support;
- GCSIM scoring for PvP.
