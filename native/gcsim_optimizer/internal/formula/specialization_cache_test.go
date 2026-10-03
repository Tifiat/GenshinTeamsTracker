package formula

// Synthetic exact-reuse controls; no gameplay constants or response claims.
import (
	"math"
	"reflect"
	"testing"
)

func TestParametricSpecializationCacheIdentityAndScratch(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}})
	if err != nil {
		t.Fatal(err)
	}
	cache := NewSpecializationCache(8, 1000)
	v := p.WithSpecializationCache(cache)
	a, err := v.Specialize([]float64{1, 7}, []float64{2}, 0)
	if err != nil {
		t.Fatal(err)
	}
	b, err := v.WithOwnScratch().Specialize([]float64{19, 7}, []float64{2}, 0)
	if err != nil || cache.Stats().Hits != 1 {
		t.Fatal(cache.Stats(), err)
	}
	if &a.nodes[0] != &b.nodes[0] || &a.values[0] == &b.values[0] {
		t.Fatal("not immutable-node/private-scratch reuse")
	}
	for _, point := range []float64{0, 3, -20} {
		got, g, _, err := b.ValueGradient([]float64{point})
		oracle, e := p.Specialize([]float64{19, 7}, []float64{2}, 0)
		want, wg, _, oe := oracle.ValueGradient([]float64{point})
		if err != nil || e != nil || oe != nil || got != want || !reflect.DeepEqual(g, wg) {
			t.Fatal(got, want, g, wg, err, e, oe)
		}
	}
	// Fixed teammate stats, effect values, variable-owner masks and proof status
	// each change the identity. A different source must not share by point DPS.
	for _, test := range []struct {
		anchor, effect []float64
		actors         []int
	}{
		{[]float64{19, 8}, []float64{2}, []int{0}},
		{[]float64{19, 7}, []float64{3}, []int{0}},
		{[]float64{19, 7}, []float64{2}, []int{1}},
	} {
		before := cache.Stats().Misses
		if _, err = v.Specialize(test.anchor, test.effect, test.actors...); err != nil || cache.Stats().Misses != before+1 {
			t.Fatal(cache.Stats(), err)
		}
	}
	q, err := v.WithoutPruning().Specialize([]float64{19, 7}, []float64{2}, 0)
	if err != nil || !q.HasUnresolvedDependencies() || a.HasUnresolvedDependencies() {
		t.Fatal("proof status leaked", err)
	}
	other, _ := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}})
	before := cache.Stats().Misses
	if _, err = other.WithSpecializationCache(cache).Specialize([]float64{19, 7}, []float64{2}, 0); err != nil || cache.Stats().Misses != before+1 {
		t.Fatal("source identity ignored", err)
	}
	if _, err = v.Specialize([]float64{math.NaN(), 7}, []float64{2}, 0); err == nil {
		t.Fatal("cache bypassed input validation")
	}
}

func TestParametricSpecializationCacheBoundedEviction(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, _ := PrepareParametric([]*CompiledMember{c}, nil)
	cache := NewSpecializationCache(1, 1000)
	v := p.WithSpecializationCache(cache)
	for _, fixed := range []float64{0, 1, 0} {
		q, err := v.Specialize([]float64{0, fixed}, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		got, err := q.Evaluate([]float64{3})
		if err != nil || got != 23*(20+fixed) {
			t.Fatal(got, err)
		}
	}
	if stats := cache.Stats(); stats.Entries != 1 || stats.Misses != 3 || stats.Nodes > 1000 {
		t.Fatal(stats)
	}
	tiny := NewSpecializationCache(4, 1)
	if _, err := p.WithSpecializationCache(tiny).Specialize([]float64{0, 0}, nil, 0); err != nil || tiny.Stats().Entries != 0 {
		t.Fatal(tiny.Stats(), err)
	}
}
