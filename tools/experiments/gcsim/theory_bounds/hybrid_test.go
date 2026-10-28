package main

// Scratch-only general team-search study. Controls are read only after every
// policy and the additional audit have finished. No engine call occurs here.
import (
	"crypto/sha256"
	"errors"
	"fmt"
	"math"
	"runtime"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func hybridLegal(s proto.State) bool {
	if s.Validate(45, true) != nil {
		return false
	}
	for _, actor := range s.Upgrades {
		sum := 0.0
		for _, slot := range actor {
			for _, x := range slot {
				sum += x
			}
		}
		if math.Abs(sum-25) > 1e-7 {
			return false
		}
	}
	return true
}

type hybridGuard struct {
	objective proto.Objective
	deadline  time.Time
	best      proto.State
	value     float64
	hasBest   bool
}

func (b *hybridGuard) evaluate(s proto.State, gradient bool) (float64, [4][10]float64, error) {
	if !time.Now().Before(b.deadline) {
		return 0, [4][10]float64{}, errProgressiveDeadline
	}
	v, g, err := b.objective(s, gradient)
	if err == nil && !math.IsNaN(v) && !math.IsInf(v, 0) && (!b.hasBest || v > b.value) && hybridLegal(s) {
		b.best, b.value, b.hasBest = s, v, true
	}
	return v, g, err
}
func hybridPackageKey(p domain.Package) string { return theoryteams.Key([4]domain.Package{p}) }
func hybridAddAlias(m map[string]map[string]bool, family, key string) {
	if m[family] == nil {
		m[family] = map[string]bool{}
	}
	m[family][key] = true
}
func hybridAliases(m map[string]map[string]bool) map[string][]string {
	out := map[string][]string{}
	for f, keys := range m {
		for k := range keys {
			out[f] = append(out[f], k)
		}
		sort.Strings(out[f])
	}
	return out
}
func hybridOffer(pool map[string]feasibleCandidate, c feasibleCandidate) bool {
	if math.IsNaN(c.value) || math.IsInf(c.value, 0) || !hybridLegal(c.state) {
		return false
	}
	if old, ok := pool[c.family]; ok && old.value >= c.value {
		return false
	}
	pool[c.family] = c
	return true
}
func hybridCopy(pool map[string]feasibleCandidate) map[string]feasibleCandidate {
	out := map[string]feasibleCandidate{}
	for k, c := range pool {
		out[k] = c
	}
	return out
}
func hybridSortedOptions(options []domain.Package) []domain.Package {
	out := append([]domain.Package(nil), options...)
	sort.Slice(out, func(i, j int) bool {
		a := sha256.Sum256([]byte(hybridPackageKey(out[i])))
		b := sha256.Sum256([]byte(hybridPackageKey(out[j])))
		return string(a[:]) < string(b[:])
	})
	return out
}
func hybridInitialTuples(original [4]domain.Package, options []domain.Package) [][4]domain.Package {
	out := [][4]domain.Package{original}
	if len(options) == 0 {
		return out
	}
	ordered := hybridSortedOptions(options)
	for k := 0; k < 8; k++ {
		p := original
		for a := range p {
			p[a] = ordered[(17+97*a+131*k)%len(ordered)]
		}
		out = append(out, p)
	}
	return out
}
func hybridFresh(initial proto.State, g [4][10]float64) []proto.State {
	mains := initial.Mains
	for a := range mains {
		for slot := 2; slot < 5; slot++ {
			value := math.Inf(-1)
			choice := mains[a][slot]
			for _, main := range proto.MainChoices[slot] {
				for j, key := range proto.StatKeys {
					if main == key {
						v := g[a][j] * proto.MainValues[main] / proto.Values[j]
						if v > value {
							value, choice = v, main
						}
					}
				}
			}
			mains[a][slot] = choice
		}
	}
	if !hybridLegal(initial) {
		initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	}
	return []proto.State{initial, proto.Seed(initial.Mains, g, 0, 45), proto.Seed(mains, g, 0, 45)}
}
func hybridSeedSet(fresh []proto.State, bank []proto.State, warm bool) []proto.State {
	seeds, _ := hybridSeedPlan(fresh, bank, warm)
	return seeds
}
func hybridSeedPlan(fresh []proto.State, bank []proto.State, warm bool) ([]proto.State, int) {
	if !warm {
		return append([]proto.State(nil), fresh...), 0
	}
	out := []proto.State{fresh[2]}
	transferred := 0
	for _, s := range bank {
		if !hybridLegal(s) {
			continue
		}
		duplicate := false
		for _, old := range out {
			if old == s {
				duplicate = true
			}
		}
		if !duplicate {
			out = append(out, s)
			transferred++
		}
		if len(out) == 3 {
			return out, transferred
		}
	}
	for _, s := range fresh {
		if len(out) == 3 {
			break
		}
		out = append(out, s)
	}
	return out, transferred
}
func hybridDistance(a, b [4]domain.Package) int {
	n := 0
	for i := range a {
		if hybridPackageKey(a[i]) != hybridPackageKey(b[i]) {
			n++
		}
	}
	return n
}
func hybridBeam(pool map[string]feasibleCandidate) []feasibleCandidate {
	rows := r2Sorted(pool)
	if len(rows) < 2 {
		return rows
	}
	chosen := 1
	for i := 2; i < min(8, len(rows)); i++ {
		if hybridDistance(rows[i].packages, rows[0].packages) > hybridDistance(rows[chosen].packages, rows[0].packages) {
			chosen = i
		}
	}
	return []feasibleCandidate{rows[0], rows[chosen]}
}

type hybridRun struct {
	w                                                     *r2World
	initial                                               proto.State
	started, deadline                                     time.Time
	name, phase                                           string
	warm                                                  bool
	pool                                                  map[string]feasibleCandidate
	aliases, unavailable                                  map[string]map[string]bool
	screened                                              map[string]bool
	visited                                               map[string]string
	aliasHits                                             int
	refined                                               map[string]int
	bank                                                  []feasibleCandidate
	curve                                                 []any
	best                                                  float64
	stages                                                map[string]float64
	sweeps                                                []any
	fullSweeps, attemptedSweeps, transferred, independent int
	completedPasses, refinedPasses                        int
	firstPass                                             []feasibleCandidate
}

func newHybrid(w *r2World, initial proto.State, name string, warm bool, global time.Time, seconds int) *hybridRun {
	now := time.Now()
	deadline := now.Add(time.Duration(seconds) * time.Second)
	if global.Before(deadline) {
		deadline = global
	}
	w.feasibleWorld.numericReuse = false
	return &hybridRun{w: w, initial: initial, started: now, deadline: deadline, name: name, warm: warm, pool: map[string]feasibleCandidate{}, aliases: map[string]map[string]bool{}, unavailable: map[string]map[string]bool{}, screened: map[string]bool{}, visited: map[string]string{}, refined: map[string]int{}, best: math.Inf(-1), stages: map[string]float64{}}
}
func (h *hybridRun) alive() bool { return time.Now().Before(h.deadline) }
func (h *hybridRun) offer(c feasibleCandidate) {
	if !hybridOffer(h.pool, c) {
		return
	}
	if c.value > h.best {
		h.best = c.value
		h.curve = append(h.curve, map[string]any{"seconds": time.Since(h.started).Seconds(), "formula_dps": c.value, "family": c.family, "package_key": theoryteams.Key(c.packages), "phase": h.phase, "formula_evaluations": h.w.work.Formula})
	}
	bank := []feasibleCandidate{c}
	for _, old := range h.bank {
		if old.family != c.family && old.state != c.state {
			bank = append(bank, old)
		}
	}
	sort.Slice(bank, func(i, j int) bool {
		if bank[i].value != bank[j].value {
			return bank[i].value > bank[j].value
		}
		return bank[i].family < bank[j].family
	})
	h.bank = bank[:min(6, len(bank))]
}
func (h *hybridRun) objective(e *feasibleEntry, p [4]domain.Package) proto.Objective {
	obj := h.w.objective(e)
	return func(s proto.State, g bool) (float64, [4][10]float64, error) {
		if !h.alive() {
			return 0, [4][10]float64{}, errProgressiveDeadline
		}
		v, grad, err := obj(s, g)
		if err == nil {
			old, ok := h.pool[e.family]
			if !ok || v > old.value {
				h.offer(feasibleCandidate{p, s, v, e.family})
			}
		}
		return v, grad, err
	}
}
func (h *hybridRun) resolve(p [4]domain.Package) (*feasibleEntry, error) {
	if !h.alive() {
		return nil, errProgressiveDeadline
	}
	at := time.Now()
	e, err := h.w.get(p)
	h.stages["set_resolve"] += time.Since(at).Seconds()
	if err != nil {
		return nil, err
	}
	key := theoryteams.Key(p)
	if e == nil {
		hybridAddAlias(h.unavailable, progressiveReason(h.w.metadata[key]), key)
	} else {
		hybridAddAlias(h.aliases, e.family, key)
	}
	return e, nil
}
func (h *hybridRun) seeds(e *feasibleEntry, p [4]domain.Package) ([]proto.State, error) {
	obj := h.objective(e, p)
	bank := append([]feasibleCandidate(nil), h.bank...)
	_, g, err := obj(h.initial, true)
	if err != nil {
		return nil, err
	}
	fresh := hybridFresh(h.initial, g)
	ranked := []feasibleCandidate{}
	if h.warm {
		for _, old := range bank {
			if old.family == e.family {
				continue
			}
			v, _, err := obj(old.state, false)
			if err != nil {
				return nil, err
			}
			old.value = v
			ranked = append(ranked, old)
		}
		sort.SliceStable(ranked, func(i, j int) bool { return ranked[i].value > ranked[j].value })
	}
	states := []proto.State{}
	for _, c := range ranked {
		states = append(states, c.state)
	}
	selected, transferred := hybridSeedPlan(fresh, states, h.warm)
	h.independent += len(selected) - transferred
	h.transferred += transferred
	return selected, nil
}
func (h *hybridRun) visit(p [4]domain.Package) (string, error) {
	if !h.alive() {
		return "", errProgressiveDeadline
	}
	key := theoryteams.Key(p)
	if family, known := h.visited[key]; known && (family == "" || h.screened[family]) {
		h.aliasHits++
		return family, nil
	}
	e, err := h.resolve(p)
	if err != nil {
		return "", err
	}
	if e == nil {
		h.visited[key] = ""
		return "", nil
	}
	h.visited[key] = e.family
	if h.screened[e.family] {
		h.w.work.FamilyReuses++
		return e.family, nil
	}
	at := time.Now()
	defer func() { h.stages["short_allocation"] += time.Since(at).Seconds() }()
	seeds, err := h.seeds(e, p)
	if err != nil {
		return e.family, err
	}
	for _, s := range seeds {
		if !hybridLegal(s) {
			return e.family, fmt.Errorf("illegal search seed")
		}
		h.w.work.AllocationAttempts++
		_, err = proto.Optimize(h.objective(e, p), s, basicConfig(4))
		if err != nil {
			return e.family, err
		}
	}
	h.screened[e.family] = true
	return e.family, nil
}
func (h *hybridRun) refine(c feasibleCandidate, deep bool) error {
	e, err := h.resolve(c.packages)
	if err != nil || e == nil {
		return err
	}
	level := 1
	if deep {
		level = 2
	}
	if h.refined[c.family] >= level {
		return nil
	}
	at := time.Now()
	obj := h.objective(e, c.packages)
	_, err = proto.FastWhole(obj, h.pool[c.family].state, basicConfig(40), proto.FastConfig{Passes: 1, InnerIterations: 4})
	h.stages["main_refinement"] += time.Since(at).Seconds()
	if err != nil {
		return err
	}
	if deep {
		at = time.Now()
		_, err = proto.SlotLines(obj, h.pool[c.family].state, basicConfig(40), proto.SlotLineConfig{Passes: 1, InnerIterations: 4})
		h.stages["line_refinement"] += time.Since(at).Seconds()
		if err != nil {
			return err
		}
		at = time.Now()
		_, err = proto.FastWhole(obj, h.pool[c.family].state, basicConfig(60), proto.FastConfig{Passes: 1, InnerIterations: 6, MainPairs: true})
		h.stages["main_pair_refinement"] += time.Since(at).Seconds()
		if err != nil {
			return err
		}
	}
	h.refined[c.family] = level
	return nil
}
func (h *hybridRun) checkpoint(label string) {
	rows := r2Sorted(h.pool)
	var best any
	if len(rows) > 0 {
		best = h.w.row(rows[0])
	}
	seconds := time.Since(h.started).Seconds()
	emitFeasible(map[string]any{"kind": "hybrid_checkpoint", "name": fmt.Sprintf("%s %s: %.3f DPS, %.3fs, %d families", h.name, label, h.best, seconds, len(rows)), "variant": h.name, "stage": label, "seconds": seconds, "best": best, "families": len(rows), "work": h.w.work, "stages_seconds": h.stages})
}
func (h *hybridRun) finalRefinement(prefix string) error {
	rows := r2Sorted(h.pool)
	picks := []feasibleCandidate{}
	for i := 0; i < min(2, len(rows)); i++ {
		picks = append(picks, rows[i])
	}
	for i := 4; i < len(rows); i++ {
		if h.refined[rows[i].family] < 2 {
			picks = append(picks, rows[i])
			break
		}
	}
	for i, c := range picks {
		h.phase = fmt.Sprintf("%s_refine_%d", prefix, i)
		if err := h.refine(c, true); err != nil {
			return err
		}
		h.checkpoint(h.phase)
	}
	return nil
}
func (h *hybridRun) search(original [4]domain.Package, options []domain.Package) error {
	starts := []feasibleCandidate{}
	startFamilies := map[string]bool{}
	h.phase = "generated_starts"
	for _, p := range hybridInitialTuples(original, options) {
		f, err := h.visit(p)
		if err != nil {
			return err
		}
		if f != "" && !startFamilies[f] {
			startFamilies[f] = true
			if err = h.refine(h.pool[f], false); err != nil {
				return err
			}
			starts = append(starts, h.pool[f])
		}
		if len(starts) == 2 {
			break
		}
	}
	if len(starts) == 0 {
		return fmt.Errorf("no available generated start")
	}
	h.checkpoint(h.phase)
	for pass := 0; pass < 2; pass++ {
		for a := 0; a < 4; a++ {
			anchors := hybridBeam(h.pool)
			if pass == 0 && a == 0 {
				anchors = starts
			}
			for b, anchor := range anchors {
				h.phase = fmt.Sprintf("pass%d_actor%d_context%d", pass, a, b)
				h.attemptedSweeps++
				at := time.Now()
				before := h.w.work
				touched := map[string]bool{}
				visited := 0
				var stop error
				for _, option := range options {
					p := anchor.packages
					p[a] = option
					f, err := h.visit(p)
					if err != nil {
						stop = err
						break
					}
					visited++
					if f != "" {
						touched[f] = true
					}
				}
				if visited == len(options) {
					h.fullSweeps++
				}
				h.sweeps = append(h.sweeps, map[string]any{"pass": pass, "actor": a, "context": b, "anchor_key": theoryteams.Key(anchor.packages), "planned": len(options), "visited": visited, "complete": visited == len(options), "seconds": time.Since(at).Seconds(), "work": difference(h.w.work, before)})
				if stop != nil {
					h.checkpoint(h.phase + "_partial")
					return stop
				}
				local := map[string]feasibleCandidate{}
				for f := range touched {
					if c, ok := h.pool[f]; ok {
						local[f] = c
					}
				}
				rows := r2Sorted(local)
				if len(rows) > 0 {
					if err := h.refine(rows[0], false); err != nil {
						h.checkpoint(h.phase + "_partial_main")
						return err
					}
				}
				h.checkpoint(h.phase)
			}
		}
		h.completedPasses = pass + 1
		if err := h.finalRefinement(fmt.Sprintf("pass%d", pass)); err != nil {
			h.checkpoint(h.phase + "_partial")
			return err
		}
		h.refinedPasses = pass + 1
		if pass == 0 {
			// Freeze the measured stopping candidate without restarting the search.
			h.firstPass = h.snapshot(h.name + "_first_pass")
		}
	}
	return nil
}
func (h *hybridRun) snapshot(label string) []feasibleCandidate {
	emitFeasible(map[string]any{"kind": "hybrid_model_profile", "variant": label, "stats": h.w.model.Stats(), "scope": "cumulative within this independently cold model; H/P share one continuation"})
	emitFeasible(map[string]any{"kind": "hybrid_alias_reuse", "variant": label, "tuple_alias_hits": h.aliasHits, "known_tuple_keys": len(h.visited), "scope": "immutable current world; family/alias sharing, no complete numerical-solve cache"})
	rows := r2Sorted(h.pool)
	ranking := []any{}
	full := []any{}
	for i, c := range rows {
		ranking = append(ranking, map[string]any{"rank": i + 1, "family": c.family, "formula_dps": c.value, "package_key": theoryteams.Key(c.packages), "refinement_level": h.refined[c.family]})
		if i < 8 {
			full = append(full, h.w.row(c))
		}
	}
	var best any
	if len(rows) > 0 {
		best = h.w.row(rows[0])
	}
	seconds := time.Since(h.started).Seconds()
	emitFeasible(map[string]any{"kind": "hybrid_policy", "name": fmt.Sprintf("%s frozen: %.3f DPS, %.3fs, %d families", label, h.best, seconds, len(rows)), "variant": label, "best": best, "seconds": seconds, "model_seconds": h.w.modelSeconds, "stages_seconds": h.stages, "work": h.w.work, "reuse": h.w.extra, "ranking": ranking, "top_witnesses": full, "curve": h.curve, "aliases_by_family": hybridAliases(h.aliases), "unavailable_by_reason": hybridAliases(h.unavailable), "sweeps": h.sweeps, "full_sweeps": h.fullSweeps, "attempted_sweeps": h.attemptedSweeps, "planned_max_sweeps": 16, "completed_catalog_passes": h.completedPasses, "completed_refined_passes": h.refinedPasses, "complete_outer_plan": h.fullSweeps == 16, "independent_starts": h.independent, "transferred_starts": h.transferred, "final_solution_cache_enabled": false, "source_upper": "unbounded", "outer_upper": "unbounded", "full_cartesian_covered": false, "additional_audit_included": false})
	return rows
}

type hybridPair struct {
	Packages [4]domain.Package
	Actors   [2]int
	Ranks    [2]int
	Anchor   string
}

func hybridPairPlan(pool map[string]feasibleCandidate, aliases map[string]map[string]bool, options []domain.Package) []hybridPair {
	// Package scores are the best observed full-team lower bound in a context
	// containing that package; they are heuristic preferences, never upper bounds.
	scores := [4]map[string]float64{}
	for a := range scores {
		scores[a] = map[string]float64{}
	}
	// Include aliases: the representative's package is not the only valid output.
	// Recover package components directly from catalog keys; no control parser.
	part := map[string]domain.Package{}
	for _, o := range options {
		part[splitHybridKey(hybridPackageKey(o))[0]] = o
	}
	for f, rows := range aliases {
		c, ok := pool[f]
		if !ok {
			continue
		}
		for key := range rows {
			tuple, ok := hybridTupleFromKey(key, part)
			if !ok {
				continue
			}
			for a, p := range tuple {
				k := hybridPackageKey(p)
				if old, seen := scores[a][k]; !seen || c.value > old {
					scores[a][k] = c.value
				}
			}
		}
	}
	type choice struct {
		p     domain.Package
		score float64
		rank  int
	}
	order := [4][]choice{}
	for a := range order {
		for _, p := range options {
			v, ok := scores[a][hybridPackageKey(p)]
			if ok {
				order[a] = append(order[a], choice{p, v, 0})
			}
		}
		sort.Slice(order[a], func(i, j int) bool {
			if order[a][i].score != order[a][j].score {
				return order[a][i].score > order[a][j].score
			}
			return hybridPackageKey(order[a][i].p) < hybridPackageKey(order[a][j].p)
		})
		for i := range order[a] {
			order[a][i].rank = i + 1
		}
	}
	plan := []hybridPair{}
	for _, anchor := range hybridBeam(pool) {
		picked := [4][]choice{}
		for a := range picked {
			seen := map[string]bool{}
			n := len(order[a])
			for _, want := range []int{2, 5, n / 2, 3 * n / 4} {
				for offset := 0; offset < n; offset++ {
					i := (want + offset) % max(n, 1)
					if i < 2 {
						continue
					}
					c := order[a][i]
					k := hybridPackageKey(c.p)
					if seen[k] || k == hybridPackageKey(anchor.packages[a]) {
						continue
					}
					seen[k] = true
					picked[a] = append(picked[a], c)
					break
				}
			}
		}
		for a := 0; a < 4; a++ {
			for b := a + 1; b < 4; b++ {
				for _, x := range picked[a] {
					for _, y := range picked[b] {
						p := anchor.packages
						p[a], p[b] = x.p, y.p
						plan = append(plan, hybridPair{p, [2]int{a, b}, [2]int{x.rank, y.rank}, theoryteams.Key(anchor.packages)})
					}
				}
			}
		}
	}
	return plan
}
func hybridTupleFromKey(key string, options map[string]domain.Package) ([4]domain.Package, bool) {
	// The key format is owned by theoryteams.Key; compare its four components
	// without interpreting set names or count syntax.
	var tuple [4]domain.Package
	parts := splitHybridKey(key)
	if len(parts) != 4 {
		return tuple, false
	}
	for a, want := range parts {
		p, found := options[want]
		if !found {
			return tuple, false
		}
		tuple[a] = p
	}
	return tuple, true
}
func splitHybridKey(key string) []string { // small helper kept independent of inputs/controls
	parts := []string{}
	last := 0
	for i, c := range key {
		if c == '|' {
			parts = append(parts, key[last:i])
			last = i + 1
		}
	}
	return append(parts, key[last:])
}
func hybridPairRefineIndices(n int) []int {
	out := []int{}
	seen := map[int]bool{}
	for _, i := range []int{0, 1, 2 + (n-2)/2} {
		if i >= 0 && i < n && !seen[i] {
			out = append(out, i)
			seen[i] = true
		}
	}
	return out
}
func (h *hybridRun) pairs(options []domain.Package, global time.Time) error {
	started := time.Now()
	h.deadline = started.Add(60 * time.Second)
	if global.Before(h.deadline) {
		h.deadline = global
	}
	h.name = "P_pairs"
	h.phase = "pair_screen"
	plan := hybridPairPlan(h.pool, h.aliases, options)
	emitFeasible(map[string]any{"kind": "hybrid_pair_plan", "planned": len(plan), "origin": "visited package ranks, excluding top two and anchor package", "budget_seconds": 60})
	completed := 0
	touched := map[string]bool{}
	var stop error
	for _, p := range plan {
		f, err := h.visit(p.Packages)
		if err != nil {
			stop = err
			break
		}
		completed++
		var candidate any
		if f != "" {
			touched[f] = true
			c := h.pool[f]
			c.packages = p.Packages
			candidate = h.w.row(c)
		}
		emitFeasible(map[string]any{"kind": "hybrid_pair_attempt", "actors": p.Actors, "package_ranks": p.Ranks, "anchor_key": p.Anchor, "package_key": theoryteams.Key(p.Packages), "family": f, "available": f != "", "candidate": candidate})
	}
	if stop == nil {
		local := map[string]feasibleCandidate{}
		for f := range touched {
			if h.refined[f] < 2 {
				local[f] = h.pool[f]
			}
		}
		rows := r2Sorted(local)
		selected := map[string]bool{}
		for _, i := range hybridPairRefineIndices(len(rows)) {
			if i >= len(rows) || selected[rows[i].family] {
				continue
			}
			selected[rows[i].family] = true
			h.phase = "pair_refinement"
			if stop = h.refine(rows[i], true); stop != nil {
				break
			}
			h.checkpoint(h.phase)
		}
	}
	emitFeasible(map[string]any{"kind": "hybrid_pair_summary", "seconds": time.Since(started).Seconds(), "planned": len(plan), "completed": completed, "pending": len(plan) - completed, "budget_exhausted": errors.Is(stop, errProgressiveDeadline)})
	return stop
}

func hybridAcceptStop(t *testing.T, err error) {
	t.Helper()
	if err != nil && !errors.Is(err, errProgressiveDeadline) {
		t.Fatal(err)
	}
}
func hybridProbe(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State, global time.Time) {
	at := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	h := newHybrid(w, initial, "seed_probe", true, global, 30)
	h.phase = "probe_training"
	for _, p := range hybridInitialTuples(original, options) {
		f, e := h.visit(p)
		if e != nil {
			hybridAcceptStop(t, e)
			break
		}
		if f != "" {
			e = h.refine(h.pool[f], true)
			hybridAcceptStop(t, e)
		}
		if len(h.bank) >= 2 || !h.alive() {
			break
		}
	}
	bank := append([]feasibleCandidate(nil), h.bank...)
	seen := map[string]bool{}
	done := 0
	ordered := hybridSortedOptions(options)
	for i := 0; i < len(ordered) && done < 24 && h.alive(); i++ {
		p := original
		p[i%4] = ordered[i]
		e, err := h.resolve(p)
		if err != nil {
			hybridAcceptStop(t, err)
			break
		}
		if e == nil || seen[e.family] {
			continue
		}
		seen[e.family] = true
		_, g, err := w.objective(e)(initial, true)
		if err != nil {
			t.Fatal(err)
		}
		fresh := hybridFresh(initial, g)
		states := []proto.State{}
		for _, c := range bank {
			states = append(states, c.state)
		}
		result := map[string]any{"kind": "hybrid_seed_probe", "family": e.family, "package_key": theoryteams.Key(p)}
		for _, warm := range []bool{false, true} {
			label := "fresh"
			if warm {
				label = "transfer"
			}
			start := time.Now()
			before := w.work
			guard := hybridGuard{objective: w.objective(e), deadline: h.deadline}
			complete := true
			for _, s := range hybridSeedSet(fresh, states, warm) {
				_, err = proto.Optimize(guard.evaluate, s, basicConfig(4))
				if err != nil {
					hybridAcceptStop(t, err)
					complete = false
					break
				}
			}
			var c any
			if guard.hasBest {
				c = w.row(feasibleCandidate{p, guard.best, guard.value, e.family})
			}
			result[label] = map[string]any{"candidate": c, "seconds": time.Since(start).Seconds(), "work": difference(w.work, before), "complete": complete}
		}
		emitFeasible(result)
		done++
	}
	emitFeasible(map[string]any{"kind": "hybrid_seed_probe_summary", "seconds": time.Since(at).Seconds(), "families": done, "training_states": len(bank), "work": w.work, "budget_seconds": 30, "is_policy_seed": false})
}
func hybridAudit(t *testing.T, h *hybridRun, global time.Time) {
	rows := r2Sorted(h.pool)
	original := hybridCopy(h.pool)
	at := time.Now()
	deadline := at.Add(60 * time.Second)
	if global.Before(deadline) {
		deadline = global
	}
	h.deadline = deadline
	h.name = "B_reference"
	h.phase = "additional_reference"
	choices := []int{2, len(rows) / 2, 3 * len(rows) / 4}
	seen := map[string]bool{}
	planned, completed := 0, 0
	items := []feasibleCandidate{}
	for _, i := range choices {
		if i < len(rows) && !seen[rows[i].family] {
			seen[rows[i].family] = true
			items = append(items, rows[i])
			planned += 2
		}
	}
	before := h.w.work
	publicRanks := []int{}
	for _, i := range choices {
		publicRanks = append(publicRanks, i+1)
	}
	emitFeasible(map[string]any{"kind": "hybrid_reference_plan", "ranks": publicRanks, "planned_attempts": planned, "budget_seconds": 60, "starts": "two independent generated states; no warm bank or controls"})
	for _, c := range items {
		e, err := h.resolve(c.packages)
		if err != nil {
			hybridAcceptStop(t, err)
			break
		}
		// Rebuild independent starts explicitly; the warm bank is never an audit start.
		_, g, err := h.w.objective(e)(h.initial, true)
		if err != nil {
			t.Fatal(err)
		}
		starts := hybridFresh(h.initial, g)
		for seed := 1; seed <= 2; seed++ {
			if !h.alive() {
				break
			}
			pointAt := time.Now()
			guard := hybridGuard{objective: h.w.objective(e), deadline: deadline}
			stages := 0
			state := starts[seed]
			first, e1 := proto.FastWhole(guard.evaluate, state, basicConfig(80), proto.FastConfig{Passes: 2, InnerIterations: 8})
			if e1 == nil {
				state = first.State
				stages++
				line, e2 := proto.SlotLines(guard.evaluate, state, basicConfig(80), proto.SlotLineConfig{Passes: 2, InnerIterations: 8})
				e1 = e2
				if e1 == nil {
					state = line.State
					stages++
					_, e1 = proto.FastWhole(guard.evaluate, state, basicConfig(100), proto.FastConfig{Passes: 2, InnerIterations: 16, MainPairs: true})
					if e1 == nil {
						stages++
					}
				}
			}
			hybridAcceptStop(t, e1)
			var candidate any
			if guard.hasBest {
				point := feasibleCandidate{c.packages, guard.best, guard.value, c.family}
				h.offer(point)
				candidate = h.w.row(point)
			}
			if stages == 3 {
				completed++
			}
			emitFeasible(map[string]any{"kind": "hybrid_reference_attempt", "family": c.family, "fresh_seed": seed, "completed_stages": stages, "candidate": candidate, "seconds": time.Since(pointAt).Seconds()})
		}
	}
	final := r2Sorted(h.pool)
	frozen := r2Sorted(original)
	changes := []any{}
	for i, c := range final {
		for j, old := range frozen {
			if c.family == old.family && (i != j || c.value != old.value) {
				changes = append(changes, map[string]any{"family": c.family, "policy_rank": j + 1, "reference_rank": i + 1, "policy_lower": old.value, "reference_lower": c.value})
			}
		}
	}
	emitFeasible(map[string]any{"kind": "hybrid_reference_summary", "policy_best": h.w.row(frozen[0]), "best": h.w.row(final[0]), "rescue_gain": final[0].value - frozen[0].value, "ranking_changes": changes, "seconds": time.Since(at).Seconds(), "work": difference(h.w.work, before), "planned_attempts": planned, "completed_attempts": completed, "pending_attempts": planned - completed, "is_oracle": false})
}
func runTheoryHybrid(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	at := time.Now()
	global := at.Add(600 * time.Second)
	emitFeasible(map[string]any{"kind": "hybrid_protocol", "protocol_revision": 2, "refinement_after_each_pass": true, "budget_seconds": 600, "input_anchor_key": theoryteams.Key(original), "all_four_wearers": true, "packages_per_wearer": len(options), "capture_calls_inside_study": 0, "finalist_calls": 0, "known_points_role": "post-selection only", "phase_budgets_seconds": []int{30, 180, 180, 60, 60}})
	hybridProbe(t, factory, req, base, original, options, initial, global)
	runtime.GC()
	makeRun := func(name string, warm bool) *hybridRun {
		start := time.Now()
		w, err := newR2World(factory, req, base, true)
		if err != nil {
			t.Fatal(err)
		}
		h := newHybrid(w, initial, name, warm, global, 180)
		h.started = start
		h.deadline = start.Add(180 * time.Second)
		if global.Before(h.deadline) {
			h.deadline = global
		}
		return h
	}
	r := makeRun("R_fresh", false)
	hybridAcceptStop(t, r.search(original, options))
	reference := r.snapshot("R_fresh")
	referenceSeconds := time.Since(r.started).Seconds()
	referenceFirstPass := r.firstPass
	r = nil
	runtime.GC()
	h := makeRun("H_transfer", true)
	hybridAcceptStop(t, h.search(original, options))
	policy := h.snapshot("H_transfer")
	hSeconds := time.Since(h.started).Seconds()
	hybridAcceptStop(t, h.pairs(options, global))
	paired := h.snapshot("P_pairs")
	pSeconds := time.Since(h.started).Seconds()
	if len(reference) == 0 || len(policy) == 0 || len(paired) == 0 {
		t.Fatal("policy has no legal candidate")
	}
	hybridAudit(t, h, global)
	// Old points are not even deserialized until all searches and audit are frozen.
	knownAt := time.Now()
	before := h.w.work
	progressiveKnown(t, h.w, paired, r2Sorted(h.pool), global)
	knownSeconds := time.Since(knownAt).Seconds()
	knownWork := difference(h.w.work, before)
	replayAt := time.Now()
	before = h.w.work
	// Re-evaluate R/H leaders on this same captured universe, without optimization.
	for _, v := range []struct {
		name string
		rows []feasibleCandidate
	}{{"R_fresh_first_pass", referenceFirstPass}, {"R_fresh", reference}, {"H_transfer_first_pass", h.firstPass}, {"H_transfer", policy}, {"P_pairs", paired}} {
		if len(v.rows) == 0 {
			emitFeasible(map[string]any{"kind": "hybrid_policy_replay_pending", "variant": v.name, "reason": "first-pass refinement not completed"})
			continue
		}
		if !time.Now().Before(global) {
			emitFeasible(map[string]any{"kind": "hybrid_policy_replay_pending", "variant": v.name, "reason": "whole-study deadline"})
			continue
		}
		c := v.rows[0]
		e, err := h.w.get(c.packages)
		if err != nil || e == nil {
			t.Fatal("policy leader replay unavailable", err)
		}
		if !time.Now().Before(global) {
			emitFeasible(map[string]any{"kind": "hybrid_policy_replay_pending", "variant": v.name, "reason": "whole-study deadline after resolve"})
			continue
		}
		value, _, err := h.w.objective(e)(c.state, false)
		if err != nil || math.Abs(value-c.value) > 1e-7*math.Max(1, math.Abs(value)) {
			t.Fatal("same-universe policy replay mismatch", value, c.value, err)
		}
		emitFeasible(map[string]any{"kind": "hybrid_policy_replay", "variant": v.name, "candidate": h.w.row(c), "replayed_dps": value})
	}
	emitFeasible(map[string]any{"kind": "hybrid_summary", "seconds": time.Since(at).Seconds(), "R_seconds": referenceSeconds, "H_seconds": hSeconds, "P_cumulative_seconds": pSeconds, "R_lower": reference[0].value, "H_lower": policy[0].value, "P_lower": paired[0].value, "known_point_seconds": knownSeconds, "known_point_work": knownWork, "policy_replay_seconds": time.Since(replayAt).Seconds(), "policy_replay_work": difference(h.w.work, before), "source_upper": "unbounded", "outer_upper": "unbounded", "fresh_capture_calls_inside_study": 0, "finalist_calls": 0, "full_cartesian_covered": false})
}
