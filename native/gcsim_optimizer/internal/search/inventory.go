package search

import (
	"container/heap"
	"context"
	"errors"
	"fmt"
	"math"
	"math/bits"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// Unlike a beam, a region is discarded only by a fixed-context numerical upper
// enclosure. A work/deadline stop leaves its unvisited size explicitly open.
// Small regions use cheap exact reduced-program evaluation: bounds must not
// cost more than simply checking their leaves. No simulator is called here.
func (engine *Engine) searchInventoryActor(ctx context.Context, anchor domain.Assignment, actor, cycle int) (step ActorStep, err error) {
	step = ActorStep{Cycle: cycle, WearerKey: engine.domain.Wearers[actor].WearerKey}
	dense, err := engine.domain.DenseDeltas(anchor)
	if err != nil {
		return step, err
	}
	program, err := engine.panel.ArtifactProgram(dense, actor)
	if err != nil {
		return step, err
	}
	step.ReducedNodes = program.NodeCount()
	vectors, ref, err := engine.domain.ArtifactVectors(actor, program.Coordinates())
	if err != nil {
		return step, err
	}
	anchorDPS, err := engine.score(anchor)
	if err != nil {
		return step, err
	}
	best := ScoredAssignment{anchor, anchorDPS, "inventory_anchor"}
	bestObjective, err := engine.objective(anchor, anchorDPS)
	if err != nil {
		return step, err
	}
	rows := map[[5]int64]ScoredAssignment{anchor[actor]: best}
	// A deadline inside refinement preserves already verified improvements.
	// Arithmetic/identity failures must not be converted to partial success.
	defer func() {
		if err != nil && !errors.Is(err, context.Canceled) && !errors.Is(err, context.DeadlineExceeded) {
			return
		}
		rows[best.Assignment[actor]] = best
		rows[anchor[actor]] = ScoredAssignment{anchor, anchorDPS, "inventory_anchor"}
		ordered := make([]ScoredAssignment, 0, len(rows))
		for _, r := range rows {
			v, e := engine.score(r.Assignment)
			if e != nil {
				err = e
				return
			}
			if math.Abs(v-r.DPS) > 1e-7*(1+math.Abs(v)) {
				err = fmt.Errorf("reduced artifact formula parity mismatch")
				return
			}
			r.DPS = v
			ordered = append(ordered, r)
		}
		engine.sortScored(ordered)
		if len(ordered) > engine.config.FinalistLimit {
			ordered = ordered[:engine.config.FinalistLimit]
		}
		step.Finalists = ordered
	}()
	seen := map[[5]int64]bool{}
	remaining := engine.config.MaxExpandedPerActor
	x := make([]float64, len(ref))
	point := func(ids [5]int64) (float64, error) {
		if e := ctx.Err(); e != nil {
			return 0, e
		}
		if old, ok := rows[ids]; ok {
			return old.DPS, nil
		}
		if seen[ids] || remaining <= 0 {
			return math.Inf(-1), nil
		}
		seen[ids] = true
		trial := anchor
		trial[actor] = ids
		if engine.domain.ValidateAssignment(trial) != nil {
			step.InvalidAssignments++
			return math.Inf(-1), nil
		}
		remaining--
		step.Expanded++
		clear(x)
		for _, id := range ids {
			for j, v := range vectors[id] {
				x[j] += v
			}
		}
		for j := range x {
			x[j] -= ref[j]
		}
		v, e := program.Evaluate(x)
		if e != nil {
			return 0, e
		}
		step.CompleteEvaluations++
		o, e := engine.objective(trial, v)
		if e != nil {
			return 0, e
		}
		scored := ScoredAssignment{trial, v, "inventory_bound"}
		if betterObjective(o, bestObjective) {
			best, bestObjective = scored, o
		}
		// Retain a bounded exact finalist pool without storing every scored leaf.
		rows[ids] = scored
		if len(rows) > 2*engine.config.FinalistLimit {
			ordered := make([]ScoredAssignment, 0, len(rows))
			for _, r := range rows {
				ordered = append(ordered, r)
			}
			engine.sortScored(ordered)
			rows = map[[5]int64]ScoredAssignment{}
			for _, r := range ordered[:engine.config.FinalistLimit] {
				rows[r.Assignment[actor]] = r
			}
		}
		return v, nil
	}
	// Priorities order real items; they do not prune. Caps, flat ATK, buffs and
	// all cross-owner dependencies are inherited from this reduced program.
	local := make([]float64, len(ref))
	fullCoordinates := engine.panel.Coordinates()
	for i, key := range program.Coordinates() {
		for j, k := range fullCoordinates {
			if key == k {
				local[i] = dense[j]
				break
			}
		}
	}
	_, weights, _, err := program.ValueGradient(local)
	if err != nil {
		return step, err
	}
	priority := map[int64]float64{}
	for id, v := range vectors {
		for j, w := range weights {
			priority[id] += w * v[j]
		}
	}
	seed, e := engine.domain.PackageSeed(anchor, actor, domain.Package{Sets: engine.domain.Wearers[actor].SelectedSets}, priority)
	if e != nil {
		return step, e
	}
	if _, e = point(seed[actor]); e != nil {
		return step, e
	}
	lanes := engine.lanes(anchor, actor)
	for i := range lanes {
		for s := range lanes[i].pools {
			sort.SliceStable(lanes[i].pools[s], func(a, b int) bool {
				x, y := lanes[i].pools[s][a], lanes[i].pools[s][b]
				if priority[x] != priority[y] {
					return priority[x] > priority[y]
				}
				return x < y
			})
		}
	}
	// A feasible warm start in every lane is cheap and prevents early ID/lane
	// order from consuming the budget before other off-slot patterns are seen.
	for _, l := range lanes {
		ids := [5]int64{}
		for s, pool := range l.pools {
			ids[s] = pool[0]
		}
		if _, e = point(ids); e != nil {
			return step, e
		}
	}
	// One queue spans every legal slot pattern. A deep promising branch cannot
	// hide another pattern merely because of lane order or equal budget slices.
	size := func(pools [5][]int64) int64 {
		n := int64(1)
		for _, p := range pools {
			n = saturatingMultiply(n, int64(len(p)))
		}
		return n
	}
	upper := func(pools [5][]int64) (float64, float64, error) {
		if e := ctx.Err(); e != nil {
			return 0, 0, e
		}
		if remaining <= 0 {
			return math.Inf(1), math.Inf(1), nil
		}
		remaining--
		step.Expanded++
		step.BoundEvaluations++
		v := make([][][]float64, 5)
		for s, pool := range pools {
			v[s] = make([][]float64, len(pool))
			for i, id := range pool {
				v[s][i] = vectors[id]
			}
		}
		potential := program.Potential(v, ref)
		if program.HasUnresolvedDependencies() {
			return math.Inf(1), potential, nil
		}
		return potential, potential, nil
	}
	queue := &inventoryRegionQueue{}
	serial := 0
	push := func(pools [5][]int64) error {
		u, potential, e := upper(pools)
		if e != nil {
			return e
		}
		heap.Push(queue, inventoryRegion{pools: pools, upper: u, potential: potential, count: size(pools), order: serial})
		serial++
		return nil
	}
	for _, l := range lanes {
		step.RawPhysicalBuilds = saturatingAdd(step.RawPhysicalBuilds, l.raw)
		if e := push(l.pools); e != nil {
			return step, e
		}
	}
	defer func() {
		for _, r := range *queue {
			step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, r.count)
		}
	}()
	for queue.Len() > 0 && remaining > 0 {
		if e := ctx.Err(); e != nil {
			return step, e
		}
		r := heap.Pop(queue).(inventoryRegion)
		// Energy feasibility outranks damage; an infeasible incumbent cannot
		// exclude a potentially feasible region using only its damage bound.
		if bestObjective.feasible && r.upper < best.DPS-1e-7*(1+math.Abs(best.DPS)) {
			step.BoundPrunedBuilds = saturatingAdd(step.BoundPrunedBuilds, r.count)
			continue
		}
		work, split := 0, 0
		for s, pool := range r.pools {
			work += len(pool)
			if len(pool) > len(r.pools[split]) {
				split = s
			}
		}
		exactLimit := int64(4 * work * (len(ref) + 1))
		if exactLimit < 256 {
			exactLimit = 256
		}
		if r.count <= exactLimit {
			ids := [5]int64{}
			visited := int64(0)
			var enumerate func(int) error
			enumerate = func(slot int) error {
				if remaining <= 0 {
					return nil
				}
				if slot == 5 {
					if _, e := point(ids); e != nil {
						return e
					}
					visited++
					return nil
				}
				for _, id := range r.pools[slot] {
					ids[slot] = id
					if e := enumerate(slot + 1); e != nil {
						return e
					}
					if remaining <= 0 {
						break
					}
				}
				return ctx.Err()
			}
			e := enumerate(0)
			step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, r.count-visited)
			if e != nil {
				return step, e
			}
			continue
		}
		left, right := r.pools, r.pools
		mid := len(r.pools[split]) / 2
		left[split], right[split] = r.pools[split][:mid], r.pools[split][mid:]
		if e := push(left); e != nil {
			step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, r.count)
			return step, e
		}
		if e := push(right); e != nil {
			step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, size(right))
			return step, e
		}
	}
	return step, nil
}

// Zero/one-bonus lanes deliberately relax OTHER family counts. Final physical
// validation enforces their exact absence; the relaxed upper remains safe.
func (engine *Engine) sparseSetLanes(occupied map[int64]struct{}, sets []contracts.SetRequirement) []lane {
	var out []lane
	for mask := 0; mask < 32; mask++ {
		if len(sets) == 0 && mask != 0 {
			continue
		}
		if len(sets) > 0 && bits.OnesCount(uint(mask)) != 2 && bits.OnesCount(uint(mask)) != 3 {
			continue
		}
		l := lane{raw: 1}
		for slot, pool := range engine.domain.CandidateIDsBySlot {
			for _, id := range pool {
				if _, ok := occupied[id]; ok {
					continue
				}
				uid, _ := engine.domain.ArtifactSetUID(id)
				if len(sets) > 0 && (uid == sets[0].SetUID) != (mask&(1<<slot) != 0) {
					continue
				}
				l.pools[slot] = append(l.pools[slot], id)
			}
			l.raw = saturatingMultiply(l.raw, int64(len(l.pools[slot])))
		}
		if l.raw > 0 {
			out = append(out, l)
		}
	}
	return out
}
