# Curated Theory source snapshot — 28 October 2026

- Source: local `codex/optimizer-theory` tip `98f1069f7736420b2b66ef932f5f4d0b3c83a726`.
- Publication form: a new root snapshot commit followed by this validation note, built through a separate Git index. Original local branch and history are unchanged; this branch is a source snapshot, not an ancestry-preserving mirror or a transfer into `master`.
- Preserved: application source, runtime/configuration files, assets, and test source from the exact source tree.

Excluded from the source tree:

- `docs/optimizer-evidence/`: raw run results and large experiment archives, including the 163 MB `2026-10-11-theory-real-output/full-table.csv` and large JSON/JSON.GZ records.
- `tests/fixtures/` and `samples/`: raw or sample inputs. Test source remains, but fixture-dependent tests are not self-contained here.
- `docs/design/`: design screenshots, references, and visual working material.
- `docs/handoff/` and root `AGENTS.md`, `CODEX.md`, `TODO.md`, `DEVELOPMENT_STORY.md`, `coordination.json`: internal task routing, historical work notes, and local coordination context.
- `native/gcsim_optimizer/set-rule-cache/`: generated cache files.
- `fandom_hp_2026_05_16.json`: raw scraped reference data.

Static closeout (no product tests or app launch): all 724 Python files parse with UTF-8 BOM handling; internal imports for `ui`, `run_workspace`, `hoyolab_export` and `localization` resolve; all native Go module import paths resolve; README relative links resolve. The historical experiment tools contain nine unresolved references to modules that are also absent from source tip `98f1069`: `tools.experiments.gcsim.mvp_polish`, `tools.experiments.gcsim.mvp_polish.r5_python`, `tools.experiments.gcsim.theory_source_repair`, `tools.experiments.gcsim.theory_audit.run_gaming_neutral`, and `tools.experiments.gcsim.theory_strategies.run_comparison`. These are inherited source-tip limitations, not caused by the exclusions.

The snapshot contains 1,593 files (36,045,179 bytes); its largest retained file is the 1,575,953-byte application background asset. Credential, token, private-key and profile/database path scans found no matches. The branch preserves experimental source only; it is not accepted, installed, or a current product baseline.