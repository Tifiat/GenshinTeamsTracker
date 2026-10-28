package formula

import (
	"encoding/json"
	"fmt"
	"math"
	"testing"
)

func TestResearchDAGRoundtripAndRejectedTopology(t *testing.T) {
	p, n := testProgram(40)
	for i := range p.coordinates {
		p.coordinates[i] = fmt.Sprintf("x%d", i)
	}
	x := n(opArtifactStat, 0, 37)
	one := n(opConstant, 1, -1)
	x1 := n(opAdd, 0, -1, x, one)
	n(opMultiply, 0, -1, x, x1)
	d := p.ResearchExport()
	raw, err := json.Marshal(d)
	if err != nil {
		t.Fatal(err)
	}
	var decoded ResearchDAG
	if err = json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	q, err := ResearchRestore(decoded)
	if err != nil {
		t.Fatal(err)
	}
	if !q.unresolved {
		t.Fatal("restored fixture acquired source certification")
	}
	for i := -8; i <= 8; i++ {
		point := make([]float64, 40)
		point[37] = float64(i) / 4
		v, e := p.Evaluate(point)
		z, f := q.Evaluate(point)
		if e != nil || f != nil || v != z {
			t.Fatal(v, z, e, f)
		}
	}
	d.Nodes[len(d.Nodes)-1].Inputs = []uint32{uint32(len(d.Nodes))}
	if _, err = ResearchRestore(d); err == nil {
		t.Fatal("future edge accepted")
	}
}

func TestResearchDiagnosisMatchesBaselineAndWitness(t *testing.T) {
	p, n := testProgram(2)
	x := n(opArtifactStat, 0, 0)
	y := n(opArtifactStat, 0, 1)
	xy := n(opMultiply, 0, -1, x, y)
	one := n(opConstant, 1, -1)
	cap := n(opMin, 0, -1, x, one)
	n(opAdd, 0, -1, xy, cap)
	points := [][]float64{{0, 2}, {1, 1}, {2, 0}}
	support := researchFiniteSupport(points)
	center, ref := []float64{1, 1}, []float64{.2, .3}
	d, err := p.ResearchDiagnose(center, ref, points[1], support)
	if err != nil {
		t.Fatal(err)
	}
	b := p.ResearchEnvelope(center, ref, support, false)
	if math.Abs(d.ModelUpper-b.ModelUpper) > 1e-8 || len(d.Top) == 0 || d.Witness > d.ModelUpper {
		t.Fatal(d, b)
	}
	if _, err = json.Marshal(d); err != nil {
		t.Fatal(err)
	}
}
