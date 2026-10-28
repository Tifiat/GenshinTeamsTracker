package theorysearch

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
)

// This resolver owns only deterministic fixture data. Its mutable model cache,
// route FIFO, counters and evaluator scratch make a partial fork observable.
// There is no engine, capture callback or external resource in this fixture.
type sessionFixtureSpec struct {
	families    map[string]string
	scores      map[string]float64
	unavailable bool
}

type sessionFixtureLedger struct {
	worlds   []*sessionFixtureWorld
	forks    int
	resolved map[string]string
}

type sessionFixtureRoute struct {
	Family string
	Hits   int
}

type sessionFixtureWorld struct {
	spec        *sessionFixtureSpec
	ledger      *sessionFixtureLedger
	models      map[string]float64
	modelFIFO   []string
	routes      map[string]sessionFixtureRoute
	routeFIFO   []string
	counters    map[string]int
	scratch     []float64
	closed      bool
	closeCalls  int
	failResolve error
	failFork    error
}

func newSessionFixtureWorld(spec *sessionFixtureSpec) (*sessionFixtureWorld, *sessionFixtureLedger) {
	l := &sessionFixtureLedger{resolved: map[string]string{}}
	w := &sessionFixtureWorld{spec: spec, ledger: l, models: map[string]float64{},
		routes: map[string]sessionFixtureRoute{}, counters: map[string]int{}, scratch: make([]float64, 4)}
	l.worlds = append(l.worlds, w)
	return w, l
}

func (w *sessionFixtureWorld) Resolve(ctx context.Context, p [4]domain.Package) (*Entry, []string, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	if w.closed {
		return nil, nil, errors.New("fixture resolver is closed")
	}
	if w.failResolve != nil {
		return nil, nil, w.failResolve
	}
	w.counters["resolve"]++
	w.scratch[0] += 1
	key := theorypackages.Key(p)
	if w.spec.unavailable {
		return nil, []string{"fixture_unavailable"}, nil
	}
	family, ok := w.spec.families[key]
	if !ok {
		return nil, nil, fmt.Errorf("tuple outside fixture: %s", key)
	}
	w.ledger.resolved[key] = family
	route, known := w.routes[key]
	if !known {
		if len(w.routeFIFO) == 7 {
			delete(w.routes, w.routeFIFO[0])
			w.routeFIFO = w.routeFIFO[1:]
		}
		w.routeFIFO = append(w.routeFIFO, key)
	}
	route.Family, route.Hits = family, route.Hits+1
	w.routes[key] = route
	if _, known := w.models[family]; !known {
		if len(w.modelFIFO) == 5 {
			delete(w.models, w.modelFIFO[0])
			w.modelFIFO = w.modelFIFO[1:]
		}
		w.modelFIFO = append(w.modelFIFO, family)
		w.models[family] = w.spec.scores[family]
	}
	value := w.spec.scores[family]
	return &Entry{Family: family, ContextSHA256: "fixture-context:" + key,
		Uncertainty: []string{"fixture_uncertainty"},
		Objective: func(_ alloc.State, gradient bool) (float64, [4][10]float64, error) {
			if w.closed {
				return 0, [4][10]float64{}, errors.New("fixture objective is closed")
			}
			w.counters["objective:"+family]++
			w.scratch[1] += value
			if gradient {
				w.counters["gradient"]++
				w.scratch[2]++
			} else {
				w.scratch[3]++
			}
			return value, [4][10]float64{}, nil
		}}, nil, nil
}

func (w *sessionFixtureWorld) Fork() (Resolver, error) {
	w.ledger.forks++
	if w.closed {
		return nil, errors.New("cannot fork closed fixture")
	}
	if w.failFork != nil {
		return nil, w.failFork
	}
	n := *w
	n.models = make(map[string]float64, len(w.models))
	for k, v := range w.models {
		n.models[k] = v
	}
	n.routes = make(map[string]sessionFixtureRoute, len(w.routes))
	for k, v := range w.routes {
		n.routes[k] = v
	}
	n.counters = make(map[string]int, len(w.counters))
	for k, v := range w.counters {
		n.counters[k] = v
	}
	n.modelFIFO = append([]string(nil), w.modelFIFO...)
	n.routeFIFO = append([]string(nil), w.routeFIFO...)
	n.scratch = append([]float64(nil), w.scratch...)
	n.closeCalls = 0
	w.ledger.worlds = append(w.ledger.worlds, &n)
	return &n, nil
}

func (w *sessionFixtureWorld) Close() {
	if !w.closed {
		w.closed = true
		w.closeCalls++
	}
}

func (w *sessionFixtureWorld) fingerprint(t *testing.T) string {
	t.Helper()
	return sessionFixtureJSON(t, struct {
		Models    map[string]float64
		ModelFIFO []string
		Routes    map[string]sessionFixtureRoute
		RouteFIFO []string
		Counters  map[string]int
		Scratch   []float64
		Closed    bool
	}{w.models, w.modelFIFO, w.routes, w.routeFIFO, w.counters, w.scratch, w.closed})
}

func sessionFixturePackage(uid string) domain.Package {
	return domain.Package{Sets: []contracts.SetRequirement{{SetUID: uid, Count: 4}}}
}

func sessionFixtureFamily(p [4]domain.Package) string {
	// The fourth wearer's packages are exact aliases of the same arithmetic.
	return strings.Join([]string{p[0].Key(), p[1].Key(), p[2].Key()}, "|")
}

func sessionFixtureConfig(t *testing.T, sizes [4]int) (Config, *sessionFixtureSpec) {
	t.Helper()
	cfg := Config{Binding: "fixture-binding", RequestSHA256: "fixture-request", SessionID: "fixture-session",
		Wearers: [4]string{"fixture-a", "fixture-b", "fixture-c", "fixture-d"}}
	mains := [4][5]string{}
	for a := range mains {
		mains[a] = [5]string{"hp", "atk", "em", "em", "em"}
		for i := 0; i < sizes[a]; i++ {
			cfg.Domains[a] = append(cfg.Domains[a], sessionFixturePackage(fmt.Sprintf("fixture-%d-%d", a, i)))
		}
		cfg.Original[a] = cfg.Domains[a][0]
	}
	cfg.Initial = alloc.Seed(mains, [4][10]float64{}, 0, 45)
	if err := alloc.ValidateFull45(cfg.Initial); err != nil {
		t.Fatalf("fixture full45 seed: %v", err)
	}
	spec := &sessionFixtureSpec{families: map[string]string{}, scores: map[string]float64{}}
	for _, a := range cfg.Domains[0] {
		for _, b := range cfg.Domains[1] {
			for _, c := range cfg.Domains[2] {
				for _, d := range cfg.Domains[3] {
					p := [4]domain.Package{a, b, c, d}
					f := sessionFixtureFamily(p)
					spec.families[theorypackages.Key(p)] = f
					spec.scores[f] = 99
				}
			}
		}
	}
	spec.scores[sessionFixtureFamily(cfg.Original)] = 100
	if sizes[1] >= 3 {
		// Choose a later actor-1 improvement absent from the two initial anchors.
		// It changes subsequent catalog anchors while keeping the objective
		// constant for every complete tuple and allocation.
		second := cfg.Original
		for _, p := range initialTuples(cfg.Original, cfg.Domains) {
			if sessionFixtureFamily(p) != sessionFixtureFamily(cfg.Original) {
				second = p
				break
			}
		}
		for _, p := range cfg.Domains[1][1:] {
			if p.Key() != second[1].Key() {
				peak := cfg.Original
				peak[1] = p
				spec.scores[sessionFixtureFamily(peak)] = 101
				break
			}
		}
	}
	return cfg, spec
}

func sessionFixtureJSON(t *testing.T, value any) string {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func assertSessionFixtureClosed(t *testing.T, l *sessionFixtureLedger) {
	t.Helper()
	for i, w := range l.worlds {
		if !w.closed || w.closeCalls != 1 {
			t.Errorf("resolver %d not closed exactly once: closed=%t closes=%d", i, w.closed, w.closeCalls)
		}
	}
}

func assertSessionBranchParity(t *testing.T, got, want *branch) {
	t.Helper()
	for _, pair := range []struct {
		name      string
		got, want any
	}{
		{"initial", got.initial, want.initial}, {"pool", got.pool, want.pool},
		{"aliases", got.aliases, want.aliases}, {"bank", got.bank, want.bank},
		{"starts", got.starts, want.starts}, {"visited", got.visited, want.visited},
		{"screened", got.screened, want.screened}, {"refined", got.refined, want.refined},
		{"unavailable", got.unavailable, want.unavailable}, {"work", got.work, want.work},
	} {
		if !reflect.DeepEqual(pair.got, pair.want) {
			t.Fatalf("resumed branch differs from direct branch in %s", pair.name)
		}
	}
	gw, gok := got.world.(*sessionFixtureWorld)
	ww, wok := want.world.(*sessionFixtureWorld)
	if !gok || !wok || gw.fingerprint(t) != ww.fingerprint(t) {
		t.Fatal("resumed resolver cache/FIFO/routes/counter/scratch differs from direct branch")
	}
}

func TestSessionFirstBreadthDeepMatchesUninterruptedCommonH(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{3, 3, 2, 2})
	w, ledger := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	oracleWorld, oracleLedger := newSessionFixtureWorld(spec)
	oracle := newBranch(oracleWorld, cfg.Initial)
	defer oracle.close()
	ctx := context.Background()
	// The oracle never calls a Session action, fork or checkpoint restoration.
	if err := oracle.start(ctx, cfg); err != nil {
		t.Fatal(err)
	}
	if err := oracle.pass(ctx, cfg, 0); err != nil {
		t.Fatal(err)
	}
	first, err := s.First(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	assertSessionBranchParity(t, s.active, oracle)
	assertSessionBranchParity(t, s.preDeep, oracle)
	firstBytes := sessionFixtureJSON(t, first)
	checkpointWorld := s.preDeep.world.(*sessionFixtureWorld).fingerprint(t)
	if ledger.forks != 1 || len(ledger.worlds) != 2 || oracleLedger.forks != 0 {
		t.Fatalf("unexpected first checkpoint fork/capture construction: forks=%d worlds=%d", ledger.forks, len(ledger.worlds))
	}
	breadth, err := s.Breadth(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	assertSessionBranchParity(t, s.preDeep, oracle)
	if checkpointWorld != s.preDeep.world.(*sessionFixtureWorld).fingerprint(t) {
		t.Fatal("breadth mutated the pre-deep resolver checkpoint")
	}
	breadthOnly := map[string]string{}
	for f, aliases := range s.archive.aliases {
		for key := range aliases {
			if _, known := oracle.aliases[f][key]; !known {
				breadthOnly[key] = f
			}
		}
	}
	if len(breadthOnly) == 0 {
		t.Fatal("fixture did not exercise breadth discoveries")
	}
	// Pinned uninterrupted common-H: first pass once, deep0, pass1, deep1.
	if err := oracle.deep(ctx, cfg); err != nil {
		t.Fatal(err)
	}
	if err := oracle.pass(ctx, cfg, 1); err != nil {
		t.Fatal(err)
	}
	if err := oracle.deep(ctx, cfg); err != nil {
		t.Fatal(err)
	}
	deep, err := s.Deep(ctx, cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	assertSessionBranchParity(t, s.active, oracle)
	if s.active.work.CompletedPasses != 2 || s.active.work.DeepBundles != 2 || ledger.forks != 1 {
		t.Fatalf("baseline repeated a first pass or forked again: work=%+v forks=%d", s.active.work, ledger.forks)
	}
	for key, family := range breadthOnly {
		if _, known := s.archive.aliases[family][key]; !known {
			t.Errorf("breadth alias lost from output archive: %s", key)
		}
	}
	if sessionFixtureJSON(t, first) != firstBytes {
		t.Fatal("later actions mutated the first snapshot")
	}
	if first.Phase != "first_light" || breadth.Phase != "breadth_light" || deep.Phase != "deep_baseline" ||
		!(first.SnapshotVersion < breadth.SnapshotVersion && breadth.SnapshotVersion < deep.SnapshotVersion) {
		t.Fatal("phase publications are not ordered immutable snapshots")
	}
	s.Close()
	assertSessionFixtureClosed(t, ledger)
}

func TestSessionAllFoundFamiliesAliasesAndFull45Witnesses(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{3, 3, 2, 2})
	w, ledger := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if _, err := s.First(context.Background(), cfg.Binding); err != nil {
		t.Fatal(err)
	}
	snapshot, err := s.Breadth(context.Background(), cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.CoLeaders) <= 5 {
		t.Fatalf("fixture did not retain more than five families: %d", len(snapshot.CoLeaders))
	}
	seen := map[string]string{}
	families := map[string]bool{}
	for _, row := range snapshot.CoLeaders {
		families[row.Family] = true
		if err := alloc.ValidateFull45(row.Witness45); err != nil {
			t.Fatalf("published illegal full45 witness: %v", err)
		}
		for a, rolls := range row.Witness45.Rolls() {
			sum := 0.0
			for _, units := range rolls {
				sum += units
			}
			if sum != 45 || row.Allocations[a].SpentRollUnits != 45 || row.Allocations[a].UnspentRollUnits != 0 {
				t.Fatalf("witness/allocation wearer %d does not spend the full 45 units", a)
			}
		}
		for _, alias := range row.Aliases {
			if _, duplicate := seen[alias.TupleKey]; duplicate {
				t.Fatalf("duplicate published exact alias: %s", alias.TupleKey)
			}
			seen[alias.TupleKey] = row.Family
			if alias.ContextSHA256 != "fixture-context:"+alias.TupleKey || len(alias.Packages) != 4 || !reflect.DeepEqual(alias.Uncertainty, []string{"fixture_uncertainty"}) {
				t.Fatal("published alias lost its context, wearer ownership or uncertainty")
			}
			var tuple [4]domain.Package
			for a, p := range alias.Packages {
				if p.WearerKey != cfg.Wearers[a] {
					t.Fatal("alias changed package wearer ownership")
				}
				tuple[a] = domain.Package{Sets: p.Sets}
			}
			if theorypackages.Key(tuple) != alias.TupleKey {
				t.Fatal("exact alias package rows do not reconstruct its tuple")
			}
		}
	}
	if !reflect.DeepEqual(seen, ledger.resolved) || snapshot.FoundGroupFamilies != len(families) || snapshot.FoundGroupTuples != len(seen) || snapshot.TotalFoundTuples != len(seen) {
		t.Fatal("snapshot capped, omitted or regrouped a found exact alias")
	}
	if snapshot.SourceUpper != "unbounded" || snapshot.OuterUpper != "unbounded" || snapshot.SearchStatus != "partial" {
		t.Fatal("found group claims an unsupported search bound")
	}
}

func TestSessionPracticalBandsUseOneFixedReferenceWithoutChaining(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{1, 1, 1, 1})
	w, _ := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	for _, row := range []struct {
		family string
		value  float64
	}{{"score-100", 100}, {"score-98", 98}, {"score-96", 96}} {
		s.archive.pool[row.family] = candidate{packages: cfg.Original, state: cfg.Initial, value: row.value, family: row.family}
		s.archive.aliases[row.family] = map[string]Alias{row.family: {TupleKey: row.family, Packages: packageRows(cfg.Original, cfg.Wearers)}}
	}
	out := s.publish(false)
	if out.ReferenceScore != 100 || out.FoundGroupFamilies != 2 || out.SensitivityGroupFamilies != 2 || len(out.Pending) != 1 {
		t.Fatalf("fixed-reference groups changed: reference=%g groups=%d sensitivity=%d pending=%d", out.ReferenceScore, out.FoundGroupFamilies, out.SensitivityGroupFamilies, len(out.Pending))
	}
	if out.Pending[0].Family != "score-96" || out.Pending[0].DeficitPercent != 4 || out.Pending[0].Reason != "below_practical_band_not_deeply_refined" {
		t.Fatal("96 was chained through 98 instead of compared with the fixed 100 reference")
	}
}

func TestSessionOwnsConfigAndPublishedSnapshots(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{2, 2, 1, 2})
	w, _ := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	ownedConfig := sessionFixtureJSON(t, s.cfg)
	cfg.Domains[0][0].Sets[0].SetUID = "mutated-domain"
	cfg.Original[1].Sets[0].SetUID = "mutated-original"
	cfg.Initial.Upgrades[0][0][0] = -1
	if sessionFixtureJSON(t, s.cfg) != ownedConfig {
		t.Fatal("session retained caller-owned input slices or state")
	}
	out, err := s.First(context.Background(), s.cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	want := sessionFixtureJSON(t, out)
	out.CoLeaders[0].Aliases[0].Packages[0].Sets[0].SetUID = "mutated-snapshot-package"
	out.CoLeaders[0].Aliases[0].Uncertainty[0] = "mutated-uncertainty"
	out.CoLeaders[0].Allocations[0].MainStats["sands"] = "mutated-main"
	out.CoLeaders[0].Allocations[0].Substats[0].RollUnits = -1
	out.CoLeaders[0].Witness45.Upgrades[0][0][0] = -1
	out.Rules["all_found_aliases"] = false
	again := s.publish(false)
	again.SnapshotVersion = out.SnapshotVersion
	if sessionFixtureJSON(t, again) != want {
		t.Fatal("snapshot mutation changed session state or a later snapshot")
	}
}

func TestSessionBindingFailureClosesAllForks(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{2, 1, 1, 1})
	w, ledger := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.First(context.Background(), cfg.Binding); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Breadth(context.Background(), "changed-input-model-engine"); !errors.Is(err, ErrBindingChanged) {
		t.Fatalf("changed binding did not fail closed: %v", err)
	}
	if _, err := s.Finish(); !errors.Is(err, ErrBindingChanged) {
		t.Fatalf("binding failure was promoted to a result: %v", err)
	}
	assertSessionFixtureClosed(t, ledger)
}

func TestSessionFinishCancelAndFailureReleaseAllWorlds(t *testing.T) {
	for _, mode := range []string{"finish-before-legal", "unavailable", "legal-finish", "cancel-before-legal", "cancel-after-legal", "resolve-failure", "fork-failure"} {
		t.Run(mode, func(t *testing.T) {
			cfg, spec := sessionFixtureConfig(t, [4]int{2, 1, 1, 1})
			w, ledger := newSessionFixtureWorld(spec)
			sentinel := errors.New("fixture failure")
			if mode == "unavailable" {
				spec.unavailable = true
			}
			if mode == "fork-failure" {
				w.failFork = sentinel
			}
			s, err := New(cfg, w)
			if err != nil {
				t.Fatal(err)
			}
			switch mode {
			case "finish-before-legal":
				if _, err := s.Finish(); !errors.Is(err, ErrNoResult) {
					t.Fatalf("early Finish: %v", err)
				}
			case "unavailable":
				if _, err := s.First(context.Background(), cfg.Binding); !errors.Is(err, ErrNoResult) {
					t.Fatalf("unavailable First: %v", err)
				}
			case "cancel-before-legal":
				ctx, cancel := context.WithCancel(context.Background())
				cancel()
				if _, err := s.First(ctx, cfg.Binding); !errors.Is(err, context.Canceled) {
					t.Fatalf("early cancellation: %v", err)
				}
			case "fork-failure":
				if _, err := s.First(context.Background(), cfg.Binding); !errors.Is(err, sentinel) {
					t.Fatalf("fork failure: %v", err)
				}
			default:
				first, err := s.First(context.Background(), cfg.Binding)
				if err != nil {
					t.Fatal(err)
				}
				if mode == "legal-finish" {
					last, err := s.Finish()
					if err != nil || !last.FinishedEarly || last.SnapshotVersion <= first.SnapshotVersion {
						t.Fatalf("legal Finish: %v", err)
					}
				} else if mode == "cancel-after-legal" {
					ctx, cancel := context.WithCancel(context.Background())
					cancel()
					if _, err := s.Breadth(ctx, cfg.Binding); !errors.Is(err, context.Canceled) {
						t.Fatalf("late cancellation: %v", err)
					}
				} else {
					w.failResolve = sentinel
					if _, err := s.Breadth(context.Background(), cfg.Binding); !errors.Is(err, sentinel) {
						t.Fatalf("resolve failure: %v", err)
					}
					if _, err := s.Finish(); !errors.Is(err, sentinel) {
						t.Fatalf("failure promoted to legal Finish: %v", err)
					}
				}
			}
			s.Close()
			assertSessionFixtureClosed(t, ledger)
			wantWorlds := 1
			if mode == "legal-finish" || mode == "cancel-after-legal" || mode == "resolve-failure" {
				wantWorlds = 2
			}
			if len(ledger.worlds) != wantWorlds {
				t.Fatalf("unexpected hidden resolver construction: %d", len(ledger.worlds))
			}
		})
	}
}

func TestSessionRejectsRepeatedAndClosedPhaseActions(t *testing.T) {
	cfg, spec := sessionFixtureConfig(t, [4]int{2, 1, 1, 1})
	w, ledger := newSessionFixtureWorld(spec)
	s, err := New(cfg, w)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	ctx := context.Background()
	if _, err := s.First(ctx, cfg.Binding); err != nil {
		t.Fatal(err)
	}
	assertRejected := func(action func(context.Context, string) (Snapshot, error)) {
		t.Helper()
		version, work := s.version, s.active.work
		fingerprint := s.active.world.(*sessionFixtureWorld).fingerprint(t)
		if _, err := action(ctx, cfg.Binding); err == nil {
			t.Fatal("stale phase action accepted")
		}
		if s.version != version || s.active.work != work || s.active.world.(*sessionFixtureWorld).fingerprint(t) != fingerprint || ledger.forks != 1 {
			t.Fatal("rejected action changed work, snapshots or resolver state")
		}
	}
	assertRejected(s.First)
	if _, err := s.Breadth(ctx, cfg.Binding); err != nil {
		t.Fatal(err)
	}
	assertRejected(s.Breadth)
	if _, err := s.Deep(ctx, cfg.Binding); err != nil {
		t.Fatal(err)
	}
	assertRejected(s.Deep)
	if _, err := s.Finish(); err != nil {
		t.Fatal(err)
	}
	version := s.version
	for _, action := range []func(context.Context, string) (Snapshot, error){s.First, s.Breadth, s.Deep} {
		if _, err := action(ctx, cfg.Binding); err == nil {
			t.Fatal("closed session accepted continuation")
		}
	}
	if s.version != version {
		t.Fatal("closed continuation published another snapshot")
	}
	assertSessionFixtureClosed(t, ledger)
}

func TestSessionTupleTieOrderAndDiverseBeamAreIndependentOfFamilyIDs(t *testing.T) {
	cfg, _ := sessionFixtureConfig(t, [4]int{1, 1, 1, 1})
	a, b, c := cfg.Original, cfg.Original, cfg.Original
	a[0], b[0], c[0] = sessionFixturePackage("a"), sessionFixturePackage("b"), sessionFixturePackage("c")
	c[1] = sessionFixturePackage("d")
	pool := map[string]candidate{
		"z-family": {packages: a, state: cfg.Initial, value: 100, family: "z-family"},
		"a-family": {packages: b, state: cfg.Initial, value: 100, family: "a-family"},
		"m-family": {packages: c, state: cfg.Initial, value: 100, family: "m-family"},
	}
	rows := sorted(pool)
	if rows[0].family != "z-family" || rows[1].family != "a-family" || rows[2].family != "m-family" {
		t.Fatal("equal scores were sorted by family instead of complete tuple")
	}
	anchors := beam(pool)
	if len(anchors) != 2 || anchors[0].family != "z-family" || anchors[1].family != "m-family" {
		t.Fatal("beam lost the tuple-first leader or most distinct tied anchor")
	}
	warm := newBranch(nil, cfg.Initial)
	warm.offer(pool["z-family"])
	other := pool["a-family"]
	other.state.Upgrades[0][0][0] += .25
	other.state.Upgrades[0][0][1] -= .25
	warm.offer(other)
	if len(warm.bank) != 2 || warm.bank[0].family != "a-family" || warm.bank[1].family != "z-family" {
		t.Fatal("warm bank tie order changed from family identity")
	}
}
