package formula

import (
	"math"
	"math/rand"
	"reflect"
	"testing"
)

func TestHypothesisLazyConstantsMatchEager(t *testing.T) {
	_, a := parametricMember(t, 1000)
	_, b := parametricMember(t, 2000)
	p, err := PrepareParametricWithReads([]*CompiledMember{a, b},
		[]EffectPort{{0, 1, "a", 20}, {0, 8, "latent", 0}, {1, 4, "b", 20}}, []ReadRoot{{0, 8, "read", 0}})
	if err != nil {
		t.Fatal(err)
	}
	rng := rand.New(rand.NewSource(87))
	cache := NewSpecializationCache(64, 128000)
	for n := 0; n < 100; n++ {
		values := []float64{rng.Float64()*40 - 20, rng.Float64()*20 - 10, rng.Float64()*10 - 5}
		patterns := [][]float64{{0, 0, 0}, {2, 2, 2}, {3, 3, 3}, {2, 0, 2}, {7, 0, 7}, {math.Copysign(0, -1), 0, 0}, {0, 2, 2}, {2, 3, 2}}
		if n < len(patterns)*2 {
			values = patterns[n%len(patterns)]
		}
		lazy, err := p.BindConstantEffectsHypothesis(values)
		if err != nil {
			t.Fatal(err)
		}
		eager, err := p.BindConstantEffects(values)
		if err != nil {
			t.Fatal(err)
		}
		lazy = lazy.WithSpecializationCache(cache)
		for j := 0; j < 5; j++ {
			x := []float64{rng.Float64()*40 - 20, rng.Float64()*40 - 20}
			lv, le := lazy.Evaluate(x, nil)
			ev, ee := eager.Evaluate(x, nil)
			if le != nil || ee != nil || lv != ev {
				t.Fatal(lv, ev, le, ee)
			}
			for _, actors := range [][]int{{0}, {1}, {0, 1}, {}} {
				l, le := lazy.Specialize(x, nil, actors...)
				e, ee := eager.Specialize(x, nil, actors...)
				if le != nil || ee != nil {
					t.Fatal(le, ee)
				}
				point := []float64{}
				for _, coordinate := range l.Coordinates() {
					if coordinate == "provider.em" {
						point = append(point, x[0])
					} else {
						point = append(point, x[1])
					}
				}
				lv, lg, _, le := l.ValueGradient(point)
				ev, eg, _, ee := e.ValueGradient(point)
				if le != nil || ee != nil || lv != ev || !reflect.DeepEqual(lg, eg) {
					t.Fatal(lv, ev, lg, eg, le, ee)
				}
			}
		}
	}
	for _, bad := range [][]float64{nil, {0}, {0, math.NaN(), 0}, {0, 0, math.Inf(1)}} {
		if _, err := p.BindConstantEffectsHypothesis(bad); err == nil {
			t.Fatal("invalid constant accepted")
		}
	}
}
