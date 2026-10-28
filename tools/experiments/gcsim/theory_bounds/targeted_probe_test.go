package formula

import (
	"math"
	"testing"
)

func checkTargetedPoints(t *testing.T, p *ArtifactProgram, points [][]float64, center, ref []float64, caps, rationals bool) ResearchTargetedResult {
	t.Helper()
	r := p.ResearchTargeted(center, ref, researchFiniteSupport(points), caps, rationals)
	if !isFinite(r.ModelUpper) || !isFinite(r.Upper) {
		t.Fatal("expected finite targeted enclosure", r)
	}
	for _, point := range points {
		delta := make([]float64, len(ref))
		for j := range delta {
			delta[j] = point[j] - ref[j]
		}
		v, err := p.Evaluate(delta)
		if err != nil || v > r.ModelUpper+1e-8 {
			t.Fatalf("point %v: value %g exceeds %g, err %v", point, v, r.ModelUpper, err)
		}
	}
	return r
}

func TestResearchTargetedSignedProportionalRatioAndReference(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	negative := n(opConstant, -2.78, -1)
	five := n(opConstant, 5, -1)
	minusOne := n(opConstant, -1, -1)
	numerator := n(opMultiply, 0, -1, negative, x)
	denominator := n(opAdd, 0, -1, x, five)
	reciprocal := n(opPower, 0, -1, denominator, minusOne)
	n(opMultiply, 0, -1, numerator, reciprocal)
	points := [][]float64{{-1}, {-.5}, {0}, {.5}, {1}, {2}}
	r := checkTargetedPoints(t, p, points, []float64{.5}, []float64{.5}, false, true)
	if r.Rationals != 1 || r.Caps != 0 {
		t.Fatal("expected one source-derived rational block", r)
	}
}

func TestResearchTargetedCapsAndNestedDominance(t *testing.T) {
	points := [][]float64{{-2}, {-1}, {0}, {.25}, {.5}, {1}, {2}}
	for _, op := range []uint8{opMin, opMax} {
		p, n := testProgram(1)
		x := n(opArtifactStat, 0, 0)
		cap := n(opConstant, .25, -1)
		n(op, 0, -1, x, cap)
		r := checkTargetedPoints(t, p, points, []float64{0}, []float64{0}, true, false)
		if r.Caps != 1 {
			t.Fatal("expected ambiguous constant cap", op, r)
		}
	}
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	farCap := n(opConstant, 10, -1)
	inner := n(opMin, 0, -1, x, farCap)
	nearCap := n(opConstant, .25, -1)
	n(opMin, 0, -1, inner, nearCap)
	r := checkTargetedPoints(t, p, points, []float64{0}, []float64{0}, true, false)
	if r.Caps != 1 {
		t.Fatal("dominated inner cap should remain source-linear", r)
	}

	q, add := testProgram(1)
	y := add(opArtifactStat, 0, 0)
	firstCap := add(opConstant, .25, -1)
	first := add(opMin, 0, -1, y, firstCap)
	secondCap := add(opConstant, -1, -1)
	add(opMax, 0, -1, first, secondCap)
	r = checkTargetedPoints(t, q, points, []float64{0}, []float64{0}, true, false)
	if r.Caps != 1 {
		t.Fatal("ambiguous nested cap must use the safe baseline at its outer node", r)
	}
}

func TestResearchTargetedResidualAndCrossingFallback(t *testing.T) {
	p, n := testProgram(2)
	x, y := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1)
	one := n(opConstant, 1, -1)
	minusOne := n(opConstant, -1, -1)
	numerator := n(opAdd, 0, -1, x, y)
	denominator := n(opAdd, 0, -1, x, one)
	reciprocal := n(opPower, 0, -1, denominator, minusOne)
	n(opMultiply, 0, -1, numerator, reciprocal)
	points := [][]float64{{0, -1}, {0, 1}, {1, -1}, {1, 1}}
	r := checkTargetedPoints(t, p, points, []float64{.5, 0}, []float64{0, 0}, false, true)
	if r.Rationals != 0 {
		t.Fatal("nonproportional residual must keep the baseline", r)
	}

	q, add := testProgram(1)
	z := add(opArtifactStat, 0, 0)
	shift := add(opConstant, 1, -1)
	e := add(opConstant, -1, -1)
	b := add(opAdd, 0, -1, z, shift)
	inv := add(opPower, 0, -1, b, e)
	add(opMultiply, 0, -1, z, inv)
	crossing := q.ResearchTargeted([]float64{0}, []float64{0}, researchFiniteSupport([][]float64{{-2}, {2}}), false, true)
	if !math.IsInf(crossing.ModelUpper, 1) || !math.IsInf(crossing.Upper, 1) || crossing.Rationals != 0 {
		t.Fatal("denominator crossing zero must fail closed", crossing)
	}
}

func TestResearchTargetedSmallResidualRetainedAndUnresolved(t *testing.T) {
	for _, sign := range []float64{-1, 1} {
		p, n := testProgram(2)
		x, y := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1)
		k, epsilon := n(opConstant, 2*sign, -1), n(opConstant, 1e-6, -1)
		five, minusOne := n(opConstant, 5, -1), n(opConstant, -1, -1)
		xTerm := n(opMultiply, 0, -1, x, k)
		yTerm := n(opMultiply, 0, -1, y, epsilon)
		a := n(opAdd, 0, -1, xTerm, yTerm)
		b := n(opAdd, 0, -1, x, five)
		inv := n(opPower, 0, -1, b, minusOne)
		n(opMultiply, 0, -1, a, inv)
		var points [][]float64
		for xi := -8; xi <= 8; xi++ {
			for yi := -8; yi <= 8; yi++ {
				points = append(points, []float64{float64(xi) / 4, float64(yi) / 4})
			}
		}
		center, ref := []float64{0, 0}, []float64{.5, -.5}
		r := checkTargetedPoints(t, p, points, center, ref, false, true)
		if r.Rationals != 1 {
			t.Fatal("small nonproportional residual should be enclosed", r)
		}
		p.unresolved = true
		r = p.ResearchTargeted(center, ref, researchFiniteSupport(points), false, true)
		if !isFinite(r.ModelUpper) || !math.IsInf(r.Upper, 1) {
			t.Fatal("targeted model bound must retain unresolved source", r)
		}
	}
}

func TestResearchTargetedMalformedAndOverflowFailClosed(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	big := n(opConstant, .75*math.MaxFloat64, -1)
	n(opAdd, 0, -1, x, big)
	support := researchFiniteSupport([][]float64{{0}, {.75 * math.MaxFloat64}})
	r := p.ResearchTargeted([]float64{0}, []float64{0}, support, true, true)
	if !math.IsInf(r.ModelUpper, 1) || !math.IsInf(r.Upper, 1) {
		t.Fatal("overflow must be unprunable", r)
	}
	malformed := p.ResearchTargeted(nil, []float64{0}, support, true, true)
	if !math.IsInf(malformed.ModelUpper, 1) || !math.IsInf(malformed.Upper, 1) {
		t.Fatal("malformed dimensions must be unprunable", malformed)
	}
	invalid := p.ResearchTargeted([]float64{0}, []float64{0}, func([]float64) (float64, float64) {
		return math.NaN(), 1
	}, true, true)
	if !math.IsInf(invalid.ModelUpper, 1) || !math.IsInf(invalid.Upper, 1) {
		t.Fatal("invalid support must be unprunable", invalid)
	}
}
