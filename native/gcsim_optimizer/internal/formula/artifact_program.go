package formula

// Reduced engine arithmetic, not another damage model. All channels (including
// cross-owner buffs) remain in the scalar DPS root. General preparation is shared
// with parametric_program.go and retained for repeated specializations.
import (
	"fmt"
	"math"
)

type ArtifactProgram struct {
	nodes       []compiledNode
	root        uint32
	values      []float64
	coordinates []string
	active      []uint32
	unresolved  bool
	// Immutable coordinate dependencies; mutable previous inputs stay local to
	// this evaluation scratch. Larger-coordinate fixtures use the full sweep.
	dependencies  []uint64
	usedInputs    uint64
	previous      []float64
	previousValid bool
}

// SpecializeArtifacts is the compatibility entry for one-off callers. All Sets
// retains PrepareParametric's result instead of reading the source graph at each
// wearer/cycle step.
func SpecializeArtifacts(members []*CompiledMember, anchor []float64, actor int) (*ArtifactProgram, error) {
	p, err := PrepareParametric(members, nil)
	if err != nil {
		return nil, err
	}
	return p.Specialize(anchor, nil, actor)
}

func (p *ArtifactProgram) Coordinates() []string           { return append([]string(nil), p.coordinates...) }
func (p *ArtifactProgram) NodeCount() int                  { return len(p.nodes) }
func (p *ArtifactProgram) HasUnresolvedDependencies() bool { return p.unresolved }

// Evaluate takes local delta coordinates and reuses sequential scratch.
// Constants are initialized once rather than evaluated for every candidate.
func (p *ArtifactProgram) Evaluate(delta []float64) (float64, error) {
	if p == nil || len(delta) != len(p.coordinates) {
		return 0, fmt.Errorf("artifact program coordinate mismatch")
	}
	for _, v := range delta {
		if !isFinite(v) {
			return 0, fmt.Errorf("nonfinite artifact input")
		}
	}
	p.prepareDependencies()
	changed := ^uint64(0)
	if p.previousValid && p.dependencies != nil {
		changed = 0
		for i, value := range delta {
			if math.Float64bits(value) != math.Float64bits(p.previous[i]) {
				changed |= uint64(1) << uint(i)
			}
		}
		if changed&p.usedInputs == 0 {
			// Different physical artifacts can have identical damage-live stats.
			// Keep every legal identity in the result archive, but reuse this exact
			// scalar value instead of even walking the unchanged arithmetic nodes.
			copy(p.previous, delta)
			return p.values[p.root], nil
		}
	}
	// An error must never make partially updated scratch reusable.
	p.previousValid = false
	partial := p.dependencies != nil && changed&p.usedInputs != p.usedInputs
	evaluate := func(i uint32) error {
		n := &p.nodes[i]
		if n.op == opArtifactStat {
			p.values[i] = delta[n.coordinate]
			return nil
		}
		v, err := evaluateConstantNode(n, p.values)
		if err != nil {
			return err
		}
		p.values[i] = v
		return nil
	}
	if p.active == nil { // Small directly constructed arithmetic unit fixtures.
		for i := range p.nodes {
			if err := evaluate(uint32(i)); err != nil {
				return 0, err
			}
		}
	} else {
		for _, i := range p.active {
			if partial && p.dependencies[i]&changed == 0 {
				continue
			}
			if err := evaluate(i); err != nil {
				return 0, err
			}
		}
	}
	v := p.values[p.root]
	if !isFinite(v) {
		return 0, fmt.Errorf("nonfinite artifact program result")
	}
	if p.dependencies != nil {
		copy(p.previous, delta)
		p.previousValid = true
	}
	return v, nil
}

func (p *ArtifactProgram) prepareDependencies() {
	if p.dependencies != nil || len(p.coordinates) > 64 || p.active == nil {
		return
	}
	p.dependencies = make([]uint64, len(p.nodes))
	for i, n := range p.nodes {
		if n.op == opArtifactStat {
			p.dependencies[i] = uint64(1) << uint(n.coordinate)
		}
		for _, in := range n.inputs {
			p.dependencies[i] |= p.dependencies[in]
		}
		p.usedInputs |= p.dependencies[i]
	}
	p.previous = make([]float64, len(p.coordinates))
}
