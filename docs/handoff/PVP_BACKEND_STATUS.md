# PvP Backend Status

Last updated: 2026-06-13.

Purpose: implementation-oriented status for the backend-only PvP v0 foundation.
The stable product contract lives in `PVP_V0_CONTRACT.md`. Ruleset/source
mapping boundaries live in `PVP_RULESET_SOURCE_MATRIX.md` and are paused until
real usable tournament files are provided.

The PvP UI roadmap is intentionally separate: see `PVP_UI_ROADMAP.md` for the
AppShell/Decks/Play/Draft/assignment/result UI direction.

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

The first real PvP AppShell UI stages are Decks v0, Play/local setup v0, and
Draft board v0:

- `LEFT_WORKSPACE_PVP = "pvp"` is registered beside Characters/Weapons,
  Artifacts, and GCSIM.
- When PvP is active, the right operations dock keeps Account/Data visible but
  replaces Abyss/DPS Dummy controls with real `Decks`, `Play`, and `Draft`
  pages.
- Leaving PvP for a normal workspace restores the normal run right dock and the
  previously selected Abyss/DPS Dummy mode.
- Decks v0 persists local presets under `data/pvp/decks/`, shows account
  characters/weapons in view/edit mode, and validates by converting presets to
  backend `DraftDeck`.
- Play/local setup v0 lists saved deck presets, validates selected Player 1 and
  Player 2 decks through the same conversion path, creates an in-memory local
  `FreeDraftController`, and switches to Draft.
- Draft board v0 renders the backend `to_board_dict()` read model in the left
  PvP workspace, lets legal character cards call
  `FreeDraftController.apply_current_action(...)`, refreshes only from backend
  projection after actions, and shows completed picks/bans/action-log summary
  when the Free Draft schedule ends.
- Draft board v0 is playable through the full local Free Draft schedule, but it
  is still a per-seat technical board. The next backend/read-model target is a
  dedicated `unified_pool` projection for the readable Draft UX.
- Decks/Play/Draft v0 do not persist sessions/history and do not mutate normal
  TeamBuilder/Run state.
- The UI roadmap and stage direction are owned by
  `PVP_UI_ROADMAP.md`; this file should remain backend/status focused.

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
  validation and private-field smoke checks. It does not yet expose the future
  backend-owned `unified_pool` read-model.
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
- `run_workspace/pvp/weapon_identity.py`: shared PvP observed weapon-stack
  identity bridge for Deck presets and future PvP screens. It models one
  selectable account observed stack, prefers `weapon_fingerprint`, uses a
  structured field fallback without localized names/paths/provenance fields,
  preserves `known_count` as stack count, and converts refs to backend
  `DraftWeaponStack` without fake copy ids.
- `run_workspace/pvp/deck_preset.py`: thin Decks UI preset persistence wrapper
  (`gtt.pvp_deck_preset`) under `data/pvp/decks/`. It stores stable
  `character_ids` and observed weapon-stack refs without localized names or
  local paths, delegates weapon identity/conversion to `weapon_identity.py`,
  then converts to `DraftDeck` for backend validation.
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

- `data/pvp/decks/`: local PvP deck preset JSON from Decks v0 plus optional
  account deck export output when `account_deck_export_smoke --write` is used.
  Preset loading skips backend `gtt.pvp_deck` export files in the same folder.
- `data/pvp/sessions/`: optional session bundle output when
  `session_bundle_smoke --write` is used.
- `data/pvp/` is ignored and should not be committed.

Default controller smoke writes no files. Session bundles are backend/debug
artifacts, not PvP History persistence.

## Tests

Focused PvP backend tests live under `tests/run_workspace/pvp/`, including the
weapon observed-stack identity helper tests in `test_weapon_identity.py`, Free
Draft board/read-model projection, validator, compact JSON smoke shape, and
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

- backend/read-model `unified_pool` projection for the readable Draft UX;
- PvP team assignment UI;
- timers/results UI;
- online/P2P/relay transport;
- PvP History persistence;
- real Gentor/Abyss importer;
- XLSX/Google Sheets/Discord importer;
- ruleset identity mapping / alias layer;
- automatic draft schedule derivation;
- third-party script execution;
- richer ruleset enforcement;
- full localized Traveler support;
- GCSIM scoring for PvP.
