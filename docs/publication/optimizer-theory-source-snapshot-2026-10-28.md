# Curated Theory source snapshot — 28 October 2026

- Source: local `codex/optimizer-theory` tip `98f1069f7736420b2b66ef932f5f4d0b3c83a726`.
- Publication form: one root commit from a separate Git index. Original local branch and history are unchanged; this branch is a source snapshot, not an ancestry-preserving mirror or a transfer into `master`.
- Preserved: application source, runtime/configuration files, assets, and test source from the exact source tree.

Excluded from the source tree:

- `docs/optimizer-evidence/`: raw run results and large experiment archives, including the 163 MB `2026-10-11-theory-real-output/full-table.csv` and large JSON/JSON.GZ records.
- `tests/fixtures/` and `samples/`: raw or sample inputs. Test source remains, but fixture-dependent tests are not self-contained here.
- `docs/design/`: design screenshots, references, and visual working material.
- `docs/handoff/` and root `AGENTS.md`, `CODEX.md`, `TODO.md`, `DEVELOPMENT_STORY.md`, `coordination.json`: internal task routing, historical work notes, and local coordination context.
- `native/gcsim_optimizer/set-rule-cache/`: generated cache files.
- `fandom_hp_2026_05_16.json`: raw scraped reference data.

No product tests or app launches were run for this publication. Static source syntax/import-path and link checks are recorded in the publication closeout after the snapshot was built. The branch is experimental source preservation only; it is not accepted, installed, or a current product baseline.