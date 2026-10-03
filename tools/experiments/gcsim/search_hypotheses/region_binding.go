package formula

// Research-only incremental constant binding. Owned by the 2026-09-28 speed
// experiment; copied into managed source, never installed by this helper.
// The arena hash-conses immutable reduced regions across DIFFERENT effect
// vectors. Artifact-dependent regions retain all coordinates/cross-owner edges.
// Export follows the original binder's first-encounter order, preserving reverse
// gradient accumulation, rather than the persistent arena's insertion order.
import (
	"fmt"
	"math"
)

type HypothesisRegionStats struct {
	Calls, Visited, Rebuilt, Reused, OutputNodes, Resets, PeakArenaNodes uint64
}

type hypothesisRegionBinder struct {
	arena       *programBuilder
	mapped      []uint32
	changed     []bool
	values      []float64
	initialized bool
	inputCount  int
	nodeLimit   int
}

func (p *ParametricProgram) HypothesisRegionsStats() HypothesisRegionStats {
	return p.hypothesisRegionStats
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
	p.hypothesisRegionStats.Calls++
	r := p.hypothesisRegions
	if r == nil {
		r = &hypothesisRegionBinder{arena: newProgramBuilder(p.Coordinates()),
			mapped: make([]uint32, len(p.program.nodes)), changed: make([]bool, len(p.program.nodes)),
			values: make([]float64, len(values)), nodeLimit: 250000}
		p.hypothesisRegions = r
	}
	for _, id := range p.damageOrder {
		p.hypothesisRegionStats.Visited++
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
			p.hypothesisRegionStats.Reused++
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
			p.hypothesisRegions = nil
			return nil, err
		}
		if len(r.arena.program.nodes) != before {
			r.inputCount += len(r.arena.program.nodes[mapped].inputs)
		}
		p.hypothesisRegionStats.Rebuilt++
		r.changed[id] = !r.initialized || mapped != r.mapped[id]
		r.mapped[id] = mapped
		p.hypothesisRegionStats.PeakArenaNodes = max(p.hypothesisRegionStats.PeakArenaNodes, uint64(len(r.arena.program.nodes)))
		if len(r.arena.program.nodes) > r.nodeLimit || r.inputCount > 1000000 {
			p.hypothesisRegionStats.Resets++
			p.hypothesisRegions = nil
			return p.BindConstantEffects(values)
		}
	}
	copy(r.values, values)
	r.initialized = true
	program, err := p.hypothesisExportRegions(r)
	if err != nil {
		p.hypothesisRegions = nil
		return nil, err
	}
	p.hypothesisRegionStats.OutputNodes += uint64(len(program.nodes))
	return &ParametricProgram{program: program, artifactCount: p.artifactCount,
		actors: append([]string(nil), p.actors...), input: make([]float64, p.artifactCount)}, nil
}

func (p *ParametricProgram) hypothesisExportRegions(r *hypothesisRegionBinder) (*ArtifactProgram, error) {
	root := r.mapped[p.program.root]
	live := map[uint32]bool{root: true}
	stack := []uint32{root}
	inputsNeeded := 0
	for len(stack) != 0 {
		id := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		n := r.arena.program.nodes[id]
		inputsNeeded += len(n.inputs)
		for _, in := range n.inputs {
			if !live[in] {
				live[in] = true
				stack = append(stack, in)
			}
		}
	}
	program := &ArtifactProgram{coordinates: p.Coordinates(), unresolved: p.program.unresolved,
		nodes: make([]compiledNode, 0, len(live)), values: make([]float64, 0, len(live)),
		active: make([]uint32, 0, len(live))}
	indices := make(map[uint32]uint32, len(live))
	operands := make([]uint32, inputsNeeded)
	next := 0
	for _, sourceID := range p.damageOrder {
		id := r.mapped[sourceID]
		if !live[id] {
			continue
		}
		if _, seen := indices[id]; seen {
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
				mapped, ok := indices[input]
				if !ok {
					return nil, fmt.Errorf("region export lost original topological order")
				}
				n.inputs[j] = mapped
			}
		}
		mapped := uint32(len(program.nodes))
		indices[id] = mapped
		program.nodes = append(program.nodes, n)
		value := 0.0
		if n.op == opConstant {
			value = n.value
		} else {
			program.active = append(program.active, mapped)
		}
		program.values = append(program.values, value)
	}
	if len(program.nodes) != len(live) || next != len(operands) {
		return nil, fmt.Errorf("region export omitted a live dependency")
	}
	program.root = indices[root]
	program.prepareDependencies()
	return program, nil
}
