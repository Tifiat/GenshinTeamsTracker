# Rotation editor functional repairs — 9 October 2026

Current owner: [READABLE_ROTATION_EDITOR.md](../handoff/READABLE_ROTATION_EDITOR.md).
The human trial rejected the prototype's density/readability and found real
behavior failures. This stage repairs functionality before a broad visual
redesign; it does not claim final usability or all-character mechanics support.

## Repaired boundaries

| Finding | Result |
| --- | --- |
| All engine characters offered | Browser obtains only its selected mode/team's explicit roster. Account keys are read by stable ID from current stored mapping; virtual keys come from overrides. Missing/ambiguous keys fail closed. Names/code never supply membership. |
| UI-only selection restriction could be bypassed | `EditorSession` checks new structural foreign references before changing history and checks complete code before commit. Active character, action lines, setup actors, character fields and explicit `.keys.char.*` references are covered. Foreign imported text is retained for inspection/correction. |
| Invalid/unknown action metadata | Documented invalid and unconfirmed actions cannot be inserted through the bound session. Buttons show confirmed actions only; variant parameters also require metadata. Missing metadata is explained rather than represented by a nonworking choice. |
| Team changed while a draft was open | Controls update to current participants. Old Apply remains blocked across further edits until explicit re-open/review. Browser rechecks binding before writing; mode/team, stable membership and known C participate. External Code and engine guards remain. |
| Mixed command navigation | Separate Characters/Cycles/Conditions/Wait pages with Back. A character opens its actions in the properties panel, preserving the insertion destination. |
| Insertion/delete lost the selected context | Adding an action selects its actual action ID, even inside a grouped character window. Delete selects a surviving action/parent body; hidden body selections remain legitimate insertion targets. Undo/redo retain the possible context. |
| Variant edit looked unchanged or failed silently | Errors and success are shown beside properties. Repeated actions are supported, and the selected action ID survives lowering. Exact previous audited plans are replaced when changing a variant again. |
| Readable tab disabled | Enabled read-only plain text built from current main Code, with adjacent actions compacted. Conditions/cycles/else remain visible. Enter updates immediately; edits while visible are collected over 200 ms. Applying the separate draft updates the existing Code signal path. |

The pure roster/session contract does not prove general dynamic execution.
Computed character selection in arbitrary custom calls cannot be statically
established by the explicit-reference check. Readiness, cooldowns, resource
availability and mode survival until queued execution still need their own
mechanical adapter or execution evidence. Do not call an absence of diagnostic
a universal legal-rotation proof.

`team.load_selected_team` receives the owning controller's explicit DB path.
It opens mode=ro with a 250 ms lock wait and queries at most four selected
character IDs. It never initializes storage, repairs keys, scans inventory or
migrates schema. Fresh stored status wins a stale snapshot. No DB means unresolved
participants, without creation. Prepared account/virtual names are injected;
the four explicit app translations remain, without name-based key matching.
No account fields are written by the adapter.

## Chasca and repeated variants

Changing `chasca aim:4` to the audited six-bullet variant now creates four
explicit iterations. Each iteration contains `if !.chasca.nightsoul.state`
preparation followed by `if .chasca.nightsoul.state` shooting. Selection remains
on the resulting action. A zero repetition wraps the plan in a false condition,
so preparation also does not run. Bennett's parameter-only variant retains its
literal action repetition. Repeated preparation exceeding exact cycle bounds
is rejected explicitly.

When an existing audited preparation/guard sequence matches exactly by tree
shape, editing its variant replaces that range. For example 4→6 Chasca bullets
removes the old C0–C5 guard rather than keeping it around the new six-bullet
action; preparation is not duplicated and neighboring dash/jump survive.
Unrelated custom guards are not recognized as replaceable templates. Imported
code still receives no automatic preparation just from reading or selecting.
Extra unrelated parameters remain an explicit detailed-edit limitation.

The 1–5 bullet template remains conservatively limited to C0–C5; C6 supports
the six-bullet template. This is not a claim that every partial shot at C6 is
impossible. Guard checks before queuing do not guarantee the state at dispatch.

## Systematic personal-mechanics inventory

Read-only inventory used the selected public source installation
`data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932` and its three generated
Actions/Params/Fields tables. References below are relative to
`internal/characters/`; no simulation was run.

| Character/group | Verified source behavior | Automatic data / remaining adapter |
| --- | --- | --- |
| Chasca | `aimed.go:59`, `skill.go`: aim selects Nightsoul shot in blessing, ordinary bow shot outside. C6 instant charging restricts bullet count. | `aim.bullets`, `aim.hold`, invalid charge/high plunge. Audited variant implemented. |
| Bennett / Furina | Hold levels; Ousia/Pneuma skill and delayed charge alignment switch. | Existing audited adapters; no new general mode assumption. |
| Hu Tao | `charge.go:38`, `skill.go:33`: charge changes in Paramita. | Preceding-attack note; no corresponding personal charge parameter/field in selected tables. |
| Tartaglia | `skill.go:78`, `aimed.go:34`, `charge.go:32`: skill toggles stance; aim errors in melee, charge errors outside melee. | Static plunge invalid flags and prose stance notes; needs an explicit stance adapter. |
| Raiden | `burst.go:31`, `attack.go:47`, `charge.go:26`: burst's timed sword state changes normal/charge. | No corresponding field/parameter in selected tables; requires audited status handling. |
| Mualani | `attack.go:78,123`, `skill.go:204`: Nightsoul attack becomes bite and consumes momentum. | `.mualani.momentum`, static action prohibitions; transition/resource adapter needed. |
| Kinich | `skill.go:51,95`, `attack.go:74`: Nightsoul attack; max-point skill becomes cannon. | `skill.hold`, `attack.direction`, `.kinich.blind_spot`; state-specific prohibitions in notes. |
| Alhaitham | `skill.go:61,96`, `plunge.go:67`: held skill and the exact prior-action requirement for low plunge. | `skill.hold`, mirror/C2 fields; preceding-action adapter needed. |
| Clorinde | `skill.go:48`, `attack.go:71`: first skill starts Night Vigil; subsequent skill dashes; attack changes. | Internal timed state, no matching table field/parameter in this source. |
| Wriothesley | `wriothesley.go:58`: rebuke readiness changes charge/stamina behavior. | `.wriothesley.gracious-rebuke`; resource/state adapter needed. |
| Arlecchino | `charge.go:27`, `skill.go:97`: early-cancel charge schedules directive absorption; follow-up dash/jump. | `charge.early_cancel`; cancellation/previous-action adapter needed. |
| Itto | `charge.go:85,187`: slash depends on previous slash and Superstrength stacks. | No corresponding field/parameter in selected tables; internal state adapter needed. |

Generated metadata can automatically describe static action prohibitions,
parameter keys and exposed fields for a new engine. It cannot prove a safe
preparation sequence from prose. Source scans of parameter reads/status branches
identify candidates, not executable adapters. Coverage work should group by
stance transitions, previous-action requirements, resources and cancellation;
each adapter needs boundary examples on both sides of its prerequisite and
idempotent re-edit/import tests. Unsupported personal alternatives are not
advertised as working templates. The implemented registry is still deliberately
limited to Bennett/Chasca/Furina; this table does not implement other characters.

## Verification and user path

- Combined focused suite: **179 tests PASS** (backend, roster, Qt Browser/editor,
  adjacent Browser regressions and AppShell virtual-slot seams). After the
  bounded review's two follow-ups, **44 overlapping focused tests PASS**.
- Go parser: prior 25 public/19 block pairs, 90 schedule truths, 23 condition/
  variant pairs and 34 truths still pass. Structural expected-code pairs increased
  from 7 to **9**, adding repeat-preserving Chasca preparation and idempotent
  4→6 replacement. These are parser/config comparisons, not battle execution.
- Independent review's main boundaries held; it found Apply re-enabling after
  a team change and a variant offered without its parameter row. Persistent
  apply blocking and metadata filtering fix both, with focused regressions.
- Native public Browser was opened via the project Python launcher and observed
  with Computer Use: Readable contained ten compact lines, including the cycle,
  odd schedule, character actions and final wait. No successful automated native
  edit/apply/delete sequence or actual account-backed AppShell restart is claimed.
  The human's app/preview windows were not terminated or restarted.
- SQLite preservation/absence checks use disposable synthetic databases only.
  A test initially retained its own fixture connection; this was corrected with
  explicit closing. Its exact failed temporary fixture was verified and removed;
  no live account data or retained generated reports were involved.

Reproduce the no-account real Browser surface:

```powershell
.venv/Scripts/python.exe -B -X utf8 tools/preview_rotation_editor_ui.py --engine-root data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932 --browser
```

On the user's restarted AppShell: choose a team → GCSIM Browser → Readable.
Open draft editor → Characters → Chasca → aim in Properties → variant/change.
Selection and the current command page should remain; six-bullet preparation
must appear in generated Code, including an existing repeat count. Delete an
action inside an if body, then add another without reselecting the body. Other
team participants/foreign Code must not pass the selected-roster gate.
Broad density/color/block presentation remains a separate design stage.

## Rotation import status and Git boundary

Read-only status from chat `01a11edd-f8f4-7962-997a-49e5ba6038b9`: mechanism audit
completed, no implementation/files changed. Import button/network adapter is
still absent. Audit covers roster-first ranking, rotation/environment extraction,
dependencies, translation providers and draft-race guards. No new implementation
message was sent to that chat during these repairs.

Own local package on master over `9b06e71a37c390ac982811e9ee7d5aced682337c`.
Direct functional-fix instructions and CODEX authorize its verified local commit.
Only owned editor/Browser/AppShell seam/locales/tests/preview/check helper and
own handoff/receipt/catalog are included; no engine change, optimizer behavior,
account write, persistent cache, branch transfer or push. Shared hub/status/Git
journal remain the orchestrator's property; they were not edited. This fixed
versioned receipt stores no screenshots/private data or second task queue.
