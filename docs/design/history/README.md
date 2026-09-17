# History visual design workspace

Updated 2026-09-17. The user approved Concept A as the basis for the first
implementation and asked to see it in the app before further refinement.
The first implementation was subsequently rejected for unreadable small text,
empty space, weak styling and appending a separate expanded report. The second
Qt pass transforms the existing card in place, but the user still finds its
composition too empty and hard to read. After the one-team study, the user
authorized trying its composition in AppShell while restoring soft gradients,
tabular separators and maximizing images by trimming only transparent margins.
The user then rejected v3's collapsed scale: heads should grow relative to
dense Akasha-like rows, not inflate the whole report. After v5's equipment,
tooltip and layout corrections, the user explicitly removed compact DPS and
requested stronger time/bonus hierarchy plus alternating record brightness.
The user now likes the compact composition and approved v7's front-portrait
team identity. V7 removes expanded team-header bars, groups art/bonuses/time
on the left and normalizes side-icon faces like the Artifact Browser. The
later splash-art investigation was explicitly cancelled; side icons are the
chosen character view and front portraits the default team art. Final v7
corrections and custom-art interaction still have the scoped checks below.
Concept approval must never be recorded as acceptance of the finished UI.

Product/architecture and implementation status are owned by
[History Browser](../../handoff/HISTORY_BROWSER.md); open work is in
[TODO](../../../TODO.md). This folder owns the visual reference images and
their interpretation. Read the images themselves before proposing UI changes.

## Reference library

All images below are unchanged copies, including the original full-resolution
PNG. Source names identify the attachments; runtime must use project/bundle
assets, not these reference screenshots.

| Image | Source | What it illustrates |
| --- | --- | --- |
| [Compact crop](references/akasha-compact-crop.png) | `codex-clipboard-618751cc-4cc5-4cbd-994a-7d00db0c925a.png` | First reminder: small character side icons and a low row with separate weapon/set/stat columns |
| [Compact table](references/akasha-compact-table.png) | `codex-clipboard-60392b87-e4f7-4daa-bff7-ad2d7703d952.png` | Full Akasha table, density, aligned data, side-icon silhouettes rather than large square portraits |
| [Expanded character](references/akasha-expanded-character.png) | `codex-clipboard-2d16911a-4efe-4dd0-b6c9-dd20e2bec266.png` | Expansion from summary to readable details; not a request to copy all artifact cards or large character art |
| [Character PNG export](references/akasha-export-character.png) | `ref.png` | Legibility and a self-contained composition that fits on screen; target is a two-team run report |
| [Character hover tooltip](references/akasha-character-tooltip.png) | `codex-clipboard-7fafd4ff-f8b4-4236-9f5d-7cfb26eb3ac4.png` | Character/weapon headers, aligned stat rows, active sets, optional subdued image behind the data |
| [Concept A](concepts/history-collage-a.png) | Built-in imagegen, 2026-09-16 | User-approved basis for the first compact/expanded implementation; illustrative data and assets |
| [User feedback on v2](references/user-v2-feedback.png) | `codex-clipboard-fc845e34-3f82-4c5c-8919-615a7d1141b5.png` | Criticized composition, wasted space and legibility; not an approved reference to imitate |
| [Akasha row scale](references/akasha-row-scale.png) | `codex-clipboard-9e82f647-3dde-4305-b06d-891dff56b7fb.png` | Latest explicit compact-scale reference: roughly 40px rows, large heads relative to row height |
| [Rejected v3 compact scale](references/user-v3-scale-feedback.png) | `codex-clipboard-a2cdad8a-1e69-4db6-8d25-e2d64ef4aa5d.png` | The 510px collapsed run filled the panel; enlarging the whole composition misread the request |
| [V4 equipment/tooltip feedback](references/user-v4-equipment-tooltip-feedback.png) | `codex-clipboard-fe440354-d600-46f7-9723-58e388d75269.png` | Remove compact duplicate metadata, enlarge equipment/enemies, fix scrolled popups |
| [V5 expanded hierarchy feedback](references/user-v5-expanded-hierarchy-feedback.png) | `codex-clipboard-3b4b284d-c103-402b-aac9-02671b4c9442.png` | Equipment should be one name line shorter than the head; stronger grouping and reading order |
| [Constellation overlay rejected](references/user-v5-constellation-feedback.png) | `codex-clipboard-d13d44c8-4197-4a7f-be37-a551f09b5376.png` | Put C beside the name; do not cover the face |
| [Compact spacing feedback](references/user-v5-compact-spacing-feedback.png) | `codex-clipboard-0130c320-d755-462a-baa1-b379a6af1503.png` | Intermediate compact layout still wastes horizontal space |
| [Right-hand results annotation](references/user-v5-right-results-annotation.png) | `codex-clipboard-dd9011b0-688a-4572-935f-5032978caf6a.png` | Explicit four-character-groups then results composition; remove the lower total squeeze |
| [Akasha alternating brightness](references/akasha-alternating-row-brightness.png) | `codex-clipboard-73697c8f-a80d-4271-b565-ca98d77245b8.png` | Alternating light/dark rows distinguish records; apply per entire run here |
| [Timer/bonus priorities](references/user-v5-timer-priority-feedback.png) | `codex-clipboard-bb506c79-5771-463d-be21-4c9dc39ec24f.png` | Remove compact DPS, enlarge bonuses, prioritize overall and team times, arrange room times in one line |
| [Expanded before sidebar](references/user-expanded-before-sidebar.png) | `5df6f37f-1111-4e3b-a2ad-a5297bbb6f78` | Wide team headers and wasted column space |
| [Left identity annotation](references/user-expanded-sidebar-annotation.png) | `13193f47-7699-49de-a7dd-b027f354d8e1` | Art/bonuses above team time, aligned beside rooms |
| [Unequal bonus scale](references/user-bonus-scale-feedback.png) | `f8b89f62-5115-46c9-ae1a-248482b4b7c5` | Size visible content rather than transparent/glow bounds |
| [Working Artifact Browser heads](references/artifact-browser-side-head-reference.png) | `cafaab57-f3b8-4c49-8156-2e48b239aa0a` | Calibrated side canvas, stable face scale and hat overhang |
| [Unequal heads A](references/user-unequal-heads-a.png) / [B](references/user-unequal-heads-b.png) | `c8595763-717a-457d-84f8-13438502a3a9` / `6395ff5f-2498-41b5-a3c1-736f17e75048` | Per-character alpha fitting was rejected |
| [Approved portrait direction](references/user-approved-team-portrait.png) | `b55dbb87-9ddc-423e-99e8-c53010b9bf4c` | Keep front portrait as team image; no splash downloads |
| [Header balance feedback](references/user-expanded-header-feedback.png) | `65d7310f-32ca-4c56-adbe-89822bc1aaec` | Move total to the left without a label, center title/month-range to replace the empty middle |

The exact generation prompt is retained in
[Concept A prompt](concepts/history-collage-a-prompt.txt). Its sample teams,
numbers, dates, badges and some icon depictions are illustrative. The generated
image is not a pixel-accurate test with actual local assets and proves neither
data correctness nor UI acceptance. It has not been regenerated for this archive.

Selected original user wording is preserved in
[source notes](SOURCE_NOTES.md), including the later icon-comparison request.
The earlier broad text-only reconstruction was not accepted as a sufficient
visual specification; do not use it to overrule these concrete references.

## User requirements retained from this discussion

- Turn the collected Run right-panel information into a static History summary.
  Selecting a saved run already restores its isolated read-only snapshot on the
  right; preserve that behavior and its separation from the live run.
- Provide collapsed and expanded views. Akasha summarizes one character; this
  report summarizes four characters per team, two teams for Abyss, and the run.
  Expansion transforms that card: keep each character header once and reveal
  stats beneath it, enriching the same room results with enemies. Do not append
  a duplicate export card below a retained compact summary.
- Keep characters, weapons, sets/builds, main-stat shorthand such as
  `ATK% / Pyro`, resonances and bonuses, total completion seconds and seconds
  per chamber. Detailed timer controls/precision are not part of these cards.
  Preserve factual and simulated DPS as distinct result types in expanded,
  exported and right-panel views. The latest explicit decision removes both
  from compact cards, superseding the earlier retain-all-compact-data rule.
- Four characters fit next to each other compactly. The final choice is side
  icons for character slots and front portraits for team identity. The earlier
  comparison setting has been removed; no splash download is wanted.
- Side heads use the Artifact Browser's calibrated full canvas and common face
  scale, with hat overhang. This supersedes per-character alpha trimming, which
  made faces with large hats smaller. Front portraits retain the cover crop;
  bonus variants fit visible content with alpha >64 bounds. Source assets are
  never changed, and image preparation is outside paint/hover.
- Retain soft gradients and restore clear table grouping. Separators should
  look integrated into the surface, not like heavy lines drawn over the data.
- Compact height is constrained by the Akasha row-scale reference. About four
  rows for the whole two-team run are acceptable. Maximize image/content use
  inside that budget; do not turn a collapsed record into a screen-sized report.
  Latest wide-panel composition: four dense character groups on the left,
  results on the right. Place C beside the name and overall total in a shared
  prominent block for the run; no duplicate Abyss/floor/date header in compact.
  Alternate whole-run brightness. Order team name -> large bonuses -> team time;
  place room times on one line. Total time leads, bonuses/team time follow,
  chamber times have the third level of emphasis.
- The expanded/export card should include compact overall character stats and
  active artifact sets, but no individual artifact pieces or artifact substats.
- Include the actual Abyss enemies/bosses for each half, with an unambiguous
  association to its team and chamber. Keep the whole export readable on screen.
- Hovering a character in the compact view should show a rich build tooltip
  inspired by the supplied Akasha example. Its visible reference fields are
  character/constellation/level, weapon/refinement/level, overall stat rows and
  active set counts. The current implementation uses these fields in a custom
  popup, clamped to the screen, with an inexpensive element-tinted gradient.
- A special new illustration is unnecessary. The user describes Akasha's
  background as a Genshin profile namecard and permits a cheap existing asset
  or simple element-based graphics. No new character-art parsing/download
  dependency is requested. No namecard asset is required by this iteration.

## V7: current expanded identity and normalized heads

2026-09-17. The overall timer is large at top left without `Total`; the title
and 14px month range are centered on the full card (`Abyss · 12`,
`9.2026–10.2026`). The save timestamp is omitted from this header. Missing or
invalid period ends are not fabricated: the older fixture displays `8.2026`.
Each team replaces its
full-width header with a left picture, separate large bonuses and a timer
aligned beside room results. The default picture is the first occupied slot's
front portrait with element/background fades, independent of character icons.
The optional uploaded image belongs only to that record/team. Hover offers
upload/reset; the lower `Team artwork` menu provides keyboard access. Export
includes the custom image without interactive controls.

Side-icon preparation now follows ArtifactCardDelegate: original calibrated
canvas, `DEFAULT_OWNER_BADGE_SIZE_RATIO`, common bottom anchor and top overhang.
An 80px slot uses the same 0.90 face proportion as a 42px compact slot; hats do
not determine scaling. Pyro's faint outer glow previously enlarged its alpha
bounds to 124px versus 96px at alpha >64; excluding this halo from sizing makes
its visible symbol comparable to Hexerei. The shared cached loader includes
that opt-in threshold in its key; other consumers retain threshold zero.

| Evidence | Scope |
| --- | --- |
| [Expanded card](implementation-v7/card-expanded.png) | Final production painter, 1220x666; previous 770px |
| [Compact card](implementation-v7/card-compact.png) | Same 1220x120 density, normalized heads |
| [864px expanded](implementation-v7/card-expanded-864.png) | 864x706, four character columns |
| [720px expanded](implementation-v7/card-expanded-720.png) | 720x1186, two columns below 800; extra height preserves readable data |
| [PNG](implementation-v7/export.png) | Final production export painter, 1600x888; not a native-dialog check |
| [Native compact check](implementation-v7/app-compact-partial.png) | Actual AppShell compact state before the final bonus threshold change; partial UI check only |

All 19 focused automated checks passed (ten card, four AppShell, five HiDPI).
The subsequent header-only adjustment was checked by renders and assertions
for month range, missing end and year crossover; the suite was not rerun for
that text/layout-only change.
They cover the saved card, immutable bundle preservation, custom
image upload through the card click, cancellation, source-file removal,
recreated row persistence, per-run/team isolation, reset, PNG, tooltip bounds
and AppShell live/frozen isolation. The temporary renderer exercised 720/864/
1220 in both states; the removed Portrait character variant remains only a
diagnostic painter argument, not an app setting.

Native check: actual project `.venv` / `ui.app_shell_smoke`, 1920x1080 secondary
display, real History click and two compact runs. Further input was stopped
when the visible workspace changed between observations, and the user explicitly
asked to postpone checks while using the app. No completed native upload/reset,
export-dialog, restart/reopen, or final head/bonus-hover path is claimed.
Resume checklist: History -> expand 444s record -> hover image/upload -> select
other record (unchanged) -> reopen first (retained) -> export PNG (same art, no
controls) -> reset -> collapse -> return to live Run (unchanged).

The user approved the compact density and front-portrait identity direction,
not the unperformed interaction checks. Splash research is cancelled, with its
bounded findings retained only in [source notes](SOURCE_NOTES.md).

## V6: historical compact hierarchy (density retained)

Adjacent saved runs now alternate dark/light surfaces in their current list
order. Both teams share one tone and one dominant total-time block on the
right, making the record boundary clearer than its internal team divider.
Selection, expansion and export do not change the alternating order.

Compact DPS is intentionally removed for both Abyss and DPS Dummy. The wide
Abyss layout keeps the same dense character groups, followed by team name,
30px bonuses and 21px team time, with three 15px chamber times on one line.
The shared total column uses 30px text (24px for longer values). Bonus images
use separately prepared alpha-trimmed variants inside small framed cells;
overflow still uses +N with its saved tooltip. Expanded/export bonus geometry,
factual/simulated DPS and all frozen snapshot fields remain unchanged.

At 1220px the eight-character card is 120px tall, down from v5's 136px. The
wide arrangement still starts at 1160 design pixels (1320 for two-set builds).
The narrower fallback is 180px at 864px and 220px at 720px: it keeps larger
bonuses and the total column, with team/chamber results below the characters.
That fallback spends more height than v5; it does not shrink the new emphasis
to force the wide arrangement onto a narrow panel.

| Output | Scope |
| --- | --- |
| [Compact / Profile](implementation-v6/card-1220-profile-compact.png) | Production Qt render, 1220x120 |
| [Compact / Portrait](implementation-v6/card-1220-portrait-compact.png) | Same geometry with HoYoLAB assets |
| [864px fallback](implementation-v6/card-864-profile-compact.png) | 864x180, results below characters |
| [720px fallback](implementation-v6/card-720-profile-compact.png) | 720x220 with text wrap |
| [Two adjacent runs](implementation-v6/app-compact.png) | Actual Windows AppShell, distinct run tones and prominent totals |
| [Large resonance hover](implementation-v6/app-bonus-tooltip.png) | Actual pointer hover retains the frozen bonus tooltip |
| [Expanded run](implementation-v6/app-expanded.png) | Native click shows retained DPS and the frozen right Run |

Validation on 2026-09-17: all 14 existing focused tests passed (ten History card,
four AppShell). Twelve bounded renders used the saved 444-second run at
720/864/1220px, both asset choices and both states, with eight slot hit regions.
The renderer's first captures reflected the primary screen's DPR 1.5; the
listed renders use an explicit process-local scale for DPR 1, without changing
application settings. The unchanged expanded layout is 770px at 1220px;
its export remains 1600x1027 on this fixture.

Native input used a fresh project `.venv` launch of `python -m ui.app_shell_smoke`
from the repository root, matching the observed PyCharm entrypoint. On the
1920x1080 secondary monitor at DPR 1, History -> inspect two runs -> hover a
resonance -> expand the second run confirmed striping, bonus hit regions,
retained expanded DPS and right-panel snapshot selection. That process exited
normally before an optional collapse/live-return recheck; those were covered
by the automated suite and the earlier v5 native checks, not repeated here.
No new native export-dialog/Portrait-setting check, real DPS Dummy save or
exhaustive locale/monitor matrix is claimed. V5's export and tooltip evidence
below remains scoped to that pass.

## V5: historical equipment, hierarchy and scroll-tooltip correction

The compact wide layout now follows the user's annotated composition. Four
character groups occupy the left portion; the right 360px contains team/time/
bonuses plus three aligned chamber rows with seconds, Fact and Sim. Overall
total sits at the upper right. The 1220px fixture is 136px tall, versus v4's
174px. This arrangement starts at 1160 design pixels (1320 for two-set builds).
At narrower widths the results remain below the characters: 152px at 864px,
216px at 720px with a text wrap. No data category was moved into hover only.
Long names can elide; the full identity remains available in the rich tooltip.

Heads, weapons and sets sit next to each other. Compact heads reach 42px,
equipment is 4-6px smaller, and C follows the name. The expanded head spans the
name/equipment block; the equipment is one 24px name line shorter. Name/C sit
above that equipment, build/level below. Both character variants receive a
subtle 2px edge zoom inside rounded corners in expanded/export mode only.
Prepared images and immutable assets remain unchanged.

The report hierarchy is overall total, colored team headers/totals, separate
character cards, then chamber cards with time accents. Explicit boundaries and
numeric separators supplement the retained gradients. Enemy tiles are 56-72px,
placed beside the room metrics when space allows and wrapping when necessary.
PNG uses the same expanded composition, 1600x1027 on this fixture.

| Output | Scope |
| --- | --- |
| [Wide compact / Profile](implementation-v5/card-1220-profile-compact.png) | Actual Qt render, 1220x136; right-hand results |
| [Wide compact / Portrait](implementation-v5/card-1220-portrait-compact.png) | Same data and dimensions, frozen HoYoLAB assets |
| [864px compact](implementation-v5/card-864-profile-compact.png) | 864x152 fallback with results below characters |
| [720px compact](implementation-v5/card-720-profile-compact.png) | 720x216, wrapped text at this narrow width |
| [AppShell compact](implementation-v5/app-compact.png) | Native collapse, 444-second right snapshot retained |
| [AppShell expanded bottom](implementation-v5/app-expanded-bottom.png) | Visible section hierarchy, large equipment/enemies and Save PNG |
| [Enemy tooltip at bottom](implementation-v5/app-enemy-tooltip-bottom.png) | Native hover after scrolling, entire popup inside screen |
| [Character tooltip at bottom](implementation-v5/app-character-tooltip-bottom.png) | Native hover opens the larger popup above the pointer |
| [Profile PNG](implementation-v5/export-profile.png) | Actual native Save PNG dialog output, 1600x1027 |
| [Portrait PNG](implementation-v5/export-portrait.png) | Direct production painter output, 1600x1027; not a native-dialog rerun |
| [Live Run return](implementation-v5/app-live-return.png) | Initial empty teams and zero total restored |

Validation on 2026-09-17: 14 focused tests passed (ten card, four AppShell),
including scrolled hover containment and both compact height budgets. The new
wide-height assertion first read a hidden widget before its deferred resize;
the check now settles its geometry, and the complete selection passed. Twelve
renders cover 720/864/1220px, Profile/Portrait and both states with eight character
hit regions. The saved fixture is the 2026-09-16 Abyss run, 444 seconds.

Actual Windows input used a fresh project `.venv` launch of
`python -m ui.app_shell_smoke` from the project root, matching the entrypoint
observed in the user's PyCharm launcher. Final checks ran at 1920x1080 / DPR 1.
History -> run -> scroll to bottom -> enemy/character hover -> Save PNG ->
collapse -> Characters verified the displayed layout, screen containment,
export, retained frozen selection and unchanged empty live Run. No private
snapshot was edited. Profile remained selected. Other locales, exhaustive
teams/monitors, a real DPS Dummy save and native Portrait switching/export
were not repeated in this pass. Implementation is not final visual acceptance.

The tooltip defect was positional: enemy text anchored to the full scrollable
card, whose top/bottom could be offscreen. Both popup types now use the visible
hover point, convert once to global logical coordinates, select that screen
and apply its clamped geometry. This opt-in shared helper leaves unrelated
tooltip callers' existing placement unchanged.

## V4 compact scale: historical density correction

The 864px-wide collapsed run is now 174px tall, down from 510px. Its 24px shared
heading is followed by two pairs of strips: four characters in 44px, then team
total/bonuses and all three chamber results in 28px. A 42px alpha-trimmed head
spans both text lines beside it; names use 14px, builds 12px, results 13-14px,
secondary labels 11-12px and small equipment badges 10px. Soft element/team
gradients and faded column rules remain. This is a distinct dense composition,
not a miniature of the expanded report.

At 720px the room results use two lines (198px total); heads use 36px. A long
build shorthand may elide at that narrower width and is fully readable after
expansion. Two-set builds can reserve one extra line; below 680px the existing
two-column fallback remains. No compact data category was moved exclusively
to expansion. Expanded details, rich hover, PNG and right-panel behavior retain
their previous contracts; clicking transforms this card rather than appending
an export image. The expanded layout is still substantially taller.

| Output | Scope |
| --- | --- |
| [Compact / Profile](implementation-v4/card-864-profile-compact.png) | Actual Qt render, 864 x 174 |
| [Compact / Portrait](implementation-v4/card-864-portrait-compact.png) | Same geometry with frozen HoYoLAB portraits |
| [720px compact](implementation-v4/card-720-profile-compact.png) | Narrow fallback, 720 x 198; long build shorthand can elide |
| [AppShell compact](implementation-v4/app-compact.png) | Native clicks expanded and collapsed the row; right snapshot remained selected |
| [AppShell expanded](implementation-v4/app-expanded.png) | Same card transforms to details |
| [Compact hover](implementation-v4/app-tooltip.png) | Native pointer hover shows frozen character details |
| [Portrait comparison](implementation-v4/app-portrait.png) | Account setting updates the compact row without changing height |
| [Live return](implementation-v4/app-live-return.png) | Characters workspace shows the empty live team and zero total |

Validation on 2026-09-16: 13 focused tests passed (nine card, four AppShell).
The new height regression guard initially assumed DPR=1 when run together with
AppShell tests; it now checks rendered dimensions under startup scaling and
the complete 13-test selection passed. Twelve supplemental renders cover
720/864/1220px, two icon variants and two states with eight character hit regions.
Normal-width builds fit; the first narrow render exposed a long build label,
and tighter equipment spacing reduced but did not eliminate that elision.
No claim of universal no-elision is made. Expanded/export size remains unchanged.

Native Windows clicks used a fresh project `.venv` launch of
`python -m ui.app_shell_smoke`, the same entrypoint observed in the user's
PyCharm process, at 1366px / DPR 0.711458. Checked expansion, collapse preserving
right selection, hover, Profile/Portrait switching and return to live Run.
Profile was restored after comparison. Native PNG dialogs were checked in v3,
not repeated for this compact-only change. Other locales/monitors, arbitrary
teams and a real DPS Dummy save were not visually checked.

## V3: historical expanded basis; oversized compact rejected

This historical pass integrated the study composition into the shared painter.
Its collapsed scale was rejected and superseded by v4; v5 later revised both
states. The following records the original v3 outcome.
Each team has a nearby total and bonus group, large character images, grouped
identity/equipment and a full-width three-room band. Expansion reveals aligned
stats and enemies inside that same card. Gradients, alternating stat rows and
faded separators distinguish data without strong boxes around every value.
Compact levels and factual/sim DPS remain; right-panel selection is unchanged.

Character pictures occupy 56-88 design pixels after exact alpha trimming.
Names are 15px, stat values 14px and room times 21px. The local readable-size
floor compensates sub-1 DPR; global AppShell scaling stays unchanged. Normal
widths keep four characters in one row; below 680 design pixels they reflow
to two columns. Two-set builds and excess enemies receive extra rows.
This deliberately spends more height on readable content: at the checked
1366px display, expanded History needs vertical scrolling. Export height is
data-driven; the checked eight-character PNG is 1600 x 1080, not a guarantee
that every report will fit every screen without scaling.

All outputs below are unchanged captures or exports from the then-current Qt code,
using the saved 2026-09-16 Abyss run (444 seconds), not generated mockups.

| Output | Evidence |
| --- | --- |
| [Compact in AppShell](implementation-v3/app-compact.png) | Four enlarged side icons per team, both teams visible |
| [Expanded top](implementation-v3/app-expanded-top.png) | Same first-team headers plus stats/enemies; frozen Run on the right |
| [Expanded bottom](implementation-v3/app-expanded-bottom.png) | Scrolled second team and Save PNG |
| [Character tooltip](implementation-v3/app-tooltip.png) | Native hover in the compact card |
| [Portrait setting](implementation-v3/app-portrait-setting.png) | Account > History > Character view, same expanded geometry |
| [Profile export](implementation-v3/export-profile.png) | 1600 x 1080, native Save PNG dialog |
| [Portrait export](implementation-v3/export-portrait.png) | Same saved data and dimensions, native Save PNG dialog |
| [Live Run return](implementation-v3/app-live-return.png) | Initial empty live team and zero total restored |
| [720px expanded card](implementation-v3/card-720-profile-expanded.png) | Supplemental direct-widget render, not an AppShell screenshot |
| [864px compact card](implementation-v3/card-864-profile-compact.png) | Supplemental direct-widget render |

Validation: 17 distinct focused tests passed (eight card, five HiDPI, four
AppShell). The new overflow test initially counted a bonus tooltip as an enemy;
the assertion was corrected, then all eight card tests passed. Twelve renders
cover 720/864/1220px, both asset variants and both states, with eight character
hit regions each. Native Windows input exercised the fresh `.venv` AppShell
launch via `python -m ui.app_shell_smoke` from the project root; the observed
user launcher was PyCharm running the same file. Actual checks covered History
selection/expansion, hover, scrolling, icon switching, both native exports
and return to the initial empty live Run. Profile was restored after comparison.
Other languages/monitors, arbitrary teams and a real DPS Dummy save were not
visually checked. Implementation checks do not imply user visual acceptance.

## One-team Qt study v3: historical composition proposal

This was the provisional component study preceding the v3 integration above.
It uses the first frozen team from the same saved Abyss run (213 seconds), real
bundle assets and Qt fonts/pixmaps. [Runnable study source](proposals/team-study-v3.py)
reuses the current card's asset/hover helpers without changing runtime imports.

- One neutral surface; no per-character frames, gradients or portrait watermarks.
- Name and C are adjacent; weapon/R and sets are grouped beside the portrait.
- The team total and bonuses sit beside its title. A full-width three-room band
  shows times and factual/sim DPS in both states. Levels also stay visible.
- Expansion retains the four headers and enriches the same block with aligned
  stats and enemies. It is not an export report appended below a compact card.
- Right-panel routing and moving DPS/levels into details are separate undecided
  proposals. The study's icon/width choices are local, not persisted settings.

| Native Qt output | Scope |
| --- | --- |
| [Compact / Profile](proposals/v3/team-864-profile-compact.png) | 864 x 191 rendered pixels |
| [Expanded / Profile](proposals/v3/team-864-profile-expanded.png) | 864 x 349; same four character groups |
| [Compact / Portrait](proposals/v3/team-864-portrait-compact.png) | Existing HoYoLAB asset comparison |
| [Expanded / Portrait](proposals/v3/team-864-portrait-expanded.png) | Same composition with front portraits |
| [Narrow expanded](proposals/v3/team-720-profile-expanded.png) | Readable-size check at 720px |
| [Visible Qt preview](proposals/v3/native-expanded.png) | After a native click expanded the actual study widget |
| [Native narrow/portrait switch](proposals/v3/native-narrow-portrait.png) | Width and icon changes through visible controls |

Validation on 2026-09-16: 12 renders (three widths, two icon choices, two states)
had four character regions and no elided text on this fixture. Native clicks in
`GTT History · Qt study v3` expanded/collapsed the card and switched width/icons.
At that study-only stage production code was unchanged; this statement does
not describe the later integration above.

The study display was reported as 1366px; startup scaled Qt to 0.711458. An
initial capture shrank text and was mistakenly enlarged back to nominal width.
That capture is superseded. The study now compensates sub-1 DPR locally for a
readable rendered-size floor, maps hit regions through the same transform, and
saves actual rendered pixels. Global AppShell scaling remains unchanged.
The narrow labels are 11-12px, builds/values 13-14px, names 15px and times 19-20px.
This design is not denser at the expense of smaller glyphs: its compact block
is taller than v2's wide strip, allocating that height to readable results.

To reproduce from the project root, set `PYTHONPATH` to that root and run the
project interpreter with `docs/design/history/proposals/team-study-v3.py`, the
chosen snapshot JSON path and `--show`; optional `--output` saves the render
matrix. No snapshot path or account data is embedded in the source. The study
is scoped to one Abyss team and imports current shared helpers; historical
captures, not rerunning it against changed helpers, preserve its original look.
Its initial validation did not cover arbitrary enemies, two sets or other locales.

## Historical v2 interpretation of Concept A

The following records v2 choices, including its superseded chamber placement
and portrait watermarks. Current geometry and styling are described above.

- Concept A stacks two full-width team sections. Each has four character
  columns, followed by a separate three-column chamber band. This preserves
  width for stats and keeps enemies beside their chamber time/result.
- Distinguish the four-character grid from the three-chamber grid with a clear
  divider so a character is not visually assigned to the room beneath it.
- Show resonance/bonus icons once per team, in a dedicated group. Keep the
  same character order in collapsed, expanded and exported presentations.
- Use one consistent stat order/grid for every character. Overall completion
  time leads the hierarchy; chamber times follow, then DPS and character stats.
- Draw directly in logical widget pixels, with readable text floors instead of
  shrinking a fixed-width report canvas into the left pane. Wide compact rows
  place chamber results beside the four characters; narrower rows put results
  below them. Expanded rows retain four character columns in both layouts.
- Use a dark blue gradient, teal/gold team headers, subtle element backgrounds,
  faint existing portraits behind expanded stats, colored build shorthand and
  aligned numeric columns. No new downloaded artwork or web renderer is used.
- Use the expanded composition as the PNG basis, removing interaction chrome.
  The card and PNG share one painter over the same frozen data; exporting
  does not capture the window or copy live right-panel widget geometry.
- Keep compact rows shallow without shrinking useful text. Suggested 1600 x 900
  was an initial suggestion, not a fixed requirement. Export is 1600px wide
  with data-driven height (918px for the checked eight-character run).
- Tooltip uses a static dark element-tinted gradient. Character and weapon
  images reuse prepared snapshot pixmaps; no image processing occurs on hover.
- Clicking a row transforms it in place and selects the same frozen run on the
  right, without an arrow. Clicking it again collapses the card while keeping
  the right-panel snapshot selected. Opening another row collapses the former.
- Changing character view updates compact, expanded, tooltip and exported
  images; it preserves selected/expanded state and persists across restarts.
- Team bonuses exclude wearer-only weapon/artifact passive entries, which
  remain in frozen slot details; repeated team sources are shown once.

## V2 application samples: further revision requested

These are unchanged outputs/captures from the second Qt pass in the visible
Windows AppShell on 2026-09-16, not generated mockups. Both exports came through
Save PNG's native file dialog for the same frozen Abyss run (444 seconds).
The maximized and smaller windows exercise both chamber placement layouts.

| Sample | Scope |
| --- | --- |
| [Profile PNG](implementation-v2/export-profile.png) | Existing side assets; 1600 x 918 |
| [Portrait PNG](implementation-v2/export-portrait.png) | Existing cropped HoYoLAB assets; same geometry |
| [Compact card](implementation-v2/app-compact.png) | Wide layout; collapsed card retains right-panel selection |
| [Expanded card](implementation-v2/app-expanded.png) | Same card transformed; both teams fit in the maximized window |
| [Narrow expanded card](implementation-v2/app-narrow-expanded.png) | Smaller split workspace, scrolled to both teams and Save PNG |
| [Character tooltip](implementation-v2/app-tooltip.png) | Native visible popup over the actual card; frozen Varesa build |
| [Portrait comparison setting](implementation-v2/app-portrait-setting.png) | Account > History > Character view updates the expanded card in place |

The user assessed v2 as closer but still too empty and hard to read. These
captures document the superseded v2 runtime, not accepted final appearance.
The immediate review is v7 above; technology choice remains open.

The rejected first pass remains unchanged for comparison: [profile export](implementation/export-profile.png),
[portrait export](implementation/export-portrait.png), [compact](implementation/app-compact.png),
[expanded](implementation/app-expanded.png), [tooltip](implementation/app-tooltip.png),
[setting](implementation/app-setting-options.png). These 1600 x 1024 exports
and appended-card screenshots are historical evidence, not implementation targets.

## Saved-build presentation repair

The saved-build adapter now uses live Run's main-property-id formatter, yielding
`ATK%/PYRO`, `ER/HP%`, etc. in the card and shared read-only right panel.
Only the two obsolete formula-not-included warning codes are suppressed in
slot decoration; other warnings and immutable provenance remain intact.
Real History selection was checked after restart. The separate top-level
unreadable-snapshot notice remains truthful: this workspace has one legacy v1
bundle unsupported by the v2 reader. It was neither hidden nor deleted.

## Keeping these references useful

Preserve originals and add named variants rather than overwrite them. For a
new image, record its source, the specific feature it demonstrates, and whether
it is inspiration, a proposal or user-approved design. Update decisions in
place; retain meaningful reversals such as the icon comparison above. Do not
replace the actual image links and concrete constraints with only "Akasha-like"
or "compact". Link an accepted design from the History contract when agreed.
