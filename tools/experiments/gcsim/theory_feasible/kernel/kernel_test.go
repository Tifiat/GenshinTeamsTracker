package theoryprototype

import (
	"math"
	"testing"
)

func testMains() [4][5]string {
	return [4][5]string{
		{"hp", "atk", "em", "pyro_damage_bonus", "crit_rate"},
		{"hp", "atk", "atk_percent", "hydro_damage_bonus", "crit_damage"},
		{"hp", "atk", "energy_recharge", "electro_damage_bonus", "healing_bonus"},
		{"hp", "atk", "hp_percent", "physical_damage_bonus", "def_percent"},
	}
}

func linearObjective(weights [4][10]float64) Objective {
	return func(state State, needGradient bool) (float64, [4][10]float64, error) {
		rolls := state.Rolls()
		value := 0.0
		for actor := range rolls {
			for stat, amount := range rolls[actor] {
				value += weights[actor][stat] * amount
			}
		}
		return value, weights, nil
	}
}

func TestProjectionUsesJointActorAndSlotConstraints(t *testing.T) {
	var input [5][4]float64
	input[0] = [4]float64{5, 5}
	input[1] = [4]float64{4, 4}
	got := projectActor(input, 7)
	for _, point := range []struct {
		slot, line int
		want       float64
	}{
		{0, 0, 2.25}, {0, 1, 2.25}, {1, 0, 1.25}, {1, 1, 1.25},
	} {
		if math.Abs(got[point.slot][point.line]-point.want) > 1e-9 {
			t.Fatalf("joint projection (%d,%d) = %.12g; want %.12g", point.slot, point.line, got[point.slot][point.line], point.want)
		}
	}
	for slot := range got {
		for line := range got[slot] {
			if slot < 2 && line < 2 {
				continue
			}
			if math.Abs(got[slot][line]) > 1e-9 {
				t.Fatalf("unexpected positive coordinate (%d,%d): %g", slot, line, got[slot][line])
			}
		}
	}
}

func TestValidityRejectsAllCritAndMainCollision(t *testing.T) {
	state := Seed(testMains(), [4][10]float64{}, 0, 45)
	if err := state.Validate(45, false); err != nil {
		t.Fatalf("seed is invalid: %v", err)
	}
	critRate := 3
	for line := range state.Lines[0][0] {
		state.Lines[0][0][line] = critRate
	}
	if err := state.Validate(45, false); err == nil {
		t.Fatal("four identical crit lines were accepted")
	}
	state = Seed(testMains(), [4][10]float64{}, 0, 45)
	state.Lines[0][4][0] = critRate // crit-rate circlet excludes crit-rate lines
	if err := state.Validate(45, false); err == nil {
		t.Fatal("line matching its circlet main was accepted")
	}
}

func TestCritSplitQuadraticAtBudget30(t *testing.T) {
	mains := testMains()
	var initialGradient [4][10]float64
	initialGradient[0][2], initialGradient[0][3] = 5, 4
	state := Seed(mains, initialGradient, 0, 30)
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		rolls := state.Rolls()
		damageError := rolls[0][2] - 10.75
		rateError := rolls[0][3] - 7.25
		var g [4][10]float64
		g[0][2], g[0][3] = -2*damageError, -2*rateError
		return -damageError*damageError - rateError*rateError, g, nil
	}
	result, err := Optimize(obj, state, Config{Budget: 30, Method: "spg", MaxIterations: 80, LineSearch: true, Polish: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := result.State.Validate(30, true); err != nil {
		t.Fatal(err)
	}
	if result.Value < -.02 {
		t.Fatalf("crit split score %.8g, continuous %.8g, rolls %v, stop %s; expected near exact quarter target",
			result.Value, result.ContinuousValue, result.State.Rolls()[0], result.Stop)
	}
}

func TestLinearTinyQuarterDomainExact(t *testing.T) {
	var weights [4][10]float64
	for stat := range weights[0] {
		weights[0][stat] = -1
	}
	weights[0][2], weights[0][3], weights[0][1] = 4, 5, 3
	state := Seed(testMains(), weights, 0, 20)
	obj := linearObjective(weights)
	best := math.Inf(-1)
	for first := -1; first < 20; first++ {
		for second := -1; second < 20; second++ {
			candidate := state
			for _, index := range [2]int{first, second} {
				if index >= 0 {
					candidate.Upgrades[0][index/4][index%4] += .25
				}
			}
			if candidate.Validate(20.5, true) != nil {
				continue
			}
			value, _, _ := obj(candidate, false)
			best = math.Max(best, value)
		}
	}
	for _, method := range []string{"fixed", "spg"} {
		result, err := Optimize(obj, state, Config{Budget: 20.5, Method: method, MaxIterations: 20, LineSearch: true, Polish: true})
		if err != nil {
			t.Fatal(err)
		}
		if err := result.State.Validate(20.5, true); err != nil {
			t.Fatal(err)
		}
		if math.Abs(result.Value-best) > 1e-8 {
			t.Fatalf("%s score %.12g; exhaustive quarter-domain best %.12g", method, result.Value, best)
		}
	}
}

func TestBudget30LinearAndUnprofitableUpgrades(t *testing.T) {
	var positive [4][10]float64
	positive[0][2] = 3
	state := Seed(testMains(), positive, 0, 20)
	base, _, _ := linearObjective(positive)(state, false)
	for _, method := range []string{"fixed", "spg"} {
		result, err := Optimize(linearObjective(positive), state, Config{Budget: 30, Method: method, MaxIterations: 20, LineSearch: true})
		if err != nil {
			t.Fatal(err)
		}
		if math.Abs(result.Value-(base+30)) > 1e-8 {
			t.Fatalf("%s score %.12g; want %.12g", method, result.Value, base+30)
		}
		if err := result.State.Validate(30, true); err != nil {
			t.Fatal(err)
		}
	}
	var negative [4][10]float64
	for actor := range negative {
		for stat := range negative[actor] {
			negative[actor][stat] = -1
		}
	}
	state = Seed(testMains(), negative, 0, 30)
	result, err := Optimize(linearObjective(negative), state, Config{Budget: 30, Method: "spg", MaxIterations: 20, LineSearch: true})
	if err != nil {
		t.Fatal(err)
	}
	for actor := range result.State.Upgrades {
		for slot := range result.State.Upgrades[actor] {
			for line, u := range result.State.Upgrades[actor][slot] {
				if u != 0 {
					t.Fatalf("unprofitable upgrade retained at (%d,%d,%d): %g", actor, slot, line, u)
				}
			}
		}
	}
}

func TestLateRoundingPreservesBetterQuarterInput(t *testing.T) {
	var seedGradient [4][10]float64
	seedGradient[0][3] = 1
	state := Seed(testMains(), seedGradient, 0, 20)
	for line, stat := range state.Lines[0][0] {
		if stat == 3 {
			state.Upgrades[0][0][line] = .25
			break
		}
	}
	if err := state.Validate(30, true); err != nil {
		t.Fatal(err)
	}
	obj := func(s State, needGradient bool) (float64, [4][10]float64, error) {
		extraRate := s.Rolls()[0][3] - 4
		delta := extraRate - .42
		curvature := 1.0
		if delta > 0 {
			curvature = 100
		}
		var gradient [4][10]float64
		gradient[0][3] = -2 * curvature * delta
		return -curvature * delta * delta, gradient, nil
	}
	before, _, _ := obj(state, false)
	result, err := Optimize(obj, state, Config{Budget: 30, Method: "spg", MaxIterations: 40, LineSearch: true})
	if err != nil {
		t.Fatal(err)
	}
	if result.Value < before-1e-12 {
		t.Fatalf("late rounding lost warm incumbent: before %g after %g", before, result.Value)
	}
	if result.ContinuousValue <= before+1e-4 {
		t.Fatalf("continuous step did not exercise better off-grid point: %g vs %g", result.ContinuousValue, before)
	}
	if result.State != state {
		t.Fatalf("expected better quarter input to survive late rounding")
	}
}

func TestImproveLinesChecksActualEligibleReplacement(t *testing.T) {
	var weights [4][10]float64
	weights[0][2] = 10
	state := Seed(testMains(), [4][10]float64{}, 0, 20)
	// Remove crit damage from the first slot and replace it by an unused stat.
	for line, stat := range state.Lines[0][0] {
		if stat == 2 {
			state.Lines[0][0][line] = 9
			break
		}
	}
	if err := state.Validate(20, true); err != nil {
		t.Fatal(err)
	}
	base, _, _ := linearObjective(weights)(state, false)
	result, err := ImproveLines(linearObjective(weights), state, Config{Budget: 20, Method: "spg", MaxIterations: 8})
	if err != nil {
		t.Fatal(err)
	}
	if result.Value < base+10-1e-8 {
		t.Fatalf("missing profitable line replacement: %g to %g", base, result.Value)
	}
	if result.Iterations < 1 || result.Iterations > 12 || result.Evaluations <= 1 {
		t.Fatalf("unexpected search accounting: %+v", result)
	}
	if err := result.State.Validate(20, true); err != nil {
		t.Fatal(err)
	}
}
