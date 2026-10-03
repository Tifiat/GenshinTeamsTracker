package formula

import (
	"math"
	"math/rand"
	"reflect"
	"testing"
)

func TestRegionsPreserveGraphGradientAndIndependentOutputs(t *testing.T) {
	_, a := parametricMember(t, 1000)
	_, b := parametricMember(t, 2000)
	p, err := PrepareParametricWithReads([]*CompiledMember{a, b},
		[]EffectPort{{0, 1, "a", 20}, {0, 8, "latent", 0}, {1, 4, "b", 20}}, []ReadRoot{{0, 8, "read", 0}})
	if err != nil {
		t.Fatal(err)
	}
	rng := rand.New(rand.NewSource(5928))
	var retained, retainedOracle *ParametricProgram
	for step := 0; step < 120; step++ {
		values := []float64{float64(step % 5), float64(step % 7), float64(step % 3)}
		if step%10 == 0 {
			values[0] = math.Copysign(0, -1)
		}
		got, e := p.BindConstantEffectsRegions(values)
		want, we := p.BindConstantEffects(values)
		if e != nil || we != nil {
			t.Fatal(e, we)
		}
		if !reflect.DeepEqual(got.program.nodes, want.program.nodes) || got.program.root != want.program.root {
			t.Fatal("region binder changed reduced graph", step)
		}
		for i, n := range got.program.nodes {
			if math.Float64bits(n.value) != math.Float64bits(want.program.nodes[i].value) {
				t.Fatal("changed IEEE literal")
			}
		}
		for k := 0; k < 4; k++ {
			x := []float64{rng.Float64()*40 - 20, rng.Float64()*30 - 10}
			v, g, _, e := got.program.ValueGradient(x)
			wv, wg, _, we := want.program.ValueGradient(x)
			if e != nil || we != nil || math.Float64bits(v) != math.Float64bits(wv) || !reflect.DeepEqual(g, wg) {
				t.Fatal(v, wv, g, wg, e, we)
			}
		}
		if step == 0 {
			retained, retainedOracle = got, want
		}
	}
	if p.regionStats.Reused == 0 {
		t.Fatal("no region reuse exercised")
	}
	a1, e1 := retained.Evaluate([]float64{11, 12}, nil)
	a2, e2 := retainedOracle.Evaluate([]float64{11, 12}, nil)
	if e1 != nil || e2 != nil || a1 != a2 {
		t.Fatal("subsequent bindings mutated retained output")
	}
	p.regions.nodeLimit = 1
	got, e := p.BindConstantEffectsRegions([]float64{101, 102, 103})
	want, we := p.BindConstantEffects([]float64{101, 102, 103})
	if e != nil || we != nil || !reflect.DeepEqual(got.program.nodes, want.program.nodes) || p.regionStats.Resets == 0 {
		t.Fatal("bounded fallback", e, we)
	}
	for _, bad := range [][]float64{nil, {1}, {0, math.NaN(), 0}, {0, 0, math.Inf(1)}} {
		if _, e := p.BindConstantEffectsRegions(bad); e == nil {
			t.Fatal("invalid effect accepted")
		}
	}
}

func TestRegionsOrderedBranchesAndFailureRecovery(t *testing.T) {
	b := newProgramBuilder([]string{"a.hp", "b.em", "effect:x", "effect:y"})
	add := func(op uint8, coordinate int, value float64, inputs ...uint32) uint32 {
		t.Helper()
		id, err := b.add(compiledNode{op: op, coordinate: coordinate, value: value, inputs: inputs})
		if err != nil {
			t.Fatal(err)
		}
		return id
	}
	a, c := add(opArtifactStat, 0, 0), add(opArtifactStat, 1, 0)
	x, y := add(opArtifactStat, 2, 0), add(opArtifactStat, 3, 0)
	one, two := add(opConstant, -1, 1), add(opConstant, -1, 2)
	left := add(opMax, -1, 0, add(opAdd, -1, 0, a, x), one)
	right := add(opMin, -1, 0, add(opMultiply, -1, 0, c, y), two)
	branch := add(opSelectLT, -1, 0, x, two, left, right)
	power := add(opPower, -1, 0, left, two)
	root := add(opAdd, -1, 0, branch, left, power, branch, right, x, y)
	p := &ParametricProgram{program: b.finish(root), artifactCount: 2, effects: []string{"x", "y"}, actors: []string{"a", "b"}, input: make([]float64, 4)}
	for i := 0; i < 24; i++ {
		values := []float64{float64(i % 4), float64(i%3) - 1}
		got, err := p.BindConstantEffectsRegions(values)
		want, we := p.BindConstantEffects(values)
		if err != nil || we != nil || !reflect.DeepEqual(got.program.nodes, want.program.nodes) || got.program.root != want.program.root {
			t.Fatal("ordered branch graph", i, err, we)
		}
		v, g, _, err := got.program.ValueGradient([]float64{2, 3})
		wv, wg, _, we := want.program.ValueGradient([]float64{2, 3})
		if err != nil || we != nil || v != wv || !reflect.DeepEqual(g, wg) {
			t.Fatal("ordered branch gradient", v, wv, g, wg)
		}
	}
	b = newProgramBuilder([]string{"effect:x"})
	x = add(opArtifactStat, 0, 0)
	half := add(opConstant, -1, .5)
	root = add(opPower, -1, 0, x, half)
	p = &ParametricProgram{program: b.finish(root), effects: []string{"x"}, input: make([]float64, 1)}
	if _, err := p.BindConstantEffectsRegions([]float64{1}); err != nil {
		t.Fatal(err)
	}
	if _, err := p.BindConstantEffectsRegions([]float64{-1}); err == nil {
		t.Fatal("nonfinite intermediate accepted")
	}
	got, err := p.BindConstantEffectsRegions([]float64{4})
	if err != nil {
		t.Fatal(err)
	}
	v, err := got.Evaluate(nil, nil)
	if err != nil || v != 2 {
		t.Fatal("failed update poisoned later binding", v, err)
	}
}
