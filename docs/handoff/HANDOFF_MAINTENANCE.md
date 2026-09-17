# Handoff maintenance protocol

Owner of the documentation lifecycle, effective 2026-09-16. This is mandatory
agent closeout, not a scheduled background job. It applies to CODEX, TODO, the
handoff index, subsystem documents and their live machine projections.

## Trigger and completion rule

Run this protocol whenever authorized work changes implementation, a saved
decision, a next step, reusable evidence, or documentation. Failed, diagnostic,
partial and blocked results count: they often change what can safely happen
next. Discussion-only turns without saved changes do not trigger edits.

Maintaining the affected handoffs is part of the authorized task. Complete
ordinary reconciliation and compaction before the final reply; do not merely
recommend another cleanup task or wait for a successful large stage. Do not
implement unrelated TODO work, rerun product validation, or delete runtime/
private data as documentation housekeeping.

## One owner for each kind of fact

| Fact | Owner | Other documents |
| --- | --- | --- |
| Stable execution rule | CODEX | Link, do not copy the full rule |
| Open work and user-decided order | TODO | Link to the task/contract; no competing queues |
| Stable subsystem behavior | Subsystem contract listed in README | Concise pointers |
| Mutable implementation, acceptance and immediate resume | One current checkpoint per scope | Link instead of reproducing status/metrics |
| A particular run, failure or measurement | Dated evidence/receipt | Cite with scope; never promote to universal truth |
| Required machine-readable current fields | Explicit live manifest section | Synchronize with its declared checkpoint |

Use the existing owner; do not create a new checkpoint for every reply.
GCSIM current acceptance is owned by GCSIM_GOB11_GP3_CHECKPOINT.md. The trace
handoff owns architecture and gate order; the Go design owns implementation
details; the engine plan owns update/rollback contracts. The cleanup manifest's
current_state/current_next_block are live projections; its other stage records
are historical.

For a mutable checkpoint, put a compact current section near the top between
the following literal markers (replace the example scope with a stable name):

~~~markdown
<!-- handoff-current: example-scope -->
Reviewed date; implementation state; evidence scope and limits; next action;
links to evidence and the open task. Keep this summary within 400 words.
<!-- /handoff-current -->
~~~

Exactly one document may own a given scope marker. When moving ownership,
remove the former live block and update incoming pointers in the same task.
Keep detailed evidence below the summary or in an existing dated receipt.
The optimizer manifest's engine/rollback/patch/hash, acceptance status and next
block projections are compared against explicit fields in its owner's current
block by the checker. Its live fields cannot be silently removed to pass.

## Closeout procedure

1. **Before editing:** read the current owner, relevant TODO items and live
   manifest fields. Identify the facts that this task can change, their
   evidence, and any duplicated current claims. Check the worktree for
   concurrent additions; work from present contents, not a remembered snapshot.
2. **Record the actual outcome in the owner:** replace stale current wording
   in place. State what exists, what automated checks verified, what was
   exercised through the real UI, and what remains unverified. Include a date
   and bounded evidence reference; do not make a review date look like a rerun.
3. **Reconcile the dependency closure:** search CODEX, TODO and docs/handoff
   (including JSON) for the affected feature/task ids, old state, owner filename
   and superseded next action. Read matching sections, not all generated data.
   Update every live dependent claim or replace it with an owner pointer.
   Unchanged history retains its original outcome. A new standalone diagnostic
   is not integrated until its result changes the current owner and next step.
4. **Clean while updating:** remove completed TODO items and obsolete pending
   decisions. Preserve unfinished subitems as explicit remaining work. Fold
   durable new constraints into their existing section. Delete repeated prose,
   superseded instructions and disposable development chronology; retain unique
   contracts, reproducible evidence, rollback identities and unresolved risks.
5. **Index and project:** register each new direct handoff Markdown document
   once in README with its role (contract/current/history/research). Update
   incoming links and explicit machine projections when ownership or state
   changes. Give dated evidence a link back to its current owner. Do not create
   a new archive merely to dump an unedited root document out of the budget.
6. **Verify semantics and structure:** use the questions below, then run
   `.venv\Scripts\python.exe tools\check_handoffs.py`.
   Fix every reported issue and repeat the lightweight check. The tool only
   reads small documentation files; it does not start the app, inspect accounts,
   import project modules, run simulations or regenerate evidence.
7. **Check the final diff:** reread shared files before applying edits and after
   verification. Use contextual patches; preserve other tasks' additions.
   If another task changes an affected fact during closeout, reconcile against
   the new content and recheck. Report the achieved outcome and real validation
   limits; do not add a permanent per-task checklist or status-log entry.

If evidence conflicts and the cause cannot be determined within the task,
preserve both scoped observations and state the exact unresolved conflict in
the current owner. Do not choose the newest date as proof, invent acceptance,
delete contrary evidence or silently mark a failed gate passed.

## Semantic questions required before completion

- Does any active instruction still ask to implement something already present?
  Conversely, does an implemented module get mislabeled as UI-accepted?
- Did a failed or partial check change the next action? Is a later diagnostic
  search incorrectly described as accepted despite an earlier response failure?
- Does a bounded pass name its fixture/points? Keep controlled response,
  arbitrary candidate coverage, installed parity, backend search and actual UI
  acceptance separate. Zero wholly frozen hits is not complete ancestry.
- Are engine/patch identities and performance claims either current in the
  owner or explicitly dated history? An old 57-second replay must not become
  a promise for new teams or hardware.
- Is an already given user decision reflected without asking again? Does
  an independent task added by another task survive? In particular preserve
  the user-decided Selected 2+2 ordering when maintaining optimizer notes.
- Are old next-step lists clearly historical and subordinate to the current
  owner? Can a future agent find one unambiguous next action?
- Is unique useful knowledge retained, with a resolvable owner/evidence pointer,
  rather than buried in a root log or duplicated among contracts?
- Does new generated output have a finite lifecycle in DATA_RUNTIME_BOUNDARIES,
  an actually connected cleaner and preservation/failure tests? Were temporary
  source/build copies cleaned or explicitly pinned for a bounded next gate?
  Record before/after bytes; `.gitignore` and a cleanup TODO are not retention.

These checks require reading evidence and code already relevant to the task.
A regular-expression checker cannot establish their truth. Do not claim that
a structural PASS verifies gameplay, software behavior or semantic consistency.

## Size and history policy

The checker enforces UTF-8 byte limits after normalizing line endings:
AGENTS 2,000; CODEX 32,000; TODO 18,000; README 16,000; this protocol 16,000.
Each marked current block is limited to 400 words. Do not raise limits, remove
markers or weaken checks to pass. Compact in the same task: first remove
duplicates/completed work, then move genuinely durable detail to its owner and
leave a pointer. Preserve meaning before optimizing size.

Even below the limits, replace outdated statements rather than append patches
to them. Root files contain concise rules, entrypoints and open work, not
per-stage metrics or a chronological diary. Historical sections may be longer
when they retain useful evidence; label their date/scope and obsolete task
instructions explicitly. Time alone does not make a stable contract stale.
No automatic age-based deletion and no rewriting old failed receipts to PASS.

## Regression examples behind these rules

| Observed debt | Prevention |
| --- | --- |
| Conflicting GP-3 status repeated across design/engine/root notes | One marked current owner; other documents link to it |
| Completed drag/switch work left as missing functionality | Code/evidence preflight, remove completed TODO subitems |
| Bloom diagnosis added without changing the old acceptance queue | Failed-result trigger, index coverage, dependency-closure review |
| Old engine ids and speed estimates presented as current | Scope/date history; compare live manifest identities to owner |
| More than 200 KB of root context and copied development logs | Hard root budgets plus in-place compaction on every relevant task |
| Machine manifest still naming a previous next step | Reconcile live projections and review next-step semantics together |
| New 2+2 task at risk during another task's cleanup | Reread before contextual patching and preserve concurrent decisions |

## Checker ownership and limits

Implementation: `tools/check_handoffs.py`; focused regression suite:
`tests/tools/test_check_handoffs.py`. Run the suite when changing the checker;
ordinary handoff changes need only the checker and semantic review.
The checker covers entrypoint routing, index coverage, document target existence,
closed TODO checkboxes, budgets, unique current scopes, JSON syntax and declared
live identity/status/next-block projections. It includes new/untracked direct
handoff documents. Write external document references as explicit external links
so they cannot be confused with missing local files; external URLs are not fetched.
It ignores fenced examples and old manifest stage records. It does not validate
Markdown anchors, historical measurements, external sites or natural-language
claims. The semantic procedure above is mandatory for those claims.

This intentionally has no destructive auto-fix, background scan or local hook
installation. Agents perform meaning-preserving edits during the task, and
structural errors prevent declaring documentation closeout complete. Keep this
protocol as the single lifecycle owner instead of copying its checklist elsewhere.
