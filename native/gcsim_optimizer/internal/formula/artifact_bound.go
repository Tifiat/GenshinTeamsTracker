package formula

import "math"

// An affine enclosure retains each item's joint stats. Its linear support is
// SUM_slots MAX_items dot(w,item), never a fictitious item assembled from stat
// maxima. Nonlinear/branch uncertainty lives in an outward remainder. These
// float64 bounds are guarded numerical enclosures, not a formal real-arithmetic
// certificate; unknown/singular/oversized expressions are unprunable (+Inf).
const boundDimensions = 32

type boundVector [boundDimensions]float64
type affineValue struct {
	c, r     float64
	w        boundVector
	lo, hi   float64
	enclosed bool
}
type artifactBound struct {
	d        int
	pools    [][][]float64
	patterns [][]int
	mean     boundVector
	cache    map[boundVector][2]float64
}

func (b *artifactBound) support(w boundVector) (float64, float64) {
	if v, ok := b.cache[w]; ok {
		return v[0], v[1]
	}
	lo, hi, magnitude := 0.0, 0.0, 0.0
	groupRanges := make([][2]float64, len(b.pools))
	for i, pool := range b.pools {
		a, z := math.Inf(1), math.Inf(-1)
		for _, item := range pool {
			v, abs := 0.0, 0.0
			for j := 0; j < b.d; j++ {
				v += w[j] * item[j]
				abs += math.Abs(w[j] * item[j])
			}
			g := 2e-14 * (1 + abs)
			a, z = math.Min(a, v-g), math.Max(z, v+g)
		}
		groupRanges[i] = [2]float64{a, z}
		lo, hi = lo+a, hi+z
		magnitude += math.Abs(a) + math.Abs(z)
	}
	if b.patterns != nil {
		lo, hi = math.Inf(1), math.Inf(-1)
		for _, pattern := range b.patterns {
			a, z, mag := 0.0, 0.0, 0.0
			for _, group := range pattern {
				a += groupRanges[group][0]
				z += groupRanges[group][1]
				mag += math.Abs(groupRanges[group][0]) + math.Abs(groupRanges[group][1])
			}
			lo, hi = math.Min(lo, a), math.Max(hi, z)
			magnitude = math.Max(magnitude, mag)
		}
	}
	offset := 0.0
	for j := 0; j < b.d; j++ {
		offset += w[j] * b.mean[j]
		magnitude += math.Abs(w[j] * b.mean[j])
	}
	g := 2e-13 * (1 + magnitude)
	lo, hi = lo-offset-g, hi-offset+g
	b.cache[w] = [2]float64{lo, hi}
	return lo, hi
}
func (b *artifactBound) span(a affineValue) (float64, float64) {
	if a.enclosed {
		return a.lo, a.hi
	}
	lo, hi := b.support(a.w)
	g := 2e-12 * (1 + math.Abs(a.c) + math.Abs(lo) + math.Abs(hi) + a.r)
	return a.c + lo - a.r - g, a.c + hi + a.r + g
}
func (b *artifactBound) deviation(a affineValue) float64 {
	if a.enclosed {
		return math.Max(math.Abs(a.lo-a.c), math.Abs(a.hi-a.c))
	}
	lo, hi := b.support(a.w)
	return math.Max(math.Abs(lo), math.Abs(hi)) + a.r
}
func affineFixed(a affineValue) bool {
	if a.r != 0 {
		return false
	}
	for _, v := range a.w {
		if v != 0 {
			return false
		}
	}
	return true
}
func affineScale(a affineValue, v float64) affineValue {
	a.enclosed = false
	a.c *= v
	a.r *= math.Abs(v)
	for j := range a.w {
		a.w[j] *= v
	}
	return a
}
func affinePlus(a, z affineValue) affineValue {
	a.enclosed = false
	a.c += z.c
	a.r += z.r
	for j := range a.w {
		a.w[j] += z.w[j]
	}
	return a
}
func affineInterval(lo, hi float64) affineValue { return affineValue{c: lo/2 + hi/2, r: (hi - lo) / 2} }
func (b *artifactBound) multiply(a, z affineValue) affineValue {
	if affineFixed(a) {
		return affineScale(z, a.c)
	}
	if affineFixed(z) {
		return affineScale(a, z.c)
	}
	r := affineValue{c: a.c * z.c, r: math.Abs(a.c)*z.r + math.Abs(z.c)*a.r + b.deviation(a)*b.deviation(z)}
	for j := 0; j < b.d; j++ {
		r.w[j] = a.c*z.w[j] + z.c*a.w[j]
	}
	return r
}
func (b *artifactBound) power(a, z affineValue) affineValue {
	if !affineFixed(z) {
		return affineValue{r: math.Inf(1)}
	}
	p := z.c
	if p == 0 {
		return affineValue{c: 1}
	}
	if p == 1 {
		return a
	}
	lo, hi := b.span(a)
	if lo <= 0 && (p < 0 || p != math.Trunc(p)) {
		return affineValue{r: math.Inf(1)}
	}
	c := lo/2 + hi/2
	slope := p * math.Pow(c, p-1)
	curvature := math.Abs(p*(p-1)) * math.Max(math.Abs(math.Pow(lo, p-2)), math.Abs(math.Pow(hi, p-2)))
	r := affineScale(a, slope)
	r.c += math.Pow(c, p) - slope*c
	r.r += .5 * curvature * math.Pow((hi-lo)/2, 2)
	return r
}

// Upper bounds this exact fixed-context program over every combination of the
// supplied real vectors. Relaxing set/ID constraints here is safe (looser), but
// a returned point is NEVER assumed physically legal by this arithmetic layer.
func (p *ArtifactProgram) Upper(pools [][][]float64, ref []float64) (float64, []float64) {
	if p.unresolved {
		return math.Inf(1), make([]float64, len(p.coordinates))
	}
	return p.modelUpper(pools, ref)
}

// Potential ranks work inside the stated approximate model. Its finite value
// does NOT become a damage upper bound when dependencies/coverage are unknown.
// Keep it separate from Upper so approximation never authorizes hard pruning.
func (p *ArtifactProgram) Potential(pools [][][]float64, ref []float64) float64 {
	u, _ := p.modelUpper(pools, ref)
	return u
}

// PotentialUnion encloses the UNION of slot patterns in one graph traversal.
// Repeated slot/family pools are evaluated once per linear support direction,
// not once per pattern. Every support still chooses complete real item vectors;
// a pattern controls which five families may occur together. The shared affine
// remainder may be looser than separate pattern bounds, so use this for cheap
// package ordering and refine selected regions later. No pattern is discarded.
func (p *ArtifactProgram) PotentialUnion(groups [][][]float64, patterns [][]int, ref []float64) float64 {
	if len(ref) != len(p.coordinates) || len(ref) > boundDimensions || len(groups) == 0 || len(patterns) == 0 {
		return math.Inf(1)
	}
	b := artifactBound{d: len(ref), pools: groups, patterns: patterns, cache: map[boundVector][2]float64{}}
	means := make([]boundVector, len(groups))
	for i, group := range groups {
		if len(group) == 0 {
			return math.Inf(1)
		}
		for _, item := range group {
			if len(item) != b.d {
				return math.Inf(1)
			}
			for j, x := range item {
				if !isFinite(x) {
					return math.Inf(1)
				}
				means[i][j] += x / float64(len(group))
			}
		}
	}
	for _, pattern := range patterns {
		if len(pattern) == 0 {
			return math.Inf(1)
		}
		for _, group := range pattern {
			if group < 0 || group >= len(groups) {
				return math.Inf(1)
			}
			for j := 0; j < b.d; j++ {
				b.mean[j] += means[group][j] / float64(len(patterns))
			}
		}
	}
	upper, _ := p.boundUpper(&b, ref)
	return upper
}

func (p *ArtifactProgram) modelUpper(pools [][][]float64, ref []float64) (float64, []float64) {
	unbounded := func() (float64, []float64) { return math.Inf(1), make([]float64, len(p.coordinates)) }
	if len(ref) != len(p.coordinates) || len(ref) > boundDimensions || len(pools) == 0 {
		return unbounded()
	}
	b := artifactBound{d: len(ref), pools: pools, cache: map[boundVector][2]float64{}}
	for _, pool := range pools {
		if len(pool) == 0 {
			return unbounded()
		}
		for _, item := range pool {
			if len(item) != b.d {
				return unbounded()
			}
			for j, v := range item {
				b.mean[j] += v / float64(len(pool))
			}
		}
	}
	return p.boundUpper(&b, ref)
}

func (p *ArtifactProgram) boundUpper(b *artifactBound, ref []float64) (float64, []float64) {
	unbounded := func() (float64, []float64) { return math.Inf(1), make([]float64, len(p.coordinates)) }
	values := make([]affineValue, len(p.nodes))
	for i, n := range p.nodes {
		r := affineValue{}
		switch n.op {
		case opConstant:
			r.c = n.value
		case opArtifactStat:
			r.c = b.mean[n.coordinate] - ref[n.coordinate]
			r.w[n.coordinate] = 1
		case opAdd:
			for _, in := range n.inputs {
				r = affinePlus(r, values[in])
			}
		case opMultiply:
			r.c = 1
			for _, in := range n.inputs {
				r = b.multiply(r, values[in])
			}
		case opPower:
			r = b.power(values[n.inputs[0]], values[n.inputs[1]])
		case opMin, opMax:
			r = values[n.inputs[0]]
			for _, in := range n.inputs[1:] {
				z := values[in]
				dl, dh := b.span(affinePlus(r, affineScale(z, -1)))
				if n.op == opMin && dh <= 0 || n.op == opMax && dl >= 0 {
					continue
				}
				if n.op == opMin && dl >= 0 || n.op == opMax && dh <= 0 {
					r = z
					continue
				}
				al, ah := b.span(r)
				zl, zh := b.span(z)
				if n.op == opMin {
					r = affineInterval(math.Min(al, zl), math.Min(ah, zh))
				} else {
					r = affineInterval(math.Max(al, zl), math.Max(ah, zh))
				}
			}
		case opSelectLT:
			dl, dh := b.span(affinePlus(values[n.inputs[0]], affineScale(values[n.inputs[1]], -1)))
			if dh < 0 {
				r = values[n.inputs[2]]
			} else if dl >= 0 {
				r = values[n.inputs[3]]
			} else {
				al, ah := b.span(values[n.inputs[2]])
				zl, zh := b.span(values[n.inputs[3]])
				r = affineInterval(math.Min(al, zl), math.Max(ah, zh))
			}
		default:
			return unbounded()
		}
		if !affineFixed(r) {
			r.r += 2e-13 * (1 + math.Abs(r.c) + r.r)
		}
		nl, nh, natural := naturalInterval(n, values)
		valid := isFinite(r.c) && isFinite(r.r)
		for _, v := range r.w {
			valid = valid && isFinite(v)
		}
		if !valid {
			// A valid capped square root at zero has an unbounded derivative,
			// not unbounded damage. Keep its finite source-operation interval.
			if !natural {
				return unbounded()
			}
			r = affineInterval(nl, nh)
		}
		lo, hi := b.span(r)
		if natural {
			lo, hi = math.Max(lo, nl), math.Min(hi, nh)
		}
		if !isFinite(lo) || !isFinite(hi) || lo > hi {
			return unbounded()
		}
		if affineFixed(r) {
			lo, hi = r.c, r.c
		}
		r.lo, r.hi, r.enclosed = lo, hi, true
		values[i] = r
	}
	r := values[p.root]
	_, hi := b.span(r)
	if math.IsNaN(hi) {
		return unbounded()
	}
	w := make([]float64, b.d)
	copy(w, r.w[:b.d])
	return hi, w
}
