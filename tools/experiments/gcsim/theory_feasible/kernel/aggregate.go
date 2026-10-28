package theoryprototype

import (
	"fmt"
	"math"
	"sort"
)

const aggregateSubsets = 1 << 10

// AggregateUpgradeTotals are the additional roll units, summed by stat, for each
// actor. Initial one-roll line counts remain fixed by a State's line incidence.
type AggregateUpgradeTotals [4][10]float64

// AggregateObjective is evaluated on a checked flow witness. Its score and
// gradient must depend on total stat rolls and fixed mains, not on which
// eligible line receives an upgrade; that restriction makes aggregation exact.
type AggregateObjective func(State, bool) (float64, [4][10]float64, error)

// AggregateConfig controls a fixed-incidence Frank-Wolfe search. Polish enables
// a bounded quarter-unit neighborhood pass after the continuous search.
type AggregateConfig struct {
	Budget        float64
	MaxIterations int
	Polish        bool
}

// AggregateUpgrades sums the line-level upgrade witness by stat. The caller is
// expected to pass a valid State; invalid line indices are ignored defensively.
func AggregateUpgrades(state State) AggregateUpgradeTotals {
	var out AggregateUpgradeTotals
	for actor := range state.Lines {
		for slot := range state.Lines[actor] {
			for line, stat := range state.Lines[actor][slot] {
				if stat >= 0 && stat < len(StatKeys) {
					out[actor][stat] += state.Upgrades[actor][slot][line]
				}
			}
		}
	}
	return out
}

func aggregateTemplate(state State, budget float64) (State, error) {
	state.Upgrades = [4][5][4]float64{}
	if err := state.Validate(budget, false); err != nil {
		return State{}, err
	}
	return state, nil
}

func validAggregateMask(mask uint16) bool {
	return mask&^uint16(aggregateSubsets-1) == 0
}

// AggregateSubsetCapacity returns the exact upper bound on total (base plus
// upgrade) rolls in subset for one actor, with mains and line identities fixed.
// The upgrade part is min(actor budget, five per slot incident to subset).
func AggregateSubsetCapacity(state State, actor int, subset uint16, budget float64) (float64, error) {
	budget = normalizedBudget(budget)
	if actor < 0 || actor >= 4 {
		return 0, fmt.Errorf("invalid actor %d", actor)
	}
	if !validAggregateMask(subset) {
		return 0, fmt.Errorf("invalid stat subset mask %#x", subset)
	}
	template, err := aggregateTemplate(state, budget)
	if err != nil {
		return 0, err
	}
	if subset == 0 {
		return 0, nil
	}
	base, support := 0.0, 0
	for slot := range template.Lines[actor] {
		incident := false
		for _, stat := range template.Lines[actor][slot] {
			if subset&uint16(1<<stat) != 0 {
				base++
				incident = true
			}
		}
		if incident {
			support++
		}
	}
	extra := math.Min(budget-20, 5*float64(support))
	return base + extra, nil
}

// DecomposeAggregate constructs an exact line-level witness for aggregate
// upgrades under the template's fixed mains and four-line incidence. The
// transportation max-flow has stat demands, eligible stat-to-slot arcs, and
// capacity five at each slot. Grid mode uses integer quarter-roll capacities.
func DecomposeAggregate(template State, upgrades AggregateUpgradeTotals, budget float64, grid bool) (State, error) {
	budget = normalizedBudget(budget)
	base, err := aggregateTemplate(template, budget)
	if err != nil {
		return State{}, err
	}
	out := base
	for actor := range out.Lines {
		allocation, err := decomposeAggregateActor(base, actor, upgrades[actor], budget, grid)
		if err != nil {
			return State{}, err
		}
		out.Upgrades[actor] = allocation
	}
	if err := out.Validate(budget, grid); err != nil {
		return State{}, fmt.Errorf("decomposed state failed validation: %w", err)
	}
	got := AggregateUpgrades(out)
	for actor := range got {
		for stat, want := range upgrades[actor] {
			if math.Abs(got[actor][stat]-want) > 1e-8*(1+math.Abs(want)) {
				return State{}, fmt.Errorf("aggregate witness mismatch actor %d stat %d: got %.12g want %.12g", actor, stat, got[actor][stat], want)
			}
		}
	}
	return out, nil
}

func decomposeAggregateActor(template State, actor int, demand [10]float64, budget float64, grid bool) ([5][4]float64, error) {
	var result [5][4]float64
	if actor < 0 || actor >= 4 {
		return result, fmt.Errorf("invalid actor %d", actor)
	}
	lineAt, err := aggregateLineMap(template, actor)
	if err != nil {
		return result, err
	}
	if grid {
		return decomposeAggregateActorGrid(lineAt, actor, demand, budget)
	}
	return decomposeAggregateActorFloat(lineAt, actor, demand, budget)
}

func aggregateLineMap(template State, actor int) ([5][10]int, error) {
	lineAt := [5][10]int{}
	for slot := range lineAt {
		for stat := range lineAt[slot] {
			lineAt[slot][stat] = -1
		}
		for line, stat := range template.Lines[actor][slot] {
			if stat < 0 || stat >= len(StatKeys) || lineAt[slot][stat] >= 0 {
				return lineAt, fmt.Errorf("actor %d slot %d has invalid fixed incidence", actor, slot)
			}
			lineAt[slot][stat] = line
		}
	}
	return lineAt, nil
}

func decomposeAggregateActorGrid(lineAt [5][10]int, actor int, demand [10]float64, budget float64) ([5][4]float64, error) {
	var result [5][4]float64
	var units [10]int64
	var total int64
	for stat, value := range demand {
		if !finite(value) || value < -1e-9 {
			return result, fmt.Errorf("actor %d stat %d has invalid aggregate upgrade %g", actor, stat, value)
		}
		if math.Abs(value*4-math.Round(value*4)) > 1e-8 {
			return result, fmt.Errorf("actor %d stat %d is off quarter grid", actor, stat)
		}
		units[stat] = int64(math.Round(math.Max(0, value) * 4))
		total += units[stat]
	}
	capUnits := int64(math.Floor((budget-20)*4 + 1e-9))
	if total > capUnits {
		return result, fmt.Errorf("actor %d aggregate upgrades use %g; budget allows %g", actor, float64(total)/4, float64(capUnits)/4)
	}
	if total == 0 {
		return result, nil
	}

	const source, statBase, slotBase, sink = 0, 1, 11, 16
	graph := newIntegerFlowGraph(17)
	for stat, amount := range units {
		graph.add(source, statBase+stat, amount)
	}
	refs := [10][5]intFlowRef{}
	for stat := range refs {
		for slot := range refs[stat] {
			refs[stat][slot].edge = -1
			if lineAt[slot][stat] >= 0 {
				refs[stat][slot] = intFlowRef{from: statBase + stat, edge: graph.add(statBase+stat, slotBase+slot, total)}
			}
		}
	}
	for slot := 0; slot < 5; slot++ {
		graph.add(slotBase+slot, sink, 20)
	}
	if got := graph.maxFlow(source, sink, total); got != total {
		return result, fmt.Errorf("actor %d aggregate demand has no fixed-incidence witness: flow %d/%d quarter units", actor, got, total)
	}
	for stat := range refs {
		for slot, ref := range refs[stat] {
			if ref.edge < 0 {
				continue
			}
			flow := graph.flow(ref.from, ref.edge)
			line := lineAt[slot][stat]
			result[slot][line] = float64(flow) / 4
		}
	}
	return result, nil
}

func decomposeAggregateActorFloat(lineAt [5][10]int, actor int, demand [10]float64, budget float64) ([5][4]float64, error) {
	var result [5][4]float64
	total, cap := 0.0, budget-20
	for stat, value := range demand {
		if !finite(value) || value < -1e-9 {
			return result, fmt.Errorf("actor %d stat %d has invalid aggregate upgrade %g", actor, stat, value)
		}
		if value < 0 {
			value = 0
		}
		demand[stat] = value
		total += value
	}
	if total > cap+1e-8 {
		return result, fmt.Errorf("actor %d aggregate upgrades use %g; budget allows %g", actor, total, cap)
	}
	if total <= 1e-12 {
		return result, nil
	}
	const source, statBase, slotBase, sink = 0, 1, 11, 16
	graph := newFloatFlowGraph(17)
	for stat, amount := range demand {
		graph.add(source, statBase+stat, amount)
	}
	refs := [10][5]intFlowRef{}
	for stat := range refs {
		for slot := range refs[stat] {
			refs[stat][slot].edge = -1
			if lineAt[slot][stat] >= 0 {
				refs[stat][slot] = intFlowRef{from: statBase + stat, edge: graph.add(statBase+stat, slotBase+slot, total)}
			}
		}
	}
	for slot := 0; slot < 5; slot++ {
		graph.add(slotBase+slot, sink, 5)
	}
	if got := graph.maxFlow(source, sink, total); got < total-1e-8*(1+total) {
		return result, fmt.Errorf("actor %d aggregate demand has no fixed-incidence witness: flow %.12g/%.12g", actor, got, total)
	}
	for stat := range refs {
		for slot, ref := range refs[stat] {
			if ref.edge < 0 {
				continue
			}
			flow := graph.flow(ref.from, ref.edge)
			if math.Abs(flow) < 1e-12 {
				flow = 0
			}
			line := lineAt[slot][stat]
			result[slot][line] = flow
		}
	}
	return result, nil
}

// OptimizeAggregate searches only upgrade totals for a fixed main/line layout.
// Its feasible region is the exact projection of the slot-capacity flow
// polytope. The nonlinear search is local, not a global-optimum certificate;
// final quarter totals are decomposed and validated before return.
func OptimizeAggregate(obj AggregateObjective, initial State, cfg AggregateConfig) (Result, error) {
	var result Result
	if obj == nil {
		return result, fmt.Errorf("nil aggregate objective")
	}
	cfg.Budget = normalizedBudget(cfg.Budget)
	if !finite(cfg.Budget) || cfg.Budget < 20 || cfg.Budget > 45 {
		return result, fmt.Errorf("budget must be finite and in [20,45]")
	}
	if cfg.MaxIterations < 0 {
		return result, fmt.Errorf("negative aggregate iteration limit")
	}
	if cfg.MaxIterations == 0 {
		cfg.MaxIterations = 80
	}
	if err := initial.Validate(cfg.Budget, false); err != nil {
		return result, fmt.Errorf("invalid initial state: %w", err)
	}
	base, err := aggregateTemplate(initial, cfg.Budget)
	if err != nil {
		return result, err
	}
	current := AggregateUpgrades(initial)
	if _, err := DecomposeAggregate(base, current, cfg.Budget, false); err != nil {
		return result, fmt.Errorf("initial aggregate has no witness: %w", err)
	}
	evaluations := 0
	evaluate := func(upgrades AggregateUpgradeTotals, gradient bool) (float64, [4][10]float64, error) {
		evaluations++
		state, err := DecomposeAggregate(base, upgrades, cfg.Budget, false)
		if err != nil {
			return 0, [4][10]float64{}, err
		}
		value, g, err := obj(state, gradient)
		if err != nil {
			return 0, g, err
		}
		if !finite(value) {
			return 0, g, fmt.Errorf("aggregate objective returned non-finite value")
		}
		if gradient {
			for actor := range g {
				for stat, component := range g[actor] {
					if !finite(component) {
						return 0, g, fmt.Errorf("aggregate gradient actor %d stat %d is non-finite", actor, stat)
					}
				}
			}
		}
		return value, g, nil
	}

	value, gradient, err := evaluate(current, true)
	if err != nil {
		return Result{}, err
	}
	continuousValue := value
	ranks := [4][aggregateSubsets]float64{}
	for actor := range ranks {
		ranks[actor] = aggregateRankTable(base, actor, cfg.Budget-20)
	}
	stop := "aggregate_iteration_cap"
	iterations := 0
	for ; iterations < cfg.MaxIterations; iterations++ {
		target := aggregateLinearOracle(gradient, ranks)
		gap := 0.0
		for actor := range current {
			for stat := range current[actor] {
				gap += gradient[actor][stat] * (target[actor][stat] - current[actor][stat])
			}
		}
		if gap <= 1e-10*(1+math.Abs(value)) {
			stop = "aggregate_stationarity"
			break
		}
		accepted := false
		for alpha := 1.0; alpha >= 1.0/65536; alpha *= .5 {
			candidate := blendAggregate(current, target, alpha)
			candidateValue, candidateGradient, err := evaluate(candidate, true)
			if err != nil {
				return Result{State: initial, Value: value, Evaluations: evaluations, Iterations: iterations, Stop: "aggregate_evaluation_error", ContinuousValue: continuousValue}, err
			}
			if candidateValue > value+1e-12*(1+math.Abs(value)) {
				current, value, gradient = candidate, candidateValue, candidateGradient
				continuousValue = math.Max(continuousValue, value)
				accepted = true
				break
			}
		}
		if !accepted {
			stop = "aggregate_stalled"
			break
		}
	}
	if iterations == cfg.MaxIterations {
		stop = "aggregate_iteration_cap"
	}

	quarter := floorAggregateQuarter(current)
	quarterState, err := DecomposeAggregate(base, quarter, cfg.Budget, true)
	if err != nil {
		return Result{State: initial, Value: value, Evaluations: evaluations, Iterations: iterations, Stop: "quarter_decomposition_error", ContinuousValue: continuousValue}, err
	}
	quarterValue, _, err := evaluate(quarter, false)
	if err != nil {
		return Result{State: quarterState, Value: value, Evaluations: evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: continuousValue}, err
	}
	inputOnGrid := initial.Validate(cfg.Budget, true) == nil
	if inputOnGrid && value > quarterValue+1e-12*(1+math.Abs(quarterValue)) {
		inputValue, _, err := evaluate(AggregateUpgrades(initial), false)
		if err != nil {
			return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: continuousValue}, err
		}
		if inputValue > quarterValue {
			quarter = AggregateUpgrades(initial)
			quarterValue = inputValue
			quarterState, err = DecomposeAggregate(base, quarter, cfg.Budget, true)
			if err != nil {
				return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: "quarter_decomposition_error", ContinuousValue: continuousValue}, err
			}
		}
	}
	if cfg.Polish {
		var polishCapped bool
		quarter, quarterValue, polishCapped, err = polishAggregateQuarter(base, quarter, quarterValue, cfg.Budget, evaluate)
		if err != nil {
			return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: "quarter_polish_error", ContinuousValue: continuousValue}, err
		}
		if polishCapped {
			stop += "+quarter_move_cap"
		} else {
			stop += "+quarter_stable"
		}
		quarterState, err = DecomposeAggregate(base, quarter, cfg.Budget, true)
		if err != nil {
			return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: "quarter_decomposition_error", ContinuousValue: continuousValue}, err
		}
	}
	if err := quarterState.Validate(cfg.Budget, true); err != nil {
		return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: "invalid_final_state", ContinuousValue: continuousValue}, err
	}
	return Result{State: quarterState, Value: quarterValue, Evaluations: evaluations, Iterations: iterations, Stop: stop, ContinuousValue: continuousValue}, nil
}

func blendAggregate(from, to AggregateUpgradeTotals, alpha float64) AggregateUpgradeTotals {
	out := from
	for actor := range out {
		for stat := range out[actor] {
			out[actor][stat] += alpha * (to[actor][stat] - from[actor][stat])
		}
	}
	return out
}

func floorAggregateQuarter(in AggregateUpgradeTotals) AggregateUpgradeTotals {
	out := in
	for actor := range out {
		for stat, value := range out[actor] {
			if value < 0 && value > -1e-9 {
				value = 0
			}
			out[actor][stat] = math.Floor(value*4+1e-9) / 4
		}
	}
	return out
}

func aggregateRankTable(base State, actor int, cap float64) [aggregateSubsets]float64 {
	var ranks [aggregateSubsets]float64
	for mask := 1; mask < aggregateSubsets; mask++ {
		support := 0
		for slot := range base.Lines[actor] {
			for _, stat := range base.Lines[actor][slot] {
				if mask&(1<<stat) != 0 {
					support++
					break
				}
			}
		}
		ranks[mask] = math.Min(cap, 5*float64(support))
	}
	return ranks
}

func aggregateLinearOracle(gradient [4][10]float64, ranks [4][aggregateSubsets]float64) AggregateUpgradeTotals {
	var out AggregateUpgradeTotals
	for actor := range out {
		order := make([]int, len(StatKeys))
		for stat := range order {
			order[stat] = stat
		}
		sort.SliceStable(order, func(i, j int) bool {
			return gradient[actor][order[i]] > gradient[actor][order[j]]
		})
		mask := 0
		for _, stat := range order {
			if gradient[actor][stat] <= 0 {
				break
			}
			next := mask | (1 << stat)
			increment := ranks[actor][next] - ranks[actor][mask]
			if increment < 0 && increment > -1e-10 {
				increment = 0
			}
			out[actor][stat] = increment
			mask = next
		}
	}
	return out
}

func polishAggregateQuarter(base State, current AggregateUpgradeTotals, value float64, budget float64,
	evaluate func(AggregateUpgradeTotals, bool) (float64, [4][10]float64, error)) (AggregateUpgradeTotals, float64, bool, error) {
	const maxMoves = 128
	lineMaps := [4][5][10]int{}
	for actor := range lineMaps {
		lineAt, err := aggregateLineMap(base, actor)
		if err != nil {
			return current, value, false, err
		}
		lineMaps[actor] = lineAt
	}
	for move := 0; move < maxMoves; move++ {
		best, bestValue := current, value
		consider := func(candidate AggregateUpgradeTotals, actor int) error {
			if actor >= 0 {
				if _, err := decomposeAggregateActorGrid(lineMaps[actor], actor, candidate[actor], budget); err != nil {
					return nil
				}
			}
			candidateValue, _, err := evaluate(candidate, false)
			if err != nil {
				return err
			}
			if candidateValue > bestValue+1e-12*(1+math.Abs(bestValue)) {
				best, bestValue = candidate, candidateValue
			}
			return nil
		}
		for actor := range current {
			for stat := range current[actor] {
				candidate := current
				candidate[actor][stat] += .25
				if err := consider(candidate, actor); err != nil {
					return current, value, false, err
				}
				if current[actor][stat] >= .25-1e-9 {
					candidate = current
					candidate[actor][stat] -= .25
					if err := consider(candidate, actor); err != nil {
						return current, value, false, err
					}
					for other := range current[actor] {
						if other == stat {
							continue
						}
						candidate = current
						candidate[actor][stat] -= .25
						candidate[actor][other] += .25
						if err := consider(candidate, actor); err != nil {
							return current, value, false, err
						}
					}
				}
			}
		}
		if best == current {
			return current, value, false, nil
		}
		current, value = best, bestValue
	}
	return current, value, true, nil
}

type intFlowRef struct{ from, edge int }

type integerFlowEdge struct {
	to, rev int
	cap     int64
	initial int64
}
type integerFlowGraph struct {
	edges [][]integerFlowEdge
	level []int
	next  []int
}

func newIntegerFlowGraph(nodes int) *integerFlowGraph {
	return &integerFlowGraph{edges: make([][]integerFlowEdge, nodes), level: make([]int, nodes), next: make([]int, nodes)}
}
func (g *integerFlowGraph) add(from, to int, cap int64) int {
	idx := len(g.edges[from])
	g.edges[from] = append(g.edges[from], integerFlowEdge{to: to, rev: len(g.edges[to]), cap: cap, initial: cap})
	g.edges[to] = append(g.edges[to], integerFlowEdge{to: from, rev: idx})
	return idx
}
func (g *integerFlowGraph) flow(from, edge int) int64 {
	e := g.edges[from][edge]
	return e.initial - e.cap
}
func (g *integerFlowGraph) maxFlow(source, sink int, limit int64) int64 {
	var total int64
	for total < limit && g.levels(source, sink) {
		for i := range g.next {
			g.next[i] = 0
		}
		for total < limit {
			pushed := g.push(source, sink, limit-total)
			if pushed == 0 {
				break
			}
			total += pushed
		}
	}
	return total
}
func (g *integerFlowGraph) levels(source, sink int) bool {
	for i := range g.level {
		g.level[i] = -1
	}
	queue := make([]int, 1, len(g.edges))
	queue[0] = source
	g.level[source] = 0
	for head := 0; head < len(queue); head++ {
		v := queue[head]
		for _, e := range g.edges[v] {
			if e.cap > 0 && g.level[e.to] < 0 {
				g.level[e.to] = g.level[v] + 1
				queue = append(queue, e.to)
			}
		}
	}
	return g.level[sink] >= 0
}
func (g *integerFlowGraph) push(v, sink int, amount int64) int64 {
	if v == sink {
		return amount
	}
	for g.next[v] < len(g.edges[v]) {
		i := g.next[v]
		e := &g.edges[v][i]
		if e.cap > 0 && g.level[e.to] == g.level[v]+1 {
			pushed := g.push(e.to, sink, minInt64(amount, e.cap))
			if pushed > 0 {
				e.cap -= pushed
				g.edges[e.to][e.rev].cap += pushed
				return pushed
			}
		}
		g.next[v]++
	}
	return 0
}

func minInt64(a, b int64) int64 {
	if a < b {
		return a
	}
	return b
}

type floatFlowEdge struct {
	to, rev int
	cap     float64
	initial float64
}
type floatFlowGraph struct {
	edges [][]floatFlowEdge
	level []int
	next  []int
}

func newFloatFlowGraph(nodes int) *floatFlowGraph {
	return &floatFlowGraph{edges: make([][]floatFlowEdge, nodes), level: make([]int, nodes), next: make([]int, nodes)}
}
func (g *floatFlowGraph) add(from, to int, cap float64) int {
	idx := len(g.edges[from])
	g.edges[from] = append(g.edges[from], floatFlowEdge{to: to, rev: len(g.edges[to]), cap: cap, initial: cap})
	g.edges[to] = append(g.edges[to], floatFlowEdge{to: from, rev: idx})
	return idx
}
func (g *floatFlowGraph) flow(from, edge int) float64 {
	e := g.edges[from][edge]
	return e.initial - e.cap
}
func (g *floatFlowGraph) maxFlow(source, sink int, limit float64) float64 {
	const eps = 1e-11
	total := 0.0
	for total < limit-eps && g.levels(source, sink, eps) {
		for i := range g.next {
			g.next[i] = 0
		}
		for total < limit-eps {
			pushed := g.push(source, sink, limit-total, eps)
			if pushed <= eps {
				break
			}
			total += pushed
		}
	}
	return total
}
func (g *floatFlowGraph) levels(source, sink int, eps float64) bool {
	for i := range g.level {
		g.level[i] = -1
	}
	queue := make([]int, 1, len(g.edges))
	queue[0] = source
	g.level[source] = 0
	for head := 0; head < len(queue); head++ {
		v := queue[head]
		for _, e := range g.edges[v] {
			if e.cap > eps && g.level[e.to] < 0 {
				g.level[e.to] = g.level[v] + 1
				queue = append(queue, e.to)
			}
		}
	}
	return g.level[sink] >= 0
}
func (g *floatFlowGraph) push(v, sink int, amount, eps float64) float64 {
	if v == sink {
		return amount
	}
	for g.next[v] < len(g.edges[v]) {
		i := g.next[v]
		e := &g.edges[v][i]
		if e.cap > eps && g.level[e.to] == g.level[v]+1 {
			pushed := g.push(e.to, sink, math.Min(amount, e.cap), eps)
			if pushed > eps {
				e.cap -= pushed
				if e.cap < eps {
					e.cap = 0
				}
				g.edges[e.to][e.rev].cap += pushed
				return pushed
			}
		}
		g.next[v]++
	}
	return 0
}
