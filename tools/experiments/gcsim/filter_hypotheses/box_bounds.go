package formula

import "math"

// HypothesisBoxResult describes a numeric enclosure of a fixed-context
// ArtifactProgram. Increasing and Decreasing are non-strict, whole-box claims;
// both true means the output is constant in that coordinate. A false entry is
// unknown, not evidence of a slope in the opposite direction.
//
// This is a research-only float64 prototype. Outward rounding and the Pow guard
// are pragmatic numerical margins, not a formal real-arithmetic certificate.
// The guarded Box methods reject unresolved capture coverage. The separate
// ModelBox methods describe only the fixed arithmetic even with that coverage
// unresolved. Malformed graphs, dynamic exponents, singular domains and
// nonfinite intermediate results are unsupported in either scope.
type HypothesisBoxResult struct {
	Lower, Upper           float64
	Increasing, Decreasing []bool
	Supported              bool
}

type hypothesisInterval struct {
	lo, hi float64
	exact  bool // independent of every artifact coordinate
}

// HypothesisBoxRange is the O(nodes) bound-only route. A supported range covers
// the rectangular coordinate domain, including uncertain select_lt arms. It
// relaxes all correlations among coordinates and is therefore often loose.
func (p *ArtifactProgram) HypothesisBoxRange(lo, hi []float64) (float64, float64, bool) {
	boxes, _, _, ok := p.hypothesisIntervals(lo, hi)
	if !ok {
		return math.Inf(-1), math.Inf(1), false
	}
	r := boxes[p.root]
	return r.lo, r.hi, true
}

// HypothesisBoxBounds also certifies coordinate order by structural signs over
// the whole box. The interval pass is O(nodes); signs cost O(nodes*coordinates)
// and O(nodes) additional scratch. Uncertain select_lt arms lose every sign.
func (p *ArtifactProgram) HypothesisBoxBounds(lo, hi []float64) HypothesisBoxResult {
	d := 0
	if p != nil {
		d = len(p.coordinates)
	}
	r := HypothesisBoxResult{
		Lower: math.Inf(-1), Upper: math.Inf(1),
		Increasing: make([]bool, d), Decreasing: make([]bool, d),
	}
	boxes, values, uncertainSelect, ok := p.hypothesisIntervals(lo, hi)
	if !ok {
		return r
	}
	r.Lower, r.Upper, r.Supported = boxes[p.root].lo, boxes[p.root].hi, true
	if uncertainSelect {
		return r
	}
	signs := make([]uint8, len(p.nodes))
	for coordinate := range p.coordinates {
		for i, n := range p.nodes {
			signs[i] = hypothesisNodeSign(n, coordinate, boxes, values, signs)
		}
		r.Increasing[coordinate] = signs[p.root]&1 != 0
		r.Decreasing[coordinate] = signs[p.root]&2 != 0
	}
	return r
}

// HypothesisModelBoxRange encloses only this already-compiled, fixed-context
// arithmetic model. It deliberately ignores unresolved response coverage for
// research measurements. It is NOT a bound on a fresh engine response and must
// never authorize product pruning. Unknown arithmetic still fails open.
// The shallow copy leaves the original coverage flag and evaluation scratch
// untouched; the interval traversal reads its shared immutable graph only.
func (p *ArtifactProgram) HypothesisModelBoxRange(lo, hi []float64) (float64, float64, bool) {
	if p == nil {
		return math.Inf(-1), math.Inf(1), false
	}
	model := *p
	model.unresolved = false
	return model.HypothesisBoxRange(lo, hi)
}

// HypothesisModelBoxBounds adds structural coordinate order claims within the
// same fixed compiled model. Its signs say nothing about unresolved engine
// dependencies, changed schedules or newly evaluated gameplay response.
func (p *ArtifactProgram) HypothesisModelBoxBounds(lo, hi []float64) HypothesisBoxResult {
	if p == nil {
		return p.HypothesisBoxBounds(lo, hi)
	}
	model := *p
	model.unresolved = false
	return model.HypothesisBoxBounds(lo, hi)
}

func (p *ArtifactProgram) hypothesisIntervals(lo, hi []float64) ([]hypothesisInterval, []float64, bool, bool) {
	if p == nil || p.unresolved || len(lo) == 0 || len(lo) != len(p.coordinates) || len(hi) != len(lo) ||
		len(p.nodes) == 0 || int(p.root) >= len(p.nodes) {
		return nil, nil, false, false
	}
	for i := range lo {
		if !isFinite(lo[i]) || !isFinite(hi[i]) || lo[i] > hi[i] {
			return nil, nil, false, false
		}
	}
	boxes := make([]hypothesisInterval, len(p.nodes))
	values := make([]float64, len(p.nodes))
	uncertainSelect := false
	for i, n := range p.nodes {
		if !hypothesisShape(n, i, len(lo)) {
			return nil, nil, false, false
		}
		if n.op == opArtifactStat {
			boxes[i] = hypothesisInterval{lo: lo[n.coordinate], hi: hi[n.coordinate]}
			continue
		}
		exact := true
		for _, in := range n.inputs {
			exact = exact && boxes[in].exact
		}
		if exact {
			v, err := evaluateConstantNode(&n, values)
			if err != nil || !isFinite(v) {
				return nil, nil, false, false
			}
			boxes[i], values[i] = hypothesisInterval{lo: v, hi: v, exact: true}, v
			continue
		}
		var b hypothesisInterval
		switch n.op {
		case opAdd:
			for _, in := range n.inputs {
				a := boxes[in]
				positive, negative := b.lo >= 0 && a.lo >= 0, b.hi <= 0 && a.hi <= 0
				b.lo, b.hi = down(b.lo+a.lo), up(b.hi+a.hi)
				if positive {
					b.lo = math.Max(0, b.lo)
				}
				if negative {
					b.hi = math.Min(0, b.hi)
				}
				if !hypothesisValid(b) {
					return nil, nil, false, false
				}
			}
		case opMultiply:
			b.lo, b.hi = 1, 1
			for _, in := range n.inputs {
				a := boxes[in]
				b.lo, b.hi = intervalProduct(b.lo, b.hi, a.lo, a.hi)
				if !hypothesisValid(b) {
					return nil, nil, false, false
				}
			}
		case opMin, opMax:
			b = boxes[n.inputs[0]]
			b.exact = false
			for _, in := range n.inputs[1:] {
				a := boxes[in]
				if n.op == opMin {
					b.lo, b.hi = math.Min(b.lo, a.lo), math.Min(b.hi, a.hi)
				} else {
					b.lo, b.hi = math.Max(b.lo, a.lo), math.Max(b.hi, a.hi)
				}
			}
		case opSelectLT:
			left, right := boxes[n.inputs[0]], boxes[n.inputs[1]]
			if left.hi < right.lo {
				b = boxes[n.inputs[2]]
			} else if left.lo >= right.hi {
				b = boxes[n.inputs[3]]
			} else {
				uncertainSelect = true
				a, z := boxes[n.inputs[2]], boxes[n.inputs[3]]
				b.lo, b.hi = math.Min(a.lo, z.lo), math.Max(a.hi, z.hi)
			}
			b.exact = false
		case opPower:
			exponent := n.inputs[1]
			if !boxes[exponent].exact {
				return nil, nil, false, false
			}
			var ok bool
			b, ok = hypothesisPower(boxes[n.inputs[0]], values[exponent])
			if !ok {
				return nil, nil, false, false
			}
		default:
			return nil, nil, false, false
		}
		if !hypothesisValid(b) {
			return nil, nil, false, false
		}
		boxes[i] = b
	}
	return boxes, values, uncertainSelect, true
}

func hypothesisShape(n compiledNode, index, dimensions int) bool {
	for _, in := range n.inputs {
		if int(in) >= index {
			return false
		}
	}
	switch n.op {
	case opConstant:
		return len(n.inputs) == 0 && isFinite(n.value)
	case opArtifactStat:
		return len(n.inputs) == 0 && n.coordinate >= 0 && n.coordinate < dimensions
	case opAdd, opMultiply:
		return true
	case opMin, opMax:
		return len(n.inputs) > 0
	case opPower:
		return len(n.inputs) == 2
	case opSelectLT:
		return len(n.inputs) == 4
	default:
		return false
	}
}

func hypothesisValid(a hypothesisInterval) bool {
	return isFinite(a.lo) && isFinite(a.hi) && a.lo <= a.hi
}

func hypothesisPower(a hypothesisInterval, exponent float64) (hypothesisInterval, bool) {
	if !isFinite(exponent) || a.lo < 0 && exponent != math.Trunc(exponent) ||
		exponent < 0 && a.lo <= 0 && a.hi >= 0 {
		return hypothesisInterval{}, false
	}
	if exponent == 0 {
		return hypothesisInterval{lo: 1, hi: 1}, true
	}
	left, right := math.Pow(a.lo, exponent), math.Pow(a.hi, exponent)
	if !isFinite(left) || !isFinite(right) {
		return hypothesisInterval{}, false
	}
	lo, hi := math.Min(left, right), math.Max(left, right)
	if a.lo <= 0 && a.hi >= 0 && exponent > 0 && math.Mod(exponent, 2) == 0 {
		lo = 0
	}
	// Go's Pow is not specified to be correctly rounded. This follows the
	// existing guarded-float interval convention and remains a numeric prototype.
	guard := 2e-12 * (1 + math.Abs(lo) + math.Abs(hi))
	b := hypothesisInterval{lo: lo - guard, hi: hi + guard}
	if a.lo >= 0 || math.Mod(exponent, 2) == 0 {
		b.lo = math.Max(0, b.lo)
	}
	return b, hypothesisValid(b)
}

// Sign bits: 1 = nondecreasing, 2 = nonincreasing, 3 = constant, 0 = unknown.
func hypothesisNodeSign(n compiledNode, coordinate int, boxes []hypothesisInterval, values []float64, signs []uint8) uint8 {
	switch n.op {
	case opConstant:
		return 3
	case opArtifactStat:
		if n.coordinate == coordinate {
			return 1
		}
		return 3
	case opAdd:
		s := uint8(3)
		for _, in := range n.inputs {
			s &= signs[in]
		}
		return s
	case opMultiply:
		s, product := uint8(3), hypothesisInterval{lo: 1, hi: 1}
		for _, in := range n.inputs {
			a := boxes[in]
			s = hypothesisFactorSign(s, a) & hypothesisFactorSign(signs[in], product)
			product.lo, product.hi = intervalProduct(product.lo, product.hi, a.lo, a.hi)
		}
		return s
	case opMin, opMax:
		merged := boxes[n.inputs[0]]
		s := signs[n.inputs[0]]
		for _, in := range n.inputs[1:] {
			a := boxes[in]
			if n.op == opMin && a.hi <= merged.lo || n.op == opMax && a.lo >= merged.hi {
				s = signs[in]
			} else if !(n.op == opMin && merged.hi <= a.lo || n.op == opMax && merged.lo >= a.hi) {
				s &= signs[in]
			}
			if n.op == opMin {
				merged.lo, merged.hi = math.Min(merged.lo, a.lo), math.Min(merged.hi, a.hi)
			} else {
				merged.lo, merged.hi = math.Max(merged.lo, a.lo), math.Max(merged.hi, a.hi)
			}
		}
		return s
	case opSelectLT:
		left, right := boxes[n.inputs[0]], boxes[n.inputs[1]]
		if left.hi < right.lo {
			return signs[n.inputs[2]]
		}
		if left.lo >= right.hi {
			return signs[n.inputs[3]]
		}
		return 0
	case opPower:
		exponent := values[n.inputs[1]]
		base := boxes[n.inputs[0]]
		s := signs[n.inputs[0]]
		if exponent == 0 {
			return 3
		}
		if exponent > 0 {
			if exponent != math.Trunc(exponent) || math.Mod(exponent, 2) != 0 {
				return s
			}
			if base.lo >= 0 {
				return s
			}
			if base.hi <= 0 {
				return hypothesisFlip(s)
			}
			return 0
		}
		if exponent == math.Trunc(exponent) && math.Mod(exponent, 2) != 0 {
			return hypothesisFlip(s)
		}
		if base.lo > 0 {
			return hypothesisFlip(s)
		}
		if base.hi < 0 {
			return s
		}
		return 0
	default:
		return 0
	}
}

func hypothesisFlip(s uint8) uint8 { return (s&1)<<1 | (s&2)>>1 }

func hypothesisFactorSign(s uint8, factor hypothesisInterval) uint8 {
	if factor.lo == 0 && factor.hi == 0 {
		return 3
	}
	if factor.lo >= 0 {
		return s
	}
	if factor.hi <= 0 {
		return hypothesisFlip(s)
	}
	if s == 3 {
		return 3
	}
	return 0
}
