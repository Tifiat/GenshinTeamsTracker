# R5 single-run admission — ROOT, 28 October 2026

One Chasca AllSets OFF run is admitted through the existing prepared owner.
No installation, ON/warm, other team, additional trace policy or repeat is admitted.

- Source commit: `79ab9dad0a581f992b513fc4515b9e680f805f04`.
- Native map: `48f643c2e4c7f353806513c8e00f9f5efd31d5bfe615cdb93a038d9f84b9ae09`.
- Product Python map: `e3d71c217355830ca8e5cf21211a0d28fb8a924a4e53f955dfabd3bbec654569`.
- Consumer: `6f3027201939f0a796db8ba90a76187bdebbee8dfe9056b98ff510677b350e27`.
- Existing producer: `f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93`.
- Protected-state baseline: `9d81f64bfb44ed408387df75e5129fa5a89f32b467706f9b42fecd2344a53c01`.
- Full account: 604 artifacts, 597 eligible, 39 sets; exact R4 input identity.

ROOT independently checked the prepared receipt, source/harness file hashes,
consumer/producer bytes and matching tested maps. Native combined: 19 PASS,
one unavailable managed fixture SKIP; AllSets compiled without a matching test.
Python focused/adapter and four final runner checks passed, including actual
frozen AppShell child imports, mutation rejection and duplicate-run prevention.
Local performance decisions and retained validation are in ../OFFLINE_RU.md.

Historical R4 product Python bytes were not frozen; do not retrospectively claim
exact Python identity or attribute the entire wall-time difference to R5.
The inherited owner.source_closure label is historical: R5 recovery is the
committed native overlay plus prospective product/harness Git deltas indexed
by ../r5-ready-v1.json, not a standalone product checkout.

Tester executes only the exact `commands.off` from r5-ready-v1.json once.
No short quality timeout. First anomaly holds further runs for ROOT diagnosis.
After export, MAIN releases the original owner, verifies protected state and
cleanup, saves the result milestone, then stops. ROOT closes routing and reports.

## Result review — same finite run

ROOT independently compared the two saved off-details receipts: all nine ordered
gear lists, assignment/config hashes, formula scores, sources, ranks and iteration
counts match R4 exactly. All operation/capture/process counters match; actual R5
Python proof reports unchanged source and no unlisted harness imports.

Button87.656→90.765s (+3.109s); native70.394→73.793s. Search39.437→40.676s
includes capture8.242→8.666s. Final outer19.588→21.837s, inner16.893→19.078s;
outer-minus-inner2.695→2.759s. Most final growth is inside the unchanged engine
checks. This locates elapsed time but does not establish OS noise or a causal
code regression. No comparable full CPU/RSS profile or repeated matched pair
exists; overall speedup is not demonstrated. No repeat is admitted.

Same winner/config/formula: measured158330.243(SE104.496)→158113.230(SE102.698),
n500; delta−0.137%, combined SE146.514. No changed winner or search-quality loss
is observed. Local removed work/allocation gains remain separately supported.

Export the finite evidence, then release original owner9388 and verify cleanup
without another ROOT wait. Closure remains conditional on that actual receipt.
