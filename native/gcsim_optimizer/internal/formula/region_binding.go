package formula

// Incremental constant binding within one prepared run-local program.
// The arena hash-conses immutable reduced regions across DIFFERENT effect
// vectors. Artifact-dependent regions retain all coordinates/cross-owner edges.
// Export follows the original binder's first-encounter order, preserving reverse
// gradient accumulation, rather than the persistent arena's insertion order.
import (
	"fmt"
	"math"
)

type RegionBindingStats struct {
	Calls, Visited, Rebuilt, Reused, OutputNodes, Resets, PeakArenaNodes uint64
}

type regionBinder struct {
	arena                               *programBuilder
	mapped                              []uint32
	changed                             []bool
	values                              []float64
	initialized                         bool
	inputCount                          int
	nodeLimit                           int
	liveStamp, exportedStamp, exportMap []uint32
	generation                          uint32
}

func (p *ParametricProgram) RegionBindingStats() RegionBindingStats {
	return p.regionStats
}

func (p *ParametricProgram) BindConstantEffectsRegions(values []float64) (*ParametricProgram, error) {
	if p == nil || len(values) != len(p.effects) {
		return nil, fmt.Errorf("region binding input length mismatch")
	}
	for _, value := range values {
		if !isFinite(value) {
			return nil, fmt.Errorf("nonfinite region binding input")
		}
	}
	p.damageNodes()
	p.regionStats.Calls++
	r := p.regions
	if r == nil {
		r = &regionBinder{arena: newProgramBuilder(p.Coordinates()),
			mapped: make([]uint32, len(p.program.nodes)), changed: make([]bool, len(p.program.nodes)),
			values: make([]float64, len(values)), nodeLimit: 250000}
		p.regions = r
	}
	for _, id := range p.damageOrder {
		p.regionStats.Visited++
		source := p.program.nodes[id]
		dirty := !r.initialized
		if source.op == opArtifactStat && source.coordinate >= p.artifactCount {
			i := source.coordinate - p.artifactCount
			dirty = dirty || math.Float64bits(values[i]) != math.Float64bits(r.values[i])
		} else {
			for _, in := range source.inputs {
				dirty = dirty || r.changed[in]
			}
		}
		r.changed[id] = false
		if !dirty {
			p.regionStats.Reused++
			continue
		}
		n := copyNode(source)
		for j, in := range n.inputs {
			n.inputs[j] = r.mapped[in]
		}
		if n.op == opArtifactStat && n.coordinate >= p.artifactCount {
			n = compiledNode{op: opConstant, coordinate: -1, value: values[n.coordinate-p.artifactCount]}
		}
		before := len(r.arena.program.nodes)
		mapped, err := r.arena.add(n)
		if err != nil {
			// A failed partial update must never contaminate a subsequent call.
			p.regions = nil
			return nil, err
		}
		if len(r.arena.program.nodes) != before {
			r.inputCount += len(r.arena.program.nodes[mapped].inputs)
		}
		p.regionStats.Rebuilt++
		r.changed[id] = !r.initialized || mapped != r.mapped[id]
		r.mapped[id] = mapped
		p.regionStats.PeakArenaNodes = max(p.regionStats.PeakArenaNodes, uint64(len(r.arena.program.nodes)))
		if len(r.arena.program.nodes) > r.nodeLimit || r.inputCount > 1000000 {
			p.regionStats.Resets++
			p.regions = nil
			return p.BindConstantEffects(values)
		}
	}
	copy(r.values, values)
	r.initialized = true
	program, err := p.exportRegions(r)
	if err != nil {
		p.regions = nil
		return nil, err
	}
	p.regionStats.OutputNodes += uint64(len(program.nodes))
	return &ParametricProgram{program: program, artifactCount: p.artifactCount,
		actors: append([]string(nil), p.actors...), input: make([]float64, p.artifactCount)}, nil
}

func (p *ParametricProgram) exportRegions(r *regionBinder) (*ArtifactProgram, error) {
	root := r.mapped[p.program.root]
	size := len(r.arena.program.nodes)
	grow := func(buffer []uint32) []uint32 {
		if cap(buffer) < size {
			next := make([]uint32, size, size+1024)
			copy(next, buffer)
			return next
		}
		return buffer[:size]
	}
	r.liveStamp, r.exportedStamp, r.exportMap = grow(r.liveStamp), grow(r.exportedStamp), grow(r.exportMap)
	r.generation++
	if r.generation == 0 {
		clear(r.liveStamp)
		clear(r.exportedStamp)
		r.generation = 1
	}
	r.liveStamp[root] = r.generation
	liveCount := 1
	stack := []uint32{root}
	inputsNeeded := 0
	for len(stack) != 0 {
		id := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		n := r.arena.program.nodes[id]
		inputsNeeded += len(n.inputs)
		for _, in := range n.inputs {
			if r.liveStamp[in] != r.generation {
				r.liveStamp[in] = r.generation
				liveCount++
				stack = append(stack, in)
			}
		}
	}
	program := &ArtifactProgram{coordinates: p.Coordinates(), unresolved: p.program.unresolved,
		nodes: make([]compiledNode, 0, liveCount), values: make([]float64, 0, liveCount),
		active: make([]uint32, 0, liveCount)}
	indices := r.exportMap
	operands := make([]uint32, inputsNeeded)
	next := 0
	for _, sourceID := range p.damageOrder {
		id := r.mapped[sourceID]
		if r.liveStamp[id] != r.generation {
			continue
		}
		if r.exportedStamp[id] == r.generation {
			continue
		}
		n := r.arena.program.nodes[id]
		originalInputs := n.inputs
		n.inputs = nil
		if len(originalInputs) > 0 {
			end := next + len(originalInputs)
			n.inputs = operands[next:end:end]
			next = end
			for j, input := range originalInputs {
				mapped := indices[input]
				if r.exportedStamp[input] != r.generation {
					return nil, fmt.Errorf("region export lost original topological order")
				}
				n.inputs[j] = mapped
			}
		}
		mapped := uint32(len(program.nodes))
		indices[id] = mapped
		r.exportedStamp[id] = r.generation
		program.nodes = append(program.nodes, n)
		value := 0.0
		if n.op == opConstant {
			value = n.value
		} else {
			program.active = append(program.active, mapped)
		}
		program.values = append(program.values, value)
	}
	if len(program.nodes) != liveCount || next != len(operands) {
		return nil, fmt.Errorf("region export omitted a live dependency")
	}
	program.root = indices[root]
	program.prepareDependencies()
	return program, nil
}
