package theoryalloc_test

import (
	"math"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

func witnessMains() [4][5]string {
	return [4][5]string{
		{"hp", "atk", "em", "pyro_damage_bonus", "crit_rate"},
		{"hp", "atk", "atk_percent", "hydro_damage_bonus", "crit_damage"},
		{"hp", "atk", "energy_recharge", "electro_damage_bonus", "healing_bonus"},
		{"hp", "atk", "hp_percent", "physical_damage_bonus", "def_percent"},
	}
}

func positiveGradient() [4][10]float64 {
	var gradient [4][10]float64
	for actor := range gradient {
		for stat := range gradient[actor] {
			gradient[actor][stat] = float64(stat + 1)
		}
	}
	return gradient
}

func TestSeedFull45WitnessesRetainTwentyInitialAndTwentyFiveUpgradeUnits(t *testing.T) {
	keys := theoryalloc.StatKeys()
	for _, variant := range []int{0, 1} {
		state := theoryalloc.Seed(witnessMains(), positiveGradient(), variant, 45)
		if err := theoryalloc.ValidateFull45(state); err != nil {
			t.Fatalf("variant %d: %v", variant, err)
		}
		rolls := state.Rolls()
		for actor := range state.Lines {
			initial, upgrades, total := 0, 0.0, 0.0
			for slot, lines := range state.Lines[actor] {
				seen := map[int]bool{}
				for line, stat := range lines {
					if seen[stat] || keys[stat] == state.Mains[actor][slot] {
						t.Fatalf("variant %d actor %d slot %d has illegal initial lines", variant, actor, slot)
					}
					seen[stat] = true
					initial++
					upgrades += state.Upgrades[actor][slot][line]
				}
			}
			for _, amount := range rolls[actor] {
				total += amount
			}
			if initial != 20 || upgrades != 25 || total != 45 {
				t.Fatalf("variant %d actor %d: initial %d upgrades %g total %g", variant, actor, initial, upgrades, total)
			}
		}
	}
}

func TestPublicationRejectsMissingUpgradesWhileSolverBudgetRemainsAnUpperBound(t *testing.T) {
	state := theoryalloc.Seed(witnessMains(), positiveGradient(), 0, 45)
	state.Upgrades[2][3][1] -= .25
	if err := state.Validate(45, true); err != nil {
		t.Fatalf("valid underfilled solver witness was rejected: %v", err)
	}
	if err := theoryalloc.ValidateFull45(state); err == nil || !strings.Contains(err.Error(), "actor 2") {
		t.Fatalf("underfilled actor was accepted for publication: %v", err)
	}
	initialOnly := theoryalloc.Seed(witnessMains(), positiveGradient(), 0, 20)
	if err := initialOnly.Validate(45, true); err != nil {
		t.Fatalf("unused upgrade budget must remain legal: %v", err)
	}
	if err := theoryalloc.ValidateFull45(initialOnly); err == nil {
		t.Fatal("initial-only witness was accepted for publication")
	}
}

func TestValidationRejectsIllegalSlotAndUpgradeWitnesses(t *testing.T) {
	base := theoryalloc.Seed(witnessMains(), positiveGradient(), 0, 45)
	cases := []struct {
		name   string
		mutate func(*theoryalloc.State)
		budget float64
		want   string
	}{
		{"duplicate_line", func(s *theoryalloc.State) { s.Lines[0][0][1] = s.Lines[0][0][0] }, 45, "duplicate or main-matching"},
		{"main_collision", func(s *theoryalloc.State) { s.Lines[0][0][0] = 8 }, 45, "duplicate or main-matching"},
		{"illegal_main", func(s *theoryalloc.State) { s.Mains[0][0] = "atk" }, 45, "illegal main"},
		{"missing_initial_line", func(s *theoryalloc.State) { s.Lines[1][2][3] = -1 }, 45, "invalid stat index"},
		{"unknown_line", func(s *theoryalloc.State) { s.Lines[1][2][3] = 10 }, 45, "invalid stat index"},
		{"negative_upgrade", func(s *theoryalloc.State) { s.Upgrades[1][2][3] = -.25 }, 45, "invalid upgrade"},
		{"missing_upgrade_value", func(s *theoryalloc.State) { s.Upgrades[1][2][3] = math.NaN() }, 45, "invalid upgrade"},
		{"infinite_upgrade", func(s *theoryalloc.State) { s.Upgrades[1][2][3] = math.Inf(1) }, 45, "invalid upgrade"},
		{"off_quarter_grid", func(s *theoryalloc.State) { s.Upgrades[1][2][3] = .1 }, 45, "off the quarter grid"},
		{"slot_overflow", func(s *theoryalloc.State) { s.Upgrades[1][2][3] += .25 }, 45, "exceeds five upgrades"},
		{"actor_budget_overflow", func(*theoryalloc.State) {}, 44.75, "exceeds budget"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			candidate := base
			tc.mutate(&candidate)
			err := candidate.Validate(tc.budget, true)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("Validate returned %v; want %q", err, tc.want)
			}
			if err := theoryalloc.ValidateFull45(candidate); tc.budget == 45 && err == nil {
				t.Fatal("illegal solver witness was accepted for publication")
			}
		})
	}
}

func TestRuleAccessorsPreservePinnedValuesAndCannotMutateAllocatorRules(t *testing.T) {
	wantKeys := [10]string{"atk", "atk_percent", "crit_damage", "crit_rate", "def", "def_percent", "em", "energy_recharge", "hp", "hp_percent"}
	wantValues := [10]float64{19.45, .0583, .0777, .0389, 23.15, .0729, 23.31, .0648, 298.75, .0583}
	wantMains := map[string]float64{
		"hp": 4780, "atk": 311, "hp_percent": .466, "atk_percent": .466,
		"def_percent": .583, "em": 186.5, "energy_recharge": .518,
		"crit_rate": .311, "crit_damage": .622, "pyro_damage_bonus": .466,
		"hydro_damage_bonus": .466, "electro_damage_bonus": .466,
		"cryo_damage_bonus": .466, "anemo_damage_bonus": .466,
		"geo_damage_bonus": .466, "dendro_damage_bonus": .466,
		"physical_damage_bonus": .583, "healing_bonus": .359,
	}
	keys, values := theoryalloc.StatKeys(), theoryalloc.StatValues()
	mains, choices := theoryalloc.MainValues(), theoryalloc.MainChoices()
	if keys != wantKeys || values != wantValues || !reflect.DeepEqual(mains, wantMains) {
		t.Fatal("pinned coordinate order or numeric rule values changed")
	}
	wantChoices := [5][]string{
		{"hp"}, {"atk"},
		{"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
		{"anemo_damage_bonus", "atk_percent", "cryo_damage_bonus", "def_percent", "dendro_damage_bonus", "electro_damage_bonus", "em", "geo_damage_bonus", "hp_percent", "hydro_damage_bonus", "physical_damage_bonus", "pyro_damage_bonus"},
		{"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
	}
	if !reflect.DeepEqual(choices, wantChoices) {
		t.Fatal("pinned main choices or their traversal order changed")
	}
	keys[0], values[0] = "other", -1
	mains["hp"] = -1
	delete(mains, "atk")
	choices[0][0] = "atk"
	choices[3][0] = "other"
	if theoryalloc.StatKeys() != wantKeys || theoryalloc.StatValues() != wantValues ||
		!reflect.DeepEqual(theoryalloc.MainValues(), wantMains) || !reflect.DeepEqual(theoryalloc.MainChoices(), wantChoices) {
		t.Fatal("consumer mutation changed allocator rules")
	}
	if err := theoryalloc.ValidateFull45(theoryalloc.Seed(witnessMains(), positiveGradient(), 0, 45)); err != nil {
		t.Fatalf("consumer mutation affected a legal witness: %v", err)
	}
}

func TestExtractedLinearAllocationMatchesFullBudgetOracle(t *testing.T) {
	var mains [4][5]string
	for actor := range mains {
		mains[actor] = [5]string{"hp", "atk", "atk_percent", "pyro_damage_bonus", "crit_rate"}
	}
	weights := positiveGradient()
	start := theoryalloc.Seed(mains, weights, 0, 20)
	// The pinned seed has [9,7,6,5] on flower and [9,8,7,6] elsewhere.
	// Its weighted base is 167 per actor. Stat 9 appears in all five slots,
	// so all 25 upgrades can reach weight 10: the independent maximum is 417.
	want := start
	for actor := range want.Upgrades {
		for slot := range want.Upgrades[actor] {
			want.Upgrades[actor][slot][0] = 5
		}
	}
	wantRolls := [10]float64{0, 0, 0, 0, 0, 1, 5, 5, 4, 30}
	objective := func(state theoryalloc.State, _ bool) (float64, [4][10]float64, error) {
		value := 0.0
		for actor, rolls := range state.Rolls() {
			for stat, amount := range rolls {
				value += weights[actor][stat] * amount
			}
		}
		return value, weights, nil
	}
	for _, method := range []string{"fixed", "spg"} {
		t.Run(method, func(t *testing.T) {
			result, err := theoryalloc.Optimize(objective, start, theoryalloc.Config{
				Budget: 45, Method: method, MaxIterations: 80, LineSearch: true, Polish: true,
			})
			if err != nil {
				t.Fatal(err)
			}
			if err := theoryalloc.ValidateFull45(result.State); err != nil {
				t.Fatal(err)
			}
			if result.State != want || result.Value != 4*417 {
				t.Fatalf("full-budget allocation differs from oracle: value %g, state %+v", result.Value, result.State)
			}
			for actor, rolls := range result.State.Rolls() {
				if rolls != wantRolls {
					t.Fatalf("actor %d rolls %v; want %v", actor, rolls, wantRolls)
				}
			}
		})
	}
}
