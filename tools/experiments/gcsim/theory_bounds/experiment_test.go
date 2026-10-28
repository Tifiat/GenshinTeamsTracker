package main

// Finite root-bound/cost study. The selected tuples are named controls, never a
// claimed enumeration of the complete package Cartesian product. The queue
// retains every unexpanded control region and an explicit unbounded outer tail.
import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func boundNumber(v float64) any {
	if math.IsInf(v, 0) || math.IsNaN(v) {
		return "unbounded"
	}
	return v
}

type boundDomain struct {
	entry       *feasibleEntry
	restriction proto.SupportDomain
	actor       []int
	key         []string
	cache       map[[128]float64][2]float64
	calls, hits int
}

func newBoundDomain(e *feasibleEntry, req contracts.OptimizerRequest) (*boundDomain, error) {
	d := &boundDomain{entry: e, actor: make([]int, len(e.coords)), key: make([]string, len(e.coords)), cache: map[[128]float64][2]float64{}}
	if len(e.coords) > 128 {
		return nil, fmt.Errorf("more than128 coordinates")
	}
	for i, coordinate := range e.coords {
		parts := strings.SplitN(coordinate, ".", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("coordinate format %s", coordinate)
		}
		d.actor[i] = -1
		for a, w := range req.Wearers {
			if parts[0] == w.WearerKey {
				d.actor[i] = a
			}
		}
		if d.actor[i] < 0 {
			return nil, fmt.Errorf("coordinate actor %s", coordinate)
		}
		d.key[i] = parts[1]
	}
	return d, nil
}

func (d *boundDomain) support(w []float64) (float64, float64) {
	var k [128]float64
	copy(k[:], w)
	if v, ok := d.cache[k]; ok {
		d.hits++
		return v[0], v[1]
	}
	d.calls++
	weights := proto.LinearWeights{}
	for a := range weights {
		weights[a] = map[string]float64{}
	}
	for i, v := range w {
		// Keys absent from the explicit Theory tables never vary in its objective.
		if _, ok := proto.MainValues[d.key[i]]; ok {
			weights[d.actor[i]][d.key[i]] += v
			continue
		}
		for _, key := range proto.StatKeys {
			if key == d.key[i] {
				weights[d.actor[i]][key] += v
				break
			}
		}
	}
	lo, hi, err := proto.Support45(weights, d.restriction)
	if err != nil {
		panic(err)
	}
	if len(d.cache) < 4096 {
		d.cache[k] = [2]float64{lo, hi}
	}
	return lo, hi
}

func (d *boundDomain) box() [][2]float64 {
	box := make([][2]float64, len(d.key))
	for i := range box {
		w := make([]float64, len(box))
		w[i] = 1
		lo, hi := d.support(w)
		g := 2e-12 * (1 + math.Abs(lo) + math.Abs(hi))
		box[i] = [2]float64{lo - g, hi + g}
	}
	return box
}

// The intersection of the exact domain and this box has support no larger
// than either superset. Taking their minimum upper / maximum lower is safe,
// even when it is loose. Binary closed boxes cover the entire parent region.
func (d *boundDomain) envelope(box [][2]float64, natural bool) formula.ResearchEnvelopeResult {
	center, ref := make([]float64, len(box)), make([]float64, len(box))
	for i, b := range box {
		center[i] = b[0]/2 + b[1]/2
		ref[i] = -d.entry.baseline[i]
	}
	support := func(w []float64) (float64, float64) {
		lo, hi := d.support(w)
		bl, bh, mag := 0.0, 0.0, 0.0
		for i, v := range w {
			a, z := v*box[i][0], v*box[i][1]
			bl += math.Min(a, z)
			bh += math.Max(a, z)
			mag += math.Abs(a) + math.Abs(z)
		}
		guard := 2e-12 * (1 + mag)
		return math.Max(lo, bl-guard), math.Min(hi, bh+guard)
	}
	return d.entry.program.ResearchEnvelope(center, ref, support, natural)
}

type boundsControl struct {
	name              string
	packages          [4]domain.Package
	entry             *feasibleEntry
	domain            *boundDomain
	root              [][2]float64
	state             proto.State
	lower             float64
	upper, modelUpper float64
}
type boundsRegion struct {
	control           int
	box               [][2]float64
	upper, modelUpper float64
	depth             int
}

func runTheoryBounds(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	started := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	if raw := os.Getenv("GTT_BOUNDS_CONTROL_PACKAGES"); raw != "" {
		var packages map[string][]contracts.SetRequirement
		if err := json.Unmarshal([]byte(raw), &packages); err != nil {
			t.Fatal(err)
		}
		if len(packages) != 4 {
			t.Fatal("comparison control requires four wearers")
		}
		for a, wearer := range req.Wearers {
			sets, ok := packages[wearer.WearerKey]
			if !ok {
				t.Fatal("missing control wearer")
			}
			original[a] = domain.Package{Sets: sets}
		}
	}
	controls := []boundsControl{{name: "none", packages: [4]domain.Package{}}, {name: "saved_packages_control", packages: original}}
	if os.Getenv("GTT_BOUNDS_CASE") == "chasca" {
		tena := r2Tuple()
		attack := tena
		attack[1] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "gladiatorsfinale", Count: 2}, {SetUID: "shimenawasreminiscence", Count: 2}}}
		controls = append(controls, boundsControl{name: "tenacity_control", packages: tena}, boundsControl{name: "attack_two_plus_two_control", packages: attack})
	} else {
		// Removing each of two wearers' packages is a declared comparison, not a
		// winning set seed or a purported shortlist of globally relevant tuples.
		for a := 0; a < 2; a++ {
			p := original
			p[a] = domain.Package{}
			controls = append(controls, boundsControl{name: fmt.Sprintf("remove_wearer_%d_control", a), packages: p})
		}
	}
	seen := map[string]bool{}
	available := []boundsControl{}
	for _, c := range controls {
		key := theoryteams.Key(c.packages)
		if seen[key] {
			continue
		}
		seen[key] = true
		stage := time.Now()
		before := w.work
		e, err := w.get(c.packages)
		if err != nil {
			t.Fatal(err)
		}
		if e == nil {
			emitFeasible(map[string]any{"kind": "bounds_unavailable", "name": c.name, "package_key": key, "strict_upper": "unbounded", "reason": "source resolution unavailable"})
			continue
		}
		c.entry = e
		c.domain, err = newBoundDomain(e, req)
		if err != nil {
			t.Fatal(err)
		}
		prepSeconds := time.Since(stage).Seconds()
		curve := []map[string]any{}
		stage = time.Now()
		v, _, err := w.objective(e)(initial, false)
		if err != nil {
			t.Fatal(err)
		}
		curve = append(curve, map[string]any{"stage": "legal_initial", "seconds": time.Since(stage).Seconds(), "dps": v})
		stage = time.Now()
		spg, err := proto.Optimize(w.objective(e), initial, basicConfig(8))
		if err != nil {
			t.Fatal(err)
		}
		curve = append(curve, map[string]any{"stage": "fixed_layout_spg8", "seconds": time.Since(stage).Seconds(), "dps": spg.Value})
		stage = time.Now()
		fast, err := w.fast(e, initial)
		if err != nil {
			t.Fatal(err)
		}
		if spg.Value > fast.Value {
			fast = spg
		}
		if err = fast.State.Validate(45, true); err != nil {
			t.Fatal(err)
		}
		c.state, c.lower = fast.State, fast.Value
		curve = append(curve, map[string]any{"stage": "whole_mains_coordinate4", "seconds": time.Since(stage).Seconds(), "dps": c.lower})
		stage = time.Now()
		c.root = c.domain.box()
		boxSeconds := time.Since(stage).Seconds()
		stage = time.Now()
		natural := c.domain.envelope(c.root, true)
		naturalSeconds := time.Since(stage).Seconds()
		stage = time.Now()
		affine := c.domain.envelope(c.root, false)
		affineSeconds := time.Since(stage).Seconds()
		c.upper, c.modelUpper = math.Min(natural.Upper, affine.Upper), math.Min(natural.ModelUpper, affine.ModelUpper)
		if c.lower > c.modelUpper+1e-6 {
			t.Fatalf("legal L exceeds frozen-DAG enclosure: %s %.9f %.9f", c.name, c.lower, c.modelUpper)
		}
		emitFeasible(map[string]any{"kind": "bounds_root", "name": c.name, "package_key": key, "lower_curves": curve,
			"candidate": w.row(feasibleCandidate{c.packages, c.state, c.lower, e.family}), "coordinates": len(e.coords), "nodes": e.program.NodeCount(),
			"source_unresolved": e.program.HasUnresolvedDependencies(), "strict_upper": boundNumber(c.upper), "model_upper": boundNumber(c.modelUpper),
			"natural_upper": boundNumber(natural.ModelUpper), "affine_upper": boundNumber(affine.ModelUpper), "model_gap": boundNumber(c.modelUpper - c.lower),
			"context_preparation_seconds": prepSeconds, "coordinate_box_seconds": boxSeconds, "natural_seconds": naturalSeconds, "affine_seconds": affineSeconds,
			"natural_support_calls": natural.SupportCalls, "affine_support_calls": affine.SupportCalls, "exact_support_computations": c.domain.calls, "exact_support_cache_hits": c.domain.hits,
			"work": difference(w.work, before)})
		available = append(available, c)
	}
	if len(available) == 0 {
		emitFeasible(map[string]any{"kind": "bounds_summary", "all_controls_unavailable": true, "outer_upper": "unbounded", "full_cartesian_exhausted": false})
		return
	}
	// Deepen only two controls with the highest complete-domain potential. All
	// unresolved source uppers stay +Inf and every other control remains live.
	order := make([]int, len(available))
	for i := range order {
		order[i] = i
	}
	sort.SliceStable(order, func(i, j int) bool { return available[order[i]].modelUpper > available[order[j]].modelUpper })
	scores := map[string]float64{}
	for _, c := range available {
		scores[theoryteams.Key(c.packages)] = c.lower
	}
	deepCount := 0
	for _, i := range order[:min(2, len(order))] {
		c := &available[i]
		stage := time.Now()
		before := w.work
		r, err := w.alternating(c.entry, initial)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > c.lower {
			c.state, c.lower = r.State, r.Value
		}
		if err = c.state.Validate(45, true); err != nil {
			t.Fatal(err)
		}
		if c.lower > c.modelUpper+1e-6 {
			t.Fatal("deep L exceeds enclosure")
		}
		scores[theoryteams.Key(c.packages)] = c.lower
		deepCount++
		emitFeasible(map[string]any{"kind": "bounds_deep_lower", "name": c.name, "seconds": time.Since(stage).Seconds(), "work": difference(w.work, before),
			"candidate": w.row(feasibleCandidate{c.packages, c.state, c.lower, c.entry.family}), "model_gap": boundNumber(c.modelUpper - c.lower)})
	}
	queue := &proto.BoundQueue{}
	regions := map[int]boundsRegion{}
	nextID := 0
	push := func(r boundsRegion) {
		regions[nextID] = r
		if err := queue.Push(proto.BoundRegion{ID: nextID, Upper: r.upper, Potential: r.modelUpper}); err != nil {
			t.Fatal(err)
		}
		nextID++
	}
	for i, c := range available {
		push(boundsRegion{control: i, box: c.root, upper: c.upper, modelUpper: c.modelUpper})
	}
	pruned, splits := 0, 0
	refineStarted := time.Now()
	for step := 0; step < 8; step++ {
		threshold := proto.KthLower(scores, 2)
		node, ok, n := queue.Pop(threshold)
		pruned += n
		if !ok {
			if n > 0 {
				regions = map[int]boundsRegion{}
			}
			break
		}
		r := regions[node.ID]
		delete(regions, node.ID)
		c := &available[r.control]
		// Largest normalized width among currently damage-sensitive coordinates.
		// The derivative proposes a split; it is never an upper bound.
		point := make([]float64, len(r.box))
		for j, b := range r.box {
			point[j] = (b[0]+b[1])/2 + c.entry.baseline[j]
		}
		_, gradient, _, gradErr := c.entry.program.ValueGradient(point)
		axis, best := -1, 0.0
		for j, b := range r.box {
			width := b[1] - b[0]
			rootWidth := c.root[j][1] - c.root[j][0]
			if width <= 1e-9 || rootWidth <= 1e-9 {
				continue
			}
			priority := width / rootWidth
			if gradErr == nil {
				priority = math.Abs(gradient[j]) * width
			}
			if priority > best {
				axis, best = j, priority
			}
		}
		if axis < 0 {
			push(r)
			break
		}
		middle := (r.box[axis][0] + r.box[axis][1]) / 2
		for side := 0; side < 2; side++ {
			box := append([][2]float64(nil), r.box...)
			if side == 0 {
				box[axis][1] = middle
			} else {
				box[axis][0] = middle
			}
			envelope := c.domain.envelope(box, false)
			push(boundsRegion{control: r.control, box: box, depth: r.depth + 1, upper: math.Min(r.upper, envelope.Upper), modelUpper: math.Min(r.modelUpper, envelope.ModelUpper)})
		}
		splits++
		modelMax := math.Inf(-1)
		wouldPrune := 0
		for _, region := range regions {
			modelMax = math.Max(modelMax, region.modelUpper)
			if region.modelUpper < threshold {
				wouldPrune++
			}
		}
		emitFeasible(map[string]any{"kind": "bounds_refinement", "split": splits, "control": c.name, "coordinate": c.entry.coords[axis], "depth": r.depth + 1,
			"seconds_cumulative": time.Since(refineStarted).Seconds(), "strict_pruned": pruned, "live_regions": queue.Len(), "strict_frontier_upper": boundNumber(queue.MaxUpper()),
			"model_frontier_upper": boundNumber(modelMax), "model_only_prunable_regions": wouldPrune, "top2_lower": boundNumber(threshold)})
	}
	finalists := []any{}
	sort.SliceStable(available, func(i, j int) bool { return available[i].lower > available[j].lower })
	for _, c := range available {
		finalists = append(finalists, w.row(feasibleCandidate{c.packages, c.state, c.lower, c.entry.family}))
	}
	count := uint64(len(options))
	outer := count * count * count * count
	emitFeasible(map[string]any{"kind": "bounds_summary", "seconds": time.Since(started).Seconds(), "deep_lower_calls": deepCount, "bound_splits": splits,
		"strict_pruned": pruned, "live_regions": queue.Len(), "strict_frontier_upper": boundNumber(queue.MaxUpper()), "top2_lower": boundNumber(proto.KthLower(scores, 2)),
		"controls_attempted": len(seen), "controls_available": len(available), "packages_per_wearer": count, "cartesian_package_tuples": outer,
		"unexpanded_package_tuples": outer - uint64(len(seen)), "outer_upper": "unbounded", "full_cartesian_exhausted": false, "finalists": finalists,
		"work": w.work, "exact_reuse": "within one immutable capture: target/family and full-input lower solve; support directions capped4096 per control",
		"scope": "bounds/cost diagnostic on named controls; surrogate potential does not prune unresolved source effects; no winning package claim"})
}
