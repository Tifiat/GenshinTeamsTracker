package search

// Resumable real-vector regions for the neutral All Sets coordinator. A caller
// can compare the next region with OTHER packages after each bound or small
// batch of leaves. Suspending never drops regions or rebuilds their search.
// This uses the same reduced arithmetic and legality as the atomic inventory
// step; Selected stays on its old route until the common-core transfer gate.
import (
	"container/heap"
	"context"
	"fmt"
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

type InventoryFrontier struct {
	engine        *Engine
	anchor        domain.Assignment
	actor         int
	program       *formula.ArtifactProgram
	vectors       map[int64][]float64
	ref, x        []float64
	best          ScoredAssignment
	bestObjective objective
	rows          map[[5]int64]ScoredAssignment
	seen          map[[5]int64]bool
	warm          [][5]int64
	queue         inventoryRegionQueue
	serial        int
	step          ActorStep
}

// The supplied potential must describe this exact anchor/package. It is only
// a scheduling hint here: fresh child bounds still establish pruning authority.
func (engine *Engine) NewWearerFrontier(anchor domain.Assignment, actor int, potential float64) (*InventoryFrontier, error) {
	if actor < 0 || actor >= 4 || math.IsNaN(potential) {
		return nil, fmt.Errorf("invalid inventory frontier")
	}
	if err := engine.domain.ValidateAssignment(anchor); err != nil {
		return nil, err
	}
	dense, err := engine.domain.DenseDeltas(anchor)
	if err != nil {
		return nil, err
	}
	program, err := engine.panel.ArtifactProgram(dense, actor)
	if err != nil {
		return nil, err
	}
	vectors, ref, err := engine.domain.ArtifactVectors(actor, program.Coordinates())
	if err != nil {
		return nil, err
	}
	dps, err := engine.score(anchor)
	if err != nil {
		return nil, err
	}
	objective, err := engine.objective(anchor, dps)
	if err != nil {
		return nil, err
	}
	f := &InventoryFrontier{engine: engine, anchor: anchor, actor: actor, program: program, vectors: vectors, ref: ref,
		x: make([]float64, len(ref)), best: ScoredAssignment{anchor, dps, "inventory_anchor"}, bestObjective: objective,
		rows: map[[5]int64]ScoredAssignment{}, seen: map[[5]int64]bool{},
		step: ActorStep{Cycle: 1, WearerKey: engine.domain.Wearers[actor].WearerKey, AnchorDPS: dps, ReducedNodes: program.NodeCount()}}
	f.rows[anchor[actor]] = f.best
	local := make([]float64, len(ref))
	positions := map[string]int{}
	for i, key := range engine.panel.Coordinates() {
		positions[key] = i
	}
	for i, key := range program.Coordinates() {
		local[i] = dense[positions[key]]
	}
	_, weights, _, err := program.ValueGradient(local)
	if err != nil {
		return nil, err
	}
	priority := map[int64]float64{}
	for id, vector := range vectors {
		for i, x := range vector {
			priority[id] += weights[i] * x
		}
	}
	seed, err := engine.domain.PackageSeed(anchor, actor, domain.Package{Sets: engine.domain.Wearers[actor].SelectedSets}, priority)
	if err != nil {
		return nil, err
	}
	f.warm = append(f.warm, seed[actor])
	for _, lane := range engine.lanes(anchor, actor) {
		ids := [5]int64{}
		for slot, pool := range lane.pools {
			sort.SliceStable(pool, func(i, j int) bool {
				if priority[pool[i]] != priority[pool[j]] {
					return priority[pool[i]] > priority[pool[j]]
				}
				return pool[i] < pool[j]
			})
			ids[slot] = pool[0]
		}
		f.warm = append(f.warm, ids)
		f.push(inventoryRegion{pools: lane.pools, count: lane.raw, upper: math.Inf(1), potential: potential})
		f.step.RawPhysicalBuilds = saturatingAdd(f.step.RawPhysicalBuilds, lane.raw)
	}
	return f, nil
}

func (f *InventoryFrontier) push(r inventoryRegion) {
	r.order = f.serial
	f.serial++
	heap.Push(&f.queue, r)
}

func (f *InventoryFrontier) Potential() float64 {
	if len(f.queue) == 0 {
		return math.Inf(-1)
	}
	return f.queue[0].potential
}
func (f *InventoryFrontier) Done() bool             { return len(f.queue) == 0 && len(f.warm) == 0 }
func (f *InventoryFrontier) Expanded() int          { return f.step.Expanded }
func (f *InventoryFrontier) Best() ScoredAssignment { return f.best }

func (f *InventoryFrontier) point(ctx context.Context, ids [5]int64) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if _, ok := f.rows[ids]; ok || f.seen[ids] {
		return nil
	}
	f.seen[ids] = true
	// Invalid complete points also consume work. Sparse-package filters must
	// not hide arbitrarily much validation outside the shared allowance.
	f.step.Expanded++
	trial := f.anchor
	trial[f.actor] = ids
	if f.engine.domain.ValidateAssignment(trial) != nil {
		f.step.InvalidAssignments++
		return nil
	}
	clear(f.x)
	for _, id := range ids {
		for i, x := range f.vectors[id] {
			f.x[i] += x
		}
	}
	for i := range f.x {
		f.x[i] -= f.ref[i]
	}
	v, err := f.program.Evaluate(f.x)
	if err != nil {
		return err
	}
	f.step.CompleteEvaluations++
	o, err := f.engine.objective(trial, v)
	if err != nil {
		return err
	}
	score := ScoredAssignment{trial, v, "inventory_frontier"}
	if betterObjective(o, f.bestObjective) {
		f.best, f.bestObjective = score, o
	}
	f.rows[ids] = score
	if len(f.rows) > 2*f.engine.config.FinalistLimit {
		rows := make([]ScoredAssignment, 0, len(f.rows))
		for _, row := range f.rows {
			rows = append(rows, row)
		}
		f.engine.sortScored(rows)
		f.rows = map[[5]int64]ScoredAssignment{}
		for _, row := range rows[:f.engine.config.FinalistLimit] {
			f.rows[row.Assignment[f.actor]] = row
		}
	}
	return nil
}

// Advance performs at most allowance units; it yields after one region bound
// even when allowance remains. Exact enumeration retains its mixed-radix cursor
// and can yield mid-region. No per-package 20k budget is renewed on resumption.
func (f *InventoryFrontier) Advance(ctx context.Context, allowance int) error {
	if allowance <= 0 {
		return nil
	}
	end := f.step.Expanded + allowance
	for len(f.warm) > 0 && f.step.Expanded < end {
		if err := f.point(ctx, f.warm[0]); err != nil {
			return err
		}
		f.warm = f.warm[1:]
	}
	for len(f.queue) > 0 && f.step.Expanded < end {
		if err := ctx.Err(); err != nil {
			return err
		}
		r := heap.Pop(&f.queue).(inventoryRegion)
		if f.bestObjective.feasible && r.upper < f.best.DPS-1e-7*(1+math.Abs(f.best.DPS)) {
			f.step.BoundPrunedBuilds = saturatingAdd(f.step.BoundPrunedBuilds, r.count-r.offset)
			continue
		}
		if !r.bounded {
			groups := make([][][]float64, 5)
			for slot, pool := range r.pools {
				for _, id := range pool {
					groups[slot] = append(groups[slot], f.vectors[id])
				}
			}
			r.potential = f.program.Potential(groups, f.ref)
			if !f.program.HasUnresolvedDependencies() {
				r.upper = r.potential
			}
			r.bounded = true
			f.step.Expanded++
			f.step.BoundEvaluations++
			f.push(r)
			return nil
		}
		work, split := 0, 0
		for slot, pool := range r.pools {
			work += len(pool)
			if len(pool) > len(r.pools[split]) {
				split = slot
			}
		}
		exactLimit := int64(max(256, 4*work*(len(f.ref)+1)))
		if r.count <= exactLimit {
			for r.offset < r.count && f.step.Expanded < end {
				n := r.offset
				ids := [5]int64{}
				for slot := 4; slot >= 0; slot-- {
					ids[slot] = r.pools[slot][n%int64(len(r.pools[slot]))]
					n /= int64(len(r.pools[slot]))
				}
				if err := f.point(ctx, ids); err != nil {
					f.push(r)
					return err
				}
				r.offset++
			}
			if r.offset < r.count {
				f.push(r)
			}
			// Let other packages compete after every small exact batch too.
			return nil
		}
		left, right := r, r
		mid := len(r.pools[split]) / 2
		left.pools[split], right.pools[split] = r.pools[split][:mid], r.pools[split][mid:]
		left.count, right.count = 1, 1
		for slot := 0; slot < 5; slot++ {
			left.count = saturatingMultiply(left.count, int64(len(left.pools[slot])))
			right.count = saturatingMultiply(right.count, int64(len(right.pools[slot])))
		}
		left.bounded, right.bounded = false, false
		f.push(left)
		f.push(right)
	}
	return nil
}

// Snapshot verifies retained points against the parent aggregate and reports
// every pending region. Model-based caller deferral never increments Pruned.
func (f *InventoryFrontier) Snapshot() (ActorStep, error) {
	out := f.step
	for _, r := range f.queue {
		out.BudgetUnexpanded = saturatingAdd(out.BudgetUnexpanded, r.count-r.offset)
	}
	f.rows[f.best.Assignment[f.actor]] = f.best
	f.rows[f.anchor[f.actor]] = ScoredAssignment{f.anchor, f.step.AnchorDPS, "inventory_anchor"}
	for _, row := range f.rows {
		v, err := f.engine.score(row.Assignment)
		if err != nil {
			return out, err
		}
		if row.Assignment != f.anchor && math.Abs(v-row.DPS) > 1e-7*(1+math.Abs(v)) {
			return out, fmt.Errorf("frontier formula parity mismatch")
		}
		row.DPS = v
		out.Finalists = append(out.Finalists, row)
	}
	f.engine.sortScored(out.Finalists)
	if len(out.Finalists) > f.engine.config.FinalistLimit {
		out.Finalists = out.Finalists[:f.engine.config.FinalistLimit]
	}
	return out, nil
}
