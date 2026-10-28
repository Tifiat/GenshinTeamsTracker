# All Sets set-effect preflight (2026-09-16)

Bounded research only. Current owner:
`docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md`; implementation direction:
`docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md` (All Sets sections).

## Output lifecycle (N0 repair, 2026-09-17)

N0 now archived most historical raw paths below in the single verified
`.codex_tmp/optimizer-retained-evidence-20260917.zip`. The checkpoint and
`tools/optimizer_deep_cleanup.json` list exact members; restore only needed
inputs into managed scratch and adapt old absolute paths before a rerun. The
current user run, cold CLI baseline and Selected2+2 input fixture remain expanded.

The commands below record historical gates, not permission to keep creating
permanent scratch clones. For new disposable/replay work use
`tools/managed_optimizer_experiment.py --timeout <seconds> -- <command>` and
put every generated output under the literal `{scratch}` argument (use a child
such as `{scratch}/output` if the tool creates its output directory itself).
This runner substitutes the actual owned path, shares a temporary Go cache
within the command, and removes its workspace on success/error/cancellation.
Go calls through the project build/probe helper respect that managed cache too.
No command may detach a background process. Export only small needed receipts
and reproducers before exit; paths inside the disposable job are not permanent
inputs. For a multi-step capture/export, wrap the whole sequence once, not each
step separately. New persistent raw witnesses require an explicit consumer,
retention rule and deletion gate in the current cleanup manifest.

Force-kill/locked-file residue blocks the next managed allocation for inspection;
it is never blindly deleted while an orphan child might still use it. There is
no background sweeper of legacy scratch or active engine installations. See
`docs/handoff/DATA_RUNTIME_BOUNDARIES.md` for the production run cleaner and the
separate user-executed legacy allowlist.

`probe.py` reads the saved Selected2+2 bloom request/config/first compact member,
binds the unchanged installed engine and imports the existing2p descriptor code.
It runs exactly seven fresh n1 same-seed set changes, not artifact searches:
remove/replace/equivalent static effects, conditional4p, resistance removal,
team buff and additional damage. Fixture names are not gameplay switches in
production. The new-damage control is not meant to be a competitive build.
Output must be a new directory under `.codex_tmp`; the DB is never opened.

Run only when repeating that gate is actually necessary, using project Python:

```text
.venv/Scripts/python.exe tools/experiments/gcsim/all_sets_preflight/probe.py --source-run .codex_tmp/selected-2plus2-20260916/run --output .codex_tmp/<new-evidence-directory>
```

It reuses the real Go interpreter/dense matrix runner. Runner PASS is not a
response gate: inspect `gate.json` and `response.json`. Static successes and
deliberately wrong conditional/ghost/double-count shortcuts have different
meanings. Never turn a failed conditional shortcut into accepted reuse.

`export_evidence.py` creates the small permanent receipt and sampled native
regressions from existing output without engine calls. The originals are kept
under `.codex_tmp/all-sets-preflight-20260916`. Portable tests:
`TestSetStaticEffectReplacementWitnesses` and
`TestSetReplacementShortcutNegativeControls` in the Go formula package.
Their oracle numbers come from the changed engine capture, not the evaluator.

The current static classifier proves a narrow constructor assignment, not
absence of all Init/helper/key/order/branch effects. The compact graph has no
set-effect identity leaves and freezes observed resistance multipliers. The
isolated `internal/setcontext` module now gates reuse explicitly; otherwise it
requests a fresh formula for the changed whole-team context. This experiment
does not add that route to UI, bypass request identities, or authorize every
static-looking set replacement. Preserve Selected and defer energy support.

## Context/routing replay (no engine calls)

```text
.venv/Scripts/python.exe tools/experiments/gcsim/all_sets_preflight/replay_context.py --matrix .codex_tmp/all-sets-preflight-20260916 --source-run .codex_tmp/selected-2plus2-20260916/run --output .codex_tmp/<new-context-replay-directory>
```

The overlay `context_replay_test.go` imports the real Go context module and
compiler, validates saved file/config identities, renders seven substitutions,
loads their bound graphs and checks baseline/response/cache/restoration. Source
baseline is LF; the old Python experiment wrote CRLF changed configs. Rendering
is checked within matching newline frames, without rebinding captured evidence.
Additional comparisons between CRLF contexts exercise the effect-proof gate,
not merely the newline identity difference. No new process capture/search runs.

The static proof contract is exercised only on a known synthetic model in
normal Go tests. The actual engine changes have no full-lifecycle proof and
route to their fresh saved graph. Keep this distinction when reporting PASS.
Durable result: `all_sets_context_routing_receipt_v1.json` in native fixtures.
Local final output: `.codex_tmp/all-sets-context-20260916-final`; earlier first/
pass2 overlay outputs are disposable after integration. Keep the raw preflight
oracles until the bound process provider is checked, then follow the cleanup
manifest; do not preserve obsolete harness output as runtime data.

## Bound provider/domain/search pilot

`capture_pilot.py` runs the generic provider/domain/shared FGBS integration on
the original copied inventory, not the live DB. It deliberately chooses two
fixture packages (Lauma/Gilded4p, Kuki/Paradise4p), with1000 expansions each.
This is not the future automatic proposal queue or a production budget change.
It reserves exactly eight new compact calls: two seeds per changed context and
two seeds per independently checked winner. Original two-seed baseline is reused.
No ordinary n500/n1000, binary installation, UI or energy-setting changes.

```text
.venv/Scripts/python.exe tools/experiments/gcsim/all_sets_preflight/capture_pilot.py --source-run .codex_tmp/selected-2plus2-20260916/run --matrix .codex_tmp/all-sets-preflight-20260916 --output .codex_tmp/<new-provider-pilot-directory>
```

Actual evidence: `.codex_tmp/all-sets-capture-pilot-20260916-run2`.
The preceding attempt stopped on an incorrect harness hash comparison before
any new engine call; Selected's trace-context hash and config hash are distinct.
Do not weaken binding checks to merge them. Post-run harness refinements bind
candidate reference-stat rows and pass energy explicitly; no extra rerun needed.
Both changed candidates match fresh expected DPS, but neither improves the
original team. Do not claim account-scale All Sets acceptance from this pilot.

`measure_decode.py --member <saved-member.json> --output .codex_tmp/<new-dir>`
compares old/direct raw canonicalization three times on identical bytes with
no engine calls. Actual output `.codex_tmp/all-sets-decode-20260916`.
The shared-compiler older-context replay after this change lives in
`.codex_tmp/all-sets-context-provider-shared-20260916`.
`export_capture_evidence.py --pilot <dir> --decode <dir> --replay <dir>` generates
`all_sets_capture_domain_receipt_v1.json` without copying private inventory.
Timing scope and current effect-discovery tradeoff live in the Go design/GP-3.

## Source recipes and neutral reaction inputs

`discover_effects.py --engine-root <bound-source-root> --source-run <saved-run>
--output .codex_tmp/<new-dir>` scans the engine catalog and replays source-term
features on the saved FAST panel, without simulation. Its source counts are not
coverage percentages; alternatives, activation and missing numeric ports stay
explicit. Current retained output: `.codex_tmp/all-sets-effects-final-20260916`.

`probe_effect_inputs.py --engine-root <bound-source-root> --output
.codex_tmp/<new-dir> --prepare` reconstructs the reviewed experimental overlay
and runs narrow observer tests. The flat-name `effect_inputs_experiment.patch`
applies ONLY to its three isolated source copies, not an engine checkout or
production patch stack. Added observer/test sources are Go overlays in this
directory. Nothing is installed; generated overlay paths are relocated to the
actual source tree.

Only explicit `--capture-controls` runs four simulations: copied bloom and
cloud fixtures, each baseline and an artificial +0.1 reaction-bonus control.
No retries or existing-control overwrite. Actual four-capture output:
`.codex_tmp/all-sets-effect-inputs-20260916`. `replay_effect_inputs.py --output
<that-dir>` runs the native input-offset program on those saved captures, with
no new simulations.100 identical offline evaluations measure arithmetic cost;
they are not candidate enumeration or a broader response gate.

`export_effect_evidence.py --catalog <source-output> --inputs <capture-output>
--engine-root <source-root>` retains a sanitized receipt and the reviewed delta.
It does not copy inventory or activate a patch. Permanent receipt:
`all_sets_effect_discovery_receipt_v1.json`. Keep final raw oracles through guide
integration; delete the experimental delta after production consolidation/gates.

## Resistance and automatic proposal pilot

`probe_resistance_inputs.py --engine-root <root> --output .codex_tmp/<new-dir>
--prepare` layers the retained resistance delta on freshly prepared reaction
observer copies, then runs compact adapter tests. Generated numeric-marker
label substitution is research-only; production must modify the source seam.
Add `--capture-controls` only for an explicit four-simulation budget. The saved
oracles are `.codex_tmp/all-sets-resistance-inputs-20260916`.
`replay_resistance_inputs.py --output <oracles> --curves <source-output>/context-curves.json
--previous <reaction-oracles>` does no simulations and checks observed-source
curve binding, zero-change parity and fresh controlled responses.

`probe_joined_guide.py --catalog <source-output> --captures <resistance-oracles>
--output .codex_tmp/<new-dir>` joins source terms and exact input ports. Current
guide: `.codex_tmp/all-sets-guide-grouped-20260916`, source:
`.codex_tmp/all-sets-source-queue-20260916`. One fixed seed supplies effect hints;
the saved two-seed panel supplies raw artifact counterfactuals, not replacements.
`probe_proposals.py --source <saved-run> --catalog <source-output> --guide <guide>
--output .codex_tmp/<new-dir>` measures the16-entry queue without simulations.
Final pilot queue: `.codex_tmp/all-sets-queue-diverse-20260916`.

`capture_queue.py --source <saved-run> --catalog <source-output> --receipt
<queue>/proposal-queue.json --output .codex_tmp/<new-dir>` explicitly spends
eight new members on the first four automatic proposals,1000 FGBS expansions
each. `--verify-winner` instead consumes an `automatic-capture-receipt.json`
and spends exactly two new members on that prior winner's stat response.
Outputs: `.codex_tmp/all-sets-auto-capture-20260916` and
`.codex_tmp/all-sets-auto-winner-20260916`. No ordinary n500/n1000 or install.

`export_guide_evidence.py` accepts explicit engine/reaction/resistance/catalog/
guide/queue/automatic/winner directories and retains a sanitized receipt plus
the reproducible resistance delta. Both experimental deltas are removed after
production consolidation, not added as parallel production patch stacks.
First queue witnesses exposed duplicate shared-effect optimism and unequal
raw-equipment anchors; first joined harness used noncanonical actor order.
These were repaired offline before the eight automatic captures. Do not treat
their superseded local outputs as current quality evidence.

## Clean observer and refreshed guide

`prepare_observer_candidate.py --output .codex_tmp/<new-dir>` starts with the
cached official2.45 archive and active consolidated patch, then applies retained
`observer_source.patch`. No install/prune. The original bootstrap option is only
for reproducing the historical transition from reviewed flat observer copies.
`build_observer_candidate.py --candidate <dir> --installed <engine-root>` exports
one candidate consolidated patch and builds with the normal source generator.
`verify_observer_candidate.py --candidate <dir> --output .codex_tmp/<new-dir>`
spends exactly two n1 captures through the actual native client. It verifies
typed sidecar provenance, original/resolved-config distinction,18 stat responses
and graph-bound input probes. `check_observer_compatibility.py --candidate <dir>`
spends three tiny n1 bundle smokes and checks patch application to pristine source.
Candidate: `.codex_tmp/all-sets-observer-candidate-20260916`; successful transport:
`.codex_tmp/all-sets-observer-transport-20260916-run2`. First attempt exposed the
raw/resolved text hash distinction and spent one n1. Permanent consolidation
receipt records all six calls. That isolated receipt did not change installed
binaries/patch; subsequent product installation is checkpoint-owned.

`refresh_guide.py --candidate <dir> --capture <transport-dir> --output <new-dir>`
does no simulations: verifies source transport, compiles a real one-seed guide,
changes the legal artifact anchor, rejects the stale guide, checks refreshed
counterfactuals and bounded shared-key transfer proposals. Current output:
`.codex_tmp/all-sets-transfer-guide-20260917`. This is not product two-seed quality.
`capture_transfers.py --guide <guide-output> --capture <transport-dir> --output
<new-dir>` spends five new n1: missing second baseline seed plus two joint contexts
with two seeds each. Same default FGBS settings compare original packages with
joint alternatives. No installation or ordinary finalist calls.

`verify_transfer_winner.py --guide <guide-dir> --capture <joint-dir> --output
<new-dir>` spends exactly two new n1 on the best joint candidate's physical stats.
The2026-09-17 winner matches the formula to roundoff; see joint-context receipt.

`coordinator_pilot.py --guide <guide-dir> --transport <transport-dir> --capture
<joint-dir> --output <new-dir>` caps the shared search at four contexts and reuses
verified saved panels. Observed four new n1 and four reused members; no ordinary
simulation in this command. `verify_coordinator.py` replays those contexts and
uses the actual shared ordinary verifier: seven n128, seven n500 and at most four
n1000, one180s deadline, no new compact captures or artifact search.

`run_all_sets_cli.py --guide <guide-dir> --output <new-dir>` builds a temporary
consumer and exercises the coarse product command cold on the copied request.
It has no replay injection: at most eight two-seed contexts, seven n128, seven
n500 and four n1000;420s search/600s overall. No installation or live equipment
mutation. The first invocation found a missing capture-root creation before any
engine call; its corrected successor is separate evidence, not a rewritten pass.

`prepare_installation.py` prepares the one-shot clean install without activation;
`--resume` resumes its recorded path without rebuilding. The first byte-identity
guard stopped:155 files had CRLF/LF differences, not code differences. The resume
gate verifies the complete module inventory and normalized bytes plus generated
manifest semantics, then uses the NEW exact hashes for source validation. Three
bundle smokes and two saved-winner controls check the actual prepared executable.
Generated absolute overlays are mechanically rebased to the final source root.
`promote_installation.py` installs only those verified bytes with prior patch,
consumer and state backups; it does not simulate, prune or claim a real UI click.
`export_product_receipt.py` sanitizes preserved results into the permanent product
receipt. No source/formula/name-based gameplay override is introduced.
These deployment runners are dated evidence, not a second production updater.
Consolidated research deltas/raw duplicates await mandatory cleanup after the
pending real UI gate; keep rollback and permanent tests/receipts.
