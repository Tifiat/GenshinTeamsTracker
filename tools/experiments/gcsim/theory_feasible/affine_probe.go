package formula

import "math"

// PositiveAffineOf returns a and b when p's objective is structurally
// certified as a*reference+b, with finite a>0 and finite b.
//
// This is deliberately a conservative graph proof: it peels only binary
// add/multiply nodes with one direct constant operand, then requires the
// remaining ordered arithmetic DAGs to match exactly. It never compares a
// sampled value, gradient, or candidate score. ArtifactProgram has no search
// domain identity, so callers may reuse an allocation only after independently
// confirming the same coordinate semantics and exact feasible domain. Unknown
// dependencies reject the proof.
func (p *ArtifactProgram) PositiveAffineOf(reference *ArtifactProgram) (a, b float64, ok bool) {
	if p == nil || reference == nil || p.unresolved || reference.unresolved ||
		!positiveAffineProbeSameCoordinates(p.coordinates, reference.coordinates) {
		return 0, 0, false
	}

	pCore, pScale, pOffset, valid := positiveAffineProbePeel(p)
	if !valid {
		return 0, 0, false
	}
	rCore, rScale, rOffset, valid := positiveAffineProbePeel(reference)
	if !valid || !positiveAffineProbeSameNode(p, pCore, reference, rCore) {
		return 0, 0, false
	}

	a = pScale / rScale
	b = pOffset - a*rOffset
	if !isFinite(a) || a <= 0 || !isFinite(b) {
		return 0, 0, false
	}
	return a, b, true
}

// positiveAffineProbePeel expresses the root as scale*core+offset. Only direct
// constant wrappers are peeled, preserving the source graph and its operand
// order. Unsupported wrappers remain part of core and can still prove identity
// when the other program has the same exact subgraph.
func positiveAffineProbePeel(p *ArtifactProgram) (core uint32, scale, offset float64, ok bool) {
	if p == nil || len(p.nodes) == 0 || int(p.root) >= len(p.nodes) {
		return 0, 0, 0, false
	}
	core, scale, offset = p.root, 1, 0
	seen := make(map[uint32]bool)
	for {
		if int(core) >= len(p.nodes) || seen[core] {
			return 0, 0, 0, false
		}
		seen[core] = true
		n := p.nodes[core]
		if len(n.inputs) != 2 || (n.op != opAdd && n.op != opMultiply) {
			break
		}
		left, right := n.inputs[0], n.inputs[1]
		if int(left) >= len(p.nodes) || int(right) >= len(p.nodes) {
			return 0, 0, 0, false
		}
		leftConstant := p.nodes[left].op == opConstant
		rightConstant := p.nodes[right].op == opConstant
		if leftConstant == rightConstant {
			break
		}
		constant, variable := left, right
		if rightConstant {
			constant, variable = right, left
		}
		value := p.nodes[constant].value
		if !isFinite(value) {
			return 0, 0, 0, false
		}
		if n.op == opAdd {
			offset += scale * value
		} else {
			scale *= value
		}
		if !isFinite(scale) || !isFinite(offset) {
			return 0, 0, 0, false
		}
		core = variable
	}
	if !isFinite(scale) || scale == 0 || !isFinite(offset) ||
		!positiveAffineProbeUsesArtifact(p, core) {
		return 0, 0, 0, false
	}
	return core, scale, offset, true
}

func positiveAffineProbeSameCoordinates(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func positiveAffineProbeSameNode(a *ArtifactProgram, left uint32, b *ArtifactProgram, right uint32) bool {
	type pair struct{ left, right uint32 }
	state := map[pair]uint8{}
	var same func(uint32, uint32) bool
	same = func(x, y uint32) bool {
		if int(x) >= len(a.nodes) || int(y) >= len(b.nodes) {
			return false
		}
		key := pair{x, y}
		switch state[key] {
		case 1: // Cycles are outside the compiler's DAG contract.
			return false
		case 2:
			return true
		case 3:
			return false
		}
		state[key] = 1
		nx, ny := a.nodes[x], b.nodes[y]
		if nx.op != ny.op || nx.coordinate != ny.coordinate ||
			math.Float64bits(nx.value) != math.Float64bits(ny.value) ||
			len(nx.inputs) != len(ny.inputs) {
			state[key] = 3
			return false
		}
		for i := range nx.inputs {
			if !same(nx.inputs[i], ny.inputs[i]) {
				state[key] = 3
				return false
			}
		}
		state[key] = 2
		return true
	}
	return same(left, right)
}

func positiveAffineProbeUsesArtifact(p *ArtifactProgram, root uint32) bool {
	if p == nil || int(root) >= len(p.nodes) {
		return false
	}
	seen := make([]bool, len(p.nodes))
	var uses func(uint32) bool
	uses = func(id uint32) bool {
		if int(id) >= len(p.nodes) || seen[id] {
			return false
		}
		seen[id] = true
		n := p.nodes[id]
		if n.op == opArtifactStat {
			return n.coordinate >= 0 && n.coordinate < len(p.coordinates)
		}
		for _, in := range n.inputs {
			if uses(in) {
				return true
			}
		}
		return false
	}
	return uses(root)
}
