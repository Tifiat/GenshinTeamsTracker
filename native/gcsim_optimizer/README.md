# GTT GCSIM Optimizer Go module

Status: GOB-3 through GOB-7 pass.
The minimal adapter lives in engine patch 0022; this standalone module now
validates/evaluates engine-neutral seed-member formulas, combines a bound fixed
panel, indexes the real Selected artifact domain, performs bounded FGBS and
verifies a staged bounded finalist set in ordinary common-context GCSIM. There
is still no UI binding.

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

`validate-request` and `validate-seed-member` own strict boundary validation.
`aggregate-fixed-panel`, `benchmark-fixed-panel` and `audit-indexed-panel` own
parity/performance diagnostics. `search-fgbs REQUEST.json COMPACT.json` compiles
the fixed panel and real artifact domain once, then returns a bounded formula
leader and finalists. `verify-fgbs REQUEST.json COMPACT.json RUN_ROOT all`
screens the formula pool plus Current at n=128, retains at most seven builds,
then runs common n=1000 and returns the measured winner plus the ranked measured
finalist pages. `controls` is the
development-only Current/formula-leader/tail check.

Shared Python/Go fixtures live under
`tests/fixtures/gcsim_optimizer_go_v1/`. The authoritative design remains
`docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md`.
