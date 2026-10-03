package formula

import "fmt"

// Exact constant-effect specialization of the already prepared aggregate.
// Latent read roots stay in the prepared graph for GENERAL expression binding;
// they cannot become damage dependencies when EVERY supplied effect is constant.
// No source rules, ports, artifact axes or schedule observations are removed.

func (p *ParametricProgram) damageNodes() []bool {
	if p.damageLive == nil {
		p.damageLive = make([]bool, len(p.program.nodes))
		// Preserve the general binder's ordered DFS postorder. A different
		// topological order can change reverse-gradient accumulation rounding,
		// even when forward DPS is equal. The graph itself is already acyclic.
		type frame struct {
			id   uint32
			next int
		}
		stack := []frame{{id: p.program.root}}
		p.damageLive[p.program.root] = true
		for len(stack) > 0 {
			at := len(stack) - 1
			top := &stack[at]
			inputs := p.program.nodes[top.id].inputs
			if top.next == len(inputs) {
				p.damageOrder = append(p.damageOrder, top.id)
				stack = stack[:at]
				continue
			}
			child := inputs[top.next]
			top.next++
			if !p.damageLive[child] {
				p.damageLive[child] = true
				stack = append(stack, frame{id: child})
			}
		}
	}
	return p.damageLive
}

// ConstantDamageEffectKeys is a conservative dependency projection for a FULL
// constant vector only. A read/artifact/effect expression can introduce another
// dependency: callers must validate all inputs as constants before using it.
func (p *ParametricProgram) ConstantDamageEffectKeys() []string {
	live := p.damageNodes()
	used := make([]bool, len(p.effects))
	for i, n := range p.program.nodes {
		if live[i] && n.op == opArtifactStat && n.coordinate >= p.artifactCount {
			used[n.coordinate-p.artifactCount] = true
		}
	}
	keys := []string{}
	for i, key := range p.effects {
		if used[i] {
			keys = append(keys, key)
		}
	}
	return keys
}

func (p *ParametricProgram) bindConstantEffects(effects map[string]*InputExpression) (*ParametricProgram, bool, error) {
	values := make([]float64, len(p.effects))
	for i, key := range p.effects {
		x := effects[key]
		if x == nil || x.Operation != "constant" || len(x.Inputs) != 0 || !isFinite(x.Value) {
			return nil, false, nil
		}
		values[i] = x.Value
	}
	bound, err := p.bindConstantValues(values)
	return bound, true, err
}

// BindConstantEffects accepts one finite constant per EffectKeys() entry, in
// that exact order. It shares the map binder's ordered reduction; no expression
// or latent dependency may be silently projected onto this API.
func (p *ParametricProgram) BindConstantEffects(values []float64) (*ParametricProgram, error) {
	if p == nil || len(values) != len(p.effects) {
		return nil, fmt.Errorf("constant effect vector does not match prepared inputs")
	}
	for _, value := range values {
		if !isFinite(value) {
			return nil, fmt.Errorf("nonfinite effect constant")
		}
	}
	return p.bindConstantValues(values)
}

func (p *ParametricProgram) bindConstantValues(values []float64) (*ParametricProgram, error) {
	p.damageNodes()
	b := newProgramBuilder(p.Coordinates())
	b.program.unresolved = p.program.unresolved
	mapped := make([]uint32, len(p.program.nodes))
	for _, i := range p.damageOrder {
		source := p.program.nodes[i]
		n := copyNode(source)
		for j, in := range n.inputs {
			n.inputs[j] = mapped[in]
		}
		if n.op == opArtifactStat && n.coordinate >= p.artifactCount {
			n = compiledNode{op: opConstant, coordinate: -1, value: values[n.coordinate-p.artifactCount]}
		}
		var err error
		mapped[i], err = b.add(n)
		if err != nil {
			return nil, err
		}
	}
	return &ParametricProgram{program: b.finish(mapped[p.program.root]), artifactCount: p.artifactCount, actors: append([]string(nil), p.actors...), input: make([]float64, p.artifactCount)}, nil
}
