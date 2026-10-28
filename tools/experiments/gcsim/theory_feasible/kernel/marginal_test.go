package theoryprototype

import (
	"encoding/json"
	"fmt"
	"math"
	"testing"
	"time"
)

func marginalReceipt(t *testing.T, fields map[string]any) {
	t.Helper()
	encoded, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println("FEASIBLE_RECEIPT " + string(encoded))
}

func firstLineWithStat(state State, actor, stat int) (slot, line int, found bool) {
	for s := range state.Lines[actor] {
		for l, candidate := range state.Lines[actor][s] {
			if candidate == stat {
				return s, l, true
			}
		}
	}
	return 0, 0, false
}

func TestQuarterExchangeFindsActualDiscreteTransfer(t *testing.T) {
	startTime := time.Now()
	var seedGradient [4][10]float64
	seedGradient[0][3], seedGradient[0][2] = 2, 1
	state := Seed(testMains(), seedGradient, 0, 20)
	baseRate := state.Rolls()[0][3]
	rateSlot, rateLine, found := firstLineWithStat(state, 0, 3)
	if !found {
		t.Fatal("rate line absent")
	}
	damageSlot, damageLine, found := firstLineWithStat(state, 0, 2)
	if !found {
		t.Fatal("damage line absent")
	}
	state.Upgrades[0][rateSlot][rateLine] = .25
	state.Upgrades[0][damageSlot][damageLine] = .25
	if err := state.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	obj := func(candidate State, needGradient bool) (float64, [4][10]float64, error) {
		x := candidate.Rolls()[0][3] - baseRate - .25
		var gradient [4][10]float64
		gradient[0][3] = 2 * x
		return x * x, gradient, nil
	}
	spg, err := Optimize(obj, state, Config{Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true})
	if err != nil {
		t.Fatal(err)
	}
	transfer, err := QuarterExchange(obj, spg.State, QuarterExchangeConfig{
		Budget: 20.5, Actors: [4]bool{true}, MaxMoves: 2, MaxEvaluations: 512,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := transfer.State.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	// The deliberately restricted independent domain redistributes exactly two
	// quarter units between rate and damage on these two existing lines.
	oracle := math.Inf(-1)
	for rateQuarters := 0; rateQuarters <= 2; rateQuarters++ {
		candidate := state
		candidate.Upgrades[0][rateSlot][rateLine] = float64(rateQuarters) / 4
		candidate.Upgrades[0][damageSlot][damageLine] = float64(2-rateQuarters) / 4
		value, _, evalErr := obj(candidate, false)
		if evalErr != nil {
			t.Fatal(evalErr)
		}
		oracle = math.Max(oracle, value)
	}
	if spg.Value != 0 || math.Abs(transfer.Value-oracle) > 1e-12 || transfer.Moves != 1 {
		t.Fatalf("stationary SPG %.9g, exchange %.9g, tiny oracle %.9g, stats %+v", spg.Value, transfer.Value, oracle, transfer)
	}
	marginalReceipt(t, map[string]any{
		"case": "actual_quarter_exchange", "spg": spg.Value,
		"exchange": transfer.Value, "oracle": oracle,
		"spg_evaluations": spg.Evaluations, "exchange_evaluations": transfer.Evaluations,
		"eligible_moves": transfer.EligibleMoves, "tested_moves": transfer.TestedMoves,
		"stop": transfer.Stop, "nanoseconds": time.Since(startTime).Nanoseconds(),
	})
}

func TestPureCritPairRateBonusReallocatesQuarterUnits(t *testing.T) {
	startTime := time.Now()
	const baseRate, baseDamage, total = .55, 1.2, 24.0
	type caseResult struct {
		Bonus           float64 `json:"bonus"`
		ContinuousRate  float64 `json:"continuous_rate"`
		QuarterRate     float64 `json:"quarter_rate"`
		ContinuousValue float64 `json:"continuous_value"`
		QuarterValue    float64 `json:"quarter_value"`
		CapRate         float64 `json:"cap_rate"`
		Capped          bool    `json:"capped"`
	}
	results := make([]caseResult, 0, 2)
	evaluations := 0
	for _, bonus := range []float64{0, .25} {
		continuousRate, continuousValue, capRate := pureCritPairContinuous(baseRate, baseDamage, bonus, total)
		bestValue := math.Inf(-1)
		bestRate := 0.0
		for quarter := 0; quarter <= int(4*total); quarter++ {
			q := float64(quarter) / 4
			value := 1 + math.Min(1, baseRate+bonus+.0389*q)*(baseDamage+.0777*(total-q))
			evaluations++
			if value > bestValue {
				bestValue, bestRate = value, q
			}
		}
		if continuousValue+1e-12 < bestValue || math.Abs(continuousRate-capRate) > 1e-10 {
			t.Fatalf("invalid capped vertex for bonus %g: continuous %g at %g, quarter %g at %g, cap %g", bonus, continuousValue, continuousRate, bestValue, bestRate, capRate)
		}
		results = append(results, caseResult{bonus, continuousRate, bestRate, continuousValue, bestValue, capRate, true})
	}
	if results[0].QuarterRate != 11.5 || results[1].QuarterRate != 5 ||
		results[0].QuarterRate-results[1].QuarterRate != 6.5 {
		t.Fatalf("rate allocation did not shift as analytically predicted: %+v", results)
	}
	marginalReceipt(t, map[string]any{
		"case": "pure_crit_pair_bonus", "domain": "one capped crit pair, 24 total units",
		"results": results, "oracle_evaluations": evaluations,
		"nanoseconds": time.Since(startTime).Nanoseconds(),
	})
}

func TestAdaptiveRollWindowsAndOutsideControl(t *testing.T) {
	startTime := time.Now()
	score := func(total int) (float64, error) {
		return 100 - math.Pow(float64(total-34), 2), nil
	}
	type window struct {
		HalfWidth   int    `json:"half_width"`
		BestTotal   int    `json:"best_total"`
		Evaluations int    `json:"evaluations"`
		Expansions  int    `json:"expansions"`
		Stop        string `json:"stop"`
	}
	windows := make([]window, 0, 3)
	for _, width := range []int{1, 3, 7} {
		result, err := AdaptiveRollWindow(score, RollWindowConfig{
			MinTotal: 20, MaxTotal: 45, Center: 25, HalfWidth: width,
			MaxExpansions: 4, MaxEvaluations: 64,
		})
		if err != nil {
			t.Fatal(err)
		}
		if result.BestTotal != 34 || result.Value != 100 || result.Expansions == 0 {
			t.Fatalf("width %d missed the interior peak: %+v", width, result)
		}
		windows = append(windows, window{width, result.BestTotal, result.Evaluations, result.Expansions, result.Stop})
	}
	outside := func(total int) (float64, error) {
		value := 100 - math.Pow(float64(total-25), 2)
		if total == 40 {
			value += 400
		}
		return value, nil
	}
	local, err := AdaptiveRollWindow(outside, RollWindowConfig{
		MinTotal: 20, MaxTotal: 45, Center: 25, HalfWidth: 2,
		MaxExpansions: 4, MaxEvaluations: 64,
	})
	if err != nil {
		t.Fatal(err)
	}
	globalTotal, globalValue := -1, math.Inf(-1)
	for total := 20; total <= 45; total++ {
		value, evalErr := outside(total)
		if evalErr != nil {
			t.Fatal(evalErr)
		}
		if value > globalValue {
			globalTotal, globalValue = total, value
		}
	}
	if local.BestTotal != 25 || local.Stop != "interior_window" || globalTotal != 40 || globalValue <= local.Value {
		t.Fatalf("outside control did not demonstrate hidden peak: local %+v, full %d %g", local, globalTotal, globalValue)
	}
	marginalReceipt(t, map[string]any{
		"case": "adaptive_roll_windows", "windows": windows,
		"outside_local_total": local.BestTotal, "outside_local_value": local.Value,
		"outside_global_total": globalTotal, "outside_global_value": globalValue,
		"outside_local_evaluations": local.Evaluations, "outside_full_evaluations": 26,
		"nanoseconds": time.Since(startTime).Nanoseconds(),
	})
}

func TestNonlinearComplementaryPackagesFourMaskOracle(t *testing.T) {
	startTime := time.Now()
	var seedGradient [4][10]float64
	seedGradient[0][7] = 1
	start := Seed(testMains(), seedGradient, 0, 20)
	baseRecharge := start.Rolls()[0][7]
	var scores [4]float64
	optEvaluations := 0
	for mask := 0; mask < 4; mask++ {
		mask := mask
		obj := func(candidate State, needGradient bool) (float64, [4][10]float64, error) {
			var gradient [4][10]float64
			if mask == 0 {
				return 0, gradient, nil
			}
			if mask != 3 {
				return -.2, gradient, nil
			}
			x := candidate.Rolls()[0][7] - baseRecharge
			gradient[0][7] = 1 + 2*x
			return .5 + x + x*x, gradient, nil
		}
		result, err := Optimize(obj, start, Config{
			Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true,
		})
		if err != nil {
			t.Fatal(err)
		}
		if err := result.State.Validate(20.5, true); err != nil {
			t.Fatal(err)
		}
		scores[mask] = result.Value
		optEvaluations += result.Evaluations
	}
	// Independent exhaustive oracle for this restricted outer four-mask and
	// inner q=0,.25,.5 energy-recharge allocation domain.
	oracleMask, oracleValue := -1, math.Inf(-1)
	for mask := 0; mask < 4; mask++ {
		for quarters := 0; quarters <= 2; quarters++ {
			q := float64(quarters) / 4
			value := 0.0
			switch mask {
			case 1, 2:
				value = -.2
			case 3:
				value = .5 + q + q*q
			}
			if value > oracleValue {
				oracleMask, oracleValue = mask, value
			}
		}
	}
	selectedOnlyMask, selectedOnlyValue := 0, scores[0]
	for _, mask := range []int{1, 2} {
		if scores[mask] > selectedOnlyValue {
			selectedOnlyMask, selectedOnlyValue = mask, scores[mask]
		}
	}
	if selectedOnlyMask != 0 || oracleMask != 3 ||
		math.Abs(scores[3]-oracleValue) > 1e-10 || scores[3] <= selectedOnlyValue {
		t.Fatalf("four-mask complementarity failed: scores %v, selected %d %g, oracle %d %g", scores, selectedOnlyMask, selectedOnlyValue, oracleMask, oracleValue)
	}
	marginalReceipt(t, map[string]any{
		"case": "nonlinear_package_complementarity", "scores": scores,
		"selected_only_mask": selectedOnlyMask, "selected_only_value": selectedOnlyValue,
		"four_mask_oracle": oracleMask, "oracle_value": oracleValue,
		"optimize_evaluations": optEvaluations, "oracle_evaluations": 12,
		"nanoseconds": time.Since(startTime).Nanoseconds(),
	})
}
