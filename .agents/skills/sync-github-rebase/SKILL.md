---
name: sync-github-rebase
description: "Quickly synchronize the current Git repository with its GitHub upstream: commit intended local changes when present, update with pull --rebase, resolve conflicts only if they occur, push local commits, and report the result. Use when the user asks to sync, pull, update, commit and push, rebase before push, or resolve conflicts with GitHub."
---

# Synchronize GitHub quickly

Use the shortest safe path. Keep commentary minimal and do not narrate routine Git commands one by one.

## Non-negotiable behavior

- If the working tree is clean and the branch is not ahead, run `git pull --rebase` and stop after it succeeds.
- Do not run tests, lint, builds, formatters, or repeated fetch/comparison checks during a routine successful sync.
- Run focused validation only after resolving a conflict or when a Git command fails and validation is needed to diagnose the failure.
- Do not create an empty commit and do not push when there are no local commits to publish.
- Preserve all user work. Never use `reset --hard`, destructive checkout/restore, plain `--force`, or automatic history rewriting beyond the requested rebase.
- Never bypass hooks with `--no-verify`. Never force-push without explicit user approval.

## Workflow

### 1. Inspect only what is necessary

1. Confirm the repository, current branch, upstream, concise status, and whether a merge or rebase is already in progress.
2. Use the configured upstream. Ask only if no suitable upstream can be determined safely.
3. Avoid broad repository inspection unless local changes or a conflict require it.

### 2. Take the fast path

When the working tree is clean:

1. Run `git pull --rebase`.
2. If it succeeds and there were no local commits ahead of upstream, report the update and finish. Do not run tests and do not push.
3. If local commits are ahead after the pull, push normally and finish.
4. If the pull produces a conflict, follow the conflict workflow.

This path covers both an already synchronized branch and a branch that is only behind GitHub. A clean fast-forward update needs no validation suite.

### 3. Commit local changes when present

1. Inspect only the changed and untracked files needed to understand commit scope.
2. Exclude secrets, credentials, generated artifacts, and clearly unrelated edits.
3. Respect intentional partial staging. If scope is materially ambiguous, ask before committing.
4. Stage the intended paths and create one concise commit. Let normal hooks run.
5. Run `git pull --rebase` immediately after the commit.
6. If the pull succeeds, push normally. Do not add routine test or fetch cycles.

### 4. Resolve only actual conflicts

If rebase reports conflicts:

1. List unmerged paths and inspect both sides plus nearby code needed to understand intent.
2. Combine compatible changes; do not select `ours` or `theirs` blindly during rebase.
3. Remove conflict markers, stage resolved files, and continue with `git -c core.editor=true rebase --continue`.
4. Repeat until rebase completes.
5. Run only the focused checks relevant to the resolved files. Run broader checks only when the conflict affects broad behavior or focused checks reveal a problem.
6. Push normally after successful resolution.
7. Ask the user only when the resolution requires an unknowable product decision.

### 5. Handle push rejection

If a normal push is rejected because GitHub advanced:

1. Run `git pull --rebase` once more.
2. Resolve conflicts only if they occur.
3. Retry the normal push.
4. Do not escalate to force-push automatically.

### 6. Finish briefly

Run one concise status check. Report the branch, commit created or pulled, whether conflicts occurred, and whether push happened. Do not perform another fetch or test suite merely to reconfirm a successful pull or push.
