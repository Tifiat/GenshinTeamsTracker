package formula

// Research-only targeted enclosures, copied into managed scratch alongside the
// affine probe. Source nodes, not game-specific coefficients, identify the two
// replacements. All other nodes retain the ordinary affine traversal.
import "math"

type ResearchTargetedResult struct {
	ResearchEnvelopeResult
	Caps, Rationals int
}

// A source-linear form is exact algebraically in the artifact coordinates.
// err encloses float evaluation and coefficient-rounding differences. It is
// never discarded when a form participates in a targeted replacement.
type targetLinear struct {
	c     float64
	w     boundVector
	err   float64
	valid bool
	fixed bool // Structural constant, including constant-only arithmetic.
}

type targetContext struct {
	b           *artifactBound
	radius      boundVector
	radiusReady [boundDimensions]bool
	forms       []targetLinear
}

func targetConstant(c float64) targetLinear {
	return targetLinear{c: c, valid: isFinite(c), fixed: true}
}

func (t *targetContext) coordinateRadius(j int) float64 {
	if !t.radiusReady[j] {
		var w boundVector
		w[j] = 1
		lo, hi := t.b.support(w)
		t.radius[j] = math.Max(math.Abs(lo), math.Abs(hi))
		t.radiusReady[j] = true
	}
	return t.radius[j]
}

func (t *targetContext) finite(f targetLinear) bool {
	if !f.valid || !isFinite(f.c) || !isFinite(f.err) || f.err < 0 {
		return false
	}
	for j := 0; j < t.b.d; j++ {
		if !isFinite(f.w[j]) {
			return false
		}
	}
	return true
}

func (t *targetContext) add(a, z targetLinear) targetLinear {
	if !t.finite(a) || !t.finite(z) {
		return targetLinear{}
	}
	if a.fixed && z.fixed {
		return targetConstant(a.c + z.c)
	}
	r := targetLinear{c: a.c + z.c, err: a.err + z.err, valid: true}
	magnitude := math.Abs(a.c) + math.Abs(z.c)
	for j := 0; j < t.b.d; j++ {
		r.w[j] = a.w[j] + z.w[j]
		if a.w[j] != 0 || z.w[j] != 0 {
			magnitude += (math.Abs(a.w[j]) + math.Abs(z.w[j])) * t.coordinateRadius(j)
		}
	}
	r.err += 8e-12 * (1 + magnitude)
	r.valid = t.finite(r)
	return r
}

func (t *targetContext) scale(a targetLinear, k float64) targetLinear {
	if !t.finite(a) || !isFinite(k) {
		return targetLinear{}
	}
	if a.fixed || k == 0 {
		return targetConstant(k * a.c)
	}
	r := targetLinear{c: k * a.c, err: math.Abs(k) * a.err, valid: true}
	magnitude := math.Abs(k*a.c) + math.Abs(k)*math.Abs(a.c)
	for j := 0; j < t.b.d; j++ {
		r.w[j] = k * a.w[j]
		if a.w[j] != 0 {
			magnitude += math.Abs(r.w[j]) * t.coordinateRadius(j)
		}
	}
	r.err += 8e-12 * (1 + magnitude)
	r.valid = t.finite(r)
	return r
}

func (t *targetContext) product(inputs []uint32) targetLinear {
	r := targetConstant(1)
	for _, id := range inputs {
		z := t.forms[id]
		if !t.finite(z) {
			return targetLinear{}
		}
		if r.fixed {
			r = t.scale(z, r.c)
		} else if z.fixed {
			r = t.scale(r, z.c)
		} else {
			return targetLinear{}
		}
		if !t.finite(r) {
			return targetLinear{}
		}
	}
	return r
}

func (t *targetContext) span(f targetLinear) (float64, float64, bool) {
	if !t.finite(f) {
		return 0, 0, false
	}
	if f.fixed {
		return f.c, f.c, true
	}
	lo, hi := t.b.support(f.w)
	guard := 8e-12 * (1 + math.Abs(f.c) + math.Abs(lo) + math.Abs(hi) + f.err)
	lo, hi = down(f.c+lo-f.err-guard), up(f.c+hi+f.err+guard)
	return lo, hi, isFinite(lo) && isFinite(hi) && lo <= hi
}

func (t *targetContext) sourceForm(n compiledNode, center, ref []float64) targetLinear {
	switch n.op {
	case opConstant:
		return targetConstant(n.value)
	case opArtifactStat:
		if n.coordinate < 0 || n.coordinate >= t.b.d {
			return targetLinear{}
		}
		j := n.coordinate
		f := targetLinear{c: center[j] - ref[j], err: 8e-12 * (1 + math.Abs(center[j]) + math.Abs(ref[j])), valid: true}
		f.w[j] = 1
		f.valid = t.finite(f)
		return f
	case opAdd:
		r := targetConstant(0)
		for _, id := range n.inputs {
			r = t.add(r, t.forms[id])
		}
		return r
	case opMultiply:
		return t.product(n.inputs)
	case opPower:
		if len(n.inputs) != 2 {
			return targetLinear{}
		}
		exp := t.forms[n.inputs[1]]
		if !exp.valid || !exp.fixed {
			return targetLinear{}
		}
		if exp.c == 0 {
			return targetConstant(1)
		}
		if exp.c == 1 {
			return t.forms[n.inputs[0]]
		}
	case opMin, opMax:
		if len(n.inputs) == 0 {
			return targetLinear{}
		}
		r := t.forms[n.inputs[0]]
		for _, id := range n.inputs[1:] {
			z := t.forms[id]
			if !t.finite(r) || !t.finite(z) {
				return targetLinear{}
			}
			if r.fixed && z.fixed {
				if n.op == opMin {
					r = targetConstant(math.Min(r.c, z.c))
				} else {
					r = targetConstant(math.Max(r.c, z.c))
				}
				continue
			}
			if !r.fixed && !z.fixed {
				return targetLinear{}
			}
			variable, cap := r, z.c
			if !z.fixed {
				variable, cap = z, r.c
			}
			lo, hi, ok := t.span(variable)
			if !ok {
				return targetLinear{}
			}
			if n.op == opMin && hi <= cap || n.op == opMax && lo >= cap {
				r = variable
			} else if n.op == opMin && lo >= cap || n.op == opMax && hi <= cap {
				r = targetConstant(cap)
			} else {
				return targetLinear{}
			}
		}
		return r
	}
	return targetLinear{}
}

// Every candidate is intersected with the original node's already guarded
// interval. This intersection changes the reported span, never the affine
// coefficients or remainder that later nodes use.
func (t *targetContext) enclosure(form targetLinear, slope, intercept, errorLo, errorHi float64, old affineValue) (affineValue, bool) {
	if !t.finite(form) || !isFinite(slope) || !isFinite(intercept) || !isFinite(errorLo) || !isFinite(errorHi) || errorLo > errorHi {
		return affineValue{}, false
	}
	mid := errorLo/2 + errorHi/2
	rad := errorHi/2 - errorLo/2
	v := affineValue{c: intercept + slope*form.c + mid}
	magnitude := math.Abs(intercept) + math.Abs(slope*form.c) + math.Abs(mid) + math.Abs(errorLo) + math.Abs(errorHi)
	for j := 0; j < t.b.d; j++ {
		v.w[j] = slope * form.w[j]
		if form.w[j] != 0 {
			magnitude += math.Abs(v.w[j]) * t.coordinateRadius(j)
		}
	}
	guard := 8e-12 * (1 + magnitude + math.Abs(old.lo) + math.Abs(old.hi))
	v.r = rad + math.Abs(slope)*form.err + guard
	if !isFinite(v.c) || !isFinite(v.r) || v.r < 0 {
		return affineValue{}, false
	}
	for j := 0; j < t.b.d; j++ {
		if !isFinite(v.w[j]) {
			return affineValue{}, false
		}
	}
	lo, hi := t.b.span(v)
	lo, hi = math.Max(lo, old.lo), math.Min(hi, old.hi)
	if !isFinite(lo) || !isFinite(hi) || lo > hi {
		return affineValue{}, false
	}
	v.lo, v.hi, v.enclosed = lo, hi, true
	return v, true
}

func (t *targetContext) cap(n compiledNode, old affineValue) (affineValue, bool) {
	if len(n.inputs) != 2 {
		return affineValue{}, false
	}
	a, z := t.forms[n.inputs[0]], t.forms[n.inputs[1]]
	if !t.finite(a) || !t.finite(z) || a.fixed == z.fixed {
		return affineValue{}, false
	}
	variable, cap := a, z.c
	if a.fixed {
		variable, cap = z, a.c
	}
	lo, hi, ok := t.span(variable)
	if !ok || !(lo < cap && cap < hi) {
		return affineValue{}, false
	}
	left, right := lo, cap
	if n.op == opMax {
		left, right = cap, hi
	}
	slope := (right - left) / (hi - lo)
	intercept := left - slope*lo
	if !isFinite(slope) || !isFinite(intercept) {
		return affineValue{}, false
	}
	// The scalar residual is piecewise linear; all extrema are at lo, cap,
	// or hi. Include a guard for endpoint and secant arithmetic.
	errLo, errHi := math.Inf(1), math.Inf(-1)
	for _, x := range [...]float64{lo, cap, hi} {
		actual := math.Min(x, cap)
		if n.op == opMax {
			actual = math.Max(x, cap)
		}
		line := slope*x + intercept
		e := actual - line
		guard := 8e-12 * (1 + math.Abs(actual) + math.Abs(slope*x) + math.Abs(intercept))
		if !isFinite(e) || !isFinite(guard) {
			return affineValue{}, false
		}
		errLo, errHi = math.Min(errLo, e-guard), math.Max(errHi, e+guard)
	}
	return t.enclosure(variable, slope, intercept, errLo, errHi, old)
}

func (t *targetContext) rational(n compiledNode, nodes []compiledNode, old affineValue) (affineValue, bool) {
	if n.op != opMultiply || len(n.inputs) != 2 {
		return affineValue{}, false
	}
	reciprocal := -1
	for i, id := range n.inputs {
		p := nodes[id]
		if p.op == opPower && len(p.inputs) == 2 {
			exponent := t.forms[p.inputs[1]]
			if exponent.valid && exponent.fixed && exponent.c == -1 {
				if reciprocal >= 0 {
					return affineValue{}, false
				}
				reciprocal = i
			}
		}
	}
	if reciprocal < 0 {
		return affineValue{}, false
	}
	power := nodes[n.inputs[reciprocal]]
	bForm := t.forms[power.inputs[0]]
	if !t.finite(bForm) || bForm.fixed {
		return affineValue{}, false
	}
	numeratorIDs := make([]uint32, 0, len(n.inputs)-1)
	for i, id := range n.inputs {
		if i != reciprocal {
			numeratorIDs = append(numeratorIDs, id)
		}
	}
	aForm := t.product(numeratorIDs)
	if !t.finite(aForm) || aForm.fixed {
		return affineValue{}, false
	}
	lo, hi, ok := t.span(bForm)
	if !ok || lo <= 0 || lo >= hi {
		return affineValue{}, false
	}
	aLo, aHi, ok := t.span(aForm)
	if !ok {
		return affineValue{}, false
	}
	dominant := -1
	for j := 0; j < t.b.d; j++ {
		if bForm.w[j] != 0 && (dominant < 0 || math.Abs(bForm.w[j]) > math.Abs(bForm.w[dominant])) {
			dominant = j
		}
	}
	if dominant < 0 {
		return affineValue{}, false
	}
	k := aForm.w[dominant] / bForm.w[dominant]
	c := aForm.c - k*bForm.c
	if !isFinite(k) || !isFinite(c) {
		return affineValue{}, false
	}
	residual := targetLinear{valid: true}
	residual.err = aForm.err + math.Abs(k)*bForm.err
	magnitude := math.Abs(aForm.c) + math.Abs(k*bForm.c) + math.Abs(c)
	for j := 0; j < t.b.d; j++ {
		residual.w[j] = aForm.w[j] - k*bForm.w[j]
		if aForm.w[j] != 0 || bForm.w[j] != 0 {
			magnitude += (math.Abs(aForm.w[j]) + math.Abs(k*bForm.w[j])) * t.coordinateRadius(j)
		}
	}
	residual.err += 8e-12 * (1 + magnitude)
	eLo, eHi, ok := t.span(residual)
	if !ok {
		return affineValue{}, false
	}
	variation := math.Max(1, math.Max(math.Abs(k)*(hi-lo), aHi-aLo))
	if !isFinite(variation) || eHi-eLo > 1e-4*variation {
		return affineValue{}, false
	}
	recipLo, recipHi := 1/hi, 1/lo
	recipGuard := 8e-12 * (1 + math.Abs(recipLo) + math.Abs(recipHi))
	recipLo, recipHi = down(recipLo-recipGuard), up(recipHi+recipGuard)
	if !isFinite(recipLo) || !isFinite(recipHi) || recipLo <= 0 {
		return affineValue{}, false
	}
	quotLo, quotHi := intervalProduct(eLo, eHi, recipLo, recipHi)
	if !isFinite(quotLo) || !isFinite(quotHi) {
		return affineValue{}, false
	}
	slope := -(c / lo) / hi
	intercept := k + c/lo - slope*lo
	if !isFinite(slope) || !isFinite(intercept) {
		return affineValue{}, false
	}
	// c/B minus its secant has zero endpoint residual and one interior
	// extremum at sqrt(lo*hi). Evaluate all three with outward slack.
	stationary := math.Sqrt(lo) * math.Sqrt(hi)
	stationary = math.Max(lo, math.Min(hi, stationary))
	errLo, errHi := math.Inf(1), math.Inf(-1)
	for _, x := range [...]float64{lo, stationary, hi} {
		term, lineTerm := c/x, slope*x
		actual, line := k+term, intercept+lineTerm
		e := actual - line
		guard := 8e-12 * (1 + math.Abs(k) + math.Abs(term) + math.Abs(intercept) + math.Abs(lineTerm))
		if !isFinite(e) || !isFinite(guard) {
			return affineValue{}, false
		}
		errLo, errHi = math.Min(errLo, e-guard), math.Max(errHi, e+guard)
	}
	errLo, errHi = down(errLo+quotLo), up(errHi+quotHi)
	if !isFinite(errLo) || !isFinite(errHi) {
		return affineValue{}, false
	}
	return t.enclosure(bForm, slope, intercept, errLo, errHi, old)
}

// ResearchTargeted applies only the requested scalar-cap and proportional
// positive-denominator ratio replacements. center/support are absolute stats;
// ref converts the source program to local artifact deltas.
func (p *ArtifactProgram) ResearchTargeted(center, ref []float64, support func([]float64) (float64, float64), caps, rationals bool) ResearchTargetedResult {
	r := ResearchTargetedResult{ResearchEnvelopeResult: ResearchEnvelopeResult{Upper: math.Inf(1), ModelUpper: math.Inf(1)}}
	if p == nil {
		return r
	}
	r.Nodes, r.Dimensions, r.Unresolved = len(p.nodes), len(p.coordinates), p.unresolved
	if len(center) != len(p.coordinates) || len(ref) != len(center) || len(center) > boundDimensions || support == nil || len(p.nodes) == 0 || int(p.root) >= len(p.nodes) {
		return r
	}
	for j := range center {
		if !isFinite(center[j]) || !isFinite(ref[j]) {
			return r
		}
	}
	for i, n := range p.nodes {
		switch n.op {
		case opConstant:
			if !isFinite(n.value) || len(n.inputs) != 0 {
				return r
			}
		case opArtifactStat:
			if n.coordinate < 0 || n.coordinate >= len(center) || len(n.inputs) != 0 {
				return r
			}
		case opAdd, opMultiply:
		case opMin, opMax:
			if len(n.inputs) == 0 {
				return r
			}
		case opPower:
			if len(n.inputs) != 2 {
				return r
			}
		case opSelectLT:
			if len(n.inputs) != 4 {
				return r
			}
		default:
			return r
		}
		for _, id := range n.inputs {
			if int(id) >= i {
				return r
			}
		}
	}
	b := artifactBound{d: len(center), cache: map[boundVector][2]float64{}}
	copy(b.mean[:], center)
	invalidSupport := false
	b.research = func(w boundVector) (float64, float64) {
		if v, ok := b.cache[w]; ok {
			return v[0], v[1]
		}
		r.SupportCalls++
		q := append([]float64(nil), w[:b.d]...)
		lo, hi := support(q)
		if !isFinite(lo) || !isFinite(hi) || lo > hi {
			invalidSupport = true
			return math.Inf(-1), math.Inf(1)
		}
		offset, magnitude := 0.0, math.Abs(lo)+math.Abs(hi)
		for j := 0; j < b.d; j++ {
			term := w[j] * center[j]
			offset += term
			magnitude += math.Abs(term)
		}
		guard := 2e-12 * (1 + magnitude)
		lo, hi = down(lo-offset-guard), up(hi-offset+guard)
		if !isFinite(lo) || !isFinite(hi) || lo > hi {
			invalidSupport = true
			return math.Inf(-1), math.Inf(1)
		}
		b.cache[w] = [2]float64{lo, hi}
		return lo, hi
	}
	if caps || rationals {
		t := targetContext{b: &b, forms: make([]targetLinear, len(p.nodes))}
		b.researchNode = func(i int, n compiledNode, old affineValue, values []affineValue) {
			t.forms[i] = t.sourceForm(n, center, ref)
			if caps && (n.op == opMin || n.op == opMax) {
				if v, ok := t.cap(n, old); ok {
					values[i] = v
					r.Caps++
				}
			}
			if rationals && n.op == opMultiply {
				if v, ok := t.rational(n, p.nodes, old); ok {
					values[i] = v
					r.Rationals++
				}
			}
		}
	}
	r.ModelUpper, _ = p.boundUpper(&b, ref)
	if invalidSupport || !isFinite(r.ModelUpper) {
		r.ModelUpper = math.Inf(1)
	}
	if !p.unresolved {
		r.Upper = r.ModelUpper
	}
	return r
}
