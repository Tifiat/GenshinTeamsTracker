package theoryalloc

import (
	"context"
	"testing"
)

func controlMains() [4][5]string {
	return [4][5]string{
		{"hp", "atk", "def_percent", "geo_damage_bonus", "crit_damage"},
		{"hp", "atk", "hp_percent", "hp_percent", "crit_damage"},
		{"hp", "atk", "hp_percent", "hydro_damage_bonus", "crit_damage"},
		{"hp", "atk", "def_percent", "geo_damage_bonus", "crit_rate"},
	}
}

func controlGradient() [4][10]float64 {
	var gradient [4][10]float64
	for actor := range gradient {
		for stat := range gradient[actor] {
			gradient[actor][stat] = float64(stat + 1)
		}
	}
	return gradient
}

func controlObjective(rewardColumbinaPyroGoblet bool) Objective {
	gradient := controlGradient()
	return func(state State, _ bool) (float64, [4][10]float64, error) {
		value := 0.0
		for actor, rolls := range state.Rolls() {
			for stat, amount := range rolls {
				value += gradient[actor][stat] * amount
			}
		}
		if rewardColumbinaPyroGoblet && state.Mains[1][3] == "pyro_damage_bonus" {
			value += 1000
		}
		return value, gradient, nil
	}
}

func TestRunConstrainedKeepsFixedCaseMainsAndFull45(t *testing.T) {
	baselineMains := controlMains()
	baseline := Seed(baselineMains, controlGradient(), 0, constrainedBudget)
	caseMains := baselineMains
	caseMains[2][3] = "hp_percent"
	result, err := RunConstrained(context.Background(), controlObjective(false), baseline, caseMains, [4][5]bool{})
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Starts) != ConstrainedStartCount {
		t.Fatalf("got %d independent starts; want %d", len(result.Starts), ConstrainedStartCount)
	}
	if result.Work.MainSweeps != 0 || result.Work.MainCandidates != 0 {
		t.Fatalf("fixed-main case searched main choices: %+v", result.Work)
	}
	if result.FixedMainsState.Mains != caseMains || result.State.Mains != caseMains {
		t.Fatal("fixed case changed one or more mains")
	}
	for _, start := range result.Starts {
		if start.State.Mains != caseMains || start.FixedMainsState.Mains != caseMains || start.FinalState.Mains != caseMains {
			t.Fatalf("start %d escaped fixed mains", start.Variant)
		}
		if err := ValidateFull45(start.State); err != nil {
			t.Fatalf("start %d is not a full45 witness: %v", start.Variant, err)
		}
		if err := ValidateFull45(start.FixedMainsState); err != nil {
			t.Fatalf("fixed checkpoint %d is not a full45 witness: %v", start.Variant, err)
		}
		if err := ValidateFull45(start.FinalState); err != nil {
			t.Fatalf("final start %d is not a full45 witness: %v", start.Variant, err)
		}
	}
	if result.Starts[0].State == baseline {
		t.Fatal("saved baseline was reused as the first warm start")
	}
	if result.DeltaFromBaseline != result.Value-result.BaselineValue {
		t.Fatalf("baseline delta %g does not match value difference", result.DeltaFromBaseline)
	}
}

func TestRunConstrainedUnlocksOnlyColumbinaMains(t *testing.T) {
	mains := controlMains()
	baseline := Seed(mains, controlGradient(), 0, constrainedBudget)
	var unlocked [4][5]bool
	unlocked[1][2], unlocked[1][3], unlocked[1][4] = true, true, true
	result, err := RunConstrained(context.Background(), controlObjective(true), baseline, mains, unlocked)
	if err != nil {
		t.Fatal(err)
	}
	if result.Work.MainSweeps != constrainedMainSweeps*ConstrainedStartCount || result.Work.MainCandidates == 0 {
		t.Fatalf("unlocked main work was not counted: %+v", result.Work)
	}
	if result.State.Mains[1][3] != "pyro_damage_bonus" {
		t.Fatalf("permitted Columbina goblet move was not found: %q", result.State.Mains[1][3])
	}
	for actor := range mains {
		for slot := range mains[actor] {
			if (actor != 1 || slot < 2) && result.State.Mains[actor][slot] != mains[actor][slot] {
				t.Fatalf("forbidden main changed at actor %d slot %d: %q", actor, slot, result.State.Mains[actor][slot])
			}
		}
	}
	if err := ValidateFull45(result.State); err != nil {
		t.Fatalf("constrained result is not a full45 witness: %v", err)
	}
}

func TestConstrainedMainMoveRejectsForbiddenAndRepairsMatchingLine(t *testing.T) {
	state := Seed(controlMains(), controlGradient(), 0, constrainedBudget)
	// Construct a legal prior witness where the requested new main already
	// appears as a distinct substat line. ReplaceMain must repair that line.
	state.Lines[0][3] = [4]int{5, 0, 1, 2}
	if err := ValidateFull45(state); err != nil {
		t.Fatalf("test witness is invalid before main move: %v", err)
	}
	before := state
	if got, err := constrainedReplaceMain(state, 0, 3, "atk", controlGradient()); err == nil || got != before {
		t.Fatalf("forbidden goblet main was not rejected without mutation: state changed=%v err=%v", got != before, err)
	}
	candidate, err := constrainedReplaceMain(state, 0, 3, "def_percent", controlGradient())
	if err != nil {
		t.Fatal(err)
	}
	if candidate.Mains[0][3] != "def_percent" {
		t.Fatalf("legal main was not applied: %q", candidate.Mains[0][3])
	}
	if err := ValidateFull45(candidate); err != nil {
		t.Fatalf("repaired candidate is not full45: %v", err)
	}
	for _, stat := range candidate.Lines[0][3] {
		if statKeys[stat] == candidate.Mains[0][3] {
			t.Fatal("main move left an illegal main-matching substat line")
		}
	}
	if candidate == before {
		t.Fatal("matching-line main move did not repair the witness")
	}
}

func TestConstrainedStartSchemesStayEqualAndFull45AcrossCases(t *testing.T) {
	firstMains := controlMains()
	secondMains := firstMains
	secondMains[2][3] = "hp_percent"
	for _, mains := range [][4][5]string{firstMains, secondMains} {
		seeds, fallback, err := constrainedSeeds(mains, [4][10]float64{})
		if err != nil {
			t.Fatal(err)
		}
		if len(seeds) != ConstrainedStartCount {
			t.Fatalf("got %d seed schemes; want %d", len(seeds), ConstrainedStartCount)
		}
		if !fallback {
			t.Fatal("zero-gradient diversity seed should use the full-budget fallback")
		}
		for i, seed := range seeds {
			if seed.Mains != mains {
				t.Fatalf("scheme %d did not use this case's legal mains", i)
			}
			if err := ValidateFull45(seed); err != nil {
				t.Fatalf("case seed scheme %d is not full45: %v", i, err)
			}
		}
	}
}

func TestRunConstrainedRejectsUnlockingFlowerOrPlume(t *testing.T) {
	mains := controlMains()
	baseline := Seed(mains, controlGradient(), 0, constrainedBudget)
	var unlocked [4][5]bool
	unlocked[1][0] = true
	if _, err := RunConstrained(context.Background(), controlObjective(false), baseline, mains, unlocked); err == nil {
		t.Fatal("fixed flower main was accepted as unlocked")
	}
	if err := validateConstrainedPolicy(mains, [4][5]bool{{true, false, false, false, false}}); err == nil {
		t.Fatal("fixed flower main policy was accepted")
	}
}

func TestRunConstrainedHonorsCallerCancellation(t *testing.T) {
	mains := controlMains()
	baseline := Seed(mains, controlGradient(), 0, constrainedBudget)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := RunConstrained(ctx, controlObjective(false), baseline, mains, [4][5]bool{}); err == nil {
		t.Fatal("pre-canceled shared context was ignored")
	}
}
