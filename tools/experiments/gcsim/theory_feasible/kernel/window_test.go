package theoryprototype

import (
	"math"
	"testing"
	"time"
)

func windowToyStart() State {
	var gradient [4][10]float64
	gradient[0][7] = 1
	return Seed(testMains(), gradient, 0, 20)
}

func TestWindowOptimizeExpandsThreeWidths(t *testing.T) {
	started := time.Now()
	start := windowToyStart()
	base := start.Rolls()[0][7]
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		x := state.Rolls()[0][7] - base
		var gradient [4][10]float64
		gradient[0][7] = 2 * (9 - x)
		return 100 - math.Pow(x-9, 2), gradient, nil
	}
	cfg := Config{Budget: 45, Method: "spg", MaxIterations: 20, LineSearch: true}
	type caseResult struct {
		InitialRadius   float64 `json:"initial_radius"`
		FinalRadius     float64 `json:"final_radius"`
		Value           float64 `json:"value"`
		Evaluations     int     `json:"evaluations"`
		RejectedOutside int     `json:"rejected_outside"`
		Expansions      int     `json:"expansions"`
		Stop            string  `json:"stop"`
	}
	cases := make([]caseResult, 0, 3)
	for _, radius := range []float64{1, 4, 12} {
		result, err := WindowOptimize(obj, start, cfg, WindowConfig{Radius: radius, MaxExpansions: 4})
		if err != nil {
			t.Fatal(err)
		}
		if err := result.State.Validate(45, true); err != nil {
			t.Fatal(err)
		}
		if math.Abs(result.Value-100) > 1e-8 ||
			!insideRollWindow(result.State, start.Rolls(), result.Radius) {
			t.Fatalf("radius %g missed the quadratic toy peak: %+v", radius, result)
		}
		if radius < 9 && result.Expansions == 0 {
			t.Fatalf("radius %g failed to expand: %+v", radius, result)
		}
		cases = append(cases, caseResult{radius, result.Radius, result.Value,
			result.Evaluations, result.RejectedOutside, result.Expansions, result.Stop})
	}
	marginalReceipt(t, map[string]any{
		"case": "per_stat_roll_windows", "budget": 45,
		"fixed_layout_peak": 9, "oracle_value": 100,
		"widths": cases, "nanoseconds": time.Since(started).Nanoseconds(),
	})
}

func TestWindowOptimizeWideCheckpointFindsOutsidePeak(t *testing.T) {
	started := time.Now()
	start := windowToyStart()
	base := start.Rolls()[0][7]
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		x := state.Rolls()[0][7] - base
		var gradient [4][10]float64
		if x < 5 {
			gradient[0][7] = -2 * x
			return -x * x, gradient, nil
		}
		gradient[0][7] = 2 * (20 - x)
		return 100 - math.Pow(x-20, 2), gradient, nil
	}
	cfg := Config{Budget: 45, Method: "spg", MaxIterations: 20, LineSearch: true}
	fixed, err := WindowOptimize(obj, start, cfg, WindowConfig{Radius: 4, MaxExpansions: 0})
	if err != nil {
		t.Fatal(err)
	}
	wide, err := WindowOptimize(obj, start, cfg, WindowConfig{
		Radius: 4, MaxExpansions: 1, ProbeWide: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := wide.State.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	// Independent exact quarter oracle for the one-dimensional fixed-layout
	// domain x=0,.25,...,25. This piecewise toy has a far higher peak at 20.
	oracleValue, oracleX := math.Inf(-1), -1.0
	for quarter := 0; quarter <= 100; quarter++ {
		x := float64(quarter) / 4
		value := -x * x
		if x >= 5 {
			value = 100 - math.Pow(x-20, 2)
		}
		if value > oracleValue {
			oracleX, oracleValue = x, value
		}
	}
	if fixed.Value != 0 || fixed.Expansions != 0 || fixed.Stop != "interior_window" ||
		wide.Stop != "wide_probe_expansion" || !wide.WideProbed || wide.Expansions != 1 ||
		math.Abs(wide.Value-oracleValue) > 1e-8 || oracleX != 20 {
		t.Fatalf("outside peak control: fixed %+v, wide %+v, oracle %g at %g", fixed, wide, oracleValue, oracleX)
	}
	marginalReceipt(t, map[string]any{
		"case": "outside_peak_wide_checkpoint", "budget": 45,
		"fixed_value": fixed.Value, "fixed_evaluations": fixed.Evaluations,
		"wide_value": wide.Value, "wide_evaluations": wide.Evaluations,
		"wide_seed_probes": wide.WideSeedProbes, "wide_probe_evaluations": wide.WideEvaluations,
		"oracle_x": oracleX, "oracle_value": oracleValue, "oracle_evaluations": 101,
		"stop": wide.Stop, "nanoseconds": time.Since(started).Nanoseconds(),
	})
}
