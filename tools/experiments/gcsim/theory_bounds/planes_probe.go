package formula

// Research-only alternative enclosure, copied into the managed scratch package.
// The two planes at each node bound its value pointwise on the supplied domain.
// Support is over absolute artifact coordinates, as in ResearchEnvelope.
import "math"

const researchPlaneDimensions = 128

type researchPlane struct {
	c float64
	w [researchPlaneDimensions]float64
}

type researchPlaneValue struct {
	lower, upper researchPlane
	lo, hi       float64
	exact        bool
	exactValue   float64
}

type researchPlaneTerm struct {
	scale float64
	plane researchPlane
}

type researchPlanes struct {
	d, calls int
	center   []float64
	callback func([]float64) (float64, float64)
	radius   [researchPlaneDimensions]float64
	cache    map[[researchPlaneDimensions]float64][2]float64
	failed   bool
}

func researchExact(v float64) researchPlaneValue {
	p := researchPlane{c: v}
	return researchPlaneValue{lower: p, upper: p, lo: v, hi: v, exact: true, exactValue: v}
}

func (b *researchPlanes) support(w [researchPlaneDimensions]float64) (float64, float64) {
	if b.failed {
		return math.Inf(-1), math.Inf(1)
	}
	zero := true
	for j := 0; j < b.d; j++ {
		if !isFinite(w[j]) {
			b.failed = true
			return math.Inf(-1), math.Inf(1)
		}
		zero = zero && w[j] == 0
	}
	if zero {
		return 0, 0
	}
	if v, ok := b.cache[w]; ok {
		return v[0], v[1]
	}
	q := make([]float64, b.d)
	copy(q, w[:b.d])
	b.calls++
	lo, hi := b.callback(q)
	if !isFinite(lo) || !isFinite(hi) || lo > hi {
		b.failed = true
		return math.Inf(-1), math.Inf(1)
	}
	offset, magnitude := 0.0, math.Abs(lo)+math.Abs(hi)
	for j := 0; j < b.d; j++ {
		term := w[j] * b.center[j]
		offset += term
		magnitude += math.Abs(term)
	}
	guard := 4e-12 * (1 + magnitude)
	lo, hi = down(lo-offset-guard), up(hi-offset+guard)
	if !isFinite(lo) || !isFinite(hi) || lo > hi {
		b.failed = true
		return math.Inf(-1), math.Inf(1)
	}
	b.cache[w] = [2]float64{lo, hi}
	return lo, hi
}

// The constant guard covers coefficient arithmetic and its evaluation at the
// largest possible coordinate displacement. It is deliberately wider than the
// support callback's own rounding guard; these are guarded floats, not proof
// certificates for exact real arithmetic.
func (b *researchPlanes) compose(base float64, terms []researchPlaneTerm, lower bool) researchPlane {
	p := researchPlane{c: base}
	magnitude := math.Abs(base)
	for _, term := range terms {
		v := term.scale * term.plane.c
		p.c += v
		magnitude += math.Abs(v)
		for j := 0; j < b.d; j++ {
			v = term.scale * term.plane.w[j]
			p.w[j] += v
			magnitude += math.Abs(v) * b.radius[j]
		}
	}
	guard := 8e-12 * (1 + magnitude)
	if lower {
		p.c = down(p.c - guard)
	} else {
		p.c = up(p.c + guard)
	}
	if !isFinite(p.c) {
		b.failed = true
	}
	for j := 0; j < b.d; j++ {
		if !isFinite(p.w[j]) {
			b.failed = true
		}
	}
	return p
}

func (b *researchPlanes) planeExtreme(p researchPlane, upper bool) float64 {
	lo, hi := b.support(p.w)
	if !isFinite(p.c) || !isFinite(lo) || !isFinite(hi) {
		b.failed = true
		return math.NaN()
	}
	v := p.c + lo
	if upper {
		v = p.c + hi
	}
	guard := 4e-12 * (1 + math.Abs(p.c) + math.Abs(lo) + math.Abs(hi))
	if !isFinite(v) || !isFinite(guard) {
		b.failed = true
		return math.NaN()
	}
	if upper {
		v = up(v + guard)
	} else {
		v = down(v - guard)
	}
	if !isFinite(v) {
		b.failed = true
		return math.NaN()
	}
	return v
}

func (b *researchPlanes) finish(v researchPlaneValue, naturalLo, naturalHi float64) researchPlaneValue {
	if v.exact {
		v.lo, v.hi = v.exactValue, v.exactValue
		if v.lo < naturalLo || v.hi > naturalHi {
			b.failed = true
		}
		return v
	}
	v.lo = math.Max(b.planeExtreme(v.lower, false), naturalLo)
	v.hi = math.Min(b.planeExtreme(v.upper, true), naturalHi)
	if !isFinite(v.lo) || !isFinite(v.hi) || v.lo > v.hi {
		b.failed = true
	}
	return v
}

func (b *researchPlanes) choose(candidates []researchPlane, upper bool) researchPlane {
	best, score := researchPlane{c: math.NaN()}, math.Inf(-1)
	if upper {
		score = math.Inf(1)
	}
	found := false
	for _, candidate := range candidates {
		v := b.planeExtreme(candidate, upper)
		if b.failed || !isFinite(v) {
			b.failed = true
			return researchPlane{c: math.NaN()}
		}
		if !found || upper && v < score || !upper && v > score {
			best, score, found = candidate, v, true
		}
	}
	if !found {
		b.failed = true
	}
	return best
}

func (b *researchPlanes) withAverage(a, z researchPlane, lower bool) []researchPlane {
	mid := b.compose(0, []researchPlaneTerm{{.5, a}, {.5, z}}, lower)
	return []researchPlane{a, z, mid}
}

func (b *researchPlanes) scale(a researchPlaneValue, k float64) researchPlaneValue {
	if k == 0 {
		return researchExact(0)
	}
	if a.exact {
		v := k * a.exactValue
		if !isFinite(v) {
			b.failed = true
		}
		return researchExact(v)
	}
	v := researchPlaneValue{}
	if k > 0 {
		v.lower = b.compose(0, []researchPlaneTerm{{k, a.lower}}, true)
		v.upper = b.compose(0, []researchPlaneTerm{{k, a.upper}}, false)
	} else {
		v.lower = b.compose(0, []researchPlaneTerm{{k, a.upper}}, true)
		v.upper = b.compose(0, []researchPlaneTerm{{k, a.lower}}, false)
	}
	lo, hi := intervalProduct(k, k, a.lo, a.hi)
	return b.finish(v, lo, hi)
}

func (b *researchPlanes) add(a, z researchPlaneValue) researchPlaneValue {
	if a.exact && z.exact {
		v := a.exactValue + z.exactValue
		if !isFinite(v) {
			b.failed = true
		}
		return researchExact(v)
	}
	v := researchPlaneValue{
		lower: b.compose(0, []researchPlaneTerm{{1, a.lower}, {1, z.lower}}, true),
		upper: b.compose(0, []researchPlaneTerm{{1, a.upper}, {1, z.upper}}, false),
	}
	return b.finish(v, down(a.lo+z.lo), up(a.hi+z.hi))
}

func (b *researchPlanes) productCandidate(a, z researchPlaneValue, ak, zk, base float64, lower bool) researchPlane {
	ap, zp := a.lower, z.lower
	if lower {
		if ak < 0 {
			ap = a.upper
		}
		if zk < 0 {
			zp = z.upper
		}
	} else {
		if ak < 0 {
			ap = a.lower
		} else {
			ap = a.upper
		}
		if zk < 0 {
			zp = z.lower
		} else {
			zp = z.upper
		}
	}
	return b.compose(base, []researchPlaneTerm{{ak, ap}, {zk, zp}}, lower)
}

func (b *researchPlanes) multiply(a, z researchPlaneValue) researchPlaneValue {
	if a.exact {
		return b.scale(z, a.exactValue)
	}
	if z.exact {
		return b.scale(a, z.exactValue)
	}
	al, ah, zl, zh := a.lo, a.hi, z.lo, z.hi
	// McCormick's four inequalities, with each signed coefficient applied to
	// the appropriate side of the child enclosure before choosing a plane.
	l1 := b.productCandidate(a, z, zl, al, -al*zl, true)
	l2 := b.productCandidate(a, z, zh, ah, -ah*zh, true)
	u1 := b.productCandidate(a, z, zl, ah, -ah*zl, false)
	u2 := b.productCandidate(a, z, zh, al, -al*zh, false)
	v := researchPlaneValue{
		lower: b.choose(b.withAverage(l1, l2, true), false),
		upper: b.choose(b.withAverage(u1, u2, false), true),
	}
	lo, hi := intervalProduct(al, ah, zl, zh)
	return b.finish(v, lo, hi)
}

func (b *researchPlanes) cap(a researchPlaneValue, c float64, minimum bool) researchPlaneValue {
	if a.exact {
		if minimum {
			return researchExact(math.Min(a.exactValue, c))
		}
		return researchExact(math.Max(a.exactValue, c))
	}
	if minimum && a.hi <= c || !minimum && a.lo >= c {
		return a
	}
	if minimum && a.lo >= c || !minimum && a.hi <= c {
		return researchExact(c)
	}
	s := (c - a.lo) / (a.hi - a.lo)
	if !minimum {
		s = (a.hi - c) / (a.hi - a.lo)
	}
	if !isFinite(s) {
		b.failed = true
		return researchPlaneValue{}
	}
	s = math.Max(0, math.Min(1, s))
	left, right := s*a.lo, s*a.hi
	base := math.Min(a.lo-left, c-right)
	if !minimum {
		base = math.Max(c-left, a.hi-right)
	}
	// Anchor both endpoints after rounding the secant slope. A line below
	// the two min endpoints stays below their concave piecewise graph; the
	// dual statement holds for max and its upper secant.
	slack := 8e-12 * (1 + math.Abs(a.lo) + math.Abs(a.hi) + math.Abs(c) + math.Abs(left) + math.Abs(right))
	if minimum {
		base = down(base - slack)
	} else {
		base = up(base + slack)
	}
	if !isFinite(base) {
		b.failed = true
		return researchPlaneValue{}
	}
	v := researchPlaneValue{}
	if minimum {
		secant := b.compose(base, []researchPlaneTerm{{s, a.lower}}, true)
		v.lower = b.choose([]researchPlane{secant, {c: a.lo}}, false)
		v.upper = b.choose(b.withAverage(a.upper, researchPlane{c: c}, false), true)
		return b.finish(v, math.Min(a.lo, c), math.Min(a.hi, c))
	}
	v.lower = b.choose(b.withAverage(a.lower, researchPlane{c: c}, true), false)
	secant := b.compose(base, []researchPlaneTerm{{s, a.upper}}, false)
	v.upper = b.choose([]researchPlane{secant, {c: a.hi}}, true)
	return b.finish(v, math.Max(a.lo, c), math.Max(a.hi, c))
}

func (b *researchPlanes) minmax(a, z researchPlaneValue, minimum bool) researchPlaneValue {
	if a.exact && z.exact {
		if minimum {
			return researchExact(math.Min(a.exactValue, z.exactValue))
		}
		return researchExact(math.Max(a.exactValue, z.exactValue))
	}
	if minimum && a.hi <= z.lo || !minimum && a.lo >= z.hi {
		return a
	}
	if minimum && z.hi <= a.lo || !minimum && z.lo >= a.hi {
		return z
	}
	if a.exact {
		return b.cap(z, a.exactValue, minimum)
	}
	if z.exact {
		return b.cap(a, z.exactValue, minimum)
	}
	v := researchPlaneValue{}
	if minimum {
		v.lower = researchPlane{c: math.Min(a.lo, z.lo)}
		v.upper = b.choose(b.withAverage(a.upper, z.upper, false), true)
		return b.finish(v, math.Min(a.lo, z.lo), math.Min(a.hi, z.hi))
	}
	v.lower = b.choose(b.withAverage(a.lower, z.lower, true), false)
	v.upper = researchPlane{c: math.Max(a.hi, z.hi)}
	return b.finish(v, math.Max(a.lo, z.lo), math.Max(a.hi, z.hi))
}

// ResearchPlanes uses absolute support statistics and the same reference
// convention as ResearchEnvelope. A finite ModelUpper describes only this
// fixed arithmetic graph; unresolved source dependencies keep Upper infinite.
func (p *ArtifactProgram) ResearchPlanes(center, ref []float64, support func([]float64) (float64, float64)) (r ResearchEnvelopeResult) {
	r = ResearchEnvelopeResult{Upper: math.Inf(1), ModelUpper: math.Inf(1)}
	if p == nil {
		return r
	}
	r.Nodes, r.Dimensions, r.Unresolved = len(p.nodes), len(p.coordinates), p.unresolved
	d := len(p.coordinates)
	if len(center) != d || len(ref) != d || d > researchPlaneDimensions || support == nil || len(p.nodes) == 0 || int(p.root) >= len(p.nodes) {
		return r
	}
	for j := 0; j < d; j++ {
		if !isFinite(center[j]) || !isFinite(ref[j]) {
			return r
		}
	}
	b := researchPlanes{d: d, center: center, callback: support, cache: map[[researchPlaneDimensions]float64][2]float64{}}
	defer func() { r.SupportCalls = b.calls }()
	var used [researchPlaneDimensions]bool
	for _, n := range p.nodes {
		if n.op == opArtifactStat {
			if n.coordinate < 0 || n.coordinate >= d {
				return r
			}
			used[n.coordinate] = true
		}
	}
	for j := 0; j < d; j++ {
		if !used[j] {
			continue
		}
		var w [researchPlaneDimensions]float64
		w[j] = 1
		lo, hi := b.support(w)
		b.radius[j] = math.Max(math.Abs(lo), math.Abs(hi))
		if b.failed || !isFinite(b.radius[j]) {
			r.SupportCalls = b.calls
			return r
		}
	}
	values := make([]researchPlaneValue, len(p.nodes))
	natural := make([]affineValue, len(p.nodes))
	for i, n := range p.nodes {
		for _, id := range n.inputs {
			if int(id) >= i {
				r.SupportCalls = b.calls
				return r
			}
		}
		v := researchPlaneValue{}
		switch n.op {
		case opConstant:
			if !isFinite(n.value) {
				return r
			}
			v = researchExact(n.value)
		case opArtifactStat:
			if n.coordinate < 0 || n.coordinate >= d {
				return r
			}
			c := center[n.coordinate] - ref[n.coordinate]
			guard := 8e-12 * (1 + math.Abs(center[n.coordinate]) + math.Abs(ref[n.coordinate]))
			v.lower.c, v.upper.c = down(c-guard), up(c+guard)
			v.lower.w[n.coordinate], v.upper.w[n.coordinate] = 1, 1
			v = b.finish(v, math.Inf(-1), math.Inf(1))
		case opAdd:
			v = researchExact(0)
			for _, id := range n.inputs {
				v = b.add(v, values[id])
			}
		case opMultiply:
			v = researchExact(1)
			for _, id := range n.inputs {
				v = b.multiply(v, values[id])
			}
		case opMin, opMax:
			if len(n.inputs) == 0 {
				return r
			}
			v = values[n.inputs[0]]
			for _, id := range n.inputs[1:] {
				v = b.minmax(v, values[id], n.op == opMin)
			}
		case opSelectLT:
			if len(n.inputs) != 4 {
				return r
			}
			a, z := values[n.inputs[0]], values[n.inputs[1]]
			if a.hi < z.lo {
				v = values[n.inputs[2]]
			} else if a.lo >= z.hi {
				v = values[n.inputs[3]]
			} else {
				left, right := values[n.inputs[2]], values[n.inputs[3]]
				if left.exact && right.exact && left.exactValue == right.exactValue {
					v = left
				} else {
					v.lower = researchPlane{c: math.Min(left.lo, right.lo)}
					v.upper = researchPlane{c: math.Max(left.hi, right.hi)}
					v = b.finish(v, math.Min(left.lo, right.lo), math.Max(left.hi, right.hi))
				}
			}
		case opPower:
			if len(n.inputs) != 2 {
				return r
			}
			a, exponent := values[n.inputs[0]], values[n.inputs[1]]
			if !exponent.exact {
				return r
			}
			if exponent.exactValue == 0 {
				v = researchExact(1)
			} else if exponent.exactValue == 1 {
				v = a
			} else {
				lo, hi, ok := naturalInterval(n, natural)
				if !ok {
					return r
				}
				if a.exact {
					pow := math.Pow(a.exactValue, exponent.exactValue)
					if !isFinite(pow) {
						return r
					}
					v = researchExact(pow)
				} else {
					v.lower, v.upper = researchPlane{c: lo}, researchPlane{c: hi}
					v = b.finish(v, lo, hi)
				}
			}
		default:
			return r
		}
		if b.failed {
			r.SupportCalls = b.calls
			return r
		}
		if n.op != opArtifactStat {
			lo, hi, ok := naturalInterval(n, natural)
			if !ok {
				r.SupportCalls = b.calls
				return r
			}
			v = b.finish(v, lo, hi)
		}
		if b.failed {
			r.SupportCalls = b.calls
			return r
		}
		values[i] = v
		natural[i] = affineValue{c: v.exactValue, lo: v.lo, hi: v.hi, enclosed: true}
		if !v.exact {
			natural[i].r = 1 // Prevent a variable exponent from appearing fixed.
		}
	}
	r.SupportCalls, r.ModelUpper = b.calls, values[p.root].hi
	if !p.unresolved {
		r.Upper = r.ModelUpper
	}
	return r
}
