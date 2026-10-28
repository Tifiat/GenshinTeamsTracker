package main

// Round two owns independent cold searches and explicitly labeled transfer
// experiments. It never treats a prior completed request as a new-input solve.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"hash"
	"math"
	"os"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

type r2Work struct {
	Requests, PositiveHits, NegativeHits, NumericHits, NumericMisses       int
	ContextEvictions, NumericEvictions, MainTrials, PairTrials, LineTrials int
	ResolveCachePeak, NumericCachePeak, UnseenPairTrials                   int
	FastCalls, ColdWholeCalls, CorrectedFamilies                           int
	FastHits, AlternatingHits, AlternatingMisses, AlternatingFresh         int
	BothChangedPairTrials, NeitherPreviouslySelectedPairTrials             int
}
type r2World struct {
	*feasibleWorld
	reuse        bool
	contexts     map[string]*feasibleEntry
	contextOrder []string
	numeric      map[[32]byte]proto.JointResult
	numericOrder [][32]byte
	extra        r2Work
	modelSeconds float64
	route        hash.Hash
	stages       map[string]float64
}

func newR2World(factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, reuse bool) (*r2World, error) {
	started := time.Now()
	m, err := factory()
	if err != nil {
		return nil, err
	}
	w := &feasibleWorld{req: req, base: base, model: m, entries: map[string]*feasibleEntry{}, boundaries: map[string]bool{}, opaque: map[string]bool{}, metadata: map[string][]string{}, entryLimit: 768, numericReuse: reuse}
	return &r2World{feasibleWorld: w, reuse: reuse, contexts: map[string]*feasibleEntry{}, numeric: map[[32]byte]proto.JointResult{}, modelSeconds: time.Since(started).Seconds(), route: sha256.New(), stages: map[string]float64{}}, nil
}

// Keys are complete target identities inside an immutable request/model/code
// universe. Neither successful nor unavailable results survive this world.
// Errors are not cached. Bounded FIFO eviction only repeats work.
func (w *r2World) get(p [4]domain.Package) (*feasibleEntry, error) {
	w.extra.Requests++
	key := theoryteams.Key(p)
	fmt.Fprintln(w.route, key)
	if w.reuse {
		if e, ok := w.contexts[key]; ok {
			if e == nil {
				w.extra.NegativeHits++
			} else {
				w.extra.PositiveHits++
			}
			return e, nil
		}
	}
	e, err := w.feasibleWorld.get(p)
	if err != nil {
		return nil, err
	}
	if w.reuse {
		if len(w.contextOrder) >= 4096 {
			delete(w.contexts, w.contextOrder[0])
			w.contextOrder = w.contextOrder[1:]
			w.extra.ContextEvictions++
		}
		w.contexts[key] = e
		w.contextOrder = append(w.contextOrder, key)
		if len(w.contexts) > w.extra.ResolveCachePeak {
			w.extra.ResolveCachePeak = len(w.contexts)
		}
	}
	return e, nil
}

func (w *r2World) solve(e *feasibleEntry, s proto.State, cfg proto.Config, joint proto.JointConfig) (proto.JointResult, error) {
	b, _ := json.Marshal(struct {
		Family string
		State  proto.State
		Config proto.Config
		Joint  proto.JointConfig
	}{e.family, s, cfg, joint})
	key := sha256.Sum256(b)
	if w.reuse {
		if r, ok := w.numeric[key]; ok {
			w.extra.NumericHits++
			return r, nil
		}
	}
	w.extra.NumericMisses++
	r, err := proto.JointOptimize(w.objective(e), s, cfg, joint)
	if err != nil {
		return r, err
	}
	if err = r.State.Validate(45, true); err != nil {
		return r, err
	}
	w.extra.MainTrials += r.SingleMainCandidates
	w.extra.PairTrials += r.JointMainCandidates
	w.extra.LineTrials += r.LineCandidates
	if w.reuse {
		if len(w.numericOrder) >= 4096 {
			delete(w.numeric, w.numericOrder[0])
			w.numericOrder = w.numericOrder[1:]
			w.extra.NumericEvictions++
		}
		w.numeric[key] = r
		w.numericOrder = append(w.numericOrder, key)
		if len(w.numeric) > w.extra.NumericCachePeak {
			w.extra.NumericCachePeak = len(w.numeric)
		}
	}
	return r, nil
}
func r2Wide() proto.JointConfig {
	return proto.JointConfig{MaxPasses: 2, InnerIterations: 16, MaxMainPairs: 96, MaxLineCandidates: 160}
}

// A broad fixed-bonus control first runs the existing complete main sweep from
// this run's own input, then attempts the corrected coupled neighborhoods.
// Retaining its feasible result prevents a bounded new neighborhood from
// silently worsening the already found fixed-bonus quality.
func (w *r2World) whole(e *feasibleEntry, s proto.State) (proto.JointResult, error) {
	before := w.work.Formula
	prior, err := w.feasibleWorld.refine(e, s)
	if err != nil {
		return proto.JointResult{}, err
	}
	r, err := w.solve(e, prior.State, basicConfig(80), r2Wide())
	if err != nil {
		return r, err
	}
	cfg := basicConfig(120)
	cfg.Polish = true
	last, err := proto.Optimize(w.objective(e), r.State, cfg)
	if err != nil {
		return r, err
	}
	r.Evaluations = w.work.Formula - before
	if last.Value > r.Value {
		r.State, r.Value = last.State, last.Value
	}
	return r, nil
}
func r2Screen(actor, iterations int) proto.JointConfig {
	s := proto.JointConfig{MaxPasses: 1, InnerIterations: iterations, DisableMainPairs: true, DisableLines: true, DisableIndependentSeeds: true}
	if actor >= 0 {
		s.Actors[actor] = true
	}
	return s
}

// Package screening includes every legal single main and every simultaneous
// goblet/circlet alternative for the changed wearer. It still has a bounded
// upgrade solve and does not claim exhaustive multi-wearer/main/line coverage.
func r2PackageScreen(actor, iterations int) proto.JointConfig {
	s := r2Screen(actor, iterations)
	s.DisableMainPairs = false
	return s
}

const r2FastMethod = "r2_fast_coordinate4_v2"
const r2AlternatingMethod = "r2_alternating_complete_v1"

type r2FastPlan struct {
	Config proto.Config
	Search proto.FastConfig
}

func r2InitialFastPlan() r2FastPlan {
	return r2FastPlan{basicConfig(100), proto.FastConfig{Passes: 2, InnerIterations: 4}}
}

type r2AlternatingPlan struct {
	FirstMethod string
	First       r2FastPlan
	LinesConfig proto.Config
	LinesSearch proto.SlotLineConfig
	LastConfig  proto.Config
	LastSearch  proto.FastConfig
}

func r2CompleteAlternatingPlan() r2AlternatingPlan {
	return r2AlternatingPlan{
		FirstMethod: r2FastMethod,
		First:       r2InitialFastPlan(),
		LinesConfig: basicConfig(100),
		LinesSearch: proto.SlotLineConfig{Passes: 2, InnerIterations: 4},
		LastConfig:  basicConfig(120),
		LastSearch:  proto.FastConfig{Passes: 2, InnerIterations: 12, MainPairs: true},
	}
}

// A family identifies source-validated arithmetic inside this immutable world.
// Coordinates, origin, mapping, complete start, domain and every solve setting
// also participate, so a different initial witness or reference origin misses.
func r2CompleteKey(method string, e *feasibleEntry, start proto.State, settings any) ([32]byte, error) {
	var empty [32]byte
	if e == nil || e.family == "" || method == "" {
		return empty, fmt.Errorf("complete numeric key needs a resolved family and method")
	}
	payload := struct {
		Method      string
		Family      string
		Coordinates []string
		Baseline    []float64
		Indices     [4][10]int
		Start       proto.State
		Settings    any
		StatKeys    [10]string
		StatValues  [10]float64
		MainValues  map[string]float64
		MainChoices [5][]string
	}{method, e.family, e.coords, e.baseline, e.indices, start, settings,
		proto.StatKeys, proto.Values, proto.MainValues, proto.MainChoices}
	b, err := json.Marshal(payload)
	if err != nil {
		return empty, err
	}
	return sha256.Sum256(b), nil
}

// Reuse a complete valid solve only within the existing 4096-entry world cache.
// State contains value arrays, so both insertion and retrieval are independent
// copies. A hit reports zero fresh evaluations while preserving the found score.
func r2MemoizedResult(w *feasibleWorld, key [32]byte, budget float64, solve func() (proto.Result, error)) (proto.Result, bool, error) {
	if w.numericReuse {
		if r, ok := w.numericCache[key]; ok {
			r.Evaluations = 0
			return r, true, nil
		}
	}
	r, err := solve()
	if err != nil {
		return r, false, err
	}
	if err := r.State.Validate(budget, true); err != nil {
		return r, false, err
	}
	if math.IsNaN(r.Value) || math.IsInf(r.Value, 0) {
		return r, false, fmt.Errorf("non-finite completed solve value")
	}
	w.remember(key, r)
	return r, false, nil
}

func (w *r2World) fast(e *feasibleEntry, s proto.State) (proto.Result, error) {
	plan := r2InitialFastPlan()
	key, err := r2CompleteKey(r2FastMethod, e, s, plan)
	if err != nil {
		return proto.Result{}, err
	}
	result, hit, err := r2MemoizedResult(w.feasibleWorld, key, plan.Config.Budget, func() (proto.Result, error) {
		w.extra.FastCalls++
		r, err := proto.FastWhole(w.objective(e), s, plan.Config, plan.Search)
		if err != nil {
			return proto.Result{}, err
		}
		w.extra.MainTrials += r.SingleMainCandidates
		return proto.Result{State: r.State, Value: r.Value, ContinuousValue: r.ContinuousValue, Evaluations: r.Evaluations, Stop: r.Stop}, nil
	})
	if hit {
		w.extra.FastHits++
	}
	return result, err
}

// One additional fixed-bonus candidate: cheap mains, two sequential artifact
// line sweeps, then revisit all mains and all goblet/circlet pairs. Its own
// cold measurements remain separate from the broad quality control.
func (w *r2World) alternating(e *feasibleEntry, s proto.State) (proto.Result, error) {
	plan := r2CompleteAlternatingPlan()
	key, err := r2CompleteKey(r2AlternatingMethod, e, s, plan)
	if err != nil {
		return proto.Result{}, err
	}
	result, hit, err := r2MemoizedResult(w.feasibleWorld, key, plan.LastConfig.Budget, func() (proto.Result, error) {
		w.extra.AlternatingFresh++
		before := w.work.Formula
		first, err := w.fast(e, s)
		if err != nil {
			return proto.Result{}, err
		}
		lines, err := proto.SlotLines(w.objective(e), first.State, plan.LinesConfig, plan.LinesSearch)
		if err != nil {
			return proto.Result{}, err
		}
		w.extra.LineTrials += lines.Candidates
		w.extra.FastCalls++
		last, err := proto.FastWhole(w.objective(e), lines.State, plan.LastConfig, plan.LastSearch)
		if err != nil {
			return proto.Result{}, err
		}
		w.extra.MainTrials += last.SingleMainCandidates
		w.extra.PairTrials += last.PairCandidates
		return proto.Result{State: last.State, Value: last.Value, ContinuousValue: last.ContinuousValue, Evaluations: w.work.Formula - before, Stop: "alternating_bounded_whole_build"}, nil
	})
	if hit {
		w.extra.AlternatingHits++
	} else {
		w.extra.AlternatingMisses++
	}
	return result, err
}
func r2Package(key string) domain.Package {
	return domain.Package{Sets: []contracts.SetRequirement{{SetUID: key, Count: 4}}}
}
func r2Tuple() [4]domain.Package {
	return [4]domain.Package{r2Package("noblesseoblige"), r2Package("obsidiancodex"), r2Package("tenacityofthemillelith"), r2Package("scrolloftheheroofcindercity")}
}
func r2Sorted(pool map[string]feasibleCandidate) []feasibleCandidate {
	rows := make([]feasibleCandidate, 0, len(pool))
	for _, c := range pool {
		rows = append(rows, c)
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].value != rows[j].value {
			return rows[i].value > rows[j].value
		}
		return theoryteams.Key(rows[i].packages) < theoryteams.Key(rows[j].packages)
	})
	return rows
}
func r2Stats(r proto.JointResult) proto.JointResult { r.State = proto.State{}; return r }

// Explicit outside-shortlist audit: start from a newly solved rich baseline,
// retain different objective families whose corrected singleton loses, then
// combine two such never-selected singletons. No previously found allocation
// is loaded. This diagnostic is separate from the measured r2_search route.
func (w *r2World) nonwinningPairs(t *testing.T, options []domain.Package, initial proto.State) {
	started := time.Now()
	packages := r2Tuple()
	entry, err := w.get(packages)
	if err != nil || entry == nil {
		t.Fatal("pair audit baseline unavailable", err)
	}
	r, err := w.whole(entry, initial)
	if err != nil {
		t.Fatal(err)
	}
	anchor := feasibleCandidate{packages, r.State, r.Value, entry.family}
	best := anchor
	var choices [4][]feasibleCandidate
	for actor := 0; actor < 4; actor++ {
		seen := map[string]bool{anchor.family: true}
		losers := map[string]feasibleCandidate{}
		winners := 0
		for _, option := range options {
			trial := packages
			trial[actor] = option
			e, getErr := w.get(trial)
			if getErr != nil {
				t.Fatal(getErr)
			}
			if e == nil || seen[e.family] {
				continue
			}
			seen[e.family] = true
			result, solveErr := w.solve(e, anchor.state, basicConfig(40), r2PackageScreen(actor, 4))
			if solveErr != nil {
				t.Fatal(solveErr)
			}
			c := feasibleCandidate{trial, result.State, result.Value, e.family}
			if c.value > anchor.value+1e-8 {
				winners++
				if c.value > best.value {
					best = c
				}
			} else {
				losers[e.family] = c
			}
		}
		ordered := r2Sorted(losers)
		if len(ordered) > 2 {
			ordered = ordered[:2]
		}
		choices[actor] = ordered
		emitFeasible(map[string]any{"kind": "r2_nonwinning_singletons", "actor": actor, "distinct_families": len(seen), "nonwinning_families": len(losers), "winning_families": winners, "retained_nonwinners": len(ordered)})
	}
	pairs, improvements := 0, 0
	for a := 0; a < 4; a++ {
		for b := a + 1; b < 4; b++ {
			for _, ca := range choices[a] {
				for _, cb := range choices[b] {
					trial := packages
					trial[a], trial[b] = ca.packages[a], cb.packages[b]
					e, getErr := w.get(trial)
					if getErr != nil {
						t.Fatal(getErr)
					}
					if e == nil {
						continue
					}
					result, solveErr := w.solve(e, anchor.state, basicConfig(50), r2PackageScreen(-1, 4))
					if solveErr != nil {
						t.Fatal(solveErr)
					}
					pairs++
					if result.Value > anchor.value+1e-8 {
						improvements++
					}
					c := feasibleCandidate{trial, result.State, result.Value, e.family}
					if c.value > best.value {
						best = c
					}
					emitFeasible(map[string]any{"kind": "r2_nonwinning_pair", "actors": [2]int{a, b}, "singleton_dps": [2]float64{ca.value, cb.value}, "baseline_dps": anchor.value, "candidate": w.row(c)})
				}
			}
		}
	}
	if pairs == 0 {
		t.Fatal("nonwinning-pair audit exercised no pairs")
	}
	rows := []map[string]any{}
	if best.value > anchor.value+1e-8 {
		e, getErr := w.get(best.packages)
		if getErr != nil {
			t.Fatal(getErr)
		}
		cold, solveErr := w.whole(e, initial)
		if solveErr != nil {
			t.Fatal(solveErr)
		}
		warm, solveErr := w.alternating(e, best.state)
		if solveErr != nil {
			t.Fatal(solveErr)
		}
		if cold.Value > best.value {
			best.state, best.value = cold.State, cold.Value
		}
		if warm.Value > best.value {
			best.state, best.value = warm.State, warm.Value
		}
		rows = append(rows, w.row(best))
	}
	emitFeasible(map[string]any{"kind": "r2_unseen_pairs", "seconds": time.Since(started).Seconds(), "model_seconds": w.modelSeconds, "work": w.work, "extra": w.extra, "pairs_of_two_nonwinning_singletons": pairs, "improving_pairs": improvements, "baseline": w.row(anchor), "best": w.row(best), "global_optimum": false, "prior_solution_cache": false, "scope": "two best distinct nonwinning singleton families per wearer; bounded outside-shortlist audit"})
	emitFeasible(map[string]any{"kind": "finalists", "candidates": rows, "scope": "only a new improvement, if found; no duplicate control verification"})
}

func (w *r2World) search(options []domain.Package, initial proto.State, iterations int) (feasibleCandidate, feasibleCandidate, feasibleCandidate, error) {
	stageStart := time.Now()
	p := [4]domain.Package{}
	e, err := w.get(p)
	if err != nil || e == nil {
		return feasibleCandidate{}, feasibleCandidate{}, feasibleCandidate{}, fmt.Errorf("none unavailable: %v", err)
	}
	r, err := w.whole(e, initial)
	if err != nil {
		return feasibleCandidate{}, feasibleCandidate{}, feasibleCandidate{}, err
	}
	best := feasibleCandidate{p, r.State, r.Value, e.family}
	none := best
	w.extra.ColdWholeCalls++
	coldNone := best
	w.stages["initial_none"] = time.Since(stageStart).Seconds()
	stageStart = time.Now()
	pool := map[string]feasibleCandidate{theoryteams.Key(p): best}
	var selected [4]map[string]bool
	for actor := range selected {
		selected[actor] = map[string]bool{p[actor].Key(): true}
	}
	retain := func(c feasibleCandidate) {
		key := theoryteams.Key(c.packages)
		if old, ok := pool[key]; !ok || c.value > old.value {
			pool[key] = c
		}
		if c.value > best.value+1e-8 {
			best = c
			for actor := range selected {
				selected[actor][c.packages[actor].Key()] = true
			}
		}
		if key == theoryteams.Key([4]domain.Package{}) && c.value > none.value {
			none = c
		}
	}
	var choices [4][]domain.Package
	for sweep := 0; sweep < 3; sweep++ {
		before := best.value
		fmt.Printf("FEASIBLE_STAGE r2_sweep %d dps=%.3f\n", sweep, best.value)
		for a := 0; a < 4; a++ {
			anchor := best
			families := map[string]proto.JointResult{}
			local := map[string]feasibleCandidate{}
			for _, option := range options {
				trial := anchor.packages
				trial[a] = option
				entry, err := w.get(trial)
				if err != nil {
					return best, best, none, err
				}
				if entry == nil {
					continue
				}
				result, ok := families[entry.family]
				if !ok {
					result, err = w.solve(entry, anchor.state, basicConfig(40), r2PackageScreen(a, iterations))
					if err != nil {
						return best, best, none, err
					}
					families[entry.family] = result
				} else {
					w.work.FamilyReuses++
				}
				candidate := feasibleCandidate{trial, result.State, result.Value, entry.family}
				retain(candidate)
				if old, ok := local[entry.family]; !ok || candidate.value > old.value {
					local[entry.family] = candidate
				}
			}
			ordered := r2Sorted(local)
			choices[a] = nil
			// Refine several objective families with all actors' own mains,
			// not only the incumbent. Screening remains a measured heuristic.
			for i, c := range ordered {
				if i >= 3 {
					break
				}
				choices[a] = append(choices[a], c.packages[a])
				entry, err := w.get(c.packages)
				if err != nil {
					return best, best, none, err
				}
				result, err := w.fast(entry, c.state)
				if err != nil {
					return best, best, none, err
				}
				retain(feasibleCandidate{c.packages, result.State, result.Value, entry.family})
			}
		}
		if best.value <= before+1e-7 {
			break
		}
	}
	// New pairs can contain packages not selected by either singleton. This
	// finite pool is explicitly not the Cartesian product of the full catalog.
	w.stages["package_sweeps"] = time.Since(stageStart).Seconds()
	stageStart = time.Now()
	anchor := best
	seen := map[string]bool{}
	for a := 0; a < 4; a++ {
		for b := a + 1; b < 4; b++ {
			for _, pa := range choices[a] {
				for _, pb := range choices[b] {
					trial := anchor.packages
					trial[a] = pa
					trial[b] = pb
					key := theoryteams.Key(trial)
					if seen[key] || key == theoryteams.Key(anchor.packages) {
						continue
					}
					seen[key] = true
					entry, err := w.get(trial)
					if err != nil {
						return best, best, none, err
					}
					if entry == nil {
						continue
					}
					w.extra.UnseenPairTrials++
					if pa.Key() != anchor.packages[a].Key() && pb.Key() != anchor.packages[b].Key() {
						w.extra.BothChangedPairTrials++
					}
					if !selected[a][pa.Key()] && !selected[b][pb.Key()] {
						w.extra.NeitherPreviouslySelectedPairTrials++
					}
					result, err := w.solve(entry, anchor.state, basicConfig(50), r2PackageScreen(-1, iterations))
					if err != nil {
						return best, best, none, err
					}
					retain(feasibleCandidate{trial, result.State, result.Value, entry.family})
				}
			}
		}
	}
	// Correct three retained objective families, plus the two predeclared
	// Furina controls and none. Every cold correction starts from initial,
	// never a solution imported from another completed run. This guarantees
	// retention of the cold control only for these corrected families.
	w.stages["unselected_package_pairs"] = time.Since(stageStart).Seconds()
	stageStart = time.Now()
	emitFeasible(map[string]any{"kind": "r2_search_screen", "reuse": w.reuse, "work": w.work, "extra": w.extra, "leader": w.row(best)})
	shortlist := []feasibleCandidate{}
	families := map[string]bool{}
	for _, c := range r2Sorted(pool) {
		if families[c.family] {
			continue
		}
		families[c.family] = true
		shortlist = append(shortlist, c)
		if len(shortlist) == 3 {
			break
		}
	}
	controls := [][4]domain.Package{r2Tuple(), r2Tuple(), {}}
	controls[1][2] = r2Package("goldentroupe")
	for _, packages := range controls {
		entry, getErr := w.get(packages)
		if getErr != nil || entry == nil {
			return best, best, none, fmt.Errorf("required cold control unavailable: %v", getErr)
		}
		if families[entry.family] {
			continue
		}
		families[entry.family] = true
		c, ok := pool[theoryteams.Key(packages)]
		if !ok {
			value, _, evalErr := w.objective(entry)(initial, false)
			if evalErr != nil {
				return best, best, none, evalErr
			}
			c = feasibleCandidate{packages, initial, value, entry.family}
		}
		shortlist = append(shortlist, c)
	}
	corrected := map[string]feasibleCandidate{}
	for _, c := range shortlist {
		started := time.Now()
		before := w.work
		entry, getErr := w.get(c.packages)
		if getErr != nil {
			return best, best, none, getErr
		}
		cold := coldNone
		if entry.family != coldNone.family {
			w.extra.ColdWholeCalls++
			result, solveErr := w.whole(entry, initial)
			if solveErr != nil {
				return best, best, none, solveErr
			}
			cold = feasibleCandidate{c.packages, result.State, result.Value, entry.family}
		}
		warm, solveErr := w.alternating(entry, c.state)
		if solveErr != nil {
			return best, best, none, solveErr
		}
		candidate := c
		if cold.value > candidate.value {
			candidate = cold
		}
		if warm.Value > candidate.value {
			candidate = feasibleCandidate{c.packages, warm.State, warm.Value, entry.family}
		}
		retain(candidate)
		corrected[entry.family] = candidate
		w.extra.CorrectedFamilies++
		emitFeasible(map[string]any{"kind": "r2_search_correction", "reuse": w.reuse, "seconds": time.Since(started).Seconds(), "work": difference(w.work, before), "screen_dps": c.value, "cold_dps": cold.value, "warm_corrected_dps": warm.Value, "candidate": w.row(candidate)})
	}
	// Rank the corrected families. The output competitor is the strongest
	// retained different objective family; it is not a catalog top-three claim.
	ordered := r2Sorted(corrected)
	w.stages["cold_and_warm_correction"] = time.Since(stageStart).Seconds()
	if len(ordered) < 2 {
		return best, best, none, fmt.Errorf("fewer than two corrected families")
	}
	return ordered[0], ordered[1], none, nil
}

func runTheoryRoundTwo(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	newWorld := func(reuse bool) *r2World {
		w, err := newR2World(factory, req, base, reuse)
		if err != nil {
			t.Fatal(err)
		}
		return w
	}
	if os.Getenv("GTT_FEASIBLE_PHASE") == "r2_pairs" {
		newWorld(true).nonwinningPairs(t, options, initial)
		return
	}
	fixed := func(w *r2World, p [4]domain.Package, s proto.State, j proto.JointConfig, name string) feasibleCandidate {
		started := time.Now()
		before := w.work
		e, err := w.get(p)
		if err != nil {
			t.Fatal(err)
		}
		if e == nil {
			emitFeasible(map[string]any{"kind": "r2_fixed", "name": name, "available": false, "seconds": time.Since(started).Seconds(), "boundaries": w.boundaries})
			return feasibleCandidate{}
		}
		r, err := w.whole(e, s)
		if err != nil {
			t.Fatal(err)
		}
		c := feasibleCandidate{p, r.State, r.Value, e.family}
		emitFeasible(map[string]any{"kind": "r2_fixed", "name": name, "available": true, "seconds": time.Since(started).Seconds(), "work": difference(w.work, before), "joint": r2Stats(r), "candidate": w.row(c)})
		return c
	}
	if os.Getenv("GTT_FEASIBLE_PHASE") == "r2_fast" {
		leader := r2Tuple()
		troupe := leader
		troupe[2] = r2Package("goldentroupe")
		attack := leader
		attack[1] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "gladiatorsfinale", Count: 2}, {SetUID: "shimenawasreminiscence", Count: 2}}}
		hunter := leader
		hunter[1] = r2Package("marechausseehunter")
		cases := []struct {
			name   string
			p      [4]domain.Package
			approx bool
		}{{"tenacity", leader, false}, {"troupe", troupe, false}, {"chasca_attack_2plus2", attack, false}, {"hunter_observed_schedule", hunter, true}}
		settings := []struct {
			name string
			cfg  proto.FastConfig
		}{{"coordinate4", proto.FastConfig{Passes: 2, InnerIterations: 4}}, {"coordinate12", proto.FastConfig{Passes: 2, InnerIterations: 12}}, {"pairs_lines", proto.FastConfig{Passes: 2, InnerIterations: 12, MainPairs: true, LinePasses: 2}}}
		var nearSource feasibleCandidate
		for _, test := range cases {
			for _, setting := range settings {
				w := newWorld(true)
				w.hunterObserved = test.approx
				start := time.Now()
				e, err := w.get(test.p)
				if err != nil || e == nil {
					t.Fatal("fast control unavailable", test.name, err)
				}
				before := w.work
				r, err := proto.FastWhole(w.objective(e), initial, basicConfig(120), setting.cfg)
				if err != nil {
					t.Fatal(err)
				}
				c := feasibleCandidate{test.p, r.State, r.Value, e.family}
				stats := r
				stats.State = proto.State{}
				emitFeasible(map[string]any{"kind": "r2_fast", "name": test.name + "_" + setting.name, "seconds": time.Since(start).Seconds(), "model_seconds": w.modelSeconds, "work": difference(w.work, before), "solver": stats, "candidate": w.row(c), "unresolved_graph": e.program.HasUnresolvedDependencies(), "prior_result_cache": false})
				if test.name == "troupe" && setting.name == "pairs_lines" {
					nearSource = c
				}
			}
		}
		// A close transfer supplements the deliberately large crit-bonus change
		// from r2_bench; no prior completed request supplies the source solution.
		var wideValue float64
		for _, radius := range []float64{25, 1, 4, 12} {
			w := newWorld(true)
			e, err := w.get(leader)
			if err != nil || e == nil {
				t.Fatal(err)
			}
			cfg := basicConfig(100)
			cfg.Polish = true
			start := time.Now()
			before := w.work
			r, err := proto.WindowOptimize(w.objective(e), nearSource.state, cfg, proto.WindowConfig{Radius: radius})
			if err != nil {
				t.Fatal(err)
			}
			if radius == 25 {
				wideValue = r.Value
			}
			emitFeasible(map[string]any{"kind": "r2_near_window", "name": fmt.Sprintf("troupe_to_tenacity_radius%.0f", radius), "seconds": time.Since(start).Seconds(), "work": difference(w.work, before), "dps": r.Value, "loss_vs_unrestricted": wideValue - r.Value, "stop": r.Stop, "source_family": nearSource.family, "target_family": e.family})
		}
		return
	}
	if os.Getenv("GTT_FEASIBLE_PHASE") == "r2_bench" {
		leader := r2Tuple()
		troupe := leader
		troupe[2] = r2Package("goldentroupe")
		attack := leader
		attack[1] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "gladiatorsfinale", Count: 2}, {SetUID: "shimenawasreminiscence", Count: 2}}}
		cases := []struct {
			name string
			p    [4]domain.Package
		}{{"original", original}, {"tenacity", leader}, {"troupe", troupe}, {"chasca_attack_2plus2", attack}}
		// Same fixed feasible seed, different independent numerical methods.
		for _, method := range []string{"slot_spg", "aggregate_flow", "quarter_exchange"} {
			w := newWorld(true)
			e, err := w.get(leader)
			if err != nil || e == nil {
				t.Fatal("fixed control unavailable", err)
			}
			obj := w.objective(e)
			_, g, err := obj(initial, true)
			if err != nil {
				t.Fatal(err)
			}
			seed := proto.Seed(initial.Mains, g, 0, 45)
			start := time.Now()
			before := w.work
			var state proto.State
			var value float64
			var stop string
			if method == "aggregate_flow" {
				r, err := proto.OptimizeAggregate(proto.AggregateObjective(obj), seed, proto.AggregateConfig{Budget: 45, MaxIterations: 100, Polish: true})
				if err != nil {
					t.Fatal(err)
				}
				state, value, stop = r.State, r.Value, r.Stop
			} else if method == "quarter_exchange" {
				// The discrete method requires an actual quarter-grid seed.
				r, err := proto.QuarterExchange(obj, seed, proto.QuarterExchangeConfig{Budget: 45, MaxMoves: 100, MaxEvaluations: 50000})
				if err != nil {
					t.Fatal(err)
				}
				state, value, stop = r.State, r.Value, r.Stop
			} else {
				cfg := basicConfig(150)
				cfg.Polish = true
				r, err := proto.Optimize(obj, seed, cfg)
				if err != nil {
					t.Fatal(err)
				}
				state, value, stop = r.State, r.Value, r.Stop
			}
			if err := state.Validate(45, true); err != nil {
				t.Fatal(err)
			}
			emitFeasible(map[string]any{"kind": "r2_numeric", "name": method, "seconds": time.Since(start).Seconds(), "work": difference(w.work, before), "dps": value, "stop": stop, "feasibility_witness": state})
		}
		cold := make([]feasibleCandidate, 0, len(cases))
		for _, test := range cases {
			w := newWorld(true)
			cold = append(cold, fixed(w, test.p, initial, r2Wide(), "cold_"+test.name))
		}
		for i := 1; i < len(cases); i++ {
			source := cold[i-1]
			target := cases[i]
			if source.value == 0 || cold[i].value == 0 {
				continue
			}
			for _, steps := range []int{4, 12} {
				w := newWorld(true)
				entry, err := w.get(target.p)
				if err != nil {
					t.Fatal(err)
				}
				if entry.family == source.family {
					emitFeasible(map[string]any{"kind": "r2_transfer_skipped", "name": target.name, "reason": "same objective family; no changed-input transfer claim"})
					continue
				}
				start := time.Now()
				before := w.work
				old, _, err := w.objective(entry)(source.state, false)
				if err != nil {
					t.Fatal(err)
				}
				r, err := w.solve(entry, source.state, basicConfig(40), r2Screen(-1, steps))
				if err != nil {
					t.Fatal(err)
				}
				c := feasibleCandidate{target.p, r.State, r.Value, entry.family}
				emitFeasible(map[string]any{"kind": "r2_transfer", "name": fmt.Sprintf("%s_to_%s_steps%d", cases[i-1].name, target.name, steps), "seconds": time.Since(start).Seconds(), "work": difference(w.work, before), "uncorrected_dps": old, "cold_control_dps": cold[i].value, "loss_dps": cold[i].value - c.value, "source_family": source.family, "target_family": entry.family, "joint": r2Stats(r), "candidate": w.row(c)})
			}
		}
		// Fixed-layout trust ranges on a genuinely changed crit/attack bonus.
		// Their reference is an unrestricted solve of exactly that same layout;
		// the independent whole-main control above is a separate, larger domain.
		windowSource := cold[1]
		windowWorld := newWorld(true)
		windowEntry, windowErr := windowWorld.get(attack)
		if windowErr != nil || windowEntry == nil {
			t.Fatal("window target unavailable", windowErr)
		}
		windowCfg := basicConfig(100)
		windowCfg.Polish = true
		windowStart := time.Now()
		windowBefore := windowWorld.work
		wide, windowErr := proto.Optimize(windowWorld.objective(windowEntry), windowSource.state, windowCfg)
		if windowErr != nil {
			t.Fatal(windowErr)
		}
		emitFeasible(map[string]any{"kind": "r2_window", "name": "unrestricted_fixed_layout", "seconds": time.Since(windowStart).Seconds(), "work": difference(windowWorld.work, windowBefore), "dps": wide.Value, "stop": wide.Stop, "source_family": windowSource.family, "target_family": windowEntry.family})
		for _, setting := range []struct {
			radius float64
			expand int
			probe  bool
		}{{1, 0, false}, {4, 0, false}, {12, 0, false}, {1, 5, true}} {
			windowWorld = newWorld(true)
			windowEntry, windowErr = windowWorld.get(attack)
			if windowErr != nil {
				t.Fatal(windowErr)
			}
			windowStart = time.Now()
			windowBefore = windowWorld.work
			r, err := proto.WindowOptimize(windowWorld.objective(windowEntry), windowSource.state, windowCfg, proto.WindowConfig{Radius: setting.radius, MaxExpansions: setting.expand, ProbeWide: setting.probe})
			if err != nil {
				t.Fatal(err)
			}
			if err = r.State.Validate(45, true); err != nil {
				t.Fatal(err)
			}
			emitFeasible(map[string]any{"kind": "r2_window", "name": fmt.Sprintf("radius%.0f_expand%d_probe%t", setting.radius, setting.expand, setting.probe), "seconds": time.Since(windowStart).Seconds(), "work": difference(windowWorld.work, windowBefore), "dps": r.Value, "loss_vs_unrestricted": wide.Value - r.Value, "stop": r.Stop, "expansions": r.Expansions, "final_radius": r.Radius, "wide_probed": r.WideProbed, "wrapper_evaluations": r.Evaluations, "rejected_outside": r.RejectedOutside})
		}
		// Preparation micro-control uses the identical route with cold model
		// and no numerical solves. Positive and unavailable targets both recur.
		var routeDigest string
		for _, reuse := range []bool{false, true} {
			w := newWorld(reuse)
			start := time.Now()
			familySequence := []string{}
			for repeat := 0; repeat < 2; repeat++ {
				for _, option := range options {
					p := leader
					p[2] = option
					e, err := w.get(p)
					if err != nil {
						t.Fatal(err)
					}
					family := "unavailable"
					if e != nil {
						family = e.family
					}
					familySequence = append(familySequence, family)
				}
			}
			b, _ := json.Marshal(familySequence)
			digest := fmt.Sprintf("%x", sha256.Sum256(b))
			if reuse && digest != routeDigest {
				t.Fatal("resolve cache changed route")
			}
			routeDigest = digest
			emitFeasible(map[string]any{"kind": "r2_prepare", "name": fmt.Sprintf("prepare_reuse_%t", reuse), "seconds": time.Since(start).Seconds(), "work": w.work, "extra": w.extra, "route_sha256": digest, "model_stats": w.model.Stats()})
		}
		// Positive-affine recognition is stronger than exact-family identity,
		// but only useful if this real team exposes such structural families.
		wAffine := newWorld(true)
		distinct := map[string]*feasibleEntry{}
		proofs := 0
		nonidentity := 0
		checks := 0
		proofSeconds := 0.0
		for _, option := range options {
			p := leader
			p[2] = option
			e, err := wAffine.get(p)
			if err != nil {
				t.Fatal(err)
			}
			if e == nil {
				continue
			}
			if _, ok := distinct[e.family]; ok {
				continue
			}
			for _, ref := range distinct {
				// The graph proof alone has no knowledge of artifact-domain or
				// delta-coordinate origins. Check those separately before reuse.
				sameOrigin := e.indices == ref.indices && len(e.baseline) == len(ref.baseline)
				if sameOrigin {
					for i := range e.baseline {
						if e.baseline[i] != ref.baseline[i] {
							sameOrigin = false
							break
						}
					}
				}
				if !sameOrigin {
					continue
				}
				begin := time.Now()
				a, b, ok := e.program.PositiveAffineOf(ref.program)
				proofSeconds += time.Since(begin).Seconds()
				checks++
				if ok {
					proofs++
					if a != 1 || b != 0 {
						nonidentity++
					}
				}
			}
			distinct[e.family] = e
		}
		emitFeasible(map[string]any{"kind": "r2_affine", "distinct_families": len(distinct), "checks": checks, "proofs": proofs, "nonidentity_proofs": nonidentity, "recognition_seconds": proofSeconds, "domain": "identical 45-unit mains/lines domain; candidate stats coordinates unchanged", "objective_scope": "whole team DPS, no per-channel multiplier inference"})
		hunter := leader
		hunter[1] = r2Package("marechausseehunter")
		w := newWorld(true)
		e, err := w.get(hunter)
		if err != nil {
			t.Fatal(err)
		}
		emitFeasible(map[string]any{"kind": "r2_availability", "name": "chasca_hunter", "available": e != nil, "boundaries": w.boundaries})
		wHunter := newWorld(true)
		wHunter.hunterObserved = true
		hunterControl := fixed(wHunter, hunter, initial, r2Wide(), "cold_hunter_observed_schedule")
		// These are fixed-package independent controls, not ranked top builds.
		rows := []map[string]any{}
		for i := 1; i <= 2; i++ {
			if cold[i].value > 0 {
				carrier := newWorld(true)
				if _, err := carrier.get(cold[i].packages); err != nil {
					t.Fatal(err)
				}
				rows = append(rows, carrier.row(cold[i]))
			}
		}
		if hunterControl.value > 0 {
			rows = append(rows, wHunter.row(hunterControl))
		}
		emitFeasible(map[string]any{"kind": "finalists", "candidates": rows, "scope": "independently solved fixed Tenacity and Troupe controls plus explicitly approximate Hunter; no top-N claim"})
		return
	}
	var reference [3]feasibleCandidate
	var referenceRoute string
	// Independent cold fixed-bonus measurement of the one added sequential-line
	// correction. No result from these worlds initializes either outer search.
	for index, name := range []string{"tenacity", "troupe", "chasca_attack_2plus2"} {
		w := newWorld(true)
		packages := r2Tuple()
		if index == 1 {
			packages[2] = r2Package("goldentroupe")
		}
		if index == 2 {
			packages[1] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "gladiatorsfinale", Count: 2}, {SetUID: "shimenawasreminiscence", Count: 2}}}
		}
		start := time.Now()
		e, err := w.get(packages)
		if err != nil || e == nil {
			t.Fatal("alternating cold control unavailable", err)
		}
		r, err := w.alternating(e, initial)
		if err != nil {
			t.Fatal(err)
		}
		c := feasibleCandidate{packages, r.State, r.Value, e.family}
		emitFeasible(map[string]any{"kind": "r2_alternating", "name": name, "seconds": time.Since(start).Seconds(), "model_seconds": w.modelSeconds, "work": w.work, "extra": w.extra, "candidate": w.row(c), "unresolved_graph": e.program.HasUnresolvedDependencies(), "prior_result_cache": false})
	}
	for _, reuse := range []bool{false, true} {
		w := newWorld(reuse)
		start := time.Now()
		leader, runner, none, err := w.search(options, initial, 4)
		if err != nil {
			t.Fatal(err)
		}
		got := [3]feasibleCandidate{leader, runner, none}
		route := fmt.Sprintf("%x", w.route.Sum(nil))
		if reuse {
			if route != referenceRoute {
				t.Fatal("same-route exact reuse changed target enumeration")
			}
			for i := range got {
				if got[i].state != reference[i].state || theoryteams.Key(got[i].packages) != theoryteams.Key(reference[i].packages) || math.Abs(got[i].value-reference[i].value) > 1e-7 {
					t.Fatal("same-route exact reuse changed result", i)
				}
			}
		} else {
			reference = got
			referenceRoute = route
		}
		emitFeasible(map[string]any{"kind": "r2_search", "name": fmt.Sprintf("joint_cold_reuse_%t", reuse), "seconds": time.Since(start).Seconds(), "model_seconds": w.modelSeconds, "stage_seconds": w.stages, "route_sha256": route, "work": w.work, "extra": w.extra, "candidate": w.row(leader), "runner": w.row(runner), "none": w.row(none), "model_stats": w.model.Stats(), "global_optimum": false, "completed_request_cache": false, "prior_solution_cache": false, "boundaries": w.boundaries})
	}
	w := newWorld(true)
	rows := []map[string]any{}
	for _, c := range reference {
		if _, err := w.get(c.packages); err != nil {
			t.Fatal(err)
		}
		rows = append(rows, w.row(c))
	}
	emitFeasible(map[string]any{"kind": "finalists", "candidates": rows, "scope": "leader, retained distinct-family competitor, none; not top three"})
}
