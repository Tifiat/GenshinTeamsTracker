package main

// One capture universe, finite cause/ablation curves, and a separately labeled
// heuristic neighborhood. No numerical upper is used to cover unknown effects.
import (
	"fmt"
	"math"
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

func slackPoint(e *feasibleEntry, s proto.State) []float64 {
	v := make([]float64, len(e.coords))
	at := map[string]int{}
	for i, k := range e.coords {
		at[k] = i
	}
	// The coordinate prefix is mapped by entry.indices, which is request order.
	rolls := s.Rolls()
	for a := range rolls {
		for j := range proto.StatKeys {
			i := e.indices[a][j]
			if i >= 0 {
				v[i] += rolls[a][j] * proto.Values[j]
			}
		}
		prefix := ""
		for _, i := range e.indices[a] {
			if i >= 0 {
				prefix = strings.SplitN(e.coords[i], ".", 2)[0]
				break
			}
		}
		for _, main := range s.Mains[a] {
			if i, ok := at[prefix+"."+main]; ok {
				v[i] += proto.MainValues[main]
			}
		}
	}
	return v
}

func slackParameters(d *boundDomain, box [][2]float64) ([]float64, []float64, func([]float64) (float64, float64)) {
	c, r := make([]float64, len(box)), make([]float64, len(box))
	for i, b := range box {
		c[i] = b[0]/2 + b[1]/2
		r[i] = -d.entry.baseline[i]
	}
	f := func(w []float64) (float64, float64) {
		lo, hi := d.support(w)
		bl, bh, mag := 0.0, 0.0, 0.0
		for i, v := range w {
			a, z := v*box[i][0], v*box[i][1]
			bl += math.Min(a, z)
			bh += math.Max(a, z)
			mag += math.Abs(a) + math.Abs(z)
		}
		g := 2e-12 * (1 + mag)
		return math.Max(lo, bl-g), math.Min(hi, bh+g)
	}
	return c, r, f
}

type slackRegion struct {
	control int
	d       *boundDomain
	box     [][2]float64
	upper   float64
	depth   int
}

func slackContains(s proto.State, mask proto.SupportDomain) bool {
	for a := range mask {
		for slot, m := range mask[a] {
			if m.Mains != nil {
				ok := false
				for _, v := range m.Mains {
					ok = ok || v == s.Mains[a][slot]
				}
				if !ok {
					return false
				}
			}
			var lines uint16
			for _, j := range s.Lines[a][slot] {
				lines |= 1 << j
			}
			if lines&m.Excluded != 0 || lines&m.Required != m.Required {
				return false
			}
		}
	}
	return true
}

// Binary masks partition real main/line choices, so each child uses exact
// Support45(child), not min(support(parent),support(coordinate box)). Priority
// comes from diagnosed nonlinear remainder pressure, not a point gradient.
func slackSplit(mask proto.SupportDomain, e *feasibleEntry, req contracts.OptimizerRequest, preferred proto.State, pressure []float64, root [][2]float64) ([2]proto.SupportDomain, string, bool) {
	out := [2]proto.SupportDomain{mask, mask}
	actor, slot, stat := -1, -1, -1
	best := 0.0
	mainSplit := false
	importance := func(a int, key string, amount float64) float64 {
		for i, c := range e.coords {
			if c == req.Wearers[a].WearerKey+"."+key && root[i][1]-root[i][0] > 1e-10 {
				return pressure[i] * math.Abs(amount) / (root[i][1] - root[i][0])
			}
		}
		return 0
	}
	for a := range mask {
		for s, m := range mask[a] {
			choices := m.Mains
			if choices == nil {
				choices = proto.MainChoices[s]
			}
			if len(choices) > 1 {
				score := 0.0
				for _, key := range choices {
					score = math.Max(score, importance(a, key, proto.MainValues[key]))
				}
				if score > best {
					best, actor, slot, stat, mainSplit = score, a, s, -1, true
				}
			}
			for j, key := range proto.StatKeys {
				bit := uint16(1) << j
				if (m.Required|m.Excluded)&bit != 0 {
					continue
				}
				score := importance(a, key, proto.Values[j]*6)
				if score > best {
					best, actor, slot, stat, mainSplit = score, a, s, j, false
				}
			}
		}
	}
	if actor < 0 {
		return out, "", false
	}
	if mainSplit {
		choices := mask[actor][slot].Mains
		if choices == nil {
			choices = proto.MainChoices[slot]
		}
		pick := choices[0]
		for _, x := range choices {
			if x == preferred.Mains[actor][slot] {
				pick = x
				break
			}
		}
		rest := []string{}
		for _, x := range choices {
			if x != pick {
				rest = append(rest, x)
			}
		}
		out[0][actor][slot].Mains = []string{pick}
		out[1][actor][slot].Mains = rest
		return out, fmt.Sprintf("%s slot%d main=%s vs remaining", req.Wearers[actor].WearerKey, slot, pick), true
	}
	bit := uint16(1) << stat
	out[0][actor][slot].Required |= bit
	out[1][actor][slot].Excluded |= bit
	return out, fmt.Sprintf("%s slot%d line=%s present/absent", req.Wearers[actor].WearerKey, slot, proto.StatKeys[stat]), true
}

func slackBound(t *testing.T, r *slackRegion, planes bool, controls []boundsControl) float64 {
	v := r.d.envelope(r.box, false).ModelUpper
	if planes {
		c, ref, support := slackParameters(r.d, r.box)
		v = math.Min(v, r.d.entry.program.ResearchPlanes(c, ref, support).ModelUpper)
	}
	c := controls[r.control]
	point := slackPoint(c.entry, c.state)
	inside := slackContains(c.state, r.d.restriction)
	for i, x := range point {
		inside = inside && x >= r.box[i][0]-1e-7 && x <= r.box[i][1]+1e-7
	}
	if inside && v+1e-6 < c.lower {
		t.Fatal("branch upper below contained legal witness", c.name, v, c.lower)
	}
	return v
}

func slackCurve(t *testing.T, name string, maskMode, planes bool, req contracts.OptimizerRequest, controls []boundsControl, diagnoses []formula.ResearchDiagnosis, threshold float64) {
	start := time.Now()
	live := []slackRegion{}
	pruned, empty, steps := 0, 0, 0
	axisCounts := map[string]int{}
	for i, c := range controls {
		d, e := newBoundDomain(c.entry, req)
		if e != nil {
			t.Fatal(e)
		}
		r := slackRegion{control: i, d: d, box: d.box()}
		r.upper = slackBound(t, &r, planes, controls)
		live = append(live, r)
	}
	rootSeconds := time.Since(start).Seconds()
	emit := func(label string) {
		upper := math.Inf(-1)
		per := map[string]float64{}
		for _, r := range live {
			upper = math.Max(upper, r.upper)
			per[controls[r.control].name] = math.Max(per[controls[r.control].name], r.upper)
		}
		emitFeasible(map[string]any{"kind": "slack_curve", "variant": name, "level": label, "seconds": time.Since(start).Seconds(), "root_seconds": rootSeconds, "splits": steps, "live_regions": len(live), "model_pruned": pruned, "empty_regions": empty, "model_upper": boundNumber(upper), "top2_lower": threshold, "control_uppers": per, "source_pruned": 0, "source_upper": "unbounded", "outer_upper": "unbounded", "split_reasons": axisCounts})
	}
	emit("root")
	levels := []float64{.5, 2, 6}
	next := 0
	for steps < 64 && len(live) > 0 && time.Since(start).Seconds() < 6 {
		best := 0
		for i := range live {
			if live[i].upper > live[best].upper {
				best = i
			}
		}
		r := live[best]
		live = append(live[:best], live[best+1:]...)
		if r.upper < threshold {
			pruned++
			continue
		}
		c := controls[r.control]
		children := []slackRegion{}
		if maskMode {
			masks, reason, ok := slackSplit(r.d.restriction, c.entry, req, c.state, diagnoses[r.control].Pressure, c.root)
			if !ok {
				live = append(live, r)
				break
			}
			axisCounts[reason]++
			for _, mask := range masks {
				if _, _, err := proto.Support45(proto.LinearWeights{}, mask); err != nil {
					empty++
					continue
				}
				d, err := newBoundDomain(c.entry, req)
				if err != nil {
					t.Fatal(err)
				}
				d.restriction = mask
				children = append(children, slackRegion{control: r.control, d: d, box: d.box(), depth: r.depth + 1})
			}
		} else {
			point := make([]float64, len(r.box))
			for i, b := range r.box {
				point[i] = (b[0]+b[1])/2 + c.entry.baseline[i]
			}
			_, g, _, err := c.entry.program.ValueGradient(point)
			if err != nil {
				t.Fatal(err)
			}
			axis, best := -1, 0.0
			for i, b := range r.box {
				v := math.Abs(g[i]) * (b[1] - b[0])
				if v > best && b[1]-b[0] > 1e-9 {
					axis, best = i, v
				}
			}
			if axis < 0 {
				live = append(live, r)
				break
			}
			axisCounts[c.entry.coords[axis]]++
			mid := (r.box[axis][0] + r.box[axis][1]) / 2
			for side := 0; side < 2; side++ {
				box := append([][2]float64(nil), r.box...)
				if side == 0 {
					box[axis][1] = mid
				} else {
					box[axis][0] = mid
				}
				children = append(children, slackRegion{control: r.control, d: r.d, box: box, depth: r.depth + 1})
			}
		}
		for _, child := range children {
			child.upper = math.Min(r.upper, slackBound(t, &child, planes, controls))
			if child.upper < threshold {
				pruned++
			} else {
				live = append(live, child)
			}
		}
		steps++
		for next < len(levels) && time.Since(start).Seconds() >= levels[next] {
			emit(fmt.Sprintf("first_complete_split_after_%.1fs", levels[next]))
			next++
		}
	}
	emit("final") // A single atomic bound may overrun the research checkpoint.
}

func runTheorySlack(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	start := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	tena := r2Tuple()
	attack := tena
	attack[1] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: "gladiatorsfinale", Count: 2}, {SetUID: "shimenawasreminiscence", Count: 2}}}
	controls := []boundsControl{{name: "none", packages: [4]domain.Package{}}, {name: "saved_packages_control", packages: original}, {name: "tenacity_control", packages: tena}, {name: "attack_two_plus_two_control", packages: attack}}
	diagnoses := make([]formula.ResearchDiagnosis, len(controls))
	scores := map[string]float64{}
	for i := range controls {
		c := &controls[i]
		stage := time.Now()
		c.entry, err = w.get(c.packages)
		if err != nil || c.entry == nil {
			t.Fatal("named control unavailable", err)
		}
		prep := time.Since(stage).Seconds()
		stage = time.Now()
		lower, err := w.fast(c.entry, initial)
		if err != nil {
			t.Fatal(err)
		}
		c.state, c.lower = lower.State, lower.Value
		lowerSeconds := time.Since(stage).Seconds()
		c.domain, err = newBoundDomain(c.entry, req)
		if err != nil {
			t.Fatal(err)
		}
		stage = time.Now()
		c.root = c.domain.box()
		rootBox := time.Since(stage).Seconds()
		stage = time.Now()
		b := c.domain.envelope(c.root, false)
		affineSeconds := time.Since(stage).Seconds()
		c.modelUpper, c.upper = b.ModelUpper, b.Upper
		center, ref, support := slackParameters(c.domain, c.root)
		stage = time.Now()
		planes := c.entry.program.ResearchPlanes(center, ref, support)
		planeSeconds := time.Since(stage).Seconds()
		stage = time.Now()
		diagnoses[i], err = c.entry.program.ResearchDiagnose(center, ref, slackPoint(c.entry, c.state), support)
		if err != nil {
			t.Fatal(err)
		}
		diagSeconds := time.Since(stage).Seconds()
		if c.lower > math.Min(c.modelUpper, planes.ModelUpper)+1e-6 {
			t.Fatal("lower exceeds root enclosure")
		}
		emitFeasible(map[string]any{"kind": "slack_root", "name": c.name, "preparation_seconds": prep, "lower_seconds": lowerSeconds, "box_seconds": rootBox, "affine_seconds": affineSeconds, "planes_seconds": planeSeconds, "diagnosis_seconds": diagSeconds, "baseline_model_upper": boundNumber(c.modelUpper), "planes_model_upper": boundNumber(planes.ModelUpper), "strict_upper": "unbounded", "diagnosis": diagnoses[i], "candidate": w.row(feasibleCandidate{c.packages, c.state, c.lower, c.entry.family})})
	}
	order := []int{0, 1, 2, 3}
	sort.SliceStable(order, func(i, j int) bool { return controls[order[i]].modelUpper > controls[order[j]].modelUpper })
	for _, i := range order[:2] {
		c := &controls[i]
		stage := time.Now()
		before := w.work
		r, err := w.alternating(c.entry, initial)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > c.lower {
			c.state, c.lower = r.State, r.Value
		}
		emitFeasible(map[string]any{"kind": "slack_deep_control", "name": c.name, "seconds": time.Since(stage).Seconds(), "work": difference(w.work, before), "candidate": w.row(feasibleCandidate{c.packages, c.state, c.lower, c.entry.family})})
	}
	// Prove the complete call now hits; separate this saving from every bound.
	i := order[0]
	before := w.work
	stage := time.Now()
	repeat, err := w.alternating(controls[i].entry, initial)
	if err != nil || repeat.Value != controls[i].lower || w.work.Formula != before.Formula || repeat.Evaluations != 0 {
		t.Fatal("complete-input reuse", err)
	}
	emitFeasible(map[string]any{"kind": "slack_complete_reuse", "seconds": time.Since(stage).Seconds(), "work": difference(w.work, before), "extra": w.extra, "same_start": true, "separate_output_keys_preserved": true})
	for _, c := range controls {
		if err = c.state.Validate(45, true); err != nil {
			t.Fatal(err)
		}
		scores[theoryteams.Key(c.packages)] = c.lower
	}
	// Exactly one fixed control is the minimal durable arithmetic replay slice.
	c := controls[2]
	dag := c.entry.program.ResearchExport()
	restored, err := formula.ResearchRestore(dag)
	if err != nil {
		t.Fatal(err)
	}
	point := slackPoint(c.entry, c.state)
	delta := append([]float64(nil), point...)
	for i := range delta {
		delta[i] += c.entry.baseline[i]
	}
	reference, err := c.entry.program.Evaluate(delta)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := restored.Evaluate(delta)
	if err != nil || replay != reference || math.Abs(replay-c.lower) > 1e-7 {
		t.Fatal("reduced DAG replay", replay, c.lower, err)
	}
	emitFeasible(map[string]any{"kind": "slack_replay_fixture", "name": c.name, "dag": dag, "baseline": c.entry.baseline, "absolute_point": point, "candidate": w.row(feasibleCandidate{c.packages, c.state, c.lower, c.entry.family}), "replay_value": replay, "raw_capture_retained": false, "scope": "one reachable reduced source DAG; frozen model only; immutable evidence retained with receipt provenance"})
	threshold := proto.KthLower(scores, 2)
	for _, v := range []struct {
		name          string
		masks, planes bool
	}{{"baseline_coordinate_boxes", false, false}, {"exact_main_line_masks", true, false}, {"planes_coordinate_boxes", false, true}, {"planes_exact_masks", true, true}} {
		slackCurve(t, v.name, v.masks, v.planes, req, controls, diagnoses, threshold)
	}
	runSlackHeuristic(t, factory, req, base, tena, options, initial, controls)
	emitFeasible(map[string]any{"kind": "slack_summary", "seconds": time.Since(start).Seconds(), "named_controls": 4, "source_upper": "unbounded", "outer_upper": "unbounded", "full_catalog_covered": false, "capture_calls_inside_study": 0, "finalist_calls": 0, "work": w.work, "extra": w.extra})
}

func slackSeeds(w *r2World, e *feasibleEntry, initial proto.State) []proto.State {
	_, g, err := w.objective(e)(initial, true)
	if err != nil {
		panic(err)
	}
	out := []proto.State{initial, proto.Seed(initial.Mains, g, 0, 45)}
	mains := initial.Mains
	for a := range mains {
		for slot := 2; slot < 5; slot++ {
			mains[a][slot] = proto.MainChoices[slot][(a+slot+3)%len(proto.MainChoices[slot])]
		}
	}
	return append(out, proto.Seed(mains, g, 1, 45))
}

func runSlackHeuristic(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, anchor [4]domain.Package, options []domain.Package, initial proto.State, controls []boundsControl) {
	start := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	actor := -1
	for a, v := range req.Wearers {
		if v.WearerKey == "furina" {
			actor = a
		}
	}
	if actor < 0 {
		t.Fatal("declared one-wearer Furina neighborhood missing")
	}
	families := map[string]feasibleCandidate{}
	aliases := map[string][]string{}
	unavailable := 0
	screenSeconds, resolveSeconds := 0.0, 0.0
	for _, option := range options {
		p := anchor
		p[actor] = option
		stage := time.Now()
		e, err := w.get(p)
		resolveSeconds += time.Since(stage).Seconds()
		if err != nil {
			t.Fatal(err)
		}
		if e == nil {
			unavailable++
			continue
		}
		aliases[e.family] = append(aliases[e.family], theoryteams.Key(p))
		if _, ok := families[e.family]; ok {
			continue
		}
		stage = time.Now()
		best := feasibleCandidate{packages: p, value: math.Inf(-1), family: e.family}
		for _, s := range slackSeeds(w, e, initial) {
			r, err := proto.Optimize(w.objective(e), s, basicConfig(8))
			if err != nil {
				t.Fatal(err)
			}
			if r.Value > best.value {
				best.state, best.value = r.State, r.Value
			}
		}
		screenSeconds += time.Since(stage).Seconds()
		families[e.family] = best
	}
	rows := r2Sorted(families)
	emitFeasible(map[string]any{"kind": "slack_outer_screen", "seconds": time.Since(start).Seconds(), "resolve_seconds": resolveSeconds, "screen_seconds": screenSeconds, "wearer": req.Wearers[actor].WearerKey, "packages": len(options), "unique_exact_families": len(rows), "unavailable": unavailable, "aliases_by_family": aliases, "independent_starts": 3, "scope": "complete one-wearer neighborhood with other three packages fixed; not Cartesian catalog coverage", "outer_upper": "unbounded"})
	if len(rows) == 0 {
		return
	}
	selected := map[int]string{}
	for i := 0; i < min(4, len(rows)); i++ {
		selected[i] = "screen_leader"
	}
	for _, i := range []int{len(rows) / 2, 3 * len(rows) / 4} {
		if _, ok := selected[i]; !ok {
			selected[i] = "previously_losing_audit"
		}
	}
	indices := []int{}
	for i := range selected {
		indices = append(indices, i)
	}
	sort.Ints(indices)
	for _, i := range indices {
		old := rows[i]
		e, err := w.get(old.packages)
		if err != nil || e == nil {
			t.Fatal(err)
		}
		stage := time.Now()
		r, err := w.fast(e, old.state)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > old.value {
			old.state, old.value = r.State, r.Value
		}
		families[old.family] = old
		emitFeasible(map[string]any{"kind": "slack_heuristic_mains", "screen_rank": i + 1, "reason": selected[i], "seconds": time.Since(stage).Seconds(), "candidate": w.row(old)})
	}
	rows = r2Sorted(families)
	for i := 0; i < min(2, len(rows)); i++ {
		old := rows[i]
		e, err := w.get(old.packages)
		if err != nil || e == nil {
			t.Fatal(err)
		}
		stage := time.Now()
		r, err := w.alternating(e, old.state)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > old.value {
			old.state, old.value = r.State, r.Value
		}
		families[old.family] = old
		emitFeasible(map[string]any{"kind": "slack_heuristic_lines", "seconds": time.Since(stage).Seconds(), "candidate": w.row(old)})
	}
	rows = r2Sorted(families)
	best := rows[0]
	controlBest := math.Inf(-1)
	comparisons := []any{}
	for _, c := range controls {
		controlBest = math.Max(controlBest, c.lower)
		r, ok := families[c.entry.family]
		comparisons = append(comparisons, map[string]any{"control": c.name, "within_scanned_families": ok, "cold_control_lower": c.lower, "heuristic_lower": func() any {
			if ok {
				return r.value
			}
			return nil
		}()})
	}
	if err = best.state.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	emitFeasible(map[string]any{"kind": "slack_heuristic_summary", "seconds": time.Since(start).Seconds(), "best": w.row(best), "best_named_control_lower": controlBest, "measured_difference": best.value - controlBest, "control_comparisons": comparisons, "unique_families": len(rows), "screened_packages": len(options), "mains_families": len(selected), "deep_families": min(2, len(rows)), "work": w.work, "extra": w.extra, "guaranteed_loss": nil, "outer_upper": "unbounded", "scope": "heuristic progressive allocation with two deterministic losing-rank audits; no global or top-K certificate"})
}

func TestSlackMaskUnionSignedSupport(t *testing.T) {
	var mask proto.SupportDomain
	mask[0][4].Mains = []string{"crit_rate", "crit_damage"}
	var w proto.LinearWeights
	for a := range w {
		w[a] = map[string]float64{"crit_rate": -2, "crit_damage": 3, "atk_percent": -1}
	}
	lo, hi, err := proto.Support45(w, mask)
	if err != nil {
		t.Fatal(err)
	}
	for _, line := range []int{-1, 2, 3} {
		children := [2]proto.SupportDomain{mask, mask}
		if line < 0 {
			children[0][0][4].Mains = []string{"crit_rate"}
			children[1][0][4].Mains = []string{"crit_damage"}
		} else {
			children[0][0][4].Required |= 1 << line
			children[1][0][4].Excluded |= 1 << line
		}
		cl, ch := math.Inf(1), math.Inf(-1)
		for _, child := range children {
			a, z, e := proto.Support45(w, child)
			if e == nil {
				cl = math.Min(cl, a)
				ch = math.Max(ch, z)
			}
		}
		if math.Abs(lo-cl) > 1e-8 || math.Abs(hi-ch) > 1e-8 {
			t.Fatal("mask union loses extrema", line, lo, hi, cl, ch)
		}
	}
}
