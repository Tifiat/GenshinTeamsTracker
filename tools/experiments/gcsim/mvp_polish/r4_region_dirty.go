package formula

import (
	"math"
	"os"
	"sort"
)

var r4DirtyRegions = os.Getenv("GTT_R4_DIRTY_REGIONS") == "1"

// Two compact reverse indexes belong to this existing sequential region binder.
// Their size is bounded by the prepared graph/edges/effects. No vector/result
// cache is added. A fork rebuilds its own work, and an arena reset drops it.
type r4RegionDirty struct {
	usersStart, effectsStart []uint32
	users, effectRoots       []uint32
	rank                     []int
	marked                   []uint32
	generation               uint32
	pending                  []uint32
}

func (p *ParametricProgram) r4RegionOrder(r *regionBinder, values []float64) []uint32 {
	if !r.initialized {
		return p.damageOrder
	}
	d := r.r4Dirty
	if d == nil {
		d = &r4RegionDirty{usersStart: make([]uint32, len(p.program.nodes)+1), effectsStart: make([]uint32, len(values)+1),
			rank: make([]int, len(p.program.nodes)), marked: make([]uint32, len(p.program.nodes))}
		for rank, id := range p.damageOrder {
			d.rank[id] = rank
			node := p.program.nodes[id]
			for _, in := range node.inputs {
				d.usersStart[in+1]++
			}
			if node.op == opArtifactStat && node.coordinate >= p.artifactCount {
				d.effectsStart[node.coordinate-p.artifactCount+1]++
			}
		}
		for i := 1; i < len(d.usersStart); i++ {
			d.usersStart[i] += d.usersStart[i-1]
		}
		for i := 1; i < len(d.effectsStart); i++ {
			d.effectsStart[i] += d.effectsStart[i-1]
		}
		d.users = make([]uint32, d.usersStart[len(d.usersStart)-1])
		d.effectRoots = make([]uint32, d.effectsStart[len(d.effectsStart)-1])
		usersNext := append([]uint32(nil), d.usersStart...)
		effectsNext := append([]uint32(nil), d.effectsStart...)
		for _, id := range p.damageOrder {
			node := p.program.nodes[id]
			for _, in := range node.inputs {
				d.users[usersNext[in]] = id
				usersNext[in]++
			}
			if node.op == opArtifactStat && node.coordinate >= p.artifactCount {
				effect := node.coordinate - p.artifactCount
				d.effectRoots[effectsNext[effect]] = id
				effectsNext[effect]++
			}
		}
		r.r4Dirty = d
		clear(r.changed) // previous full traversal may have set any source node
	} else {
		for _, id := range d.pending {
			r.changed[id] = false
		}
	}
	d.pending = d.pending[:0]
	d.generation++
	if d.generation == 0 {
		clear(d.marked)
		d.generation = 1
	}
	mark := func(id uint32) {
		if d.marked[id] != d.generation {
			d.marked[id] = d.generation
			d.pending = append(d.pending, id)
		}
	}
	for i, value := range values {
		if math.Float64bits(value) != math.Float64bits(r.values[i]) {
			for _, id := range d.effectRoots[d.effectsStart[i]:d.effectsStart[i+1]] {
				mark(id)
			}
		}
	}
	for at := 0; at < len(d.pending); at++ {
		id := d.pending[at]
		for _, user := range d.users[d.usersStart[id]:d.usersStart[id+1]] {
			mark(user)
		}
	}
	// damageOrder is ordered DFS postorder, not numeric node order. Retain its
	// precise first-encounter order for reduction and reverse-gradient parity.
	sort.Slice(d.pending, func(i, j int) bool { return d.rank[d.pending[i]] < d.rank[d.pending[j]] })
	return d.pending
}
