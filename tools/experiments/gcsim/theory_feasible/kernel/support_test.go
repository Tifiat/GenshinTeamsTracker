package theoryprototype

import (
	"math"
	"testing"
	"time"
)

func supportMask(stats ...int) uint16 {
	var mask uint16
	for _, stat := range stats {
		mask |= uint16(1) << stat
	}
	return mask
}

// The other actor-zero slots have fixed zero-weight lines, so the independent
// oracle below only has to enumerate the named slot. Other actors have no
// weights and can retain any legal witness.
func supportSingleSlotFixture(target int, restriction SlotDomain) (SupportDomain, State) {
	domain := SupportDomain{}
	state := Seed(testMains(), [4][10]float64{}, 0, 20)
	fixedMains := [5]string{"hp", "atk", "def_percent", "pyro_damage_bonus", "healing_bonus"}
	fixedLines := [5][4]int{
		{0, 4, 6, 9}, {4, 6, 8, 9}, {0, 4, 6, 8},
		{0, 4, 6, 8}, {0, 4, 6, 8},
	}
	for slot := 0; slot < 5; slot++ {
		if slot == target {
			continue
		}
		domain[0][slot] = SlotDomain{Mains: []string{fixedMains[slot]}, Required: supportMask(fixedLines[slot][:]...)}
		state.Mains[0][slot] = fixedMains[slot]
		state.Lines[0][slot] = fixedLines[slot]
	}
	domain[0][target] = restriction
	return domain, state
}

func supportOracleValue(state State, weights LinearWeights) float64 {
	value := 0.0
	rolls := state.Rolls()
	for actor := range state.Mains {
		for _, main := range state.Mains[actor] {
			value += weights[actor][main] * MainValues[main]
		}
		for stat, key := range StatKeys {
			value += weights[actor][key] * rolls[actor][stat] * Values[stat]
		}
	}
	return value
}

func exhaustiveSupportSlot(t *testing.T, weights LinearWeights, domain SupportDomain, seed State, target int) (lo, hi float64, count int) {
	t.Helper()
	lo, hi = math.Inf(1), math.Inf(-1)
	d := domain[0][target]
	mains := d.Mains
	if mains == nil {
		mains = MainChoices[target]
	}
	for _, main := range mains {
		eligible := []int{}
		for stat, key := range StatKeys {
			if key != main && d.Excluded&(uint16(1)<<stat) == 0 {
				eligible = append(eligible, stat)
			}
		}
		for i := 0; i < len(eligible); i++ {
			for j := i + 1; j < len(eligible); j++ {
				for k := j + 1; k < len(eligible); k++ {
					for l := k + 1; l < len(eligible); l++ {
						lines := [4]int{eligible[i], eligible[j], eligible[k], eligible[l]}
						if supportMask(lines[:]...)&d.Required != d.Required {
							continue
						}
						for vertex := -1; vertex < 4; vertex++ {
							candidate := seed
							candidate.Mains[0][target] = main
							candidate.Lines[0][target] = lines
							candidate.Upgrades[0][target] = [4]float64{}
							if vertex >= 0 {
								candidate.Upgrades[0][target][vertex] = 5
							}
							if err := candidate.Validate(45, true); err != nil {
								t.Fatal(err)
							}
							v := supportOracleValue(candidate, weights)
							lo, hi = math.Min(lo, v), math.Max(hi, v)
							count++
						}
					}
				}
			}
		}
	}
	return lo, hi, count
}

func assertSupportWitness(t *testing.T, weights LinearWeights, domain SupportDomain, maximize bool, expected float64) {
	t.Helper()
	state, value, err := SupportWitness45(weights, domain, maximize)
	if err != nil {
		t.Fatal(err)
	}
	if err := state.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	for actor := range domain {
		for slot, restriction := range domain[actor] {
			if restriction.Mains != nil {
				found := false
				for _, main := range restriction.Mains {
					found = found || state.Mains[actor][slot] == main
				}
				if !found {
					t.Fatalf("actor %d slot %d has unlisted main", actor, slot)
				}
			}
			mask := uint16(0)
			for _, stat := range state.Lines[actor][slot] {
				mask |= uint16(1) << stat
			}
			if mask&restriction.Required != restriction.Required || mask&restriction.Excluded != 0 {
				t.Fatalf("actor %d slot %d violated line mask", actor, slot)
			}
		}
	}
	if math.Abs(value-expected) > 1e-9*(1+math.Abs(expected)) ||
		math.Abs(value-supportOracleValue(state, weights)) > 1e-9*(1+math.Abs(value)) {
		t.Fatalf("support witness %.12g, oracle %.12g", value, expected)
	}
}

func TestSupport45MatchesExhaustiveSignedSingleSlotUnions(t *testing.T) {
	started := time.Now()
	cases := []struct {
		name        string
		slot        int
		restriction SlotDomain
		weights     LinearWeights
	}{
		{
			name: "flower_required_excluded", slot: 0,
			restriction: SlotDomain{Mains: []string{"hp"}, Required: supportMask(2), Excluded: supportMask(7)},
			weights:     LinearWeights{0: {"crit_damage": -4, "crit_rate": 5, "energy_recharge": 7, "atk_percent": 3}},
		},
		{
			name: "two_main_union", slot: 2,
			restriction: SlotDomain{Mains: []string{"atk_percent", "energy_recharge"}, Required: supportMask(3), Excluded: supportMask(2)},
			weights:     LinearWeights{0: {"atk_percent": 12, "energy_recharge": -3, "crit_rate": 5, "crit_damage": -4}},
		},
		{
			name: "default_mains_with_main_exclusion", slot: 2,
			restriction: SlotDomain{Required: supportMask(1), Excluded: supportMask(2)},
			weights:     LinearWeights{0: {"atk_percent": 5, "energy_recharge": -8, "crit_rate": 4, "crit_damage": -2}},
		},
	}
	totalOracle := 0
	for _, tc := range cases {
		domain, seed := supportSingleSlotFixture(tc.slot, tc.restriction)
		loOracle, hiOracle, count := exhaustiveSupportSlot(t, tc.weights, domain, seed, tc.slot)
		if count == 0 {
			t.Fatalf("%s oracle domain empty", tc.name)
		}
		totalOracle += count
		lo, hi, err := Support45(tc.weights, domain)
		if err != nil {
			t.Fatal(err)
		}
		if math.Abs(lo-loOracle) > 1e-9*(1+math.Abs(loOracle)) ||
			math.Abs(hi-hiOracle) > 1e-9*(1+math.Abs(hiOracle)) {
			t.Fatalf("%s support [%.12g,%.12g], oracle [%.12g,%.12g]", tc.name, lo, hi, loOracle, hiOracle)
		}
		assertSupportWitness(t, tc.weights, domain, false, loOracle)
		assertSupportWitness(t, tc.weights, domain, true, hiOracle)
	}
	marginalReceipt(t, map[string]any{
		"case": "support45_single_slot_unions", "cases": len(cases),
		"oracle_vertices": totalOracle,
		"nanoseconds":     time.Since(started).Nanoseconds(),
	})
}

func TestSupport45AllNegativeLeavesOptionalUnitsUnspent(t *testing.T) {
	weights := LinearWeights{}
	weights[0] = map[string]float64{}
	for _, key := range StatKeys {
		weights[0][key] = -1
	}
	domain, seed := supportSingleSlotFixture(0, SlotDomain{Mains: []string{"hp"}, Required: supportMask(2)})
	loOracle, hiOracle, _ := exhaustiveSupportSlot(t, weights, domain, seed, 0)
	// The target-slot oracle leaves the four other fixed slots at zero extras.
	// For a negative linear objective, each of those slots independently puts
	// five optional units on its most negative mandatory line for the minimum.
	for slot := 1; slot < 5; slot++ {
		worst := 0.0
		for _, stat := range seed.Lines[0][slot] {
			worst = math.Max(worst, Values[stat])
		}
		loOracle -= 5 * worst
	}
	lo, hi, err := Support45(weights, domain)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(lo-loOracle) > 1e-8 || math.Abs(hi-hiOracle) > 1e-8 {
		t.Fatalf("all-negative support [%.12g,%.12g], oracle [%.12g,%.12g]", lo, hi, loOracle, hiOracle)
	}
	state, value, err := SupportWitness45(weights, domain, true)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(value-hiOracle) > 1e-8 || state.Validate(45, true) != nil {
		t.Fatalf("invalid all-negative maximum witness %.12g", value)
	}
	for actor := range state.Upgrades {
		for slot := range state.Upgrades[actor] {
			for _, u := range state.Upgrades[actor][slot] {
				if u != 0 {
					t.Fatal("all-negative maximum spent an optional upgrade")
				}
			}
		}
	}
}

func TestSupport45RejectsUnsupportedConstraintsAndNumbers(t *testing.T) {
	cases := []struct {
		name    string
		weights LinearWeights
		domain  SupportDomain
	}{
		{name: "nan", weights: LinearWeights{0: {"atk": math.NaN()}}},
		{name: "infinite", weights: LinearWeights{0: {"crit_rate": math.Inf(1)}}},
		{name: "unknown", weights: LinearWeights{0: {"unknown_stat": 1}}},
		{name: "overflow", weights: LinearWeights{0: {"hp": math.MaxFloat64}}},
		{name: "required_too_many", domain: SupportDomain{0: {0: {Required: supportMask(0, 1, 2, 3, 4)}}}},
		{name: "required_excluded", domain: SupportDomain{0: {0: {Required: supportMask(3), Excluded: supportMask(3)}}}},
		{name: "out_of_range_mask", domain: SupportDomain{0: {0: {Excluded: uint16(1) << 10}}}},
		{name: "main_excludes_required", domain: SupportDomain{0: {0: {Required: supportMask(8)}}}},
		{name: "invalid_main", domain: SupportDomain{0: {2: {Mains: []string{"hp"}}}}},
		{name: "empty_main_list", domain: SupportDomain{0: {2: {Mains: []string{}}}}},
		{name: "too_few_lines", domain: SupportDomain{0: {0: {Excluded: supportMask(0, 1, 2, 3, 4, 5)}}}},
	}
	for _, tc := range cases {
		if _, _, err := Support45(tc.weights, tc.domain); err == nil {
			t.Fatalf("%s unexpectedly accepted", tc.name)
		}
	}
}
