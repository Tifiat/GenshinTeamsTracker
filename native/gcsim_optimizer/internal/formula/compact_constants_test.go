package formula

import (
	"math"
	"reflect"
	"testing"
)

func TestCompactConstantsPreserveGeneralGraphAndGradient(t *testing.T) {
	_, member := parametricMember(t, 1000)
	p, err := PrepareParametricWithReads([]*CompiledMember{member},
		[]EffectPort{{0, 1, "bonus", 20}, {0, 8, "latent", 0}},
		[]ReadRoot{{0, 8, "saved", 0}})
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []float64{0, math.Copysign(0, -1), -13.25, 100} {
		x := map[string]*InputExpression{"bonus": {Operation: "constant", Value: value},
			"latent": {Operation: "constant", Value: 17}}
		values := make([]float64, len(p.EffectKeys()))
		for i, key := range p.EffectKeys() {
			values[i] = x[key].Value
		}
		fast, err := p.BindConstantEffects(values)
		want, slowErr := p.bindEffectExpressionsGeneral(x)
		if err != nil || slowErr != nil {
			t.Fatal(err, slowErr)
		}
		if !reflect.DeepEqual(fast.program.nodes, want.program.nodes) || fast.program.root != want.program.root {
			t.Fatal("dense binding changed the reduced graph")
		}
		for _, point := range [][]float64{{0, 0}, {3, 7}, {-2, 19}} {
			a, ga, _, e := fast.program.ValueGradient(point)
			b, gb, _, se := want.program.ValueGradient(point)
			if e != nil || se != nil || a != b || !reflect.DeepEqual(ga, gb) {
				t.Fatal(a, b, ga, gb, e, se)
			}
		}
	}
	for _, bad := range [][]float64{nil, {0}, {0, 0, 0}, {0, math.NaN()}, {math.Inf(1), 0}, {0, math.Inf(-1)}} {
		if _, err := p.BindConstantEffects(bad); err == nil {
			t.Fatal("invalid vector accepted", bad)
		}
	}
}
