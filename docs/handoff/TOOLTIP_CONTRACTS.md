# Tooltip regression contract

<!-- handoff-current: tooltip-regressions -->
2026-10-04. Worker5's source is integrated on local master. Each registered tooltip family has semantic
fixtures and the UI binding inventory rejects unregistered new entry points.
The suite exercises actual controllers, chamber-cell refresh, History popup
painting, local-image loading, locale completeness and set description freshness.
Empty translated HTML no longer hides the English bonus; reinstallation updates
one popup and clearing a payload removes its old text. Remaining native action
hints were moved to the shared custom surface.

In Worker5, `tools/check_tooltips.py` passed all 67 checks, including the existing active
account's Emblem of Severed Fate 2p/4p text on both surfaces. Existing
account-page/import lifecycle/settings checks also
passed in a 50-case combined run (overlaps the tooltip suite; do not sum counts).
These are offscreen/controlled checks plus a read-only local-catalog witness.
The user's visible AppShell hover acceptance remains separate and no app was
restarted for this change. Local commit is now authorized separately from that
acceptance; [transfer scope](WORKER5_TRANSFER_PACKAGE.md) records its boundaries.
The [target receipt](integration_receipts/2026-10-04_ready_workers.md) separates
controlled main tests from that earlier real-catalog witness. Main now covers
PvP run-admission block/update/clear through the same shared custom surface,
with its own semantic regression and binding registration. No fresh main
real-account witness or visible hover acceptance is claimed.
<!-- /handoff-current -->

## Required workflow

A reported tooltip defect is fixed together with a regression for that defect.
Do not weaken an assertion to accept a broken screenshot. Update the relevant
family in `tests/ui/tooltips/test_inventory.py` and its independent expected
content when a legitimate source/product change changes the contract. Every
new tooltip binding must be classified; adding only a name to the inventory
without a semantic check is not sufficient.

Run `python tools/check_tooltips.py`; add `-v` for individual cases or `--db`
with an existing account `artifacts.db` for an explicit source. The command
forces offscreen Qt, never creates an account, does not log in, and writes no
catalog, snapshots, credentials or screenshots. It uses this checkout's active
profile by default without invoking profile bootstrap or migration. Only the
set IDs and descriptions needed for the semantic witness are inspected.

## First available real set

`known_sets.py` contains independently reviewed facts for Emblem of Severed
Fate, Deepwood Memories and Noblesse Oblige, in EN/RU/PT (both `pt-pt` and `pt-br`
catalog tags). Content/API language is separate from the app's UI locale.
Source links and review
date are attached to the expectations; fixtures are authored API-shaped examples.
Expected percentages, triggering mechanics, duration and piece boundaries are
independent of the import/parser/display implementation.

The account check selects by **owned artifact `set_uid`**, not the seeded list
of every possible set. It walks the ordered witnesses until the first owned
set, then checks both 2p and 4p through the right-panel mini-zone and Artifact
Browser custom-tooltip handlers. A missing set advances to the next candidate.
A present set with absent/incorrect text fails immediately; it must not fall
through to another set that happens to pass. If none is available, emit
`TooltipCoverageWarning` asking to extend the autotest, without failing the
clean/uncovered account. This warning is not a claim of real-catalog coverage.
Per-piece language fallback is checked independently. Deterministic tests
exercise all reviewed witnesses regardless of what the user's account owns.

## Families and boundaries

The executable family index covers artifact bonuses/slots; account characters
and weapon stacks/passives; equipment warnings; resonance, Moonsign and Hexerei
bonus variants/member descriptions; factual enemy HP/DPS and GCSIM status;
History painted character cards, enemies, bonus overflow and compact summaries;
PvP draft ownership/postdraft equipment/run admission; optimizer save/replacement help; virtual
editor hints; filters, actions, profile deletion and account/legacy import state.
Shared presentation tests cover plain/rich text, escaping, one controller per
widget, active-text refresh, clear/hide and grid hover identity. Supplemental
tests retain DB/WAL/language freshness, transient lookup recovery, 2+2 boundaries,
Windows file URIs and popup positioning/dismissal during scroll.

The structural inventory scans production tooltip binding calls and counts
calls inside each registered method, excluding developer smoke launchers. A
mutation check ensures adding a call inside an existing method is detected.
It is a review guard, not proof of semantic coverage
for arbitrary future branches inside an existing producer. A fixture does not
prove every live upstream translation or every account/build combination.

Visible smoke: hover a populated 4p set, a 2+2 build, weapon and character;
inspect Fact DPS enemy icons and GCSIM details; repeat in expanded/collapsed
History and PvP; scroll with a popup open; import/update catalog and repeat the
same unchanged set; switch content/UI language and verify fresh text.
