# GTT GCSIM Optimizer Go module

Current acceptance and installed identities belong to
`docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md` at the repository root. The trace
contract owns behavior; the Go design owns implementation detail. This README
describes module boundaries and commands, not an independent acceptance log.

AppShell routes through `ui/gcsim_browser/run_worker.py` to the Python
`optimizer_go_selected`, `optimizer_go_all` and `optimizer_go_theory` sessions.
Python prepares immutable inputs, runs the selected executables and presents
results. Numerical search and finalist selection execute in this Go module.
`optimizer_go_requests`, `optimizer_go_inputs` and `optimizer_go_session` own
shared immutable requests, explicit mode preparation and process lifecycle;
`optimizer_go_contracts` owns canonical transport writers. The three mode
adapters supply capture/source preparation and their own native command. All
Sets does not inherit Selected's compact capture. Shared display text belongs
to `optimizer_go_result_text`, not the numerical backend.

- Selected fixes the chosen 4p or distinct2+2 package and searches owned items
  with one flexible piece using the shared domain/formula/search implementation.
- Infinite-energy All Sets with neutral-input capability uses
  `internal/allsets.RunNeutral`: capture without set bonuses, replay source rules
  over the observed event schedule, bind their effects to retained formula
  inputs, then search feasible packages and owned items. Schedule-changing
  effects route to their separately captured context. Unknown responses remain
  diagnosed boundaries.
- Finite-energy All Sets and the capability fallback use `internal/allsets.Run`,
  with separate full-context capture and observed energy constraints. This path
  remains live and must be preserved during cleanup.
- Theory uses the separate Go theoretical allocation route. Its finite-energy
  mode currently rejects the request; its remaining quality audit is queued in
  TODO and the checkpoint.

`internal/setcontext` owns context identity, rendering, captures and run-local
formula caches. `internal/seteffects` owns verified source interpretation,
activation, composition and the bounded source-only AST cache. Full discovery
is still used by finite All Sets, Theory and source audits. The neutral inventory
route skips those legacy descriptions. Equal syntax does not share team or
activation state. Synthetic static-replacement proofs have no production
producer. `optimizer_go_all_sources.py` verifies the built source tree before
transporting source bytes.

Ordinary Selected/All Sets results use one n500 measurement per selected
finalist. Fast mode ranks by formula and skips that final measurement. Result
pages group by set bonuses and expose independent single-item swaps. Display
limits do not widen core search. Product wall-clock timeouts are zero; search
work/cycle bounds still apply. Cooperative Finish finalizes complete builds
already found; Cancel terminates the request.

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

`optimize-all-sets REQUEST.json SOURCES.json RUN_ROOT` selects the neutral or
full-context route described above. `optimize-theory` takes the same three
paths and uses the theoretical allocation domain. Selected uses
`verify-fgbs REQUEST.json COMPACT.json RUN_ROOT all`.

Both inventory commands accept `--finish-file PATH`. Output options determine
normal/fast ranking and the number of found groups/swaps returned. No equipped
comparison build is reserved in the product finalist panel.

`validate-request` and `validate-seed-member` own strict boundary validation.
`aggregate-fixed-panel`, `benchmark-fixed-panel` and `audit-indexed-panel` own
parity/performance diagnostics. `search-fgbs REQUEST.json COMPACT.json` compiles
the fixed panel and real artifact domain once, then returns a bounded formula
leader and finalists. `verify-fgbs ... controls` is a separate development
comparison command; the application does not select it. `audit-set-sources`
reports verified source metadata. `warm-set-cache REQUEST.json SOURCES.json
TARGET` prepares all source-only syntax entries for distribution. The bundled
`set-rule-cache` is read-only at runtime; updated source entries go into the
bounded runtime cache selected by the Python adapter.

Cache warming uses a separate unfiltered syntax compiler: it includes sets
absent from the account but does not build legacy effect descriptions. Full
effect discovery remains a different operation; warming is not team-specific
activation or a claim about damage/schedule response.

Schema-v1 `finalists`, `budgets.development_timeout_ms` and
`cancellation.mode` remain validated compatibility inputs. They do not choose
the application panel, add a second timeout or switch the cancellation method.
Current inventory product output follows `result_options`; ordinary finalists
use one n500 pass, Finish is cooperative and Cancel interrupts the owned work.
Retire old fields only with an explicit versioned migration, not reinterpretation
of retained requests.

Shared Python/Go fixtures live under
`tests/fixtures/gcsim_optimizer_go_v1/`. The authoritative design remains
`docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md`.

## Build and test boundary

Go version is declared in `go.mod`. The executable is a generated ignored
artifact; checked-in Go source/tests, the Python bridge, fixtures and the
complete engine patch stack are the reproducible inputs. Ordinary unit tests
run with `go test -p 1 ./... -count=1 -timeout=120s` from this module. Saved-run
and active-engine tests require explicit `GTT_*` evidence paths and skip when
those inputs are absent; their skips do not prove live engine acceptance.

Builds, captures and research runs use `tools/managed_optimizer_experiment.py`
so caches and outputs have a finite lifecycle. Installing a binary is a
separate identity/parity gate; building alone does not authorize replacing the
application's executable. Historical source-copy overlays live under
`tools/experiments/gcsim/` and are not another product implementation.
