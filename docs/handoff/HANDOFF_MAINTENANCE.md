# Handoff closeout

Use this after implementation, a saved decision, changed acceptance/evidence,
or a handoff edit. A failed or partial check counts when it changes a gate or
next action. Routine local code fixes with no durable change require focused
validation and the lightweight checker, but no documentation entry. Discussion-
only turns require no file edits or checker.

## Ownership

| Fact | One owner |
| --- | --- |
| Cross-project execution rule | `CODEX.md` or the linked scoped work-rule file |
| Active order | Shared hub TODO and backlog; local files are routers through [COORDINATION](COORDINATION.md) |
| Stable subsystem behavior | Area contract linked from `README.md` |
| Current implementation, acceptance, immediate next action | One current checkpoint per scope |
| A particular run, failure or measurement | Dated receipt/fixture |
| Required machine fields | Live manifest projection, checked against its owner |

Other files link to the owner rather than repeating status, numbers or a task
queue. Source code and tests decide implemented behavior; a passed test is not
automatically UI acceptance. Preserve scoped failed evidence, rollback IDs and
unique design knowledge. Remove superseded instructions and repeated prose.

The optimizer's current owner is `GCSIM_GOB11_GP3_CHECKPOINT.md`; the trace
handoff owns architecture, Go design owns implementation detail, and engine
integration owns update/rollback. Its cleanup manifest projects current
engine/patch/status/next-block fields and retains historical disposition.

## Current block

One file may own each current scope. Keep its compact status near the top:

~~~markdown
<!-- handoff-current: example-scope -->
Review date; installed state; acceptance and limits; next action; evidence links.
<!-- /handoff-current -->
~~~

Current blocks have a 400-word maximum. Moving ownership requires updating
incoming links and live projections in the same change. A review date is not
proof that product tests or external research were rerun.

## Closeout for an affected fact

1. Read the shared queue and Worker5 status through `COORDINATION.md`, then the
   current technical owner, relevant task item and live machine fields only.
   Inspect the present worktree/diff; preserve concurrent edits.
2. Update the owner in place with the actual outcome and its verification
   boundary. Keep backend, controlled response, installed engine and real UI
   evidence distinct. If facts conflict, retain both scoped observations and
   state the unresolved conflict.
3. Search narrow identifiers/old status/owner names in `CODEX.md`,
   `TODO.md` and `docs/handoff/`. Read and reconcile matching live claims;
   historical receipts keep their original results. Remove completed tasks and
   obsolete pending decisions, preserving unfinished subitems.
4. Add new direct handoff documents once to `CATALOG.md`; route a new active
   area from `README.md`. Update machine projections when their owner changes.
   New generated outputs require the lifecycle in `DATA_WORK_RULES.md`.
5. Run `.venv/Scripts/python.exe tools/check_handoffs.py` and fix structural
   errors. Review the meaning of affected facts and the final diff yourself.
   The checker is read-only and cannot prove gameplay, UI or semantic truth.
   Run `tests/tools/test_check_handoffs.py` when changing the checker.
   Until this worker receives the coordination-aware checker, the main checkout's
   script may be invoked read-only with `--root` naming this worker's checkout.
   Update only Worker5's shared status; queue changes are proposals for Worker1.

For a routine code fix with no affected durable fact, verify that boundary,
run the checker and report the focused product checks; skip steps 1-4 and do
not append an empty handoff log.

Do not rerun product tests or read every handoff solely for documentation
closeout. In a continuing chat, inspect diffs or changed sections of documents
already read rather than loading the whole file again.

## Size and history

The checker enforces UTF-8 budgets for short entrypoints and 400 words per
current block. Compact duplicated/completed content before moving durable
detail to its owner. Do not raise limits to avoid compaction. Dated receipts
remain dated, including failures; their old next-step labels do not control
today's work. No automatic age-based deletion or rewriting failed checks to
PASS. The complete catalog and long historical designs are optional lookup,
not startup context.
