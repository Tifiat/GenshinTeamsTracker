package theoryprototype

import (
	"math"
	"testing"
	"time"
)

// These oracles deliberately have only one changing actor and at most two
// quarter upgrades. The remaining actors retain mandatory four-line pieces.
// They test neighborhood decisions, not full-account artifact optimality.
func tinyQuarterOracle(t *testing.T, obj Objective, layouts []State) float64 {
	t.Helper()
	best := math.Inf(-1)
	for _, layout := range layouts {
		for first := -1; first < 20; first++ {
			for second := -1; second < 20; second++ {
				candidate := layout
				for _, coordinate := range [2]int{first, second} {
					if coordinate >= 0 {
						candidate.Upgrades[0][coordinate/4][coordinate%4] += .25
					}
				}
				if candidate.Validate(20.5, true) != nil {
					continue
				}
				value, _, err := obj(candidate, false)
				if err != nil {
					t.Fatal(err)
				}
				best = math.Max(best, value)
			}
		}
	}
	return best
}

func TestJointMainReoptimizesBeforeComparing(t *testing.T) {
	started := time.Now()
	mains := testMains()
	mains[0][3] = "hydro_damage_bonus"
	var seedGradient [4][10]float64
	seedGradient[0][7] = 1 // energy recharge is a line, not a character rule.
	start := Seed(mains, seedGradient, 0, 20)
	baseRecharge := start.Rolls()[0][7]
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		var gradient [4][10]float64
		if state.Mains[0][3] != "pyro_damage_bonus" {
			return 0, gradient, nil
		}
		extra := state.Rolls()[0][7] - baseRecharge
		if extra < 0 {
			gradient[0][7] = 1
			return -.1 + extra, gradient, nil
		}
		gradient[0][7] = 1 + 2*extra
		return -.1 + extra + extra*extra, gradient, nil
	}
	changed := ReplaceMain(start, 0, 3, "pyro_damage_bonus", [4][10]float64{}, 20.5)
	direct, _, _ := obj(changed, false)
	if direct >= 0 {
		t.Fatalf("toy main must look worse before upgrades: %g", direct)
	}
	oracle := tinyQuarterOracle(t, obj, []State{start, changed})
	result, err := JointOptimize(obj, start, Config{Budget: 20.5, Method: "spg", LineSearch: true}, JointConfig{
		Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 12,
		DisableMainPairs: true, DisableLines: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := result.State.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	if math.Abs(result.Value-oracle) > 1e-8 || result.State.Mains[0][3] != "pyro_damage_bonus" {
		t.Fatalf("reoptimized main %.9g, oracle %.9g, main %q", result.Value, oracle, result.State.Mains[0][3])
	}
	if result.AcceptedSingleMains != 1 || result.SingleMainCandidates < 11 || result.OptimizeCalls <= result.SingleMainCandidates {
		t.Fatalf("missing whole-layout comparisons: %+v", result)
	}
	marginalReceipt(t, map[string]any{
		"case": "joint_main_reoptimization", "direct": direct,
		"value": result.Value, "oracle": oracle,
		"objective_evaluations":  result.Evaluations,
		"optimize_calls":         result.OptimizeCalls,
		"single_main_candidates": result.SingleMainCandidates,
		"nanoseconds":            time.Since(started).Nanoseconds(),
	})
}

func TestJointGobletCircletCrossesTwoMainBarrier(t *testing.T) {
	started := time.Now()
	mains := testMains()
	mains[0][3] = "hydro_damage_bonus"
	start := Seed(mains, [4][10]float64{}, 0, 20)
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		goblet := state.Mains[0][3] == "pyro_damage_bonus"
		circlet := state.Mains[0][4] == "crit_damage"
		switch {
		case goblet && circlet:
			return 5, [4][10]float64{}, nil
		case goblet || circlet:
			return -1, [4][10]float64{}, nil
		default:
			return 0, [4][10]float64{}, nil
		}
	}
	maxFour := math.Inf(-1)
	for _, goblet := range []string{"hydro_damage_bonus", "pyro_damage_bonus"} {
		for _, circlet := range []string{"crit_rate", "crit_damage"} {
			candidate := ReplaceMain(start, 0, 3, goblet, [4][10]float64{}, 20)
			candidate = ReplaceMain(candidate, 0, 4, circlet, [4][10]float64{}, 20)
			if err := candidate.Validate(20, true); err != nil {
				t.Fatal(err)
			}
			value, _, _ := obj(candidate, false)
			maxFour = math.Max(maxFour, value)
		}
	}
	result, err := JointOptimize(obj, start, Config{Budget: 20, Method: "spg", LineSearch: true}, JointConfig{
		Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 4, DisableLines: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Value != maxFour || result.AcceptedMainPairs != 1 {
		t.Fatalf("two-main barrier result %+v; four-layout oracle %g", result, maxFour)
	}
	if err := result.State.Validate(20, true); err != nil {
		t.Fatal(err)
	}
	// A deliberately truncated pair neighborhood must report its uncertainty.
	limited, err := JointOptimize(obj, start, Config{Budget: 20, Method: "spg", LineSearch: true}, JointConfig{
		Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 4,
		DisableIndependentSeeds: true, DisableSingleMains: true, DisableLines: true,
		MaxMainPairs: 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	if limited.Stop != "candidate_cap" || limited.MainPairEligible != 66 || limited.JointMainCandidates != 1 || limited.TruncatedMainPairs != 65 {
		t.Fatalf("pair cap was not explicit: %+v", limited)
	}
	marginalReceipt(t, map[string]any{
		"case": "joint_two_main_barrier", "value": result.Value,
		"four_layout_oracle":      maxFour,
		"objective_evaluations":   result.Evaluations,
		"pair_candidates":         result.JointMainCandidates,
		"limited_pair_candidates": limited.JointMainCandidates,
		"limited_eligible":        limited.MainPairEligible,
		"nanoseconds":             time.Since(started).Nanoseconds(),
	})
}

func TestJointLineReplacementScoresAfterUpgrades(t *testing.T) {
	started := time.Now()
	start := Seed(testMains(), [4][10]float64{}, 0, 20)
	for slot := range start.Lines[0] {
		for _, stat := range start.Lines[0][slot] {
			if stat == 9 {
				t.Fatal("toy target must be absent from every starting line")
			}
		}
	}
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		x := state.Rolls()[0][9]
		var gradient [4][10]float64
		gradient[0][9] = -3 + 4.4*x
		return -3*x + 2.2*x*x, gradient, nil
	}
	cfg := Config{Budget: 20.5, Method: "spg", LineSearch: true}
	old, err := ImproveLines(obj, start, cfg)
	if err != nil {
		t.Fatal(err)
	}
	if old.Value != 0 || old.Iterations != 0 {
		t.Fatalf("direct-only baseline unexpectedly crossed line barrier: %+v", old)
	}
	layouts := []State{start}
	for slot := range start.Lines[0] {
		for line := range start.Lines[0][slot] {
			candidate := start
			candidate.Lines[0][slot][line] = 9
			if candidate.Validate(20.5, true) == nil {
				layouts = append(layouts, candidate)
			}
		}
	}
	oracle := tinyQuarterOracle(t, obj, layouts)
	result, err := JointOptimize(obj, start, cfg, JointConfig{
		Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 8,
		DisableIndependentSeeds: true, DisableSingleMains: true, DisableMainPairs: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(result.Value-oracle) > 1e-8 || result.AcceptedLines != 1 || result.LineCandidates == 0 {
		t.Fatalf("delayed line score %.9g, oracle %.9g, stats %+v", result.Value, oracle, result)
	}
	if err := result.State.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	marginalReceipt(t, map[string]any{
		"case": "joint_delayed_line_replacement", "old_value": old.Value,
		"value": result.Value, "oracle": oracle,
		"objective_evaluations": result.Evaluations,
		"line_candidates":       result.LineCandidates,
		"nanoseconds":           time.Since(started).Nanoseconds(),
	})
}

func TestComplementaryFixedBonusesRequireOuterPairEnumeration(t *testing.T) {
	var seedGradient [4][10]float64
	seedGradient[0][7] = 1
	start := Seed(testMains(), seedGradient, 0, 20)
	baseRecharge := start.Rolls()[0][7]
	var scores [4]float64
	// The outer four-mask domain represents none, each singleton, and both
	// complementary fixed bonuses. JointOptimize never selects set packages.
	for mask := 0; mask < 4; mask++ {
		bonus := 0.0
		if mask == 1 || mask == 2 {
			bonus = -.2
		}
		if mask == 3 {
			bonus = 1
		}
		obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
			var gradient [4][10]float64
			if mask != 3 {
				return bonus, gradient, nil
			}
			extra := state.Rolls()[0][7] - baseRecharge
			gradient[0][7] = 1 + 2*extra
			return bonus + extra + extra*extra, gradient, nil
		}
		result, err := JointOptimize(obj, start, Config{Budget: 20.5, Method: "spg", LineSearch: true}, JointConfig{
			Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 8,
			DisableIndependentSeeds: true, DisableSingleMains: true,
			DisableMainPairs: true, DisableLines: true,
		})
		if err != nil {
			t.Fatal(err)
		}
		scores[mask] = result.Value
	}
	if scores[1] >= scores[0] || scores[2] >= scores[0] || scores[3] <= scores[0] {
		t.Fatalf("complementary pair was hidden by both singleton comparisons: %v", scores)
	}
}

func TestOuterSetChoiceNeedsMainAndUpgradeReoptimization(t *testing.T) {
	started := time.Now()
	mains := testMains()
	mains[0][3] = "hydro_damage_bonus"
	var seedGradient [4][10]float64
	seedGradient[0][7] = 1
	start := Seed(mains, seedGradient, 0, 20)
	baseRecharge := start.Rolls()[0][7]
	packages := [2]Objective{
		func(state State, needGradient bool) (float64, [4][10]float64, error) {
			return 0, [4][10]float64{}, nil
		},
		func(state State, needGradient bool) (float64, [4][10]float64, error) {
			var gradient [4][10]float64
			if state.Mains[0][3] != "pyro_damage_bonus" {
				return -.2, gradient, nil
			}
			x := state.Rolls()[0][7] - baseRecharge
			gradient[0][7] = 1 + 2*x
			return -.1 + x + x*x, gradient, nil
		},
	}
	cfg := Config{Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true}
	var anchor [2]float64
	var joint [2]JointResult
	anchorEvaluations := 0
	for packageID, obj := range packages {
		fixedMain, err := Optimize(obj, start, cfg)
		if err != nil {
			t.Fatal(err)
		}
		anchor[packageID] = fixedMain.Value
		anchorEvaluations += fixedMain.Evaluations
		joint[packageID], err = JointOptimize(obj, start, cfg, JointConfig{
			Actors: [4]bool{true}, MaxPasses: 1, InnerIterations: 8,
			DisableIndependentSeeds: true, DisableMainPairs: true, DisableLines: true,
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	// Exact oracle only for these four package/main combinations and q=0,.25,.5
	// upgrade units on an existing energy-recharge line. The outer package
	// choice is separate from JointOptimize's fixed-bonus inner search.
	oracleValue, oraclePackage := math.Inf(-1), -1
	for packageID, obj := range packages {
		for _, main := range []string{"hydro_damage_bonus", "pyro_damage_bonus"} {
			layout := ReplaceMain(start, 0, 3, main, seedGradient, 20.5)
			slot, line, found := firstLineWithStat(layout, 0, 7)
			if !found {
				t.Fatal("oracle layout lacks recharge line")
			}
			for quarter := 0; quarter <= 2; quarter++ {
				candidate := layout
				candidate.Upgrades[0][slot][line] = float64(quarter) / 4
				if err := candidate.Validate(20.5, true); err != nil {
					t.Fatal(err)
				}
				value, _, err := obj(candidate, false)
				if err != nil {
					t.Fatal(err)
				}
				if value > oracleValue {
					oracleValue, oraclePackage = value, packageID
				}
			}
		}
	}
	if anchor[0] <= anchor[1] || joint[1].Value <= joint[0].Value ||
		joint[1].State.Mains[0][3] != "pyro_damage_bonus" ||
		math.Abs(joint[1].Value-oracleValue) > 1e-10 || oraclePackage != 1 {
		t.Fatalf("hidden package/main pair: anchor %v, joint A %g B %g, oracle %g package %d", anchor, joint[0].Value, joint[1].Value, oracleValue, oraclePackage)
	}
	marginalReceipt(t, map[string]any{
		"case": "outer_set_main_bonus", "anchor_scores": anchor,
		"joint_scores":    [2]float64{joint[0].Value, joint[1].Value},
		"winning_package": oraclePackage, "oracle_value": oracleValue,
		"anchor_evaluations": anchorEvaluations,
		"joint_evaluations":  joint[0].Evaluations + joint[1].Evaluations,
		"oracle_evaluations": 12, "nanoseconds": time.Since(started).Nanoseconds(),
	})
}
