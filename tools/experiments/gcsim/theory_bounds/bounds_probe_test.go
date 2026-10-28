package formula

import (
	"math"
	"testing"
)

func researchFiniteSupport(points [][]float64) func([]float64) (float64, float64) {
	return func(w []float64) (float64, float64) {
		lo, hi := math.Inf(1), math.Inf(-1)
		for _, p := range points {
			v := 0.0
			for i, x := range p {
				v += w[i] * x
			}
			lo, hi = math.Min(lo, v), math.Max(hi, v)
		}
		return lo, hi
	}
}

func TestResearchEnvelopeExhaustiveSignedCapsAndJump(t *testing.T) {
	p, n := testProgram(2)
	x, y := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1)
	one := n(opConstant, 1, -1)
	minus := n(opConstant, -2, -1)
	xy := n(opMultiply, 0, -1, x, y)
	xneg := n(opMultiply, 0, -1, x, minus)
	cap := n(opMin, 0, -1, y, one)
	low := n(opAdd, 0, -1, xy, xneg, cap)
	high := n(opConstant, 19, -1)
	n(opSelectLT, 0, -1, x, one, low, high)
	points := [][]float64{}
	for i := -4; i <= 8; i++ {
		for j := -4; j <= 8; j++ {
			points = append(points, []float64{float64(i) / 4, float64(j) / 4})
		}
	}
	for _, natural := range []bool{true, false} {
		r := p.ResearchEnvelope([]float64{.5, .5}, []float64{0, 0}, researchFiniteSupport(points), natural)
		if math.IsInf(r.Upper, 1) {
			t.Fatal("unexpected unbounded", natural)
		}
		for _, point := range points {
			v, e := p.Evaluate(point)
			if e != nil || v > r.Upper+1e-8 {
				t.Fatal(natural, point, v, r, e)
			}
		}
		p.unresolved = true
		u := p.ResearchEnvelope([]float64{.5, .5}, []float64{0, 0}, researchFiniteSupport(points), natural)
		if !math.IsInf(u.Upper, 1) || u.ModelUpper != r.ModelUpper {
			t.Fatal("unresolved must remain unprunable", u, r)
		}
		p.unresolved = false
	}
}

func TestResearchEnvelopeRetainsJointSupportAndReference(t *testing.T) {
	p, n := testProgram(40)
	x := n(opArtifactStat, 0, 3)
	y := n(opArtifactStat, 0, 37)
	n(opAdd, 0, -1, x, y)
	points := make([][]float64, 2)
	for i := range points {
		points[i] = make([]float64, 40)
	}
	points[0][3], points[1][37] = 3, 3
	center, ref := make([]float64, 40), make([]float64, 40)
	center[3], center[37], ref[3], ref[37] = 1.5, 1.5, 1, 1
	a := p.ResearchEnvelope(center, ref, researchFiniteSupport(points), false)
	z := p.ResearchEnvelope(center, ref, researchFiniteSupport(points), true)
	if a.Upper < 1 || a.Upper > 1.000001 || z.Upper < 4 || z.Upper > 4.000001 {
		t.Fatal(a, z)
	}
}

func TestResearchEnvelopeSingularityNeverPrunes(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	e := n(opConstant, -1, -1)
	n(opPower, 0, -1, x, e)
	for _, natural := range []bool{true, false} {
		r := p.ResearchEnvelope([]float64{0}, []float64{0}, researchFiniteSupport([][]float64{{-1}, {1}}), natural)
		if !math.IsInf(r.Upper, 1) {
			t.Fatal(r)
		}
	}
}
