package formula

import (
	"math"
	"math/rand"
	"reflect"
	"testing"
)

func incrementalFixture(t *testing.T) *ArtifactProgram {
	t.Helper()
	b := newProgramBuilder([]string{"a.atk", "a.cr", "b.hp"})
	add := func(n compiledNode) uint32 {
		id, err := b.add(n)
		if err != nil {
			t.Fatal(err)
		}
		return id
	}
	x := add(compiledNode{op: opArtifactStat, coordinate: 0})
	y := add(compiledNode{op: opArtifactStat, coordinate: 1})
	z := add(compiledNode{op: opArtifactStat, coordinate: 2})
	one := add(compiledNode{op: opConstant, coordinate: -1, value: 1})
	cap := add(compiledNode{op: opMin, coordinate: -1, inputs: []uint32{y, one}})
	left := add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{x, cap}})
	right := add(compiledNode{op: opMax, coordinate: -1, inputs: []uint32{z, one}})
	branch := add(compiledNode{op: opSelectLT, coordinate: -1, inputs: []uint32{x, z, left, right}})
	root := add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{branch, left, right, cap, one}})
	return b.finish(root)
}

func TestIncrementalEvaluationExactFullSweepAndPrivateScratch(t *testing.T) {
	fast := incrementalFixture(t)
	slow := copyArtifactScratch(fast)
	slow.active = nil // existing full evaluation path, independent scratch
	x := []float64{0, 0, 0}
	rng := rand.New(rand.NewSource(702))
	for i := 0; i < 1000; i++ {
		if i%7 != 0 {
			x[rng.Intn(len(x))] = rng.Float64()*4 - 2
		}
		if i%11 == 0 {
			x[0] = math.Copysign(0, -1)
		}
		a, err := fast.Evaluate(x)
		b, other := slow.Evaluate(x)
		if err != nil || other != nil || math.Float64bits(a) != math.Float64bits(b) {
			t.Fatal(i, a, b, err, other)
		}
		_, ag, as, err := fast.ValueGradient(x)
		_, bg, bs, other := slow.ValueGradient(x)
		if err != nil || other != nil || as != bs || !reflect.DeepEqual(ag, bg) {
			t.Fatal(i, ag, bg, err, other)
		}
	}
	clone := copyArtifactScratch(fast)
	if &clone.previous[0] == &fast.previous[0] {
		t.Fatal("shared mutable input scratch")
	}
	clone.Evaluate([]float64{8, 9, 10})
	a, _ := fast.Evaluate(x)
	b, _ := slow.Evaluate(x)
	if a != b {
		t.Fatal("clone contaminated original", a, b)
	}
	if _, err := fast.Evaluate([]float64{math.NaN(), 0, 0}); err == nil {
		t.Fatal("accepted NaN")
	}
	a, _ = fast.Evaluate(x)
	if a != b {
		t.Fatal("invalid input contaminated scratch")
	}
}

func TestIncrementalErrorDoesNotCachePartiallyUpdatedValues(t *testing.T) {
	b := newProgramBuilder([]string{"a.x", "a.y"})
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	y, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 1})
	e, _ := b.add(compiledNode{op: opConstant, coordinate: -1, value: .5})
	r, _ := b.add(compiledNode{op: opPower, coordinate: -1, inputs: []uint32{x, e}})
	r, _ = b.add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{r, y}})
	p := b.finish(r)
	if got, err := p.Evaluate([]float64{4, 1}); got != 3 || err != nil {
		t.Fatal(got, err)
	}
	if _, err := p.Evaluate([]float64{-4, 2}); err == nil {
		t.Fatal("missing invalid power")
	}
	if got, err := p.Evaluate([]float64{4, 1}); got != 3 || err != nil {
		t.Fatal(got, err)
	}
}

func TestIncrementalUnchangedLiveStatsStillValidateAllInputs(t *testing.T) {
	b := newProgramBuilder([]string{"a.atk", "a.unused"})
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	c, _ := b.add(compiledNode{op: opConstant, coordinate: -1, value: 3})
	r, _ := b.add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{x, c}})
	p := b.finish(r)
	for _, input := range [][]float64{{2, 0}, {2, 100}, {2, math.Copysign(0, -1)}, {4, 10}} {
		if got, err := p.Evaluate(input); err != nil || got != 3*input[0] {
			t.Fatal(input, got, err)
		}
	}
	if _, err := p.Evaluate([]float64{4, math.NaN()}); err == nil {
		t.Fatal("unused nonfinite coordinate bypassed validation")
	}
	if got, err := p.Evaluate([]float64{4, 10}); err != nil || got != 12 {
		t.Fatal(got, err)
	}
}

func TestSmallProgramKeyPreservesSignedZeroAndOperandOrder(t *testing.T) {
	b := newProgramBuilder([]string{"a.x", "a.y"})
	p, _ := b.add(compiledNode{op: opConstant, coordinate: -1, value: 0})
	n, _ := b.add(compiledNode{op: opConstant, coordinate: -1, value: math.Copysign(0, -1)})
	if p == n {
		t.Fatal("merged signed zero")
	}
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	y, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 1})
	for _, inputs := range [][]uint32{{x, y}, {x, y, x, y, x}} {
		a, _ := b.add(compiledNode{op: opAdd, coordinate: -1, inputs: inputs})
		dup, _ := b.add(compiledNode{op: opAdd, coordinate: -1, inputs: append([]uint32(nil), inputs...)})
		reversed := append([]uint32(nil), inputs...)
		reversed[0], reversed[1] = reversed[1], reversed[0]
		z, _ := b.add(compiledNode{op: opAdd, coordinate: -1, inputs: reversed})
		if a != dup || a == z {
			t.Fatal("changed ordered identity")
		}
	}
}

func TestProgramCompactionOwnsOperandSlices(t *testing.T) {
	b := newProgramBuilder([]string{"a.x", "a.y"})
	b.add(compiledNode{op: opConstant, coordinate: -1, value: 12345}) // removed
	x, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 0})
	y, _ := b.add(compiledNode{op: opArtifactStat, coordinate: 1})
	input := []uint32{x, y}
	r, _ := b.add(compiledNode{op: opMultiply, coordinate: -1, inputs: input})
	p := b.finish(r)
	if !reflect.DeepEqual(input, []uint32{x, y}) {
		t.Fatal("source operands modified", input)
	}
	for _, n := range p.nodes {
		if len(n.inputs) > 0 && cap(n.inputs) != len(n.inputs) {
			t.Fatal("operand capacity exposes neighboring node")
		}
	}
	input[0] = 999
	if got, err := p.Evaluate([]float64{2, 3}); got != 6 || err != nil {
		t.Fatal(got, err)
	}
}
