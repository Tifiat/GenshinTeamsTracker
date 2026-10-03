package formula

// Natural intervals complement, never replace, real-vector affine supports.
// Intersect at every node: affine supports retain joint item correlations;
// intervals retain exact clamp signs and tame accumulated nonlinear remainder.
// These share the existing guarded-float contract, not a real-arithmetic proof.
import "math"

func down(x float64) float64 { return math.Nextafter(x, math.Inf(-1)) }
func up(x float64) float64   { return math.Nextafter(x, math.Inf(1)) }

func intervalProduct(al, ah, bl, bh float64) (float64, float64) {
	a, b, c, d := al*bl, al*bh, ah*bl, ah*bh
	lo, hi := down(math.Min(math.Min(a, b), math.Min(c, d))), up(math.Max(math.Max(a, b), math.Max(c, d)))
	if al >= 0 && bl >= 0 || ah <= 0 && bh <= 0 {
		lo = math.Max(0, lo)
	}
	if al >= 0 && bh <= 0 || ah <= 0 && bl >= 0 {
		hi = math.Min(0, hi)
	}
	return lo, hi
}

func naturalInterval(n compiledNode, values []affineValue) (lo, hi float64, ok bool) {
	span := func(id uint32) (float64, float64) { return values[id].lo, values[id].hi }
	if n.op == opArtifactStat {
		return 0, 0, false
	}
	if n.op == opConstant {
		return n.value, n.value, true
	}
	for _, id := range n.inputs {
		if !values[id].enclosed {
			return 0, 0, false
		}
	}
	switch n.op {
	case opAdd:
		for _, id := range n.inputs {
			a, z := span(id)
			nonnegative, nonpositive := lo >= 0 && a >= 0, hi <= 0 && z <= 0
			lo, hi = down(lo+a), up(hi+z)
			if nonnegative {
				lo = math.Max(0, lo)
			}
			if nonpositive {
				hi = math.Min(0, hi)
			}
		}
	case opMultiply:
		lo, hi = 1, 1
		for _, id := range n.inputs {
			a, z := span(id)
			lo, hi = intervalProduct(lo, hi, a, z)
		}
	case opMin, opMax:
		lo, hi = span(n.inputs[0])
		for _, id := range n.inputs[1:] {
			a, z := span(id)
			if n.op == opMin {
				lo, hi = math.Min(lo, a), math.Min(hi, z)
			} else {
				lo, hi = math.Max(lo, a), math.Max(hi, z)
			}
		}
	case opSelectLT:
		al, ah := span(n.inputs[0])
		bl, bh := span(n.inputs[1])
		if ah < bl {
			lo, hi = span(n.inputs[2])
		} else if al >= bh {
			lo, hi = span(n.inputs[3])
		} else {
			a, z := span(n.inputs[2])
			b, y := span(n.inputs[3])
			lo, hi = math.Min(a, b), math.Max(z, y)
		}
	case opPower:
		if !affineFixed(values[n.inputs[1]]) {
			return 0, 0, false
		}
		power := values[n.inputs[1]].c
		a, z := span(n.inputs[0])
		if a < 0 && power != math.Trunc(power) || a <= 0 && z >= 0 && power < 0 {
			return 0, 0, false
		}
		if power == 0 {
			return 1, 1, true
		}
		left, right := math.Pow(a, power), math.Pow(z, power)
		lo, hi = math.Min(left, right), math.Max(left, right)
		if a <= 0 && z >= 0 && power > 0 && math.Mod(power, 2) == 0 {
			lo = 0
		}
		// Pow is not guaranteed correctly rounded. Retain the same conservative
		// numerical guard as the affine route; an exact zero endpoint stays zero
		// when nonnegativity follows from the operation's domain.
		guard := 2e-12 * (1 + math.Abs(lo) + math.Abs(hi))
		lo, hi = lo-guard, hi+guard
		if a >= 0 || math.Mod(power, 2) == 0 {
			lo = math.Max(0, lo)
		}
	default:
		return 0, 0, false
	}
	return lo, hi, isFinite(lo) && isFinite(hi) && lo <= hi
}
