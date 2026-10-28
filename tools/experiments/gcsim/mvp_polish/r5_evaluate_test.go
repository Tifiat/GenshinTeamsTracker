package formula

import (
	"math"
	"testing"
)

func r5Program(t *testing.T) *ArtifactProgram {
	t.Helper()
	_, compiled := parametricMember(t, 1000)
	prepared, err := PrepareParametric([]*CompiledMember{compiled}, nil)
	if err != nil {
		t.Fatal(err)
	}
	p := copyArtifactScratch(prepared.program)
	p.coordinates = append(append([]string(nil), p.coordinates...), "unused.hp")
	p.dependencies, p.dependencyRuns, p.previous = nil, nil, nil
	p.previousValid = false
	return p
}

func TestR5EvaluateFiniteBitsReuseAndErrors(t *testing.T) {
	p := r5Program(t)
	legacy := copyArtifactScratch(p)
	vectors := [][]float64{
		{0, 0, 0}, {0, 0, 1}, {math.Copysign(0, -1), 0, 1},
		{1, 2, 1}, {1, 2, math.Copysign(0, -1)}, {1, 2, 0},
		{math.MaxFloat64, math.MaxFloat64, 0}, {1, 2, 0},
		{1, 2, math.NaN()}, {1, 2, 0}, {1, 2, math.Inf(1)}, {1, 2, 0},
	}
	for i, x := range vectors {
		got, err := p.Evaluate(x)
		want, oldErr := legacy.evaluateR4Legacy(x)
		if (err == nil) != (oldErr == nil) {
			t.Fatalf("%d: %v / %v", i, err, oldErr)
		}
		if err == nil && math.Float64bits(got) != math.Float64bits(want) {
			t.Fatalf("%d: %x != %x", i, math.Float64bits(got), math.Float64bits(want))
		}
		if p.previousValid != legacy.previousValid {
			t.Fatalf("%d: reuse/error state differs from R4", i)
		}
	}
	_, err := p.Evaluate([]float64{1})
	_, oldErr := legacy.evaluateR4Legacy([]float64{1})
	if err == nil || oldErr == nil || p.previousValid != legacy.previousValid {
		t.Fatal("shape error changed R4 scratch state")
	}
	if _, err := p.Evaluate([]float64{1, 2, 0}); err != nil {
		t.Fatal(err)
	}
}
