package formula

import (
	"math"
	"reflect"
	"testing"
)

func r4RegionFixture(t *testing.T) *ParametricProgram {
	t.Helper()
	_, a := parametricMember(t, 1000)
	_, b := parametricMember(t, 2000)
	p, err := PrepareParametricWithReads([]*CompiledMember{a, b}, []EffectPort{{0, 1, "a", 20}, {0, 8, "latent", 0}, {1, 4, "b", 20}}, []ReadRoot{{0, 8, "read", 0}})
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func r4RegionCompare(t *testing.T, got, want *ParametricProgram) {
	t.Helper()
	if !reflect.DeepEqual(got.program.nodes, want.program.nodes) || got.program.root != want.program.root {
		t.Fatal("ordered reduced graph differs")
	}
	for i, node := range got.program.nodes {
		if math.Float64bits(node.value) != math.Float64bits(want.program.nodes[i].value) {
			t.Fatal("IEEE literal changed")
		}
	}
	for _, delta := range [][]float64{{0, 0}, {2, 3}, {-1, 0}, {math.Copysign(0, -1), 4}} {
		value, g, s, err := got.program.ValueGradient(delta)
		wv, wg, ws, we := want.program.ValueGradient(delta)
		if err != nil || we != nil || math.Float64bits(value) != math.Float64bits(wv) || s != ws || len(g) != len(wg) {
			t.Fatal("region value/gradient outcome differs", err, we)
		}
		for i := range g {
			if math.Float64bits(g[i]) != math.Float64bits(wg[i]) {
				t.Fatal("gradient FP order changed")
			}
		}
	}
}

func TestR4RegionsDisjointChangesUnchangedAndFork(t *testing.T) {
	previous := r4DirtyRegions
	r4DirtyRegions = true
	defer func() { r4DirtyRegions = previous }()
	p, control := r4RegionFixture(t), r4RegionFixture(t)
	vectors := [][]float64{{1, 2, 3}, {1, 2, 3}, {4, 2, 3}, {4, 5, 3}, {4, 5, 6}, {0, 5, 6}, {math.Copysign(0, -1), 5, 6}, {1, 2, 3}, {1, 2, 3}}
	var kept, oracle *ParametricProgram
	for i, values := range vectors {
		before := p.regionStats.Visited
		got, e := p.BindConstantEffectsRegions(values)
		want, we := control.r4FrozenBindConstantEffectsRegions(values)
		if e != nil || we != nil {
			t.Fatal(e, we)
		}
		r4RegionCompare(t, got, want)
		if i == 1 && p.regionStats.Visited != before {
			t.Fatal("unchanged vector traversed clean damage nodes")
		}
		if i == 0 {
			kept, oracle = got, want
		}
	}
	r4RegionCompare(t, kept, oracle)
	if p.regionStats.Rebuilt != control.regionStats.Rebuilt || p.regionStats.Reused != control.regionStats.Reused || p.regionStats.Visited >= control.regionStats.Visited {
		t.Fatal("dirty accounting/rebuild parity failed")
	}
	fork := p.ForkTheory()
	if fork.regions.r4Dirty != nil {
		t.Fatal("fork shared mutable frontier")
	}
	saved := append([]uint32(nil), p.regions.mapped...)
	oldValues := append([]float64(nil), p.regions.values...)
	got, e := fork.BindConstantEffectsRegions([]float64{9, 8, 7})
	want, we := control.r4FrozenBindConstantEffectsRegions([]float64{9, 8, 7})
	if e != nil || we != nil {
		t.Fatal(e, we)
	}
	r4RegionCompare(t, got, want)
	if !reflect.DeepEqual(saved, p.regions.mapped) || !reflect.DeepEqual(oldValues, p.regions.values) {
		t.Fatal("fork mutated parent's binder")
	}
	p.regions.r4Dirty.generation = math.MaxUint32
	got, e = p.BindConstantEffectsRegions([]float64{9, 8, 7})
	if e != nil {
		t.Fatal(e)
	}
	r4RegionCompare(t, got, want)
	p.regions.nodeLimit = 1
	got, e = p.BindConstantEffectsRegions([]float64{101, 102, 103})
	want, we = control.BindConstantEffects([]float64{101, 102, 103})
	if e != nil || we != nil || p.regions != nil || p.regionStats.Resets == 0 {
		t.Fatal("bounded reset lost", e, we)
	}
	r4RegionCompare(t, got, want)
}

func TestR4RegionsErrorInvalidatesAndRecovers(t *testing.T) {
	previous := r4DirtyRegions
	r4DirtyRegions = true
	defer func() { r4DirtyRegions = previous }()
	b := newProgramBuilder([]string{"effect:x"})
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	half, _ := b.add(compiledNode{op: opConstant, value: .5})
	root, _ := b.add(compiledNode{op: opPower, inputs: []uint32{x, half}})
	p := &ParametricProgram{program: b.finish(root), effects: []string{"x"}, input: make([]float64, 1)}
	if _, e := p.BindConstantEffectsRegions([]float64{1}); e != nil {
		t.Fatal(e)
	}
	for _, bad := range [][]float64{nil, {math.NaN()}, {math.Inf(1)}} {
		if _, e := p.BindConstantEffectsRegions(bad); e == nil {
			t.Fatal("invalid vector accepted")
		}
	}
	if _, e := p.BindConstantEffectsRegions([]float64{-1}); e == nil || p.regions != nil {
		t.Fatal("failed partial bind retained arena/frontier")
	}
	got, e := p.BindConstantEffectsRegions([]float64{4})
	if e != nil {
		t.Fatal(e)
	}
	value, e := got.Evaluate(nil, nil)
	if e != nil || value != 2 {
		t.Fatal("failed frontier poisoned next bind", value, e)
	}
}
