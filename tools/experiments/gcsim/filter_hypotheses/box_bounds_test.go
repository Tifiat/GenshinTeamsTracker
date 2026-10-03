package formula

import (
	"math"
	"testing"
)

func hypothesisProgram(dimensions int) (*ArtifactProgram, func(uint8, float64, int, ...uint32) uint32) {
	p := &ArtifactProgram{coordinates: make([]string, dimensions)}
	add := func(op uint8, value float64, coordinate int, inputs ...uint32) uint32 {
		id := uint32(len(p.nodes))
		p.nodes = append(p.nodes, compiledNode{op: op, value: value, coordinate: coordinate, inputs: inputs})
		p.values = append(p.values, 0)
		p.root = id
		return id
	}
	return p, add
}

// Every sampled fixed-context result must lie inside the bound. Check each
// claimed sign against pairs of points that differ in only one coordinate.
func hypothesisCheckGrid(t *testing.T, p *ArtifactProgram, lo, hi []float64, wantInc, wantDec []bool) HypothesisBoxResult {
	t.Helper()
	r := p.HypothesisBoxBounds(lo, hi)
	if !r.Supported || len(r.Increasing) != len(lo) || len(r.Decreasing) != len(lo) {
		t.Fatalf("unsupported box or sign shape: %+v", r)
	}
	boundLo, boundHi, supported := p.HypothesisBoxRange(lo, hi)
	if !supported || boundLo != r.Lower || boundHi != r.Upper {
		t.Fatalf("bound-only and signed paths disagree: %+v, %g..%g, supported=%t", r, boundLo, boundHi, supported)
	}
	for i := range lo {
		if r.Increasing[i] != wantInc[i] || r.Decreasing[i] != wantDec[i] {
			t.Fatalf("coordinate %d signs: increasing=%t decreasing=%t, want %t/%t", i, r.Increasing[i], r.Decreasing[i], wantInc[i], wantDec[i])
		}
	}
	const steps = 6
	x := make([]float64, len(lo))
	var walk func(int)
	walk = func(dimension int) {
		if dimension == len(lo) {
			v, err := p.Evaluate(x)
			if err != nil || v < r.Lower || v > r.Upper {
				t.Fatalf("point %v escaped %g..%g: value=%g err=%v", x, r.Lower, r.Upper, v, err)
			}
			for j := range x {
				if !r.Increasing[j] && !r.Decreasing[j] {
					continue
				}
				old := x[j]
				x[j] = math.Min(hi[j], old+(hi[j]-lo[j])/steps)
				w, nextErr := p.Evaluate(x)
				x[j] = old
				if nextErr != nil {
					t.Fatal(nextErr)
				}
				tolerance := 1e-12 * (1 + math.Abs(v) + math.Abs(w))
				if r.Increasing[j] && w+tolerance < v || r.Decreasing[j] && w > v+tolerance {
					t.Fatalf("coordinate %d sign failed near %v: %g -> %g", j, x, v, w)
				}
			}
			return
		}
		for step := 0; step <= steps; step++ {
			x[dimension] = lo[dimension] + (hi[dimension]-lo[dimension])*float64(step)/steps
			walk(dimension + 1)
		}
	}
	walk(0)
	return r
}

func TestHypothesisBoxCritCapAndCrossOwnerSigns(t *testing.T) {
	p, n := hypothesisProgram(2)
	cr := n(opArtifactStat, 0, 0)
	cd := n(opArtifactStat, 0, 1)
	half := n(opConstant, .5, -1)
	one := n(opConstant, 1, -1)
	rate := n(opMin, 0, -1, one, n(opAdd, 0, -1, half, cr))
	damage := n(opAdd, 0, -1, one, cd)
	n(opMultiply, 0, -1, rate, damage)
	r := hypothesisCheckGrid(t, p, []float64{-.25, 0}, []float64{1, .8}, []bool{true, true}, []bool{false, false})
	if r.Upper < 1.8 || r.Lower > .3 {
		t.Fatalf("crit cap enclosure lost endpoints: %+v", r)
	}
	hypothesisCheckGrid(t, p, []float64{1, 0}, []float64{2, .8}, []bool{true, true}, []bool{true, false})
}

func TestHypothesisBoxNegativeProductsAndMixedOrder(t *testing.T) {
	p, n := hypothesisProgram(2)
	x := n(opArtifactStat, 0, 0)
	y := n(opArtifactStat, 0, 1)
	negative := n(opConstant, -2, -1)
	n(opMultiply, 0, -1, negative, x, y)
	hypothesisCheckGrid(t, p, []float64{1, 2}, []float64{3, 4}, []bool{false, false}, []bool{true, true})

	p, n = hypothesisProgram(2)
	x = n(opArtifactStat, 0, 0)
	y = n(opArtifactStat, 0, 1)
	negative = n(opConstant, -1, -1)
	minusY := n(opMultiply, 0, -1, negative, y)
	n(opAdd, 0, -1, x, minusY)
	hypothesisCheckGrid(t, p, []float64{-3, -2}, []float64{4, 5}, []bool{true, false}, []bool{false, true})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	negative = n(opConstant, -1, -1)
	minusX := n(opMultiply, 0, -1, negative, x)
	n(opMin, 0, -1, x, minusX)
	hypothesisCheckGrid(t, p, []float64{-2}, []float64{2}, []bool{false}, []bool{false})
}

func TestHypothesisBoxFixedAndUncertainSelect(t *testing.T) {
	p, n := hypothesisProgram(1)
	x := n(opArtifactStat, 0, 0)
	zero := n(opConstant, 0, -1)
	negative := n(opConstant, -1, -1)
	minusX := n(opMultiply, 0, -1, negative, x)
	n(opSelectLT, 0, -1, x, zero, x, minusX)
	hypothesisCheckGrid(t, p, []float64{-2}, []float64{-1}, []bool{true}, []bool{false})
	hypothesisCheckGrid(t, p, []float64{1}, []float64{2}, []bool{false}, []bool{true})
	r := hypothesisCheckGrid(t, p, []float64{-1}, []float64{1}, []bool{false}, []bool{false})
	if !isFinite(r.Lower) || !isFinite(r.Upper) || r.Lower > -1 || r.Upper < 1 {
		t.Fatalf("uncertain select lost a finite arm hull: %+v", r)
	}
}

func TestHypothesisBoxPowersAndClampedSqrt(t *testing.T) {
	for _, tc := range []struct {
		name       string
		exponent   float64
		lo, hi     float64
		increasing bool
		decreasing bool
	}{
		{"square positive", 2, 0, 3, true, false},
		{"square negative", 2, -3, -1, false, true},
		{"square crossing", 2, -2, 3, false, false},
		{"reciprocal positive", -1, 1, 3, false, true},
		{"reciprocal negative", -1, -3, -1, false, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p, n := hypothesisProgram(1)
			x := n(opArtifactStat, 0, 0)
			exponent := n(opConstant, tc.exponent, -1)
			n(opPower, 0, -1, x, exponent)
			r := hypothesisCheckGrid(t, p, []float64{tc.lo}, []float64{tc.hi}, []bool{tc.increasing}, []bool{tc.decreasing})
			if tc.name == "square crossing" && (r.Lower > 0 || r.Upper < 9) {
				t.Fatalf("even power lost interior zero or endpoint: %+v", r)
			}
		})
	}
	p, n := hypothesisProgram(1)
	x := n(opArtifactStat, 0, 0)
	zero := n(opConstant, 0, -1)
	half := n(opConstant, .5, -1)
	clamped := n(opMax, 0, -1, zero, x)
	n(opPower, 0, -1, clamped, half)
	hypothesisCheckGrid(t, p, []float64{-1}, []float64{4}, []bool{true}, []bool{false})
}

func TestHypothesisBoxFailsOpen(t *testing.T) {
	check := func(t *testing.T, p *ArtifactProgram, lo, hi []float64) {
		t.Helper()
		r := p.HypothesisBoxBounds(lo, hi)
		if r.Supported || !math.IsInf(r.Lower, -1) || !math.IsInf(r.Upper, 1) {
			t.Fatalf("unsupported box became prunable: %+v", r)
		}
		for i := range r.Increasing {
			if r.Increasing[i] || r.Decreasing[i] {
				t.Fatalf("unsupported box certified coordinate %d: %+v", i, r)
			}
		}
		lower, upper, ok := p.HypothesisBoxRange(lo, hi)
		if ok || !math.IsInf(lower, -1) || !math.IsInf(upper, 1) {
			t.Fatalf("bound-only route became prunable: %g..%g, %t", lower, upper, ok)
		}
	}
	p, n := hypothesisProgram(1)
	x := n(opArtifactStat, 0, 0)
	negative := n(opConstant, -1, -1)
	n(opPower, 0, -1, x, negative)
	check(t, p, []float64{-1}, []float64{1}) // reciprocal singularity
	p.unresolved = true
	check(t, p, []float64{1}, []float64{2})
	p.unresolved = false
	check(t, p, []float64{2}, []float64{1})
	check(t, p, []float64{math.NaN()}, []float64{1})
	check(t, p, nil, nil)
	check(t, p, []float64{1, 2}, []float64{2, 3})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	y := n(opArtifactStat, 0, 0)
	n(opPower, 0, -1, x, y) // coordinate-controlled exponent
	check(t, p, []float64{1}, []float64{2})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	half := n(opConstant, .5, -1)
	n(opPower, 0, -1, x, half)
	check(t, p, []float64{-1}, []float64{1}) // invalid real domain

	p, n = hypothesisProgram(1)
	n(opConstant, math.Inf(1), -1)
	check(t, p, []float64{0}, []float64{1})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	p.nodes[x].op = 255
	check(t, p, []float64{0}, []float64{1})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	p.nodes[x].coordinate = 3
	check(t, p, []float64{0}, []float64{1})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	n(opAdd, 0, -1, x, 5) // non-topological input
	check(t, p, []float64{0}, []float64{1})
}

func TestHypothesisModelBoxKeepsUnresolvedGuardAndScratch(t *testing.T) {
	p, n := hypothesisProgram(1)
	x := n(opArtifactStat, 0, 0)
	three := n(opConstant, 3, -1)
	two := n(opConstant, 2, -1)
	product := n(opMultiply, 0, -1, three, x)
	n(opAdd, 0, -1, product, two)
	p.unresolved = true
	for i := range p.values {
		p.values[i] = 777 + float64(i)
	}
	p.previous = []float64{91}
	p.previousValid = true

	lo, hi := []float64{1}, []float64{4}
	guarded := p.HypothesisBoxBounds(lo, hi)
	if guarded.Supported || !math.IsInf(guarded.Upper, 1) || guarded.Increasing[0] || guarded.Decreasing[0] {
		t.Fatalf("unresolved response acquired a hard bound: %+v", guarded)
	}
	if _, upper, ok := p.HypothesisBoxRange(lo, hi); ok || !math.IsInf(upper, 1) {
		t.Fatalf("guarded range acquired a hard upper: %g, %t", upper, ok)
	}
	model := p.HypothesisModelBoxBounds(lo, hi)
	lower, upper, ok := p.HypothesisModelBoxRange(lo, hi)
	if !ok || !model.Supported || lower != model.Lower || upper != model.Upper ||
		model.Lower > 5 || model.Upper < 14 || !model.Increasing[0] || model.Decreasing[0] {
		t.Fatalf("fixed compiled model lost its finite arithmetic enclosure/order: %+v, %g..%g, %t", model, lower, upper, ok)
	}
	if !p.unresolved || !p.previousValid || len(p.previous) != 1 || p.previous[0] != 91 {
		t.Fatal("model-only call changed original coverage or previous-input scratch")
	}
	for i, value := range p.values {
		if value != 777+float64(i) {
			t.Fatalf("model-only call changed evaluation scratch at %d: %g", i, value)
		}
	}
	for _, point := range []float64{1, 1.5, 2, 3, 4} {
		value, err := p.Evaluate([]float64{point})
		if err != nil || value < model.Lower || value > model.Upper {
			t.Fatalf("fixed model value escaped at %g: %g, %v", point, value, err)
		}
	}
	if p.HypothesisBoxBounds(lo, hi).Supported {
		t.Fatal("model-only call cleared unresolved coverage")
	}
}

func TestHypothesisModelBoxStillFailsOpenOnUnknownArithmetic(t *testing.T) {
	check := func(t *testing.T, p *ArtifactProgram, lo, hi []float64) {
		t.Helper()
		p.unresolved = true
		r := p.HypothesisModelBoxBounds(lo, hi)
		lower, upper, ok := p.HypothesisModelBoxRange(lo, hi)
		if r.Supported || ok || !math.IsInf(r.Lower, -1) || !math.IsInf(r.Upper, 1) ||
			!math.IsInf(lower, -1) || !math.IsInf(upper, 1) || r.Increasing[0] || r.Decreasing[0] || !p.unresolved {
			t.Fatalf("unknown model arithmetic became certified: %+v, %g..%g, %t", r, lower, upper, ok)
		}
	}
	p, n := hypothesisProgram(1)
	x := n(opArtifactStat, 0, 0)
	p.nodes[x].op = 255
	check(t, p, []float64{1}, []float64{2})

	p, n = hypothesisProgram(1)
	x = n(opArtifactStat, 0, 0)
	negative := n(opConstant, -1, -1)
	n(opPower, 0, -1, x, negative)
	check(t, p, []float64{-1}, []float64{1})
}
