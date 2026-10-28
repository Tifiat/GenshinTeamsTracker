package theoryprototype

import (
	"math"
	"testing"
	"time"
)

func TestFastWholeFindsHiddenSetMainCombination(t *testing.T) {
	started := time.Now()
	mains := testMains()
	mains[0][3] = "hydro_damage_bonus"
	var gradient [4][10]float64
	gradient[0][7] = 1
	start := Seed(mains, gradient, 0, 20)
	baseRecharge := start.Rolls()[0][7]
	objectives := [2]Objective{
		func(State, bool) (float64, [4][10]float64, error) {
			return 0, [4][10]float64{}, nil
		},
		func(state State, needGradient bool) (float64, [4][10]float64, error) {
			var g [4][10]float64
			if state.Mains[0][3] != "pyro_damage_bonus" {
				return -.2, g, nil
			}
			x := state.Rolls()[0][7] - baseRecharge
			g[0][7] = 1 + 2*x
			return -.1 + x + x*x, g, nil
		},
	}
	cfg := Config{Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true}
	var anchor [2]float64
	var solved [2]FastResult
	for packageID, obj := range objectives {
		fixed, err := Optimize(obj, start, cfg)
		if err != nil {
			t.Fatal(err)
		}
		anchor[packageID] = fixed.Value
		solved[packageID], err = FastWhole(obj, start, cfg, FastConfig{Passes: 1, InnerIterations: 8})
		if err != nil {
			t.Fatal(err)
		}
		if err := solved[packageID].State.Validate(20.5, true); err != nil {
			t.Fatal(err)
		}
	}
	oracle := math.Inf(-1)
	for _, obj := range objectives {
		for _, main := range []string{"hydro_damage_bonus", "pyro_damage_bonus"} {
			layout := ReplaceMain(start, 0, 3, main, gradient, 20.5)
			slot, line, found := firstLineWithStat(layout, 0, 7)
			if !found {
				t.Fatal("oracle recharge line absent")
			}
			for q := 0; q <= 2; q++ {
				candidate := layout
				candidate.Upgrades[0][slot][line] = float64(q) / 4
				value, _, err := obj(candidate, false)
				if err != nil {
					t.Fatal(err)
				}
				if value > oracle {
					oracle = value
				}
			}
		}
	}
	if anchor[0] <= anchor[1] || solved[1].Value <= solved[0].Value ||
		math.Abs(solved[1].Value-oracle) > 1e-10 ||
		solved[1].State.Mains[0][3] != "pyro_damage_bonus" {
		t.Fatalf("fast set/main score: anchor %v, solved %g/%g, oracle %g", anchor, solved[0].Value, solved[1].Value, oracle)
	}
	marginalReceipt(t, map[string]any{
		"case": "fast_hidden_set_main", "anchor": anchor,
		"fast_values": [2]float64{solved[0].Value, solved[1].Value},
		"oracle":      oracle, "oracle_evaluations": 12,
		"fast_evaluations":    solved[0].Evaluations + solved[1].Evaluations,
		"fast_optimize_calls": solved[0].OptimizeCalls + solved[1].OptimizeCalls,
		"nanoseconds":         time.Since(started).Nanoseconds(),
	})
}

func TestFastWholeReoptimizesDelayedLine(t *testing.T) {
	started := time.Now()
	start := Seed(testMains(), [4][10]float64{}, 0, 20)
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		x := state.Rolls()[0][9]
		var g [4][10]float64
		g[0][9] = -3 + 4.4*x
		return -3*x + 2.2*x*x, g, nil
	}
	oracle := 0.0
	for slot := range start.Lines[0] {
		for line := range start.Lines[0][slot] {
			layout := start
			layout.Lines[0][slot][line] = 9
			if layout.Validate(20.5, true) != nil {
				continue
			}
			for q := 0; q <= 2; q++ {
				candidate := layout
				candidate.Upgrades[0][slot][line] = float64(q) / 4
				value, _, err := obj(candidate, false)
				if err != nil {
					t.Fatal(err)
				}
				oracle = math.Max(oracle, value)
			}
		}
	}
	r, err := FastWhole(obj, start, Config{
		Budget: 20.5, Method: "spg", MaxIterations: 8, LineSearch: true,
	}, FastConfig{Passes: 1, InnerIterations: 8, LinePasses: 1})
	if err != nil {
		t.Fatal(err)
	}
	if err := r.State.Validate(20.5, true); err != nil {
		t.Fatal(err)
	}
	if math.Abs(r.Value-oracle) > 1e-10 || r.AcceptedLines != 1 {
		t.Fatalf("fast delayed line result %+v, oracle %g", r, oracle)
	}
	marginalReceipt(t, map[string]any{
		"case": "fast_delayed_line", "value": r.Value, "oracle": oracle,
		"line_candidates": r.LineCandidates, "evaluations": r.Evaluations,
		"optimize_calls": r.OptimizeCalls,
		"nanoseconds":    time.Since(started).Nanoseconds(),
	})
}

func TestFastWholeOptionalPairedMains(t *testing.T) {
	started := time.Now()
	mains := testMains()
	mains[0][3] = "hydro_damage_bonus"
	start := Seed(mains, [4][10]float64{}, 0, 20)
	obj := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		goblet := state.Mains[0][3] == "pyro_damage_bonus"
		circlet := state.Mains[0][4] == "crit_damage"
		if goblet && circlet {
			return 5, [4][10]float64{}, nil
		}
		if goblet || circlet {
			return -1, [4][10]float64{}, nil
		}
		return 0, [4][10]float64{}, nil
	}
	cfg := Config{Budget: 20, Method: "spg", MaxIterations: 4, LineSearch: true}
	without, err := FastWhole(obj, start, cfg, FastConfig{Passes: 1, InnerIterations: 4})
	if err != nil {
		t.Fatal(err)
	}
	with, err := FastWhole(obj, start, cfg, FastConfig{Passes: 1, InnerIterations: 4, MainPairs: true})
	if err != nil {
		t.Fatal(err)
	}
	if without.Value != 0 || with.Value != 5 || with.AcceptedMainPairs != 1 ||
		with.State.Mains[0][3] != "pyro_damage_bonus" || with.State.Mains[0][4] != "crit_damage" {
		t.Fatalf("fast paired-main barrier: without %+v, with %+v", without, with)
	}
	marginalReceipt(t, map[string]any{
		"case": "fast_optional_main_pairs", "without_pairs": without.Value,
		"with_pairs": with.Value, "four_layout_oracle": 5,
		"pair_candidates":     with.PairCandidates,
		"evaluations_without": without.Evaluations, "evaluations_with": with.Evaluations,
		"nanoseconds": time.Since(started).Nanoseconds(),
	})
}

func TestFastWholePreservesUnimprovedQuarterInput(t *testing.T) {
	start := Seed(testMains(), [4][10]float64{}, 0, 20)
	start.Upgrades[0][0][0] = .25
	obj := func(State, bool) (float64, [4][10]float64, error) {
		return 7, [4][10]float64{}, nil
	}
	r, err := FastWhole(obj, start, Config{
		Budget: 20.25, Method: "spg", MaxIterations: 4, LineSearch: true,
	}, FastConfig{Passes: 1, InnerIterations: 4})
	if err != nil {
		t.Fatal(err)
	}
	if r.State != start || r.Value != 7 {
		t.Fatalf("valid warm incumbent was lost: %+v", r)
	}
}
