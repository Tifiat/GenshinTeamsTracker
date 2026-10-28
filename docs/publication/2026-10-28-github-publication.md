# GitHub publication receipt — 28 October 2026

Remote: `https://github.com/Tifiat/GenshinTeamsTracker.git`.

## Published refs

| Remote branch | Commit | Notes |
| --- | --- | --- |
| `master` | `9d3179a689af587e8f9c5b2a7e815108f9b52931` | 40 previously outgoing commits plus the Russian README. |
| `codex/archive-bugfix-1-20261028` | `b9abf6b1aed1e19d9267f8b422a1f2003c71d18e` | Preserves the local side of the divergent `bugfix-1`; remote `bugfix-1` was left unchanged. |
| `codex/gob10-performance-audit` | `ba093f4126c534eb2d01211131585d6e5f040b15` | Named historical branch pointer; no commits unique against the published main history. |
| `codex/history-review` | `93abec584145bb0975f42875cd18b85acf40311f` | Includes its branch-specific History work. |
| `codex/optimizer-polish` | `95427ca338f38ad76708da317b231bb736058e5d` | Named historical branch pointer; no commits unique against the published main history. |
| `codex/pvp-providers` | `8356c59733c9113a3fba4985d978c1611150864b` | Named historical branch pointer; no commits unique against the published main history. |
| `codex/optimizer-theory-source-20261028-v2` | `919055af0185c44cc11b18684532c362b82264c9` | Curated source-only root snapshot from local source tip `98f1069f7736420b2b66ef932f5f4d0b3c83a726`; no original branch ancestry. |
| `worker3` | `23537c05859f8dbbb57ebbad0ce6b977a0efe2c6` | Includes its branch-specific work and evidence. |

The original `codex/optimizer-theory` history remains local and unchanged. Its
full tree contains large raw experiment/cleanup artifacts, including
`docs/optimizer-evidence/2026-10-11-theory-real-output/full-table.csv`
(163,071,805 bytes) and multi-megabyte result JSON files. The curated snapshot
excludes `docs/optimizer-evidence/`, `tests/fixtures/`, `samples/`, design and
handoff working materials, and the generated set-rule cache. Its README and
[snapshot note](optimizer-theory-source-snapshot-2026-10-28.md) state the exact
source tip, exclusions, and inherited experimental-tool import limitations.

## Checks and limits

- Explicit refspec pushes succeeded. `git ls-remote --heads origin` confirmed
  the published hashes above, including the curated snapshot, and showed the
  existing `bugfix-1` unchanged at `a8788d6637ee3e532f74ec02df0253e2cd07e621`.
- Scanned outgoing commit objects for profile/database/auth path names,
  credential patterns and private-key/token formats. No matches were found in
  the published branch ranges or curated snapshot. Large text patch blobs were
  checked separately.
- README link targets exist and `git diff --cached --check` passed.
- Static snapshot checks: 724 Python files parse with UTF-8 BOM handling;
  application import paths and native Go package imports resolve. Nine missing
  imports in old experiment utilities are also absent from source tip `98f1069`;
  see the snapshot note. No product tests or app launch were run.
- `tools/check_handoffs.py` reported one pre-existing size violation in the
  shared `workers/worker1.md` at initial publication; that shared file was not
  changed by the publisher. The owner later shortened repeated history, and the
  final closeout recheck passed.
- The main checkout's other dirty work was not staged or published: at capture
  it contained 135 modified, 5 deleted and 893 untracked paths. The README and
  this receipt were the only files added by this publication task.

This receipt records the refs at publication. The receipt and its closeout update
are follow-up commits after the README publication, so `master` advances again.
