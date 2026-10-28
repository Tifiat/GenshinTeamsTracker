package formula

import (
	"math"
	"testing"
)

func checkResearchPlanesPoints(t *testing.T, p *ArtifactProgram, points [][]float64, center, ref []float64) ResearchEnvelopeResult {
	t.Helper()
	r := p.ResearchPlanes(center, ref, researchFiniteSupport(points))
	if !isFinite(r.ModelUpper) || !isFinite(r.Upper) || r.SupportCalls == 0 {
		t.Fatal("expected a finite supported enclosure", r)
	}
	for _, point := range points {
		delta := make([]float64, len(ref))
		for j := range delta {
			delta[j] = point[j] - ref[j]
		}
		value, err := p.Evaluate(delta)
		if err != nil || value > r.ModelUpper+1e-8 {
			t.Fatalf("point %v: value %g exceeds %g, err %v", point, value, r.ModelUpper, err)
		}
	}
	return r
}

func TestResearchPlanesExhaustiveSignedCapsAndJump(t *testing.T) {
	p, n := testProgram(2)
	x, y := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1)
	one := n(opConstant, 1, -1)
	minusTwo := n(opConstant, -2, -1)
	xy := n(opMultiply, 0, -1, x, y)
	minusX := n(opMultiply, 0, -1, x, minusTwo)
	cap := n(opMin, 0, -1, y, one)
	floor := n(opMax, 0, -1, x, minusTwo)
	left := n(opAdd, 0, -1, xy, minusX, cap, floor)
	right := n(opConstant, 19, -1)
	n(opSelectLT, 0, -1, x, one, left, right)
	points := make([][]float64, 0, 13*13)
	for i := -4; i <= 8; i++ {
		for j := -4; j <= 8; j++ {
			points = append(points, []float64{float64(i) / 4, float64(j) / 4})
		}
	}
	checkResearchPlanesPoints(t, p, points, []float64{.5, .5}, []float64{0, 0})
}

func TestResearchPlanesRetainsTiedSharedCoordinate(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	one := n(opConstant, 1, -1)
	minusOne := n(opConstant, -1, -1)
	minusX := n(opMultiply, 0, -1, minusOne, x)
	oneMinusX := n(opAdd, 0, -1, one, minusX)
	n(opMultiply, 0, -1, x, oneMinusX)
	points := [][]float64{{0}, {.25}, {.5}, {.75}, {1}}
	r := checkResearchPlanesPoints(t, p, points, []float64{.5}, []float64{0})
	if r.ModelUpper > .501 {
		t.Fatal("McCormick upper planes lost the shared-coordinate tie", r)
	}
}

func TestResearchPlanesExhaustiveRepeatedSignedProduct(t *testing.T) {
	p, n := testProgram(2)
	x, y := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1)
	negative := n(opConstant, -1.5, -1)
	n(opMultiply, 0, -1, negative, x, x, y)
	points := make([][]float64, 0, 81)
	for i := -4; i <= 4; i++ {
		for j := -4; j <= 4; j++ {
			points = append(points, []float64{float64(i) / 2, float64(j) / 2})
		}
	}
	checkResearchPlanesPoints(t, p, points, []float64{0, 0}, []float64{0, 0})
}

func TestResearchPlanesSignedCapSecants(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	cap := n(opConstant, .5, -1)
	minus := n(opConstant, -1, -1)
	below := n(opMin, 0, -1, x, cap)
	above := n(opMax, 0, -1, x, cap)
	negativeBelow := n(opMultiply, 0, -1, minus, below)
	n(opAdd, 0, -1, negativeBelow, above)
	points := make([][]float64, 0, 17)
	for i := -8; i <= 8; i++ {
		points = append(points, []float64{float64(i) / 4})
	}
	checkResearchPlanesPoints(t, p, points, []float64{0}, []float64{0})
}

func TestResearchPlanesJointSupportBeyondOldDimensionLimit(t *testing.T) {
	p, n := testProgram(48)
	x, y := n(opArtifactStat, 0, 3), n(opArtifactStat, 0, 44)
	n(opAdd, 0, -1, x, y)
	points := make([][]float64, 2)
	for j := range points {
		points[j] = make([]float64, 48)
	}
	points[0][3], points[1][44] = 3, 3
	center, ref := make([]float64, 48), make([]float64, 48)
	center[3], center[44], ref[3], ref[44] = 1.5, 1.5, 1, 1
	r := checkResearchPlanesPoints(t, p, points, center, ref)
	if r.ModelUpper < 1 || r.ModelUpper > 1.001 || r.Dimensions != 48 {
		t.Fatal("joint support or reference shift lost", r)
	}
}

func TestResearchPlanesFailsClosed(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	e := n(opConstant, -1, -1)
	n(opPower, 0, -1, x, e)
	support := researchFiniteSupport([][]float64{{-1}, {1}})
	checkInf := func(name string, r ResearchEnvelopeResult) {
		t.Helper()
		if !math.IsInf(r.Upper, 1) || !math.IsInf(r.ModelUpper, 1) {
			t.Fatal(name, r)
		}
	}
	checkInf("singular", p.ResearchPlanes([]float64{0}, []float64{0}, support))
	checkInf("missing center", p.ResearchPlanes(nil, []float64{0}, support))
	checkInf("missing reference", p.ResearchPlanes([]float64{0}, nil, support))
	checkInf("missing support", p.ResearchPlanes([]float64{0}, []float64{0}, nil))
	checkInf("invalid support", p.ResearchPlanes([]float64{0}, []float64{0}, func([]float64) (float64, float64) { return math.NaN(), 1 }))
	large, _ := testProgram(129)
	checkInf("oversized", large.ResearchPlanes(make([]float64, 129), make([]float64, 129), support))
	unknown, add := testProgram(1)
	add(255, 0, -1)
	checkInf("unknown op", unknown.ResearchPlanes([]float64{0}, []float64{0}, support))

	q, node := testProgram(1)
	stat := node(opArtifactStat, 0, 0)
	node(opAdd, 0, -1, stat)
	baseline := q.ResearchPlanes([]float64{0}, []float64{0}, support)
	if !isFinite(baseline.ModelUpper) {
		t.Fatal(baseline)
	}
	q.unresolved = true
	unresolved := q.ResearchPlanes([]float64{0}, []float64{0}, support)
	if !math.IsInf(unresolved.Upper, 1) || !isFinite(unresolved.ModelUpper) || unresolved.ModelUpper != baseline.ModelUpper {
		t.Fatal("unresolved model bound must not authorize pruning", unresolved, baseline)
	}
}

func TestResearchPlanesFiniteInputsOverflowExtremeFailsClosed(t *testing.T) {
	large := .75 * math.MaxFloat64
	support := researchFiniteSupport([][]float64{{0}, {large}})
	b := researchPlanes{
		d:        1,
		center:   []float64{0},
		callback: support,
		cache:    map[[researchPlaneDimensions]float64][2]float64{},
	}
	candidate := researchPlane{c: large}
	candidate.w[0] = 1
	chosen := b.choose([]researchPlane{candidate, candidate}, true)
	if !b.failed || !math.IsNaN(chosen.c) {
		t.Fatal("overflowed candidates must not select an apparent zero plane", chosen, b.failed)
	}

	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	c := n(opConstant, large, -1)
	n(opAdd, 0, -1, x, c)
	r := p.ResearchPlanes([]float64{0}, []float64{0}, support)
	if !math.IsInf(r.ModelUpper, 1) || !math.IsInf(r.Upper, 1) {
		t.Fatal("finite inputs whose result exceeds float64 must fail closed", r)
	}
}
