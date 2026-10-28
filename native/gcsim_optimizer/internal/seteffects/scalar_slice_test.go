package seteffects

import (
	"math"
	"strings"
	"testing"
)

const scalarWitness = `package fixture
func damage() {
 input := read()
 factor := 1 - input/2
 if input >= 0 && input < 0.75 {
  factor = 1-input
 } else if input >= 0.75 {
  factor = 1/(4*input+1)
 }
 trace := observer()
 trace.Resistance = input
 trace.ResMod = factor
}`

func TestScalarSourceCurve(t *testing.T) {
	slices, e := ExtractScalarSlices([]byte(scalarWitness), "Resistance", "ResMod")
	if e != nil || len(slices) != 1 {
		t.Fatal(slices, e)
	}
	for _, p := range [][2]float64{{-0.25, 1.125}, {0, 1}, {0.1, 0.9}, {0.75, 0.25}, {1, 0.2}} {
		got, e := slices[0].Evaluate(p[0])
		if e != nil || math.Abs(got-p[1]) > 1e-14 {
			t.Fatal(p, got, e)
		}
	}
	renamed := strings.NewReplacer("input", "other", "factor", "result").Replace(scalarWitness)
	other, e := ExtractScalarSlices([]byte(renamed), "Resistance", "ResMod")
	if e != nil || other[0].RecipeSHA256 != slices[0].RecipeSHA256 {
		t.Fatal("rename changed arithmetic", e)
	}
	changed := strings.Replace(scalarWitness, "4*input+1", "7*input+2", 1)
	next, e := ExtractScalarSlices([]byte(changed), "Resistance", "ResMod")
	if e != nil {
		t.Fatal(e)
	}
	got, e := next[0].Evaluate(1)
	if e != nil || got != 1.0/9 {
		t.Fatal("coefficient not source-owned", got, e)
	}
}

func TestScalarConstantGoSemantics(t *testing.T) {
	for _, p := range []struct {
		expr string
		want float64
	}{{"input + (1/2)", 2}, {"input+(2.0/2)/2", 2.5}, {"input+(-1/2)", 2}, {"input+(1.0/3)*3", 3}} {
		src := `package fixture;func f(){ input:=read(); factor:=` + p.expr + `; trace:=observer(); trace.Resistance=input;trace.ResMod=factor }`
		ss, e := ExtractScalarSlices([]byte(src), "Resistance", "ResMod")
		if e != nil {
			t.Fatal(p, e)
		}
		got, e := ss[0].Evaluate(2)
		if e != nil || got != p.want {
			t.Fatal(p, got, e)
		}
	}
}

func TestScalarUnknownBoundaries(t *testing.T) {
	for _, src := range []string{
		strings.Replace(scalarWitness, "factor = 1-input", "factor = secret(input)", 1),
		strings.Replace(scalarWitness, "trace := observer()", "input = 0;trace := observer()", 1),
		strings.Replace(scalarWitness, "trace := observer()", "escape(&factor);trace := observer()", 1),
		strings.Replace(scalarWitness, "factor = 1-input", "for i:=0;i<2;i++ {factor=1-input}", 1),
		strings.Replace(scalarWitness, "factor := 1 - input/2", "factor := 1/2", 1),
		strings.Replace(scalarWitness, "trace.ResMod = factor", "trace.ResMod=factor;factor=input", 1),
	} {
		if _, e := ExtractScalarSlices([]byte(src), "Resistance", "ResMod"); e == nil {
			t.Fatal("accepted unknown source", src)
		}
	}
}
