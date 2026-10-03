package formula

import (
	"math"
	"reflect"
	"testing"
)

func TestHypothesisMixedInputsPreserveGraphAndGradient(t *testing.T) {
	_, member := parametricMember(t, 1000)
	p, err := PrepareParametricWithReads([]*CompiledMember{member}, []EffectPort{{0, 1, "a", 20}, {0, 4, "b", 20}}, []ReadRoot{{0, 8, "r", 0}})
	if err != nil { t.Fatal(err) }
	for k := 0; k < 12; k++ {
		values := []float64{float64(k), 0}
		for _, expression := range []*InputExpression{
			{Operation: "constant", Value: 3},
			{Operation: "artifact", Key: p.Coordinates()[0]},
			{Operation: "effect", Key: "a"},
			{Operation: "read", Key: "r"},
			{Operation: "add", Inputs: []*InputExpression{{Operation: "artifact", Key: p.Coordinates()[0]}, {Operation: "constant", Value: 2}}},
		} {
			sparse := map[int]*InputExpression{1: expression}
			effects := map[string]*InputExpression{"a": {Operation: "constant", Value: values[0]}, "b": expression}
			got, ge := p.BindMixedEffects(values, sparse)
			want, we := p.BindEffectExpressions(effects)
			if (ge == nil) != (we == nil) { t.Fatal("boundary differs", ge, we) }
			if ge != nil { continue }
			if got.program.root != want.program.root || !reflect.DeepEqual(got.program.nodes, want.program.nodes) { t.Fatal("mixed graph changed") }
			for _, x := range [][]float64{{0, 0}, {2, 7}, {-1, 3}, {24, -2}} {
				v, g, _, e := got.program.ValueGradient(x)
				wv, wg, _, we := want.program.ValueGradient(x)
				if e != nil || we != nil || math.Float64bits(v) != math.Float64bits(wv) || !reflect.DeepEqual(g, wg) { t.Fatal("mixed gradient changed", v, wv, g, wg, e, we) }
			}
		}
	}
	for _, sparse := range []map[int]*InputExpression{{-1: {Operation: "constant"}}, {2: {Operation: "constant"}}, {0: nil}} {
		if _, e := p.BindMixedEffects([]float64{0, 0}, sparse); e == nil { t.Fatal("invalid dimension accepted") }
	}
	if _, e := p.BindMixedEffects([]float64{math.NaN(), 0}, nil); e == nil { t.Fatal("invalid literal accepted") }
}
