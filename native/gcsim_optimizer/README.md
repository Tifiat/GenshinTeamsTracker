# GTT GCSIM Optimizer Go module

Current status/acceptance: `docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md` at the
repository root. The adapter lives in the consolidated engine patch; this module
validates/evaluates engine-neutral seed-member formulas, combines a bound fixed
panel, indexes the real Selected artifact domain, performs bounded FGBS and
verifies a staged bounded finalist set in ordinary common-context GCSIM. AppShell
Selected calls this module through `ui/gcsim_browser/run_worker.py` and the
Selected session bridge; Python does not perform the numerical search.
Selected preserves each currently equipped4p or distinct2+2 package, with one
flexible piece. Both use the same domain/search/formula engine; the new2+2 wire
requires the matching Python adapter and rebuilt standalone Go binary.

`internal/setcontext` is the isolated All Sets context/render/routing/cache
pilot. It shares the formula compiler, keeps set deltas outside raw item stats
and requires exact identities or trusted scoped replacement proofs. Its real
capture-process adapter now passes a two-seed copied-inventory pilot, sharing
`evaluator.CompileMembers`, `domain.ForPackages` and `search.RefineWearer`.
Slot-feasible package discovery does not enumerate physical builds. A general
effect-informed proposal/transfer coordinator is isolated in `internal/allsets`;
a real-set proof producer remains absent. `optimize-all-sets` now joins the
bounded coordinator with the shared ordinary finalist verifier; the Python
adapter and gated UI wiring reuse existing Selected account/cards/save paths.
The installed consumer now enables All Sets with the matching engine capability;
see the Go design and current checkpoint for bounded evidence and pending UI acceptance.

`internal/seteffects` discovers source recipes, amount alternatives, recipient
roles and typed attack-tag filters. Old-context raw-stat/channel probes are
heuristic features, not activation/replacement proofs. Its isolated reaction
input bridge uses `formula.CompileInterventions` over the same arithmetic and
exact-node annotations from the consolidated adapter's typed effect sidecar.
`optimizer_go_all_sources.py` verifies the whole built source tree
before transporting source bytes. Guide snapshots bind context, source, graph
and current item-stat anchor; stale guides cannot be reused. Pair-package seeds
use top-two per-slot candidates and a tiny set-count DP, not item-pair products.
Unknown syntax/ownership stays explicit. Do not wire these probes directly to
artifact scoring or treat the current graph's displayed actor as input owner.

The module is deliberately standalone and has no dependency on GCSIM internals.
Its versioned process contracts live in `internal/contracts` and use strict JSON
decoding: unknown fields, unknown schema versions/kinds, non-canonical ordering,
invalid identities, and inconsistent physical assignments fail closed.

## Canonical identity

Contract identity is SHA-256 of compact canonical UTF-8 JSON:

- object keys sorted lexicographically;
- array order validated by each schema rather than silently reordered;
- no insignificant whitespace;
- HTML escaping disabled;
- U+2028/U+2029 escaped as required by Go JSON;
- all gameplay decimals transported as canonical decimal strings.

Decimal strings avoid Python/Go float serialization drift. Later Go stages may
parse them once into numeric arrays outside the identity boundary.

## Current commands

`optimize-all-sets REQUEST.json SOURCES.json RUN_ROOT` runs the separate coordinator.
Source/neutral-input hints create a bounded package queue; `Refine` resolves
each shortlisted package's own context before sharing FGBS. Hint priorities
are not changed-set DPS. The Go design records the mathematics and limitations;
GP-3 owns acceptance and remaining team/UI/cleanup gates.

`validate-request` and `validate-seed-member` own strict boundary validation.
`aggregate-fixed-panel`, `benchmark-fixed-panel` and `audit-indexed-panel` own
parity/performance diagnostics. `search-fgbs REQUEST.json COMPACT.json` compiles
the fixed panel and real artifact domain once, then returns a bounded formula
leader and finalists. `verify-fgbs REQUEST.json COMPACT.json RUN_ROOT all`
screens the formula pool plus Current at n=128, retains at most seven builds,
then uses bounded adaptive n=500/n=1000 verification and returns the measured winner plus the ranked measured
finalist pages. `controls` is the
development-only Current/formula-leader/tail check.

Shared Python/Go fixtures live under
`tests/fixtures/gcsim_optimizer_go_v1/`. The authoritative design remains
`docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md`.
