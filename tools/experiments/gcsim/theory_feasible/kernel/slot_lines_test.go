package theoryprototype

import (
	"math"
	"testing"
	"time"
)

// This nonlinear toy makes a new line unattractive before upgrades, and makes
// the second line unattractive before reallocating the first line's upgrades.
// Only actor zero's flower and plume can activate the two toy features.
func twoSlotLineToy(state State, needGradient bool) (float64, [4][10]float64, error) {
	var gradient [4][10]float64
	first, second := false, false
	countFirst, countSecond, offTarget := 0, 0, 0
	for slot := range state.Lines[0] {
		for _, stat := range state.Lines[0][slot] {
			switch stat {
			case 9:
				countFirst++
				if slot == 0 {
					first = true
				} else {
					offTarget++
				}
			case 8:
				countSecond++
				if slot == 1 {
					second = true
				} else {
					offTarget++
				}
			}
		}
	}
	rolls := state.Rolls()[0]
	qFirst := rolls[9] - float64(countFirst)
	qSecond := rolls[8] - float64(countSecond)
	penalty := 100 * float64(offTarget)
	switch {
	case first && second:
		gradient[0][9] = 1.2
		gradient[0][8] = 2.4 + .8*qSecond
		return -.3 + 1.2*qFirst + 2.4*qSecond + .4*qSecond*qSecond - penalty, gradient, nil
	case first:
		gradient[0][9] = 2 + .4*qFirst
		return -.2 + 2*qFirst + .2*qFirst*qFirst - penalty, gradient, nil
	case second:
		gradient[0][8] = 1.5 + .4*qSecond
		return -.2 + 1.5*qSecond + .2*qSecond*qSecond - penalty, gradient, nil
	default:
		return -penalty, gradient, nil
	}
}

func TestSlotLinesAcceptsTwoReoptimizedSlotsInOnePass(t *testing.T) {
	started := time.Now()
	start := Seed(testMains(), [4][10]float64{}, 0, 20)
	if err := start.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	if StatKeys[9] == start.Mains[0][0] || StatKeys[8] == start.Mains[0][1] {
		t.Fatal("toy target matches a forbidden main")
	}
	first := start
	first.Lines[0][0][0] = 9
	if err := first.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	firstDirect, _, _ := twoSlotLineToy(first, false)
	first.Upgrades[0][0][0] = .5
	firstOptimized, _, _ := twoSlotLineToy(first, false)
	secondDirect := first
	secondDirect.Lines[0][1][0] = 8
	if err := secondDirect.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	secondDirectValue, _, _ := twoSlotLineToy(secondDirect, false)
	if firstDirect >= 0 || firstOptimized <= 0 || secondDirectValue >= firstOptimized {
		t.Fatalf("toy lacks the two delayed improvements: direct %g, optimized %g, second direct %g", firstDirect, firstOptimized, secondDirectValue)
	}
	// Exhaust this explicit four-layout domain with at most two quarter units
	// assigned to the two special lines. Other actors and lines are fixed.
	oracle := math.Inf(-1)
	oracleEvaluations := 0
	for mask := 0; mask < 4; mask++ {
		layout := start
		if mask&1 != 0 {
			layout.Lines[0][0][0] = 9
		}
		if mask&2 != 0 {
			layout.Lines[0][1][0] = 8
		}
		for firstQuarters := 0; firstQuarters <= 2; firstQuarters++ {
			if mask&1 == 0 && firstQuarters != 0 {
				continue
			}
			for secondQuarters := 0; secondQuarters <= 2-firstQuarters; secondQuarters++ {
				if mask&2 == 0 && secondQuarters != 0 {
					continue
				}
				candidate := layout
				candidate.Upgrades[0][0][0] = float64(firstQuarters) / 4
				candidate.Upgrades[0][1][0] = float64(secondQuarters) / 4
				if err := candidate.Validate(20.5, true); err != nil {
					t.Fatal(err)
				}
				value, _, err := twoSlotLineToy(candidate, false)
				if err != nil {
					t.Fatal(err)
				}
				oracle = math.Max(oracle, value)
				oracleEvaluations++
			}
		}
	}
	result, err := SlotLines(twoSlotLineToy, start, Config{
		Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true,
	}, SlotLineConfig{Passes: 1, InnerIterations: 4})
	if err != nil {
		t.Fatal(err)
	}
	if err := result.State.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	if math.Abs(result.Value-oracle) > 1e-10 || result.Accepted != 2 || result.Passes != 1 {
		t.Fatalf("two-slot optimized result %+v, oracle %g", result, oracle)
	}
	marginalReceipt(t, map[string]any{
		"case": "two_slot_line_reoptimization", "first_direct": firstDirect,
		"first_optimized": firstOptimized, "second_direct": secondDirectValue,
		"value": result.Value, "oracle": oracle,
		"oracle_evaluations": oracleEvaluations,
		"candidate_count":    result.Candidates, "accepted": result.Accepted,
		"objective_evaluations": result.Evaluations,
		"nanoseconds":           time.Since(started).Nanoseconds(),
	})
}

func TestSlotLinesPreservesUnimprovedQuarterInput(t *testing.T) {
	start := Seed(testMains(), [4][10]float64{}, 0, 20)
	start.Upgrades[0][0][0] = .25
	constant := func(State, bool) (float64, [4][10]float64, error) {
		return 7, [4][10]float64{}, nil
	}
	result, err := SlotLines(constant, start, Config{
		Budget: 20.25, Method: "spg", MaxIterations: 4, LineSearch: true,
	}, SlotLineConfig{Passes: 1, InnerIterations: 4})
	if err != nil {
		t.Fatal(err)
	}
	if result.State != start || result.Value != 7 || result.Accepted != 0 {
		t.Fatalf("valid warm input was lost: %+v", result)
	}
}
