package formula

import (
	"math"
	"reflect"
	"testing"
)

func r3GradientFixture() *ArtifactProgram {
	b := newProgramBuilder([]string{"actor.atk", "actor.em"})
	a, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 1})
	two, _ := b.add(compiledNode{op: opConstant, value: 2})
	power, _ := b.add(compiledNode{op: opPower, inputs: []uint32{a, two}})
	product, _ := b.add(compiledNode{op: opMultiply, inputs: []uint32{a, x, power}})
	low, _ := b.add(compiledNode{op: opMin, inputs: []uint32{a, x}})
	high, _ := b.add(compiledNode{op: opMax, inputs: []uint32{a, x}})
	branch, _ := b.add(compiledNode{op: opSelectLT, inputs: []uint32{a, x, low, high}})
	root, _ := b.add(compiledNode{op: opAdd, inputs: []uint32{product, branch}})
	return b.finish(root)
}

func TestR3AdjointBitParityAndReturnedOwnership(t *testing.T) {
	t.Setenv("GTT_R3_ADJOINT_REUSE", "1")
	p := r3GradientFixture()
	control := copyArtifactScratch(p)
	for pass := 0; pass < 4; pass++ {
		for _, delta := range [][]float64{{0, 0}, {1, 2}, {2, 1}, {-2, 3}, {3, 3}, {math.Copysign(0, -1), 2}, {1e-9, 1e9}} {
			want, wg, ws, we := control.r3FrozenValueGradient(delta)
			got, gg, gs, ge := p.ValueGradient(delta)
			if (we == nil) != (ge == nil) || math.Float64bits(want) != math.Float64bits(got) || ws != gs || len(wg) != len(gg) {
				t.Fatal("gradient arithmetic differs")
			}
			for i := range wg {
				if math.Float64bits(wg[i]) != math.Float64bits(gg[i]) {
					t.Fatal("gradient FP order differs")
				}
			}
			saved := append([]float64(nil), gg...)
			if _, _, _, err := p.ValueGradient([]float64{4, 2}); err != nil {
				t.Fatal(err)
			}
			if !reflect.DeepEqual(saved, gg) {
				t.Fatal("returned gradient was overwritten by another call")
			}
		}
	}
	if _, _, _, err := p.ValueGradient([]float64{math.NaN(), 0}); err == nil {
		t.Fatal("nonfinite input accepted")
	}
	if _, _, _, err := p.ValueGradient([]float64{1}); err == nil {
		t.Fatal("bad dimensions accepted")
	}
	if _, _, _, err := p.ValueGradient([]float64{2, 3}); err != nil {
		t.Fatal("failed call poisoned scratch")
	}
}

func TestR3AdjointScratchCopiesAndToggle(t *testing.T) {
	t.Setenv("GTT_R3_ADJOINT_REUSE", "1")
	p := r3GradientFixture()
	p.ValueGradient([]float64{2, 3})
	if len(p.r3Adjoints) != len(p.nodes) {
		t.Fatal("owner buffer absent")
	}
	for _, copy := range []*ArtifactProgram{copyArtifactScratch(p), p.ForkTheory()} {
		if copy.r3Adjoints != nil {
			t.Fatal("fork borrowed mutable adjoints")
		}
		copy.ValueGradient([]float64{4, 2})
		if &copy.r3Adjoints[0] == &p.r3Adjoints[0] {
			t.Fatal("fork allocated shared adjoints")
		}
	}
	t.Setenv("GTT_R3_ADJOINT_REUSE", "0")
	other := r3GradientFixture()
	other.ValueGradient([]float64{2, 3})
	if other.r3Adjoints != nil {
		t.Fatal("disabled module retained buffer")
	}
}
