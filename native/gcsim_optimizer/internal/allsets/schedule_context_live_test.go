package allsets

// Opt-in end-to-end exercise of the isolated schedule-capture route against a
// managed saved run. All generated capture files live under t.TempDir; this is
// a route diagnostic, not an optimizer or item-timing exactness claim.
import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestScheduleRouterActiveEngine(t *testing.T) {
	run := os.Getenv("GTT_SCHEDULE_CAPTURE_SAVED_RUN")
	if run == "" {
		t.Skip("explicit managed saved-run schedule-capture diagnosis only")
	}
	scratch := os.Getenv("GTT_SCRATCH_DIR")
	cache := os.Getenv("GOCACHE")
	if !filepath.IsAbs(run) || !filepath.IsAbs(scratch) || !filepath.IsAbs(cache) ||
		!schedulePathChild(scratch, cache) {
		t.Fatal("absolute saved run, managed scratch root, and child Go cache required")
	}
	tmp := os.TempDir()
	if !filepath.IsAbs(tmp) || !schedulePathChild(scratch, tmp) {
		t.Fatalf("t.TempDir must resolve below the managed job TMP: temp=%q scratch=%q", tmp, scratch)
	}
	if info, err := os.Stat(run); err != nil || !info.IsDir() {
		t.Fatalf("saved run directory unavailable: %s: %v", run, err)
	}
	read := func(path string, value any) {
		t.Helper()
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(data, value); err != nil {
			t.Fatal(err)
		}
	}
	var request contracts.OptimizerRequest
	var bundle seteffects.SourceBundle
	read(filepath.Join(run, "request.json"), &request)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	if err := request.Validate(); err != nil {
		t.Fatalf("saved request validation: %v", err)
	}
	if !strings.Contains(strings.ToLower(request.Context.PreparedConfig.Text), "chasca") {
		t.Fatal("saved prepared config is not the expected Chasca run")
	}
	if len(request.Stochastic.Seeds) != 2 || request.Stochastic.Seeds[0] >= request.Stochastic.Seeds[1] {
		t.Fatal("schedule capture requires exactly two sorted, distinct saved seeds")
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	sources, err := seteffects.CompileSourceBundle(bundle, request.Engine, bundle.CatalogSHA256)
	if err != nil {
		t.Fatalf("saved source bundle binding: %v", err)
	}
	oceanUID, oceanRow := scheduleOceanClamSource(sources)
	if oceanUID == "" || oceanRow.RuleUnresolved != "" {
		t.Fatalf("Ocean-Hued Clam rule unavailable (uid=%q unresolved=%q)", oceanUID, oceanRow.RuleUnresolved)
	}
	binding := setcontext.Binding{
		Engine: request.Engine, CatalogSHA256: bundle.CatalogSHA256,
		ReferenceStatsSHA256: requestSHA, Seeds: request.Stochastic.Seeds,
	}
	base, err := setcontext.New(binding, request.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatalf("saved prepared config binding: %v", err)
	}
	actors := base.Actors()
	chasca, chascaOwner := "", -1
	bennett, owner := "", -1
	for index, actor := range actors {
		if strings.Contains(strings.ToLower(actor), "chasca") {
			chasca, chascaOwner = actor, index
		}
		if strings.Contains(strings.ToLower(actor), "bennett") {
			bennett, owner = actor, index
		}
	}
	if chascaOwner < 0 || owner < 0 || !strings.Contains(strings.ToLower(request.Context.PreparedConfig.Text), "bennett") {
		t.Fatal("saved Chasca run must contain Chasca and Bennett wearers for the OHC schedule probe")
	}
	potential, reasons := sources.RequiresScheduleCapture([]seteffects.RuleChoice{{Owner: owner, Key: oceanUID, Pieces: 4}})
	if !potential {
		t.Fatalf("OHC 4-piece source did not publish schedule potential metadata: uid=%s reasons=%v", oceanUID, reasons)
	}
	neutralChanges := make(map[string][]setcontext.Set, len(actors))
	for _, actor := range actors {
		neutralChanges[actor] = nil
	}
	neutral, err := base.Replace(neutralChanges)
	if err != nil {
		t.Fatal(err)
	}
	chascaPotential, chascaReasons := sources.RequiresScheduleCapture([]seteffects.RuleChoice{{Owner: chascaOwner, Key: oceanUID, Pieces: 4}})
	if !chascaPotential {
		t.Fatalf("OHC 4-piece potential metadata missing for Chasca context: uid=%s reasons=%v", oceanUID, chascaReasons)
	}
	chascaChanges := make(map[string][]setcontext.Set, len(actors))
	for _, actor := range actors {
		chascaChanges[actor] = nil
	}
	chascaChanges[chasca] = []setcontext.Set{{UID: oceanUID, Count: 4}}
	chascaTarget, err := base.Replace(chascaChanges)
	if err != nil {
		t.Fatal(err)
	}
	targetChanges := make(map[string][]setcontext.Set, len(actors))
	for _, actor := range actors {
		targetChanges[actor] = nil
	}
	targetChanges[bennett] = []setcontext.Set{{UID: oceanUID, Count: 4}}
	target, err := base.Replace(targetChanges)
	if err != nil {
		t.Fatal(err)
	}

	ownedTemp := t.TempDir()
	neutralRoot := filepath.Join(ownedTemp, "neutral")
	scheduleRoot := filepath.Join(ownedTemp, "schedule")
	if err = os.Mkdir(neutralRoot, 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(scheduleRoot, 0700); err != nil {
		t.Fatal(err)
	}
	neutralProvider, err := setcontext.NewEffectEngineProvider(binding, neutralRoot)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := neutralProvider.Close(); closeErr != nil {
			t.Errorf("neutral provider binding changed: %v", closeErr)
		}
	}()
	scheduleProvider, err := setcontext.NewEffectEngineProvider(binding, scheduleRoot)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := scheduleProvider.Close(); closeErr != nil {
			t.Errorf("schedule provider binding changed: %v", closeErr)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	neutralSession, err := setcontext.NewSession(neutralProvider.Capture, len(request.Stochastic.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	neutralHandle, err := neutralSession.Resolve(ctx, neutral, nil, nil)
	if err != nil {
		t.Fatalf("two-seed neutral capture: %v", err)
	}
	neutralDPS, err := neutralHandle.EvaluateDPS(map[string]float64{})
	if err != nil {
		t.Fatal(err)
	}
	if len(neutralProvider.Timings()) != 2 {
		t.Fatalf("neutral engine calls=%d, want 2 seed calls", len(neutralProvider.Timings()))
	}
	assertScheduleCaptureTimings(t, neutralProvider.Timings(), neutral, request.Stochastic.Seeds)
	model, err := setcontext.NewNeutralModel(neutralHandle, sources)
	if err != nil {
		t.Fatalf("neutral source model: %v", err)
	}
	scheduleSession, err := setcontext.NewSession(scheduleProvider.Capture, len(request.Stochastic.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	observed := map[string]bool{}
	router := &scheduleContextRouter{
		sources: sources, model: model, captures: scheduleSession,
		maxMembers: len(request.Stochastic.Seeds), attempts: map[string]scheduleCaptureOutcome{},
		onCapture: func(reason string) { observed[reason] = true },
	}
	// OHC source potential is not proof of activation: Chasca does not heal in
	// this saved rotation, so the neutral replay must win without an engine call.
	inactiveHandle, inactiveBoundaries, err := router.Resolve(ctx, chascaTarget)
	if err != nil || inactiveHandle == nil || inactiveHandle.Route() != setcontext.NeutralEffects {
		t.Fatalf("inactive Chasca OHC potential was not resolved by neutral replay: route=%v boundaries=%v err=%v", routeOf(inactiveHandle), inactiveBoundaries, err)
	}
	if len(scheduleProvider.Timings()) != 0 || scheduleSession.AttemptedCaptureMembers() != 0 {
		t.Fatalf("inactive Chasca OHC context caused a schedule capture: calls=%d members=%d", len(scheduleProvider.Timings()), scheduleSession.AttemptedCaptureMembers())
	}
	setHandle, boundaries, err := router.Resolve(ctx, target)
	if err != nil || setHandle == nil || setHandle.Route() != setcontext.FreshCapture {
		t.Fatalf("active OHC context did not take an independent schedule capture: route=%v boundaries=%v err=%v", routeOf(setHandle), boundaries, err)
	}
	if setHandle.ContextKey() != target.Key() {
		t.Fatalf("captured handle is not keyed to the complete target context: %s != %s", setHandle.ContextKey(), target.Key())
	}
	setDPS, err := setHandle.EvaluateDPS(map[string]float64{})
	if err != nil {
		t.Fatal(err)
	}
	if setHandle.GraphSHA256() == neutralHandle.GraphSHA256() || math.Abs(setDPS-neutralDPS) <= 1e-8*math.Max(1, math.Abs(neutralDPS)) {
		t.Fatalf("OHC target did not change captured graph and damage output: neutral_graph=%s target_graph=%s neutral_dps=%.12f target_dps=%.12f", neutralHandle.GraphSHA256(), setHandle.GraphSHA256(), neutralDPS, setDPS)
	}
	if math.IsNaN(setDPS) || math.IsInf(setDPS, 0) || math.IsNaN(neutralDPS) || math.IsInf(neutralDPS, 0) {
		t.Fatalf("nonfinite captured damage score: neutral=%.12f target=%.12f", neutralDPS, setDPS)
	}
	if len(scheduleProvider.Timings()) != 2 || scheduleSession.AttemptedCaptureMembers() != len(request.Stochastic.Seeds) {
		t.Fatalf("target capture did not use exactly its two saved seeds: timings=%d members=%d", len(scheduleProvider.Timings()), scheduleSession.AttemptedCaptureMembers())
	}
	assertScheduleCaptureTimings(t, scheduleProvider.Timings(), target, request.Stochastic.Seeds)
	if !hasObservedPrefix(observed, "schedule_capture_changed_item_timing_unverified:") {
		t.Fatalf("captured graph lost its changed-item timing caveat: %v", observed)
	}
	if repeated, _, repeatErr := router.Resolve(ctx, target); repeatErr != nil || repeated == nil || len(scheduleProvider.Timings()) != 2 {
		t.Fatalf("repeated target recaptured or disappeared: handle=%v calls=%d err=%v", repeated, len(scheduleProvider.Timings()), repeatErr)
	}
	back, backBoundaries, err := router.Resolve(ctx, neutral)
	if err != nil || back == nil || back.Route() != setcontext.NeutralEffects {
		t.Fatalf("switch back to neutral did not return its neutral model: route=%v boundaries=%v err=%v", routeOf(back), backBoundaries, err)
	}
	backDPS, err := back.EvaluateDPS(map[string]float64{})
	if err != nil {
		t.Fatal(err)
	}
	if back.GraphSHA256() != neutralHandle.GraphSHA256() || math.Abs(backDPS-neutralDPS) > 1e-8*math.Max(1, math.Abs(neutralDPS)) {
		t.Fatalf("switching back leaked schedule-set effects: graph=%s/%s dps=%.12f/%.12f", back.GraphSHA256(), neutralHandle.GraphSHA256(), backDPS, neutralDPS)
	}
	if len(scheduleProvider.Timings()) != 2 {
		t.Fatalf("returning to neutral caused a target engine call: %d", len(scheduleProvider.Timings()))
	}
	t.Logf("schedule route verified: neutral_dps=%.12f target_dps=%.12f neutral_calls=%d target_calls=%d warning=changed_item_timing_unverified", neutralDPS, setDPS, len(neutralProvider.Timings()), len(scheduleProvider.Timings()))
}

func scheduleOceanClamSource(catalog *seteffects.SourceCatalog) (string, seteffects.DiscoveredSet) {
	for _, set := range catalog.Sets {
		key := strings.ToLower(strings.NewReplacer("-", "", "_", "").Replace(set.Key))
		if key == "oceanhuedclam" {
			return set.Key, set
		}
	}
	return "", seteffects.DiscoveredSet{}
}

func assertScheduleCaptureTimings(t *testing.T, timings []setcontext.CaptureTiming, target *setcontext.Context, seeds []uint64) {
	t.Helper()
	if len(timings) != len(seeds) {
		t.Fatalf("engine calls=%d, want one per seed (%d)", len(timings), len(seeds))
	}
	for i, timing := range timings {
		if timing.ContextSHA256 != target.Key() || timing.Seed != seeds[i] {
			t.Fatalf("engine call was not bound to target context/seed: %+v", timing)
		}
	}
}

func schedulePathWithin(root, path string) bool {
	relative, err := filepath.Rel(filepath.Clean(root), filepath.Clean(path))
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(os.PathSeparator))
}

func schedulePathChild(root, path string) bool {
	return filepath.Clean(root) != filepath.Clean(path) && schedulePathWithin(root, path)
}

func hasObservedPrefix(rows map[string]bool, prefix string) bool {
	for row := range rows {
		if strings.HasPrefix(row, prefix) {
			return true
		}
	}
	return false
}

func routeOf(handle *setcontext.Handle) setcontext.Route {
	if handle == nil {
		return "missing"
	}
	return handle.Route()
}
