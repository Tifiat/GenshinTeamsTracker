package formula

// Research-only: freeze scalar effects in one ordered traversal, defer common
// subexpression interning to wearer specialization. No arithmetic reassociation.
import "fmt"

func (p *ParametricProgram) BindConstantEffectsHypothesis(values []float64) (*ParametricProgram, error) {
	if p == nil || len(values) != len(p.effects) {
		return nil, fmt.Errorf("constant vector mismatch")
	}
	for _, v := range values {
		if !isFinite(v) {
			return nil, fmt.Errorf("nonfinite constant")
		}
	}
	p.damageNodes()
	b := newProgramBuilder(p.Coordinates())
	b.program.unresolved = p.program.unresolved
	mapped := make([]uint32, len(p.program.nodes))
	for _, i := range p.damageOrder {
		n := copyNode(p.program.nodes[i])
		for j, in := range n.inputs {
			n.inputs[j] = mapped[in]
		}
		if n.op == opArtifactStat && n.coordinate >= p.artifactCount {
			n = compiledNode{op: opConstant, coordinate: -1, value: values[n.coordinate-p.artifactCount]}
		}
		id, err := b.hypothesisAppend(n)
		if err != nil {
			return nil, err
		}
		mapped[i] = id
	}
	return &ParametricProgram{program: b.finish(mapped[p.program.root]), artifactCount: p.artifactCount, actors: append([]string(nil), p.actors...), input: make([]float64, p.artifactCount)}, nil
}

func (b *programBuilder) hypothesisAppend(n compiledNode) (uint32, error) {
	p := b.program
	if n.op != opConstant && n.op != opArtifactStat {
		fixed := true
		for _, in := range n.inputs {
			fixed = fixed && p.nodes[in].op == opConstant
		}
		if n.op == opSelectLT && p.nodes[n.inputs[0]].op == opConstant && p.nodes[n.inputs[1]].op == opConstant {
			if p.values[n.inputs[0]] < p.values[n.inputs[1]] {
				return n.inputs[2], nil
			}
			return n.inputs[3], nil
		}
		if fixed {
			v, err := evaluateConstantNode(&n, p.values)
			if err != nil {
				return 0, err
			}
			n = compiledNode{op: opConstant, value: v, coordinate: -1}
		}
	}
	id := uint32(len(p.nodes))
	p.nodes = append(p.nodes, n)
	p.values = append(p.values, n.value)
	return id, nil
}
