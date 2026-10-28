package main

// Isolated search harness. Copied into a managed native checkout for compilation.
// It reuses source-owned formulas, and never implements character damage rules.
import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

type feasibleWork struct {
	Formula, Gradient, Contexts, Unavailable, FamilyReuses, AllocationAttempts int
	AllocationCacheHits, RefineCacheHits                                       int
	ResolveSeconds, SpecializeSeconds                                          float64
}
type feasibleEntry struct {
	panel    *evaluator.Panel
	program  *formula.ArtifactProgram
	coords   []string
	baseline []float64
	indices  [4][10]int
	family   string
}
type feasibleWorld struct {
	req                contracts.OptimizerRequest
	base               *setcontext.Context
	model              *setcontext.NeutralModel
	entries            map[string]*feasibleEntry
	order              []string
	work               feasibleWork
	boundaries, opaque map[string]bool
	metadata           map[string][]string
	numericCache       map[[32]byte]proto.Result
	numericOrder       [][32]byte
	numericReuse       bool
	entryLimit         int
	hunterObserved     bool
}
type feasibleCandidate struct {
	packages [4]domain.Package
	state    proto.State
	value    float64
	family   string
}

func emitFeasible(x any) {
	b, e := json.Marshal(x)
	if e != nil {
		panic(e)
	}
	fmt.Println("FEASIBLE_RECEIPT " + string(b))
}
func (w *feasibleWorld) get(p [4]domain.Package) (*feasibleEntry, error) {
	choices := map[string][]setcontext.Set{}
	for a, wearer := range w.req.Wearers {
		for _, s := range p[a].Sets {
			choices[wearer.WearerKey] = append(choices[wearer.WearerKey], setcontext.Set{UID: s.SetUID, Count: s.Count})
		}
	}
	target, e := w.base.Replace(choices)
	if e != nil {
		return nil, e
	}
	start := time.Now()
	h, key, codes, e := w.model.ResearchFamily(target)
	if e == nil && h == nil && w.hunterObserved {
		h, codes, e = w.model.ResearchResolveHunterObservedSchedule(target)
		key = "observed-hunter:" + theoryteams.Key(p)
	}
	w.work.ResolveSeconds += time.Since(start).Seconds()
	w.work.Contexts++
	for _, code := range codes {
		w.boundaries[code] = true
	}
	if e != nil {
		return nil, e
	}
	if h == nil {
		w.work.Unavailable++
		return nil, nil
	}
	panel, e := h.SearchPanel()
	if e != nil {
		return nil, e
	}
	for _, reason := range panel.OpaqueReasons() {
		w.opaque[reason] = true
	}
	w.metadata[theoryteams.Key(p)] = append(append([]string(nil), codes...), panel.OpaqueReasons()...)
	if known := w.entries[key]; known != nil {
		return known, nil
	}
	start = time.Now()
	index, e := domain.BuildTheory(w.req, panel.Coordinates())
	if e != nil {
		return nil, e
	}
	delta, e := index.DenseDeltas(index.Incumbent)
	if e != nil {
		return nil, e
	}
	program, e := panel.ArtifactProgramForActors(delta, 0, 1, 2, 3)
	if e != nil {
		return nil, e
	}
	baseline, e := index.AssignmentStats(index.Incumbent)
	if e != nil {
		return nil, e
	}
	entry := &feasibleEntry{panel: panel, program: program, coords: panel.Coordinates(), family: key}
	if strings.Join(entry.coords, "|") != strings.Join(program.Coordinates(), "|") {
		return nil, fmt.Errorf("coordinate ordering")
	}
	entry.baseline = make([]float64, len(entry.coords))
	at := map[string]int{}
	for i, k := range entry.coords {
		at[k] = i
	}
	for a, wearer := range w.req.Wearers {
		for k, v := range baseline[a] {
			if i, ok := at[wearer.WearerKey+"."+k]; ok {
				entry.baseline[i] -= v
			}
		}
		for j, k := range proto.StatKeys {
			entry.indices[a][j] = -1
			if i, ok := at[wearer.WearerKey+"."+k]; ok {
				entry.indices[a][j] = i
			}
		}
	}
	w.work.SpecializeSeconds += time.Since(start).Seconds()
	limit := w.entryLimit
	if limit == 0 {
		limit = 192
	}
	if len(w.order) >= limit {
		delete(w.entries, w.order[0])
		w.order = w.order[1:]
	}
	w.entries[key] = entry
	w.order = append(w.order, key)
	return entry, nil
}
func (w *feasibleWorld) objective(entry *feasibleEntry) proto.Objective {
	at := map[string]int{}
	for i, k := range entry.coords {
		at[k] = i
	}
	return func(s proto.State, gradient bool) (float64, [4][10]float64, error) {
		var g [4][10]float64
		dense := append([]float64(nil), entry.baseline...)
		rolls := s.Rolls()
		for a, wearer := range w.req.Wearers {
			for _, main := range s.Mains[a] {
				if i, ok := at[wearer.WearerKey+"."+main]; ok {
					dense[i] += proto.MainValues[main]
				}
			}
			for j, u := range rolls[a] {
				if i := entry.indices[a][j]; i >= 0 {
					dense[i] += u * proto.Values[j]
				}
			}
		}
		w.work.Formula++
		if gradient {
			w.work.Gradient++
			v, grad, _, e := entry.program.ValueGradient(dense)
			for a := range g {
				for j := range g[a] {
					if i := entry.indices[a][j]; i >= 0 {
						g[a][j] = grad[i] * proto.Values[j]
					}
				}
			}
			return v, g, e
		}
		v, e := entry.program.Evaluate(dense)
		return v, g, e
	}
}
func basicConfig(iterations int) proto.Config {
	return proto.Config{Budget: 45, Method: "spg", MaxIterations: iterations, LineSearch: true}
}
func initialMains() [4][5]string {
	var m [4][5]string
	for a := range m {
		m[a] = [5]string{"hp", "atk", "atk_percent", "atk_percent", "crit_rate"}
	}
	return m
}

// Full-input memoization within one frozen model. No entry survives this world;
// eviction only adds computation. Key includes all constraints/configuration,
// line identities, mains, upgrades, independent-start choice and operation.
func numericKey(operation, family string, state proto.State, cfg proto.Config, independent bool) [32]byte {
	b, err := json.Marshal(struct {
		Operation, Family string
		State             proto.State
		Config            proto.Config
		Independent       bool
	}{operation, family, state, cfg, independent})
	if err != nil {
		panic(err)
	}
	return sha256.Sum256(b)
}
func (w *feasibleWorld) remember(key [32]byte, r proto.Result) {
	if !w.numericReuse {
		return
	}
	if w.numericCache == nil {
		w.numericCache = map[[32]byte]proto.Result{}
	}
	if _, ok := w.numericCache[key]; ok {
		return
	}
	if len(w.numericOrder) >= 4096 {
		delete(w.numericCache, w.numericOrder[0])
		w.numericOrder = w.numericOrder[1:]
	}
	w.numericCache[key] = r
	w.numericOrder = append(w.numericOrder, key)
}
func (w *feasibleWorld) allocate(e *feasibleEntry, s proto.State, cfg proto.Config, independent bool) (proto.Result, error) {
	key := numericKey("allocate", e.family, s, cfg, independent)
	if w.numericReuse {
		if r, ok := w.numericCache[key]; ok {
			w.work.AllocationCacheHits++
			return r, nil
		}
	}
	w.work.AllocationAttempts++
	obj := w.objective(e)
	r, err := proto.Optimize(obj, s, cfg)
	if err != nil {
		return r, err
	}
	if independent {
		_, g, err := obj(s, true)
		if err != nil {
			return r, err
		}
		seed := proto.Seed(s.Mains, g, 0, 45)
		w.work.AllocationAttempts++
		alt, err := proto.Optimize(obj, seed, cfg)
		if err != nil {
			return r, err
		}
		if alt.Value > r.Value {
			r = alt
		}
	}
	w.remember(key, r)
	return r, nil
}

// Every admitted package gets its own allocation attempt. Neither the fixed
// score nor a gradient is used to discard a package. Main and line neighborhoods
// are heuristic finite searches, never global certificates.
func (w *feasibleWorld) refine(e *feasibleEntry, s proto.State) (proto.Result, error) {
	cfg := basicConfig(100)
	cfg.Polish = true
	key := numericKey("refine", e.family, s, cfg, true)
	if w.numericReuse {
		if r, ok := w.numericCache[key]; ok {
			w.work.RefineCacheHits++
			return r, nil
		}
	}
	r, err := w.allocate(e, s, cfg, true)
	if err != nil {
		return r, err
	}
	obj := w.objective(e)
	for sweep := 0; sweep < 3; sweep++ {
		before := r.Value
		line, err := proto.ImproveLines(obj, r.State, cfg)
		if err != nil {
			return r, err
		}
		if line.Value > r.Value {
			r = line
		}
		for a := 0; a < 4; a++ {
			for slot := 2; slot < 5; slot++ {
				anchor := r
				_, g, err := obj(anchor.State, true)
				if err != nil {
					return r, err
				}
				for _, main := range proto.MainChoices[slot] {
					if main == anchor.State.Mains[a][slot] {
						continue
					}
					candidate := proto.ReplaceMain(anchor.State, a, slot, main, g, 45)
					trial, err := w.allocate(e, candidate, basicConfig(45), true)
					if err != nil {
						return r, err
					}
					if trial.Value > r.Value+1e-8 {
						r = trial
					}
				}
			}
		}
		if r.Value <= before+1e-7 {
			break
		}
	}
	final, err := proto.Optimize(obj, r.State, cfg)
	if err == nil && final.Value > r.Value {
		r = final
	}
	if err == nil {
		w.remember(key, r)
	}
	return r, err
}
func (w *feasibleWorld) row(c feasibleCandidate) map[string]any {
	slots := []string{"flower", "plume", "sands", "goblet", "circlet"}
	rolls := c.state.Rolls()
	alloc := make([]theory.WearerAllocation, 4)
	for a, wearer := range w.req.Wearers {
		alloc[a] = theory.WearerAllocation{WearerKey: wearer.WearerKey, MainStats: map[string]string{}}
		for i, s := range slots {
			alloc[a].MainStats[s] = c.state.Mains[a][i]
		}
		for j, key := range proto.StatKeys {
			u := rolls[a][j]
			alloc[a].Substats = append(alloc[a].Substats, theory.StatAllocation{StatKey: key, RollUnits: u, StatValue: u * proto.Values[j]})
			alloc[a].SpentRollUnits += u
		}
		alloc[a].UnspentRollUnits = 45 - alloc[a].SpentRollUnits
	}
	b, _ := json.Marshal(theoryCandidateRow(w.req, theoryteams.Candidate{Packages: c.packages, Allocation: theory.Result{FormulaDPS: c.value, Allocations: alloc}, Source: "feasible_witness_prototype"}))
	var row map[string]any
	json.Unmarshal(b, &row)
	row["feasibility_witness"] = c.state
	row["formula_family"] = c.family
	row["uncertainty"] = w.metadata[theoryteams.Key(c.packages)]
	// Panel opaque reasons include source uncertainty flags. Keep one honestly
	// named combined list rather than pretending to have two disjoint classes.
	row["model_diagnostics"] = w.metadata[theoryteams.Key(c.packages)]
	delete(row, "opaque_reasons")
	row["allocation_stop_reason"] = "bounded_research_neighborhood"
	row["roll_stop_reason"] = "per_attempt_local_search_with_iteration_limits"
	for _, key := range []string{"rank", "context_sha256", "formula_evaluations", "infeasible_main_layouts", "main_layout_quota_stops", "main_layouts_attempted", "main_layouts_evaluated", "main_layouts_previewed"} {
		delete(row, key)
	}
	return row
}
func (w *feasibleWorld) search(options []domain.Package, initial proto.State) (feasibleCandidate, feasibleCandidate, feasibleCandidate, error) {
	p := [4]domain.Package{}
	entry, err := w.get(p)
	if err != nil || entry == nil {
		return feasibleCandidate{}, feasibleCandidate{}, feasibleCandidate{}, fmt.Errorf("none: %v", err)
	}
	r, err := w.refine(entry, initial)
	if err != nil {
		return feasibleCandidate{}, feasibleCandidate{}, feasibleCandidate{}, err
	}
	best := feasibleCandidate{p, r.State, r.Value, entry.family}
	none := best
	runner := none
	pool := map[string]feasibleCandidate{best.family: best}
	retain := func(c feasibleCandidate) {
		if prev, ok := pool[c.family]; !ok || c.value > prev.value {
			pool[c.family] = c
		}
		if c.value > best.value+1e-8 {
			best = c
		}
	}
	for sweep := 0; sweep < 3; sweep++ {
		before := best.value
		fmt.Printf("FEASIBLE_STAGE package_sweep %d dps=%.3f\n", sweep, best.value)
		for a := 0; a < 4; a++ {
			anchor := best
			cache := map[string]proto.Result{}
			for _, option := range options {
				trial := anchor.packages
				trial[a] = option
				e, err := w.get(trial)
				if err != nil {
					return best, runner, none, err
				}
				if e == nil {
					continue
				}
				result, ok := cache[e.family]
				if ok {
					w.work.FamilyReuses++
				} else {
					result, err = w.allocate(e, anchor.state, basicConfig(40), true)
					if err != nil {
						return best, runner, none, err
					}
					cache[e.family] = result
				}
				retain(feasibleCandidate{trial, result.State, result.Value, e.family})
			}
			e, err := w.get(best.packages)
			if err != nil {
				return best, runner, none, err
			}
			refined, err := w.refine(e, best.state)
			if err != nil {
				return best, runner, none, err
			}
			best.state, best.value = refined.State, refined.Value
			pool[best.family] = best
		}
		if best.value <= before+1e-7 {
			break
		}
	}
	// Complementary selected-package relocation/exchange: bounded neighborhood,
	// no claim to enumerate every pair of unselected packages.
	anchor := best
	seen := map[string]bool{}
	for a := 0; a < 4; a++ {
		for b := a + 1; b < 4; b++ {
			for _, kind := range []string{"swap", "a_to_b", "b_to_a"} {
				trial := anchor.packages
				switch kind {
				case "swap":
					trial[a], trial[b] = trial[b], trial[a]
				case "a_to_b":
					trial[b] = trial[a]
					trial[a] = domain.Package{}
				case "b_to_a":
					trial[a] = trial[b]
					trial[b] = domain.Package{}
				}
				key := theoryteams.Key(trial)
				if seen[key] {
					continue
				}
				seen[key] = true
				e, err := w.get(trial)
				if err != nil {
					return best, runner, none, err
				}
				if e == nil {
					continue
				}
				result, err := w.allocate(e, anchor.state, basicConfig(80), true)
				if err != nil {
					return best, runner, none, err
				}
				retain(feasibleCandidate{trial, result.State, result.Value, e.family})
			}
		}
	}
	e, err := w.get(best.packages)
	if err != nil {
		return best, runner, none, err
	}
	result, err := w.refine(e, best.state)
	if err != nil {
		return best, runner, none, err
	}
	best.state, best.value = result.State, result.Value
	ordered := []feasibleCandidate{}
	for family, c := range pool {
		if family != best.family {
			ordered = append(ordered, c)
		}
	}
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].value != ordered[j].value {
			return ordered[i].value > ordered[j].value
		}
		return theoryteams.Key(ordered[i].packages) < theoryteams.Key(ordered[j].packages)
	})
	if len(ordered) > 0 {
		runner = ordered[0]
	}
	if runner.family != best.family {
		e, err = w.get(runner.packages)
		if err != nil {
			return best, runner, none, err
		}
		if e != nil {
			result, err = w.refine(e, runner.state)
			if err != nil {
				return best, runner, none, err
			}
			runner.state, runner.value = result.State, result.Value
		}
	}
	if runner.value > best.value {
		best, runner = runner, best
	}
	return best, runner, none, nil
}
func difference(a, b feasibleWork) feasibleWork {
	return feasibleWork{a.Formula - b.Formula, a.Gradient - b.Gradient, a.Contexts - b.Contexts, a.Unavailable - b.Unavailable, a.FamilyReuses - b.FamilyReuses, a.AllocationAttempts - b.AllocationAttempts, a.AllocationCacheHits - b.AllocationCacheHits, a.RefineCacheHits - b.RefineCacheHits, a.ResolveSeconds - b.ResolveSeconds, a.SpecializeSeconds - b.SpecializeSeconds}
}

func TestTheoryFeasibleExperiment(t *testing.T) {
	req, sources, err := readSetSources(os.Getenv("GTT_FEASIBLE_REQUEST"), os.Getenv("GTT_FEASIBLE_SOURCES"))
	if err != nil {
		t.Fatal(err)
	}
	sha, err := contracts.CanonicalSHA256(req)
	if err != nil {
		t.Fatal(err)
	}
	req.Legality.TheorySearch = true
	req.Legality.FixedFourPiece = false
	req.Legality.FixedSetPackages = false
	req.Legality.MaxOffSetPiecesPerWearer = 0
	for i := range req.Wearers {
		req.Wearers[i].SelectedSetUID = ""
		req.Wearers[i].SelectedSets = nil
	}
	if err = req.ValidateTheory(); err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	original := [4]domain.Package{}
	empty := map[string][]setcontext.Set{}
	for a, w := range req.Wearers {
		for _, s := range base.Sets(w.WearerKey) {
			original[a].Sets = append(original[a].Sets, contracts.SetRequirement{SetUID: s.UID, Count: s.Count})
		}
		empty[w.WearerKey] = nil
	}
	base, err = base.Replace(empty)
	if err != nil {
		t.Fatal(err)
	}
	root := filepath.Join(os.Getenv("GTT_FEASIBLE_ROOT"), "capture")
	if err = os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, root)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	session, err := setcontext.NewSession(provider.Capture, len(base.Seeds()))
	if err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	h, err := session.Resolve(context.Background(), base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	captureSeconds := time.Since(start).Seconds()
	start = time.Now()
	factory := setcontext.ResearchNeutralFactory(h, sources)
	var model *setcontext.NeutralModel
	if !strings.HasPrefix(os.Getenv("GTT_FEASIBLE_PHASE"), "r2_") {
		model, err = factory()
		if err != nil {
			t.Fatal(err)
		}
	}
	modelSeconds := time.Since(start).Seconds()
	var rarity map[string]int
	blob, err := os.ReadFile(os.Getenv("GTT_FEASIBLE_RARITIES"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(blob, &rarity); err != nil {
		t.Fatal(err)
	}
	catalog := []domain.SetCapability{}
	excluded := []string{}
	for _, s := range sources.Sets {
		if rarity[s.Key] != 5 {
			excluded = append(excluded, s.Key)
			continue
		}
		catalog = append(catalog, domain.SetCapability{UID: s.Key, TwoPiece: true, FourPiece: s.FourPieceModeled})
	}
	options, err := theoryteams.Packages(catalog)
	if err != nil {
		t.Fatal(err)
	}
	world := &feasibleWorld{req: req, base: base, model: model, entries: map[string]*feasibleEntry{}, boundaries: map[string]bool{}, opaque: map[string]bool{}, metadata: map[string][]string{}}
	world.numericReuse = os.Getenv("GTT_FEASIBLE_NUMERIC_REUSE") == "1"
	initial := proto.Seed(initialMains(), [4][10]float64{}, 1, 45)
	// Check that the copied tables have not drifted from their production owner.
	rules := theory.RulesReceipt()
	for j, k := range proto.StatKeys {
		if rules["substat_max_values"].(map[string]float64)[k] != proto.Values[j] {
			t.Fatal("stat table drift", k)
		}
	}
	for k, v := range proto.MainValues {
		if rules["main_stat_values"].(map[string]float64)[k] != v {
			t.Fatal("main table drift", k)
		}
	}
	emitFeasible(map[string]any{"kind": "preparation", "capture_seconds": captureSeconds, "model_seconds": modelSeconds, "engine_calls": session.AttemptedCaptureMembers(), "packages_per_wearer": len(options), "rarity_excluded": excluded, "domain": "all five-star source catalog none, 2p, 2+2, modeled 4p"})
	if strings.HasPrefix(os.Getenv("GTT_FEASIBLE_PHASE"), "r2_") {
		if os.Getenv("GTT_FEASIBLE_PHASE") == "r2_bench" {
			ledger, ledgerErr := h.ResearchHunterScheduleLedger()
			if ledgerErr != nil {
				t.Fatal(ledgerErr)
			}
			emitFeasible(map[string]any{"kind": "r2_hunter_ledger", "members": ledger, "scope": "observed neutral health-event operands, not candidate-dependent health expressions"})
		}
		runTheoryRoundTwo(t, factory, req, base, original, options, initial)
		return
	}
	if os.Getenv("GTT_FEASIBLE_PHASE") == "combined" {
		var leader, runner, none feasibleCandidate
		for _, name := range []string{"combined_cold", "combined_repeat"} {
			start = time.Now()
			before := world.work
			leader, runner, none, err = world.search(options, initial)
			if err != nil {
				t.Fatal(err)
			}
			for _, c := range []feasibleCandidate{leader, runner, none} {
				if err = c.state.Validate(45, true); err != nil {
					t.Fatal(err)
				}
			}
			emitFeasible(map[string]any{"kind": "search", "name": name, "seconds": time.Since(start).Seconds(), "work": difference(world.work, before), "candidate": world.row(leader), "runner": world.row(runner), "none": world.row(none), "global_optimum": false, "full_cartesian_exhausted": false})
		}
		bounds, opaque := []string{}, []string{}
		for c := range world.boundaries {
			bounds = append(bounds, c)
		}
		for c := range world.opaque {
			opaque = append(opaque, c)
		}
		sort.Strings(bounds)
		sort.Strings(opaque)
		if math.IsNaN(leader.value) {
			t.Fatal("nonfinite result")
		}
		emitFeasible(map[string]any{"kind": "finalists", "candidates": []map[string]any{world.row(leader), world.row(runner), world.row(none)}, "boundaries": bounds, "opaque_reasons": opaque, "model_stats": world.model.Stats(), "formula_work": world.work, "verification_limit": 3, "scope": "frozen two-seed team formula; heuristic neighborhoods; infinite energy"})
		return
	}
	// Isolated step/rounding ablations use the same package tuple, mains and lines.
	entry, err := world.get(original)
	if err != nil || entry == nil {
		t.Fatal("original package unavailable", err)
	}
	obj := world.objective(entry)
	_, g, err := obj(initial, true)
	if err != nil {
		t.Fatal(err)
	}
	fixedSeed := proto.Seed(initial.Mains, g, 0, 45)
	var fixedBest proto.Result
	for _, name := range []string{"fixed_early_rounding", "fixed_late_rounding", "spg_late_rounding"} {
		cfg := basicConfig(150)
		cfg.Method = "fixed"
		cfg.GridEachStep = name == "fixed_early_rounding"
		if name == "spg_late_rounding" {
			cfg.Method = "spg"
		}
		cfg.Polish = true
		start = time.Now()
		before := world.work
		r, e := world.allocate(entry, fixedSeed, cfg, false)
		if e != nil {
			t.Fatal(e)
		}
		if r.Value > fixedBest.Value {
			fixedBest = r
		}
		emitFeasible(map[string]any{"kind": "ablation", "name": name, "seconds": time.Since(start).Seconds(), "work": difference(world.work, before), "dps": r.Value, "continuous_dps": r.ContinuousValue, "stop": r.Stop, "iterations": r.Iterations})
	}
	// Small set perturbation: compare reused state against both independent seeds.
	shifted := original
	shifted[2] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "tenacityofthemillelith", Count: 4}}}
	entry, err = world.get(shifted)
	if err != nil || entry == nil {
		t.Fatal("shift context", err)
	}
	for _, name := range []string{"reuse_no_correction", "cold_start", "warm_start", "warm_plus_independent"} {
		start = time.Now()
		before := world.work
		s := fixedSeed
		if name != "cold_start" {
			s = fixedBest.State
		}
		obj = world.objective(entry)
		v, _, e := obj(s, false)
		if e != nil {
			t.Fatal(e)
		}
		if name != "reuse_no_correction" {
			r, e := world.allocate(entry, s, basicConfig(150), name == "warm_plus_independent")
			if e != nil {
				t.Fatal(e)
			}
			v = r.Value
		}
		emitFeasible(map[string]any{"kind": "ablation", "name": name, "seconds": time.Since(start).Seconds(), "work": difference(world.work, before), "dps": v})
	}
	// Same source-context traversal and same starting point, only the repeated
	// numeric solve cache is toggled. Warm sequential wall time is secondary to
	// the exact reduction in formula evaluations; it is not a cold speedup claim.
	for _, name := range []string{"family_reuse_off", "family_reuse_on"} {
		start = time.Now()
		before := world.work
		cache := map[string]proto.Result{}
		best := math.Inf(-1)
		aliases := 0
		for _, option := range options {
			p := original
			p[1] = option
			e, err := world.get(p)
			if err != nil {
				t.Fatal(err)
			}
			if e == nil {
				continue
			}
			r, ok := cache[e.family]
			if name == "family_reuse_off" {
				ok = false
			}
			if ok {
				aliases++
				world.work.FamilyReuses++
			} else {
				r, err = world.allocate(e, fixedSeed, basicConfig(8), false)
				if err != nil {
					t.Fatal(err)
				}
				cache[e.family] = r
			}
			best = math.Max(best, r.Value)
		}
		emitFeasible(map[string]any{"kind": "ablation", "name": name, "seconds": time.Since(start).Seconds(), "work": difference(world.work, before), "dps": best, "duplicate_solves_avoided": aliases, "packages": len(options), "cache_scope": "one frozen model, one identical sweep input"})
	}
	emitFeasible(map[string]any{"kind": "ablation_summary", "model_stats": world.model.Stats(), "formula_work": world.work})
}
