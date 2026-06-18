---
name: sync-github-rebase
description: Safely synchronize a local Git repository with its GitHub remote by reviewing and committing intended changes, fetching and checking upstream state, rebasing local commits onto the updated remote branch, resolving rebase conflicts, validating the result, pushing without force, and confirming final synchronization. Use when the user asks to sync, update, publish, commit and push, rebase before push, bring a branch up to date with GitHub, or handle conflicts during that workflow.
---

# Synchronize GitHub with rebase

Complete the whole synchronization workflow unless a conflict requires a genuine product decision. Preserve user work and report the final commit, branch, remote, validation, and synchronization state.

## Safety rules

- Treat all existing local changes and commits as user-owned. Never discard or overwrite them.
- Never use `reset --hard`, destructive checkout/restore commands, plain `--force`, or history rewriting unrelated to the requested synchronization.
- Do not amend existing commits, bypass hooks with `--no-verify`, change branches, or force-push unless the user explicitly requests it.
- Stage only intended project changes. Exclude secrets, credentials, local environment files, generated artifacts, and unrelated edits.
- Preserve the existing staged/unstaged split when it reflects an intentional partial commit. If commit scope is materially ambiguous, ask before committing.
- Resolve conflicts from the surrounding code and intent. During rebase, do not choose `ours` or `theirs` blindly because their meaning differs from a normal merge.
- Use normal `git push`. If non-fast-forward rejection repeats after fetch and rebase, diagnose it; do not escalate automatically to force-push.

## Workflow

### 1. Inspect the repository

1. Locate the repository root and inspect:
   - current branch and whether HEAD is detached;
   - concise status, including untracked files;
   - staged and unstaged diffs;
   - remotes, upstream tracking branch, and any in-progress Git operation;
   - recent local commits when needed to understand intent.
2. Stop and explain if a merge, rebase, cherry-pick, or revert is already in progress; continue that operation only when it is clearly part of the user's request.
3. Prefer the configured upstream. Otherwise infer `origin/<current-branch>` if it exists. If no suitable GitHub remote or branch can be determined safely, ask for direction.

### 2. Validate and commit intended changes

1. Review the diff for accidental secrets, debug output, generated files, and unrelated changes.
2. Run the repository's relevant fast tests, formatter check, lint, typecheck, or build before committing when discoverable and proportionate. Do not silently rewrite unrelated files with an auto-formatter.
3. Stage only the intended paths. Respect any deliberate partial staging already present.
4. Create one coherent commit with a concise message derived from the actual diff. If there are no intended uncommitted changes, skip the commit.
5. If a hook or validation fails, fix an in-scope problem and retry. Never bypass the failure without explicit user approval.
6. Ensure the working tree is clean before rebase. If unrelated local edits must remain uncommitted, preserve them with rebase autostash only after recording their state; verify that they are restored afterward.

### 3. Fetch and measure synchronization

1. Fetch the relevant remote with pruning.
2. Compare local HEAD with the resolved upstream using left/right commit counts and inspect the commits on each side when either count is nonzero.
3. Interpret the state:
   - equal: no rebase needed;
   - local ahead only: ready for the final remote check and push;
   - remote ahead only or diverged: rebase onto the fetched upstream;
   - no upstream yet: rebase onto `origin/<current-branch>` if that branch exists, otherwise prepare to establish upstream on first push.

### 4. Rebase and resolve conflicts

1. Rebase the current branch onto the fetched upstream. Do not use an interactive rebase unless explicitly requested.
2. For every conflict:
   - list all unmerged paths and inspect the base/upstream/local context plus nearby callers and tests;
   - determine the intent of both sides and combine compatible changes rather than selecting a side wholesale;
   - handle modify/delete and rename conflicts according to the resulting project structure;
   - remove all conflict markers, stage the resolved paths, and continue the rebase non-interactively while retaining the original commit message;
   - repeat until the rebase completes.
3. Run focused validation after meaningful resolutions. Then run the broader relevant checks after the rebase.
4. If the correct result depends on an unknowable product choice, pause with the exact files, competing behaviors, and a concise question. Keep all user work recoverable and state whether the rebase remains in progress.
5. If the rebase fails for a mechanical reason, diagnose and repair it. Abort only when continuing safely is impossible, and explain the reason.

### 5. Close the race and push

1. Fetch the upstream again immediately before pushing.
2. Recompute ahead/behind counts. If the remote advanced, rebase again and revalidate instead of attempting a stale push.
3. Push normally:
   - use the configured upstream when present;
   - on a new remote branch, push the current HEAD and establish upstream deliberately.
4. If push is rejected because the remote advanced between the final fetch and push, fetch, rebase, validate, and retry the normal push.

### 6. Verify final state

1. Fetch once more after the push.
2. Confirm that local HEAD and the upstream resolve to the same commit and that ahead/behind counts are both zero.
3. Check status for unresolved conflicts or unexpected leftover changes. If autostash was used, confirm the original edits were restored.
4. Report:
   - branch and upstream;
   - pushed commit hash and subject;
   - whether rebase or conflict resolution occurred;
   - validation commands and results;
   - explicit confirmation that local and GitHub are synchronized, or the exact remaining blocker.

## Useful checks

Adapt syntax to the current shell and repository rather than copying blindly.

```text
git status --short --branch
git diff --check
git remote -v
git rev-parse --abbrev-ref --symbolic-full-name @{upstream}
git fetch --prune <remote>
git rev-list --left-right --count HEAD...<upstream>
git log --oneline --left-right HEAD...<upstream>
git diff --name-only --diff-filter=U
git rebase <upstream>
git -c core.editor=true rebase --continue
git push
git rev-parse HEAD
git rev-parse <upstream>
```
