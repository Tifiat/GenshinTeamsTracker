package formula

import "math"

// ValueGradient differentiates the prepared arithmetic in one reverse traversal,
// not one complete evaluation per stat. It is a local ordering hint, NEVER a
// monotonicity or pruning certificate. At caps/branch boundaries smooth is false
// and the returned vector follows one deterministic active branch.
func (p *ArtifactProgram) ValueGradient(delta []float64) (value float64, gradient []float64, smooth bool, err error) {
	value, err = p.Evaluate(delta)
	if err != nil {
		return
	}
	gradient = make([]float64, len(delta))
	adjoint := make([]float64, len(p.nodes))
	adjoint[p.root] = 1
	smooth = true
	for i := len(p.nodes) - 1; i >= 0; i-- {
		n, a := p.nodes[i], adjoint[i]
		if a == 0 {
			continue
		}
		switch n.op {
		case opConstant:
		case opArtifactStat:
			gradient[n.coordinate] += a
		case opAdd:
			for _, in := range n.inputs {
				adjoint[in] += a
			}
		case opMultiply:
			// Zero factors are valid and must not use output/input division.
			zeros, nonzero := 0, 1.0
			for _, in := range n.inputs {
				if p.values[in] == 0 {
					zeros++
				} else {
					nonzero *= p.values[in]
				}
			}
			for _, in := range n.inputs {
				if zeros == 0 {
					adjoint[in] += a * nonzero / p.values[in]
				}
				if zeros == 1 && p.values[in] == 0 {
					adjoint[in] += a * nonzero
				}
			}
		case opPower:
			x, y := p.values[n.inputs[0]], p.values[n.inputs[1]]
			if y != 0 {
				adjoint[n.inputs[0]] += a * y * math.Pow(x, y-1)
			}
			if p.nodes[n.inputs[1]].op != opConstant {
				if x > 0 {
					adjoint[n.inputs[1]] += a * p.values[i] * math.Log(x)
				} else {
					smooth = false
				}
			}
		case opMin, opMax:
			chosen, matches := n.inputs[0], 0
			for _, in := range n.inputs {
				if p.values[in] == p.values[i] {
					chosen = in
					matches++
				}
			}
			if matches > 1 {
				smooth = false
			}
			adjoint[chosen] += a
		case opSelectLT:
			left, right := p.values[n.inputs[0]], p.values[n.inputs[1]]
			if left == right {
				smooth = false
			}
			if left < right {
				adjoint[n.inputs[2]] += a
			} else {
				adjoint[n.inputs[3]] += a
			}
		}
	}
	for i, g := range gradient {
		if !isFinite(g) {
			gradient[i], smooth = 0, false
		}
	}
	return
}
