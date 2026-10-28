package evaluator

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"testing"
)

func TestR5SearchViewOwnScratchZeroPreflight(t *testing.T) {
	request, ir := fixtures(t)
	panel, err := Compile(request, ir)
	if err != nil {
		t.Fatal(err)
	}
	program, err := panel.PrepareEffectInputs(nil)
	if err != nil {
		t.Fatal(err)
	}
	cache := formula.NewSpecializationCache(8, 100000)
	for _, reasons := range [][]string{nil, {"observed_window"}} {
		calls := formula.ResearchEvaluateCalls
		legacy, err := panel.ParametricView(program.WithSpecializationCache(cache), reasons)
		if err != nil {
			t.Fatal(err)
		}
		current, err := panel.ParametricSearchView(program, cache, reasons)
		if err != nil {
			t.Fatal(err)
		}
		if formula.ResearchEvaluateCalls != calls+2 {
			t.Fatal("zero-input preflight skipped or duplicated")
		}
		if math.Float64bits(legacy.baseline.MeanDPS) != math.Float64bits(current.baseline.MeanDPS) {
			t.Fatal("baseline changed")
		}
		other, err := panel.ParametricSearchView(program, cache, reasons)
		if err != nil {
			t.Fatal(err)
		}
		for _, amount := range []float64{0, .1, .2, -.1, 0} {
			x := make([]float64, len(current.coordinates))
			for i := range x {
				x[i] = amount
			}
			got, e := current.EvaluateDPS(x)
			want, e2 := legacy.EvaluateDPS(x)
			if e != nil || e2 != nil || math.Float64bits(got) != math.Float64bits(want) {
				t.Fatal(got, want, e, e2)
			}
			zero := make([]float64, len(other.coordinates))
			value, e := other.EvaluateDPS(zero)
			if e != nil || math.Float64bits(value) != math.Float64bits(other.baseline.MeanDPS) {
				t.Fatal("scratch leaked between views", value, e)
			}
		}
	}
	if _, err = panel.ParametricSearchView(nil, cache, nil); err == nil {
		t.Fatal("invalid program accepted")
	}
}
