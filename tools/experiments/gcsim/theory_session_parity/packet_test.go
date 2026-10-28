package main

// Copied only into a managed assembly. One captured universe, no ordinary
// simulator or second capture. Product/reference numerical functions are unchanged.
import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

var stage12Observer func(*hybridRun, string)

func stage12ObserveReference(h *hybridRun, label string) {
	if stage12Observer != nil {
		stage12Observer(h, label)
	}
}
func stage12Emit(v any) {
	b, e := json.Marshal(v)
	if e != nil {
		panic(e)
	}
	fmt.Println("STAGE12_RECEIPT " + string(b))
}
func stage12Route(s *theorysearch.Session) string {
	h := sha256.New()
	for _, key := range s.ParityRoute() {
		fmt.Fprintln(h, key)
	}
	return fmt.Sprintf("%x", h.Sum(nil))
}
func stage12RouteReference(h *hybridRun) string { return fmt.Sprintf("%x", h.w.route.Sum(nil)) }
func stage12Anchors(h *hybridRun) []theorysearch.ParityAnchor {
	out := []theorysearch.ParityAnchor{}
	for _, item := range h.sweeps {
		r := item.(map[string]any)
		out = append(out, theorysearch.ParityAnchor{Pass: r["pass"].(int), Actor: r["actor"].(int), Tuple: r["anchor_key"].(string)})
	}
	return out
}
func stage12ExtraCompare(t *testing.T, name string, s *theorysearch.Session, expectedRoute string, anchors []theorysearch.ParityAnchor) {
	t.Helper()
	if got := stage12Route(s); got != expectedRoute {
		t.Fatalf("stage12 %s ordered resolve route mismatch got=%s expected=%s", name, got, expectedRoute)
	}
	if !reflect.DeepEqual(s.ParityAnchors(), anchors) {
		t.Fatalf("stage12 %s sweep anchor mismatch", name)
	}
	stage12Emit(map[string]any{"kind": "route_anchor_parity", "phase": name, "route_sha256": expectedRoute, "resolved_calls": len(s.ParityRoute()), "anchors": anchors})
}
func stage12Reference(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State, light bool, deadline time.Time) *hybridRun {
	t.Helper()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	name, seconds := "stage12_H", 180
	if light {
		name = "stage12_light"
		seconds = 135
	}
	h := newHybrid(w, initial, name, true, deadline, seconds)
	cfg, err := commonHConfiguration("full", len(options))
	if err != nil {
		t.Fatal(err)
	}
	h.researchH = &cfg
	h.researchLight = &lightObservation{SkipDeep: light}
	if err = h.search(original, options); err != nil {
		t.Fatalf("stage12 reference %s stopped: %v", name, err)
	}
	if !h.alive() || h.completedPasses != 2 || (!light && h.refinedPasses != 2) {
		t.Fatalf("stage12 reference %s partial/guarded", name)
	}
	return h
}
func stage12PointVariants(t *testing.T, state alloc.State) []alloc.State {
	t.Helper()
	out := []alloc.State{state}
	mains := alloc.MainChoices()
	changed := false
	for a := 0; a < 4 && !changed; a++ {
		for slot := 2; slot < 5 && !changed; slot++ {
			for _, key := range mains[slot] {
				if key != state.Mains[a][slot] {
					s := alloc.ReplaceMain(state, a, slot, key, [4][10]float64{}, 45)
					if alloc.ValidateFull45(s) == nil {
						out = append(out, s)
						changed = true
						break
					}
				}
			}
		}
	}
	if !changed {
		t.Fatal("stage12 no legal changed-main replay")
	}
	changed = false
	for a := 0; a < 4 && !changed; a++ {
		for slot := 0; slot < 5 && !changed; slot++ {
			for from := 0; from < 4 && !changed; from++ {
				if state.Upgrades[a][slot][from] < .25 {
					continue
				}
				for to := 0; to < 4; to++ {
					if to == from {
						continue
					}
					s := state
					s.Upgrades[a][slot][from] -= .25
					s.Upgrades[a][slot][to] += .25
					if alloc.ValidateFull45(s) == nil {
						out = append(out, s)
						changed = true
						break
					}
				}
			}
		}
	}
	if !changed {
		t.Fatal("stage12 no legal quarter replay")
	}
	return out
}
func stage12Replay(t *testing.T, name string, c theorysearch.ParityCandidate, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, cfg theorysearch.Config, deadline time.Time, productBudget *[2]int, refBudget *[2]int) {
	t.Helper()
	if !time.Now().Before(deadline) {
		t.Fatal("stage12 replay offline guard")
	}
	rw, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	re, err := rw.get(c.Packages)
	if err != nil || re == nil {
		t.Fatalf("stage12 replay reference unavailable: %v", err)
	}
	model, err := factory()
	if err != nil {
		t.Fatal(err)
	}
	pw, err := theorysearch.NewFormulaWorld(req, base, model, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	defer pw.Close()
	pe, codes, err := pw.Resolve(context.Background(), c.Packages)
	if err != nil || pe == nil {
		t.Fatalf("stage12 replay product unavailable %v %v", codes, err)
	}
	ro := rw.objective(re)
	for i, s := range stage12PointVariants(t, c.State) {
		if !time.Now().Before(deadline) {
			t.Fatal("stage12 replay offline guard")
		}
		productBudget[0]++
		productBudget[1]++
		refBudget[0]++
		refBudget[1]++
		if productBudget[0] > 800000 || productBudget[1] > 200000 || refBudget[0] > 400000 || refBudget[1] > 100000 {
			t.Fatal("stage12 replay work guard")
		}
		pv, pg, err := pe.Objective(s, true)
		if err != nil {
			t.Fatal(err)
		}
		rv, rg, err := ro(proto.State(s), true)
		if err != nil {
			t.Fatal(err)
		}
		if math.Float64bits(pv) != math.Float64bits(rv) || pg != rg {
			t.Fatalf("stage12 %s point%d independent value/roll-gradient mismatch product=%016x reference=%016x", name, i, math.Float64bits(pv), math.Float64bits(rv))
		}
		b, _ := json.Marshal(pg)
		stage12Emit(map[string]any{"kind": "point_replay", "phase": name, "variant": i, "packages": c.Packages, "witness45": s, "value": pv, "value_bits": fmt.Sprintf("%016x", math.Float64bits(pv)), "gradient_sha256": fmt.Sprintf("%x", sha256.Sum256(b))})
	}
}
func stage12ArchiveCheck(t *testing.T, s *theorysearch.Session, first, breadth, deep theorysearch.Snapshot, light, H theorysearch.ParityPhase) {
	t.Helper()
	best := map[string]theorysearch.ParityCandidate{}
	aliases := map[string]map[string]bool{}
	for _, p := range []theorysearch.ParityPhase{light, H} {
		for _, r := range p.Pool {
			if old, ok := best[r.Family]; !ok || r.Value > old.Value {
				best[r.Family] = r
			}
		}
		for f, keys := range p.Aliases {
			if aliases[f] == nil {
				aliases[f] = map[string]bool{}
			}
			for _, key := range keys {
				aliases[f][key] = true
			}
		}
	}
	current := append(append([]theorysearch.FamilyRow{}, deep.CoLeaders...), deep.Pending...)
	ref := -math.MaxFloat64
	for _, r := range current {
		if r.FormulaDPS > ref {
			ref = r.FormulaDPS
		}
	}
	if ref != deep.ReferenceScore || len(current) != len(best) {
		t.Fatal("stage12 archive/reference mismatch")
	}
	familyCount, tupleCount, sensitivity := 0, 0, 0
	for _, r := range current {
		if alloc.ValidateFull45(r.Witness45) != nil {
			t.Fatal("stage12 archive illegal45")
		}
		f := stage12NormalizedFamily(r.Family)
		expected, ok := best[f]
		if !ok || math.Float64bits(r.FormulaDPS) != math.Float64bits(expected.Value) || r.Witness45 != expected.State || len(r.Aliases) != len(aliases[f]) {
			t.Fatal("stage12 archive lost or invented witness/alias")
		}
		for _, a := range r.Aliases {
			if !aliases[f][a.TupleKey] {
				t.Fatal("stage12 archive invented alias")
			}
		}
		deficit := 100 * (ref - r.FormulaDPS) / math.Abs(ref)
		if deficit <= 3+1e-12 {
			familyCount++
			tupleCount += len(r.Aliases)
		}
		if deficit <= 2+1e-12 {
			sensitivity++
		}
	}
	if familyCount != deep.FoundGroupFamilies || tupleCount != deep.FoundGroupTuples || sensitivity != deep.SensitivityGroupFamilies {
		t.Fatal("stage12 fixed-reference group mismatch")
	}
	active := s.ParityPhase()
	archive := s.ParityArchive()
	// Every active branch alias must be retained; breadth adds output only.
	for f, keys := range active.Aliases {
		want := map[string]bool{}
		for _, k := range archive.Aliases[f] {
			want[k] = true
		}
		for _, k := range keys {
			if !want[k] {
				t.Fatal("stage12 active alias missing from archive")
			}
		}
	}
	stage12Emit(map[string]any{"kind": "archive_group_parity", "families": len(current), "found_group_families": familyCount, "found_group_tuples": tupleCount, "sensitivity_families": sensitivity, "reference": ref, "snapshot_versions": []int64{first.SnapshotVersion, breadth.SnapshotVersion, deep.SnapshotVersion}})
}
func TestStage12NumericalParity(t *testing.T) {
	requestPath := os.Getenv("GTT_FEASIBLE_REQUEST")
	if requestPath == "" {
		t.Skip("managed study inputs required")
	}
	started := time.Now()
	overall, stop := context.WithTimeout(context.Background(), 600*time.Second)
	defer stop()
	raw, req, sources, err := readTheorySetSources(requestPath, os.Getenv("GTT_FEASIBLE_SOURCES"))
	if err != nil {
		t.Fatal(err)
	}
	rawSHA, err := contracts.CanonicalSHA256(raw)
	if err != nil {
		t.Fatal(err)
	}
	sourceBytes, err := os.ReadFile(os.Getenv("GTT_FEASIBLE_SOURCES"))
	if err != nil {
		t.Fatal(err)
	}
	sourceSHA := contracts.TextSHA256(string(sourceBytes))
	cfg, err := theorySessionConfig(raw, req, sources, rawSHA, sourceSHA, "preparation", "stage12-parity")
	if err != nil {
		t.Fatal(err)
	}
	if len(req.Stochastic.Seeds) != 2 || req.Stochastic.Seeds[0] != 742031889 || req.Stochastic.Seeds[1] != 742031890 {
		t.Fatal("stage12 seeds changed")
	}
	var rarity map[string]int
	b, err := os.ReadFile(os.Getenv("GTT_FEASIBLE_RARITIES"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(b, &rarity); err != nil {
		t.Fatal(err)
	}
	catalog := []domain.SetCapability{}
	for _, set := range sources.Sets {
		if rarity[set.Key] != 5 {
			t.Fatalf("stage12 unexpected non5star catalog set %s", set.Key)
		}
		catalog = append(catalog, domain.SetCapability{UID: set.Key, TwoPiece: true, FourPiece: set.FourPieceModeled})
	}
	options, err := theoryteams.Packages(catalog)
	if err != nil {
		t.Fatal(err)
	}
	for a := 0; a < 4; a++ {
		if !reflect.DeepEqual(options, cfg.Domains[a]) || cfg.Initial.Mains[a] != initialMains()[a] {
			t.Fatal("stage12 frozen domain/mains differ")
		}
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: rawSHA, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	original := [4]domain.Package{}
	empty := map[string][]setcontext.Set{}
	for a, w := range req.Wearers {
		for _, set := range base.Sets(w.WearerKey) {
			original[a].Sets = append(original[a].Sets, contracts.SetRequirement{SetUID: set.UID, Count: set.Count})
		}
		empty[w.WearerKey] = nil
	}
	if !reflect.DeepEqual(original, cfg.Original) {
		for a := range original {
			if theoryteams.Key([4]domain.Package{original[a]}) != theoryteams.Key([4]domain.Package{cfg.Original[a]}) {
				t.Fatal("stage12 original tuple differs")
			}
		}
	}
	base, err = base.Replace(empty)
	if err != nil {
		t.Fatal(err)
	}
	caproot := filepath.Join(os.Getenv("GTT_FEASIBLE_ROOT"), "capture")
	if err = os.MkdirAll(caproot, 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, caproot)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	capture, err := setcontext.NewSession(provider.Capture, 2)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		stage12Emit(map[string]any{"kind": "capture_budget", "attempted": capture.AttemptedCaptureMembers(), "ordinary_finalists": 0, "outer_seconds": time.Since(started).Seconds()})
	}()
	h, err := capture.Resolve(overall, base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if capture.AttemptedCaptureMembers() != 2 {
		t.Fatal("stage12 capture count")
	}
	if err = provider.Close(); err != nil {
		t.Fatal(err)
	}
	cfg, err = theorySessionConfig(raw, req, sources, rawSHA, sourceSHA, h.GraphSHA256(), cfg.SessionID)
	if err != nil {
		t.Fatal(err)
	}
	factory := setcontext.ResearchNeutralFactory(h, sources)
	offline := time.Now()
	deadline := offline.Add(480 * time.Second)
	if d, _ := overall.Deadline(); d.Before(deadline) {
		deadline = d
	}
	initial := proto.State(cfg.Initial)
	var firstExpected theorysearch.ParityPhase
	var firstRoute string
	var firstAnchors []theorysearch.ParityAnchor
	stage12Observer = func(ref *hybridRun, label string) {
		if label == "pass0" {
			firstExpected = referencePhase(ref)
			firstRoute = stage12RouteReference(ref)
			firstAnchors = stage12Anchors(ref)
		}
	}
	light := stage12Reference(t, factory, req, base, original, options, initial, true, deadline)
	stage12Observer = nil
	lightPhase := referencePhase(light)
	lightRoute := stage12RouteReference(light)
	lightAnchors := stage12Anchors(light)
	model, err := factory()
	if err != nil {
		t.Fatal(err)
	}
	world, err := theorysearch.NewFormulaWorld(req, base, model, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	guarded := theorysearch.NewParityResolver(world, deadline)
	session, err := theorysearch.New(cfg, guarded)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()
	ctx, cancel := context.WithDeadline(overall, deadline)
	defer cancel()
	first, err := session.First(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	stage12ComparePhases(t, "first", session.ParityPhase(), firstExpected, nil, nil, true)
	stage12ExtraCompare(t, "first", session, firstRoute, firstAnchors)
	firstLeader := session.ParityPhase().Pool[0]
	breadth, err := session.Breadth(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	stage12ComparePhases(t, "breadth", session.ParityPhase(), lightPhase, nil, nil, true)
	stage12ExtraCompare(t, "breadth", session, lightRoute, lightAnchors)
	breadthLeader := session.ParityPhase().Pool[0]
	deep, err := session.Deep(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	deepPhase := session.ParityPhase()
	deepLeader := deepPhase.Pool[0]
	stage12Observer = func(ref *hybridRun, label string) {
		if label == "pass0" {
			stage12ComparePhases(t, "H_pre_deep0", firstExpected, referencePhase(ref), nil, nil, true)
		}
	}
	baseline := stage12Reference(t, factory, req, base, original, options, initial, false, deadline)
	stage12Observer = nil
	baselinePhase := referencePhase(baseline)
	stage12ComparePhases(t, "deep", deepPhase, baselinePhase, nil, nil)
	stage12ExtraCompare(t, "deep", session, stage12RouteReference(baseline), stage12Anchors(baseline))
	stage12ArchiveCheck(t, session, first, breadth, deep, lightPhase, baselinePhase)
	totals := guarded.Totals()
	productBudget := [2]int{totals.Formula, totals.Gradient}
	lightBudget := [2]int{light.w.work.Formula, light.w.work.Gradient}
	baseBudget := [2]int{baseline.w.work.Formula, baseline.w.work.Gradient}
	for i, c := range []theorysearch.ParityCandidate{firstLeader, breadthLeader, deepLeader} {
		refBudget := &lightBudget
		if i == 2 {
			refBudget = &baseBudget
		}
		stage12Replay(t, []string{"first", "breadth", "deep"}[i], c, factory, req, base, cfg, deadline, &productBudget, refBudget)
	}
	if !time.Now().Before(deadline) || overall.Err() != nil {
		t.Fatal("stage12 final hard guard")
	}
	stage12Emit(map[string]any{"kind": "parity_summary", "status": "pass", "offline_seconds": time.Since(offline).Seconds(), "outer_seconds": time.Since(started).Seconds(), "offline_guard_seconds": 480, "capture_members": capture.AttemptedCaptureMembers(), "ordinary_finalists": 0, "catalog": len(options), "product_cumulative": productBudget, "light_with_replays": lightBudget, "H_with_replays": baseBudget, "model_graph_sha256": h.GraphSHA256(), "request_sha256": rawSHA, "source_sha256": sourceSHA})
}
func TestStage12PointVariantsAreLegalAndDistinct(t *testing.T) {
	var mains [4][5]string
	for a := range mains {
		mains[a] = initialMains()[a]
	}
	s := alloc.Seed(mains, [4][10]float64{}, 0, 45)
	rows := stage12PointVariants(t, s)
	if len(rows) != 3 || rows[0] == rows[1] || rows[0] == rows[2] {
		t.Fatal("replay variants not distinct")
	}
	for _, r := range rows {
		if alloc.ValidateFull45(r) != nil {
			t.Fatal("illegal replay variant")
		}
	}
}
